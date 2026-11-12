"""Cartella "magica" in Nextcloud (facoltativa): i PDF messi li' vengono elaborati da soli.

Si attiva con NEXTCLOUD_URL, NEXTCLOUD_USER e NEXTCLOUD_PASSWORD (meglio una password per le app),
oppure NEXTCLOUD_PASSWORD_FILE con il percorso di un file che contiene la password.
Dentro la cartella NEXTCLOUD_MAGIC_DIR (predefinita "Plico") c'e' una sottocartella per ogni catena
con "cartella magica" attiva nella pagina /admin. Un PDF messo in "Plico/<catena>/" viene elaborato:
il risultato va in "<catena>/Fatti/", l'originale in "<catena>/Originali/". Se qualcosa va storto,
l'originale va in "<catena>/Errori/" con un file .txt che spiega il motivo.
Il controllo si ripete ogni NEXTCLOUD_POLL_SECONDS secondi (predefinito 60).
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from base64 import b64encode
from pathlib import Path

from fastapi import HTTPException

import i18n
import ops

log = logging.getLogger("plico.magic")
DONE, ORIGINALS, ERRORS = "Fatti", "Originali", "Errori"


class WebDAV:
    def __init__(self, url: str, user: str, password: str):
        self.root = f"{url.rstrip('/')}/remote.php/dav/files/{urllib.parse.quote(user)}"
        self.base_path = urllib.parse.urlparse(self.root).path
        self.auth = "Basic " + b64encode(f"{user}:{password}".encode()).decode()

    def _url(self, path: str) -> str:
        return self.root + urllib.parse.quote("/" + path.strip("/"))

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None, timeout=120):
        req = urllib.request.Request(self._url(path), body, {"Authorization": self.auth, **(headers or {})}, method=method)
        return urllib.request.urlopen(req, timeout=timeout)

    def listdir(self, path: str) -> list[tuple[str, bool, int]]:
        """[(nome, e' una cartella, dimensione)]"""
        body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:getcontentlength/></d:prop></d:propfind>'
        with self.request("PROPFIND", path, body, {"Depth": "1", "Content-Type": "application/xml"}) as r:
            tree = ET.fromstring(r.read())
        out, me = [], urllib.parse.quote("/" + path.strip("/")).rstrip("/")
        for resp in tree.findall("{DAV:}response"):
            href = urllib.parse.urlparse(resp.findtext("{DAV:}href")).path
            rel = href[len(self.base_path):].rstrip("/")
            if rel == me:
                continue
            is_dir = resp.find(".//{DAV:}collection") is not None
            size = int(resp.findtext(".//{DAV:}getcontentlength") or 0)
            out.append((urllib.parse.unquote(rel.rsplit("/", 1)[-1]), is_dir, size))
        return out

    def mkdir(self, path: str):
        try:
            self.request("MKCOL", path).close()
        except urllib.error.HTTPError as e:
            if e.code != 405:  # 405 = esiste gia'
                raise

    def download(self, path: str, dst: Path):
        with self.request("GET", path, timeout=600) as r, dst.open("wb") as f:
            shutil.copyfileobj(r, f)

    def upload(self, src: Path, path: str):
        with src.open("rb") as f:
            self.request("PUT", path, f.read(), {"Content-Type": "application/octet-stream"}, timeout=600).close()

    def move(self, src: str, dst: str):
        self.request("MOVE", src, headers={"Destination": self._url(dst), "Overwrite": "F"}).close()


def config() -> dict | None:
    url, user, pw = (os.environ.get(k, "") for k in ("NEXTCLOUD_URL", "NEXTCLOUD_USER", "NEXTCLOUD_PASSWORD"))
    pw_file = os.environ.get("NEXTCLOUD_PASSWORD_FILE", "")
    if not pw and pw_file:
        try:
            pw = Path(pw_file).read_text("utf-8").strip()
        except OSError as e:
            log.error("NEXTCLOUD_PASSWORD_FILE non leggibile: %s", e)
    if not (url and user and pw):
        return None
    return {"url": url, "user": user, "password": pw, "dir": os.environ.get("NEXTCLOUD_MAGIC_DIR", "Plico").strip("/"),
            "poll": max(15, int(os.environ.get("NEXTCLOUD_POLL_SECONDS", "60")))}


def free_name(names: set[str], name: str) -> str:
    if name not in names:
        return name
    stem, dot, ext = name.rpartition(".")
    stem, ext = (stem, "." + ext) if dot else (name, "")
    k = 2
    while f"{stem} ({k}){ext}" in names:
        k += 1
    return f"{stem} ({k}){ext}"


def process_once(dav: WebDAV, root: str, chains: list[dict], work: Path, stats: dict) -> int:
    """Un giro: elabora i PDF presenti nelle cartelle delle catene magiche. Restituisce quanti ne ha fatti."""
    done = 0
    dav.mkdir(root)
    for c in chains:
        if not c.get("magic"):
            continue
        folder = f"{root}/{c['name']}"
        dav.mkdir(folder)
        entries = dav.listdir(folder)
        pdfs = [n for n, is_dir, size in entries if not is_dir and n.lower().endswith(".pdf") and size > 0]
        if not pdfs:
            continue
        for sub in (DONE, ORIGINALS, ERRORS):
            dav.mkdir(f"{folder}/{sub}")
        done_names = {n for n, _, _ in dav.listdir(f"{folder}/{DONE}")}
        orig_names = {n for n, _, _ in dav.listdir(f"{folder}/{ORIGINALS}")}
        for name in pdfs:
            job = Path(tempfile.mkdtemp(dir=work))
            try:
                src = job / "in.pdf"
                dav.download(f"{folder}/{name}", src)
                try:
                    res = ops.chain(src, job, c["steps"], name=Path(name).stem)
                except HTTPException as e:
                    msg = i18n.t(e.detail, "it")
                    err_names = {n for n, _, _ in dav.listdir(f"{folder}/{ERRORS}")}
                    target = free_name(err_names, name)
                    dav.move(f"{folder}/{name}", f"{folder}/{ERRORS}/{target}")
                    note = job / "errore.txt"
                    note.write_text(f"{name}: {msg}\n", "utf-8")
                    dav.upload(note, f"{folder}/{ERRORS}/{target}.txt")
                    stats["errors"] += 1
                    continue
                out_name = free_name(done_names, name)
                dav.upload(res.path, f"{folder}/{DONE}/{out_name}")
                done_names.add(out_name)
                orig = free_name(orig_names, name)
                dav.move(f"{folder}/{name}", f"{folder}/{ORIGINALS}/{orig}")
                orig_names.add(orig)
                done += 1
                stats["processed"] += 1
            finally:
                shutil.rmtree(job, ignore_errors=True)
    return done


async def loop(get_chains, work: Path, heavy, stats: dict):
    cfg = config()
    if not cfg:
        return
    dav = WebDAV(cfg["url"], cfg["user"], cfg["password"])
    work.mkdir(parents=True, exist_ok=True)
    log.warning("Cartella magica attiva: %s/%s, ogni %s s", cfg["url"], cfg["dir"], cfg["poll"])
    while True:
        try:
            await heavy(process_once, dav, cfg["dir"], get_chains(), work, stats)
            stats.update(last_run=int(time.time()), last_error=None)
        except Exception as e:  # rete, credenziali, Nextcloud spento: si riprova al giro dopo
            stats.update(last_run=int(time.time()), last_error=str(e)[:300])
            log.error("Cartella magica: %s", e)
        await asyncio.sleep(cfg["poll"])

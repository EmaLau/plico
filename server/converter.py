"""Word, Excel, PowerPoint <-> PDF con un server Universal Converter (facoltativo).

Si attiva impostando CONVERTER_URL (es. http://converter:8080). Il file viene mandato al convertitore,
si aspetta il risultato e lo si scarica; il lavoro viene poi cancellato dal convertitore.
CONVERTER_API_KEY, se impostata, viene mandata nell'intestazione `apikey`.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from ops import Result, fail, media_for

URL = os.environ.get("CONVERTER_URL", "").rstrip("/")
API_KEY = os.environ.get("CONVERTER_API_KEY", "")
TIMEOUT = int(os.environ.get("CONVERTER_TIMEOUT", "600"))

OFFICE_IN = {".doc", ".docx", ".odt", ".rtf", ".txt", ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp"}
PDF_TO = {"docx", "odt", "xlsx", "pptx", "txt"}


def enabled() -> bool:
    return bool(URL)


def _request(method: str, path: str, body: bytes | None = None, headers: dict | None = None, timeout: int = 60):
    h = {"User-Agent": "universal-pdf", **(headers or {})}
    if API_KEY:
        h["apikey"] = API_KEY
    req = urllib.request.Request(URL + path, body, h, method=method)
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", "")
        except Exception:
            detail = ""
        fail(f"Il convertitore ha risposto con un errore: {detail or e.code}", 502)
    except OSError:
        fail("Il convertitore non risponde", 502)


def convert(src: Path, out_dir: Path, target: str, base: str = "documento") -> Result:
    if not enabled():
        fail("Conversione Office non attiva su questo server (CONVERTER_URL)", 501)
    ext = src.suffix.lower()
    if target == "pdf":
        if ext not in OFFICE_IN:
            fail("Formato non supportato: scegli un documento Word, Excel, PowerPoint o OpenDocument")
    elif target in PDF_TO:
        if ext != ".pdf":
            fail("Scegli un PDF")
    else:
        fail("Formato di destinazione sconosciuto")
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="target"\r\n\r\n{target}\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{base}{ext}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n').encode() + src.read_bytes() + f"\r\n--{b}--\r\n".encode()
    with _request("POST", "/api/jobs", body, {"Content-Type": f"multipart/form-data; boundary={b}"}) as r:
        job = json.loads(r.read())
    jid = job["id"]
    try:
        deadline = time.time() + TIMEOUT
        while True:
            with _request("GET", f"/api/jobs/{jid}") as r:
                st = json.loads(r.read())
            if st.get("state") == "done":
                break
            if st.get("state") == "error":
                fail(f"Il convertitore non e' riuscito a convertire il file: {st.get('error') or ''}".strip(), 502)
            if time.time() > deadline:
                fail("Il convertitore: tempo scaduto", 504)
            time.sleep(1)
        res = out_dir / f"{base}.{target}"
        with _request("GET", f"/api/jobs/{jid}/download", timeout=TIMEOUT) as r, res.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        return Result(res, media_for(res))
    finally:
        try:
            _request("DELETE", f"/api/jobs/{jid}", timeout=10).close()
        except Exception:
            pass

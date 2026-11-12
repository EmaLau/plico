"""Chiavi API e area admin di Universal-PDF, sul modello di Gokapi.

- Le chiavi hanno un nome e dei permessi (uno per strumento). Si creano nella pagina /admin, protetta
  da una password; la chiave intera si vede una sola volta e sul disco resta solo il suo hash SHA-256.
- Gli script mandano la chiave nell'intestazione `apikey`. La pagina web non ne ha bisogno: quando la
  si apre riceve un cookie di sessione firmato.
- Con API_REQUIRE_KEY=true le chiamate senza chiave e senza la sessione della pagina vengono rifiutate.
  Chi apre prima la pagina ottiene comunque la sessione: e' un modo per mettere ordine, non una difesa
  contro chi raggiunge il servizio.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.security import APIKeyHeader

# permesso -> descrizione mostrata nella pagina admin
PERMISSIONS = {
    "info": "Informazioni e anteprime",
    "merge": "Unisci",
    "split": "Dividi ed estrai",
    "organize": "Riordina, ruota ed elimina pagine",
    "rotate": "Ruota tutte le pagine",
    "compress": "Comprimi",
    "img2pdf": "Immagini in PDF",
    "pdf2img": "PDF in immagini",
    "protect": "Proteggi e sblocca",
    "stamp": "Numeri di pagina e filigrana",
}

SESSION_COOKIE = "updf_session"
ADMIN_COOKIE = "updf_admin"
SESSION_TTL = 30 * 24 * 3600  # la pagina rinnova la sessione a ogni apertura
ADMIN_TTL = 12 * 3600
LAST_USED_EVERY = 60  # secondi tra un salvataggio e l'altro dell'"ultimo uso"

header_scheme = APIKeyHeader(name="apikey", auto_error=False,
                             description="Chiave creata nella pagina /admin")


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "si", "on")


class KeyStore:
    def __init__(self, data_dir: Path):
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "apikeys.json"
        self.lock = threading.Lock()
        self.require_key = _truthy(os.environ.get("API_REQUIRE_KEY"))
        self.secret = self._load_secret()
        self.admin_password = self._load_admin_password()
        self.keys: dict[str, dict] = {}
        self._dirty = False
        self._last_save = 0.0
        self._failures: dict[str, list[float]] = {}
        if self.file.exists():
            self.keys = json.loads(self.file.read_text("utf-8")).get("keys", {})

    # ------------------------------------------------------------ configurazione

    def _load_secret(self) -> bytes:
        f = self.dir / "secret"
        if not f.exists():
            self._write_private(f, secrets.token_hex(32))
        return bytes.fromhex(f.read_text().strip())

    def _load_admin_password(self) -> str:
        pw = os.environ.get("UPDF_ADMIN_PASSWORD", "")
        f = self.dir / "admin-password"
        if not pw and f.exists():
            pw = f.read_text("utf-8").strip()
        return pw

    @staticmethod
    def _write_private(path: Path, text: str):
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_password)

    # ------------------------------------------------------------ chiavi

    def _save(self):
        self._write_private(self.file, json.dumps({"keys": self.keys}, indent=1, ensure_ascii=False))
        self._dirty = False
        self._last_save = time.time()

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def create(self, name: str, perms: list[str]) -> tuple[str, dict]:
        name = name.strip()[:80]
        if not name:
            raise HTTPException(400, "Dai un nome alla chiave")
        perms = self._clean_perms(perms)
        key = "updf_" + secrets.token_urlsafe(32)
        kid = secrets.token_hex(6)
        rec = {"name": name, "hash": self._hash(key), "prefix": key[:10], "perms": perms,
               "created": int(time.time()), "last_used": None}
        with self.lock:
            self.keys[kid] = rec
            self._save()
        return key, self.public(kid, rec)

    def update(self, kid: str, name: str | None, perms: list[str] | None) -> dict:
        with self.lock:
            rec = self.keys.get(kid)
            if not rec:
                raise HTTPException(404, "Chiave inesistente")
            if name is not None and name.strip():
                rec["name"] = name.strip()[:80]
            if perms is not None:
                rec["perms"] = self._clean_perms(perms)
            self._save()
            return self.public(kid, rec)

    def delete(self, kid: str):
        with self.lock:
            if self.keys.pop(kid, None) is None:
                raise HTTPException(404, "Chiave inesistente")
            self._save()

    def list(self) -> list[dict]:
        with self.lock:
            return [self.public(k, r) for k, r in sorted(self.keys.items(), key=lambda kv: kv[1]["created"])]

    @staticmethod
    def public(kid: str, rec: dict) -> dict:
        return {"id": kid, "name": rec["name"], "prefix": rec["prefix"], "perms": rec["perms"],
                "created": rec["created"], "last_used": rec["last_used"]}

    @staticmethod
    def _clean_perms(perms: list[str]) -> list[str]:
        bad = [p for p in perms if p not in PERMISSIONS]
        if bad:
            raise HTTPException(400, f"Permessi sconosciuti: {', '.join(bad)}")
        return [p for p in PERMISSIONS if p in perms]

    def check_key(self, key: str, perm: str):
        h = self._hash(key)
        with self.lock:
            for rec in self.keys.values():
                if hmac.compare_digest(rec["hash"], h):
                    break
            else:
                raise HTTPException(401, "Chiave API non valida")
            if perm not in rec["perms"]:
                raise HTTPException(403, f"La chiave non ha il permesso '{perm}'")
            now = time.time()
            rec["last_used"] = int(now)
            if now - self._last_save >= LAST_USED_EVERY:
                self._save()
            else:
                self._dirty = True

    def flush(self):
        with self.lock:
            if self._dirty:
                self._save()

    # ------------------------------------------------------------ token firmati (cookie)

    def sign(self, kind: str, ttl: int) -> str:
        exp = str(int(time.time()) + ttl)
        mac = hmac.new(self.secret, f"{kind}.{exp}".encode(), hashlib.sha256).hexdigest()
        return f"{exp}.{mac}"

    def verify(self, kind: str, token: str | None) -> bool:
        if not token or "." not in token:
            return False
        exp, mac = token.split(".", 1)
        good = hmac.new(self.secret, f"{kind}.{exp}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, good) and exp.isdigit() and int(exp) > time.time()

    # ------------------------------------------------------------ login admin

    def login(self, ip: str, password: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(ip, []) if now - t < 600]
        if len(recent) >= 5:
            raise HTTPException(429, "Troppi tentativi: riprova tra qualche minuto")
        if self.admin_enabled and hmac.compare_digest(password.encode(), self.admin_password.encode()):
            self._failures.pop(ip, None)
            return True
        recent.append(now)
        self._failures[ip] = recent
        return False


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"

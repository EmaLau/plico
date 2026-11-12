"""Catene di operazioni salvate sul server (es. comprimi + numera + proteggi).

Si creano nella pagina /admin e si usano dalla pagina web, dall'API (/api/chain con `chain`) e dalla
cartella "magica" di Nextcloud. Sono salvate in DATA_DIR/chains.json.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
from pathlib import Path

from fastapi import HTTPException

import ops

DEFAULTS = [
    {"name": "Comprimi e numera", "steps": [{"op": "compress", "level": "medium"},
                                            {"op": "stamp", "numbers": True, "num_fmt": "{n} / {tot}"}]},
    {"name": "Archivio (OCR + PDF/A)", "steps": [{"op": "ocr", "lang": "ita+eng"}, {"op": "pdfa"}]},
    {"name": "Pulisci prima di condividere", "steps": [{"op": "metadata", "clean": True}, {"op": "compress", "level": "medium"}]},
]


class ChainStore:
    def __init__(self, data_dir: Path):
        self.file = data_dir / "chains.json"
        self.lock = threading.Lock()
        if self.file.exists():
            self.items = json.loads(self.file.read_text("utf-8")).get("chains", [])
        else:
            self.items = [{"id": secrets.token_hex(4), "magic": False, **c} for c in DEFAULTS]

    def _save(self):
        tmp = self.file.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"chains": self.items}, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.file)

    @staticmethod
    def _check(name: str, steps) -> tuple[str, list]:
        name = re.sub(r'[\\/:*?"<>|]+', " ", (name or "").strip())[:60].strip()
        if not name:
            raise HTTPException(400, "Dai un nome alla catena")
        if not isinstance(steps, list) or not steps or len(steps) > 12:
            raise HTTPException(400, "Catena di operazioni non valida")
        for s in steps:
            if not isinstance(s, dict) or s.get("op") not in ops.CHAIN_OPS:
                raise HTTPException(400, f"Operazione sconosciuta nella catena: {s.get('op') if isinstance(s, dict) else s}")
            if s["op"] == "protect" and not s.get("password"):
                raise HTTPException(400, "Scrivi una password")
        return name, steps

    def list(self) -> list[dict]:
        with self.lock:
            return [dict(c) for c in self.items]

    def public(self) -> list[dict]:
        """Senza le password delle operazioni 'proteggi'."""
        out = []
        for c in self.list():
            steps = [{k: ("•••" if k in ("password", "owner") else v) for k, v in s.items()} for s in c["steps"]]
            out.append({**c, "steps": steps})
        return out

    def get(self, key: str) -> dict:
        with self.lock:
            for c in self.items:
                if c["id"] == key or c["name"].lower() == key.lower():
                    return dict(c)
        raise HTTPException(404, "Catena inesistente")

    def create(self, name: str, steps, magic: bool = False) -> dict:
        name, steps = self._check(name, steps)
        with self.lock:
            if any(c["name"].lower() == name.lower() for c in self.items):
                raise HTTPException(400, "Esiste gia' una catena con questo nome")
            c = {"id": secrets.token_hex(4), "name": name, "steps": steps, "magic": bool(magic)}
            self.items.append(c)
            self._save()
            return dict(c)

    def update(self, cid: str, name: str | None = None, steps=None, magic: bool | None = None) -> dict:
        with self.lock:
            for c in self.items:
                if c["id"] == cid:
                    n, s = self._check(name if name is not None else c["name"], steps if steps is not None else c["steps"])
                    c.update(name=n, steps=s)
                    if magic is not None:
                        c["magic"] = bool(magic)
                    self._save()
                    return dict(c)
        raise HTTPException(404, "Catena inesistente")

    def delete(self, cid: str):
        with self.lock:
            before = len(self.items)
            self.items = [c for c in self.items if c["id"] != cid]
            if len(self.items) == before:
                raise HTTPException(404, "Catena inesistente")
            self._save()

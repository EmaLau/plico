"""Configurazione dei test: il server viene importato con cartelle temporanee e una password admin di prova."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
ADMIN_PASSWORD = "test-admin-password"

_work = Path(tempfile.mkdtemp(prefix="plico-test-"))
os.environ.update(WORK_DIR=str(_work), DATA_DIR=str(_work / "data"), PLICO_ADMIN_PASSWORD=ADMIN_PASSWORD,
                  API_REQUIRE_KEY="false", PLICO_ADMIN_LOGIN="true")
sys.path.insert(0, str(SERVER))

import fitz  # noqa: E402
import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def make_pdf(n=5, width=595, height=842, rotate_third=False) -> bytes:
    d = fitz.open()
    for i in range(n):
        p = d.new_page(width=width, height=height)
        p.insert_text((72, 120), f"Pagina {i + 1}", fontsize=40)
        p.draw_rect(fitz.Rect(72, 200, 523, 700), color=(0, 0, 1), fill=(0.8, 0.9, 1))
        if rotate_third and i == 2:
            p.set_rotation(90)
    return d.tobytes()


def make_png(w=400, h=300) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    pix.set_rect(pix.irect, (200, 60, 60))
    return pix.tobytes("png")


def pages(data: bytes) -> int:
    return fitz.open("pdf", data).page_count


@pytest.fixture
def client():
    with TestClient(server.app, headers={"Accept-Language": "it-IT,it;q=0.9"}) as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/admin/api/login", json={"password": ADMIN_PASSWORD},
                    headers={"X-Requested-With": "plico"})
    assert r.status_code == 200
    client.headers["X-Requested-With"] = "plico"
    return client


@pytest.fixture(autouse=True)
def clean_state():
    """Ogni test parte senza chiavi e con le impostazioni predefinite."""
    server.KEYS.keys.clear()
    server.KEYS.require_key = False
    server.KEYS.admin_login = True
    server.KEYS._failures.clear()
    yield
    leftovers = list(server.TMP.glob("*")) if server.TMP.exists() else []
    assert not leftovers, f"cartelle temporanee rimaste: {leftovers}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    """Il server vero, con uvicorn, per la prova dell'interfaccia nel browser."""
    port = _free_port()
    work = Path(tempfile.mkdtemp(prefix="plico-live-"))
    env = {**os.environ, "WORK_DIR": str(work), "DATA_DIR": str(work / "data")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1",
                             "--port", str(port), "--no-access-log"], cwd=SERVER, env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("il server non e' partito")
    yield url
    proc.terminate()
    proc.wait(10)

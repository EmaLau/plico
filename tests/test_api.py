"""Test dell'API con TestClient, senza container. Comprendono i casi dell'audit del 2026-11-12."""
import asyncio
import io
import time
import zipfile

import fitz
import pikepdf
import pytest

import ops
import server
from conftest import make_pdf, make_png, pages

PDF = make_pdf(5, rotate_third=True)
PDF2 = make_pdf(2)
PNG = make_png()


def up(name, data, field="file"):
    return (field, (name, data, "application/octet-stream"))


# ---------------------------------------------------------------- strumenti

def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_info(client):
    r = client.post("/api/info", files=[up("a.pdf", PDF)])
    assert r.status_code == 200
    assert r.json() == {"pages": 5, "encrypted": False, "size": len(PDF), "metadata": {}, "form_fields": 0}


def test_info_garbage(client):
    r = client.post("/api/info", files=[up("x.pdf", b"not a pdf")])
    assert r.status_code == 400


def test_thumbs(client):
    r = client.post("/api/thumbs", files=[up("a.pdf", PDF)], data={"width": "120"})
    p = r.json()["pages"]
    assert len(p) == 5 and p[0]["img"].startswith("data:image/jpeg;base64,") and p[2]["rot"] == 90


def test_merge_pdf_and_image(client):
    r = client.post("/api/merge", files=[up("a.pdf", PDF, "files"), up("b.pdf", PDF2, "files"), up("c.png", PNG, "files")])
    assert r.status_code == 200 and pages(r.content) == 8


def test_merge_needs_two_files(client):
    assert client.post("/api/merge", files=[up("a.pdf", PDF, "files")]).status_code == 400


@pytest.mark.parametrize("data,count", [({"mode": "ranges", "ranges": "1-2, 4, 5-"}, 3),
                                        ({"mode": "every", "every": "2"}, 3)])
def test_split(client, data, count):
    r = client.post("/api/split", data=data, files=[up("a.pdf", PDF)])
    assert r.status_code == 200 and len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == count


def test_extract(client):
    r = client.post("/api/split", data={"mode": "ranges", "ranges": "1,3", "merge_out": "true"}, files=[up("a.pdf", PDF)])
    assert r.status_code == 200 and pages(r.content) == 2


def test_split_bad_range(client):
    r = client.post("/api/split", data={"mode": "ranges", "ranges": "9"}, files=[up("a.pdf", PDF)])
    assert r.status_code == 400 and "fuori dal documento" in r.json()["detail"]


def test_organize(client):
    r = client.post("/api/organize", data={"pages": "[[4,0],[0,90],[2,0]]"}, files=[up("a.pdf", PDF)])
    d = fitz.open("pdf", r.content)
    assert d.page_count == 3 and d[1].rotation == 90 and "Pagina 5" in d[0].get_text()


def test_rotate(client):
    d = fitz.open("pdf", client.post("/api/rotate", data={"angle": "90"}, files=[up("a.pdf", PDF)]).content)
    assert d[0].rotation == 90 and d[2].rotation == 180


def test_compress_never_bigger(client):
    r = client.post("/api/compress", data={"level": "high"}, files=[up("a.pdf", PDF)])
    assert r.status_code == 200 and pages(r.content) == 5
    assert int(r.headers["x-size-after"]) <= int(r.headers["x-size-before"])


def test_img2pdf(client):
    r = client.post("/api/img2pdf", data={"page": "a4", "margin": "20"},
                    files=[up("x.png", PNG, "files"), up("y.png", PNG, "files")])
    d = fitz.open("pdf", r.content)
    assert d.page_count == 2 and round(d[0].rect.width) == 842  # immagine orizzontale -> A4 orizzontale


def test_pdf2img(client):
    r = client.post("/api/pdf2img", data={"format": "jpg", "dpi": "72"}, files=[up("a.pdf", PDF)])
    assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 5
    r = client.post("/api/pdf2img", data={"format": "png", "dpi": "72", "ranges": "3"}, files=[up("a.pdf", PDF)])
    assert r.content[:4] == b"\x89PNG" and "x-dpi-reduced" not in r.headers


def test_protect_and_unlock(client):
    prot = client.post("/api/protect", data={"password": "segreta"}, files=[up("a.pdf", PDF)]).content
    assert fitz.open("pdf", prot).needs_pass
    assert client.post("/api/unlock", data={"password": "sbagliata"}, files=[up("p.pdf", prot)]).status_code == 400
    r = client.post("/api/unlock", data={"password": "segreta"}, files=[up("p.pdf", prot)])
    assert not fitz.open("pdf", r.content).needs_pass and pages(r.content) == 5
    assert client.post("/api/thumbs", files=[up("p.pdf", prot)]).status_code == 400


def test_stamp(client):
    r = client.post("/api/stamp", data={"numbers": "true", "num_fmt": "Pagina {n} di {tot}", "watermark": "BOZZA €ñ"},
                    files=[up("a.pdf", PDF)])
    d = fitz.open("pdf", r.content)
    assert all("di 5" in p.get_text() and "BOZZA" in p.get_text() for p in d)


# ---------------------------------------------------------------- casi dell'audit

def test_huge_page_is_rendered_smaller(client):
    """Un PDF minuscolo con una pagina di 14.400 pt non deve chiedere un'immagine da 3,6 miliardi di pixel."""
    huge = make_pdf(1, width=14400, height=14400)
    assert len(huge) < 2000
    r = client.post("/api/pdf2img", data={"format": "jpg", "dpi": "300"}, files=[up("huge.pdf", huge)])
    pix = fitz.Pixmap(r.content)
    assert r.headers["x-dpi-reduced"] == "1" and pix.width * pix.height <= ops.MAX_PAGE_PX


def test_open_password_does_not_give_owner_rights(client):
    r = client.post("/api/protect", data={"password": "segreta", "allow_edit": "false"}, files=[up("a.pdf", PDF)])
    pdf = pikepdf.open(io.BytesIO(r.content), password="segreta")
    assert not pdf.owner_password_matched and not pdf.allow.modify_other
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(io.BytesIO(r.content), password="segreta\x01owner")


def test_upload_limit_gives_413(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_MB", 1)
    r = client.post("/api/info", files=[up("big.pdf", b"0" * (2 << 20))])
    assert r.status_code == 413 and "troppo grande" in r.json()["detail"]


def test_no_upload_limit_by_default(client):
    assert server.MAX_MB == 0
    r = client.post("/api/info", files=[up("big.pdf", PDF + b"\n" * (3 << 20))])
    assert r.status_code == 200


def test_output_limit_gives_413(client, monkeypatch):
    monkeypatch.setattr(ops, "MAX_OUT", 100_000)
    r = client.post("/api/pdf2img", data={"format": "png", "dpi": "150"}, files=[up("a.pdf", PDF)])
    assert r.status_code == 413 and "risultato supera" in r.json()["detail"]


def test_internal_error_hides_details(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("dettaglio segreto /percorso/interno")
    monkeypatch.setattr(ops, "parse_ranges", boom)
    with pytest.raises(RuntimeError):  # TestClient rilancia l'eccezione del server...
        client.post("/api/split", data={"mode": "ranges", "ranges": "1"}, files=[up("a.pdf", PDF)])
    from fastapi.testclient import TestClient
    with TestClient(server.app, raise_server_exceptions=False) as c:  # ...questo invece vede la risposta
        r = c.post("/api/split", data={"mode": "ranges", "ranges": "1"}, files=[up("a.pdf", PDF)])
    assert r.status_code == 500 and "segreto" not in r.text


def test_queue_runs_at_most_max_parallel(monkeypatch):
    monkeypatch.setattr(server, "MAX_PARALLEL", 2)
    monkeypatch.setattr(server, "_slots", None)
    running, peak = 0, 0

    def job():
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        time.sleep(0.05)
        running -= 1

    async def main():
        await asyncio.gather(*(server.heavy(job) for _ in range(6)))

    asyncio.run(main())
    monkeypatch.setattr(server, "_slots", None)
    assert peak == 2


def test_uploads_are_spooled_in_work_dir():
    import tempfile
    assert tempfile.gettempdir() == str(server.SPOOL)


# ---------------------------------------------------------------- chiavi API e area admin

def create_key(admin, perms, name="test"):
    r = admin.post("/admin/api/keys", json={"name": name, "perms": perms})
    assert r.status_code == 200
    return r.json()


def test_page_sets_session_cookie(client):
    r = client.get("/")
    assert r.status_code == 200 and "plico_session" in r.cookies


def test_invalid_key(client):
    r = client.post("/api/info", files=[up("a.pdf", PDF)], headers={"apikey": "plico_sbagliata"})
    assert r.status_code == 401


def test_key_permissions(admin, client):
    k = create_key(admin, ["merge"])
    assert k["key"].startswith("plico_") and "hash" not in k
    h = {"apikey": k["key"]}
    r = client.post("/api/merge", files=[up("a.pdf", PDF, "files"), up("b.pdf", PDF2, "files")], headers=h)
    assert r.status_code == 200
    r = client.post("/api/rotate", files=[up("a.pdf", PDF)], headers=h)
    assert r.status_code == 403
    listed = admin.get("/admin/api/keys").json()["keys"][0]
    assert listed["last_used"] and listed["prefix"] == k["key"][:10] and "key" not in listed
    admin.put(f"/admin/api/keys/{k['id']}", json={"perms": ["merge", "rotate"]})
    assert client.post("/api/rotate", files=[up("a.pdf", PDF)], headers=h).status_code == 200
    admin.delete(f"/admin/api/keys/{k['id']}")
    assert client.post("/api/rotate", files=[up("a.pdf", PDF)], headers=h).status_code == 401


def test_key_stored_only_as_hash(admin):
    k = create_key(admin, ["info"])
    assert k["key"] not in server.KEYS.file.read_text()


def test_unknown_permission(admin):
    assert admin.post("/admin/api/keys", json={"name": "x", "perms": ["root"]}).status_code == 400


def test_require_key_switch(admin):
    from fastapi.testclient import TestClient
    assert admin.put("/admin/api/settings", json={"require_key": True}).json()["require_key"]
    with TestClient(server.app) as anon:
        assert anon.post("/api/info", files=[up("a.pdf", PDF)]).status_code == 401
        anon.get("/")  # la pagina web da' la sessione
        assert anon.post("/api/info", files=[up("a.pdf", PDF)]).status_code == 200
    admin.put("/admin/api/settings", json={"require_key": False})
    with TestClient(server.app) as anon:
        assert anon.post("/api/info", files=[up("a.pdf", PDF)]).status_code == 200


def test_admin_requires_login(client):
    assert client.get("/admin/api/keys").status_code == 401
    r = client.post("/admin/api/login", json={"password": "no"}, headers={"X-Requested-With": "plico"})
    assert r.status_code == 401


def test_admin_write_needs_header(admin):
    del admin.headers["X-Requested-With"]
    assert admin.post("/admin/api/keys", json={"name": "x", "perms": ["info"]}).status_code == 403


def test_admin_login_rate_limit(client, monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(server.asyncio, "sleep", lambda s: real_sleep(0))
    h = {"X-Requested-With": "plico"}
    codes = [client.post("/admin/api/login", json={"password": "no"}, headers=h).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_admin_login_switch(admin):
    from fastapi.testclient import TestClient
    admin.put("/admin/api/settings", json={"admin_login": False})
    with TestClient(server.app) as anon:
        assert anon.get("/admin/api/keys").status_code == 200
        r = anon.put("/admin/api/settings", json={"admin_login": True}, headers={"X-Requested-With": "plico"})
        assert r.status_code == 200
    with TestClient(server.app) as anon:
        assert anon.get("/admin/api/keys").status_code == 401


def test_apidocs(client):
    assert client.get("/apidocs").status_code == 200
    spec = client.get("/apidocs/openapi.json").json()
    assert "apikey" in str(spec["components"]["securitySchemes"]) and "/api/merge" in spec["paths"]
    assert not any(p.startswith("/admin") for p in spec["paths"])


# ---------------------------------------------------------------- lingue e sicurezza

@pytest.mark.parametrize("accept,expected", [(None, "outside the document"), ("en-US,en;q=0.9", "outside the document"),
                                             ("it-IT,it;q=0.9,en;q=0.8", "fuori dal documento")])
def test_error_language(accept, expected):
    from fastapi.testclient import TestClient
    headers = {"Accept-Language": accept} if accept else {}
    with TestClient(server.app) as c:
        r = c.post("/api/split", data={"mode": "ranges", "ranges": "9"}, files=[up("a.pdf", PDF)], headers=headers)
    assert expected in r.json()["detail"]


def test_every_italian_message_has_a_translation():
    """Ogni messaggio passato a fail() o HTTPException ha la sua traduzione inglese."""
    import re
    import i18n
    src = "".join((server.STATIC.parent / f).read_text()
                  for f in ("server.py", "apikeys.py", "ops.py", "chains.py", "converter.py", "magic.py"))
    msgs = re.findall(r'(?:fail\(|HTTPException\(\d+, )f?"([^"]+)"', src)
    assert len(msgs) > 60
    missing = [m for m in msgs if i18n.t(re.sub(r"\{[^}]*\}", "1", m), "en") == re.sub(r"\{[^}]*\}", "1", m)]
    assert not missing, f"mancano le traduzioni di: {missing}"


def test_security_headers(client):
    h = client.get("/").headers
    assert "frame-ancestors 'none'" in h["content-security-policy"] and "'unsafe-inline'" not in h["content-security-policy"].split("style-src")[0]
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "cdn.jsdelivr.net" in client.get("/apidocs").headers["content-security-policy"]
    assert client.post("/api/info", files=[up("x.pdf", b"x")]).headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("headers,status", [({"Origin": "http://evil.example"}, 403),
                                            ({"Sec-Fetch-Site": "cross-site"}, 403),
                                            ({"Origin": "null"}, 403),
                                            ({"Origin": "http://testserver"}, 200),
                                            ({"Sec-Fetch-Site": "same-origin"}, 200),
                                            ({}, 200)])
def test_cross_site_requests(client, headers, status):
    r = client.post("/api/info", files=[up("a.pdf", PDF)], headers=headers)
    assert r.status_code == status


def test_cross_site_admin_login_rejected(client):
    r = client.post("/admin/api/login", json={"password": "x"},
                    headers={"X-Requested-With": "plico", "Origin": "http://evil.example"})
    assert r.status_code == 403


def test_i18n_script_served(client):
    r = client.get("/static/i18n.js")
    assert r.status_code == 200 and "PLICO_I18N" in r.text


def test_docs_page(client):
    """/docs: pagina generata da docs/web/build.sh (in CI e nell'immagine); senza, 404 con un messaggio chiaro."""
    import base64, hashlib, re
    if not (server.STATIC / "docs-en.html").exists():
        r = client.get("/docs?lang=en")
        assert r.status_code == 404 and "build.sh" in r.json()["detail"]
        return
    r = client.get("/docs?lang=en")
    assert r.status_code == 200 and "<title>Plico — Documentation</title>" in r.text
    assert 'id="toc"' in r.text and "docs?lang=it" in r.text
    script = re.search(r"<script>(.*?)</script>", r.text, re.S).group(1)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert digest in r.headers["content-security-policy"]
    r = client.get("/docs", headers={"Accept-Language": "it-IT,it;q=0.9"})
    assert "<title>Plico — Documentazione</title>" in r.text
    assert "https://github.com/EmaLau/plico/blob/main/docs/api.md" in r.text

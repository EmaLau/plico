"""Test delle funzioni della fase 4 (OCR, firma, moduli, annotazioni, oscuramento, confronto, pagine,
opuscolo, riparazione, PDF/A, metadati, estrazione, scanner, catene, Office, cartella magica)."""
import io
import json
import shutil
import zipfile
from pathlib import Path

import fitz
import pikepdf
import pytest

import chains
import converter
import magic
import server
from conftest import make_pdf, make_png, pages

PDF = make_pdf(4)
needs_ocr = pytest.mark.skipif(not (shutil.which("ocrmypdf") and shutil.which("tesseract")), reason="serve Tesseract")


def up(name, data, field="file"):
    return (field, (name, data, "application/octet-stream"))


def text_pdf(lines, size=(595, 842)) -> bytes:
    d = fitz.open()
    p = d.new_page(width=size[0], height=size[1])
    for k, line in enumerate(lines):
        p.insert_text((72, 100 + k * 30), line, fontsize=14)
    return d.tobytes()


def form_pdf() -> bytes:
    d = fitz.open()
    p = d.new_page()
    for name, kind, rect in (("nome", fitz.PDF_WIDGET_TYPE_TEXT, (72, 72, 300, 92)),
                             ("accetto", fitz.PDF_WIDGET_TYPE_CHECKBOX, (72, 110, 90, 128))):
        w = fitz.Widget()
        w.field_name, w.field_type, w.rect = name, kind, fitz.Rect(rect)
        p.add_widget(w)
    return d.tobytes()


def scanned_pdf(text="Fattura numero 12345") -> bytes:
    """Una pagina che contiene solo un'immagine del testo (come una scansione)."""
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 120), text, fontsize=28)
    pix = p.get_pixmap(dpi=200)
    s = fitz.open()
    s.new_page().insert_image(fitz.Rect(0, 0, 595, 842), stream=pix.tobytes("png"))
    return s.tobytes()


# ---------------------------------------------------------------- OCR e PDF/A

@needs_ocr
def test_ocr_makes_text_searchable(client):
    src = scanned_pdf()
    assert fitz.open("pdf", src)[0].get_text().strip() == ""
    r = client.post("/api/ocr", data={"lang": "ita+eng"}, files=[up("scan.pdf", src)])
    assert r.status_code == 200 and "12345" in fitz.open("pdf", r.content)[0].get_text()


def test_ocr_rejects_unknown_language(client):
    r = client.post("/api/ocr", data={"lang": "klingon"}, files=[up("a.pdf", PDF)])
    assert r.status_code == 400


@needs_ocr
def test_pdfa(client):
    r = client.post("/api/pdfa", files=[up("a.pdf", PDF)])
    assert r.status_code == 200
    with pikepdf.open(io.BytesIO(r.content)) as pdf:
        assert "pdfaid" in str(pdf.open_metadata())


# ---------------------------------------------------------------- firma, annotazioni, moduli

def test_sign(client):
    sig = make_png(200, 80)
    r = client.post("/api/sign", data={"page": "1", "box": "[0.5, 0.8, 0.9, 0.9]"},
                    files=[up("a.pdf", PDF), up("firma.png", sig, "image")])
    d = fitz.open("pdf", r.content)
    assert r.status_code == 200 and len(d[1].get_images()) == 1 and len(d[0].get_images()) == 0
    bbox = d[1].get_image_rects(d[1].get_images()[0][0])[0]
    assert bbox.y0 > d[1].rect.height * 0.75


def test_sign_needs_image(client):
    r = client.post("/api/sign", files=[up("a.pdf", PDF), up("firma.png", b"", "image")])
    assert r.status_code in (400, 422)


def test_annotate_and_flatten(client):
    items = [{"page": 0, "type": "highlight", "box": [0.1, 0.1, 0.6, 0.16]},
             {"page": 0, "type": "text", "box": [0.1, 0.3, 0.6, 0.36], "text": "Nota importante", "color": "#2563eb"},
             {"page": 1, "type": "arrow", "from": [0.2, 0.5], "to": [0.6, 0.5]},
             {"page": 1, "type": "note", "at": [0.8, 0.1], "text": "Ricontrollare"},
             {"page": 2, "type": "ink", "points": [[0.1, 0.1], [0.2, 0.2], [0.3, 0.1]]},
             {"page": 3, "type": "rect", "box": [0.1, 0.1, 0.4, 0.4], "color": "#e5322d"}]
    r = client.post("/api/annotate", data={"items": json.dumps(items)}, files=[up("a.pdf", PDF)])
    d = fitz.open("pdf", r.content)
    kinds = sorted(a.type[1] for p in d for a in p.annots())
    assert kinds == sorted(["Highlight", "FreeText", "Line", "Text", "Ink", "Square"])
    r = client.post("/api/annotate", data={"items": json.dumps(items[1:2]), "flatten": "true"}, files=[up("a.pdf", PDF)])
    d = fitz.open("pdf", r.content)
    assert not list(d[0].annots()) and "Nota importante" in d[0].get_text()


def test_forms_list_fill_flatten(client):
    src = form_pdf()
    fields = client.post("/api/forms", files=[up("m.pdf", src)]).json()["fields"]
    assert {f["name"] for f in fields} == {"nome", "accetto"}
    r = client.post("/api/fill", data={"values": json.dumps({"nome": "Mario Rossi", "accetto": True})},
                    files=[up("m.pdf", src)])
    assert r.headers["x-fields-filled"] == "2"
    d = fitz.open("pdf", r.content)
    vals = {w.field_name: w.field_value for w in d[0].widgets()}
    assert vals["nome"] == "Mario Rossi" and vals["accetto"] not in ("Off", False, "")
    r = client.post("/api/fill", data={"values": json.dumps({"nome": "Mario Rossi"}), "flatten": "true"},
                    files=[up("m.pdf", src)])
    d = fitz.open("pdf", r.content)
    assert not list(d[0].widgets()) and "Mario Rossi" in d[0].get_text()


# ---------------------------------------------------------------- oscuramento e confronto

def test_redact_removes_text(client):
    src = text_pdf(["Mario Rossi", "mail: mario.rossi@example.com", "IBAN IT60X0542811101000000123456", "resto"])
    r = client.post("/api/redact", data={"terms": "Mario Rossi", "presets": "email,iban"}, files=[up("a.pdf", src)])
    t = fitz.open("pdf", r.content)[0].get_text()
    assert r.status_code == 200 and int(r.headers["x-redactions"]) >= 3
    assert "Rossi" not in t and "example.com" not in t and "IT60" not in t and "resto" in t


def test_redact_area(client):
    src = text_pdf(["segreto in alto", "", "", "", "", "", "", "", "visibile"])
    r = client.post("/api/redact", data={"areas": json.dumps([{"page": 0, "box": [0, 0, 1, 0.14]}])}, files=[up("a.pdf", src)])
    t = fitz.open("pdf", r.content)[0].get_text()
    assert "segreto" not in t and "visibile" in t


def test_redact_needs_something(client):
    assert client.post("/api/redact", files=[up("a.pdf", PDF)]).status_code == 400


def test_compare(client):
    a = text_pdf(["Il prezzo e' di 100 euro", "consegna lunedi'"])
    b = text_pdf(["Il prezzo e' di 120 euro", "consegna lunedi'"])
    r = client.post("/api/compare", files=[up("v1.pdf", a, "file_a"), up("v2.pdf", b, "file_b")])
    d = fitz.open("pdf", r.content)
    assert r.headers["x-pages-changed"] == "1" and d.page_count == 2
    assert "100" in d[0].get_text() and "120" in d[0].get_text()
    r = client.post("/api/compare", files=[up("v1.pdf", a, "file_a"), up("v1b.pdf", a, "file_b")])
    assert r.headers["x-pages-changed"] == "0"


# ---------------------------------------------------------------- pagine e stampa

def test_resize_to_a4(client):
    src = make_pdf(2, width=300, height=500)
    d = fitz.open("pdf", client.post("/api/pages", data={"mode": "resize", "paper": "a4"}, files=[up("a.pdf", src)]).content)
    assert [round(d[0].rect.width), round(d[0].rect.height)] == [595, 842]


def test_crop_and_trim(client):
    d = fitz.open("pdf", client.post("/api/pages", data={"mode": "crop", "top": "10", "left": "10", "right": "10",
                                                         "bottom": "10"}, files=[up("a.pdf", PDF)]).content)
    assert round(d[0].rect.width) == round(595 - 2 * 10 * 72 / 25.4)
    d = fitz.open("pdf", client.post("/api/pages", data={"mode": "trim"}, files=[up("a.pdf", PDF)]).content)
    assert d[0].rect.width < 500 and d[0].rect.height < 700


@pytest.mark.parametrize("n,sheets", [(2, 2), (4, 1)])
def test_nup(client, n, sheets):
    d = fitz.open("pdf", client.post("/api/nup", data={"n": str(n)}, files=[up("a.pdf", PDF)]).content)
    assert d.page_count == sheets


def test_booklet(client):
    d = fitz.open("pdf", client.post("/api/nup", data={"mode": "booklet"}, files=[up("a.pdf", make_pdf(6))]).content)
    assert d.page_count == 4 and d[0].rect.width > d[0].rect.height  # 8 facciate -> 2 fogli fronte-retro
    first = d[0].get_text()
    assert "Pagina 1" in first  # foglio esterno: ultima (vuota) e prima


def test_stamp_header_footer_logo(client):
    r = client.post("/api/stamp", data={"header": "Documento {file}", "footer": "Pagina {n} di {tot} · {date}"},
                    files=[up("relazione.pdf", PDF), up("logo.png", make_png(100, 100), "wm_image")])
    d = fitz.open("pdf", r.content)
    assert "Documento relazione" in d[0].get_text() and "Pagina 2 di 4" in d[1].get_text() and d[0].get_images()


# ---------------------------------------------------------------- riparazione, metadati, estrazione

def test_repair_broken_xref(client):
    broken = PDF.replace(b"startxref", b"startxrXX")  # tabella degli oggetti rovinata
    r = client.post("/api/repair", files=[up("rotto.pdf", broken)])
    assert r.status_code == 200 and pages(r.content) == 4 and r.headers["x-repair-method"]


def test_repair_hopeless(client):
    assert client.post("/api/repair", files=[up("x.pdf", b"%PDF-1.4 niente")]).status_code == 422


def test_metadata_set_and_clean(client):
    r = client.post("/api/metadata", data={"title": "Relazione", "author": "Ema"}, files=[up("a.pdf", PDF)])
    m = fitz.open("pdf", r.content).metadata
    assert m["title"] == "Relazione" and m["author"] == "Ema"
    info = client.post("/api/info", files=[up("a.pdf", r.content)]).json()
    assert info["metadata"]["title"] == "Relazione"
    r = client.post("/api/metadata", data={"clean": "true"}, files=[up("a.pdf", r.content)])
    m = fitz.open("pdf", r.content).metadata
    assert not m["title"] and not m["author"]


def test_extract_text_and_images(client):
    r = client.post("/api/extract", data={"kind": "text"}, files=[up("a.pdf", PDF)])
    assert r.headers["content-type"].startswith("text/plain") and "Pagina 3" in r.text
    d = fitz.open()
    d.new_page().insert_image(fitz.Rect(50, 50, 250, 200), stream=make_png(200, 150))
    r = client.post("/api/extract", data={"kind": "images"}, files=[up("a.pdf", d.tobytes())])
    assert len(zipfile.ZipFile(io.BytesIO(r.content)).namelist()) == 1
    assert client.post("/api/extract", data={"kind": "images"}, files=[up("a.pdf", PDF)]).status_code == 422


# ---------------------------------------------------------------- scanner

def test_scan_straightens_photo(client):
    import cv2
    import numpy as np
    photo = np.full((900, 1200, 3), 60, np.uint8)  # tavolo scuro
    pts = np.array([[300, 120], [900, 160], [950, 820], [250, 780]], np.int32)  # foglio storto
    cv2.fillPoly(photo, [pts], (245, 245, 245))
    cv2.putText(photo, "SCAN", (450, 480), cv2.FONT_HERSHEY_SIMPLEX, 3, (20, 20, 20), 8)
    ok, jpg = cv2.imencode(".jpg", photo)
    r = client.post("/api/scan", data={"mode": "bw"}, files=[up("foto.jpg", jpg.tobytes(), "files"),
                                                             up("foto2.jpg", jpg.tobytes(), "files")])
    assert r.status_code == 200 and pages(r.content) == 2 and r.headers["x-pages-straightened"] == "2"


# ---------------------------------------------------------------- catene e piu' file

def test_chain_one_file(client):
    steps = [{"op": "stamp", "numbers": True, "num_fmt": "{n}/{tot}"}, {"op": "protect", "password": "x"}]
    r = client.post("/api/chain", data={"steps": json.dumps(steps)}, files=[up("a.pdf", PDF, "files")])
    d = fitz.open("pdf", r.content)
    assert d.needs_pass and d.authenticate("x") and "2/4" in d[1].get_text()


def test_chain_many_files_zip(client):
    steps = [{"op": "rotate", "angle": 90}]
    r = client.post("/api/chain", data={"steps": json.dumps(steps)},
                    files=[up("a.pdf", PDF, "files"), up("a.pdf", PDF, "files"), up("b.pdf", make_pdf(1), "files")])
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert sorted(names) == ["a (2).pdf", "a.pdf", "b.pdf"]


def test_chain_errors(client):
    r = client.post("/api/chain", data={"steps": json.dumps([{"op": "rm -rf"}])}, files=[up("a.pdf", PDF, "files")])
    assert r.status_code == 400
    r = client.post("/api/chain", data={"steps": json.dumps([{"op": "compress", "bogus": 1}])}, files=[up("a.pdf", PDF, "files")])
    assert r.status_code == 400


def test_chain_key_needs_step_permissions(admin, client):
    k = admin.post("/admin/api/keys", json={"name": "c", "perms": ["chain", "rotate"]}).json()["key"]
    h = {"apikey": k}
    ok = client.post("/api/chain", data={"steps": json.dumps([{"op": "rotate"}])}, files=[up("a.pdf", PDF, "files")], headers=h)
    no = client.post("/api/chain", data={"steps": json.dumps([{"op": "compress"}])}, files=[up("a.pdf", PDF, "files")], headers=h)
    assert ok.status_code == 200 and no.status_code == 403


def test_saved_chains(admin, client):
    c = admin.post("/admin/api/chains", json={"name": "Ruota e numera", "steps": [{"op": "rotate"}, {"op": "stamp", "numbers": True}]}).json()
    assert any(x["name"] == "Ruota e numera" for x in client.get("/api/chains").json()["chains"])
    r = client.post("/api/chain", data={"chain": "Ruota e numera"}, files=[up("a.pdf", PDF, "files")])
    assert fitz.open("pdf", r.content)[0].rotation == 90
    p = admin.post("/admin/api/chains", json={"name": "Segreto", "steps": [{"op": "protect", "password": "pw123"}]}).json()
    assert "pw123" not in json.dumps(client.get("/api/chains").json())
    admin.put(f"/admin/api/chains/{p['id']}", json={"steps": [{"op": "protect", "password": "•••"}], "magic": True})
    assert server.CHAINS.get(p["id"])["steps"][0]["password"] == "pw123"
    admin.delete(f"/admin/api/chains/{c['id']}")
    admin.delete(f"/admin/api/chains/{p['id']}")
    assert client.post("/api/chain", data={"chain": "Ruota e numera"}, files=[up("a.pdf", PDF, "files")]).status_code == 404


# ---------------------------------------------------------------- Office (con un convertitore finto)

def test_office_disabled(client):
    assert client.get("/api/features").json()["office"] in (True, False)
    if not converter.enabled():
        assert client.post("/api/office", data={"target": "pdf"}, files=[up("a.docx", b"x")]).status_code == 501


def test_office_with_fake_converter(client, monkeypatch, tmp_path):
    calls = []

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.close()

    def fake_request(method, path, body=None, headers=None, timeout=60):
        calls.append((method, path))
        if method == "POST":
            assert b'name="target"\r\n\r\npdf' in body
            return FakeResp(b'{"id": "j1", "state": "queued"}')
        if path == "/api/jobs/j1":
            return FakeResp(b'{"state": "done"}')
        if path.endswith("/download"):
            return FakeResp(PDF)
        return FakeResp(b"{}")

    monkeypatch.setattr(converter, "URL", "http://fake")
    monkeypatch.setattr(converter, "_request", fake_request)
    r = client.post("/api/office", data={"target": "pdf"}, files=[up("lettera.docx", b"PK fake docx")])
    assert r.status_code == 200 and pages(r.content) == 4
    assert ("DELETE", "/api/jobs/j1") in calls
    assert client.post("/api/office", data={"target": "pdf"}, files=[up("a.exe", b"x")]).status_code == 400


# ---------------------------------------------------------------- cartella magica (Nextcloud finto)

class FakeDAV:
    def __init__(self):
        self.files = {}  # percorso -> bytes; le cartelle sono percorsi con valore None

    def mkdir(self, path):
        self.files.setdefault(path.strip("/"), None)

    def listdir(self, path):
        path = path.strip("/")
        out = []
        for k, v in self.files.items():
            if k.rsplit("/", 1)[0] == path and k != path:
                out.append((k.rsplit("/", 1)[1], v is None, len(v or b"")))
        return out

    def download(self, path, dst: Path):
        dst.write_bytes(self.files[path.strip("/")])

    def upload(self, src: Path, path):
        self.files[path.strip("/")] = src.read_bytes()

    def move(self, src, dst):
        self.files[dst.strip("/")] = self.files.pop(src.strip("/"))


def test_magic_folder(tmp_path):
    dav = FakeDAV()
    chs = [{"name": "Numera", "magic": True, "steps": [{"op": "stamp", "numbers": True}]},
           {"name": "Spenta", "magic": False, "steps": [{"op": "rotate"}]}]
    stats = {"processed": 0, "errors": 0}
    magic.process_once(dav, "Universal-PDF", chs, tmp_path, stats)  # crea le cartelle
    assert "Universal-PDF/Numera" in dav.files and "Universal-PDF/Spenta" not in dav.files
    dav.files["Universal-PDF/Numera/fattura.pdf"] = PDF
    dav.files["Universal-PDF/Numera/rotto.pdf"] = b"%PDF niente"
    n = magic.process_once(dav, "Universal-PDF", chs, tmp_path, stats)
    assert n == 1 and stats == {"processed": 1, "errors": 1}
    out = dav.files["Universal-PDF/Numera/Fatti/fattura.pdf"]
    assert "1" in fitz.open("pdf", out)[0].get_text()
    assert "Universal-PDF/Numera/Originali/fattura.pdf" in dav.files
    assert "Universal-PDF/Numera/Errori/rotto.pdf" in dav.files
    assert "non e' un PDF valido" in dav.files["Universal-PDF/Numera/Errori/rotto.pdf.txt"].decode()
    assert "Universal-PDF/Numera/fattura.pdf" not in dav.files
    # un secondo file con lo stesso nome non sovrascrive il primo
    dav.files["Universal-PDF/Numera/fattura.pdf"] = PDF
    magic.process_once(dav, "Universal-PDF", chs, tmp_path, stats)
    assert "Universal-PDF/Numera/Fatti/fattura (2).pdf" in dav.files


def test_chain_store_defaults(tmp_path):
    s = chains.ChainStore(tmp_path)
    assert len(s.list()) == 3 and not any(c["magic"] for c in s.list())
    with pytest.raises(Exception):
        s.create("x", [{"op": "protect"}])  # senza password


def test_new_endpoints_documented(client):
    paths = client.get("/apidocs/openapi.json").json()["paths"]
    for p in ("ocr", "pdfa", "repair", "metadata", "extract", "pages", "nup", "sign", "annotate", "forms", "fill",
              "redact", "compare", "scan", "office", "chain"):
        assert f"/api/{p}" in paths, p


def test_magic_password_file(tmp_path, monkeypatch):
    f = tmp_path / "nc-password"
    f.write_text("segreta\n")
    monkeypatch.setenv("NEXTCLOUD_URL", "http://nc.example")
    monkeypatch.setenv("NEXTCLOUD_USER", "utente")
    monkeypatch.delenv("NEXTCLOUD_PASSWORD", raising=False)
    monkeypatch.setenv("NEXTCLOUD_PASSWORD_FILE", str(f))
    assert magic.config()["password"] == "segreta"
    monkeypatch.setenv("NEXTCLOUD_PASSWORD_FILE", str(tmp_path / "manca"))
    assert magic.config() is None

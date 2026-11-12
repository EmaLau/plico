"""Prova tutti gli strumenti contro il server in esecuzione: docker exec <container> python3 /app/selftest.py
Salva i risultati in /work/selftest/ per poterli guardare."""
import io, json, os, sys, uuid, urllib.request, zipfile
from pathlib import Path

import fitz
import pikepdf

URL = os.environ.get("SELFTEST_URL", "http://127.0.0.1:8080")
WORK = Path(os.environ.get("WORK_DIR", "/work"))
OUT = WORK / "selftest"; OUT.mkdir(parents=True, exist_ok=True)


def make_pdf(n=5, rotate_third=True):
    d = fitz.open()
    for i in range(n):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 120), f"Pagina {i+1}", fontsize=40)
        p.draw_rect(fitz.Rect(72, 200, 523, 700), color=(0, 0, 1), fill=(0.8, 0.9, 1))
        if rotate_third and i == 2:
            p.set_rotation(90)
    return d.tobytes()


def make_png():
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False)
    pix.set_rect(pix.irect, (200, 60, 60))
    return pix.tobytes("png")


def post(path, fields=None, files=()):
    b = uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in (fields or {}).items():
        body.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, name, data in files:
        body.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                   f'Content-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    body.write(f"--{b}--\r\n".encode())
    req = urllib.request.Request(URL + path, body.getvalue(), {"Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


ok = True
def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("OK  " if cond else "ERR ") + name + (f"  {extra}" if extra else ""))


pdf, pdf2, png = make_pdf(5), make_pdf(2, False), make_png()
pages = lambda b: fitz.open("pdf", b).page_count

s, b, _ = post("/api/info", files=[("file", "a.pdf", pdf)]); check("info", s == 200 and json.loads(b)["pages"] == 5)
s, b, _ = post("/api/thumbs", files=[("file", "a.pdf", pdf)]); check("thumbs", s == 200 and len(json.loads(b)["pages"]) == 5)
s, b, _ = post("/api/merge", files=[("files", "a.pdf", pdf), ("files", "b.pdf", pdf2), ("files", "c.png", png)])
check("merge", s == 200 and pages(b) == 8); (OUT / "merge.pdf").write_bytes(b)
s, b, _ = post("/api/split", {"mode": "ranges", "ranges": "1-2, 4, 5-"}, [("file", "a.pdf", pdf)])
check("split ranges", s == 200 and len(zipfile.ZipFile(io.BytesIO(b)).namelist()) == 3)
s, b, _ = post("/api/split", {"mode": "every", "every": "2"}, [("file", "a.pdf", pdf)])
check("split every", s == 200 and len(zipfile.ZipFile(io.BytesIO(b)).namelist()) == 3)
s, b, _ = post("/api/split", {"mode": "ranges", "ranges": "1,3", "merge_out": "true"}, [("file", "a.pdf", pdf)])
check("extract", s == 200 and pages(b) == 2)
s, b, _ = post("/api/split", {"mode": "ranges", "ranges": "9"}, [("file", "a.pdf", pdf)])
check("split bad range -> 400", s == 400, json.loads(b)["detail"])
s, b, _ = post("/api/organize", {"pages": "[[4,0],[0,90],[2,0]]"}, [("file", "a.pdf", pdf)])
d = fitz.open("pdf", b) if s == 200 else None
check("organize", d and d.page_count == 3 and d[1].rotation == 90 and "Pagina 5" in d[0].get_text())
s, b, _ = post("/api/rotate", {"angle": "90"}, [("file", "a.pdf", pdf)])
d = fitz.open("pdf", b); check("rotate", d[0].rotation == 90 and d[2].rotation == 180)
s, b, h = post("/api/compress", {"level": "high"}, [("file", "m.pdf", (OUT / "merge.pdf").read_bytes())])
check("compress", s == 200 and pages(b) == 8, f"{h.get('x-size-before')} -> {h.get('x-size-after')}")
s, b, _ = post("/api/img2pdf", {"page": "a4", "margin": "20"}, [("files", "x.png", png), ("files", "y.png", png)])
check("img2pdf", s == 200 and pages(b) == 2); (OUT / "img2pdf.pdf").write_bytes(b)
s, b, _ = post("/api/pdf2img", {"format": "jpg", "dpi": "72"}, [("file", "a.pdf", pdf)])
check("pdf2img zip", s == 200 and len(zipfile.ZipFile(io.BytesIO(b)).namelist()) == 5)
s, b, _ = post("/api/pdf2img", {"format": "png", "dpi": "72", "ranges": "3"}, [("file", "a.pdf", pdf)])
check("pdf2img one", s == 200 and b[:4] == b"\x89PNG")
s, b, _ = post("/api/protect", {"password": "segreta"}, [("file", "a.pdf", pdf)])
check("protect", s == 200 and fitz.open("pdf", b).needs_pass); prot = b
s, b, _ = post("/api/unlock", {"password": "sbagliata"}, [("file", "p.pdf", prot)]); check("unlock wrong -> 400", s == 400)
s, b, _ = post("/api/unlock", {"password": "segreta"}, [("file", "p.pdf", prot)])
check("unlock", s == 200 and not fitz.open("pdf", b).needs_pass and pages(b) == 5)
s, b, _ = post("/api/thumbs", files=[("file", "p.pdf", prot)]); check("locked pdf -> 400", s == 400)
s, b, _ = post("/api/stamp", {"numbers": "true", "num_fmt": "Pagina {n} di {tot}", "watermark": "BOZZA"},
               [("file", "a.pdf", pdf)])
d = fitz.open("pdf", b) if s == 200 else None
check("stamp", d and all("di 5" in p.get_text() and "BOZZA" in p.get_text() for p in d))
if d:
    (OUT / "stamp.pdf").write_bytes(b)
    for i in (0, 2):
        d[i].get_pixmap(dpi=50).save(OUT / f"stamp_p{i+1}.png")
s, b, _ = post("/api/merge", files=[("files", "a.pdf", pdf)]); check("merge one file -> 400", s == 400)
s, b, _ = post("/api/info", files=[("file", "x.pdf", b"not a pdf")]); check("garbage -> 400", s == 400)
# Pagina enorme (14.400 pt): l'immagine va ridotta, non deve far finire la memoria
d = fitz.open(); d.new_page(width=14400, height=14400); huge = d.tobytes()
s, b, h = post("/api/pdf2img", {"format": "jpg", "dpi": "300"}, [("file", "huge.pdf", huge)])
px = fitz.Pixmap(b) if s == 200 else None
max_px = float(os.environ.get("MAX_PAGE_MPX", "50")) * 1e6
check("pdf2img huge page reduced", px and px.width * px.height <= max_px and h.get("x-dpi-reduced") == "1",
      f"{px.width}x{px.height}" if px else str(s))
# La password per aprire non deve dare i permessi del proprietario
s, b, _ = post("/api/protect", {"password": "segreta", "allow_edit": "false"}, [("file", "a.pdf", pdf)])
u = pikepdf.open(io.BytesIO(b), password="segreta")
try:
    o = pikepdf.open(io.BytesIO(b), password="segreta\x01owner"); old_owner = o.owner_password_matched
except pikepdf.PasswordError:
    old_owner = False
check("protect random owner password", s == 200 and not u.owner_password_matched and not old_owner
      and not u.allow.modify_other)
# File oltre il limite su /api/info: 413, non "PDF non valido"
max_mb = int(os.environ.get("MAX_UPLOAD_MB", "2048"))
if max_mb <= 200:
    s, b, _ = post("/api/info", files=[("file", "big.pdf", b"0" * ((max_mb + 1) << 20))])
    check("info too large -> 413", s == 413, json.loads(b)["detail"])
else:
    print(f"SKIP info too large -> 413  (MAX_UPLOAD_MB={max_mb}, prova solo con limiti fino a 200 MB)")
left = list((WORK / "upd").glob("*")) if (WORK / "upd").exists() else []
check("no leftover temp files", not left, str(left))
print("TUTTO OK" if ok else "CI SONO ERRORI")
sys.exit(0 if ok else 1)

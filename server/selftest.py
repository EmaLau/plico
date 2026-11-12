"""Prova tutti gli strumenti contro il server in esecuzione: docker exec <container> python3 /app/selftest.py
Salva i risultati in /work/selftest/ per poterli guardare."""
import io, json, os, sys, time, uuid, urllib.request, zipfile
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


def get_cookie(resp_headers, name):
    for k, v in resp_headers:
        if k.lower() == "set-cookie" and v.startswith(name + "="):
            return v.split(";", 1)[0]
    return ""


# sessione della pagina web, come un browser che apre "/"
with urllib.request.urlopen(URL + "/", timeout=30) as r:
    SESSION = get_cookie(r.getheaders(), "updf_session")


def post(path, fields=None, files=(), headers=None, session=True):
    b = uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in (fields or {}).items():
        body.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, name, data in files:
        body.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\n'
                   f'Content-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n")
    body.write(f"--{b}--\r\n".encode())
    h = {"Content-Type": f"multipart/form-data; boundary={b}", **(headers or {})}
    if session and SESSION:
        h["Cookie"] = SESSION
    req = urllib.request.Request(URL + path, body.getvalue(), h)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def jcall(method, path, body=None, cookie="", xrw=True):
    h = {"Content-Type": "application/json"}
    if xrw:
        h["X-Requested-With"] = "universal-pdf"
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(URL + path, json.dumps(body).encode() if body is not None else None, h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}"), r.getheaders()
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers.items()


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
max_mb = int(os.environ.get("MAX_UPLOAD_MB", "0"))
if 0 < max_mb <= 200:
    s, b, _ = post("/api/info", files=[("file", "big.pdf", b"0" * ((max_mb + 1) << 20))])
    check("info too large -> 413", s == 413, json.loads(b)["detail"])
else:
    print(f"SKIP info too large -> 413  (MAX_UPLOAD_MB={max_mb}: si prova solo con un limite tra 1 e 200 MB)")
# Limite sui risultati: pagine di puro rumore, che come PNG non si comprimono
max_out = float(os.environ.get("MAX_OUTPUT_MB", "4096"))
if max_out <= 10:
    noise = fitz.Pixmap(fitz.csRGB, 1200, 1700, os.urandom(1200 * 1700 * 3), False)
    d = fitz.open()
    for _ in range(3):
        d.new_page(width=595, height=842).insert_image(fitz.Rect(0, 0, 595, 842), pixmap=noise)
    s, b, _ = post("/api/pdf2img", {"format": "png", "dpi": "150"}, [("file", "noise.pdf", d.tobytes())])
    check("pdf2img output limit -> 413", s == 413, json.loads(b)["detail"])
else:
    print(f"SKIP pdf2img output limit -> 413  (MAX_OUTPUT_MB={max_out:g}: si prova solo fino a 10 MB)")
# Funzioni della fase 4
d = fitz.open(); pg = d.new_page(); pg.insert_text((72, 120), "Fattura numero 12345", fontsize=28)
scan_pdf = fitz.open(); scan_pdf.new_page().insert_image(fitz.Rect(0, 0, 595, 842), stream=pg.get_pixmap(dpi=200).tobytes("png"))
s, b, _ = post("/api/ocr", {"lang": "ita+eng"}, [("file", "scan.pdf", scan_pdf.tobytes())])
check("ocr", s == 200 and "12345" in fitz.open("pdf", b)[0].get_text())
s, b, _ = post("/api/pdfa", files=[("file", "a.pdf", pdf)])
check("pdfa", s == 200 and "pdfaid" in str(pikepdf.open(io.BytesIO(b)).open_metadata()))
s, b, _ = post("/api/sign", {"page": "0"}, [("file", "a.pdf", pdf), ("image", "firma.png", png)])
check("sign", s == 200 and len(fitz.open("pdf", b)[0].get_images()) == 1)
d = fitz.open(); d.new_page().insert_text((72, 100), "mario.rossi@example.com resto", fontsize=14)
s, b, h = post("/api/redact", {"presets": "email"}, [("file", "r.pdf", d.tobytes())])
check("redact", s == 200 and "example" not in fitz.open("pdf", b)[0].get_text())
s, b, h = post("/api/compare", files=[("file_a", "a.pdf", pdf), ("file_b", "b.pdf", pdf2)])
check("compare", s == 200 and h.get("x-pages-changed") not in (None, "0"))
s, b, _ = post("/api/nup", {"mode": "booklet"}, [("file", "a.pdf", pdf)])
check("booklet", s == 200 and pages(b) == 4)
s, b, _ = post("/api/pages", {"mode": "resize", "paper": "a4"}, [("file", "a.pdf", pdf)])
check("resize a4", s == 200 and round(fitz.open("pdf", b)[0].rect.width) in (595, 842))
s, b, _ = post("/api/repair", files=[("file", "x.pdf", pdf.replace(b"startxref", b"startxrXX"))])
check("repair", s == 200 and pages(b) == 5)
s, b, _ = post("/api/metadata", {"title": "Prova"}, [("file", "a.pdf", pdf)])
check("metadata", s == 200 and fitz.open("pdf", b).metadata["title"] == "Prova")
s, b, _ = post("/api/extract", {"kind": "text"}, [("file", "a.pdf", pdf)])
check("extract text", s == 200 and b"Pagina 3" in b)
import numpy as np, cv2
photo = np.full((900, 1200, 3), 60, np.uint8)
cv2.fillPoly(photo, [np.array([[300, 120], [900, 160], [950, 820], [250, 780]], np.int32)], (245, 245, 245))
s, b, h = post("/api/scan", {"mode": "bw"}, [("files", "foto.jpg", cv2.imencode(".jpg", photo)[1].tobytes())])
check("scan", s == 200 and h.get("x-pages-straightened") == "1")
steps = json.dumps([{"op": "compress", "level": "high"}, {"op": "stamp", "numbers": True}])
s, b, _ = post("/api/chain", {"steps": steps}, [("files", "a.pdf", pdf), ("files", "b.pdf", pdf2)])
check("chain zip", s == 200 and len(zipfile.ZipFile(io.BytesIO(b)).namelist()) == 2)

# Chiavi API
check("page session cookie", SESSION.startswith("updf_session="))
s, b, _ = post("/api/info", files=[("file", "a.pdf", pdf)], headers={"apikey": "updf_sbagliata"})
check("invalid api key -> 401", s == 401, json.loads(b)["detail"])
if os.environ.get("API_REQUIRE_KEY", "").lower() in ("1", "true", "yes", "si", "on"):
    s, b, _ = post("/api/info", files=[("file", "a.pdf", pdf)], session=False)
    check("API_REQUIRE_KEY: no key -> 401", s == 401)
else:
    s, b, _ = post("/api/info", files=[("file", "a.pdf", pdf)], session=False)
    check("no key, no session -> 200 (API_REQUIRE_KEY off)", s == 200)
admin_pw = os.environ.get("UPDF_ADMIN_PASSWORD", "")
if admin_pw:
    s, _, _ = jcall("POST", "/admin/api/login", {"password": "sbagliata"})
    check("admin wrong password -> 401", s == 401)
    s, _, h = jcall("POST", "/admin/api/login", {"password": admin_pw})
    adm = get_cookie(h, "updf_admin")
    check("admin login", s == 200 and adm)
    s, _, _ = jcall("POST", "/admin/api/keys", {"name": "x", "perms": ["merge"]}, adm, xrw=False)
    check("admin write without X-Requested-With -> 403", s == 403)
    s, _, _ = jcall("GET", "/admin/api/keys")
    check("admin list without login -> 401", s == 401)
    s, k, _ = jcall("POST", "/admin/api/keys", {"name": "selftest", "perms": ["merge"]}, adm)
    key = k.get("key", "")
    check("create api key", s == 200 and key.startswith("updf_"))
    s, b, _ = post("/api/merge", files=[("files", "a.pdf", pdf), ("files", "b.pdf", pdf2)],
                   headers={"apikey": key}, session=False)
    check("api key with permission -> 200", s == 200 and pages(b) == 7)
    s, b, _ = post("/api/rotate", files=[("file", "a.pdf", pdf)], headers={"apikey": key}, session=False)
    check("api key without permission -> 403", s == 403, json.loads(b)["detail"])
    s, lst, _ = jcall("GET", "/admin/api/keys", cookie=adm)
    mine = [x for x in lst["keys"] if x["id"] == k["id"]]
    check("key listed with last use, no hash", mine and mine[0]["last_used"] and "hash" not in mine[0])
    s, _, _ = jcall("PUT", f"/admin/api/keys/{k['id']}", {"perms": ["merge", "rotate"]}, adm)
    s2, b, _ = post("/api/rotate", files=[("file", "a.pdf", pdf)], headers={"apikey": key}, session=False)
    check("permission added -> 200", s == 200 and s2 == 200)
    # interruttore "chiave obbligatoria" dalla pagina admin
    s, st, _ = jcall("PUT", "/admin/api/settings", {"require_key": True}, adm)
    s2, _, _ = post("/api/info", files=[("file", "a.pdf", pdf)], session=False)
    s3, _, _ = post("/api/info", files=[("file", "a.pdf", pdf)])
    s4, _, _ = jcall("PUT", "/admin/api/settings", {"require_key": False}, adm)
    s5, _, _ = post("/api/info", files=[("file", "a.pdf", pdf)], session=False)
    check("admin toggle require key (on: 401 without key, page ok; off: 200)",
          s == 200 and st["require_key"] and s2 == 401 and s3 == 200 and s4 == 200 and s5 == 200)
    # interruttore "password per l'area admin"
    s, _, _ = jcall("PUT", "/admin/api/settings", {"admin_login": False}, adm)
    s2, lst2, _ = jcall("GET", "/admin/api/keys")
    s3, _, h3 = jcall("PUT", "/admin/api/settings", {"admin_login": True})
    s4, _, _ = jcall("GET", "/admin/api/keys")
    check("admin toggle login (off: open without password; on again: 401)",
          s == 200 and s2 == 200 and s3 == 200 and s4 == 401)
    s, _, _ = jcall("DELETE", f"/admin/api/keys/{k['id']}", cookie=adm)
    s2, b, _ = post("/api/merge", files=[("files", "a.pdf", pdf), ("files", "b.pdf", pdf2)],
                    headers={"apikey": key}, session=False)
    check("revoked key -> 401", s == 200 and s2 == 401)
else:
    print("SKIP admin / api keys  (UPDF_ADMIN_PASSWORD non impostata)")
# le cartelle dei file inviati si cancellano subito DOPO la risposta (BackgroundTask):
# si aspetta qualche secondo prima di considerarle dimenticate
for _ in range(50):
    left = list((WORK / "upd").glob("*")) if (WORK / "upd").exists() else []
    if not left:
        break
    time.sleep(0.1)
check("no leftover temp files", not left, str(left))
print("TUTTO OK" if ok else "CI SONO ERRORI")
sys.exit(0 if ok else 1)

"""Universal-PDF: strumenti PDF self-hosted (unisci, dividi, riordina, ruota, elimina, comprimi,
converti, proteggi/sblocca, numeri di pagina e filigrana).

Ogni richiesta lavora in una cartella temporanea che viene cancellata appena il file e' stato inviato:
sul server non resta niente.

Documentazione interattiva dell'API in /apidocs; chiavi API e area admin in apikeys.py (/admin).

API (tutte POST multipart, rispondono col file risultato, o JSON {"detail": ...} con errore;
intestazione facoltativa "apikey", obbligatoria fuori dalla pagina web se API_REQUIRE_KEY=true)
  /api/info        file             -> {"pages": n, "encrypted": bool, "size": bytes}
  /api/thumbs      file, width      -> {"pages": [{"w","h","rot","img": dataURL JPEG}]}
  /api/merge       files[]          -> PDF (accetta anche immagini)
  /api/split       file, mode, ranges|every -> ZIP (o PDF se ne esce uno solo)
  /api/organize    file, pages=JSON [[indice, rotazione], ...] -> PDF (riordina/ruota/elimina)
  /api/rotate      file, angle      -> PDF (tutte le pagine)
  /api/compress    file, level      -> PDF
  /api/img2pdf     files[]          -> PDF
  /api/pdf2img     file, format, dpi -> ZIP (o immagine se una pagina); X-Dpi-Reduced = pagine
                                        rese a dpi piu' bassi per non superare MAX_PAGE_MPX
  /api/protect     file, password   -> PDF (AES-256)
  /api/unlock      file, password   -> PDF
  /api/stamp       file, numbers..., watermark... -> PDF
  GET /healthz
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

import apikeys
import chains
import converter
import i18n
import magic
import ops
from ops import fail

STATIC = Path(__file__).parent / "static"
WORK = Path(os.environ.get("WORK_DIR", "/tmp"))
TMP = WORK / "upd"
# I file caricati vengono "parcheggiati" da Starlette in file temporanei: li teniamo nel volume dei
# dati invece che nel sistema del container.
SPOOL = WORK / "tmp"
SPOOL.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(SPOOL)
# Nessun limite di upload, a meno che non venga impostato (MB per file, 0 = nessun limite).
MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", "0"))
# Lavori pesanti eseguiti insieme; gli altri aspettano il loro turno.
MAX_PARALLEL = max(1, int(os.environ.get("MAX_PARALLEL", "2")))

API_DOC = """Strumenti PDF self-hosted. Ogni richiesta lavora in una cartella temporanea cancellata subito dopo l'invio.

**Chiavi API.** Gli script mandano la chiave nell'intestazione `apikey` (si crea nella pagina `/admin`).
Ogni chiave ha dei permessi, uno per strumento. La pagina web non ha bisogno della chiave.
Se il server ha `API_REQUIRE_KEY=true`, le chiamate senza chiave vengono rifiutate.

Tutte le chiamate sono `POST` con `multipart/form-data` e rispondono con il file risultato,
oppure con JSON `{"detail": "..."}` e un codice di errore HTTP.

Esempio: `curl -H "apikey: updf_..." -F files=@a.pdf -F files=@b.pdf -o unito.pdf http://host:8080/api/merge`"""

DATA = Path(os.environ.get("DATA_DIR", str(WORK / "data")))
KEYS = apikeys.KeyStore(DATA)


CHAINS = chains.ChainStore(DATA)
MAGIC_STATS = {"processed": 0, "errors": 0, "last_run": None, "last_error": None}


@contextlib.asynccontextmanager
async def lifespan(_):
    task = asyncio.create_task(magic.loop(CHAINS.list, WORK / "magic", heavy, MAGIC_STATS)) if magic.config() else None
    yield
    if task:
        task.cancel()
    KEYS.flush()  # salva l'"ultimo uso" delle chiavi rimasto in memoria


app = FastAPI(title="Universal-PDF", version="1.0", description=API_DOC, lifespan=lifespan,
              docs_url="/apidocs", redoc_url=None, openapi_url="/apidocs/openapi.json")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
API = {"dependencies": [Security(apikeys.header_scheme)], "tags": ["Strumenti PDF"]}
# percorso dell'API -> permesso richiesto alla chiave
PATH_PERM = {f"/api/{p}": p for p in apikeys.PERMISSIONS} | {"/api/thumbs": "info", "/api/unlock": "protect",
                                                              "/api/fill": "forms", "/api/forms": "forms"}
log = logging.getLogger("universal-pdf")
_slots: asyncio.Semaphore | None = None


async def heavy(fn, *args, **kw):
    """Esegue un lavoro pesante in un thread, al massimo MAX_PARALLEL alla volta."""
    global _slots
    if _slots is None:
        _slots = asyncio.Semaphore(MAX_PARALLEL)
    async with _slots:
        return await run_in_threadpool(fn, *args, **kw)


class Job:
    """Cartella temporanea per una richiesta; si cancella dopo l'invio della risposta."""

    def __init__(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.dir = Path(tempfile.mkdtemp(dir=TMP))

    def path(self, name: str) -> Path:
        return self.dir / name

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def send(self, path: Path, name: str, media: str):
        return FileResponse(path, filename=name, media_type=media,
                            background=BackgroundTask(self.cleanup),
                            headers={"Cache-Control": "no-store"})


def error(request: Request, msg, status: int) -> JSONResponse:
    lang = i18n.pick(request.headers.get("accept-language"))
    return JSONResponse({"detail": i18n.t(msg, lang)}, status_code=status, headers={"Content-Language": lang})


@app.exception_handler(HTTPException)
async def http_error(request, exc: HTTPException):
    return error(request, exc.detail, exc.status_code)


@app.exception_handler(Exception)
async def any_error(request, exc: Exception):
    log.error("Errore su %s", request.url.path, exc_info=exc)
    return security_headers(request, error(request, "Errore durante l'elaborazione del file", 500))


def _inline_hashes(*pages: str) -> str:
    """Hash degli script scritti dentro le pagine, per permetterli nella Content-Security-Policy."""
    out = []
    for page in pages:
        for body in re.findall(r"<script>(.*?)</script>", (STATIC / page).read_text("utf-8"), re.S):
            out.append("'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'")
    return " ".join(out)


CSP_PAGE = ("default-src 'self'; script-src 'self' " + _inline_hashes("index.html", "admin.html") +
            "; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
# la documentazione Swagger carica i suoi file da jsDelivr e ha uno script nella pagina
CSP_DOCS = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")


def security_headers(request: Request, resp):
    h = resp.headers
    h["Content-Security-Policy"] = CSP_DOCS if request.url.path == "/apidocs" else CSP_PAGE
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return resp


def cross_site(request: Request) -> bool:
    """Vero per le richieste che modificano qualcosa inviate dal browser da una pagina di un altro sito."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return False
    if request.headers.get("sec-fetch-site") == "cross-site":
        return True
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return origin == "null"
    hosts = {request.headers.get("host"), request.headers.get("x-forwarded-host")}
    return urlparse(origin).netloc not in hosts


@app.middleware("http")
async def guard(request: Request, call_next):
    """Richieste da altri siti, chiave e permessi (prima di ricevere il file), intestazioni di sicurezza."""
    try:
        if cross_site(request):
            fail("Richiesta inviata da un altro sito", 403)
        perm = PATH_PERM.get(request.url.path)
        if perm and request.method == "POST":
            key = request.headers.get("apikey")
            if key:
                request.state.key_perms = KEYS.check_key(key, perm)
            elif KEYS.require_key and not KEYS.verify("session", request.cookies.get(apikeys.SESSION_COOKIE)):
                fail("Serve una chiave API nell'intestazione 'apikey'", 401)
    except HTTPException as e:
        return security_headers(request, error(request, e.detail, e.status_code))
    return security_headers(request, await call_next(request))


async def save(job: Job, up: UploadFile, idx: int = 0) -> Path:
    name = Path(up.filename or "file").name
    ext = Path(name).suffix.lower() or ".pdf"
    dst = job.path(f"in{idx:03d}{ext}")
    size = 0
    with dst.open("wb") as f:
        while chunk := await up.read(1 << 20):
            size += len(chunk)
            if MAX_MB and size > MAX_MB * 1024 * 1024:
                fail(f"File troppo grande (massimo {MAX_MB} MB)", 413)
            f.write(chunk)
    return dst


def stem(up: UploadFile) -> str:
    s = Path(up.filename or "documento").stem
    return re.sub(r'[\\/:*?"<>|]+', "_", s)[:120] or "documento"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index():
    resp = HTMLResponse((STATIC / "index.html").read_text("utf-8"), headers={"Cache-Control": "no-cache"})
    resp.set_cookie(apikeys.SESSION_COOKIE, KEYS.sign("session", apikeys.SESSION_TTL),
                    max_age=apikeys.SESSION_TTL, httponly=True, samesite="strict")
    return resp


# ---------------------------------------------------------------- area admin (chiavi API)

def admin_only(request: Request, write: bool = False):
    if not KEYS.admin_enabled:
        fail("Area admin disattivata: imposta UPDF_ADMIN_PASSWORD", 404)
    if not KEYS.is_admin(request.cookies.get(apikeys.ADMIN_COOKIE)):
        fail("Accedi con la password admin", 401)
    # contro le richieste inviate da pagine di altri siti
    if write and request.headers.get("x-requested-with") != "universal-pdf":
        fail("Richiesta non valida", 403)


@app.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page():
    return HTMLResponse((STATIC / "admin.html").read_text("utf-8"), headers={"Cache-Control": "no-cache"})


@app.get("/admin/api/state", include_in_schema=False)
async def admin_state(request: Request):
    return {"enabled": KEYS.admin_enabled, "logged": KEYS.is_admin(request.cookies.get(apikeys.ADMIN_COOKIE)),
            "admin_login": KEYS.admin_login, "has_password": bool(KEYS.admin_password),
            "require_key": KEYS.require_key, "permissions": apikeys.PERMISSIONS}


@app.post("/admin/api/login", include_in_schema=False)
async def admin_login(request: Request, password: str = Body(..., embed=True)):
    if not KEYS.admin_password:
        fail("Nessuna password admin impostata", 404)
    if request.headers.get("x-requested-with") != "universal-pdf":
        fail("Richiesta non valida", 403)
    if not KEYS.login(apikeys.client_ip(request), password):
        await asyncio.sleep(1)
        fail("Password sbagliata", 401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(apikeys.ADMIN_COOKIE, KEYS.sign("admin", apikeys.ADMIN_TTL), max_age=apikeys.ADMIN_TTL,
                    httponly=True, samesite="strict", path="/admin")
    return resp


@app.post("/admin/api/logout", include_in_schema=False)
async def admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(apikeys.ADMIN_COOKIE, path="/admin")
    return resp


@app.put("/admin/api/settings", include_in_schema=False)
async def admin_settings(request: Request, require_key: bool | None = Body(None), admin_login: bool | None = Body(None)):
    admin_only(request, write=True)
    KEYS.update_settings(require_key, admin_login)
    resp = JSONResponse({"require_key": KEYS.require_key, "admin_login": KEYS.admin_login})
    if admin_login:  # chi riattiva la password resta dentro
        resp.set_cookie(apikeys.ADMIN_COOKIE, KEYS.sign("admin", apikeys.ADMIN_TTL), max_age=apikeys.ADMIN_TTL,
                        httponly=True, samesite="strict", path="/admin")
    return resp


@app.get("/admin/api/keys", include_in_schema=False)
async def keys_list(request: Request):
    admin_only(request)
    return {"keys": KEYS.list()}


@app.post("/admin/api/keys", include_in_schema=False)
async def keys_create(request: Request, name: str = Body(...), perms: list[str] = Body(...)):
    admin_only(request, write=True)
    key, rec = KEYS.create(name, perms)
    return {"key": key, **rec}


@app.put("/admin/api/keys/{kid}", include_in_schema=False)
async def keys_update(request: Request, kid: str, name: str | None = Body(None), perms: list[str] | None = Body(None)):
    admin_only(request, write=True)
    return KEYS.update(kid, name, perms)


@app.delete("/admin/api/keys/{kid}", include_in_schema=False)
async def keys_delete(request: Request, kid: str):
    admin_only(request, write=True)
    KEYS.delete(kid)
    return {"ok": True}


# ---------------------------------------------------------------- strumenti

def send(job: Job, res: ops.Result, name: str | None = None):
    """Invia il risultato; name = nome del file da proporre (se None si usa quello del risultato)."""
    if name is None or Path(name).suffix.lower() != res.path.suffix.lower():
        name = res.path.name
    resp = job.send(res.path, name, res.media)
    for k, v in res.headers.items():
        resp.headers[k] = v
    if res.headers:
        resp.headers["Access-Control-Expose-Headers"] = ", ".join(res.headers)
    return resp


async def one_file(file: UploadFile, fn, name_suffix: str | None, base_kw: str | None = None, **opts):
    """Schema comune: salva il file, esegue l'operazione nella coda, invia il risultato."""
    job = Job()
    try:
        p = await save(job, file)
        base = stem(file)
        if base_kw:
            opts[base_kw] = base
        res = await heavy(fn, p, job.dir, **opts)
        return send(job, res, None if name_suffix is None else base + name_suffix)
    except BaseException:
        job.cleanup()
        raise


async def many_files(files: list[UploadFile], fn, name_suffix: str, **opts):
    job = Job()
    try:
        paths = [await save(job, f, i) for i, f in enumerate(files)]
        res = await heavy(fn, paths, job.dir, **opts)
        return send(job, res, stem(files[0]) + name_suffix)
    except BaseException:
        job.cleanup()
        raise


async def read_small(up: UploadFile | None, limit_mb: int = 20) -> bytes | None:
    if up is None:
        return None
    data = await up.read(limit_mb * 1024 * 1024 + 1)
    if len(data) > limit_mb * 1024 * 1024:
        fail(f"File troppo grande (massimo {limit_mb} MB)", 413)
    return data or None


def tool(path: str, summary: str, perm: str, doc: str = ""):
    return app.post(path, summary=summary, description=(doc + "\n\n" if doc else "") + f"Permesso: `{perm}`", **API)


@app.get("/healthz", tags=["Servizio"], summary="Stato del servizio")
async def healthz():
    return {"ok": True}


@app.get("/api/features", tags=["Servizio"], summary="Funzioni facoltative attive su questo server")
async def features():
    return {"office": converter.enabled(), "ocr": shutil.which("ocrmypdf") is not None,
            "magic_folder": magic.config() is not None, "office_formats": sorted(converter.PDF_TO)}


@tool("/api/info", "Pagine, protezione, dimensione e metadati di un PDF", "info")
async def info(file: UploadFile = File(...)):
    job = Job()
    try:
        return ops.info(await save(job, file))
    finally:
        job.cleanup()


@tool("/api/thumbs", "Anteprime delle pagine (JPEG)", "info", "`pages` vuoto = tutte; `width` in pixel (40-2000).")
async def thumbs(file: UploadFile = File(...), width: int = Form(160), pages: str = Form("")):
    job = Job()
    try:
        p = await save(job, file)
        return await heavy(ops.thumbs, p, width, pages)
    finally:
        job.cleanup()


@tool("/api/merge", "Unisci PDF e immagini", "merge")
async def merge(files: list[UploadFile] = File(...)):
    return await many_files(files, ops.merge, "-unito.pdf")


@tool("/api/split", "Dividi o estrai pagine", "split")
async def split(file: UploadFile = File(...), mode: str = Form("ranges"), ranges: str = Form(""),
                every: int = Form(1), merge_out: bool = Form(False)):
    return await one_file(file, ops.split, None, "base", mode=mode, ranges=ranges, every=every, merge_out=merge_out)


@tool("/api/organize", "Riordina, ruota ed elimina pagine", "organize",
      "`pages` = JSON `[[indice_da_0, rotazione], ...]` nell'ordine finale; le pagine assenti si eliminano.")
async def organize(file: UploadFile = File(...), pages: str = Form(...)):
    return await one_file(file, ops.organize, "-modificato.pdf", pages=pages)


@tool("/api/rotate", "Ruota le pagine", "rotate")
async def rotate(file: UploadFile = File(...), angle: int = Form(90), pages: str = Form("")):
    return await one_file(file, ops.rotate, "-ruotato.pdf", angle=angle, pages=pages)


@tool("/api/compress", "Comprimi", "compress")
async def compress(file: UploadFile = File(...), level: str = Form("medium"), gray: bool = Form(False)):
    return await one_file(file, ops.compress, "-compresso.pdf", level=level, gray=gray)


@tool("/api/img2pdf", "Immagini in PDF", "img2pdf")
async def img2pdf(files: list[UploadFile] = File(...), page: str = Form("fit"), margin: float = Form(0)):
    return await many_files(files, ops.img2pdf, "-immagini.pdf" if len(files) > 1 else ".pdf", page=page, margin=margin)


@tool("/api/pdf2img", "PDF in immagini", "pdf2img")
async def pdf2img(file: UploadFile = File(...), format: str = Form("png"), dpi: int = Form(150), ranges: str = Form("")):
    return await one_file(file, ops.pdf2img, None, "base", format=format, dpi=dpi, ranges=ranges)


@tool("/api/protect", "Proteggi con password (AES-256)", "protect")
async def protect(file: UploadFile = File(...), password: str = Form(...), owner: str = Form(""),
                  allow_print: bool = Form(True), allow_copy: bool = Form(True), allow_edit: bool = Form(False)):
    if not password:
        fail("Scrivi una password")
    return await one_file(file, ops.protect, "-protetto.pdf", password=password, owner=owner,
                          allow_print=allow_print, allow_copy=allow_copy, allow_edit=allow_edit)


@tool("/api/unlock", "Togli la password", "protect")
async def unlock(file: UploadFile = File(...), password: str = Form("")):
    return await one_file(file, ops.unlock, "-sbloccato.pdf", password=password)


@tool("/api/stamp", "Numeri di pagina, intestazione, piè di pagina e filigrana", "stamp",
      "In `header` e `footer` si possono usare `{n}`, `{tot}`, `{date}` e `{file}`. `wm_image` = logo (PNG/JPG).")
async def stamp(file: UploadFile = File(...),
                numbers: bool = Form(False), num_pos: str = Form("bottom-center"), num_fmt: str = Form("{n}"),
                num_start: int = Form(1), num_size: float = Form(11), num_skip_first: bool = Form(False),
                watermark: str = Form(""), wm_size: float = Form(60), wm_opacity: float = Form(0.2),
                wm_angle: int = Form(45), wm_color: str = Form("#c0392b"), header: str = Form(""),
                footer: str = Form(""), hf_size: float = Form(9), wm_image: UploadFile | None = File(None),
                wm_image_scale: float = Form(0.4)):
    img = await read_small(wm_image)
    return await one_file(file, ops.stamp, "-timbrato.pdf", "name", numbers=numbers, num_pos=num_pos, num_fmt=num_fmt,
                          num_start=num_start, num_size=num_size, num_skip_first=num_skip_first, watermark=watermark,
                          wm_size=wm_size, wm_opacity=wm_opacity, wm_angle=wm_angle, wm_color=wm_color, header=header,
                          footer=footer, hf_size=hf_size, wm_image=img, wm_image_scale=wm_image_scale)


@tool("/api/ocr", "OCR: rende il PDF ricercabile e copiabile", "ocr",
      "`lang`: `ita`, `eng` o `ita+eng`. `force` rifà l'OCR anche sulle pagine che hanno già testo.")
async def ocr(file: UploadFile = File(...), lang: str = Form("ita+eng"), force: bool = Form(False), deskew: bool = Form(False)):
    return await one_file(file, ops.ocr, "-ocr.pdf", lang=lang, force=force, deskew=deskew)


@tool("/api/pdfa", "Converti in PDF/A-2 per l'archiviazione", "pdfa")
async def pdfa(file: UploadFile = File(...), ocr_text: bool = Form(False), lang: str = Form("ita+eng")):
    return await one_file(file, ops.pdfa, "-pdfa.pdf", ocr_text=ocr_text, lang=lang)


@tool("/api/repair", "Ripara un PDF danneggiato", "repair")
async def repair(file: UploadFile = File(...)):
    return await one_file(file, ops.repair, "-riparato.pdf")


@tool("/api/metadata", "Modifica i metadati o togli i dati nascosti", "metadata",
      "`clean` toglie metadati, XMP, JavaScript, file allegati, miniature e testo nascosto. "
      "I campi lasciati vuoti non vengono cambiati.")
async def metadata(file: UploadFile = File(...), clean: bool = Form(False), title: str | None = Form(None),
                   author: str | None = Form(None), subject: str | None = Form(None), keywords: str | None = Form(None),
                   creator: str | None = Form(None), producer: str | None = Form(None)):
    return await one_file(file, ops.metadata, "-metadati.pdf", clean=clean, title=title, author=author, subject=subject,
                          keywords=keywords, creator=creator, producer=producer)


@tool("/api/extract", "Estrai le immagini (ZIP) o il testo (TXT)", "extract")
async def extract(file: UploadFile = File(...), kind: str = Form("images"), pages: str = Form("")):
    return await one_file(file, ops.extract, None, "base", kind=kind, pages=pages)


@tool("/api/pages", "Ridimensiona le pagine (es. tutto in A4) o ritaglia i margini", "pages",
      "`mode`: `resize` (formato `paper`), `crop` (margini in mm `top`, `right`, `bottom`, `left`), `trim` (automatico).")
async def pages(file: UploadFile = File(...), mode: str = Form("resize"), paper: str = Form("a4"),
                orientation: str = Form("auto"), margin_mm: float = Form(0), top: float = Form(0), right: float = Form(0),
                bottom: float = Form(0), left: float = Form(0)):
    return await one_file(file, ops.pages, "-pagine.pdf", mode=mode, paper=paper, orientation=orientation,
                          margin_mm=margin_mm, top=top, right=right, bottom=bottom, left=left)


@tool("/api/nup", "Più pagine per foglio o opuscolo da stampare", "nup",
      "`mode`: `nup` (`n` = 2, 4, 6, 8, 9 o 16) o `booklet` (fronte-retro, da piegare a metà).")
async def nup(file: UploadFile = File(...), mode: str = Form("nup"), n: int = Form(2), paper: str = Form("a4"),
              gap_mm: float = Form(4)):
    return await one_file(file, ops.nup, "-opuscolo.pdf" if mode == "booklet" else "-fogli.pdf", mode=mode, n=n,
                          paper=paper, gap_mm=gap_mm)


def parse_box(text: str):
    try:
        box = [float(v) for v in json.loads(text)]
        assert len(box) == 4
        return box
    except Exception:
        fail("Posizione non valida")


@tool("/api/sign", "Firma: inserisce un'immagine della firma nella pagina", "sign",
      "`image` = PNG (meglio trasparente). `page` da 0 (-1 = ultima). `box` = JSON `[x0, y0, x1, y1]` in frazioni "
      "della pagina come si vede (0-1, origine in alto a sinistra).")
async def sign(file: UploadFile = File(...), image: UploadFile = File(...), page: int = Form(-1),
               box: str = Form("[0.6, 0.82, 0.92, 0.92]")):
    img = await read_small(image)
    return await one_file(file, ops.sign, "-firmato.pdf", image=img, page=page, box=parse_box(box))


@tool("/api/annotate", "Annotazioni: evidenziatore, riquadri, testo, note, frecce, disegno", "annotate",
      "`items` = JSON, es. `[{\"page\": 0, \"type\": \"highlight\", \"box\": [0.1, 0.2, 0.5, 0.25]}]`. Tipi: "
      "`highlight`, `rect`, `text` (`box`, `text`), `note` (`at`, `text`), `arrow` (`from`, `to`), `ink` (`points`). "
      "Coordinate in frazioni della pagina. `flatten` rende le annotazioni parte della pagina.")
async def annotate(file: UploadFile = File(...), items: str = Form(...), flatten: bool = Form(False)):
    return await one_file(file, ops.annotate, "-annotato.pdf", items=items, flatten=flatten)


@tool("/api/forms", "Elenco dei campi di un modulo PDF", "forms")
async def forms(file: UploadFile = File(...)):
    job = Job()
    try:
        p = await save(job, file)
        return await heavy(ops.form_fields, p)
    finally:
        job.cleanup()


@tool("/api/fill", "Compila un modulo PDF", "forms",
      "`values` = JSON `{\"nome campo\": \"valore\"}`; per le caselle `true`/`false`. `flatten` blocca i campi.")
async def fill(file: UploadFile = File(...), values: str = Form(...), flatten: bool = Form(False)):
    return await one_file(file, ops.fill_form, "-compilato.pdf", values=values, flatten=flatten)


@tool("/api/redact", "Oscura testo e zone (il contenuto viene tolto davvero)", "redact",
      "`terms` = parole o frasi, una per riga. `presets` = `email`, `phone`, `iban`, `cf`, `card`. "
      "`areas` = JSON `[{\"page\": 0, \"box\": [x0, y0, x1, y1]}]`. `regex` = espressione regolare su ogni parola.")
async def redact(file: UploadFile = File(...), terms: str = Form(""), presets: str = Form(""), areas: str = Form("[]"),
                 regex: str = Form(""), clean_metadata: bool = Form(True)):
    return await one_file(file, ops.redact, "-oscurato.pdf", terms=terms, presets=presets, areas=areas, regex=regex,
                          clean_metadata=clean_metadata)


@tool("/api/compare", "Confronta due PDF", "compare",
      "Risponde con un PDF: riepilogo con le parole tolte e aggiunte, e le pagine diverse affiancate con le zone cambiate in rosso.")
async def compare(file_a: UploadFile = File(...), file_b: UploadFile = File(...)):
    job = Job()
    try:
        a, b = await save(job, file_a, 0), await save(job, file_b, 1)
        a, b = a.rename(job.path(Path(file_a.filename or "A.pdf").name)), b.rename(job.path("B-" + Path(file_b.filename or "B.pdf").name))
        res = await heavy(ops.compare, a, b, job.dir)
        return send(job, res, f"confronto-{stem(file_a)}.pdf")
    except BaseException:
        job.cleanup()
        raise


@tool("/api/scan", "Scanner: foto di documenti raddrizzate e unite in un PDF", "scan",
      "`mode`: `color`, `gray`, `bw` (bianco e nero, testo nitido). `paper`: `a4`, `letter` o `fit`.")
async def scan(files: list[UploadFile] = File(...), mode: str = Form("color"), paper: str = Form("a4")):
    return await many_files(files, ops.scan, "-scansione.pdf", mode=mode, paper=paper)


@tool("/api/office", "Word, Excel, PowerPoint ↔ PDF (con Universal Converter)", "office",
      "`target`: `pdf` per un documento Office, oppure `docx`, `odt`, `xlsx`, `pptx`, `txt` per un PDF. "
      "Serve `CONVERTER_URL` sul server: vedi `/api/features`.")
async def office(file: UploadFile = File(...), target: str = Form("pdf")):
    return await one_file(file, converter.convert, None, "base", target=target)


@tool("/api/chain", "Catena di operazioni, anche su più file insieme", "chain",
      "`steps` = JSON `[{\"op\": \"compress\", \"level\": \"high\"}, {\"op\": \"stamp\", \"numbers\": true}]`, oppure "
      "`chain` = nome o id di una catena salvata. Operazioni: " + ", ".join(f"`{k}`" for k in ops.CHAIN_OPS) + ". "
      "Con un file risponde con il PDF, con più file con uno ZIP. Una chiave API deve avere anche i permessi delle operazioni.")
async def chain_run(request: Request, files: list[UploadFile] = File(...), steps: str = Form(""), chain: str = Form("")):
    if chain.strip():
        steps_list = CHAINS.get(chain.strip())["steps"]
    else:
        try:
            steps_list = json.loads(steps)
        except Exception:
            fail("Catena di operazioni non valida")
    key_perms = getattr(request.state, "key_perms", None)
    if key_perms is not None:
        missing = ops.step_perms(steps_list) - key_perms
        if missing:
            fail(f"La chiave non ha il permesso '{sorted(missing)[0]}'", 403)
    job = Job()
    try:
        paths = [await save(job, f, i) for i, f in enumerate(files)]
        names = [stem(f) for f in files]

        def work():
            outs, total = [], ops.Output()
            used = set()
            for k, (p, base) in enumerate(zip(paths, names)):
                d = job.path(f"c{k}")
                d.mkdir()
                r = ops.chain(p, d, steps_list, name=base)
                name = magic.free_name(used, f"{base}.pdf")
                used.add(name)
                outs.append(total.add(r.path.rename(job.path(name))))
            if len(outs) == 1:
                return ops.Result(outs[0])
            return ops.Result(ops.zip_files(job.dir, outs, "risultati.zip"), "application/zip")

        res = await heavy(work)
        return send(job, res, names[0] + "-elaborato.pdf" if len(paths) == 1 else "risultati.zip")
    except BaseException:
        job.cleanup()
        raise


@app.get("/api/chains", tags=["Strumenti PDF"], summary="Catene salvate")
async def chains_list():
    return {"chains": CHAINS.public()}


# ---------------------------------------------------------------- catene salvate e cartella magica (admin)

@app.get("/admin/api/chains", include_in_schema=False)
async def admin_chains(request: Request):
    admin_only(request)
    return {"chains": CHAINS.public(), "magic": magic.config() is not None and {
        k: v for k, v in (magic.config() or {}).items() if k in ("url", "user", "dir", "poll")}, "magic_stats": MAGIC_STATS}


@app.post("/admin/api/chains", include_in_schema=False)
async def admin_chain_create(request: Request, name: str = Body(...), steps: list = Body(...), magic_on: bool = Body(False, alias="magic")):
    admin_only(request, write=True)
    return CHAINS.create(name, steps, magic_on)


@app.put("/admin/api/chains/{cid}", include_in_schema=False)
async def admin_chain_update(request: Request, cid: str, name: str | None = Body(None), steps: list | None = Body(None),
                             magic_on: bool | None = Body(None, alias="magic")):
    admin_only(request, write=True)
    if steps is not None:  # le password nascoste ("•••") restano quelle salvate
        old = CHAINS.get(cid)["steps"]
        for i, s in enumerate(steps):
            for k in ("password", "owner"):
                if s.get(k) == "•••" and i < len(old):
                    s[k] = old[i].get(k, "")
    return CHAINS.update(cid, name, steps, magic_on)


@app.delete("/admin/api/chains/{cid}", include_in_schema=False)
async def admin_chain_delete(request: Request, cid: str):
    admin_only(request, write=True)
    CHAINS.delete(cid)
    return {"ok": True}


# all'avvio: pulizia di eventuali avanzi (es. container riavviato a meta' lavoro)
shutil.rmtree(TMP, ignore_errors=True)

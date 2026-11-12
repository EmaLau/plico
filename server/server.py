"""Universal-PDF: strumenti PDF self-hosted (unisci, dividi, riordina, ruota, elimina, comprimi,
converti, proteggi/sblocca, numeri di pagina e filigrana).

Ogni richiesta lavora in una cartella temporanea che viene cancellata appena il file e' stato inviato:
sul server non resta niente.

API (tutte POST multipart, rispondono col file risultato, o JSON {"detail": ...} con errore)
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
import io
import json
import logging
import math
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import pikepdf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

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
# Dimensione massima dei risultati di una richiesta (es. tutte le immagini di "PDF in immagini").
MAX_OUT = int(float(os.environ.get("MAX_OUTPUT_MB", "4096")) * 1024 * 1024)
# Lavori pesanti eseguiti insieme; gli altri aspettano il loro turno.
MAX_PARALLEL = max(1, int(os.environ.get("MAX_PARALLEL", "2")))
# Pixel massimi per una pagina resa come immagine (milioni): oltre, i dpi della pagina si abbassano.
MAX_PAGE_PX = int(float(os.environ.get("MAX_PAGE_MPX", "50")) * 1_000_000)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

app = FastAPI(title="Universal-PDF", docs_url=None, redoc_url=None, openapi_url=None)
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


def fail(msg: str, status: int = 400):
    raise HTTPException(status, msg)


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def any_error(request, exc: Exception):
    log.error("Errore su %s", request.url.path, exc_info=exc)
    return JSONResponse({"detail": "Errore durante l'elaborazione del file"}, status_code=500)


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


def open_pdf(path: Path, password: str = "") -> fitz.Document:
    try:
        doc = fitz.open(path)
    except Exception:
        fail("Il file non e' un PDF valido")
    if doc.needs_pass and not doc.authenticate(password):
        doc.close()
        fail("Il PDF e' protetto da password: sbloccalo prima con 'Proteggi / Sblocca'")
    return doc


def parse_ranges(text: str, n: int) -> list[list[int]]:
    """"1-3, 5, 8-" -> [[0,1,2],[4],[7..n-1]] (pagine da 1)."""
    out = []
    for part in re.split(r"[,;\s]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)|(\d+)", part)
        if not m:
            fail(f"Intervallo non valido: '{part}'")
        if m.group(3):
            a = b = int(m.group(3))
        else:
            a = int(m.group(1) or 1)
            b = int(m.group(2) or n)
        if not (1 <= a <= n and 1 <= b <= n):
            fail(f"'{part}' e' fuori dal documento (pagine 1-{n})")
        out.append(list(range(a - 1, b)) if a <= b else list(range(a - 1, b - 2, -1)))
    if not out:
        fail("Scrivi almeno un intervallo di pagine")
    return out


def zip_files(job: Job, files: list[Path], name: str) -> Path:
    z = job.path(name)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    return z


def finish_pdf(doc: fitz.Document, out: Path):
    doc.save(out, garbage=3, deflate=True)


class Output:
    """Conta i byte dei risultati di una richiesta e si ferma oltre MAX_OUTPUT_MB."""

    def __init__(self):
        self.size = 0

    def add(self, path: Path) -> Path:
        self.size += path.stat().st_size
        if self.size > MAX_OUT:
            fail(f"Il risultato supera {MAX_OUT >> 20} MB: scegli meno pagine o una risoluzione piu' bassa", 413)
        return path


# ---------------------------------------------------------------- pagine

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((STATIC / "index.html").read_text("utf-8"), headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/api/info")
async def info(file: UploadFile = File(...)):
    job = Job()
    try:
        p = await save(job, file)
        try:
            doc = fitz.open(p)
        except Exception:
            fail("Il file non e' un PDF valido")
        with doc:
            return {"pages": doc.page_count if not doc.needs_pass else None, "encrypted": doc.needs_pass,
                    "size": p.stat().st_size}
    finally:
        job.cleanup()


@app.post("/api/thumbs")
async def thumbs(file: UploadFile = File(...), width: int = Form(160)):
    job = Job()
    try:
        p = await save(job, file)

        def work():
            with open_pdf(p) as doc:
                if doc.page_count > 1000:
                    fail("Troppe pagine per l'anteprima (massimo 1000)")
                pages = []
                for page in doc:
                    r = page.rect
                    zoom = max(0.05, min(2.0, width / max(r.width, 1)))
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    data = base64.b64encode(pix.tobytes("jpeg", jpg_quality=70)).decode()
                    pages.append({"w": r.width, "h": r.height, "rot": page.rotation,
                                  "img": "data:image/jpeg;base64," + data})
                return {"pages": pages}

        return await heavy(work)
    finally:
        job.cleanup()


@app.post("/api/merge")
async def merge(files: list[UploadFile] = File(...)):
    if len(files) < 2:
        fail("Scegli almeno due file da unire")
    job = Job()
    try:
        paths = [await save(job, f, i) for i, f in enumerate(files)]

        def work():
            with fitz.open() as out:
                for p in paths:
                    with (image_doc(p) if p.suffix.lower() in IMG_EXT else open_pdf(p)) as src:
                        out.insert_pdf(src)
                res = job.path("unito.pdf")
                finish_pdf(out, res)
            return Output().add(res)

        res = await heavy(work)
        return job.send(res, f"{stem(files[0])}-unito.pdf", "application/pdf")
    except BaseException:
        job.cleanup()
        raise


@app.post("/api/split")
async def split(file: UploadFile = File(...), mode: str = Form("ranges"), ranges: str = Form(""),
                every: int = Form(1), merge_out: bool = Form(False)):
    job = Job()
    try:
        p = await save(job, file)
        base = stem(file)

        def work():
            with open_pdf(p) as doc:
                n = doc.page_count
                if mode == "every":
                    k = max(1, every)
                    groups = [list(range(i, min(i + k, n))) for i in range(0, n, k)]
                else:
                    groups = parse_ranges(ranges, n)
                if merge_out:  # "estrai": tutte le pagine scelte in un solo PDF
                    groups = [[i for g in groups for i in g]]
                outs, total = [], Output()
                for g in groups:
                    with fitz.open() as part:
                        for i in g:
                            part.insert_pdf(doc, from_page=i, to_page=i)
                        label = f"{g[0]+1}" if len(g) == 1 else f"{g[0]+1}-{g[-1]+1}"
                        o = job.path(f"{base}_p{label}.pdf")
                        finish_pdf(part, o)
                    outs.append(total.add(o))
                return outs

        def work_zip():  # lo ZIP nello stesso turno della coda, per non rimettersi in fila
            outs = work()
            return outs[0] if len(outs) == 1 else zip_files(job, outs, f"{base}-diviso.zip")

        res = await heavy(work_zip)
        return job.send(res, res.name, "application/zip" if res.suffix == ".zip" else "application/pdf")
    except BaseException:
        job.cleanup()
        raise


@app.post("/api/organize")
async def organize(file: UploadFile = File(...), pages: str = Form(...)):
    """pages = [[indice_da_0, rotazione_aggiuntiva], ...] nell'ordine finale; le pagine assenti si eliminano."""
    try:
        spec = [(int(a), int(b) % 360) for a, b in json.loads(pages)]
    except Exception:
        fail("Elenco pagine non valido")
    if not spec:
        fail("Il documento finale non puo' essere vuoto")
    job = Job()
    try:
        p = await save(job, file)

        def work():
            with open_pdf(p) as doc, fitz.open() as out:
                for idx, rot in spec:
                    if not 0 <= idx < doc.page_count:
                        fail("Pagina inesistente")
                    out.insert_pdf(doc, from_page=idx, to_page=idx)
                    if rot:
                        pg = out[-1]
                        pg.set_rotation((pg.rotation + rot) % 360)
                res = job.path("out.pdf")
                finish_pdf(out, res)
            return Output().add(res)

        res = await heavy(work)
        return job.send(res, f"{stem(file)}-modificato.pdf", "application/pdf")
    except BaseException:
        job.cleanup()
        raise


@app.post("/api/rotate")
async def rotate(file: UploadFile = File(...), angle: int = Form(90)):
    job = Job()
    try:
        p = await save(job, file)

        def work():
            with open_pdf(p) as doc:
                for pg in doc:
                    pg.set_rotation((pg.rotation + angle) % 360)
                res = job.path("out.pdf")
                finish_pdf(doc, res)
            return res

        res = await heavy(work)
        return job.send(res, f"{stem(file)}-ruotato.pdf", "application/pdf")
    except BaseException:
        job.cleanup()
        raise


GS_LEVELS = {  # livello -> (preset, dpi immagini a colori)
    "low": ("/ebook", 220),
    "medium": ("/ebook", 150),
    "high": ("/screen", 72),
}


@app.post("/api/compress")
async def compress(file: UploadFile = File(...), level: str = Form("medium"), gray: bool = Form(False)):
    if level not in GS_LEVELS:
        fail("Livello di compressione sconosciuto")
    job = Job()
    try:
        p = await save(job, file)
        await heavy(lambda: open_pdf(p).close())
        preset, dpi = GS_LEVELS[level]
        res = job.path("out.pdf")
        cmd = ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6",
               f"-dPDFSETTINGS={preset}", "-dDetectDuplicateImages=true", "-dCompressFonts=true",
               "-dDownsampleColorImages=true", f"-dColorImageResolution={dpi}",
               "-dDownsampleGrayImages=true", f"-dGrayImageResolution={dpi}",
               "-dDownsampleMonoImages=true", f"-dMonoImageResolution={max(dpi * 2, 300)}"]
        if gray:
            cmd += ["-sColorConversionStrategy=Gray", "-dProcessColorModel=/DeviceGray"]
        cmd += [f"-sOutputFile={res}", str(p)]
        r = await heavy(subprocess.run, cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not res.exists():
            log.error("Ghostscript: %s", (r.stderr or "")[-1000:])
            fail("Ghostscript non e' riuscito a comprimere il file", 500)
        before, after = p.stat().st_size, res.stat().st_size
        if after >= before:  # non peggioriamo mai: restituiamo l'originale
            res = p
        resp = job.send(res, f"{stem(file)}-compresso.pdf", "application/pdf")
        resp.headers["X-Size-Before"] = str(before)
        resp.headers["X-Size-After"] = str(min(before, after))
        resp.headers["Access-Control-Expose-Headers"] = "X-Size-Before, X-Size-After"
        return resp
    except BaseException:
        job.cleanup()
        raise


def image_doc(path: Path, page: str = "fit", margin: float = 0) -> fitz.Document:
    """Un'immagine -> documento PDF di una pagina (pagina grande come l'immagine, oppure A4)."""
    try:
        img = fitz.open(path)
        if img.page_count == 0:
            raise ValueError
        rect = img[0].rect
        pdfbytes = img.convert_to_pdf()
        img.close()
    except Exception:
        # formati che MuPDF non apre (es. webp vecchi): passiamo da Pillow
        from PIL import Image
        with Image.open(path) as im:
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "PDF", resolution=72)
        return fitz.open("pdf", buf.getvalue())
    src = fitz.open("pdf", pdfbytes)
    if page == "fit" and not margin:
        return src
    if page == "fit":
        W, H = rect.width + 2 * margin, rect.height + 2 * margin
    else:
        W, H = fitz.paper_size(page)  # "a4", "letter"
        if rect.width > rect.height:
            W, H = H, W
    out = fitz.open()
    pg = out.new_page(width=W, height=H)
    box = fitz.Rect(margin, margin, W - margin, H - margin)
    pg.show_pdf_page(box, src, 0, keep_proportion=True)
    src.close()
    return out


@app.post("/api/img2pdf")
async def img2pdf(files: list[UploadFile] = File(...), page: str = Form("fit"), margin: float = Form(0)):
    if page not in ("fit", "a4", "letter"):
        fail("Formato pagina sconosciuto")
    job = Job()
    try:
        paths = [await save(job, f, i) for i, f in enumerate(files)]

        def work():
            with fitz.open() as out:
                for p in paths:
                    src = open_pdf(p) if p.suffix.lower() == ".pdf" else \
                        image_doc(p, page, max(0.0, min(margin, 72.0)))
                    with src:
                        out.insert_pdf(src)
                res = job.path("out.pdf")
                finish_pdf(out, res)
            return Output().add(res)

        res = await heavy(work)
        name = stem(files[0]) + ("-immagini.pdf" if len(files) > 1 else ".pdf")
        return job.send(res, name, "application/pdf")
    except BaseException:
        job.cleanup()
        raise


def safe_dpi(page: fitz.Page, dpi: int) -> int:
    """Dpi per la pagina, abbassati se l'immagine supererebbe MAX_PAGE_PX pixel."""
    r = page.rect
    px = (r.width * dpi / 72) * (r.height * dpi / 72)
    if px <= MAX_PAGE_PX:
        return dpi
    return max(1, math.floor(dpi * math.sqrt(MAX_PAGE_PX / px)))


@app.post("/api/pdf2img")
async def pdf2img(file: UploadFile = File(...), format: str = Form("png"), dpi: int = Form(150),
                  ranges: str = Form("")):
    if format not in ("png", "jpg"):
        fail("Formato immagine sconosciuto")
    dpi = max(36, min(dpi, 600))
    job = Job()
    try:
        p = await save(job, file)
        base = stem(file)

        def work():
            with open_pdf(p) as doc:
                idx = [i for g in parse_ranges(ranges, doc.page_count) for i in g] if ranges.strip() \
                    else range(doc.page_count)
                outs, reduced, total = [], 0, Output()
                for i in idx:
                    page_dpi = safe_dpi(doc[i], dpi)
                    reduced += page_dpi < dpi
                    pix = doc[i].get_pixmap(dpi=page_dpi, alpha=False)
                    o = job.path(f"{base}_p{i+1:03d}.{format}")
                    if format == "jpg":
                        o.write_bytes(pix.tobytes("jpeg", jpg_quality=90))
                    else:
                        pix.save(o)
                    del pix
                    outs.append(total.add(o))
                return outs, reduced

        def work_zip():  # lo ZIP nello stesso turno della coda, per non rimettersi in fila
            outs, reduced = work()
            return (outs[0] if len(outs) == 1 else zip_files(job, outs, f"{base}-immagini.zip")), reduced

        res, reduced = await heavy(work_zip)
        if res.suffix == ".zip":
            resp = job.send(res, res.name, "application/zip")
        else:
            resp = job.send(res, res.name, "image/png" if format == "png" else "image/jpeg")
        if reduced:
            resp.headers["X-Dpi-Reduced"] = str(reduced)
        return resp
    except BaseException:
        job.cleanup()
        raise


@app.post("/api/protect")
async def protect(file: UploadFile = File(...), password: str = Form(...), owner: str = Form(""),
                  allow_print: bool = Form(True), allow_copy: bool = Form(True), allow_edit: bool = Form(False)):
    if len(password) < 1:
        fail("Scrivi una password")
    job = Job()
    try:
        p = await save(job, file)

        def work():
            try:
                pdf = pikepdf.open(p)
            except pikepdf.PasswordError:
                fail("Il PDF e' gia' protetto: sbloccalo prima")
            except Exception:
                fail("Il file non e' un PDF valido")
            perms = pikepdf.Permissions(print_lowres=allow_print, print_highres=allow_print,
                                        extract=allow_copy, accessibility=True,
                                        modify_other=allow_edit, modify_annotation=allow_edit,
                                        modify_form=allow_edit, modify_assembly=allow_edit)
            res = job.path("out.pdf")
            with pdf:
                pdf.save(res, encryption=pikepdf.Encryption(user=password, owner=owner or secrets.token_urlsafe(24),
                                                            R=6, allow=perms))
            return res

        res = await heavy(work)
        return job.send(res, f"{stem(file)}-protetto.pdf", "application/pdf")
    except BaseException:
        job.cleanup()
        raise


@app.post("/api/unlock")
async def unlock(file: UploadFile = File(...), password: str = Form("")):
    job = Job()
    try:
        p = await save(job, file)

        def work():
            try:
                pdf = pikepdf.open(p, password=password)
            except pikepdf.PasswordError:
                fail("Password sbagliata")
            except Exception:
                fail("Il file non e' un PDF valido")
            res = job.path("out.pdf")
            with pdf:
                pdf.save(res)  # senza encryption= salva in chiaro
            return res

        res = await heavy(work)
        return job.send(res, f"{stem(file)}-sbloccato.pdf", "application/pdf")
    except BaseException:
        job.cleanup()
        raise


def hex_color(s: str) -> tuple[float, float, float]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", s.strip())
    if not m:
        return (0, 0, 0)
    v = m.group(1)
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))


@app.post("/api/stamp")
async def stamp(file: UploadFile = File(...),
                numbers: bool = Form(False), num_pos: str = Form("bottom-center"), num_fmt: str = Form("{n}"),
                num_start: int = Form(1), num_size: float = Form(11), num_skip_first: bool = Form(False),
                watermark: str = Form(""), wm_size: float = Form(60), wm_opacity: float = Form(0.2),
                wm_angle: int = Form(45), wm_color: str = Form("#c0392b")):
    if not numbers and not watermark.strip():
        fail("Scegli i numeri di pagina, una filigrana o entrambi")
    job = Job()
    try:
        p = await save(job, file)

        def work():
            doc = open_pdf(p)
            total = doc.page_count
            font = fitz.Font("helv")
            for i, page in enumerate(doc):
                # lavoriamo in coordinate "come si vede" anche sulle pagine ruotate
                page.wrap_contents()
                R = page.rect
                derot = page.derotation_matrix
                if numbers and not (num_skip_first and i == 0):
                    n = num_start + i - (1 if num_skip_first else 0)
                    text = num_fmt.replace("{n}", str(n)).replace("{tot}", str(total + num_start - 1 -
                                                                                  (1 if num_skip_first else 0)))
                    tw = font.text_length(text, num_size)
                    m = 28
                    vert, horiz = (num_pos.split("-") + ["center"])[:2]
                    x = {"left": m, "center": (R.width - tw) / 2, "right": R.width - m - tw}.get(horiz, (R.width - tw) / 2)
                    y = m + num_size if vert == "top" else R.height - m
                    tw_ = fitz.TextWriter(page.rect)
                    tw_.append(fitz.Point(x, y) * derot, text, font=font, fontsize=num_size)
                    tw_.write_text(page, color=(0.15, 0.15, 0.15), morph=(fitz.Point(x, y) * derot,
                                                                         fitz.Matrix(page.rotation)))
                if watermark.strip():
                    txt = watermark.strip()
                    size = wm_size
                    tl = font.text_length(txt, size)
                    # centro della pagina (in coordinate non ruotate); il testo si scrive orizzontale
                    # centrato li' e poi si ruota attorno al centro
                    c = fitz.Point(R.width / 2, R.height / 2) * derot
                    start = fitz.Point(c.x - tl / 2, c.y + size * 0.35)
                    tw_ = fitz.TextWriter(page.rect)
                    tw_.append(start, txt, font=font, fontsize=size)
                    tw_.write_text(page, color=hex_color(wm_color), opacity=max(0.02, min(wm_opacity, 1.0)),
                                   morph=(c, fitz.Matrix(page.rotation + wm_angle)))
            res = job.path("out.pdf")
            finish_pdf(doc, res)
            doc.close()
            return res

        res = await heavy(work)
        return job.send(res, f"{stem(file)}-timbrato.pdf", "application/pdf")
    except BaseException:
        job.cleanup()
        raise


# all'avvio: pulizia di eventuali avanzi (es. container riavviato a meta' lavoro)
shutil.rmtree(TMP, ignore_errors=True)

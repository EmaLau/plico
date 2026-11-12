"""Operazioni sui PDF, separate dall'API.

Ogni operazione riceve il percorso del file di ingresso e la cartella di lavoro e restituisce un Result.
Le usano gli endpoint dell'API, le catene di operazioni e la cartella "magica" di Nextcloud.
Gli errori per l'utente sono HTTPException (messaggio in italiano, tradotto da i18n.py).
"""
from __future__ import annotations

import base64
import difflib
import io
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import pikepdf
from fastapi import HTTPException

MAX_OUT = int(float(os.environ.get("MAX_OUTPUT_MB", "4096")) * 1024 * 1024)
MAX_PAGE_PX = int(float(os.environ.get("MAX_PAGE_MPX", "50")) * 1_000_000)
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}
OCR_LANGS = {"ita", "eng"}


def fail(msg: str, status: int = 400):
    raise HTTPException(status, msg)


@dataclass
class Result:
    path: Path
    media: str = "application/pdf"
    headers: dict = field(default_factory=dict)


def media_for(path: Path) -> str:
    return {".pdf": "application/pdf", ".zip": "application/zip", ".png": "image/png", ".jpg": "image/jpeg",
            ".txt": "text/plain; charset=utf-8", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".odt": "application/vnd.oasis.opendocument.text"}.get(path.suffix.lower(), "application/octet-stream")


# ---------------------------------------------------------------- utilita'

def open_pdf(path: Path, password: str = "") -> fitz.Document:
    try:
        doc = fitz.open(path)
    except Exception:
        fail("Il file non e' un PDF valido")
    if not doc.is_pdf:
        doc.close()
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


def page_list(text: str, n: int) -> list[int]:
    """Pagine scelte (da 0); testo vuoto = tutte."""
    return [i for g in parse_ranges(text, n) for i in g] if text.strip() else list(range(n))


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


def zip_files(out_dir: Path, files: list[Path], name: str) -> Path:
    z = out_dir / name
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    return z


def one_or_zip(out_dir: Path, files: list[Path], name: str) -> Result:
    if len(files) == 1:
        return Result(files[0], media_for(files[0]))
    return Result(zip_files(out_dir, files, name), "application/zip")


def hex_color(s: str) -> tuple[float, float, float]:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (s or "").strip())
    if not m:
        return (0, 0, 0)
    v = m.group(1)
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))


DEJAVU = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def text_font() -> fitz.Font:
    """DejaVu Sans (lettere accentate, greco, cirillico) se c'e', altrimenti Helvetica."""
    return fitz.Font(fontfile=str(DEJAVU)) if DEJAVU.exists() else fitz.Font("helv")


def safe_dpi(page: fitz.Page, dpi: float) -> float:
    """Dpi per la pagina, abbassati se l'immagine supererebbe MAX_PAGE_PX pixel."""
    r = page.rect
    px = (r.width * dpi / 72) * (r.height * dpi / 72)
    if px <= MAX_PAGE_PX:
        return dpi
    return max(1, math.floor(dpi * math.sqrt(MAX_PAGE_PX / px)))


def run(cmd: list[str], what: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        fail(f"{what} non e' disponibile su questo server", 501)
    except subprocess.TimeoutExpired:
        fail(f"{what}: tempo scaduto", 504)
    return r


def frac_rect(page: fitz.Page, box) -> fitz.Rect:
    """[x0, y0, x1, y1] in frazioni della pagina come si vede (0-1, origine in alto a sinistra) ->
    rettangolo nelle coordinate di PyMuPDF (pagina non ruotata)."""
    x0, y0, x1, y1 = (float(v) for v in box)
    R = page.rect
    r = fitz.Rect(min(x0, x1) * R.width, min(y0, y1) * R.height, max(x0, x1) * R.width, max(y0, y1) * R.height)
    return r * page.derotation_matrix


def frac_point(page: fitz.Page, pt) -> fitz.Point:
    R = page.rect
    return fitz.Point(float(pt[0]) * R.width, float(pt[1]) * R.height) * page.derotation_matrix


# ---------------------------------------------------------------- strumenti di base

def info(src: Path) -> dict:
    try:
        doc = fitz.open(src)
    except Exception:
        fail("Il file non e' un PDF valido")
    with doc:
        if not doc.is_pdf:
            fail("Il file non e' un PDF valido")
        meta = {} if doc.needs_pass else {k: v for k, v in (doc.metadata or {}).items()
                                          if k in ("title", "author", "subject", "keywords", "creator", "producer") and v}
        return {"pages": doc.page_count if not doc.needs_pass else None, "encrypted": bool(doc.needs_pass),
                "size": src.stat().st_size, "metadata": meta,
                "form_fields": 0 if doc.needs_pass else sum(1 for p in doc for _ in p.widgets())}


def thumbs(src: Path, width: int = 160, pages: str = "") -> dict:
    with open_pdf(src) as doc:
        idx = page_list(pages, doc.page_count)
        if len(idx) > 1000:
            fail("Troppe pagine per l'anteprima (massimo 1000)")
        width = max(40, min(width, 2000))
        out = []
        for i in idx:
            page = doc[i]
            r = page.rect
            zoom = max(0.05, min(4.0, width / max(r.width, 1)))
            zoom = min(zoom, safe_dpi(page, zoom * 72) / 72)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            data = base64.b64encode(pix.tobytes("jpeg", jpg_quality=75)).decode()
            out.append({"i": i, "w": r.width, "h": r.height, "rot": page.rotation, "img": "data:image/jpeg;base64," + data})
        return {"pages": out}


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
        # formati che MuPDF non apre (es. HEIC dei telefoni, webp vecchi): passiamo da Pillow
        from PIL import Image
        try:
            import pi_heif
            pi_heif.register_heif_opener()
        except ImportError:
            pass
        try:
            with Image.open(path) as im:
                buf = io.BytesIO()
                im.convert("RGB").save(buf, "PDF", resolution=72)
        except Exception:
            fail(f"Immagine non leggibile: {path.name}")
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
    pg.show_pdf_page(fitz.Rect(margin, margin, W - margin, H - margin), src, 0, keep_proportion=True)
    src.close()
    return out


def merge(srcs: list[Path], out_dir: Path) -> Result:
    if len(srcs) < 2:
        fail("Scegli almeno due file da unire")
    res = out_dir / "unito.pdf"
    with fitz.open() as out:
        for p in srcs:
            with (image_doc(p) if p.suffix.lower() in IMG_EXT else open_pdf(p)) as src:
                out.insert_pdf(src)
        finish_pdf(out, res)
    return Result(Output().add(res))


def split(src: Path, out_dir: Path, mode: str = "ranges", ranges: str = "", every: int = 1,
          merge_out: bool = False, base: str = "documento") -> Result:
    with open_pdf(src) as doc:
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
                o = out_dir / f"{base}_p{label}.pdf"
                finish_pdf(part, o)
            outs.append(total.add(o))
    return one_or_zip(out_dir, outs, f"{base}-diviso.zip")


def organize(src: Path, out_dir: Path, pages) -> Result:
    """pages = [[indice_da_0, rotazione_aggiuntiva], ...] nell'ordine finale; le pagine assenti si eliminano."""
    try:
        spec = [(int(a), int(b) % 360) for a, b in (json.loads(pages) if isinstance(pages, str) else pages)]
    except Exception:
        fail("Elenco pagine non valido")
    if not spec:
        fail("Il documento finale non puo' essere vuoto")
    res = out_dir / "organizzato.pdf"
    with open_pdf(src) as doc, fitz.open() as out:
        for idx, rot in spec:
            if not 0 <= idx < doc.page_count:
                fail("Pagina inesistente")
            out.insert_pdf(doc, from_page=idx, to_page=idx)
            if rot:
                pg = out[-1]
                pg.set_rotation((pg.rotation + rot) % 360)
        finish_pdf(out, res)
    return Result(Output().add(res))


def rotate(src: Path, out_dir: Path, angle: int = 90, pages: str = "") -> Result:
    res = out_dir / "ruotato.pdf"
    with open_pdf(src) as doc:
        for i in page_list(pages, doc.page_count):
            pg = doc[i]
            pg.set_rotation((pg.rotation + int(angle)) % 360)
        finish_pdf(doc, res)
    return Result(res)


GS_LEVELS = {"low": ("/ebook", 220), "medium": ("/ebook", 150), "high": ("/screen", 72)}


def compress(src: Path, out_dir: Path, level: str = "medium", gray: bool = False) -> Result:
    if level not in GS_LEVELS:
        fail("Livello di compressione sconosciuto")
    open_pdf(src).close()
    preset, dpi = GS_LEVELS[level]
    res = out_dir / "compresso.pdf"
    cmd = ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6",
           f"-dPDFSETTINGS={preset}", "-dDetectDuplicateImages=true", "-dCompressFonts=true",
           "-dDownsampleColorImages=true", f"-dColorImageResolution={dpi}",
           "-dDownsampleGrayImages=true", f"-dGrayImageResolution={dpi}",
           "-dDownsampleMonoImages=true", f"-dMonoImageResolution={max(dpi * 2, 300)}"]
    if gray:
        cmd += ["-sColorConversionStrategy=Gray", "-dProcessColorModel=/DeviceGray"]
    r = run(cmd + [f"-sOutputFile={res}", str(src)], "Ghostscript", 1800)
    if r.returncode != 0 or not res.exists():
        fail("Ghostscript non e' riuscito a comprimere il file", 500)
    before, after = src.stat().st_size, res.stat().st_size
    if after >= before:  # non peggioriamo mai: restituiamo l'originale
        shutil.copyfile(src, res)
    return Result(res, headers={"X-Size-Before": str(before), "X-Size-After": str(min(before, after))})


def img2pdf(srcs: list[Path], out_dir: Path, page: str = "fit", margin: float = 0) -> Result:
    if page not in ("fit", "a4", "letter"):
        fail("Formato pagina sconosciuto")
    res = out_dir / "immagini.pdf"
    with fitz.open() as out:
        for p in srcs:
            src = open_pdf(p) if p.suffix.lower() == ".pdf" else image_doc(p, page, max(0.0, min(float(margin), 72.0)))
            with src:
                out.insert_pdf(src)
        finish_pdf(out, res)
    return Result(Output().add(res))


def pdf2img(src: Path, out_dir: Path, format: str = "png", dpi: int = 150, ranges: str = "",
            base: str = "documento") -> Result:
    if format not in ("png", "jpg"):
        fail("Formato immagine sconosciuto")
    dpi = max(36, min(int(dpi), 600))
    with open_pdf(src) as doc:
        outs, reduced, total = [], 0, Output()
        for i in page_list(ranges, doc.page_count):
            page_dpi = safe_dpi(doc[i], dpi)
            reduced += page_dpi < dpi
            pix = doc[i].get_pixmap(dpi=page_dpi, alpha=False)
            o = out_dir / f"{base}_p{i+1:03d}.{format}"
            if format == "jpg":
                o.write_bytes(pix.tobytes("jpeg", jpg_quality=90))
            else:
                pix.save(o)
            del pix
            outs.append(total.add(o))
    res = one_or_zip(out_dir, outs, f"{base}-immagini.zip")
    if reduced:
        res.headers["X-Dpi-Reduced"] = str(reduced)
    return res


def protect(src: Path, out_dir: Path, password: str = "", owner: str = "", allow_print: bool = True,
            allow_copy: bool = True, allow_edit: bool = False) -> Result:
    if not password:
        fail("Scrivi una password")
    try:
        pdf = pikepdf.open(src)
    except pikepdf.PasswordError:
        fail("Il PDF e' gia' protetto: sbloccalo prima")
    except Exception:
        fail("Il file non e' un PDF valido")
    perms = pikepdf.Permissions(print_lowres=allow_print, print_highres=allow_print, extract=allow_copy,
                                accessibility=True, modify_other=allow_edit, modify_annotation=allow_edit,
                                modify_form=allow_edit, modify_assembly=allow_edit)
    res = out_dir / "protetto.pdf"
    with pdf:
        pdf.save(res, encryption=pikepdf.Encryption(user=password, owner=owner or secrets.token_urlsafe(24),
                                                    R=6, allow=perms))
    return Result(res)


def unlock(src: Path, out_dir: Path, password: str = "") -> Result:
    try:
        pdf = pikepdf.open(src, password=password)
    except pikepdf.PasswordError:
        fail("Password sbagliata")
    except Exception:
        fail("Il file non e' un PDF valido")
    res = out_dir / "sbloccato.pdf"
    with pdf:
        pdf.save(res)  # senza encryption= salva in chiaro
    return Result(res)


def _placeholders(text: str, n: int, tot: int, name: str) -> str:
    return (text.replace("{n}", str(n)).replace("{tot}", str(tot)).replace("{date}", time.strftime("%d/%m/%Y"))
            .replace("{file}", name))


def _write(page, font, x, y, text, size, color=(0.15, 0.15, 0.15), opacity=1.0, angle=0, center=None):
    """Testo nelle coordinate "come si vede", anche sulle pagine ruotate."""
    derot = page.derotation_matrix
    p = fitz.Point(x, y) * derot
    tw = fitz.TextWriter(page.rect)
    tw.append(p, text, font=font, fontsize=size)
    pivot = (fitz.Point(*center) * derot) if center else p
    tw.write_text(page, color=color, opacity=opacity, morph=(pivot, fitz.Matrix(page.rotation + angle)))


def _image_with_opacity(data: bytes, opacity: float) -> bytes:
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGBA")
        if opacity < 1:
            a = im.getchannel("A").point(lambda v: int(v * opacity))
            im.putalpha(a)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def stamp(src: Path, out_dir: Path, numbers: bool = False, num_pos: str = "bottom-center", num_fmt: str = "{n}",
          num_start: int = 1, num_size: float = 11, num_skip_first: bool = False, watermark: str = "",
          wm_size: float = 60, wm_opacity: float = 0.2, wm_angle: int = 45, wm_color: str = "#c0392b",
          header: str = "", footer: str = "", hf_size: float = 9, wm_image: bytes | None = None,
          wm_image_scale: float = 0.4, name: str = "documento") -> Result:
    if not numbers and not watermark.strip() and not header.strip() and not footer.strip() and not wm_image:
        fail("Scegli i numeri di pagina, una filigrana o entrambi")
    res = out_dir / "timbrato.pdf"
    font = text_font()
    logo = _image_with_opacity(wm_image, max(0.02, min(float(wm_opacity), 1.0))) if wm_image else None
    with open_pdf(src) as doc:
        total = doc.page_count
        last = total + num_start - 1 - (1 if num_skip_first else 0)
        for i, page in enumerate(doc):
            page.wrap_contents()
            R = page.rect
            m = 28
            if numbers and not (num_skip_first and i == 0):
                n = num_start + i - (1 if num_skip_first else 0)
                text = num_fmt.replace("{n}", str(n)).replace("{tot}", str(last))
                tw = font.text_length(text, num_size)
                vert, horiz = (num_pos.split("-") + ["center"])[:2]
                x = {"left": m, "center": (R.width - tw) / 2, "right": R.width - m - tw}.get(horiz, (R.width - tw) / 2)
                y = m + num_size if vert == "top" else R.height - m
                _write(page, font, x, y, text, num_size)
            for txt, y in ((header, m * 0.75 + hf_size), (footer, R.height - m * 0.75)):
                if txt.strip():
                    t = _placeholders(txt.strip(), i + 1, total, name)
                    _write(page, font, (R.width - font.text_length(t, hf_size)) / 2, y, t, hf_size, color=(0.3, 0.3, 0.3))
            if watermark.strip():
                txt = watermark.strip()
                tl = font.text_length(txt, wm_size)
                c = (R.width / 2, R.height / 2)
                _write(page, font, c[0] - tl / 2, c[1] + wm_size * 0.35, txt, wm_size, color=hex_color(wm_color),
                       opacity=max(0.02, min(float(wm_opacity), 1.0)), angle=int(wm_angle), center=c)
            if logo:
                s = max(0.05, min(float(wm_image_scale), 1.0))
                w, h = R.width * s, R.height * s
                box = fitz.Rect((R.width - w) / 2, (R.height - h) / 2, (R.width + w) / 2, (R.height + h) / 2)
                page.insert_image(box * page.derotation_matrix, stream=logo, keep_proportion=True, rotate=-page.rotation % 360)
        finish_pdf(doc, res)
    return Result(res)


# ---------------------------------------------------------------- OCR, PDF/A, riparazione

def _ocrmypdf(src: Path, res: Path, args: list[str]):
    r = run(["ocrmypdf", "--quiet", "--jobs", "1", *args, str(src), str(res)], "OCRmyPDF")
    if r.returncode == 8:
        fail("Il PDF e' protetto da password: sbloccalo prima con 'Proteggi / Sblocca'")
    if r.returncode == 2 and "is not a valid PDF" in (r.stderr or ""):
        fail("Il file non e' un PDF valido")
    if r.returncode not in (0, 10) or not res.exists():  # 10 = PDF/A non perfetto, il file c'e' comunque
        raise RuntimeError(f"ocrmypdf {r.returncode}: {(r.stderr or '')[-800:]}")


def ocr(src: Path, out_dir: Path, lang: str = "ita+eng", force: bool = False, deskew: bool = False) -> Result:
    langs = [x for x in re.split(r"[+, ]+", lang) if x]
    if not langs or any(x not in OCR_LANGS for x in langs):
        fail(f"Lingua OCR non disponibile: {lang}")
    open_pdf(src).close()
    res = out_dir / "ocr.pdf"
    args = ["-l", "+".join(langs), "--output-type", "pdf", "--optimize", "1"]
    args += ["--force-ocr"] if force else ["--skip-text"]
    if deskew:
        if not force:
            args = [a for a in args if a != "--skip-text"] + ["--redo-ocr"]
        args += ["--deskew"] if force else []
    _ocrmypdf(src, res, args)
    return Result(Output().add(res))


def pdfa(src: Path, out_dir: Path, ocr_text: bool = False, lang: str = "ita+eng") -> Result:
    open_pdf(src).close()
    res = out_dir / "pdfa.pdf"
    args = ["--output-type", "pdfa-2", "--skip-text", "-l", "+".join(x for x in lang.split("+") if x in OCR_LANGS) or "eng"]
    if not ocr_text:
        args += ["--tesseract-timeout", "0"]  # nessun OCR: solo conversione
    _ocrmypdf(src, res, args)
    return Result(Output().add(res))


def repair(src: Path, out_dir: Path) -> Result:
    res = out_dir / "riparato.pdf"
    try:  # qpdf (dentro pikepdf) ricostruisce la tabella degli oggetti
        with pikepdf.open(src, attempt_recovery=True) as pdf:
            if len(pdf.pages) == 0:
                raise ValueError
            pdf.save(res)
        return Result(res, headers={"X-Repair-Method": "qpdf"})
    except pikepdf.PasswordError:
        fail("Il PDF e' protetto da password: sbloccalo prima con 'Proteggi / Sblocca'")
    except Exception:
        pass
    try:  # MuPDF ripara in un altro modo
        with fitz.open(src) as doc:
            if doc.page_count == 0:
                raise ValueError
            doc.save(res, garbage=4, deflate=True, clean=True)
        return Result(res, headers={"X-Repair-Method": "mupdf"})
    except Exception:
        pass
    r = run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", f"-sOutputFile={res}", str(src)],
            "Ghostscript", 1800)
    if r.returncode == 0 and res.exists() and res.stat().st_size > 0 and "Error" not in (r.stderr or "") + (r.stdout or ""):
        try:  # Ghostscript produce una pagina bianca anche da un file illeggibile: deve esserci del contenuto
            with fitz.open(res) as d:
                if any(pg.get_text().strip() or pg.get_images() or pg.get_drawings() for pg in d):
                    return Result(res, headers={"X-Repair-Method": "ghostscript"})
        except Exception:
            pass
    fail("Non sono riuscito a riparare il file: e' troppo danneggiato", 422)


# ---------------------------------------------------------------- metadati, estrazione

META_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")


def metadata(src: Path, out_dir: Path, clean: bool = False, **fields) -> Result:
    res = out_dir / "metadati.pdf"
    with open_pdf(src) as doc:
        if clean:  # via metadati, XMP, JavaScript, file allegati, miniature, testo nascosto
            doc.scrub(attached_files=True, clean_pages=True, embedded_files=True, hidden_text=True, javascript=True,
                      metadata=True, redactions=True, redact_images=0, remove_links=False, reset_fields=False,
                      reset_responses=True, thumbnails=True, xml_metadata=True)
        meta = {k: v for k, v in (doc.metadata or {}).items() if k in META_KEYS} if not clean else {}
        for k in META_KEYS:
            if fields.get(k) is not None:
                meta[k] = str(fields[k])[:1000]
        doc.set_metadata({k: meta.get(k, "") for k in META_KEYS} if (clean or meta) else {})
        if clean:
            doc.del_xml_metadata()
        doc.save(res, garbage=4, deflate=True, clean=True)
    return Result(res)


def extract(src: Path, out_dir: Path, kind: str = "images", pages: str = "", base: str = "documento",
            min_size: int = 32) -> Result:
    with open_pdf(src) as doc:
        idx = page_list(pages, doc.page_count)
        if kind == "text":
            parts = [f"===== {i + 1} =====\n{doc[i].get_text('text').strip()}\n" for i in idx]
            res = out_dir / f"{base}.txt"
            res.write_text("\n".join(parts), "utf-8")
            return Result(Output().add(res), "text/plain; charset=utf-8")
        if kind != "images":
            fail("Scegli immagini o testo")
        seen, outs, total = set(), [], Output()
        for i in idx:
            for img in doc[i].get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    data = doc.extract_image(xref)
                except Exception:
                    continue
                if not data or data["width"] < min_size or data["height"] < min_size:
                    continue
                ext = data["ext"] if data["ext"] in ("png", "jpeg", "jpg", "jpx", "tiff", "bmp", "gif") else "png"
                if ext not in ("png", "jpeg", "jpg"):
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha >= 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    o = out_dir / f"{base}_p{i+1:03d}_{len(outs)+1:03d}.png"
                    pix.save(o)
                else:
                    o = out_dir / f"{base}_p{i+1:03d}_{len(outs)+1:03d}.{'jpg' if ext == 'jpeg' else ext}"
                    o.write_bytes(data["image"])
                outs.append(total.add(o))
        if not outs:
            fail("Nel PDF non ci sono immagini da estrarre", 422)
    return Result(zip_files(out_dir, outs, f"{base}-immagini.zip"), "application/zip")


# ---------------------------------------------------------------- pagine: ritaglio, formato, piu' pagine per foglio

PAPER = {"a3", "a4", "a5", "letter", "legal"}


def _content_bbox(page: fitz.Page) -> fitz.Rect | None:
    """Rettangolo che contiene tutto cio' che non e' bianco (nelle coordinate "come si vede")."""
    zoom = 72 / 72 if max(page.rect.width, page.rect.height) < 2000 else 0.3
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY, alpha=False)
    w, h, s = pix.width, pix.height, pix.samples
    rows = [y for y in range(h) if min(s[y * w:(y + 1) * w]) < 245]
    if not rows:
        return None
    cols = [x for x in range(w) if min(s[x::w][rows[0]:rows[-1] + 1]) < 245]
    return fitz.Rect(cols[0] / zoom, rows[0] / zoom, (cols[-1] + 1) / zoom, (rows[-1] + 1) / zoom)


def pages(src: Path, out_dir: Path, mode: str = "resize", paper: str = "a4", orientation: str = "auto",
          margin_mm: float = 0, top: float = 0, right: float = 0, bottom: float = 0, left: float = 0) -> Result:
    """resize: tutte le pagine nel formato scelto; crop: togli margini fissi (mm); trim: ritaglio automatico."""
    mm = 72 / 25.4
    res = out_dir / "pagine.pdf"
    with open_pdf(src) as doc:
        if mode == "resize":
            if paper not in PAPER:
                fail("Formato pagina sconosciuto")
            W, H = fitz.paper_size(paper)
            pad = max(0.0, float(margin_mm)) * mm
            with fitz.open() as out:
                for page in doc:
                    r = page.rect
                    land = r.width > r.height if orientation == "auto" else orientation == "landscape"
                    pw, ph = (H, W) if land else (W, H)
                    np = out.new_page(width=pw, height=ph)
                    np.show_pdf_page(fitz.Rect(pad, pad, pw - pad, ph - pad), doc, page.number, keep_proportion=True)
                finish_pdf(out, res)
            return Result(Output().add(res))
        if mode not in ("crop", "trim"):
            fail("Modalita' sconosciuta")
        for page in doc:
            R = page.rect
            if mode == "crop":
                box = fitz.Rect(left * mm, top * mm, R.width - right * mm, R.height - bottom * mm)
            else:
                bb = _content_bbox(page)
                if not bb:
                    continue
                pad = max(0.0, float(margin_mm)) * mm
                box = fitz.Rect(bb.x0 - pad, bb.y0 - pad, bb.x1 + pad, bb.y1 + pad) & R
            if box.width < 36 or box.height < 36:
                fail("I margini sono troppo grandi per la pagina")
            mb = page.mediabox
            crop = box * page.derotation_matrix
            crop = fitz.Rect(crop.x0 + mb.x0, crop.y0 + mb.y0, crop.x1 + mb.x0, crop.y1 + mb.y0) & mb
            page.set_cropbox(crop)
        finish_pdf(doc, res)
    return Result(res)


def nup(src: Path, out_dir: Path, mode: str = "nup", n: int = 2, paper: str = "a4", gap_mm: float = 4) -> Result:
    """nup: n pagine per foglio; booklet: opuscolo da stampare fronte-retro e piegare a meta'."""
    if paper not in PAPER:
        fail("Formato pagina sconosciuto")
    W, H = fitz.paper_size(paper)
    gap = max(0.0, float(gap_mm)) * 72 / 25.4
    res = out_dir / ("opuscolo.pdf" if mode == "booklet" else "fogli.pdf")
    with open_pdf(src) as doc, fitz.open() as out:
        total = doc.page_count
        if mode == "booklet":
            k = math.ceil(total / 4) * 4
            order = []
            for s in range(k // 4):
                order += [(k - 1 - 2 * s, 2 * s), (2 * s + 1, k - 2 - 2 * s)]
            for left_i, right_i in order:
                sheet = out.new_page(width=H, height=W)  # orizzontale
                for slot, i in enumerate((left_i, right_i)):
                    if i < total:
                        x0 = slot * H / 2
                        sheet.show_pdf_page(fitz.Rect(x0 + gap, gap, x0 + H / 2 - gap, W - gap), doc, i, keep_proportion=True)
        else:
            n = int(n)
            grid = {2: (2, 1), 4: (2, 2), 6: (3, 2), 8: (4, 2), 9: (3, 3), 16: (4, 4)}.get(n)
            if not grid:
                fail("Pagine per foglio: 2, 4, 6, 8, 9 o 16")
            cols, rows = grid
            land = n in (2, 6, 8)
            pw, ph = (H, W) if land else (W, H)
            for start in range(0, total, n):
                sheet = out.new_page(width=pw, height=ph)
                cw, ch = pw / cols, ph / rows
                for k_, i in enumerate(range(start, min(start + n, total))):
                    c, r = k_ % cols, k_ // cols
                    sheet.show_pdf_page(fitz.Rect(c * cw + gap, r * ch + gap, (c + 1) * cw - gap, (r + 1) * ch - gap),
                                        doc, i, keep_proportion=True)
        finish_pdf(out, res)
    return Result(Output().add(res))


# ---------------------------------------------------------------- firma, annotazioni, moduli, oscuramento

def sign(src: Path, out_dir: Path, image: bytes, page: int = -1, box=(0.6, 0.8, 0.9, 0.9)) -> Result:
    """Inserisce l'immagine della firma nel riquadro box (frazioni della pagina come si vede)."""
    if not image:
        fail("Disegna la firma o scegli un'immagine")
    try:
        png = _image_with_opacity(image, 1.0)
    except Exception:
        fail("Immagine della firma non leggibile")
    res = out_dir / "firmato.pdf"
    with open_pdf(src) as doc:
        p = doc[int(page) if 0 <= int(page) < doc.page_count else doc.page_count - 1]
        p.insert_image(frac_rect(p, box), stream=png, keep_proportion=True, rotate=-p.rotation % 360)
        finish_pdf(doc, res)
    return Result(res)


def annotate(src: Path, out_dir: Path, items, flatten: bool = False) -> Result:
    """items: [{"page", "type": highlight|rect|text|note|arrow|ink, "box"/"from"/"to"/"points", "color", "text"}]"""
    try:
        items = json.loads(items) if isinstance(items, str) else items
        assert isinstance(items, list)
    except Exception:
        fail("Elenco annotazioni non valido")
    if not items:
        fail("Aggiungi almeno un'annotazione")
    res = out_dir / "annotato.pdf"
    with open_pdf(src) as doc:
        for it in items:
            pg = int(it.get("page", 0))
            if not 0 <= pg < doc.page_count:
                fail("Pagina inesistente")
            page = doc[pg]
            color = hex_color(it.get("color", "#ffd400"))
            kind = it.get("type")
            if kind == "highlight":
                r = frac_rect(page, it["box"])
                words = [fitz.Rect(w[:4]) for w in page.get_text("words") if fitz.Rect(w[:4]).intersects(r)]
                a = page.add_highlight_annot([w.quad for w in words] if words else r.quad)
            elif kind == "rect":
                a = page.add_rect_annot(frac_rect(page, it["box"]))
                a.set_border(width=float(it.get("width", 2)))
            elif kind == "text":
                a = page.add_freetext_annot(frac_rect(page, it["box"]), str(it.get("text", ""))[:2000],
                                            fontsize=float(it.get("size", 12)), text_color=color, fontname="helv",
                                            rotate=page.rotation)
            elif kind == "note":
                a = page.add_text_annot(frac_point(page, it["at"]), str(it.get("text", ""))[:5000])
            elif kind == "arrow":
                a = page.add_line_annot(frac_point(page, it["from"]), frac_point(page, it["to"]))
                a.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_OPEN_ARROW)
                a.set_border(width=float(it.get("width", 2)))
            elif kind == "ink":
                a = page.add_ink_annot([[tuple(frac_point(page, p)) for p in it["points"]]])
                a.set_border(width=float(it.get("width", 2)))
            else:
                fail(f"Tipo di annotazione sconosciuto: {kind}")
            if kind != "text":
                a.set_colors(stroke=color)
            if it.get("opacity") is not None:
                a.set_opacity(float(it["opacity"]))
            a.update()
        if flatten:
            doc.bake(annots=True, widgets=False)
        finish_pdf(doc, res)
    return Result(res)


def form_fields(src: Path) -> dict:
    with open_pdf(src) as doc:
        out = []
        for page in doc:
            for w in page.widgets():
                out.append({"name": w.field_name, "label": w.field_label or w.field_name, "type": w.field_type_string,
                            "value": w.field_value, "options": list(w.choice_values or []), "page": page.number,
                            "on": w.on_state() if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON) else None})
        return {"fields": out}


def fill_form(src: Path, out_dir: Path, values, flatten: bool = False) -> Result:
    try:
        values = json.loads(values) if isinstance(values, str) else values
        assert isinstance(values, dict)
    except Exception:
        fail("Valori dei campi non validi")
    res = out_dir / "compilato.pdf"
    with open_pdf(src) as doc:
        found = 0
        for page in doc:
            for w in page.widgets():
                if w.field_name not in values:
                    continue
                v = values[w.field_name]
                if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                    on = w.on_state()
                    w.field_value = on if (v is True or v == on or str(v).lower() in ("true", "1", "on", "si", "yes")) else "Off"
                else:
                    w.field_value = str(v)
                w.update()
                found += 1
        if flatten:
            doc.bake(annots=False, widgets=True)
        finish_pdf(doc, res)
    return Result(res, headers={"X-Fields-Filled": str(found)})


REDACT_PRESETS = {
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "phone": r"(?:\+\d{1,3})?\d{6,13}",
    "iban": r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}",
    "cf": r"[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]",  # codice fiscale
    "card": r"\d{13,19}",
}


def redact(src: Path, out_dir: Path, terms: str = "", presets: str = "", areas="[]", regex: str = "",
           clean_metadata: bool = True) -> Result:
    """Oscuramento vero: il testo sotto i riquadri viene tolto dal file, non solo coperto."""
    try:
        areas = json.loads(areas) if isinstance(areas, str) else areas
    except Exception:
        fail("Elenco aree non valido")
    words = [t.strip() for t in re.split(r"[\n;]+", terms) if t.strip()]
    pats = [REDACT_PRESETS[p] for p in re.split(r"[,\s]+", presets) if p in REDACT_PRESETS]
    if regex.strip():
        try:
            re.compile(regex)
        except re.error:
            fail("Espressione regolare non valida")
        pats.append(regex.strip())
    rx = [re.compile(p) for p in pats]
    if not words and not rx and not areas:
        fail("Scrivi cosa oscurare o disegna le aree")
    count = 0
    res = out_dir / "oscurato.pdf"
    with open_pdf(src) as doc:
        for page in doc:
            hits = [r for w in words for r in page.search_for(w)]
            if rx:
                for wd in page.get_text("words"):
                    token = re.sub(r"[^\w@.+-]", "", wd[4])
                    if any(r.fullmatch(token) or r.fullmatch(wd[4]) for r in rx):
                        hits.append(fitz.Rect(wd[:4]))
            for a in areas or []:
                if int(a.get("page", -1)) == page.number:
                    hits.append(frac_rect(page, a["box"]))
            for r in hits:
                page.add_redact_annot(r, fill=(0, 0, 0))
            if hits:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
                count += len(hits)
        if clean_metadata:
            doc.set_metadata({})
            doc.del_xml_metadata()
        doc.save(res, garbage=4, deflate=True, clean=True)
    return Result(res, headers={"X-Redactions": str(count)})


# ---------------------------------------------------------------- confronto

def compare(a: Path, b: Path, out_dir: Path, dpi: int = 72) -> Result:
    """Rapporto PDF: riepilogo, parole aggiunte/tolte per pagina e le pagine affiancate con le differenze in rosso."""
    from PIL import Image, ImageChops
    res = out_dir / "confronto.pdf"
    font = text_font()
    with open_pdf(a) as da, open_pdf(b) as db, fitz.open() as out:
        n = max(da.page_count, db.page_count)
        changed, summary = [], []
        for i in range(n):
            ta = da[i].get_text("words") if i < da.page_count else []
            tb = db[i].get_text("words") if i < db.page_count else []
            wa, wb = [w[4] for w in ta], [w[4] for w in tb]
            sm = difflib.SequenceMatcher(None, wa, wb, autojunk=False)
            removed = [w for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("delete", "replace") for w in wa[i1:i2]]
            added = [w for op, i1, i2, j1, j2 in sm.get_opcodes() if op in ("insert", "replace") for w in wb[j1:j2]]
            imgs = []
            for d in (da, db):
                if i < d.page_count:
                    pix = d[i].get_pixmap(dpi=safe_dpi(d[i], dpi), alpha=False)
                    imgs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
                else:
                    imgs.append(None)
            boxes = []
            if imgs[0] and imgs[1]:
                ib = imgs[1].resize(imgs[0].size)
                diff = ImageChops.difference(imgs[0], ib).convert("L").point(lambda v: 255 if v > 40 else 0)
                step = 24
                for y in range(0, diff.height, step):
                    for x in range(0, diff.width, step):
                        if diff.crop((x, y, x + step, y + step)).getbbox():
                            boxes.append((x / diff.width, y / diff.height, (x + step) / diff.width, (y + step) / diff.height))
            if removed or added or boxes or not (imgs[0] and imgs[1]):
                changed.append(i)
                summary.append((i, removed, added, imgs, boxes))
        # pagina di riepilogo
        W, H = fitz.paper_size("a4")
        cover = out.new_page(width=W, height=H)
        y = 60
        lines = [("Confronto tra due PDF", 20), (f"A: {a.name} ({da.page_count} pagine)", 11),
                 (f"B: {b.name} ({db.page_count} pagine)", 11), ("", 8),
                 ("Nessuna differenza trovata." if not changed else
                  f"Pagine con differenze: {', '.join(str(i + 1) for i in changed)}", 12)]
        for i, removed, added, _, boxes in summary[:40]:
            lines.append((f"Pagina {i + 1}: {len(removed)} parole tolte, {len(added)} aggiunte, {len(boxes)} zone diverse", 10))
            if removed:
                lines.append(("  − " + " ".join(removed)[:180], 8))
            if added:
                lines.append(("  + " + " ".join(added)[:180], 8))
        for text, size in lines:
            if y > H - 50:
                break
            if text:
                tw = fitz.TextWriter(cover.rect)
                tw.append((50, y), text, font=font, fontsize=size)
                tw.write_text(cover, color=(0.85, 0.1, 0.1) if text.startswith("  −") else
                              (0.1, 0.55, 0.2) if text.startswith("  +") else (0.1, 0.1, 0.1))
            y += size * 1.6
        # pagine affiancate
        for i, removed, added, imgs, boxes in summary:
            sheet = out.new_page(width=H, height=W)
            half = H / 2
            for slot, (d, label) in enumerate(((da, "A"), (db, "B"))):
                x0 = slot * half
                tw = fitz.TextWriter(sheet.rect)
                tw.append((x0 + 20, 24), f"{label} · pagina {i + 1}", font=font, fontsize=10)
                tw.write_text(sheet)
                if i < d.page_count:
                    area = fitz.Rect(x0 + 16, 34, x0 + half - 16, W - 16)
                    sheet.show_pdf_page(area, d, i, keep_proportion=True)
                    pr = d[i].rect
                    s = min(area.width / pr.width, area.height / pr.height)
                    ox = area.x0 + (area.width - pr.width * s) / 2
                    oy = area.y0 + (area.height - pr.height * s) / 2
                    for bx in boxes:
                        r = fitz.Rect(ox + bx[0] * pr.width * s, oy + bx[1] * pr.height * s,
                                      ox + bx[2] * pr.width * s, oy + bx[3] * pr.height * s)
                        sheet.draw_rect(r, color=None, fill=(1, 0, 0), fill_opacity=0.25, overlay=True)
        finish_pdf(out, res)
    return Result(res, headers={"X-Pages-Changed": str(len(changed))})


# ---------------------------------------------------------------- scanner da telefono

def _scan_image(path: Path, mode: str):
    import cv2
    import numpy as np
    data = np.frombuffer(path.read_bytes(), np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:  # HEIC e altri formati: passiamo da Pillow
        from PIL import Image
        try:
            import pi_heif
            pi_heif.register_heif_opener()
        except ImportError:
            pass
        try:
            with Image.open(path) as im:
                img = cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR)
        except Exception:
            fail(f"Immagine non leggibile: {path.name}")
    h, w = img.shape[:2]
    scale = 1000 / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img.copy()
    scale = min(scale, 1)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8))
    quad = None
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.25 * small.shape[0] * small.shape[1]:
            quad = approx.reshape(4, 2).astype("float32") / scale
            break
    found = quad is not None
    if found:  # raddrizza: angoli in ordine alto-sx, alto-dx, basso-dx, basso-sx
        s, d = quad.sum(1), np.diff(quad, axis=1).ravel()
        tl, br, tr, bl = quad[np.argmin(s)], quad[np.argmax(s)], quad[np.argmin(d)], quad[np.argmax(d)]
        W = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        H = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
        M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl]), np.array([[0, 0], [W, 0], [W, H], [0, H]], "float32"))
        img = cv2.warpPerspective(img, M, (W, H))
    if mode == "gray":
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif mode == "bw":
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes(), found


def scan(srcs: list[Path], out_dir: Path, mode: str = "color", paper: str = "a4") -> Result:
    if mode not in ("color", "gray", "bw"):
        fail("Modalita' sconosciuta")
    if not srcs:
        fail("Scegli almeno una foto")
    res = out_dir / "scansione.pdf"
    found = 0
    with fitz.open() as out:
        for p in srcs:
            jpg, ok = _scan_image(p, mode)
            found += ok
            with fitz.open("jpg", jpg) as im:
                r = im[0].rect
            if paper == "fit":
                page = out.new_page(width=r.width, height=r.height)
                page.insert_image(page.rect, stream=jpg)
            else:
                W, H = fitz.paper_size(paper if paper in PAPER else "a4")
                if r.width > r.height:
                    W, H = H, W
                page = out.new_page(width=W, height=H)
                page.insert_image(fitz.Rect(14, 14, W - 14, H - 14), stream=jpg, keep_proportion=True)
        finish_pdf(out, res)
    return Result(Output().add(res), headers={"X-Pages-Straightened": str(found)})


# ---------------------------------------------------------------- catene di operazioni

# operazioni che prendono un PDF e restituiscono un PDF: si possono mettere in fila
CHAIN_OPS = {
    "compress": (compress, "compress"), "stamp": (stamp, "stamp"), "protect": (protect, "protect"),
    "unlock": (unlock, "protect"), "rotate": (rotate, "rotate"), "ocr": (ocr, "ocr"), "pdfa": (pdfa, "pdfa"),
    "repair": (repair, "repair"), "metadata": (metadata, "metadata"), "pages": (pages, "pages"),
    "nup": (nup, "nup"), "redact": (redact, "redact"), "organize": (organize, "organize"),
}
CHAIN_FORBIDDEN_OPTS = {"wm_image", "image", "name"}


def chain(src: Path, out_dir: Path, steps, name: str = "documento") -> Result:
    """steps = [{"op": "compress", "level": "high"}, {"op": "stamp", "numbers": true}, ...]"""
    try:
        steps = json.loads(steps) if isinstance(steps, str) else steps
        assert isinstance(steps, list) and steps
    except Exception:
        fail("Catena di operazioni non valida")
    if len(steps) > 12:
        fail("Troppe operazioni in una catena (massimo 12)")
    cur, headers = src, {}
    for k, step in enumerate(steps):
        op = step.get("op") if isinstance(step, dict) else None
        if op not in CHAIN_OPS:
            fail(f"Operazione sconosciuta nella catena: {op}")
        fn = CHAIN_OPS[op][0]
        opts = {k2: v for k2, v in step.items() if k2 != "op" and k2 not in CHAIN_FORBIDDEN_OPTS}
        if op == "stamp":
            opts["name"] = name
        step_dir = out_dir / f"step{k}"
        step_dir.mkdir(exist_ok=True)
        try:
            r = fn(cur, step_dir, **opts)
        except TypeError as e:
            fail(f"Opzioni non valide per '{op}': {e}")
        if r.path.suffix != ".pdf":
            fail(f"'{op}' non produce un PDF")
        cur, headers = r.path, {**headers, **r.headers}
    final = out_dir / "catena.pdf"
    shutil.copyfile(cur, final)
    return Result(final, headers={k: v for k, v in headers.items() if k != "X-Size-Before"})


def step_perms(steps) -> set[str]:
    try:
        steps = json.loads(steps) if isinstance(steps, str) else steps
        return {CHAIN_OPS[s["op"]][1] for s in steps if isinstance(s, dict) and s.get("op") in CHAIN_OPS}
    except Exception:
        return set()

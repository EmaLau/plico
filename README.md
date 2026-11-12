# Universal-PDF

<p align="center"><img src="docs/cover.svg" width="400" alt=""></p>

🇬🇧 **English** · 🇮🇹 [Italiano](README.it.md)

**Self-hosted PDF tools on a single web page.** Merge, split, extract, reorder, rotate, delete pages, compress, convert between PDF and images, protect or unlock with a password, add page numbers and watermarks. Everything runs on your own server: each request works in a temporary folder that is deleted as soon as the result has been sent, so **no file stays on the server**.

![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PyMuPDF](https://img.shields.io/badge/PyMuPDF-1.26-e5322d)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)

## Tools

| Group | Tools |
|---|---|
| Organize | Merge (PDFs and images together), Split (by ranges or every N pages), Extract pages, Reorder / rotate / delete with page thumbnails, Rotate all pages |
| Optimize | Compress (three levels, optional grayscale) with Ghostscript; the original is returned if compression would make it bigger |
| Convert | Images → PDF (fit, A4 or Letter, with margins), PDF → JPG/PNG at a chosen DPI |
| Security | Protect with a password (AES-256), Unlock |
| Edit | Page numbers (position, format such as `Page {n} of {tot}`, start number, skip first page) and text watermark (size, opacity, angle, colour), also on rotated pages |

> The user interface is in Italian. The API and this documentation are language-independent.

## Quick start

You need Docker with Docker Compose.

```bash
git clone https://github.com/EmaLau/universal-pdf.git
cd universal-pdf
docker compose up -d --build
```

Open <http://localhost:8080>. To check that every tool works:

```bash
docker compose exec universal-pdf python3 /app/selftest.py
```

The selftest runs 21 checks against the live server and saves sample results in `/work/selftest/` inside the container.

> **Security note.** The service has no login and by default listens only on `127.0.0.1`. Open it to the network only if the network is trusted (home, VPN), or put it behind a reverse proxy with authentication. Do not expose it directly to the Internet.

## Configuration

Copy `.env.example` to `.env` and change what you need.

| Variable | Default | Description |
|---|---|---|
| `UPDF_BIND` / `UPDF_PORT` | `127.0.0.1` / `8080` | Where to publish the service (`0.0.0.0` for the whole network) |
| `MAX_UPLOAD_MB` | `2048` | Maximum size of each uploaded file |
| `UPDF_CPUS` / `UPDF_MEMORY` | `4` / `3G` | Container resource limits |
| `UPDF_UID` / `UPDF_GID` | `1000` | User that runs the service inside the container |
| `TZ` | `Europe/Rome` | Time zone |

## API

All endpoints are `POST` with `multipart/form-data`. They answer with the resulting file, or with JSON `{"detail": "..."}` and an HTTP error code.

| Endpoint | Fields | Result |
|---|---|---|
| `/api/info` | `file` | `{"pages", "encrypted", "size"}` |
| `/api/thumbs` | `file`, `width` | `{"pages": [{"w", "h", "png"}]}` (PNG data URLs) |
| `/api/merge` | `files` (2 or more, PDFs or images) | PDF |
| `/api/split` | `file`, `mode` (`ranges` or `every`), `ranges` (`1-3, 5, 8-`), `every`, `merge_out` | ZIP, or PDF if there is a single output |
| `/api/organize` | `file`, `pages` (JSON `[[index, rotation], ...]`, 0-based) | PDF |
| `/api/rotate` | `file`, `angle` | PDF |
| `/api/compress` | `file`, `level` (`low`, `medium`, `high`), `gray` | PDF, with headers `X-Size-Before` / `X-Size-After` |
| `/api/img2pdf` | `files`, `page` (`fit`, `a4`, `letter`), `margin` | PDF |
| `/api/pdf2img` | `file`, `format` (`png`, `jpg`), `dpi`, `ranges` | ZIP, or an image for a single page |
| `/api/protect` | `file`, `password`, `owner` | PDF (AES-256) |
| `/api/unlock` | `file`, `password` | PDF |
| `/api/stamp` | `file`, `numbers`, `num_pos`, `num_fmt`, `num_start`, `num_size`, `num_skip_first`, `watermark`, `wm_size`, `wm_opacity`, `wm_angle`, `wm_color` | PDF |

`GET /healthz` returns `{"ok": true}`.

```bash
# merge two PDFs
curl -F files=@a.pdf -F files=@b.pdf -o merged.pdf http://localhost:8080/api/merge

# compress
curl -F file=@scan.pdf -F level=high -o smaller.pdf http://localhost:8080/api/compress
```

## How it works

- **FastAPI** server (`server/server.py`) with a single static page (`server/static/index.html`, no build step and no external resources).
- **PyMuPDF** for pages, thumbnails, images and stamps; **pikepdf** for encryption; **Ghostscript** for compression.
- Each request creates a folder under `/work/upd`, and a background task removes it once the response has been sent. Leftovers from an interrupted run are removed when the service starts.
- The container runs as an unprivileged user, behind `tini`.

## Project layout

```
server/
  Dockerfile       Debian trixie + Python, PyMuPDF, pikepdf, Ghostscript
  server.py        API and page
  static/          the web page
  selftest.py      real test of every tool against the running server
docker-compose.yml
.env.example
```

## License

[GNU Affero General Public License v3.0](LICENSE), the same licence as PyMuPDF. You are free to use, modify and redistribute the project. If you modify it and offer it as a network service, you must also make the source code of your changes available.

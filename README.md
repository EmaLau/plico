# Universal-PDF

<p align="center"><img src="docs/cover.svg" width="400" alt=""></p>

🇬🇧 **English** · 🇮🇹 [Italiano](README.it.md)

> **Work in progress — private repository.** It runs on one homelab; a few limits must be fixed before publishing. See [To do before publishing](#to-do-before-publishing).

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

The selftest runs about 30 checks (some only when the related setting is enabled) against the live server and saves sample results in `/work/selftest/` inside the container.

> **Security note.** The web page has no login and by default the service listens only on `127.0.0.1`. API keys (below) control scripts, not the page. Open it to the network only if the network is trusted (home, VPN), or put it behind a reverse proxy with authentication. Do not expose it directly to the Internet.

## Configuration

Copy `.env.example` to `.env` and change what you need.

| Variable | Default | Description |
|---|---|---|
| `UPDF_BIND` / `UPDF_PORT` | `127.0.0.1` / `8080` | Where to publish the service (`0.0.0.0` for the whole network) |
| `MAX_UPLOAD_MB` | `0` | Maximum size of each uploaded file; `0` means no limit |
| `MAX_OUTPUT_MB` | `4096` | Maximum total size of the results of one request (e.g. all the images of *PDF to images*) |
| `MAX_PARALLEL` | `2` | Heavy jobs run at the same time; the others wait their turn |
| `MAX_PAGE_MPX` | `50` | Maximum megapixels for a page rendered by *PDF to images*: larger pages get a lower DPI |
| `UPDF_CPUS` / `UPDF_MEMORY` | `4` / `3G` | Container resource limits |
| `UPDF_ADMIN_PASSWORD` | empty | Password of the `/admin` page where API keys are managed. Empty = admin page disabled. It can also be written in the file `admin-password` inside `DATA_DIR` |
| `UPDF_ADMIN_LOGIN` | `true` | Initial value of the *admin password* switch. `false` = the `/admin` page opens without a password, so anyone who can reach the service can manage keys. The switch on `/admin` overrides it and is remembered |
| `API_REQUIRE_KEY` | `false` | Initial value of the *key required* switch: `true` = API calls made outside the web page need an API key. The switch on the `/admin` page overrides it and is remembered |
| `DATA_DIR` | `/work/data` | Where API keys (only their SHA-256 hashes) and the signing secret are stored |
| `UPDF_UID` / `UPDF_GID` | `1000` | User that runs the service inside the container |
| `TZ` | `Europe/Rome` | Time zone |

## API

Interactive documentation (Swagger UI) is at **`/apidocs`**, the OpenAPI schema at `/apidocs/openapi.json`.

### API keys

API keys work like in [Gokapi](https://github.com/Forceu/Gokapi):

1. Set `UPDF_ADMIN_PASSWORD` and open **`/admin`**.
2. Create a key with a name and the permissions it needs, one per tool (`info`, `merge`, `split`, `organize`, `rotate`, `compress`, `img2pdf`, `pdf2img`, `protect`, `stamp`). The full key is shown only once; the server keeps its SHA-256 hash, the last time it was used, and lets you change permissions or revoke it.
3. Send it in the `apikey` header:

```bash
curl -H "apikey: updf_..." -F files=@a.pdf -F files=@b.pdf -o merged.pdf http://localhost:8080/api/merge
```

A wrong or revoked key gets `401`, a key without the permission for that tool gets `403`; both are checked before the upload is received. The web page does not need a key: opening it sets a signed session cookie. When *Key required for the API* is switched on in `/admin` (initial value from `API_REQUIRE_KEY`), calls with neither a key nor that cookie get `401`. Anyone who can open the page can still get the cookie, so this keeps scripts in order; it is not a protection against people who can reach the service.

### Endpoints

All endpoints are `POST` with `multipart/form-data`. They answer with the resulting file, or with JSON `{"detail": "..."}` and an HTTP error code.

| Endpoint | Fields | Result |
|---|---|---|
| `/api/info` | `file` | `{"pages", "encrypted", "size"}` |
| `/api/thumbs` | `file`, `width` | `{"pages": [{"w", "h", "rot", "img"}]}` (`img` is a JPEG data URL) |
| `/api/merge` | `files` (2 or more, PDFs or images) | PDF |
| `/api/split` | `file`, `mode` (`ranges` or `every`), `ranges` (`1-3, 5, 8-`), `every`, `merge_out` | ZIP, or PDF if there is a single output |
| `/api/organize` | `file`, `pages` (JSON `[[index, rotation], ...]`, 0-based) | PDF |
| `/api/rotate` | `file`, `angle` | PDF |
| `/api/compress` | `file`, `level` (`low`, `medium`, `high`), `gray` | PDF, with headers `X-Size-Before` / `X-Size-After` |
| `/api/img2pdf` | `files`, `page` (`fit`, `a4`, `letter`), `margin` | PDF |
| `/api/pdf2img` | `file`, `format` (`png`, `jpg`), `dpi`, `ranges` | ZIP, or an image for a single page. Pages that would exceed `MAX_PAGE_MPX` are rendered at a lower DPI and counted in the `X-Dpi-Reduced` header |
| `/api/protect` | `file`, `password`, `owner`, `allow_print`, `allow_copy`, `allow_edit` | PDF (AES-256). Without `owner`, a random owner password is generated, so the permissions are enforced |
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
- API keys and the `/admin` page are in `server/apikeys.py` and `server/static/admin.html`.
- The container runs as an unprivileged user, behind `tini`.

## Project layout

```
server/
  Dockerfile       Debian trixie + Python, PyMuPDF, pikepdf, Ghostscript
  server.py        API and page
  apikeys.py       API keys and /admin login
  static/          the web page (index.html) and the admin page (admin.html)
  selftest.py      real test of every tool against the running server
  requirements.txt pinned Python dependencies
tests/
  test_api.py      API tests with FastAPI's TestClient (no container)
  test_ui.py       every tool driven from the page in headless Chromium (Playwright)
.github/workflows/ci.yml   pytest + Docker build + selftest on every push
docker-compose.yml
.env.example
```

## Development

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium   # or use your Chrome: PW_CHANNEL=chrome
python -m pytest                        # needs Ghostscript installed for the compress test
```

The same tests run in GitHub Actions, together with a Docker build and the selftest inside the container.

## To do before publishing

- [x] Cap the pixel size of each page in PDF → images: a tiny PDF with a huge page can exhaust the container memory
- [x] Random owner password when none is given
- [x] `/api/info`: answer 413, not 400, for files over the limit; fix the `/api/thumbs` response in the docs (`img`, `rot`)
- [x] Uploads are spooled to the data volume, not to the container filesystem; limit on output size
- [x] Limit on parallel heavy jobs
- [x] pytest tests, browser test of the page, CI
- [ ] English or bilingual interface, security headers
- [ ] Review the name and make sure nothing is copied from the site that inspired it

## License

[GNU Affero General Public License v3.0](LICENSE), the same licence as PyMuPDF. You are free to use, modify and redistribute the project. If you modify it and offer it as a network service, you must also make the source code of your changes available.

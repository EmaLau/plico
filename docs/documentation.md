# Plico — Documentation

🇬🇧 **English** · 🇮🇹 [Italiano](documentazione.md)

This is the complete guide: installation, configuration, every part of the service, how it works inside, security, maintenance and development. The API reference with examples is in [api.md](api.md); the short version of everything is in the [README](../README.md).

- [Overview](#overview)
- [Installation](#installation)
- [Configuration](#configuration)
- [Using the web page](#using-the-web-page)
- [The admin page](#the-admin-page)
- [Saved chains](#saved-chains)
- [Office documents (Universal Converter)](#office-documents-universal-converter)
- [Nextcloud: right click → Strumenti PDF](#nextcloud-right-click--strumenti-pdf)
- [Nextcloud: magic folder](#nextcloud-magic-folder)
- [How it works](#how-it-works)
- [Security and privacy](#security-and-privacy)
- [Maintenance](#maintenance)
- [Development](#development)
- [Reusing the building blocks](#reusing-the-building-blocks)
- [Known limits](#known-limits)

# Overview

Plico is a set of PDF tools on a single web page, running on your own server. It is a FastAPI service with no database: every request receives its files, works on them in a temporary folder, sends back the result and deletes the folder. The only things kept on disk are the settings in `DATA_DIR` (API key hashes, saved chains, switches).

| Group | Tools |
|---|---|
| Organize | Merge, Split, Extract pages, Reorder / rotate / delete with thumbnails, Rotate |
| Optimize and convert | Compress, Images → PDF, PDF → JPG/PNG, OCR, PDF/A-2, Scanner, Word/Excel/PowerPoint ↔ PDF (optional) |
| Security | Protect (AES-256), Unlock |
| Edit and sign | Page numbers, header/footer, text and image watermark, Sign, Fill forms, Annotate, Redact, Metadata |
| Advanced | Compare, Crop and resize, N-up and booklet, Extract images and text, Repair, Batch and chains |
| Integrations | API keys, Nextcloud app, Nextcloud magic folder (all optional) |

## By the numbers

- 28 tool endpoints, 25 API permissions, 3 saved chains ready on first start.
- About 5,000 lines of Python, JavaScript and PHP, no build step, no external resources in the page.
- 110 pytest tests (API, tools, page in headless Chromium) and a selftest of about 50 checks against the running container.
- Docker image of about 870 MB (most of it is Tesseract and OpenCV for OCR and the scanner).

# Installation

## With Docker Compose (recommended)

```bash
git clone https://github.com/EmaLau/plico.git
cd plico
cp .env.example .env        # optional: change what you need
docker compose up -d --build
```

Open <http://localhost:8080>, then check every tool:

```bash
docker compose exec plico python3 /app/selftest.py
```

By default the service listens only on `127.0.0.1`. To reach it from other devices set `PLICO_BIND=0.0.0.0` in `.env`, but read [Security and privacy](#security-and-privacy) first.

## With Docker, without Compose

```bash
docker build -t plico -f server/Dockerfile .
docker run -d --name plico -p 127.0.0.1:8080:8080 -v plico-work:/work \
  -e PLICO_ADMIN_PASSWORD=change-me plico
```

The build context is the repository root, because the image also builds the documentation pages from `docs/`. `--build-arg UID=… --build-arg GID=…` choose the user that runs the service (default 1000). It must own the `/work` volume.

## Without Docker (development)

You need Python 3.11 or newer, Ghostscript, and for OCR `ocrmypdf` with Tesseract (`ita` and `eng`).

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r server/requirements.txt
cd server && WORK_DIR=/tmp/plico uvicorn server:app --port 8080
```

# Configuration

All settings are environment variables. With Compose they are read from `.env`; `.env.example` lists them with comments.

| Variable | Default | Description |
|---|---|---|
| `PLICO_BIND` / `PLICO_PORT` | `127.0.0.1` / `8080` | Where Compose publishes the service |
| `MAX_UPLOAD_MB` | `0` | Maximum size of each uploaded file; `0` = no limit |
| `MAX_OUTPUT_MB` | `4096` | Maximum total size of the results of one request |
| `MAX_PARALLEL` | `2` | Heavy jobs running at the same time; the others wait |
| `MAX_PAGE_MPX` | `50` | Maximum megapixels of a page in *PDF to images*; larger pages get a lower DPI |
| `PLICO_CPUS` / `PLICO_MEMORY` | `4` / `3G` | Container limits (Compose) |
| `PLICO_ADMIN_PASSWORD` | empty | Password of `/admin`. Can also be written in `DATA_DIR/admin-password` |
| `PLICO_ADMIN_LOGIN` | `true` | Initial value of the *admin password* switch |
| `API_REQUIRE_KEY` | `false` | Initial value of the *key required for the API* switch |
| `DATA_DIR` | `/work/data` | Settings, key hashes, chains, signing secret |
| `WORK_DIR` | `/work` (image) | Base folder for temporary files |
| `CONVERTER_URL` / `CONVERTER_API_KEY` | empty | Universal Converter for Office ↔ PDF |
| `CONVERTER_TIMEOUT` | `600` | Seconds to wait for a conversion |
| `NEXTCLOUD_URL` / `NEXTCLOUD_USER` | empty | Magic folder: Nextcloud address and user |
| `NEXTCLOUD_PASSWORD` / `NEXTCLOUD_PASSWORD_FILE` | empty | App password, directly or from a file |
| `NEXTCLOUD_MAGIC_DIR` / `NEXTCLOUD_POLL_SECONDS` | `Plico` / `60` | Magic folder name and check interval (minimum 15) |
| `PLICO_UID` / `PLICO_GID` | `1000` | User inside the container (build arguments) |
| `TZ` | `Europe/Rome` | Time zone (used by `{date}` in headers and footers) |

The two switches (`PLICO_ADMIN_LOGIN`, `API_REQUIRE_KEY`) are only *initial* values: once changed on `/admin` they are saved in `DATA_DIR/settings.json` and win over the environment.

## Working directory

```
/work
  upd/       one folder per request, deleted after the answer (and emptied at start-up)
  tmp/       uploads being received (Starlette spools large uploads here, not in the container filesystem)
  magic/     one folder per file processed by the magic folder, deleted at once
  data/      settings: apikeys.json, chains.json, settings.json, secret, admin-password (all mode 600)
  selftest/  sample results written by the selftest
```

# Using the web page

The home page shows every tool as a card, grouped as in the table above. A tool opens on the same page; files are added by dragging them or with the button, and the result downloads by itself.

- **Thumbnails.** Reorder, Split, Sign, Annotate and Redact show the pages. They come from `/api/thumbs` as small JPEGs.
- **Language.** The page follows the browser language and has an IT / EN switch, remembered in the browser. API errors are translated with the same choice (`Accept-Language`).
- **Optional tools.** The page asks `/api/features` which optional tools are on: without `CONVERTER_URL` the Office tools are hidden.
- **Light and dark theme** follow the system.
- **Messages from headers.** When a tool reports something (size saved by Compress, pages rendered at a lower DPI, redactions made) the page shows it after the download.

# The admin page

`/admin` manages API keys, saved chains and the two switches. It is enabled when there is an admin password (`PLICO_ADMIN_PASSWORD` or the `admin-password` file), or when the *admin password* switch is off.

- **Login.** The password gives a signed cookie valid for 12 hours, limited to `/admin`. Five wrong attempts from the same address in 10 minutes block the login for a while (`429`).
- **API keys.** Each key has a name and a list of permissions, one per tool (see the table in [api.md](api.md#api-keys)). The full key (`plico_` + 43 characters) is shown once; the server keeps only its SHA-256 hash, the first 10 characters to recognise it, and the time it was last used (saved at most once a minute). Keys can be renamed, have their permissions changed, or be revoked.
- **Key required for the API.** Off: the API answers anyone who can reach it, like the page. On: calls with neither a key nor the page's session cookie get `401`. The page keeps working, because opening it gives a signed session cookie (30 days). Anyone who can open the page can get that cookie, so this switch keeps scripts in order; it does not protect against people who can reach the service.
- **Admin password.** Off: `/admin` opens without a password, with a warning. Useful only on a network where every user is trusted.

Changes made on `/admin` must come from the page itself: they need the `X-Requested-With: plico` header, which another site's page cannot send.

# Saved chains

A chain is a list of up to 12 steps run one after the other on the same PDF, for example *compress → page numbers → protect*. Steps can be: `compress`, `stamp`, `protect`, `unlock`, `rotate`, `ocr`, `pdfa`, `repair`, `metadata`, `pages`, `nup`, `redact`, `organize`.

- On first start there are three chains: *Comprimi e numera*, *Archivio (OCR + PDF/A)*, *Pulisci prima di condividere*.
- They are created and changed on `/admin`, used from the page (*Batch and chains*), from the API (`/api/chain` with `chain=<name or id>`) and from the magic folder.
- With several files a chain runs on each and the answer is a ZIP.
- Passwords saved in a chain step are never sent back to the page: they appear as `•••`, and saving `•••` keeps the old value.
- An API key that runs a chain needs the `chain` permission **and** the permission of every step.

# Office documents (Universal Converter)

With `CONVERTER_URL` pointing to a [Universal Converter](https://github.com/EmaLau/universal-converter), the *Word, Excel, PowerPoint ↔ PDF* tools appear. Plico sends the file to the converter's job API, waits for it (`CONVERTER_TIMEOUT`), downloads the result and deletes the job on the converter.

- To PDF: `.doc .docx .odt .rtf .txt .xls .xlsx .ods .csv .ppt .pptx .odp`.
- From PDF: `docx`, `odt`, `xlsx`, `pptx`, `txt`.
- If the converter requires a key, set `CONVERTER_API_KEY` (sent as `apikey`).

# Nextcloud: right click → Strumenti PDF

The app in `nextcloud-app/` (id `strumentipdf`, Nextcloud 30–36) adds a *Strumenti PDF* submenu to PDF files in the Files app: merge the selected files, compress, OCR, page numbers, rotate, protect, unlock, remove hidden data, PDF/A, repair, and every saved chain. The result is saved next to the original with a free name (`file (2).pdf`).

## Installation

```bash
cp -r nextcloud-app /path/to/nextcloud/custom_apps/strumentipdf
occ app:enable strumentipdf
occ config:app:set strumentipdf pdf_url --value=http://plico-address:8080
occ config:app:set strumentipdf api_key --value=plico_...      # only if Key required for the API is on
occ config:system:set allow_local_remote_servers --value=true --type=boolean   # if the address is on the local network
```

## How it works

- The page script (`js/strumentipdf.js`, no build step) registers the menu with the Files app. It receives, as initial state, the optional tools available on the server (`/api/features`) and the saved chains, cached for 5 minutes: a new chain appears in the menu within 5 minutes.
- Clicking a tool calls the app's `POST /apps/strumentipdf/run` with the file ids. The PHP controller reads the files as the logged-in user, sends them to Plico (`lib/Service/PdfClient.php`), and writes the result in the same folder.
- The user needs write permission on the folder. Very large files take as long as the tool takes; the browser shows a notice while waiting.

## Common problems

| Symptom | Cause |
|---|---|
| The submenu does not appear | App not enabled, or `pdf_url` empty |
| Error about local or remote servers in the Nextcloud log | `allow_local_remote_servers` is false and the server is on the local network |
| `401` from the server | *Key required for the API* is on and `api_key` is missing or revoked |
| Nextcloud shows the update page | `<version>` changed in `appinfo/info.xml`: run `occ upgrade` |

# Nextcloud: magic folder

The server watches a folder in one Nextcloud account and processes the PDFs dropped there, with no click.

## How it works

1. Every `NEXTCLOUD_POLL_SECONDS` the server lists `Plico/` over WebDAV.
2. Every saved chain with *magic folder* switched on (on `/admin`) gets a subfolder with its name.
3. A PDF dropped in `Plico/<chain>/` is downloaded, processed with that chain, and:
   - the result goes to `<chain>/Fatti/`;
   - the original moves to `<chain>/Originali/`;
   - if the chain fails, the original moves to `<chain>/Errori/` with a `.txt` explaining why.
4. Existing names are never overwritten: a free name is chosen (`file (2).pdf`).

The magic folder uses the same queue as the page (`MAX_PARALLEL`), so it does not slow everything down. Network errors, a wrong password or Nextcloud being off are logged and retried at the next round; `/admin` shows how many files have been processed, the last round and the last error.

## Installation

1. In Nextcloud, create an **app password** for the account (*Personal settings → Security*, or `occ user:add-app-password <user>`). Do not use the account password.
2. Set `NEXTCLOUD_URL`, `NEXTCLOUD_USER` and either `NEXTCLOUD_PASSWORD` or `NEXTCLOUD_PASSWORD_FILE` (a file with the password, e.g. `/work/data/nextcloud-password`, mode 600). The file keeps the password out of the container configuration.
3. Restart, open `/admin`, and switch on *magic folder* for the chains you want.

To stop it, revoke the app password in Nextcloud and remove the variables.

# How it works

## Request flow

```
browser / script ──► guard (middleware) ──► endpoint ──► Job folder ──► queue (MAX_PARALLEL) ──► ops.<tool> ──► FileResponse ──► cleanup
                     cross-site check                    /work/upd/…      thread pool                              background task
                     API key + permission
                     security headers
```

1. **guard** (`server.py`) runs before the upload is read: it rejects cross-site requests (`403`), checks the API key and its permission (`401` / `403`), and adds the security headers to every answer, errors included.
2. The endpoint creates a **Job**: a folder in `/work/upd`. Uploads are written there in 1 MB chunks (`save`), checking `MAX_UPLOAD_MB` while reading.
3. The real work is in **`ops.py`**: every tool is a function `tool(src, out_dir, **options) -> Result`. The same functions are used by the API, by chains and by the magic folder.
4. Heavy work goes through **`heavy()`**: an `asyncio.Semaphore(MAX_PARALLEL)` in front of a thread pool. When a tool returns several files, the ZIP is built in the same turn, so it does not queue again.
5. The answer is a `FileResponse` with a **background task** that deletes the Job folder after the last byte has been sent, also when the download is interrupted. If anything fails before that, the endpoint deletes the folder itself. At start-up `/work/upd` is emptied, in case the container stopped in the middle of a job.

## Limits that protect the service

- **Pixels per page** (`MAX_PAGE_MPX`): a 1 KB PDF can declare a page of 5 × 5 metres; at 300 DPI that would be a 60,000 × 60,000 image and the container would run out of memory. Larger pages are rendered at a lower DPI; `X-Dpi-Reduced` says how many.
- **Output size** (`MAX_OUTPUT_MB`): counted file by file as results are produced (`ops.Output`), so a request stops as soon as it goes over.
- **Parallel jobs** (`MAX_PARALLEL`) and container limits (`PLICO_CPUS`, `PLICO_MEMORY`).
- **External programs** (Ghostscript with `-dSAFER`, OCRmyPDF) run with a timeout, without a shell.
- **Errors**: unexpected exceptions answer a generic `500` and the details go to the log only.

## Libraries

| Library | Used for |
|---|---|
| PyMuPDF | pages, thumbnails, rendering, stamps, signatures, annotations, forms, redaction, compare, n-up |
| pikepdf (qpdf) | encryption, repair |
| Ghostscript | compression, repair (last resort) |
| OCRmyPDF + Tesseract | OCR, PDF/A-2 (with or without text recognition) |
| OpenCV | scanner (edge detection, perspective) |
| FastAPI + Uvicorn | HTTP server and OpenAPI documentation |

## Translations

The page texts are in `server/static/i18n.js` (Italian and English). API errors are written in Italian in the code and translated by `server/i18n.py`, which matches fixed messages and patterns (e.g. `File troppo grande (massimo {n} MB)`). A message missing from the table is sent as it is, in Italian.

## The documentation page

This guide is also served by the app at `/docs` (Italian or English, from `?lang=` or the browser language), opened with the *Documentation* button at the top of the page. While the image is built, a first stage with pandoc turns `docs/documentazione.md` and `docs/documentation.md` into `docs-it.html` and `docs-en.html` with `docs/web/build.sh`, `template.html` and `style.html`; pandoc does not end up in the final image. Without those files (e.g. running the server from the sources) `/docs` answers `404`. To build them locally: `sh docs/web/build.sh server/static`.

# Security and privacy

- **No login on the page.** Anyone who can reach the service can use it. By default it listens only on `127.0.0.1`. Open it only on a trusted network (home, VPN), or behind a reverse proxy with authentication. Do not expose it directly to the Internet.
- **No files kept.** Every request folder is deleted after the answer; the magic folder deletes each file's folder at once. The selftest checks that nothing is left over.
- **Security headers** on every answer: `Content-Security-Policy` that allows only the page's own scripts (by SHA-256 hash, computed at start-up), `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`. The Swagger page `/apidocs` has its own policy that allows its files from jsDelivr.
- **Cross-site requests.** A `POST` sent by a page of another site (`Sec-Fetch-Site: cross-site`, or an `Origin` different from the host) gets `403`, so a malicious page cannot use the service through the visitor's browser.
- **API keys** are stored as SHA-256 hashes and compared in constant time. Cookies are HMAC-SHA256 signed with a random secret in `DATA_DIR/secret`, `HttpOnly` and `SameSite=Strict`.
- **Passwords of protected PDFs**: without an owner password a random one is generated, so the chosen permissions (print, copy, edit) are really enforced.
- **Redaction** removes the text under the boxes and blanks the image pixels there, instead of just covering them; *clean metadata* also removes metadata and hidden data.
- **Unprivileged container** (user 1000 by default, behind `tini`), no Docker socket, a single volume.
- **Uploads** are not limited by default (`MAX_UPLOAD_MB=0`), by choice: the limits that protect the server are on pixels, output size and parallel jobs. Set `MAX_UPLOAD_MB` if the service is shared with people you do not trust.

# Maintenance

## Selftest

```bash
docker compose exec plico python3 /app/selftest.py
```

It calls every tool of the running server with generated files and checks the results; at the end it checks that no request folder is left over (it waits up to 5 seconds, because folders are deleted just after the answer). Some checks run only with the related setting:

| Check | Runs when |
|---|---|
| file over the limit → `413` | `MAX_UPLOAD_MB` between 1 and 200 |
| output over the limit → `413` | `MAX_OUTPUT_MB` up to 10 |
| API keys, switches, revocation | `PLICO_ADMIN_PASSWORD` is set in the environment |
| Office | `CONVERTER_URL` is set |

The CI runs it with small limits and an admin password, so every check runs there.

## Updating

```bash
git pull
docker compose up -d --build
docker compose exec plico python3 /app/selftest.py
```

`DATA_DIR` is in the volume, so keys, chains and switches stay.

## Logs

```bash
docker compose logs -f plico
```

Access logs are off (`--no-access-log`): file names are not written anywhere. The log has start-up messages, unexpected errors with their traceback, and the magic folder activity.

## Backup

Only `DATA_DIR` is worth saving (`/work/data`): API key hashes, chains, switches and the cookie secret. Losing it means creating the keys again.

# Development

## Code structure

```
server/
  server.py        FastAPI app: guard middleware, Job folders, queue, endpoints, admin API
  ops.py           every PDF operation (one function per tool), limits, chains
  apikeys.py       KeyStore: keys, settings, signed cookies, admin login
  chains.py        ChainStore: saved chains
  magic.py         WebDAV client and magic folder loop
  converter.py     client for Universal Converter
  i18n.py          English translations of API errors
  selftest.py      checks against the running server
  static/          index.html, admin.html, i18n.js (and the generated docs-it.html, docs-en.html)
docs/              this guide, the API reference, docs/web/ (template and script of the /docs page)
nextcloud-app/     Nextcloud app (PHP controller and client, page script)
tests/             pytest: test_api.py, test_features.py, test_ui.py
```

## Adding a tool

1. Write the operation in `ops.py`: `def mytool(src: Path, out_dir: Path, option: str = "x") -> Result`. Use `open_pdf()`, `finish_pdf()`, `fail()` for errors the user should read, and `Output()` / `one_or_zip()` when it produces several files, so `MAX_OUTPUT_MB` is respected.
2. Add the permission to `apikeys.PERMISSIONS`.
3. Add the endpoint in `server.py` with `@tool(...)` and `one_file()` or `many_files()`; they take care of the Job folder, the queue and the cleanup.
4. If it can be a chain step, add it to `ops.CHAIN_OPS`.
5. Add the card and its form in `static/index.html`, the texts in `static/i18n.js`, new error messages in `i18n.py`.
6. Add a test in `tests/`, a check in `selftest.py`, and the endpoint in `docs/api.md`.

## Tests

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium     # or PW_CHANNEL=chrome to use the installed Chrome
python -m pytest
```

- `test_api.py` uses FastAPI's `TestClient`: no container, no network.
- `test_features.py` covers the newer tools, chains, the converter and the magic folder with fake servers.
- `test_ui.py` starts the server and drives every tool from the page in headless Chromium, failing on any JavaScript error.

GitHub Actions (`.github/workflows/ci.yml`) runs pytest, builds the image and runs the selftest inside it.

# Reusing the building blocks

Several parts are not specific to PDFs and were written to be copied into other FastAPI services, starting with [Universal Converter](https://github.com/EmaLau/universal-converter). Each block below says which files to take and what to change.

## API keys and admin page (like Gokapi)

- **Files**: `server/apikeys.py`, `server/static/admin.html`, the admin routes in `server.py` (`/admin`, `/admin/api/*`), the `guard` middleware.
- **Change**: `PERMISSIONS` (one per feature of the other service), the cookie names (`plico_session`, `plico_admin`), the key prefix (`plico_`), the `X-Requested-With` value, `PATH_PERM` (path → permission).
- **Keep**: keys checked in the middleware *before* the body is read; SHA-256 hashes compared with `hmac.compare_digest`; the key shown once; `last_used` saved at most once a minute and flushed at shutdown; the two switches saved in `settings.json`, with the environment as initial value; login rate limit.
- **Watch**: clients of the other service (for the converter, its Nextcloud app *Converti in*) must be able to send a key when *key required* is on.

## Security headers and cross-site check

- **Files**: `security_headers()`, `_inline_hashes()` and `cross_site()` in `server.py`.
- **Change**: the pages whose inline scripts are hashed, and the separate policy for `/apidocs`.
- **Keep**: headers added also to error answers (the middleware wraps everything); `Origin` compared with `Host` and `X-Forwarded-Host`, so it works behind a reverse proxy.

## Temporary files and limits

- **Files**: the `Job` class, `save()`, `heavy()` in `server.py`; `Output` in `ops.py`.
- **Keep**: uploads spooled into the data volume (`tempfile.tempdir`), cleanup in a `BackgroundTask` plus `except BaseException` before the answer, emptying the folder at start-up, a semaphore in front of the thread pool, output counted while it is written.
- **Watch**: a selftest that looks for leftovers must wait a moment, because the background task runs just *after* the client has the answer.

## Translations of API errors

- **Files**: `server/i18n.py` and the `error()` handler in `server.py`.
- **Keep**: messages written once in one language in the code, translated at the edge from `Accept-Language`, with `Content-Language` in the answer.

## Tests and CI

- **Files**: `tests/conftest.py` (sample files, live server for Playwright), `.github/workflows/ci.yml`, `pytest.ini`, `requirements-dev.txt`.
- **Keep**: two CI jobs: pytest without Docker, and Docker build + selftest with small limits so that every check runs; the browser test that fails on any JavaScript error.

## Interactive API documentation

- FastAPI with `docs_url="/apidocs"`, `openapi_url="/apidocs/openapi.json"`, a description with examples, and `Security(header_scheme)` on the endpoints, so Swagger shows the *Authorize* button for `apikey`.

## Optional integrations

- **Pattern**: an integration is on only when its variables are set (`CONVERTER_URL`, `NEXTCLOUD_*`), and `/api/features` tells the page what to show. The repository works without any of them.
- **Secrets from files**: `NEXTCLOUD_PASSWORD_FILE` and `DATA_DIR/admin-password` keep passwords out of the container configuration.

# Known limits

- The page has no user accounts: it is meant for a home or a small team on a trusted network.
- Very large scans with OCR can take minutes and use a lot of memory; `MAX_PARALLEL` and the container limits decide how many run together.
- Compare works on text and on the rendered pages: it does not understand moved paragraphs.
- The scanner finds the page when it stands out from the background; on a background of the same colour it keeps the whole photo.
- Office conversions depend on the Universal Converter and on LibreOffice's fidelity.

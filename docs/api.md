# Universal-PDF API

Every tool of the web page is also an HTTP endpoint, so scripts, other services and iPhone Shortcuts can use it. The interactive reference, generated from the code, is at **`/apidocs`** on your server (OpenAPI schema at `/apidocs/openapi.json`).

- [Basics](#basics)
- [API keys](#api-keys)
- [Endpoints](#endpoints)
- [Chains and batches](#chains-and-batches)
- [Examples](#examples): curl, Python, iPhone Shortcuts
- [Errors](#errors)

## Basics

- All tools are `POST` requests with `multipart/form-data`. One input file goes in the field `file`, several in `files`.
- The answer is the resulting file, with a `Content-Disposition` header that suggests a name. Tools that can produce several files (split, PDF to images, extract images, chains on many files) answer with a ZIP, or with the single file when there is only one.
- Some tools add information in headers: `X-Size-Before` / `X-Size-After` (compress), `X-Dpi-Reduced` (PDF to images), `X-Redactions` (redact), `X-Pages-Changed` (compare), `X-Fields-Filled` (fill), `X-Repair-Method` (repair), `X-Pages-Straightened` (scan).
- Nothing is kept: every request works in a temporary folder that is deleted as soon as the answer has been sent.
- Error messages are in English, or in Italian when the request sends `Accept-Language: it`.
- `GET /api/features` tells which optional tools are on (`office`, `ocr`, `magic_folder`); `GET /healthz` returns `{"ok": true}`.

## API keys

Keys work like in Gokapi. An administrator creates them on the `/admin` page (protected by `UPDF_ADMIN_PASSWORD`), gives each a name and the permissions it needs, and can revoke them at any time. The full key (`updf_…`) is shown only once.

Send it in the `apikey` header:

```bash
curl -H "apikey: updf_..." -F file=@scan.pdf -o scan-ocr.pdf http://pdf.example:8080/api/ocr
```

| Answer | Meaning |
|---|---|
| `401` | wrong or revoked key, or no key while *Key required for the API* is on |
| `403` | the key does not have the permission for this tool (or, for `/api/chain`, for one of its steps) |

Both are checked before the upload is received. Without a key the API answers like the web page, unless the administrator switched on *Key required for the API*.

| Permission | Endpoints |
|---|---|
| `info` | `/api/info`, `/api/thumbs` |
| `merge`, `split`, `organize`, `rotate`, `compress`, `img2pdf`, `pdf2img`, `stamp` | the endpoint with the same name |
| `protect` | `/api/protect`, `/api/unlock` |
| `ocr`, `pdfa`, `repair`, `metadata`, `extract`, `pages`, `nup`, `sign`, `annotate`, `redact`, `compare`, `scan`, `office` | the endpoint with the same name |
| `forms` | `/api/forms`, `/api/fill` |
| `chain` | `/api/chain` (plus the permissions of every step) |

## Endpoints

Coordinates on a page (signature, annotations, redaction areas) are fractions of the page **as it is displayed**: `0` to `1`, origin at the top left, rotation already taken into account. A box is `[x0, y0, x1, y1]`, a point `[x, y]`. Pages are counted from `0` in JSON and from `1` in ranges such as `1-3, 5, 8-`.

| Endpoint | Fields (defaults in brackets) | Result |
|---|---|---|
| `/api/info` | `file` | JSON: `pages`, `encrypted`, `size`, `metadata`, `form_fields` |
| `/api/thumbs` | `file`, `width` (160), `pages` (all) | JSON with JPEG data URLs |
| `/api/merge` | `files` (2 or more, PDFs or images) | PDF |
| `/api/split` | `file`, `mode` (`ranges` or `every`), `ranges`, `every`, `merge_out` | PDF or ZIP |
| `/api/organize` | `file`, `pages` = JSON `[[index, rotation], …]` in the final order | PDF |
| `/api/rotate` | `file`, `angle` (90), `pages` (all) | PDF |
| `/api/compress` | `file`, `level` (`low`, `medium`, `high`), `gray` | PDF, never bigger than the original |
| `/api/img2pdf` | `files`, `page` (`fit`, `a4`, `letter`), `margin` | PDF |
| `/api/pdf2img` | `file`, `format` (`png`, `jpg`), `dpi` (150), `ranges` | image or ZIP |
| `/api/protect` | `file`, `password`, `owner` (random), `allow_print`, `allow_copy`, `allow_edit` | PDF, AES-256 |
| `/api/unlock` | `file`, `password` | PDF |
| `/api/stamp` | `file`, `numbers`, `num_pos`, `num_fmt` (`{n}`, `{tot}`), `num_start`, `num_size`, `num_skip_first`, `watermark`, `wm_size`, `wm_opacity`, `wm_angle`, `wm_color`, `header`, `footer` (`{n}`, `{tot}`, `{date}`, `{file}`), `hf_size`, `wm_image` (PNG/JPG), `wm_image_scale` | PDF |
| `/api/ocr` | `file`, `lang` (`ita+eng`), `force`, `deskew` | PDF with selectable text |
| `/api/pdfa` | `file`, `ocr_text`, `lang` | PDF/A-2 |
| `/api/repair` | `file` | PDF (`422` if it cannot be recovered) |
| `/api/metadata` | `file`, `clean`, `title`, `author`, `subject`, `keywords`, `creator`, `producer` | PDF |
| `/api/extract` | `file`, `kind` (`images` or `text`), `pages` | ZIP or TXT |
| `/api/pages` | `file`, `mode` (`resize`, `crop`, `trim`), `paper` (`a4`, `a3`, `a5`, `letter`, `legal`), `orientation`, `margin_mm`, `top`, `right`, `bottom`, `left` (mm) | PDF |
| `/api/nup` | `file`, `mode` (`nup` or `booklet`), `n` (2, 4, 6, 8, 9, 16), `paper`, `gap_mm` | PDF |
| `/api/sign` | `file`, `image` (PNG, transparent is best), `page` (-1 = last), `box` | PDF |
| `/api/annotate` | `file`, `items` (JSON, see below), `flatten` | PDF |
| `/api/forms` | `file` | JSON: `fields` with `name`, `type`, `value`, `options` |
| `/api/fill` | `file`, `values` = JSON `{"field": "value"}` (`true`/`false` for check boxes), `flatten` | PDF |
| `/api/redact` | `file`, `terms` (one per line), `presets` (`email`, `phone`, `iban`, `cf`, `card`), `areas` = JSON `[{"page", "box"}]`, `regex`, `clean_metadata` (true) | PDF; the text is removed, not covered |
| `/api/compare` | `file_a`, `file_b` | PDF report |
| `/api/scan` | `files` (photos, also HEIC), `mode` (`color`, `gray`, `bw`), `paper` (`a4`, `letter`, `fit`) | PDF |
| `/api/office` | `file`, `target` (`pdf` for Office files; `docx`, `odt`, `xlsx`, `pptx`, `txt` for a PDF) | converted file; `501` without `CONVERTER_URL` |
| `/api/chain` | `files`, `steps` (JSON) or `chain` (name or id of a saved chain) | PDF, or ZIP for several files |
| `GET /api/chains` | | saved chains (passwords hidden) |

Annotation items:

```json
[
  {"page": 0, "type": "highlight", "box": [0.10, 0.20, 0.60, 0.24]},
  {"page": 0, "type": "text", "box": [0.10, 0.30, 0.50, 0.36], "text": "Check this", "color": "#1d4ed8", "size": 12},
  {"page": 0, "type": "note", "at": [0.80, 0.10], "text": "Comment"},
  {"page": 1, "type": "arrow", "from": [0.2, 0.5], "to": [0.6, 0.5], "color": "#e5322d"},
  {"page": 1, "type": "rect", "box": [0.1, 0.1, 0.4, 0.4]},
  {"page": 2, "type": "ink", "points": [[0.1, 0.1], [0.2, 0.2], [0.3, 0.1]]}
]
```

## Chains and batches

`/api/chain` runs several operations in a row on each uploaded file. `steps` is a JSON list; each step has an `op` and the same options as the endpoint of that tool:

```json
[{"op": "ocr", "lang": "ita+eng"}, {"op": "compress", "level": "high"}, {"op": "stamp", "numbers": true, "num_fmt": "{n} / {tot}"}, {"op": "protect", "password": "secret"}]
```

Operations: `compress`, `stamp`, `protect`, `unlock`, `rotate`, `ocr`, `pdfa`, `repair`, `metadata`, `pages`, `nup`, `redact`, `organize` (at most 12 steps). With one file the answer is the PDF; with several, a ZIP with one PDF per file (same names, numbered if repeated).

Chains can also be saved on `/admin` and called by name: `-F chain="Archivio (OCR + PDF/A)"`. Saved chains can feed the Nextcloud magic folder (see the README).

## Examples

### curl

```bash
URL=http://pdf.example:8080
KEY="apikey: updf_..."      # leave out -H "$KEY" if the server does not require keys

# merge, in this order
curl -H "$KEY" -F files=@cover.pdf -F files=@report.pdf -F files=@photo.jpg -o all.pdf $URL/api/merge

# OCR of a scan
curl -H "$KEY" -F file=@scan.pdf -F lang=ita+eng -o scan-ocr.pdf $URL/api/ocr

# sign the last page, bottom right
curl -H "$KEY" -F file=@contract.pdf -F image=@signature.png -F page=-1 -F 'box=[0.6,0.82,0.92,0.92]' -o signed.pdf $URL/api/sign

# redact emails and a name
curl -H "$KEY" -F file=@doc.pdf -F presets=email -F 'terms=John Smith' -o redacted.pdf $URL/api/redact

# a whole folder through a chain, results in a ZIP
curl -H "$KEY" $(for f in invoices/*.pdf; do printf -- '-F files=@%s ' "$f"; done) \
     -F 'steps=[{"op":"compress","level":"medium"},{"op":"stamp","numbers":true}]' -o results.zip $URL/api/chain
```

### Python

```python
import requests

URL = "http://pdf.example:8080"
HEADERS = {"apikey": "updf_..."}

with open("scan.pdf", "rb") as f:
    r = requests.post(f"{URL}/api/ocr", headers=HEADERS, files={"file": f}, data={"lang": "ita+eng"})
r.raise_for_status()
open("scan-ocr.pdf", "wb").write(r.content)
```

### iPhone and iPad Shortcuts

A shortcut that appears in the share sheet of Files, Mail and Safari and returns a compressed, page-numbered PDF:

1. Create a key on `/admin` with the permissions you need (for this example `chain`, `compress` and `stamp`).
2. In Shortcuts, create a new shortcut and open its details: turn on **Show in Share Sheet** and accept **PDFs** (and **Files**).
3. Add **Get Contents of URL**:
   - URL: `http://pdf.example:8080/api/chain` (the server must be reachable from the phone, for example through a VPN such as Tailscale);
   - Method: **POST**;
   - Headers: `apikey` = your key;
   - Request Body: **Form**, with the fields
     - `files` → type **File** → *Shortcut Input*;
     - `steps` → type **Text** → `[{"op":"compress","level":"medium"},{"op":"stamp","numbers":true,"num_fmt":"{n} / {tot}"}]`.
4. Add **Save File** (or **Quick Look**, or **Share**) with the result of the previous action.

Other ideas: use `/api/scan` with **Take Photo** (repeat it to add pages, field `files`) to scan a document; `/api/ocr` to make a received PDF searchable; `/api/merge` with several files from the share sheet. For a saved chain, replace `steps` with a `chain` field holding its name.

## Errors

Errors are JSON `{"detail": "…"}` with an HTTP status:

| Status | When |
|---|---|
| `400` | invalid input (not a PDF, wrong range, missing option, password-protected PDF that must be unlocked first) |
| `401` / `403` | API key (see above), or the admin area |
| `403` | request sent by a page of another site (`Origin` / `Sec-Fetch-Site`) |
| `413` | file larger than `MAX_UPLOAD_MB` (if set), or result larger than `MAX_OUTPUT_MB` |
| `422` | the file cannot be processed (nothing to extract, cannot be repaired) |
| `500` | unexpected error; details are only in the server log |
| `501` / `502` / `504` | optional tool not configured, the converter failed or did not answer in time |

# Plico — Documentazione

🇬🇧 [English](documentation.md) · 🇮🇹 **Italiano**

Questa è la guida completa: installazione, configurazione, ogni parte del servizio, come funziona dentro, sicurezza, manutenzione e sviluppo. Il riferimento dell'API con gli esempi è in [api.md](api.md) (in inglese); la versione breve di tutto è nel [README](../README.it.md).

- [Panoramica](#panoramica)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Uso della pagina web](#uso-della-pagina-web)
- [La pagina admin](#la-pagina-admin)
- [Catene salvate](#catene-salvate)
- [Documenti Office (Convertitore universale)](#documenti-office-convertitore-universale)
- [Nextcloud: tasto destro → Strumenti PDF](#nextcloud-tasto-destro--strumenti-pdf)
- [Nextcloud: cartella magica](#nextcloud-cartella-magica)
- [Come funziona](#come-funziona)
- [Sicurezza e privacy](#sicurezza-e-privacy)
- [Manutenzione](#manutenzione)
- [Sviluppo](#sviluppo)
- [Riusare i componenti](#riusare-i-componenti)
- [Limiti noti](#limiti-noti)

# Panoramica

Plico è un insieme di strumenti PDF in una sola pagina web, sul tuo server. È un servizio FastAPI senza database: ogni richiesta riceve i file, li elabora in una cartella temporanea, restituisce il risultato e cancella la cartella. Sul disco restano solo le impostazioni in `DATA_DIR` (hash delle chiavi API, catene salvate, interruttori).

| Gruppo | Strumenti |
|---|---|
| Organizza | Unisci, Dividi, Estrai pagine, Riordina / ruota / elimina con le anteprime, Ruota |
| Ottimizza e converti | Comprimi, Immagini → PDF, PDF → JPG/PNG, OCR, PDF/A-2, Scanner, Word/Excel/PowerPoint ↔ PDF (facoltativo) |
| Sicurezza | Proteggi (AES-256), Sblocca |
| Modifica e firma | Numeri di pagina, intestazione e piè di pagina, filigrana di testo e immagine, Firma, Compila moduli, Annota, Oscura, Metadati |
| Avanzati | Confronta, Ritaglia e ridimensiona, Più pagine per foglio e opuscolo, Estrai immagini e testo, Ripara, Più file e catene |
| Integrazioni | Chiavi API, app Nextcloud, cartella magica in Nextcloud (tutte facoltative) |

## In numeri

- 28 endpoint di strumenti, 25 permessi per le chiavi, 3 catene pronte al primo avvio.
- Circa 5.000 righe di Python, JavaScript e PHP, nessuna compilazione, nessuna risorsa esterna nella pagina.
- 110 test pytest (API, strumenti, pagina in Chromium headless) e un selftest di circa 50 controlli sul container in funzione.
- Immagine Docker di circa 870 MB (soprattutto Tesseract e OpenCV, per l'OCR e lo scanner).

# Installazione

## Con Docker Compose (consigliato)

```bash
git clone https://github.com/EmaLau/plico.git
cd plico
cp .env.example .env        # facoltativo: cambia quello che ti serve
docker compose up -d --build
```

Apri <http://localhost:8080>, poi controlla tutti gli strumenti:

```bash
docker compose exec plico python3 /app/selftest.py
```

Il servizio ascolta solo su `127.0.0.1`. Per raggiungerlo da altri dispositivi imposta `PLICO_BIND=0.0.0.0` in `.env`, ma prima leggi [Sicurezza e privacy](#sicurezza-e-privacy).

## Con Docker, senza Compose

```bash
docker build -t plico server
docker run -d --name plico -p 127.0.0.1:8080:8080 -v plico-work:/work \
  -e PLICO_ADMIN_PASSWORD=cambiami plico
```

`--build-arg UID=… --build-arg GID=…` scelgono l'utente che esegue il servizio (predefinito 1000). Deve essere il proprietario del volume `/work`.

## Senza Docker (sviluppo)

Servono Python 3.11 o più recente, Ghostscript e, per l'OCR, `ocrmypdf` con Tesseract (`ita` e `eng`).

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r server/requirements.txt
cd server && WORK_DIR=/tmp/plico uvicorn server:app --port 8080
```

# Configurazione

Le impostazioni sono variabili d'ambiente. Con Compose si leggono da `.env`; `.env.example` le elenca con i commenti.

| Variabile | Predefinito | Descrizione |
|---|---|---|
| `PLICO_BIND` / `PLICO_PORT` | `127.0.0.1` / `8080` | Dove Compose pubblica il servizio |
| `MAX_UPLOAD_MB` | `0` | Dimensione massima di ogni file caricato; `0` = nessun limite |
| `MAX_OUTPUT_MB` | `4096` | Dimensione massima dei risultati di una richiesta |
| `MAX_PARALLEL` | `2` | Lavori pesanti eseguiti insieme; gli altri aspettano |
| `MAX_PAGE_MPX` | `50` | Megapixel massimi di una pagina in *PDF in immagini*; le pagine più grandi hanno dpi più bassi |
| `PLICO_CPUS` / `PLICO_MEMORY` | `4` / `3G` | Limiti del container (Compose) |
| `PLICO_ADMIN_PASSWORD` | vuota | Password di `/admin`. Si può anche scrivere in `DATA_DIR/admin-password` |
| `PLICO_ADMIN_LOGIN` | `true` | Valore iniziale dell'interruttore *password per l'area admin* |
| `API_REQUIRE_KEY` | `false` | Valore iniziale dell'interruttore *chiave obbligatoria per le API* |
| `DATA_DIR` | `/work/data` | Impostazioni, hash delle chiavi, catene, segreto per i cookie |
| `WORK_DIR` | `/work` (immagine) | Cartella dei file temporanei |
| `CONVERTER_URL` / `CONVERTER_API_KEY` | vuote | Convertitore universale per Office ↔ PDF |
| `CONVERTER_TIMEOUT` | `600` | Secondi di attesa per una conversione |
| `NEXTCLOUD_URL` / `NEXTCLOUD_USER` | vuote | Cartella magica: indirizzo di Nextcloud e utente |
| `NEXTCLOUD_PASSWORD` / `NEXTCLOUD_PASSWORD_FILE` | vuote | Password per le app, scritta qui o letta da un file |
| `NEXTCLOUD_MAGIC_DIR` / `NEXTCLOUD_POLL_SECONDS` | `Plico` / `60` | Nome della cartella magica e ogni quanto si controlla (minimo 15) |
| `PLICO_UID` / `PLICO_GID` | `1000` | Utente dentro il container (argomenti di build) |
| `TZ` | `Europe/Rome` | Fuso orario (usato da `{date}` in intestazioni e piè di pagina) |

I due interruttori (`PLICO_ADMIN_LOGIN`, `API_REQUIRE_KEY`) danno solo il valore *iniziale*: una volta cambiati in `/admin` vengono salvati in `DATA_DIR/settings.json` e prevalgono sulle variabili.

## Cartella di lavoro

```
/work
  upd/       una cartella per richiesta, cancellata dopo la risposta (e svuotata all'avvio)
  tmp/       file in arrivo (Starlette parcheggia qui i caricamenti grandi, non nel sistema del container)
  magic/     una cartella per ogni file della cartella magica, cancellata subito
  data/      impostazioni: apikeys.json, chains.json, settings.json, secret, admin-password (tutti con permessi 600)
  selftest/  esempi di risultati scritti dal selftest
```

# Uso della pagina web

La pagina iniziale mostra ogni strumento come una scheda, divisi nei gruppi della tabella sopra. Lo strumento si apre nella stessa pagina; i file si aggiungono trascinandoli o con il pulsante, e il risultato si scarica da solo.

- **Anteprime.** Riordina, Dividi, Firma, Annota e Oscura mostrano le pagine, come piccoli JPEG da `/api/thumbs`.
- **Lingua.** La pagina segue la lingua del browser e ha un selettore IT / EN, ricordato nel browser. Anche gli errori dell'API seguono questa scelta (`Accept-Language`).
- **Strumenti facoltativi.** La pagina chiede a `/api/features` quali sono attivi: senza `CONVERTER_URL` gli strumenti Office sono nascosti.
- **Tema chiaro e scuro**, secondo il sistema.
- **Messaggi dalle intestazioni.** Quando uno strumento comunica qualcosa (spazio risparmiato da Comprimi, pagine rese a dpi più bassi, oscuramenti fatti) la pagina lo mostra dopo il download.

# La pagina admin

`/admin` gestisce chiavi API, catene salvate e i due interruttori. È attiva se c'è una password admin (`PLICO_ADMIN_PASSWORD` o il file `admin-password`), oppure se l'interruttore *password per l'area admin* è spento.

- **Accesso.** La password dà un cookie firmato valido 12 ore, limitato a `/admin`. Cinque tentativi sbagliati dallo stesso indirizzo in 10 minuti bloccano l'accesso per un po' (`429`).
- **Chiavi API.** Ogni chiave ha un nome e un elenco di permessi, uno per strumento (vedi la tabella in [api.md](api.md#api-keys)). La chiave intera (`plico_` + 43 caratteri) si vede una sola volta; il server tiene solo l'hash SHA-256, i primi 10 caratteri per riconoscerla e l'ora dell'ultimo uso (salvata al massimo una volta al minuto). Le chiavi si possono rinominare, cambiare di permessi o revocare.
- **Chiave obbligatoria per le API.** Spento: l'API risponde a chiunque la raggiunga, come la pagina. Acceso: le chiamate senza chiave e senza il cookie di sessione della pagina ricevono `401`. La pagina continua a funzionare, perché aprendola si riceve un cookie di sessione firmato (30 giorni). Chiunque apra la pagina può ottenere quel cookie: l'interruttore mette ordine negli script, non protegge da chi raggiunge il servizio.
- **Password per l'area admin.** Spento: `/admin` si apre senza password, con un avviso. Ha senso solo in una rete dove tutti sono fidati.

Le modifiche fatte in `/admin` devono arrivare dalla pagina stessa: serve l'intestazione `X-Requested-With: plico`, che la pagina di un altro sito non può mandare.

# Catene salvate

Una catena è un elenco di massimo 12 passi eseguiti uno dopo l'altro sullo stesso PDF, per esempio *comprimi → numeri di pagina → proteggi*. I passi possibili sono: `compress`, `stamp`, `protect`, `unlock`, `rotate`, `ocr`, `pdfa`, `repair`, `metadata`, `pages`, `nup`, `redact`, `organize`.

- Al primo avvio ci sono tre catene: *Comprimi e numera*, *Archivio (OCR + PDF/A)*, *Pulisci prima di condividere*.
- Si creano e si modificano in `/admin`, si usano dalla pagina (*Più file e catene*), dall'API (`/api/chain` con `chain=<nome o id>`) e dalla cartella magica.
- Con più file la catena viene eseguita su ognuno e la risposta è uno ZIP.
- Le password salvate in un passo non tornano mai alla pagina: compaiono come `•••`, e salvando `•••` resta il valore di prima.
- Una chiave API che esegue una catena ha bisogno del permesso `chain` **e** del permesso di ogni passo.

# Documenti Office (Convertitore universale)

Con `CONVERTER_URL` che punta a un [Convertitore universale](https://github.com/EmaLau/universal-converter) compaiono gli strumenti *Word, Excel, PowerPoint ↔ PDF*. Plico manda il file all'API dei lavori del convertitore, aspetta (`CONVERTER_TIMEOUT`), scarica il risultato e cancella il lavoro sul convertitore.

- In PDF: `.doc .docx .odt .rtf .txt .xls .xlsx .ods .csv .ppt .pptx .odp`.
- Da PDF: `docx`, `odt`, `xlsx`, `pptx`, `txt`.
- Se il convertitore chiede una chiave, imposta `CONVERTER_API_KEY` (mandata come `apikey`).

# Nextcloud: tasto destro → Strumenti PDF

L'app in `nextcloud-app/` (id `strumentipdf`, Nextcloud 30–36) aggiunge ai PDF, nell'app File, il sottomenu *Strumenti PDF*: unisci i file selezionati, comprimi, OCR, numeri di pagina, ruota, proteggi, sblocca, rimuovi i dati nascosti, PDF/A, ripara, e ogni catena salvata. Il risultato viene salvato accanto all'originale con un nome libero (`file (2).pdf`).

## Installazione

```bash
cp -r nextcloud-app /percorso/di/nextcloud/custom_apps/strumentipdf
occ app:enable strumentipdf
occ config:app:set strumentipdf pdf_url --value=http://indirizzo-di-plico:8080
occ config:app:set strumentipdf api_key --value=plico_...      # solo se la chiave è obbligatoria
occ config:system:set allow_local_remote_servers --value=true --type=boolean   # se l'indirizzo è nella rete locale
```

## Come funziona

- Lo script della pagina (`js/strumentipdf.js`, senza compilazione) registra il menu nell'app File. Riceve come stato iniziale gli strumenti facoltativi attivi sul server (`/api/features`) e le catene salvate, tenuti in cache 5 minuti: una catena nuova compare nel menu entro 5 minuti.
- Scegliendo uno strumento, la pagina chiama `POST /apps/strumentipdf/run` con gli id dei file. Il controller PHP legge i file come l'utente collegato, li manda a Plico (`lib/Service/PdfClient.php`) e scrive il risultato nella stessa cartella.
- L'utente deve poter scrivere nella cartella. Con file molto grandi si aspetta quanto ci mette lo strumento; intanto il browser mostra un avviso.

## Problemi comuni

| Sintomo | Causa |
|---|---|
| Il sottomenu non compare | App non attiva, oppure `pdf_url` vuoto |
| Errore sui server locali o remoti nel log di Nextcloud | `allow_local_remote_servers` è falso e il server è nella rete locale |
| `401` dal server | La chiave è obbligatoria e `api_key` manca o è stata revocata |
| Nextcloud mostra la pagina di aggiornamento | È cambiata `<version>` in `appinfo/info.xml`: lancia `occ upgrade` |

# Nextcloud: cartella magica

Il server controlla una cartella di un account Nextcloud ed elabora i PDF che ci finiscono, senza clic.

## Come funziona

1. Ogni `NEXTCLOUD_POLL_SECONDS` il server legge `Plico/` via WebDAV.
2. Ogni catena salvata con *cartella magica* attiva (in `/admin`) ha una sottocartella con il suo nome.
3. Un PDF messo in `Plico/<catena>/` viene scaricato ed elaborato con quella catena, poi:
   - il risultato va in `<catena>/Fatti/`;
   - l'originale va in `<catena>/Originali/`;
   - se la catena fallisce, l'originale va in `<catena>/Errori/` con un `.txt` che spiega il motivo.
4. I nomi esistenti non vengono mai sovrascritti: si sceglie un nome libero (`file (2).pdf`).

La cartella magica usa la stessa coda della pagina (`MAX_PARALLEL`), quindi non rallenta tutto. Errori di rete, password sbagliata o Nextcloud spento vengono scritti nel log e si riprova al giro dopo; `/admin` mostra quanti file sono stati elaborati, l'ultimo giro e l'ultimo errore.

## Installazione

1. In Nextcloud crea una **password per le app** per l'account (*Impostazioni personali → Sicurezza*, oppure `occ user:add-app-password <utente>`). Non usare la password dell'account.
2. Imposta `NEXTCLOUD_URL`, `NEXTCLOUD_USER` e `NEXTCLOUD_PASSWORD`, oppure `NEXTCLOUD_PASSWORD_FILE` (un file con la password, es. `/work/data/nextcloud-password`, permessi 600). Con il file la password resta fuori dalla configurazione del container.
3. Riavvia, apri `/admin` e accendi *cartella magica* per le catene che vuoi.

Per spegnerla, revoca la password per le app in Nextcloud e togli le variabili.

# Come funziona

## Percorso di una richiesta

```
browser / script ──► guard (middleware) ──► endpoint ──► cartella Job ──► coda (MAX_PARALLEL) ──► ops.<strumento> ──► FileResponse ──► pulizia
                     altri siti                          /work/upd/…      thread pool                                   compito in background
                     chiave API + permesso
                     intestazioni di sicurezza
```

1. **guard** (`server.py`) agisce prima di leggere il file: rifiuta le richieste da altri siti (`403`), controlla la chiave API e il suo permesso (`401` / `403`) e aggiunge le intestazioni di sicurezza a ogni risposta, anche agli errori.
2. L'endpoint crea un **Job**: una cartella in `/work/upd`. I file vengono scritti lì a blocchi di 1 MB (`save`), controllando `MAX_UPLOAD_MB` durante la lettura.
3. Il lavoro vero è in **`ops.py`**: ogni strumento è una funzione `strumento(src, out_dir, **opzioni) -> Result`. Le stesse funzioni servono all'API, alle catene e alla cartella magica.
4. I lavori pesanti passano da **`heavy()`**: un `asyncio.Semaphore(MAX_PARALLEL)` davanti a un thread pool. Quando uno strumento produce più file, lo ZIP si fa nello stesso turno, così non si rimette in fila.
5. La risposta è una `FileResponse` con un **compito in background** che cancella la cartella del Job dopo l'ultimo byte inviato, anche se il download si interrompe. Se qualcosa va storto prima, è l'endpoint stesso a cancellarla. All'avvio `/work/upd` viene svuotata, nel caso il container si sia fermato a metà lavoro.

## Limiti che proteggono il servizio

- **Pixel per pagina** (`MAX_PAGE_MPX`): un PDF di 1 KB può dichiarare una pagina di 5 × 5 metri; a 300 dpi sarebbe un'immagine di 60.000 × 60.000 pixel e il container finirebbe la memoria. Le pagine più grandi vengono rese a dpi più bassi; `X-Dpi-Reduced` dice quante sono.
- **Dimensione dei risultati** (`MAX_OUTPUT_MB`): contata file per file mentre i risultati vengono prodotti (`ops.Output`), così la richiesta si ferma appena supera il limite.
- **Lavori in parallelo** (`MAX_PARALLEL`) e limiti del container (`PLICO_CPUS`, `PLICO_MEMORY`).
- **Programmi esterni** (Ghostscript con `-dSAFER`, OCRmyPDF) eseguiti con un tempo massimo, senza shell.
- **Errori**: le eccezioni impreviste rispondono con un `500` generico, e i dettagli vanno solo nel log.

## Librerie

| Libreria | Usata per |
|---|---|
| PyMuPDF | pagine, anteprime, conversione in immagini, timbri, firme, annotazioni, moduli, oscuramento, confronto, più pagine per foglio |
| pikepdf (qpdf) | cifratura, riparazione |
| Ghostscript | compressione, riparazione (ultima risorsa) |
| OCRmyPDF + Tesseract | OCR, PDF/A-2 (con o senza riconoscimento del testo) |
| OpenCV | scanner (bordi del foglio, prospettiva) |
| FastAPI + Uvicorn | server HTTP e documentazione OpenAPI |

## Traduzioni

I testi della pagina sono in `server/static/i18n.js` (italiano e inglese). Gli errori dell'API sono scritti in italiano nel codice e tradotti da `server/i18n.py`, che riconosce messaggi fissi e schemi (es. `File troppo grande (massimo {n} MB)`). Un messaggio che manca dalla tabella viene mandato così com'è, in italiano.

# Sicurezza e privacy

- **La pagina non ha login.** Chiunque raggiunga il servizio può usarlo. Ascolta solo su `127.0.0.1`. Aprilo solo in una rete fidata (casa, VPN), oppure dietro un reverse proxy con autenticazione. Non esporlo direttamente su Internet.
- **Nessun file conservato.** La cartella di ogni richiesta viene cancellata dopo la risposta; la cartella magica cancella subito la cartella di ogni file. Il selftest controlla che non resti niente.
- **Intestazioni di sicurezza** su ogni risposta: `Content-Security-Policy` che permette solo gli script della pagina (per hash SHA-256, calcolato all'avvio), `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy`, `Permissions-Policy`. La pagina Swagger `/apidocs` ha una politica sua, che permette i suoi file da jsDelivr.
- **Richieste da altri siti.** Un `POST` inviato da una pagina di un altro sito (`Sec-Fetch-Site: cross-site`, oppure un `Origin` diverso dall'host) riceve `403`: una pagina malevola non può usare il servizio attraverso il browser di chi la visita.
- **Chiavi API** salvate come hash SHA-256 e confrontate in tempo costante. I cookie sono firmati con HMAC-SHA256 e un segreto casuale in `DATA_DIR/secret`, `HttpOnly` e `SameSite=Strict`.
- **Password dei PDF protetti**: senza password di proprietario ne viene generata una casuale, così i permessi scelti (stampa, copia, modifica) valgono davvero.
- **Oscuramento**: toglie il testo sotto i riquadri e cancella i pixel delle immagini, invece di coprirli soltanto; *pulisci metadati* toglie anche metadati e dati nascosti.
- **Container senza privilegi** (utente 1000, dietro `tini`), niente socket di Docker, un solo volume.
- **Caricamenti** senza limite (`MAX_UPLOAD_MB=0`), per scelta: i limiti che proteggono il server sono sui pixel, sulla dimensione dei risultati e sui lavori in parallelo. Imposta `MAX_UPLOAD_MB` se il servizio è condiviso con persone di cui non ti fidi.

# Manutenzione

## Selftest

```bash
docker compose exec plico python3 /app/selftest.py
```

Chiama ogni strumento del server in funzione con file generati e controlla i risultati; alla fine verifica che non sia rimasta nessuna cartella di richiesta (aspetta fino a 5 secondi, perché le cartelle si cancellano subito dopo la risposta). Alcuni controlli partono solo con l'impostazione relativa:

| Controllo | Parte quando |
|---|---|
| file oltre il limite → `413` | `MAX_UPLOAD_MB` tra 1 e 200 |
| risultato oltre il limite → `413` | `MAX_OUTPUT_MB` fino a 10 |
| chiavi API, interruttori, revoca | `PLICO_ADMIN_PASSWORD` è impostata nell'ambiente |
| Office | `CONVERTER_URL` è impostata |

La CI lo esegue con limiti piccoli e una password admin, così lì partono tutti i controlli.

## Aggiornamento

```bash
git pull
docker compose up -d --build
docker compose exec plico python3 /app/selftest.py
```

`DATA_DIR` sta nel volume, quindi chiavi, catene e interruttori restano.

## Log

```bash
docker compose logs -f plico
```

Il log degli accessi è spento (`--no-access-log`): i nomi dei file non vengono scritti da nessuna parte. Nel log ci sono i messaggi di avvio, gli errori imprevisti con il traceback e l'attività della cartella magica.

## Backup

Vale la pena salvare solo `DATA_DIR` (`/work/data`): hash delle chiavi, catene, interruttori e segreto dei cookie. Se si perde, bisogna ricreare le chiavi.

# Sviluppo

## Struttura del codice

```
server/
  server.py        app FastAPI: middleware guard, cartelle Job, coda, endpoint, API admin
  ops.py           tutte le operazioni sui PDF (una funzione per strumento), limiti, catene
  apikeys.py       KeyStore: chiavi, impostazioni, cookie firmati, accesso admin
  chains.py        ChainStore: catene salvate
  magic.py         client WebDAV e ciclo della cartella magica
  converter.py     client del Convertitore universale
  i18n.py          traduzioni in inglese degli errori dell'API
  selftest.py      controlli sul server in funzione
  static/          index.html, admin.html, i18n.js
nextcloud-app/     app Nextcloud (controller e client PHP, script della pagina)
tests/             pytest: test_api.py, test_features.py, test_ui.py
```

## Aggiungere uno strumento

1. Scrivi l'operazione in `ops.py`: `def strumento(src: Path, out_dir: Path, opzione: str = "x") -> Result`. Usa `open_pdf()`, `finish_pdf()`, `fail()` per gli errori da mostrare all'utente, e `Output()` / `one_or_zip()` quando produce più file, così `MAX_OUTPUT_MB` viene rispettato.
2. Aggiungi il permesso in `apikeys.PERMISSIONS`.
3. Aggiungi l'endpoint in `server.py` con `@tool(...)` e `one_file()` o `many_files()`, che si occupano della cartella Job, della coda e della pulizia.
4. Se può essere un passo di una catena, aggiungilo a `ops.CHAIN_OPS`.
5. Aggiungi la scheda e il modulo in `static/index.html`, i testi in `static/i18n.js`, i nuovi messaggi di errore in `i18n.py`.
6. Aggiungi un test in `tests/`, un controllo in `selftest.py` e l'endpoint in `docs/api.md`.

## Test

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium     # oppure PW_CHANNEL=chrome per usare Chrome già installato
python -m pytest
```

- `test_api.py` usa il `TestClient` di FastAPI: niente container, niente rete.
- `test_features.py` copre gli strumenti più recenti, le catene, il convertitore e la cartella magica con server finti.
- `test_ui.py` avvia il server e usa ogni strumento dalla pagina in Chromium headless; fallisce a qualsiasi errore JavaScript.

GitHub Actions (`.github/workflows/ci.yml`) esegue pytest, costruisce l'immagine ed esegue il selftest dentro il container.

# Riusare i componenti

Diverse parti non riguardano i PDF e sono state scritte per essere copiate in altri servizi FastAPI, a cominciare dal [Convertitore universale](https://github.com/EmaLau/universal-converter). Per ogni componente: quali file prendere e cosa cambiare.

## Chiavi API e pagina admin (come in Gokapi)

- **File**: `server/apikeys.py`, `server/static/admin.html`, le route admin in `server.py` (`/admin`, `/admin/api/*`), il middleware `guard`.
- **Da cambiare**: `PERMISSIONS` (uno per funzione dell'altro servizio), i nomi dei cookie (`plico_session`, `plico_admin`), il prefisso delle chiavi (`plico_`), il valore di `X-Requested-With`, `PATH_PERM` (percorso → permesso).
- **Da tenere**: chiavi controllate nel middleware *prima* di leggere il corpo della richiesta; hash SHA-256 confrontati con `hmac.compare_digest`; chiave mostrata una volta sola; `last_used` salvato al massimo una volta al minuto e scritto alla chiusura; i due interruttori salvati in `settings.json`, con le variabili come valore iniziale; limite ai tentativi di accesso.
- **Attenzione**: i client dell'altro servizio (per il convertitore, la sua app Nextcloud *Converti in*) devono poter mandare una chiave quando l'obbligo è attivo.

## Intestazioni di sicurezza e controllo degli altri siti

- **File**: `security_headers()`, `_inline_hashes()` e `cross_site()` in `server.py`.
- **Da cambiare**: le pagine di cui calcolare gli hash degli script, e la politica separata per `/apidocs`.
- **Da tenere**: intestazioni aggiunte anche alle risposte di errore (il middleware avvolge tutto); `Origin` confrontato con `Host` e `X-Forwarded-Host`, così funziona anche dietro un reverse proxy.

## File temporanei e limiti

- **File**: la classe `Job`, `save()` e `heavy()` in `server.py`; `Output` in `ops.py`.
- **Da tenere**: caricamenti parcheggiati nel volume dei dati (`tempfile.tempdir`), pulizia con un `BackgroundTask` più `except BaseException` prima della risposta, cartella svuotata all'avvio, un semaforo davanti al thread pool, risultati contati mentre vengono prodotti.
- **Attenzione**: un selftest che cerca gli avanzi deve aspettare un momento, perché il compito in background parte subito *dopo* che il client ha ricevuto la risposta.

## Traduzione degli errori dell'API

- **File**: `server/i18n.py` e il gestore `error()` in `server.py`.
- **Da tenere**: messaggi scritti una volta, in una lingua, nel codice; tradotti all'uscita secondo `Accept-Language`, con `Content-Language` nella risposta.

## Test e CI

- **File**: `tests/conftest.py` (file di esempio, server avviato per Playwright), `.github/workflows/ci.yml`, `pytest.ini`, `requirements-dev.txt`.
- **Da tenere**: due job nella CI, pytest senza Docker e build Docker + selftest con limiti piccoli, così partono tutti i controlli; il test del browser che fallisce a qualsiasi errore JavaScript.

## Documentazione interattiva dell'API

- FastAPI con `docs_url="/apidocs"`, `openapi_url="/apidocs/openapi.json"`, una descrizione con esempi e `Security(header_scheme)` sugli endpoint, così Swagger mostra il pulsante *Authorize* per `apikey`.

## Integrazioni facoltative

- **Schema**: un'integrazione è attiva solo quando ci sono le sue variabili (`CONVERTER_URL`, `NEXTCLOUD_*`), e `/api/features` dice alla pagina cosa mostrare. Il repository funziona senza nessuna di esse.
- **Segreti da file**: `NEXTCLOUD_PASSWORD_FILE` e `DATA_DIR/admin-password` tengono le password fuori dalla configurazione del container.

# Limiti noti

- La pagina non ha account utente: è pensata per una casa o un piccolo gruppo in una rete fidata.
- Scansioni molto grandi con l'OCR possono richiedere minuti e molta memoria; `MAX_PARALLEL` e i limiti del container decidono quante ne girano insieme.
- Il confronto lavora sul testo e sulle pagine disegnate: non riconosce i paragrafi spostati.
- Lo scanner trova il foglio quando si stacca dallo sfondo; su uno sfondo dello stesso colore tiene tutta la foto.
- Le conversioni Office dipendono dal Convertitore universale e dalla fedeltà di LibreOffice.

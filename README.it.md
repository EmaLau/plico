# Universal-PDF

<p align="center"><img src="docs/cover.svg" width="400" alt=""></p>

🇬🇧 [English](README.md) · 🇮🇹 **Italiano**

> **Lavori in corso — repository privato.** Gira su un homelab; alcuni limiti vanno sistemati prima di pubblicarlo. L'elenco è nel [README in inglese](README.md#to-do-before-publishing).

**Strumenti PDF self-hosted in una sola pagina web.** Unisci, dividi, estrai, riordina, ruota, elimina pagine, comprimi, converti tra PDF e immagini, proteggi o sblocca con password, aggiungi numeri di pagina e filigrane. Tutto gira sul tuo server: ogni richiesta lavora in una cartella temporanea che viene cancellata appena il risultato è stato inviato, quindi **sul server non resta nessun file**.

## Strumenti

| Gruppo | Strumenti |
|---|---|
| Organizza | Unisci (anche PDF e immagini insieme), Dividi (per intervalli o ogni N pagine), Estrai pagine, Riordina / ruota / elimina con le miniature, Ruota tutte le pagine |
| Ottimizza | Comprimi (tre livelli, scala di grigi facoltativa) con Ghostscript; se il risultato sarebbe più grande, restituisce l'originale |
| Converti | Immagini → PDF (adatta, A4 o Letter, con margini), PDF → JPG/PNG ai DPI scelti |
| Sicurezza | Proteggi con password (AES-256), Sblocca |
| Modifica | Numeri di pagina (posizione, formato come `Pagina {n} di {tot}`, numero iniziale, salta la prima) e filigrana di testo (dimensione, opacità, angolo, colore), anche su pagine ruotate |

## Avvio rapido

Serve Docker con Docker Compose.

```bash
git clone https://github.com/EmaLau/universal-pdf.git
cd universal-pdf
docker compose up -d --build
```

Apri <http://localhost:8080>. Per controllare che tutti gli strumenti funzionino:

```bash
docker compose exec universal-pdf python3 /app/selftest.py
```

Il selftest esegue 21 controlli sul server in funzione e salva alcuni risultati di esempio in `/work/selftest/` dentro il container.

> **Sicurezza.** Il servizio non ha login e di base ascolta solo su `127.0.0.1`. Aprilo alla rete solo se la rete è fidata (casa, VPN), oppure mettilo dietro un reverse proxy con autenticazione. Non esporlo direttamente su Internet.

## Configurazione

Copia `.env.example` in `.env` e cambia quello che serve.

| Variabile | Predefinito | Descrizione |
|---|---|---|
| `UPDF_BIND` / `UPDF_PORT` | `127.0.0.1` / `8080` | Dove pubblicare il servizio (`0.0.0.0` per tutta la rete) |
| `MAX_UPLOAD_MB` | `2048` | Dimensione massima di ogni file caricato |
| `MAX_PAGE_MPX` | `50` | Megapixel massimi per una pagina in *PDF in immagini*: le pagine più grandi vengono rese a dpi più bassi |
| `UPDF_CPUS` / `UPDF_MEMORY` | `4` / `3G` | Limiti di risorse del container |
| `UPDF_UID` / `UPDF_GID` | `1000` | Utente che esegue il servizio nel container |
| `TZ` | `Europe/Rome` | Fuso orario |

## API

L'elenco completo degli endpoint e dei campi è nel [README in inglese](README.md#api). Esempio:

```bash
# unisci due PDF
curl -F files=@a.pdf -F files=@b.pdf -o unito.pdf http://localhost:8080/api/merge
```

## Licenza

[GNU Affero General Public License v3.0](LICENSE), la stessa di PyMuPDF. Puoi usare, modificare e ridistribuire il progetto; se lo modifichi e lo offri come servizio di rete, devi rendere disponibile anche il codice delle tue modifiche.

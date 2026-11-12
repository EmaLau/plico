"""Messaggi di errore in italiano o in inglese.

Il codice scrive i messaggi in italiano; se la richiesta preferisce un'altra lingua (Accept-Language), o non
ne indica nessuna, il messaggio viene tradotto in inglese con questa tabella.
"""
from __future__ import annotations

import re

_EN: list[tuple[str, str]] = [
    (r"Errore durante l'elaborazione del file", "Error while processing the file"),
    (r"Il file non e' un PDF valido", "The file is not a valid PDF"),
    (r"Il PDF e' protetto da password: sbloccalo prima con 'Proteggi / Sblocca'",
     "The PDF is password protected: unlock it first with 'Protect / Unlock'"),
    (r"Il PDF e' gia' protetto: sbloccalo prima", "The PDF is already protected: unlock it first"),
    (r"File troppo grande \(massimo (\d+) MB\)", r"File too large (maximum \1 MB)"),
    (r"Il risultato supera (\d+) MB: scegli meno pagine o una risoluzione piu' bassa",
     r"The result exceeds \1 MB: choose fewer pages or a lower resolution"),
    (r"Intervallo non valido: '(.*)'", r"Invalid range: '\1'"),
    (r"'(.*)' e' fuori dal documento \(pagine 1-(\d+)\)", r"'\1' is outside the document (pages 1-\2)"),
    (r"Scrivi almeno un intervallo di pagine", "Write at least one page range"),
    (r"Troppe pagine per l'anteprima \(massimo (\d+)\)", r"Too many pages for the preview (maximum \1)"),
    (r"Scegli almeno due file da unire", "Choose at least two files to merge"),
    (r"Elenco pagine non valido", "Invalid page list"),
    (r"Il documento finale non puo' essere vuoto", "The final document cannot be empty"),
    (r"Pagina inesistente", "Page does not exist"),
    (r"Livello di compressione sconosciuto", "Unknown compression level"),
    (r"Ghostscript non e' riuscito a comprimere il file", "Ghostscript could not compress the file"),
    (r"Formato pagina sconosciuto", "Unknown page size"),
    (r"Formato immagine sconosciuto", "Unknown image format"),
    (r"Scrivi una password", "Write a password"),
    (r"Password sbagliata", "Wrong password"),
    (r"Scegli i numeri di pagina, una filigrana o entrambi", "Choose page numbers, a watermark or both"),
    (r"Serve una chiave API nell'intestazione 'apikey'", "An API key is required in the 'apikey' header"),
    (r"Chiave API non valida", "Invalid API key"),
    (r"La chiave non ha il permesso '(.*)'", r"The key does not have the '\1' permission"),
    (r"Area admin disattivata: imposta UPDF_ADMIN_PASSWORD", "Admin area disabled: set UPDF_ADMIN_PASSWORD"),
    (r"Accedi con la password admin", "Log in with the admin password"),
    (r"Nessuna password admin impostata", "No admin password is set"),
    (r"Richiesta non valida", "Invalid request"),
    (r"Troppi tentativi: riprova tra qualche minuto", "Too many attempts: try again in a few minutes"),
    (r"Dai un nome alla chiave", "Give the key a name"),
    (r"Permessi sconosciuti: (.*)", r"Unknown permissions: \1"),
    (r"Chiave inesistente", "Key does not exist"),
    (r"Imposta prima una password \(UPDF_ADMIN_PASSWORD o file admin-password\)",
     "Set a password first (UPDF_ADMIN_PASSWORD or the admin-password file)"),
    (r"Richiesta inviata da un altro sito", "Request sent from another site"),
    (r"Posizione non valida", "Invalid position"),
    (r"Catena di operazioni non valida", "Invalid chain of operations"),
    (r"(.+) non e' disponibile su questo server", r"\1 is not available on this server"),
    (r"(.+): tempo scaduto", r"\1: timed out"),
    (r"Immagine non leggibile: (.*)", r"Unreadable image: \1"),
    (r"Lingua OCR non disponibile: (.*)", r"OCR language not available: \1"),
    (r"Non sono riuscito a riparare il file: e' troppo danneggiato", "Could not repair the file: it is too damaged"),
    (r"Scegli immagini o testo", "Choose images or text"),
    (r"Nel PDF non ci sono immagini da estrarre", "There are no images to extract in the PDF"),
    (r"Modalita' sconosciuta", "Unknown mode"),
    (r"I margini sono troppo grandi per la pagina", "The margins are too large for the page"),
    (r"Pagine per foglio: 2, 4, 6, 8, 9 o 16", "Pages per sheet: 2, 4, 6, 8, 9 or 16"),
    (r"Disegna la firma o scegli un'immagine", "Draw the signature or choose an image"),
    (r"Immagine della firma non leggibile", "Unreadable signature image"),
    (r"Elenco annotazioni non valido", "Invalid annotation list"),
    (r"Aggiungi almeno un'annotazione", "Add at least one annotation"),
    (r"Tipo di annotazione sconosciuto: (.*)", r"Unknown annotation type: \1"),
    (r"Valori dei campi non validi", "Invalid field values"),
    (r"Elenco aree non valido", "Invalid area list"),
    (r"Espressione regolare non valida", "Invalid regular expression"),
    (r"Scrivi cosa oscurare o disegna le aree", "Write what to redact or draw the areas"),
    (r"Scegli almeno una foto", "Choose at least one photo"),
    (r"Troppe operazioni in una catena \(massimo (\d+)\)", r"Too many operations in a chain (maximum \1)"),
    (r"Operazione sconosciuta nella catena: (.*)", r"Unknown operation in the chain: \1"),
    (r"Opzioni non valide per '(.*)': (.*)", r"Invalid options for '\1': \2"),
    (r"'(.*)' non produce un PDF", r"'\1' does not produce a PDF"),
    (r"Dai un nome alla catena", "Give the chain a name"),
    (r"Catena inesistente", "Chain does not exist"),
    (r"Esiste gia' una catena con questo nome", "A chain with this name already exists"),
    (r"Il convertitore ha risposto con un errore: (.*)", r"The converter returned an error: \1"),
    (r"Il convertitore non risponde", "The converter does not respond"),
    (r"Conversione Office non attiva su questo server \(CONVERTER_URL\)", "Office conversion is not enabled on this server (CONVERTER_URL)"),
    (r"Formato non supportato: scegli un documento Word, Excel, PowerPoint o OpenDocument",
     "Unsupported format: choose a Word, Excel, PowerPoint or OpenDocument file"),
    (r"Scegli un PDF", "Choose a PDF"),
    (r"Formato di destinazione sconosciuto", "Unknown target format"),
    (r"Il convertitore non e' riuscito a convertire il file:?(.*)", r"The converter could not convert the file:\1"),
    (r"Il convertitore", "The converter"),
]
_TABLE = [(re.compile(f"^{it}$"), en) for it, en in _EN]


def pick(accept_language: str | None) -> str:
    """'it' se la lingua preferita e' l'italiano, altrimenti 'en'."""
    first = (accept_language or "").split(",")[0].strip().lower()
    return "it" if first.startswith("it") else "en"


def t(msg, lang: str):
    if lang == "it" or not isinstance(msg, str):
        return msg
    for rx, en in _TABLE:
        if rx.match(msg):
            return rx.sub(en, msg)
    return msg

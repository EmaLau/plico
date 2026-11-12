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

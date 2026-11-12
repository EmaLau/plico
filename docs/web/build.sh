#!/bin/sh
# Genera le pagine /docs di Plico (italiano e inglese) dai Markdown di docs/, con pandoc.
# Uso: docs/web/build.sh <cartella di uscita>   (crea docs-it.html e docs-en.html)
# Gira nello stadio "docs" del Dockerfile; in locale serve pandoc installato.
set -eu
# pandoc legge gli argomenti (titoli con — e →) secondo la localizzazione: serve UTF-8
export LANG=C.UTF-8 LC_ALL=C.UTF-8
HERE=$(cd "$(dirname "$0")" && pwd)
DOCS=$(dirname "$HERE")
OUT=${1:?cartella di uscita}
mkdir -p "$OUT"
GH=https://github.com/EmaLau/plico/blob/main

# toglie titolo, link alle lingue e indice scritti per GitHub (la pagina ha i suoi), e sistema i link relativi
prep() {
  awk 'f || /^# (Overview|Panoramica)$/ {f=1} f' "$1" | sed \
    -e "s#](api\.md#]($GH/docs/api.md#g" \
    -e "s#](\.\./README\.it\.md#]($GH/README.it.md#g" \
    -e "s#](\.\./README\.md#]($GH/README.md#g" \
    -e "s#](documentation\.md#](docs?lang=en#g" \
    -e "s#](documentazione\.md#](docs?lang=it#g"
}

page() {  # md lang pagetitle crumb subtitle cta tocname top otherlang otherlabel
  prep "$DOCS/$1" | pandoc --from markdown --standalone --section-divs --toc --toc-depth=2 \
    --template "$HERE/template.html" -H "$HERE/style.html" \
    -M lang="$2" -M pagetitle="$3" -M crumb="$4" -M subtitle="$5" -M cta="$6" -M tocname="$7" -M top="$8" \
    -M otherlang="$9" -M otherlabel="${10}" -o "$OUT/docs-$2.html"
  echo "$OUT/docs-$2.html"
}

page documentazione.md it "Plico — Documentazione" "Documentazione" \
  "Installazione, configurazione, pagina admin, catene, Nextcloud, funzionamento interno, sicurezza e sviluppo." \
  "Apri Plico →" "Indice" "torna su ↑" en "English"
page documentation.md en "Plico — Documentation" "Documentation" \
  "Installation, configuration, admin page, chains, Nextcloud, internals, security and development." \
  "Open Plico →" "Contents" "back to top ↑" it "Italiano"

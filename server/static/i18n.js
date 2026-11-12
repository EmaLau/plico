/* Plico: interfaccia in italiano o in inglese.
   Le pagine sono scritte in italiano; se la lingua scelta e' l'inglese, ogni testo che compare nella
   pagina (anche quelli creati dal JavaScript) viene tradotto con questo dizionario. La lingua parte da
   quella del browser e si cambia con il selettore IT / EN (ricordato in localStorage).
   Alle richieste al server si aggiunge Accept-Language, cosi' anche i messaggi di errore arrivano
   nella lingua giusta. */
"use strict";
const PLICO_I18N = (() => {
  const EN = {
    // intestazione e home
    "Tutto": "Runs", "in locale": "locally", "Documentazione": "Documentation",
    "Tutti gli strumenti PDF, in casa": "All the PDF tools, at home",
    "Unisci, dividi, comprimi, converti e proteggi i tuoi PDF. Tutto gira sul tuo server: i file non vanno su internet e vengono cancellati appena hai scaricato il risultato.":
      "Merge, split, compress, convert and protect your PDFs. Everything runs on your own server: files never go to the Internet and are deleted as soon as you download the result.",
    "Trascina qui un PDF (o in qualsiasi punto della pagina)": "Drop a PDF here (or anywhere on the page)",
    "oppure clicca per sceglierlo, poi scegli cosa farci": "or click to choose it, then pick what to do",
    "Organizza": "Organize", "Ottimizza e converti": "Optimize and convert", "Sicurezza e modifica": "Security and editing",
    "Tutti gli strumenti": "All tools",
    "Plico · self-hosted · nessun file conservato ·": "Plico · self-hosted · no files kept ·",
    "Cosa vuoi fare?": "What do you want to do?", "Annulla": "Cancel", "Rilascia il file": "Drop the file",
    // strumenti
    "Unisci PDF": "Merge PDF", "Metti insieme più PDF (anche immagini) nell'ordine che vuoi.": "Combine several PDFs (images too) in the order you want.",
    "Dividi PDF": "Split PDF", "Separa il documento per intervalli o ogni N pagine.": "Split the document by ranges or every N pages.",
    "Estrai pagine": "Extract pages", "Tieni solo le pagine che ti servono, in un unico PDF.": "Keep only the pages you need, in a single PDF.",
    "Riordina pagine": "Reorder pages", "Trascina le anteprime per cambiare l'ordine.": "Drag the thumbnails to change the order.",
    "Ruota PDF": "Rotate PDF", "Ruota tutte le pagine o solo alcune.": "Rotate all pages or just some.",
    "Elimina pagine": "Delete pages", "Clicca le pagine da togliere.": "Click the pages to remove.",
    "Comprimi PDF": "Compress PDF", "Riduci il peso del file scegliendo la qualità.": "Make the file smaller by choosing the quality.",
    "Immagini in PDF": "Images to PDF", "JPG, PNG, WebP… in un PDF, una pagina per immagine.": "JPG, PNG, WebP… into a PDF, one page per image.",
    "PDF in immagini": "PDF to images", "Esporta le pagine come PNG o JPG.": "Export the pages as PNG or JPG.",
    "Proteggi / Sblocca": "Protect / Unlock", "Aggiungi una password (AES-256) o toglila.": "Add a password (AES-256) or remove it.",
    "Numeri pagina e filigrana": "Page numbers and watermark", "Numera le pagine e/o aggiungi un testo in filigrana.": "Number the pages and/or add a text watermark.",
    // caricamento file
    "Scegli il file": "Choose the file", "Scegli i file": "Choose the files", "Scegli il PDF": "Choose the PDF",
    "o trascinalo qui": "or drop it here", "o trascinali qui (puoi aggiungerne altri dopo)": "or drop them here (you can add more later)",
    "Alcuni file non sono del tipo giusto e sono stati ignorati.": "Some files are not the right type and were ignored.",
    "Trascina per spostare": "Drag to move", "Su": "Up", "Giù": "Down", "Togli": "Remove", "Avvia": "Start",
    // anteprime
    "Preparo le anteprime…": "Preparing thumbnails…", "Errore": "Error",
    "Il documento ha": "The document has", "pagine.": "pages.",
    "Trascina le pagine (o usa le frecce) per cambiare l'ordine.": "Drag the pages (or use the arrows) to change the order.",
    "Usa le frecce su ogni pagina, o ruota tutto insieme.": "Use the arrows on each page, or rotate everything at once.",
    "Clicca le pagine da eliminare (diventano barrate).": "Click the pages to delete (they get crossed out).",
    "Clicca le pagine da tenere: le altre non saranno nel file.": "Click the pages to keep: the others won't be in the file.",
    "Inverti ordine": "Reverse order", "Ordine originale": "Original order", "Tutte a sinistra": "All left",
    "Tutte a destra": "All right", "Annulla rotazioni": "Undo rotations", "Elimina dispari": "Delete odd",
    "Elimina pari": "Delete even", "Nessuna": "None", "Tutte": "All", "Prima": "Earlier", "Dopo": "Later",
    "Ruota a sinistra": "Rotate left", "Ruota a destra": "Rotate right",
    // opzioni
    "Per intervalli": "By ranges", "es. 1-3, 5, 8-": "e.g. 1-3, 5, 8-", "Ogni N pagine": "Every N pages",
    "parti uguali": "equal parts", "Una pagina per file": "One page per file", "tutte separate": "all separate",
    "Intervalli (ogni intervallo diventa un PDF)": "Ranges (each range becomes a PDF)", "Pagine per file": "Pages per file",
    "Se escono più file li scarichi tutti insieme in uno ZIP.": "If there are several files you download them together in a ZIP.",
    "L'ordine dei file nella lista è l'ordine nel PDF finale. Le immagini diventano una pagina ciascuna.":
      "The order of the list is the order in the final PDF. Each image becomes one page.",
    "Leggera": "Light", "qualità alta · 220 dpi": "high quality · 220 dpi", "Consigliata": "Recommended",
    "buon equilibrio · 150 dpi": "good balance · 150 dpi", "Forte": "Strong", "file minimo · 72 dpi": "smallest file · 72 dpi",
    "Converti anche in bianco e nero (scala di grigi)": "Also convert to black and white (grayscale)",
    "Dimensione pagina": "Page size", "Come l'immagine": "Same as the image", "Lettera (US)": "Letter (US)",
    "Margine": "Margin", "Nessuno": "None", "Piccolo": "Small", "Grande": "Large",
    "Puoi aggiungere anche PDF: vengono inseriti così come sono.": "You can add PDFs too: they are inserted as they are.",
    "migliore qualità": "best quality", "file più leggeri": "smaller files", "Risoluzione": "Resolution",
    "72 dpi · schermo": "72 dpi · screen", "150 dpi · normale": "150 dpi · normal", "300 dpi · stampa": "300 dpi · print",
    "600 dpi · massima": "600 dpi · maximum", "Solo queste pagine (vuoto = tutte)": "Only these pages (empty = all)",
    "es. 1, 3-5": "e.g. 1, 3-5", "Proteggi": "Protect", "aggiungi password": "add a password", "Sblocca": "Unlock",
    "togli password": "remove the password", "Password per aprire": "Password to open", "Ripeti password": "Repeat password",
    "Cosa può fare chi apre il file": "What people who open the file can do", "Stampare": "Print",
    "Copiare il testo": "Copy the text", "Modificare": "Edit",
    "Cifratura AES-256. Se dimentichi la password il file non si apre più: non c'è modo di recuperarla.":
      "AES-256 encryption. If you forget the password the file can't be opened any more: there is no way to recover it.",
    "Password attuale del PDF": "Current PDF password", "Il file sbloccato si apre senza password.": "The unlocked file opens without a password.",
    "Numeri di pagina": "Page numbers", "Posizione": "Position", "In basso al centro": "Bottom center",
    "In basso a destra": "Bottom right", "In basso a sinistra": "Bottom left", "In alto al centro": "Top center",
    "In alto a destra": "Top right", "In alto a sinistra": "Top left", "Formato": "Format", "Inizia da": "Start at",
    "Dimensione": "Size", "Non numerare la prima pagina (copertina)": "Don't number the first page (cover)",
    "Filigrana (lascia vuoto per non metterla)": "Watermark (leave empty for none)", "Testo": "Text",
    "es. BOZZA, RISERVATO, COPIA": "e.g. DRAFT, CONFIDENTIAL, COPY", "Trasparenza": "Opacity", "Inclinazione": "Angle",
    "Diagonale": "Diagonal", "Orizzontale": "Horizontal", "Verticale": "Vertical", "Colore": "Color",
    // pulsante e invio
    "Salva nuovo ordine": "Save new order", "Applica rotazione": "Apply rotation", "Crea PDF": "Create PDF",
    "Converti in immagini": "Convert to images", "Sblocca PDF": "Unlock PDF", "Proteggi PDF": "Protect PDF", "Applica": "Apply",
    "Le due password non coincidono.": "The two passwords don't match.", "Invio al server…": "Uploading…",
    "Elaborazione in corso…": "Processing…", "Connessione al server persa. Controlla la rete e riprova.": "Connection to the server lost. Check the network and try again.",
    "Il file è pronto": "Your file is ready", "Scarica": "Download", "Ricomincia": "Start over",
    "Continua con lo stesso file:": "Continue with the same file:", "Scarica ZIP": "Download ZIP",
    "Scarica immagine": "Download image", "Scarica PDF": "Download PDF",
    "Il file era già ottimizzato: non si riesce a ridurlo ulteriormente.": "The file was already optimized: it can't be made any smaller.",
    // fase 4: strumenti nuovi
    "Modifica e firma": "Edit and sign", "Strumenti avanzati": "Advanced tools",
    "OCR": "OCR", "Rendi cercabile e copiabile il testo dei PDF scansionati.": "Make the text of scanned PDFs searchable and copyable.",
    "Office in PDF": "Office to PDF", "Word, Excel, PowerPoint e OpenDocument in PDF.": "Word, Excel, PowerPoint and OpenDocument to PDF.",
    "PDF in Office": "PDF to Office", "Da PDF a Word, Excel, PowerPoint o testo.": "From PDF to Word, Excel, PowerPoint or text.",
    "PDF/A": "PDF/A", "Converti in PDF/A per conservarlo a lungo.": "Convert to PDF/A to keep it for the long term.",
    "Scanner": "Scanner", "Foto di documenti raddrizzate e unite in un PDF.": "Photos of documents straightened and combined into a PDF.",
    "Firma PDF": "Sign PDF", "Disegna la firma o usa un'immagine e mettila dove vuoi.": "Draw your signature or use an image and place it where you want.",
    "Compila moduli": "Fill forms", "Riempi i campi di un modulo PDF ed eventualmente bloccali.": "Fill in the fields of a PDF form and optionally lock them.",
    "Annota PDF": "Annotate PDF", "Evidenziatore, note, caselle di testo, frecce e disegno.": "Highlighter, notes, text boxes, arrows and drawing.",
    "Oscura": "Redact", "Togli davvero testo e zone sensibili, non solo coprirli.": "Really remove sensitive text and areas, not just cover them.",
    "Metadati e pulizia": "Metadata and cleanup", "Cambia titolo e autore o togli i dati nascosti.": "Change title and author or remove hidden data.",
    "Confronta PDF": "Compare PDF", "Trova le differenze tra due versioni di un documento.": "Find the differences between two versions of a document.",
    "Ritaglia e ridimensiona": "Crop and resize", "Togli i margini o porta tutte le pagine in A4.": "Remove margins or bring every page to A4.",
    "Più pagine per foglio": "Pages per sheet", "2, 4 o più pagine per foglio, o un opuscolo da stampare.": "2, 4 or more pages per sheet, or a booklet to print.",
    "Estrai immagini e testo": "Extract images and text", "Salva le immagini (ZIP) o tutto il testo (TXT).": "Save the images (ZIP) or all the text (TXT).",
    "Ripara PDF": "Repair PDF", "Prova a recuperare un PDF danneggiato che non si apre.": "Try to recover a damaged PDF that won't open.",
    "Più file e catene": "Batch and chains", "Più operazioni di fila, anche su tanti file insieme (ZIP).": "Several operations in a row, also on many files at once (ZIP).",
    "Evidenzia": "Highlight", "Riquadro": "Box", "Nota": "Note", "Freccia": "Arrow", "Disegno": "Drawing",
    "Zona da oscurare": "Area to redact", "Posizione della firma": "Signature position",
    "Disegna la firma qui sopra (o scegli un'immagine), poi trascina sulla pagina il riquadro dove metterla.":
      "Draw your signature above (or choose an image), then drag on the page the box where to put it.",
    "Scegli lo strumento e trascina sulla pagina. Per Testo e Nota scrivi prima il testo qui sopra.":
      "Choose the tool and drag on the page. For Text and Note, type the text above first.",
    "Trascina sulla pagina sopra le zone da oscurare. Puoi anche scrivere più sotto le parole da cercare in tutto il documento.":
      "Drag on the page over the areas to redact. You can also type below the words to look for in the whole document.",
    "Cancella la firma": "Clear signature", "Usa un'immagine": "Use an image", "Testo per Testo e Nota": "Text for Text and Note",
    "Togli l'ultima": "Remove last", "Togli tutte": "Remove all",
    "Questo PDF non ha campi da compilare.": "This PDF has no fields to fill in.",
    "Intestazione e piè di pagina": "Header and footer", "Intestazione": "Header", "Piè di pagina": "Footer",
    "es. {file} · {date}": "e.g. {file} · {date}", "es. Riservato · pagina {n} di {tot}": "e.g. Confidential · page {n} of {tot}",
    "Puoi usare {n} (pagina), {tot} (totale), {date} (data) e {file} (nome del file).": "You can use {n} (page), {tot} (total), {date} (date) and {file} (file name).",
    "Logo o immagine in filigrana": "Logo or image watermark", "Dimensione del logo": "Logo size",
    "Usa la stessa trasparenza della filigrana di testo.": "Uses the same opacity as the text watermark.",
    "Lingua del testo": "Text language", "Italiano e inglese": "Italian and English", "Italiano": "Italian", "Inglese": "English",
    "Rifai l'OCR anche sulle pagine che hanno già del testo": "Redo OCR also on pages that already have text",
    "Il PDF resta uguale a vista, ma il testo diventa ricercabile e copiabile. Può richiedere qualche secondo per pagina.":
      "The PDF looks the same, but the text becomes searchable and copyable. It can take a few seconds per page.",
    "Fai anche l'OCR delle pagine scansionate": "Also run OCR on scanned pages",
    "PDF/A-2 incorpora i font e i colori, così il documento si apre uguale anche fra molti anni.":
      "PDF/A-2 embeds fonts and colors, so the document opens the same even many years from now.",
    "La conversione la fa il Convertitore universale collegato a questo server.": "The conversion is done by the Universal Converter connected to this server.",
    "Word (.docx)": "Word (.docx)", "OpenDocument (.odt)": "OpenDocument (.odt)", "Testo (.txt)": "Text (.txt)",
    "Colori": "Color", "come la foto": "like the photo", "Grigi": "Gray", "più leggero": "lighter", "Bianco e nero": "Black and white",
    "testo nitido": "sharp text", "Pagina": "Page", "Come la foto": "Same as the photo",
    "Fotografa il foglio su un piano scuro: i bordi vengono trovati da soli e la pagina raddrizzata. Dal telefono puoi scattare direttamente.":
      "Photograph the sheet on a dark surface: the edges are found automatically and the page is straightened. On a phone you can take the photo directly.",
    "La firma viene inserita come immagine. Non è una firma digitale con certificato.": "The signature is added as an image. It is not a digital signature with a certificate.",
    "Rendi le annotazioni parte della pagina (non si possono più modificare)": "Make the annotations part of the page (they can no longer be edited)",
    "Parole o frasi da oscurare in tutto il documento (una per riga)": "Words or phrases to redact in the whole document (one per line)",
    "es. Mario Rossi": "e.g. John Smith", "Cerca anche": "Also look for", "Indirizzi email": "Email addresses",
    "Numeri di telefono": "Phone numbers", "IBAN": "IBAN", "Codici fiscali": "Italian tax codes", "Numeri di carta": "Card numbers",
    "Il testo oscurato viene tolto dal file, non solo coperto: non si può recuperare. Vengono tolti anche i metadati.":
      "Redacted text is removed from the file, not just covered: it cannot be recovered. Metadata is removed too.",
    "Blocca i campi dopo averli compilati": "Lock the fields after filling them in", "Leggo i campi del modulo…": "Reading the form fields…",
    "Titolo": "Title", "Autore": "Author", "Oggetto": "Subject", "Parole chiave": "Keywords",
    "Togli tutti i dati nascosti (metadati, JavaScript, allegati, miniature, testo nascosto)": "Remove all hidden data (metadata, JavaScript, attachments, thumbnails, hidden text)",
    "Leggo i metadati…": "Reading the metadata…",
    "Scegli due PDF: il primo è la versione A, il secondo la B. Ottieni un PDF con le parole cambiate e le pagine affiancate, con le differenze in rosso.":
      "Choose two PDFs: the first is version A, the second version B. You get a PDF with the changed words and the pages side by side, with the differences in red.",
    "Ridimensiona": "Resize", "tutto nello stesso formato": "everything in the same size", "Ritaglia": "Crop", "margini in mm": "margins in mm",
    "Ritaglio automatico": "Auto crop", "togli il bianco": "remove white space", "A3": "A3", "A5": "A5", "Legal (US)": "Legal (US)",
    "Margine (mm)": "Margin (mm)", "Sopra (mm)": "Top (mm)", "Destra (mm)": "Right (mm)", "Sotto (mm)": "Bottom (mm)", "Sinistra (mm)": "Left (mm)",
    "Spazio da lasciare (mm)": "Space to keep (mm)", "risparmia carta": "saves paper", "Opuscolo": "Booklet",
    "fronte-retro, piegato a metà": "double-sided, folded in half", "Pagine per foglio": "Pages per sheet", "Foglio": "Sheet",
    "Stampa fronte-retro girando sul lato corto, poi piega i fogli a metà.": "Print double-sided flipping on the short edge, then fold the sheets in half.",
    "Immagini": "Images", "in uno ZIP": "in a ZIP", "file .txt": ".txt file",
    "Ricostruisce la struttura del file. Se il PDF è troppo danneggiato non sempre è possibile.": "Rebuilds the structure of the file. If the PDF is too damaged it is not always possible.",
    "Catena salvata": "Saved chain", "— scegli tu le operazioni qui sotto —": "— choose the operations below —",
    "Operazioni, nell'ordine": "Operations, in order", "OCR (italiano e inglese)": "OCR (Italian and English)", "Togli i dati nascosti": "Remove hidden data",
    "Numeri di pagina (1 / 10)": "Page numbers (1 / 10)", "Proteggi con password": "Protect with a password",
    "Con più file ricevi uno ZIP con un PDF per ogni file. Le catene salvate si gestiscono nella pagina admin.":
      "With several files you get a ZIP with one PDF per file. Saved chains are managed on the admin page.",
    "Avvia l'OCR": "Run OCR", "Converti in PDF": "Convert to PDF", "Converti": "Convert", "Converti in PDF/A": "Convert to PDF/A",
    "Compila": "Fill in", "Salva le annotazioni": "Save annotations", "Salva": "Save", "Confronta": "Compare", "Crea": "Create",
    "Estrai": "Extract", "Ripara": "Repair",
    // pagina admin: catene
    "Catene salvate": "Saved chains", "Nuova catena": "New chain", "Nome della catena": "Chain name", "Crea catena": "Create chain",
    "Cartella magica in Nextcloud": "Magic folder in Nextcloud", "Elimina": "Delete", "Conferma eliminazione": "Confirm delete",
    "Nessuna catena per ora.": "No chains yet.",
    "Scegli almeno un'operazione": "Choose at least one operation", "Password (solo per Proteggi)": "Password (only for Protect)",
    "Ruota": "Rotate", "Riordina": "Reorder",
    "Una catena mette in fila più operazioni. Si usa dalla pagina web (Più file e catene), dall'API (": "A chain runs several operations in a row. It can be used from the web page (Batch and chains), from the API (",
    ") e, se attivi la cartella magica, da Nextcloud.": ") and, if you turn on the magic folder, from Nextcloud.",
    "con": "with",
    "Cartella magica non configurata: servono NEXTCLOUD_URL, NEXTCLOUD_USER e NEXTCLOUD_PASSWORD sul server.": "Magic folder not configured: NEXTCLOUD_URL, NEXTCLOUD_USER and NEXTCLOUD_PASSWORD are needed on the server.",
    // pagina admin
    "Documentazione API": "API documentation", "Esci": "Log out", "Chiavi API": "API keys",
    "Le chiavi servono agli script (curl, Comandi rapidi di iPhone, altri servizi) per usare l'API. Ognuna ha i suoi permessi e si può revocare in ogni momento. La pagina web non ne ha bisogno.":
      "Keys let scripts (curl, iPhone Shortcuts, other services) use the API. Each has its own permissions and can be revoked at any time. The web page doesn't need one.",
    "Area admin disattivata": "Admin area disabled", "Accedi": "Log in", "Password admin": "Admin password",
    "Nuova chiave": "New key", "Nome (per ricordarti chi la usa)": "Name (to remember who uses it)",
    "es. Comandi rapidi iPhone": "e.g. iPhone Shortcuts", "Crea chiave": "Create key", "Tutti i permessi": "All permissions",
    "Accesso all'area admin": "Access to the admin area", "Password per entrare in questa pagina": "Password to open this page",
    "Chiave creata: copiala adesso": "Key created: copy it now",
    "Non verrà più mostrata: sul server resta solo una sua impronta. Se la perdi, revocala e creane un'altra.":
      "It won't be shown again: the server keeps only a fingerprint of it. If you lose it, revoke it and create another one.",
    "Copia": "Copy", "Copiata": "Copied", "Esempio:": "Example:", "Chiavi attive": "Active keys",
    "Chiave obbligatoria per le API": "Key required for the API", "Revoca": "Revoke", "Conferma revoca": "Confirm revoke",
    "Nessuna chiave per ora.": "No keys yet.", "Scegli almeno un permesso": "Choose at least one permission",
    "Informazioni e anteprime": "Info and thumbnails", "Unisci": "Merge", "Dividi ed estrai": "Split and extract",
    "Riordina, ruota ed elimina pagine": "Reorder, rotate and delete pages", "Ruota tutte le pagine": "Rotate all pages",
    "Comprimi": "Compress", "Proteggi e sblocca": "Protect and unlock", "Numeri di pagina e filigrana": "Page numbers and watermark",
    "Attiva: per entrare serve la password admin.": "On: the admin password is needed to get in.",
    "Attivo: ogni chiamata fatta fuori dalla pagina web deve avere una chiave. La pagina web continua a funzionare.":
      "On: every call made outside the web page needs a key. The web page keeps working.",
    "Disattivo: le chiamate senza chiave sono accettate. Le chiavi limitano comunque cosa può fare ogni script.":
      "Off: calls without a key are accepted. Keys still limit what each script can do.",
    "Disattiva:": "Off:",
    "chiunque raggiunga il servizio può creare, modificare e revocare le chiavi. Con la password spenta anche l'obbligo della chiave protegge poco, perché chiunque può crearsene una.":
      "anyone who can reach the service can create, change and revoke keys. With the password off, requiring a key protects little, because anyone can create one.",
    "Disattiva, e non c'è nessuna password impostata: per riattivarla imposta PLICO_ADMIN_PASSWORD o il file admin-password e riavvia.":
      "Off, and no password is set: to turn it back on set PLICO_ADMIN_PASSWORD or the admin-password file and restart.",
    "Per attivarla imposta la variabile": "To enable it set the variable", ", oppure scrivi la password nel file": ", or write the password in the file",
    "della cartella dei dati (": "in the data folder (", ", predefinita": ", default", "), poi riavvia il servizio.": "), then restart the service.",
  };
  const RX = [
    [/^(\d+) file selezionati$/, "$1 files selected"],
    [/^Pagina (\d+)$/, "Page $1"], [/^Pagina (\d+) · (\d+)°$/, "Page $1 · $2°"], [/^Pagina (\d+) di (\d+)$/, "Page $1 of $2"],
    [/^(\d+) da eliminare, (\d+) restano$/, "$1 to delete, $2 left"], [/^(\d+) pagine scelte$/, "$1 pages selected"],
    [/^(\d+) pagine$/, "$1 pages"], [/^Invio al server… (.+) di (.+)$/, "Uploading… $1 of $2"], [/^Errore (\d+)$/, "Error $1"],
    [/^Da (.+) a (.+): (\d+)% più leggero\.$/, "From $1 to $2: $3% smaller."],
    [/^(.*) Una pagina era molto grande ed è stata resa a una risoluzione più bassa\.$/, "$1 One page was very large and was rendered at a lower resolution."],
    [/^(.*) (\d+) pagine erano molto grandi e sono state rese a una risoluzione più bassa\.$/, "$1 $2 pages were very large and were rendered at a lower resolution."],
    [/^Creata (.+) · ultimo uso: mai$/, "Created $1 · last used: never"], [/^Creata (.+) · ultimo uso: (.+)$/, "Created $1 · last used: $2"],
    [/^(.+) · Plico$/, m => tr(m[1]) + " · Plico"],
    [/^Plico · Chiavi API$/, "Plico · API keys"],
    [/^Scarica (\w+)$/, "Download $1"],
    [/^Cartella magica attiva: (.+), cartella "(.+)", controllo ogni (\d+) s\. Elaborati: (\d+), errori: (\d+)(.*)\.$/, 'Magic folder on: $1, folder "$2", checked every $3 s. Processed: $4, errors: $5$6.'],
  ];

  let saved = null;
  try { saved = localStorage.getItem("plico-lang"); } catch {}
  const lang = saved === "it" || saved === "en" ? saved : ((navigator.language || "en").toLowerCase().startsWith("it") ? "it" : "en");

  function tr(s) {
    if (lang === "it" || !s) return s;
    const t = s.trim();
    if (!t) return s;
    let out = EN[t];
    if (out === undefined) {
      for (const [rx, rep] of RX) {
        const m = t.match(rx);
        if (m) { out = typeof rep === "function" ? rep(m) : t.replace(rx, rep); break; }
      }
    }
    if (out === undefined) return s;
    return s.slice(0, s.indexOf(t[0])) + out + s.slice(s.lastIndexOf(t[t.length - 1]) + 1);
  }

  const ATTRS = ["placeholder", "title", "aria-label"];
  function translate(node) {
    if (node.nodeType === 3) {
      const v = tr(node.data);
      if (v !== node.data) node.data = v;
      return;
    }
    if (node.nodeType !== 1 || node.tagName === "SCRIPT" || node.tagName === "STYLE") return;
    for (const a of ATTRS) if (node.hasAttribute(a)) { const v = tr(node.getAttribute(a)); if (v !== node.getAttribute(a)) node.setAttribute(a, v); }
    for (const c of node.childNodes) translate(c);
  }

  if (lang === "en") {
    document.documentElement.lang = "en";
    new MutationObserver(list => {
      for (const m of list) {
        if (m.type === "characterData") translate(m.target);
        else if (m.type === "attributes") translate(m.target);
        else m.addedNodes.forEach(translate);
      }
    }).observe(document.documentElement, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS});
    document.addEventListener("DOMContentLoaded", () => translate(document.documentElement));
  }

  // la lingua anche nelle richieste al server, per i messaggi di errore
  const _fetch = window.fetch.bind(window);
  window.fetch = (url, opt = {}) => {
    const headers = new Headers(opt.headers || {});
    if (!headers.has("Accept-Language")) headers.set("Accept-Language", lang);
    return _fetch(url, {...opt, headers});
  };
  const _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function (body) { try { this.setRequestHeader("Accept-Language", lang); } catch {} return _send.call(this, body); };

  function set(l) { try { localStorage.setItem("plico-lang", l); } catch {} location.reload(); }

  // selettore IT / EN, in qualsiasi elemento con data-lang-switch
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-lang-switch]").forEach(el => {
      el.innerHTML = ["it", "en"].map(l => `<button type="button" data-l="${l}" class="${l === lang ? "on" : ""}" aria-pressed="${l === lang}">${l.toUpperCase()}</button>`).join("");
      el.onclick = e => { const b = e.target.closest("button"); if (b && b.dataset.l !== lang) set(b.dataset.l); };
    });
  });

  return {lang, tr, set};
})();

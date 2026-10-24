# `--png`: installazione e diagnosi di mmdc + Chromium

`--png` è **opzionale**: senza `mmdc` la skill produce Mermaid puro (`stdout`) e file `.md`.
Serve solo per consegnare un'immagine (report, Telegram, documenti).

## 1. mmdc (mermaid-cli)

```bash
PUPPETEER_SKIP_DOWNLOAD=1 npm i -g --prefix ~/.local @mermaid-js/mermaid-cli@12
ln -sf ~/.local/lib/node_modules/@mermaid-js/mermaid-cli/src/cli.js ~/bin/mmdc   # ~/bin deve essere nel PATH
mmdc --version
```

`PUPPETEER_SKIP_DOWNLOAD=1` evita il download di ~150 MB di Chromium: la skill riusa un
Chromium già presente sulla macchina.

**Pinnare la major**: la 12 ha cambiato i flag (`-w/--width` non esiste più → `--size`),
e la skill usa `--size`, `-b white`, `-q`, `-p`.

## 2. Chromium

Ordine di risoluzione usato da `scripts/gitgraph.py`:

1. `PUPPETEER_EXECUTABLE_PATH` (se impostato e il file esiste)
2. `~/.pi/agent/skills/pi-skills/browser-tools/chrome/*/chrome-linux64/chrome` (ecosistema pi)
3. `~/.cache/puppeteer/chrome/*/chrome-linux64/chrome`
4. `~/.cache/ms-playwright/chromium-*/chrome-linux/chrome`
5. `/usr/bin/chromium`, `/usr/bin/chromium-browser`, `/usr/bin/google-chrome`

Se nessuno esiste, lo script esce con `chromium non trovato: imposta PUPPETEER_EXECUTABLE_PATH`.
Nessun download automatico: la scelta è deliberata (niente ~150 MB e niente pacchetti non voluti).

## 3. Diagnosi rapida

```bash
mmdc --version
mmdc --help | grep -E -- '--size|-b,|--scale'     # i flag ci sono ancora?
python3 -c "import shutil;print(shutil.which('mmdc'))"
echo "${PUPPETEER_EXECUTABLE_PATH:-'(non impostata)'}"
```

Errore `mmdc fallito: ...` → quasi sempre Chromium sbagliato o assente: imposta
`PUPPETEER_EXECUTABLE_PATH` e riprova.

## 4. Percorsi con spazi o repo remoti

`--png` scrive dove gli dici: usa un path assoluto e verifica che la directory esista.

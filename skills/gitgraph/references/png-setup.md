# `--png`: installazione e diagnosi di mmdc + Chromium

`--png` è **opzionale**: senza `mmdc` la skill produce Mermaid puro (`stdout`) e file `.md`.
Serve solo per consegnare un'immagine (report, Telegram, documenti).

## 1. mmdc (mermaid-cli)

```bash
PUPPETEER_SKIP_DOWNLOAD=1 npm i -g --prefix ~/.local --ignore-scripts @mermaid-js/mermaid-cli@12.0.0
ln -sf ~/.local/lib/node_modules/@mermaid-js/mermaid-cli/src/cli.js ~/bin/mmdc   # ~/bin deve essere nel PATH
mmdc --version
```

`PUPPETEER_SKIP_DOWNLOAD=1` evita il download di ~150 MB di Chromium: la skill riusa un
Chromium già presente sulla macchina. `--ignore-scripts` non esegue gli script di install del
pacchetto (nessuna post-install dal registry).

**Versione esatta (`12.0.0`)**: è quella con cui è stato generato `assets/example.png`. Due 12.x
installate a distanza di mesi possono produrre render diversi, quindi `selftest.sh` confronta
`mmdc --version` con `12.0.0` e, se diversa, stampa un `WARN` su `stderr` e prosegue: il render
deve riuscire lo stesso (un confronto bloccante renderebbe il path `--png` non installabile con
altre 12.x). La 12 ha cambiato i flag (`-w/--width` non esiste più → `--size`), e la skill usa
`--size`, `-b white`, `-q`, `-p`.

Le tre leve dello script mappano cosi': `--width` → `--size` di mmdc, sfondo `-b white` (o
`#1e1e1e` con `--theme dark`); `--theme` e `--font` finiscono nel codice Mermaid (`%%{init}%%`),
non sono flag di mmdc, quindi valgono anche per l'output `.md`/stdout.

## 2. Chromium

Ordine di risoluzione usato da `scripts/gitgraph.py`:

1. `PUPPETEER_EXECUTABLE_PATH` (se impostato e il file esiste)
2. `~/.pi/agent/skills/pi-skills/browser-tools/chrome/*/chrome-linux64/chrome` (ecosistema pi)
3. `~/.cache/puppeteer/chrome/*/chrome-linux64/chrome`
4. `~/.cache/ms-playwright/chromium-*/chrome-linux/chrome`
5. `/usr/bin/chromium`, `/usr/bin/chromium-browser`, `/usr/bin/google-chrome`

Se nessuno esiste, lo script esce con `chromium non trovato: imposta PUPPETEER_EXECUTABLE_PATH`.
Nessun download automatico: la scelta è deliberata (niente ~150 MB e niente pacchetti non voluti).

## 3. Sandbox Chromium: attiva di default

Il render lancia Chromium **con la sandbox attiva**. `--no-sandbox` è un ripiego dietro un gate
esplicito, non il default:

```bash
GITGRAPH_NO_SANDBOX=1 python3 scripts/gitgraph.py <repo> --png grafo.png
```

`GITGRAPH_NO_SANDBOX=1` è l'unico nome (nessun alias) ed è **contratto utente**: passare a
Chromium `--no-sandbox --disable-setuid-sandbox`. Qualunque altro valore (compreso vuoto)
lascia la sandbox attiva. Resta un bypass **esterno** a questo gate: se nell'ambiente c'è
`PUPPETEER_DANGEROUS_NO_SANDBOX=true`, puppeteer aggiunge `--no-sandbox` da sé. In diagnosi,
quando «la sandbox risulta attiva» ma non lo è, controlla anche
`echo ${PUPPETEER_DANGEROUS_NO_SANDBOX:-unset}`.

Perché: il diagramma contiene testo preso dal repository (subject dei commit, nomi di rami e
tag), quindi in un repo clonato da terzi o in una PR da fork è contenuto influenzabile
dall'esterno. Senza sandbox un bug del renderer (font/SVG/layout, la classe di 0-day tipica di
Chromium) diventa esecuzione di codice con i privilegi dell'utente. Il flag serve solo dove la
sandbox non può partire: container/root senza user namespace
(`/proc/sys/kernel/unprivileged_userns_clone` o `/proc/sys/user/max_user_namespaces` a 0).

Verifica che la sandbox sia davvero attiva: durante il render i processi `--type=renderer` di
Chromium girano in un user namespace separato da quello della shell:

```bash
readlink /proc/self/ns/user                       # es. user:[4026531837]
readlink /proc/<pid renderer>/ns/user             # deve essere un namespace diverso
```

Su WSL2 con utente non root la sandbox funziona (verificato con Chromium 155 e mmdc 12.0.0):
il render di default resta quindi quello sandboxato, e la variabile va usata solo se il render
fallisce con un errore di sandbox. In CI il job `png` la imposta perché il runner ubuntu-latest
limita lo user namespace di Chromium.

## 4. Diagnosi rapida

```bash
mmdc --version
mmdc --help | grep -E -- '--size|-b,|--scale'     # i flag ci sono ancora?
python3 -c "import shutil;print(shutil.which('mmdc'))"
echo "${PUPPETEER_EXECUTABLE_PATH:-'(non impostata)'}"
```

Errore `mmdc fallito: ...` → quasi sempre Chromium sbagliato o assente: imposta
`PUPPETEER_EXECUTABLE_PATH` e riprova.

## 5. Percorsi con spazi o repo remoti

`--png` scrive dove gli dici: usa un path assoluto e verifica che la directory esista.

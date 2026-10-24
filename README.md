# pi-skill-gitgraph

Skill per [pi](https://pi.dev) che trasforma la storia di un repository Git in un **grafo Mermaid
`gitGraph`** con rami, fork e merge ricostruiti (non una fila indiana), più — opzionalmente — il
rendering PNG locale.

Output possibili:

| Cosa | Comando | Destinazione |
|---|---|---|
| Mermaid puro | `python3 scripts/gitgraph.py <repo>` | incollabile su <https://mermaid.live> |
| file `.md` con fence `mermaid` | `... -o grafo.md --md` | preview di VS Code (`Ctrl+Shift+V`) |
| immagine | `... --png grafo.png` | report, Telegram, documenti |

## Requirements

| Componente | Versione / note | Obbligatorio |
|---|---|---|
| `python3` | ≥ 3.8 (testato su 3.14) | sì |
| `git` | ≥ 2.20 (testato su 2.53) | sì |
| `mmdc` (`@mermaid-js/mermaid-cli`) | 12.x pinnata (testato 12.0.0) | no, solo `--png` |
| Chromium | uno qualsiasi fra i percorsi in `references/png-setup.md` | no, solo `--png` |
| `pi` | ≥ 1.4 (pacchetti `pi` + skill) | sì per l'uso come skill |

Nessuna dipendenza Python esterna: solo standard library. Nessuna chiamata di rete: tutto locale,
tranne il caso in cui **tu** decidi di incollare il grafo su mermaid.live.

## Install

Da path locale (senza copiare nulla: il pacchetto è caricato dal path):

```bash
pi install /percorso/pi-skill-gitgraph
```

Da repository Git, quando sarà pubblicato:

```bash
pi install git:github.com/Axxx75/pi-skill-gitgraph@v1.0.0
```

Verifica che il pacchetto sia dichiarato:

```bash
pi list          # deve comparire pi-skill-gitgraph
```

In alternativa, senza toccare la configurazione (una sola invocazione):

```bash
pi -e /percorso/pi-skill-gitgraph
```

La skill si attiva da sola quando la richiesta la riguarda, oppure in modo esplicito:
`/skill:gitgraph mostra la storia di ~/progetti/repo`.

### `--png` (opzionale)

```bash
PUPPETEER_SKIP_DOWNLOAD=1 npm i -g --prefix ~/.local @mermaid-js/mermaid-cli@12
ln -sf ~/.local/lib/node_modules/@mermaid-js/mermaid-cli/src/cli.js ~/bin/mmdc
```

Chromium: la skill riusa quello che trova (browser-tools di pi, cache puppeteer/playwright,
chromium di sistema) oppure quello indicato da `PUPPETEER_EXECUTABLE_PATH`.
Dettagli e diagnosi: [`skills/gitgraph/references/png-setup.md`](skills/gitgraph/references/png-setup.md).

## Verify

```bash
bash skills/gitgraph/tests/selftest.sh
```

Cosa fa: costruisce un repo usa-e-getta (ramo `feature/x`, un merge `--no-ff`, un tag), poi verifica

- prima riga = direttiva `%%{init:...}` e presenza di `gitGraph`;
- `branch feature_x` e `merge feature_x id:` presenti (slash sanificato, merge ricostruito);
- `tag: "v1"` riportato dal tag git reale;
- numero di `commit id:` esatto (5);
- `--md` apre e chiude il fence, l'output raw **non** contiene fence;
- un file che non è un repo viene rifiutato;
- `--png` produce un file non vuoto (se `mmdc` è installato, altrimenti `SKIP`).

Output atteso: `OK` e exit code 0. Qualunque altra cosa è un fallimento.

Verifica manuale su un repo vero:

```bash
python3 skills/gitgraph/scripts/gitgraph.py ~/un/repo -n 15
python3 skills/gitgraph/scripts/gitgraph.py ~/un/repo -n 15 -o /tmp/grafo.md --md
python3 skills/gitgraph/scripts/gitgraph.py ~/un/repo -n 15 --png /tmp/grafo.png
```

## Usage

| Opzione | Significato |
|---|---|
| `REPO` | path del repository (default `.`) |
| `-n N` | commit massimi, default 30 |
| `-o FILE` | scrive su file invece che su stdout |
| `--md` | avvolge l'output nel fence ```` ```mermaid ```` |
| `--png FILE` | renderizza il PNG con `mmdc` (largo 1600 px, sfondo bianco); niente stdout |
| `--linear` | fila indiana, un solo ramo: ripiego se la ricostruzione esce sbagliata |

`stdout` è Mermaid puro; i warning vanno su `stderr`.

Un merge si ricostruisce solo con **entrambi i genitori** nella finestra di commit: se `stderr`
segnala `commit fuori dalle catene principali` o `merge non ricostruiti`, rilancia con `-n` più alto.

## Troubleshooting

| Sintomo | Causa | Rimedio |
|---|---|---|
| `mmdc non trovato` | `mmdc` non nel `PATH` | vedi §Install: symlink in `~/bin` o `PATH` che include `~/.local/bin` |
| `chromium non trovato` | nessun Chromium nei percorsi noti | `export PUPPETEER_EXECUTABLE_PATH=/path/al/chrome` |
| `mmdc fallito: ...` | Chromium incompatibile o `--size` assente (major vecchia) | verifica `mmdc --version` e `mmdc --help` |
| `non e' un repository git` | path sbagliato o sottodirectory di un worktree | passa la radice del repo |
| Grafo "a fila indiana" | finestra `-n` troppo piccola, merge fuori | `-n` più alto, o `--linear` se vuoi davvero la fila |
| Repo con `main` divergente da `origin/main` | due lane: è la storia reale | nessuna azione |
| Skill `gitgraph` duplicata (pacchetto + copia in `~/.pi/agent/skills/gitgraph`) | pi carica la **prima** trovata e stampa un warning di collisione | rimuovi la copia vecchia: `pi config` → Resources |

## Privacy

Nessun dato esce dalla macchina. Attenzione solo a un caso: incollare il grafo su **mermaid.live**
manda i subject dei commit e i nomi dei rami a un servizio esterno. Per repo privati, non farlo
senza averlo chiesto al proprietario.

## Uninstall

```bash
pi remove /percorso/pi-skill-gitgraph    # o: pi remove git:github.com/Axxx75/pi-skill-gitgraph
```

Nessun file scritto fuori dal repository target e da `/tmp`: non resta niente da pulire.

## License

MIT — vedi [LICENSE](LICENSE).

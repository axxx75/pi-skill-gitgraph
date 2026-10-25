# Release notes — pi-skill-gitgraph

Formato: una sezione per versione, dalla più recente. Ogni voce = modifica testata e accettata da Axxx,
allineata su tre punti (repo locale `~/PI/repos/pi-skill-gitgraph`, checkout installato, GitHub).
Le versioni precedenti sono ricostruibili dalla storia git.

## 1.1.0 — in preparazione (non pubblicata)

- P1-03: un solo meccanismo di avanzamento in `settle()`; `deferred` è un `set` di diagnostica,
  niente doppia lista da tenere allineata. Warning dei commit persi derivato da
  `max(0, len(commits) - len(finished))`.
- P2-04: costanti nominate (`MAIN_NAMES`, `PNG_SIZE`, `LABEL_LEN_DEFAULT`) al posto dei valori
  sparsi; trunk preso dal nome reale di `HEAD` con fallback dichiarato; `--png` esclusivo con
  `-o`/`--md` e `-n < 1` rifiutato con `ap.error`; `render_png()` perde il parametro `size`,
  che nessun chiamante passava.
- P2-05: `is_worktree()` emette davvero `non e' un repository git` (su un path inesistente o un
  file l'errore grezzo di git usciva prima); doc allineata al troncamento reale (l'ellissi `…`
  sta dentro `--label-len`, non oltre); `selftest.sh` verifica il testo del messaggio, non solo
  l'exit code.
- P2-14: `-n` documentato come **finestra di ricostruzione** (perché alzarlo ricostruisce i merge e
  perché più rami = più lento); nuova sezione «Limiti noti» con bare repo rifiutati e directory di
  output non create; i casi già risolti (tag con spazio, escaping) sono scritti nella forma
  definitiva, non come limiti.
- P2-09: `selftest.sh` ora è fail-fast (`set -euo pipefail`), i file di commit usano un contatore
  deterministico (niente `date +%s%N`) e `git init -b` ha il fallback senza `-b` per git < 2.28
  (soglia dichiarata invariata a 2.20). Nuovi casi: `-n` (conteggio e rifiuto di `0`), repo a un
  commit, repo vuoto, clone `--depth 1`. README §Verify dichiara anche cosa **non** è coperto.
- P2-11: installazione di `mmdc` pinnata alla versione esatta `12.0.0` con `--ignore-scripts`
  (nessuno script di install del pacchetto) in README e `references/png-setup.md`; `selftest.sh`
  confronta `mmdc --version` con `12.0.0` e, se diversa, lo dice su stderr proseguendo: è un avviso,
  non un gate. Nessuna promessa di riproducibilità byte-per-byte dell'asset.
- P2-06: `WARN_LOST`, `WARN_DEFERRED` e `CHROME_PATTERNS` sono l'unica fonte (codice, test e doc);
  la frase contrattuale dei due warning resta identica e riceve in coda l'hint operativo
  (`-n 60` con il default 30). Il messaggio di `-o` diventa `N commit -> /path/assoluto`: conta i soli
  `commit id:` (non la direttiva `%%{init}%%` né i fence) e non usa più un path relativo.
- P2-12: `package.json` ha `repository` e `engines` (`node >= 22.19.0`, requisito del runtime pi 1.4.0,
  che copre anche mmdc 12.0.0); `docs/packages.md` di pi non prevede un campo per il requisito minimo
  di `pi`, quindi `pi >= 1.4` sta nel front-matter `compatibility` di `SKILL.md` (con python3/git/mmdc),
  ripetuto in README. Nuovo `.gitattributes`
  (`skills/gitgraph/assets/example.png binary`) e README che dichiara l'esempio un'**illustrazione,
  non un golden file**, con la ricetta esatta (mmdc 12.0.0 e Chromium non registrato).
- P2-02: Chromium gira **con la sandbox attiva**; `--no-sandbox --disable-setuid-sandbox` passano
  solo con `GITGRAPH_NO_SANDBOX=1` (unico nome, nessun alias), il ripiego per container/root senza
  user namespace. Motivazione e verifica in `references/png-setup.md` §3; il nome della variabile è
  contratto utente: non si cambia senza una release.
- P2-13: il diagramma esce con **palette ad alto contrasto** (`themeVariables`: lane ≥ 3:1 sullo
  sfondo, etichette bianche) e `showCommitLabel: true`, tema di default `neutral`; tre leve
  esplicite `--width N`, `--theme NOME`, `--font N` al posto di larghezza 1600, tema e font cablati.
  Con `--png` lo stdout è la riga `![Storia git: N commit su M rami](file.png)` da incollare nel
  documento (prima era vuoto): il passo di consegna di `SKILL.md` la richiede.
- P2-08: lo stato della lane è esplicito (`self.current` + `self.made`) invece di un dict-cella
  ereditato dal refactor da closure; `switch()` è l'unico posto che decide `branch` vs `checkout`.
  L'output resta byte-identico (verificato con `diff` su tre repo e tre finestre); la pulizia del
  `checkout` in coda resta un caso mirato, con il commento che dice dove andrebbe gestita una
  nuova direttiva Mermaid.
- P2-03: dei ref remoti si tengono solo quelli di `origin` (se esistono; senza alcun ref di
  `origin` si usano i remoti presenti): i fork/upstream non aprono più lane e i loro commit non
  entrano nella finestra
  (che ora è `git log` sui soli ref tenuti più i tag, non `--all`), quindi non finiscono appesi alla
  lane corrente. Il filtro è per nome e precede il dedup per SHA: una lista `origin` svuotata dal
  dedup (clone con `origin/main` = `main`) non fa più scattare il ripiego sui remoti. Misura su 216
  ref (6 locali, 10 origin, 200 upstream, SHA distinti, lane contate dopo il dedup): 215 → 15 lane a
  `-n 300`, ~0,06 s contro ~0,05 s su un repo a 4 ref (il vecchio costo `N rev-list` non esiste più
  dal refactor P0-04). Nella forma del fork-clone (202 ref: `main` locale, `origin/main` = `main`,
  200 upstream) la stessa finestra dà 1 commit e 0 lane upstream in ~0,05 s. Nessun `rev-list
  --stdin`: non serve. Limite e numeri dichiarati in `SKILL.md` (Limiti) e README.

### Note

- **Cambio di output dichiarato (P2-13).** Il PNG di default cambia aspetto: palette ad alto
  contrasto e tema `neutral` al posto della palette Mermaid di default su lane giallo/lime (sotto
  3:1), quindi `assets/example.png` è stato rigenerato con la stessa ricetta. Cambia anche lo stdout
  di `--png`, da vuoto alla riga alt: chi parsa lo stdout di `--png` trova quella riga, il path resta
  su `stderr` (`png -> …`). La palette sovrascrive i colori delle lane anche scegliendo `--theme`:
  il tema cambia sfondo e testi, non le tinte delle lane (sono quelle che garantiscono il contrasto).
- **Sandbox attiva di default (P2-02).** Cambia il render solo in un punto: senza
  `GITGRAPH_NO_SANDBOX=1` il `puppeteer.json` non contiene più `--no-sandbox
  --disable-setuid-sandbox`. Verificato in questo ambiente (WSL2, utente non root): il render
  funziona con la sandbox attiva e i processi `--type=renderer` girano in un user namespace
  separato; con la variabile impostata il render passa dai flag espliciti. L'asset non cambia
  (stessi pixel: il flag non tocca il layout).

- **Doc, non codice (P2-14).** Nessuna modifica di comportamento: la precedenza dei flag del
  README/SKILL è già stata riscritta in P2-04 (rifiuto di `--png` con `-o`/`--md`), qui si
  documentano `-n` e i limiti reali verificati con lo script.
- **Messaggio raggiungibile (P2-05).** Un path inesistente, un file o un bare repo ora escono con
  `non e' un repository git` (exit 1, invariato), non più con `git rev-parse ...: fatal: ...`.
  Il contratto di `--label-len` è "N caratteri, ellissi compresa": il vecchio `32 + "..." = 35`
  non esiste più da quando `label()` tronca dentro il limite, e README/SKILL lo dicono così.
- **Cambio di comportamento (P2-04).** `--png` insieme a `-o` oppure a `--md` ora è un errore
  (`ap.error`, exit 2, nessun file scritto) invece dello scarto silenzioso di `-o`/`--md`; `-n < 1`
  risponde `serve -n >= 1` invece del fuorviante `nessun commit trovato`. `-o` con `--md` resta
  valido. La lane di partenza prende il nome reale di HEAD quando nessun tip rivendica la radice
  della finestra (fallback `main` solo se HEAD non risolve o è detached): su un trunk `develop`
  non compare più `mainBranchName: main` per un ramo inesistente. Se HEAD è su un ramo di feature
  e la radice è fuori dalla finestra `-n`, la lane di partenza porta il nome di quel ramo.

- **Cambio semantico dichiarato (P1-03).** Il passaggio di `deferred` da lista a `set` deduplica:
  un commit con lo stesso genitore ripetuto (es. `c00 -> c02, c02`, quindi due volte in
  `children[c02]`) non produce più il falso `warning: 1 merge non ricostruiti`. Il caso **non è
  creabile con git normale** (`git commit-tree -p X -p X` scarta il parent duplicato) ed è
  raggiungibile solo leggendo un repo con `.git/info/grafts`; lo stdout resta invariato.
  Il vecchio warning era un artefatto del doppio accumulator, quindi il nuovo comportamento è
  quello corretto.

## 1.0.2 — 2026-10-25

- Fix `--linear`: nessun header Mermaid quando il grafo è lineare.
- Fix `HEAD` unborn/dangling: `git()` non termina più con exit 1 (`strict=False` + fallback), caso coperto nel selftest.

## 1.0.0

- Release iniziale.

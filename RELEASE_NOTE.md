# Release notes — pi-skill-gitgraph

Formato: una sezione per versione, dalla più recente. Ogni voce = modifica testata e accettata da Axxx,
allineata su tre punti (repo locale `~/PI/repos/pi-skill-gitgraph`, checkout installato, GitHub).
Le versioni precedenti sono ricostruibili dalla storia git.

## 1.1.0 — in preparazione (non pubblicata)

- P1-03: un solo meccanismo di avanzamento in `settle()`; `deferred` è un `set` di diagnostica,
  niente doppia lista da tenere allineata. Warning dei commit persi derivato da
  `max(0, len(commits) - len(finished))`.

### Note

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

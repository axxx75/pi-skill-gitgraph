# ADR 0004 — Finestra del grafo = rami locali + `origin` + tag

- **Stato:** accettata
- **Data:** 2026-10-25

## Contesto

La finestra `-n` leggeva `git log --all`: entravano i commit raggiungibili solo dai ref di
fork/upstream, che non hanno una lane propria e finivano appesi alla lane corrente. Su un repo con
molti remoti (200 ref upstream) le lane esplodevano e il grafo diventava inutilizzabile, senza che
`-n` aiutasse (`#TASK-P2-03`).

## Decisione

La finestra sono i **soli ref tenuti**: rami locali + `origin` (se non esiste alcun ref di `origin`
si usano i remoti presenti), più i tag (`git log … --tags`). La scelta del set viene prima del dedup
per SHA; l'ordine dei tip resta per data di commit, con i nomi di trunk (`MAIN_NAMES`) per primi.

## Conseguenze

- Fork/upstream non aprono lane e i loro commit restano fuori dal grafo, senza bisogno di un flag:
  per vederli si rinomina quel remoto in `origin` (limite dichiarato in README/SKILL).
- Un commit raggiungibile solo da un tag resta nella finestra: i tag sono ref legittimi, non lane.
- Il dedup per SHA vale solo sul set scelto, quindi `origin/main` = `main` non fa scattare il
  ripiego sui remoti e un ref di fork con lo stesso SHA non può scartare quello di `origin`.
- `-n` è documentato come **finestra di ricostruzione** (alzarla fa rientrare i genitori dei merge),
  non come tetto di commit: il costo è O(ref) in due `for-each-ref` più il walk dei tip.

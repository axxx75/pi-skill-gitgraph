# ADR 0001 — Escaping Mermaid in un unico punto

- **Stato:** accettata
- **Data:** 2026-10-25

## Contesto

I testi che finiscono nel diagramma vengono da git (subject dei commit, nomi dei tag): sono input
influenzabile dall'esterno. `"`, `\`, `#`, backtick e caratteri di controllo rompevano il parser di
Mermaid con un errore che non nominava il commit, quindi il grafo diventava illeggibile su repo
reali (finding di robustezza, `#TASK-P2-01`, commit `8867717`, non rilasciato: 1.1.0 in preparazione).

## Decisione

Un solo punto di escaping: `escape()` in `scripts/gitgraph.py`, applicato da `label()`, l'unica via
per cui passa il testo preso da git. I nomi dei rami non ne hanno bisogno perché `slug()` li riduce
a `[A-Za-z0-9_-]`; gli hash sono esadecimali.

## Conseguenze

- Il grafo resta renderizzabile anche con subject ostili: `"`→`'`, `\`→`#92;`, `#`→`#35;`,
  `` ` ``→`#96;`, non stampabili→`#65533;`; i casi sono nel selftest e nei test unitari.
- L'escaping **allunga** la stringa: `--label-len` conta i caratteri del soggetto, non quelli
  dell'etichetta resa (dichiarato in README/SKILL).
- Un nuovo campo preso da git deve passare da `label()`/`escape()`; non si aggiungono escape locali
  altrove (né nel render né nel PNG).

# ADR 0005 — Warning su stderr come contratto macchina

- **Stato:** accettata
- **Data:** 2026-10-25

## Contesto

La skill reagisce ai due warning su stderr (`commit fuori dalle catene principali`, `merge non
ricostruiti`) per decidere se rilanciare con `-n` più alto: sono l'unico segnale di grafo
incompleto. Le frasi erano costruite a mano in più punti e potevano cambiare senza che nessuno se ne
accorgesse, rompendo la skill in silenzio (`#TASK-P2-06`, commit `f824f7f`, non rilasciato: 1.1.0 in preparazione).

## Decisione

I warning sono contratto macchina: la frase resta **invariata**, l'hint operativo (la finestra
suggerita, es. `-n 60` con il default 30) si accoda **dopo**. `WARN_LOST` e `WARN_DEFERRED` in
`scripts/gitgraph.py` sono l'unica fonte; test e documentazione le ripetono senza riscriverle.
`stdout` resta Mermaid puro (con `--png` la sola riga alt): la diagnostica va su stderr.

## Conseguenze

- Cambiare la frase è un breaking change per la skill: richiede una release e l'allineamento di
  `SKILL.md`, README e selftest (che la verifica carattere per carattere). L'hint invece è libero di
  cambiare perché viene dopo la frase.
- Anche i messaggi di successo/diagnostica (`N commit -> /path`, `png -> …`, `directory
  inesistente`) restano su stderr: chi parsa stdout non deve gestire eccezioni.
- Nulla di ciò che riguarda il grafo può sparire in silenzio: i buchi diventano warning, non commit
  persi senza traccia.

# ADR 0003 — Sandbox Chromium attiva di default, gate `GITGRAPH_NO_SANDBOX=1`

- **Stato:** accettata
- **Data:** 2026-10-25

## Contesto

Il PNG passa da `mmdc`, che usa Chromium. Il diagramma contiene subject e nomi di ramo presi dal
repo: su un repo di terzi è input influenzabile dall'esterno. Il render girava con `--no-sandbox
--disable-setuid-sandbox` sempre, per comodità (container/root senza user namespace), cioè
disattivava la sandbox anche dove funzionava (`#TASK-P2-02`).

## Decisione

Sandbox **attiva** di default. I flag che la disattivano passano solo con `GITGRAPH_NO_SANDBOX=1`,
unico nome, nessun alias: il ripiego è esplicito e si vede nella configurazione passata a `mmdc`.

## Conseguenze

- Dove lo user namespace è limitato il render fallisce finché non si imposta il gate: è il caso del
  runner `ubuntu-latest` (il job `png` della CI lo imposta come configurazione corretta) e di
  container/root. Il selftest prova entrambi i rami (default e gate).
- Il nome della variabile è contratto utente: non si cambia senza una release. Diagnosi in
  `references/png-setup.md` §3.
- Non tocca il layout: i pixel del PNG restano gli stessi, cambia solo chi può leggere il filesystem
  durante il render.

# Release notes — pi-skill-gitgraph

Formato: una sezione per versione, dalla più recente. Ogni voce = modifica testata e accettata da Axxx,
allineata su tre punti (repo locale `~/PI/repos/pi-skill-gitgraph`, checkout installato, GitHub).
Le versioni precedenti sono ricostruibili dalla storia git.

## 1.0.2 — 2026-10-25

- Fix `--linear`: nessun header Mermaid quando il grafo è lineare.
- Fix `HEAD` unborn/dangling: `git()` non termina più con exit 1 (`strict=False` + fallback), caso coperto nel selftest.

## 1.0.0

- Release iniziale.

---
name: gitgraph
description: "Genera la storia di un repository Git come grafo Mermaid gitGraph (rami, fork e merge ricostruiti, non fila indiana) in un file .md per la preview di VS Code o da incollare su mermaid.live. Usa quando l'utente chiede di vedere o visualizzare la storia, il grafo o l'albero dei commit di un repo, o quando nomina gitGraph / mermaid e git."
license: MIT
compatibility: "python3 >= 3.8, git >= 2.20; mmdc + Chromium solo per --png"
---

# gitGraph — storia git come grafo Mermaid

Produce il codice Mermaid e, con `--png`, il rendering locale. Tre destinazioni: PNG (consegna rapida, Telegram, report), file `.md` con `--md` (preview di VS Code), testo puro da incollare su <https://mermaid.live> (condivisione). Tutto locale tranne mermaid.live.

## Uso

```bash
python3 {baseDir}/scripts/gitgraph.py [REPO] [-n 30] [-o FILE] [--md] [--png FILE] [--linear] [--label-len N]
```

| Opzione | Significato |
|---|---|
| `REPO` | path del repository, default `.` |
| `-n N` | commit massimi, default 30 (oltre il grafo diventa illeggibile) |
| `-o FILE` | scrive su file invece che su stdout |
| `--md` | avvolge l'output nel fence ```` ```mermaid ````: `-o grafo.md` è pronto per la preview |
| `--png FILE` | renderizza il PNG con `mmdc` (largo 1600px, sfondo bianco); niente stdout |
| `--linear` | fila indiana, un solo ramo: ripiego se la ricostruzione esce sbagliata |
| `--label-len N` | caratteri massimi per etichetta, troncata a confine di parola con `…` (default 32; `0` = soggetto intero, 10-12 per grafi stretti) |

stdout è Mermaid puro; con `--md` è un blocco fences; con `--png` lo stdout resta vuoto. Warning e diagnostica vanno su stderr. `--png` richiede `mmdc` e un Chromium: installazione e diagnosi in `references/png-setup.md`.

## Passi

1. Esegui lo script col **path assoluto** del repo e `-n` adeguato (30 è il default; 10-15 se serve un grafo stretto).
   Fatto quando: stdout contiene `gitGraph` e almeno un `commit id:` (e nessun warning su stderr).
2. Se stderr riporta `commit fuori dalle catene principali` o `merge non ricostruiti`: un merge si ricostruisce solo con entrambi i genitori nella finestra → riprova con `-n` più alto; se il repo è troppo grande per un grafo leggibile, consegna il risultato dicendo quali rami mancano.
3. Consegna: `--png <path>` se serve un'immagine (Telegram, report, doc), `-o <repo>-history.md --md` per la preview in VS Code (`Ctrl+Shift+V`), testo + link a mermaid.live se l'utente vuole condividerlo. Non incollare tu nulla su servizi esterni e non inventare path: dì dove hai scritto.

## Cosa ricostruisce

- Una lane per ramo locale o remoto distinto, aperta al fork point reale (first-parent), chiusa con `merge <ramo> id: "<hash>"`.
- Catene laterali senza ref (tipiche dei merge PR): lane sintetica `merge_<hash>`.
- `tag:` = tag git reale se il commit ne ha uno (con più tag: il primo più `+N`, mai un tag spezzato), altrimenti subject troncato a `--label-len` caratteri (default 32) a confine di parola con `…`.
- Nomi ramo sanificati per Mermaid: `feature/x` → `feature_x`.

## Limiti

- `--png` dipende da `mmdc` e da un Chromium: se manca un pezzo lo script esce con il messaggio giusto (installazione e diagnosi in `references/png-setup.md`).
- Nessuna pagina pubblicata: il rendering lo fa `mmdc` in locale, la preview di VS Code (estensione Mermaid Chart, richiede workspace trusted) o mermaid.live.
- Nessun file `.md` viene scritto senza `-o`: l'agente sceglie il path e lo dice all'utente.
- Fila indiana con `--linear` o quando la finestra taglia i genitori di un merge.
- Repo divergenti (locale `main` indietro rispetto a `origin/main`) producono due lane: è la storia reale, non un errore.

## Privacy

mermaid.live è un servizio esterno: incollando il grafo i subject dei commit (e i nomi dei rami) gli vengono inviati. Per repo privati o con dati sensibili, avvisa l'utente prima di proporre l'incollaggio.

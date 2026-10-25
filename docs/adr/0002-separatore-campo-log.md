# ADR 0002 — Separatore di campo `\x1f` nel parsing del log

- **Stato:** accettata
- **Data:** 2026-10-25

## Contesto

Il log di git era letto con un separatore visibile (`|`) e con `split()` posizionale. Un subject
che conteneva `|` spostava i campi (commit fuori posto o eccezione), un separatore di riga Unicode
(U+2028 e simili) spezzava un commit in due perché `splitlines()` divide anche lì, e una riga
malformata faceva esplodere l'unpacking (`#TASK-P2-07`).

## Decisione

Formato del log con un separatore di controllo che non ha significato nel testo:
`--pretty=format:%h\x1f%H\x1f%P\x1f%s` (`SEP = "\x1f"`), letto con `split(SEP, 3)` e righe divise
su `"\n"` (non `splitlines()`). Una riga con meno di 3 `SEP` è un errore leggibile
(`log git non interpretabile: …`), un campo in più resta nel subject.

## Conseguenze

- `|` torna un carattere legittimo di un subject, e un subject non può più troncare il commit.
- Un formato inatteso è un errore dichiarato (exit 1), non un traceback né un commit silenziosamente
  perso; il parser dei tag segue la stessa regola (`tag non interpretabile`).
- I test unitari fissano il formato con un fake di `git()` che produce lo stesso `SEP`: cambiare il
  formato richiede di aggiornare le fixture, non di allentare le asserzioni.

#!/usr/bin/env bash
# Self-check: costruisce un repo usa-e-getta e verifica rami e merge nell'output.
set -u
here=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

cd "$tmp" || exit 1
git init -q -b main
git config user.email t@t.t; git config user.name t
c(){ echo "$1" > "f$(date +%s%N).txt"; git add -A; git commit -qm "$1"; }
c A; c B; git tag v1
git checkout -qb feature/x; c C; c D
git checkout -q main; git merge -q --no-ff "feature/x" -m M; c E

out=$(python3 "$here/scripts/gitgraph.py" .) || { echo "FAIL: exit non-zero"; exit 1; }
fail=0
grep -qx 'gitGraph' <<<"$out" || { echo "FAIL: manca gitGraph"; fail=1; }
# HEAD di riga = prima riga della direttiva init (stdout = mermaid puro)
case "$(head -1 <<<"$out")" in
  '%%{init:'*) ;;
  *) echo "FAIL: prima riga non e' la direttiva init"; fail=1 ;;
esac
grep -qx '    branch feature_x' <<<"$out" || { echo "FAIL: manca branch feature_x"; fail=1; }
grep -q '    merge feature_x id: ' <<<"$out" || { echo "FAIL: manca merge feature_x"; fail=1; }
grep -q 'tag: "v1"' <<<"$out" || { echo "FAIL: tag git non riportato"; fail=1; }
[ "$(grep -c 'commit id:' <<<"$out")" -eq 5 ] || { echo "FAIL: numero commit errato"; fail=1; }
grep -q '```' <<<"$out" && { echo "FAIL: fence mermaid nell'output raw"; fail=1; }

# --linear: deve restare un diagramma mermaid valido (init + gitGraph + commit)
lin=$(python3 "$here/scripts/gitgraph.py" . --linear) || { echo "FAIL: --linear exit non-zero"; exit 1; }
case "$(head -1 <<<"$lin")" in
  '%%{init:'*) ;;
  *) echo "FAIL: --linear, prima riga non e' la direttiva init"; fail=1 ;;
esac
grep -qx 'gitGraph' <<<"$lin" || { echo "FAIL: --linear, manca gitGraph"; fail=1; }
grep -q 'commit id:' <<<"$lin" || { echo "FAIL: --linear, nessun commit"; fail=1; }
# --linear con HEAD non risolto (ref puntato ma mai committato): deve restare exit 0
ub="$tmp/ub"; mkdir "$ub"; git -C "$ub" init -q -b main
ubg(){ git -C "$ub" -c user.email=t@t.t -c user.name=t "$@"; }
ubg checkout -qb feature/x; echo u > "$ub/f.txt"; ubg add -A; ubg commit -qm U
ubg symbolic-ref HEAD refs/heads/main
lin=$(python3 "$here/scripts/gitgraph.py" "$ub" --linear) || { echo "FAIL: --linear su HEAD non risolto exit non-zero"; fail=1; }
case "$(head -1 <<<"$lin")" in
  '%%{init:'*) ;;
  *) echo "FAIL: --linear HEAD non risolto, prima riga non e' la direttiva init"; fail=1 ;;
esac
grep -qx 'gitGraph' <<<"$lin" || { echo "FAIL: --linear HEAD non risolto, manca gitGraph"; fail=1; }
grep -q 'commit id:' <<<"$lin" || { echo "FAIL: --linear HEAD non risolto, nessun commit"; fail=1; }

md=$(python3 "$here/scripts/gitgraph.py" . --md) || { echo "FAIL: --md exit non-zero"; exit 1; }
head -1 <<<"$md" | grep -qx '```mermaid' || { echo "FAIL: --md non apre il fence"; fail=1; }
tail -1 <<<"$md" | grep -qx '```' || { echo "FAIL: --md non chiude il fence"; fail=1; }

# path non-repo: deve arrivare il messaggio documentato (non l'errore grezzo di git), con exit 1
printf 'non sono un repo\n' > "$tmp/f.txt"
git init -q --bare "$tmp/bare"
for bad in "$tmp/f.txt" "$tmp/manca" "$tmp/bare"; do
  err=$(python3 "$here/scripts/gitgraph.py" "$bad" 2>&1 >/dev/null); rc=$?
  [ "$rc" -eq 1 ] || { echo "FAIL: $bad, exit $rc (atteso 1)"; fail=1; }
  grep -q "non e' un repository git" <<<"$err" \
    || { echo "FAIL: $bad, messaggio non-repo assente: $err"; fail=1; }
done

# -o: parita' byte-identica con stdout, nessun .tmp orfano, path invalido = una riga su stderr
o=$(python3 "$here/scripts/gitgraph.py" .) || { echo "FAIL: stdout exit non-zero"; exit 1; }
python3 "$here/scripts/gitgraph.py" . -o "$tmp/out.mmd" 2>/dev/null || { echo "FAIL: -o exit non-zero"; exit 1; }
cmp -s "$tmp/out.mmd" <(printf '%s\n' "$o") || { echo "FAIL: -o diverso da stdout"; fail=1; }
[ ! -e "$tmp/out.mmd.tmp" ] || { echo "FAIL: .tmp orfano dopo -o"; fail=1; }
err=$(python3 "$here/scripts/gitgraph.py" . -o "$tmp/manca/out.mmd" 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: -o su directory inesistente, exit $rc"; fail=1; }
[ "$(grep -c . <<<"$err")" -eq 1 ] || { echo "FAIL: -o su path invalido, messaggio non di una riga: $err"; fail=1; }
grep -q 'directory inesistente' <<<"$err" || { echo "FAIL: -o su path invalido, messaggio inatteso: $err"; fail=1; }

# collisione di nomi sanificati: feature/x e feature_x sono due rami, non una lane
col="$tmp/col"; git init -q -b main "$col"
cg(){ git -C "$col" -c user.email=t@t.t -c user.name=t "$@"; }
cc(){ echo "$1" > "$col/f-$1.txt"; cg add -A; cg commit -qm "$1"; }
cc A; cc B
cg checkout -qb feature/x; cc C
cg checkout -q main; cg checkout -qb feature_x; cc D
cg checkout -q main; cg merge -q --no-ff feature/x -m MX
cg merge -q --no-ff feature_x -m MY; cc E
cout=$(python3 "$here/scripts/gitgraph.py" "$col" 2>"$tmp/col.err") || { echo "FAIL: collisione, exit non-zero"; exit 1; }
grep -qx '    branch feature_x' <<<"$cout" || { echo "FAIL: collisione, manca branch feature_x"; fail=1; }
grep -qx '    branch feature_x_2' <<<"$cout" || { echo "FAIL: collisione, manca branch feature_x_2"; fail=1; }
grep -q '    merge feature_x id: ' <<<"$cout" || { echo "FAIL: collisione, manca merge feature_x"; fail=1; }
grep -q '    merge feature_x_2 id: ' <<<"$cout" || { echo "FAIL: collisione, manca merge feature_x_2"; fail=1; }
grep -q 'warning: ramo "feature[/_]x": "feature_x"' "$tmp/col.err" \
  || { echo "FAIL: collisione, nessun warning su stderr"; fail=1; }
[ "$(grep -c 'commit id:\|merge .* id:' <<<"$cout")" -eq 7 ] \
  || { echo "FAIL: collisione, commit persi"; fail=1; }

# etichette: troncatura a confine di parola, --label-len, multi-tag mai spezzato
cat > "$tmp/maxlabel.py" <<'PY'
import sys
limit, bad = int(sys.argv[1]), False
for line in sys.stdin:
    if ' tag: "' not in line:
        continue
    text = line.partition(' tag: "')[2].rstrip().rstrip('"')
    bad = bad or len(text.rsplit(" +", 1)[0]) > limit
sys.exit(1 if bad else 0)
PY
lab="$tmp/lab"; git init -q -b main "$lab"
lg(){ git -C "$lab" -c user.email=t@t.t -c user.name=t "$@"; }
lc(){ echo "$1" > "$lab/f$(date +%s%N).txt"; lg add -A; lg commit -qm "$1"; }
lc "feat: configurazione molto lunga delle etichette nei diagrammi"
lc "secondo commit con soggetto breve"
lg tag t1; lg tag t2; lg tag t3
lout=$(python3 "$here/scripts/gitgraph.py" "$lab") || { echo "FAIL: etichette, exit non-zero"; exit 1; }
grep -q 'tag: "feat: configurazione molto…"' <<<"$lout" \
  || { echo "FAIL: troncatura non a confine di parola con ellissi"; fail=1; }
python3 "$tmp/maxlabel.py" 32 <<<"$lout" \
  || { echo "FAIL: etichetta oltre 32 caratteri"; fail=1; }
grep -q 'tag: "t1 +2"' <<<"$lout" || { echo "FAIL: multi-tag non annotato '+2'"; fail=1; }
grep -q 'tag: "t[23]' <<<"$lout" && { echo "FAIL: secondo tag troncato o ripetuto"; fail=1; }
lout0=$(python3 "$here/scripts/gitgraph.py" "$lab" --label-len 0) \
  || { echo "FAIL: --label-len 0 exit non-zero"; exit 1; }
grep -q 'tag: "feat: configurazione molto lunga delle etichette nei diagrammi"' <<<"$lout0" \
  || { echo "FAIL: --label-len 0 non tiene il soggetto intero"; fail=1; }
lout12=$(python3 "$here/scripts/gitgraph.py" "$lab" --label-len 12) \
  || { echo "FAIL: --label-len 12 exit non-zero"; exit 1; }
grep -q 'tag: "feat: confi…"' <<<"$lout12" || { echo "FAIL: --label-len 12 non tronca"; fail=1; }
python3 "$tmp/maxlabel.py" 12 <<<"$lout12" \
  || { echo "FAIL: --label-len 12, etichetta oltre 12 caratteri"; fail=1; }

# soggetto convenzionale reale: la troncatura non deve collassare il testo utile
conv="$tmp/conv"; git init -q -b main "$conv"
vg(){ git -C "$conv" -c user.email=t@t.t -c user.name=t "$@"; }
echo v > "$conv/f.txt"; vg add -A; vg commit -qm "feat: add-idempotency-key-rotation"
vout=$(python3 "$here/scripts/gitgraph.py" "$conv") || { echo "FAIL: soggetto convenzionale, exit non-zero"; exit 1; }
vl=$(sed -n 's/.* tag: "\(.*\)"/\1/p' <<<"$vout")
python3 - "$vl" <<'PY' || fail=1
import sys
s = sys.argv[1]
if not s.endswith("…") or len(s) < 16:
    sys.exit(f"FAIL: etichetta collassata ({len(s)} caratteri): {s!r}")
if "add-idempotency" not in s:
    sys.exit(f"FAIL: caratteri distintivi persi: {s!r}")
PY

# escaping Mermaid: '#', '\', backtick e caratteri di controllo non rompono la stringa
# "…" (appsec CWE-116/CWE-79, ux-perf finding 4: senza escape il render e' corrotto)
esc="$tmp/esc"; git init -q -b main "$esc"
eg(){ git -C "$esc" -c user.email=t@t.t -c user.name=t "$@"; }
printf 'e\n' > "$esc/f1.txt"; eg add -A; eg commit -qm 'foo"bar\baz'
printf 'e\n' > "$esc/f2.txt"; eg add -A; eg commit -qm "$(printf 'fix #12 e `code`\001 con controllo')"
printf 'e\n' > "$esc/f3.txt"; eg add -A; eg commit -qm 'ultimo'
eg tag 'v1#2'
eout=$(python3 "$here/scripts/gitgraph.py" "$esc") || { echo "FAIL: escaping, exit non-zero"; exit 1; }
grep -q 'tag: "foo'\''bar#92;baz"' <<<"$eout" \
  || { echo "FAIL: escaping, backslash o doppio apice non neutralizzati"; fail=1; }
grep -q 'tag: "fix #35;12 e #96;code#96;#65533; con controllo"' <<<"$eout" \
  || { echo "FAIL: escaping, '#', backtick o carattere di controllo non neutralizzati"; fail=1; }
grep -q 'tag: "v1#35;2"' <<<"$eout" || { echo "FAIL: escaping, '#' nel nome tag non neutralizzato"; fail=1; }

# parsing: un subject con '|' non deve confondere il log (separatore di campo esplicito)
pip="$tmp/pip"; git init -q -b main "$pip"
pg(){ git -C "$pip" -c user.email=t@t.t -c user.name=t "$@"; }
printf 'p\n' > "$pip/f1.txt"; pg add -A; pg commit -qm 'fix | tabella | riga'
pout=$(python3 "$here/scripts/gitgraph.py" "$pip") || { echo "FAIL: subject con '|', exit non-zero"; exit 1; }
grep -q 'tag: "fix | tabella | riga"' <<<"$pout" \
  || { echo "FAIL: subject con '|' non conservato"; fail=1; }

# tag con spazio: git non lo permette (check-ref-format), quindi il parser si prova diretto
python3 - "$here/scripts" <<'PY' || fail=1
import sys
sys.path.insert(0, sys.argv[1])
import gitgraph

SEP = "\x1f"   # = gitgraph.SEP: il formato del log mockato deve essere quello reale

def fake(repo, *args, strict=True):
    if "rev-parse" in args:
        return "true\n"
    if "log" in args:
        return f"a1{SEP}A1{SEP}{SEP}soggetto\n"
    if "refs/tags" in args:
        return "commit release 1.0 A1 A1\n"   # 5 campi: nome tag con spazio
    return "refs/heads/main a1 \n" if "refs/heads/" in args else ""

gitgraph.git = fake
try:
    gitgraph.read_graph(".", 10)
except gitgraph.GitError as e:
    if "tag non interpretabile" not in str(e):
        sys.exit(f"FAIL: tag con spazio, messaggio inatteso: {e}")
else:
    sys.exit("FAIL: tag con spazio accettato in silenzio (nessun errore leggibile)")
PY

if command -v mmdc >/dev/null; then
  python3 "$here/scripts/gitgraph.py" . --png "$tmp/out.png" 2>/dev/null
  [ -s "$tmp/out.png" ] || { echo "FAIL: --png non produce il file"; fail=1; }
  # il path invalido deve dirlo subito, non travestirsi da "mmdc fallito"
  err=$(python3 "$here/scripts/gitgraph.py" . --png "$tmp/manca/out.png" 2>&1 >/dev/null)
  [ "$(grep -c . <<<"$err")" -eq 1 ] \
    || { echo "FAIL: --png su path invalido, messaggio non di una riga: $err"; fail=1; }
  grep -q 'directory inesistente' <<<"$err" \
    || { echo "FAIL: --png su path invalido maschera l'errore: $err"; fail=1; }
else
  echo "SKIP: mmdc assente, test PNG non eseguito"
fi

# unit test della logica pura (render) e degli errori tipizzati
if ! python3 -m unittest discover -s "$here/tests" -p 'test_*.py' -q \
     >"$tmp/unit.log" 2>&1; then
  echo "FAIL: unit test"; cat "$tmp/unit.log"; fail=1
fi

[ "$fail" -eq 0 ] && echo "OK"
exit "$fail"

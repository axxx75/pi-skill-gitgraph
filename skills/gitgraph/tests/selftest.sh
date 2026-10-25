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

python3 "$here/scripts/gitgraph.py" "$tmp/f.txt" >/dev/null 2>&1 && { echo "FAIL: file non-repo accettato"; fail=1; }

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

if command -v mmdc >/dev/null; then
  python3 "$here/scripts/gitgraph.py" . --png "$tmp/out.png" 2>/dev/null
  [ -s "$tmp/out.png" ] || { echo "FAIL: --png non produce il file"; fail=1; }
else
  echo "SKIP: mmdc assente, test PNG non eseguito"
fi

[ "$fail" -eq 0 ] && echo "OK"
exit "$fail"

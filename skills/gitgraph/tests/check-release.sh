#!/usr/bin/env bash
# Gate di release: package.json.version <-> tag git locale <-> voce in RELEASE_NOTE.md.
# Offline: solo i tag del checkout (nessuna rete, nessun git ls-remote). Exit 0 anche con
# SKIP (checkout senza tag: fetch-depth 1, tarball), non-zero solo su incoerenza.
# Nel flusso di release si lancia DOPO il tag (README §Release): tra il bump di
# package.json e il tag la versione non ha ancora un tag, quindi il check fallisce.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' \
          "$root/package.json")

# .git e' una directory in un clone ma un file in un worktree: chiedilo a git
git -C "$root" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "SKIP: $root non e' un checkout git"; exit 0; }
[ -n "$(git -C "$root" tag -l)" ] \
  || { echo "SKIP: nessun tag locale (clone shallow/tarball: git fetch --tags)"; exit 0; }

tag="v$version"
fail=0

if ! git -C "$root" rev-parse -q --verify "refs/tags/$tag^{commit}" >/dev/null; then
  echo "FAIL: package.json version $version senza tag $tag (git tag $tag)" >&2
  fail=1
elif ! git -C "$root" merge-base --is-ancestor "refs/tags/$tag^{commit}" HEAD; then
  echo "FAIL: il tag $tag non e' nella storia di HEAD: versione non rilasciata su questo ramo" >&2
  fail=1
fi

# la voce della versione corrente nel registro: '## X.Y.Z' seguito da spazio o fine riga
re=$(printf '%s' "$version" | sed 's/[.[\*^$]/\\&/g')
grep -qE "^## $re([[:space:]]|$)" "$root/RELEASE_NOTE.md" \
  || { echo "FAIL: RELEASE_NOTE.md senza la voce '## $version'" >&2; fail=1; }

if [ "$fail" -eq 0 ]; then
  echo "OK: $version = $tag, voce in RELEASE_NOTE.md"
fi
exit "$fail"

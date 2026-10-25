#!/usr/bin/env python3
"""Storia git -> Mermaid gitGraph (stdout, da incollare su https://mermaid.live)."""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

MAX_SUBJECT = 32


def git(repo, *args, strict=True):
    r = subprocess.run(["git", "-C", repo, *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 and strict:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def slug(branch):
    # mermaid vuole nomi ramo senza spazi: slash e simili diventano underscore
    return re.sub(r"[^A-Za-z0-9_-]", "_", branch) or "branch"


def label(text):
    text = " ".join(text.replace('"', "'").split())
    return text[:MAX_SUBJECT] + "..." if len(text) > MAX_SUBJECT else text


def branch_tips(repo):
    """(ref, commit) dei rami, senza duplicati: un ramo locale vince sul remoto omonimo."""
    tips, seen = [], set()
    for ns in ("refs/heads/", "refs/remotes/"):
        raw = git(repo, "for-each-ref", "--sort=-committerdate",
                  "--format=%(refname) %(objectname) %(symref)", ns)
        for line in raw.splitlines():
            ref, _, rest = line.partition(" ")
            sha, _, symref = rest.partition(" ")
            if not sha or symref.strip() or sha in seen:
                continue
            seen.add(sha)
            tips.append((ref[len(ns):], sha))
    # il ramo principale rivendica per primo la sua catena first-parent
    return sorted(tips, key=lambda t: t[0] not in ("main", "master"))


def chrome_bin():
    """Chromium gia' presente: mmdc non deve scaricarne uno suo."""
    env = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if env and os.path.exists(env):
        return env
    # in ordine: browser-tools dell'ecosistema pi, cache puppeteer/playwright, chromium di sistema
    patterns = [
        "~/.pi/agent/skills/pi-skills/browser-tools/chrome/*/chrome-linux64/chrome",
        "~/.cache/puppeteer/chrome/*/chrome-linux64/chrome",
        "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return None


def render_png(mermaid, out, size=1600):
    mmdc = shutil.which("mmdc")
    if not mmdc:
        sys.exit("mmdc non trovato (npm i -g @mermaid-js/mermaid-cli): vedi README.md, sezione «--png»")
    chrome = chrome_bin()
    if not chrome:
        sys.exit("chromium non trovato: imposta PUPPETEER_EXECUTABLE_PATH")
    with tempfile.TemporaryDirectory() as tmp:
        src, cfg = os.path.join(tmp, "in.mmd"), os.path.join(tmp, "puppeteer.json")
        with open(src, "w", encoding="utf-8") as f:
            f.write(mermaid)
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"executablePath": chrome,
                       "args": ["--no-sandbox", "--disable-setuid-sandbox"]}, f)
        r = subprocess.run([mmdc, "-i", src, "-o", out, "-p", cfg,
                            "--size", str(size), "-b", "white", "-q"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            sys.exit(f"mmdc fallito: {r.stderr.strip() or r.stdout.strip()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", nargs="?", default=".", help="path del repository")
    ap.add_argument("-n", type=int, default=30, help="numero massimo di commit (default 30)")
    ap.add_argument("-o", metavar="FILE", help="scrive su file invece che su stdout")
    ap.add_argument("--png", metavar="FILE",
                    help="renderizza un PNG con mmdc (chromium gia' presente, nessun download)")
    ap.add_argument("--md", action="store_true",
                    help="avvolge l'output in un fence ```mermaid (file .md per la preview)")
    ap.add_argument("--linear", action="store_true",
                    help="fila indiana: un solo ramo, nessuna ricostruzione dei merge")
    a = ap.parse_args()

    if git(a.repo, "rev-parse", "--is-inside-work-tree").strip() != "true":
        sys.exit(f"{a.repo}: non e' un repository git")

    # commit -> ([parents], subject), dal piu' recente al piu' vecchio
    log = git(a.repo, "log", "--all", "--topo-order", f"-n{a.n}",
              "--pretty=format:%h|%H|%P|%s")
    short, commits = {}, {}
    for line in log.splitlines():
        h, _, rest = line.partition("|")
        full, _, rest = rest.partition("|")
        parents, _, subject = rest.partition("|")
        short[full] = h
        commits[full] = (parents.split(), subject)
    if not commits:
        sys.exit("nessun commit trovato")

    # tag git reali (annotati e leggeri): commit -> nomi tag
    tags = {}
    for line in git(a.repo, "for-each-ref", "refs/tags",
                    "--format=%(objecttype) %(refname:short) %(objectname) %(*objectname)").splitlines():
        kind, tag, obj, deref = line.split(" ")
        tags.setdefault(deref if kind == "tag" else obj, []).append(tag)

    out = []

    def emit(line):
        out.append("    " + line)

    def tag_of(h, fallback):
        return label(", ".join(tags[h])) if h in tags else fallback

    def commit_line(h):
        emit(f'commit id: "{short[h]}" tag: "{tag_of(h, label(commits[h][1]))}"')

    def header(branch_name):
        out.append('%%{init: {"gitGraph": {"mainBranchName": "'
                   + branch_name + '"}}}%%')
        out.append("gitGraph")

    if a.linear:
        # ordine parents-first, senza rami: il nome serve solo all'etichetta del ramo
        # HEAD puo' non risolvere (ref puntato ma mai committato): non e' fatale
        head = git(a.repo, "rev-parse", "--abbrev-ref", "HEAD", strict=False).strip()
        header(slug("main" if head in ("", "HEAD") else head))
        for h in reversed(list(commits)):
            commit_line(h)
    else:
        owner = {}  # commit -> ramo che lo rivendica
        tips = branch_tips(a.repo)
        names, taken = {}, set()  # unica mappa raw -> nome Mermaid (nessuna collisione)

        def uname(branch):
            """raw -> nome Mermaid unico: nomi diversi non possono collassare in una lane."""
            if branch not in names:
                base = slug(branch)
                cand, i = base, 1
                while cand in taken:
                    i += 1
                    cand = f"{base}_{i}"
                if cand != base:
                    sys.stderr.write(
                        f'warning: ramo "{branch}": "{base}" occupato, uso "{cand}"\n')
                names[branch] = cand
                taken.add(cand)
            return names[branch]

        for ref, sha in tips:
            uname(ref)  # la frontiera rivendica i nomi per prima (main/master in testa)
            for h in git(a.repo, "rev-list", "--first-parent", f"-n{a.n}", sha).split():
                owner.setdefault(h, ref)

        children = {}
        for h, (parents, _) in commits.items():
            for p in parents:
                if p in commits:
                    children.setdefault(p, []).append(h)

        def parents_of(h):
            return [p for p in commits[h][0] if p in commits]

        # catene laterali senza ref (tipiche dei merge PR): lane dedicata al merge
        for m in commits:
            par = parents_of(m)
            if len(par) < 2:
                continue
            p = par[1]
            while p in commits and p not in owner:
                owner[p] = f"merge_{short[m]}"
                p = commits[p][0][0] if commits[p][0] else None

        roots = [h for h in commits if not parents_of(h)]
        start = roots[-1] if roots else next(reversed(commits))
        start_branch = owner.get(start, "main")
        header(uname(start_branch))

        heads, finished, deferred = {}, set(), []
        # stato in un solo dominio (nomi Mermaid): lane corrente + lane gia' emesse
        first = uname(start_branch)
        state = {"cur": first, "made": {first}}

        def switch(branch):
            n = uname(branch)
            if state["cur"] == n:
                return
            if n in state["made"]:
                emit(f"checkout {n}")
            else:
                emit(f"branch {n}")
                state["made"].add(n)
            state["cur"] = n

        def emit_commit(h, branch):
            par = parents_of(h)
            if len(par) > 1:
                side = owner.get(par[1]) or next(
                    (b for b, tip in heads.items() if tip == par[1]), None)
                if side and side != branch and heads.get(side) == par[1]:
                    emit(f'merge {uname(side)} id: "{short[h]}" tag: "{tag_of(h, label(commits[h][1]))}"')
                    return
            commit_line(h)

        def walk(h, branch):
            if h in finished:
                return
            finished.add(h)
            emit_commit(h, branch)
            heads[branch] = h
            # figli di cui h e' il primo genitore presente: il ramo nasce qui
            kids = [c for c in children.get(h, []) if parents_of(c)[0] == h]
            # prima i rami che si staccano, poi la continuazione, i merge in coda
            for c in sorted(kids, key=lambda c: (len(parents_of(c)) > 1,
                                                 owner.get(c, branch) == branch)):
                cb = owner.get(c, branch)
                par = parents_of(c)
                if len(par) > 1 and heads.get(owner.get(par[1])) != par[1]:
                    switch(cb)   # lane creata al fork point, poi si torna indietro
                    switch(branch)
                    deferred.append(c)
                    continue
                switch(cb)
                walk(c, cb)
                switch(branch)

        walk(start, start_branch)

        def ready(h):
            return h not in finished and all(p in finished for p in parents_of(h))

        # componenti staccate (finestra troncata) e merge sbloccati in un secondo giro
        while True:
            todo = [h for h in reversed(list(commits)) if ready(h)]
            if not todo:
                break
            for h in todo:
                if not ready(h):
                    continue
                if h in deferred:
                    deferred.remove(h)
                cb = owner.get(h, start_branch)
                switch(cb)
                walk(h, cb)

        # reti di sicurezza: nulla sparisce in silenzio
        lost = [h for h in reversed(list(commits)) if h not in finished]
        if lost:
            sys.stderr.write(f"warning: {len(lost)} commit fuori dalle catene principali\n")
            switch(start_branch)
            for h in lost:
                commit_line(h)
        if deferred:
            sys.stderr.write(f"warning: {len(deferred)} merge non ricostruiti\n")
        # un checkout finale non disegna nulla
        while out and out[-1].strip().startswith("checkout "):
            out.pop()

    text = "\n".join(out) + "\n"
    if a.png:
        render_png(text, a.png)
        print(f"png -> {a.png}", file=sys.stderr)
        return
    if a.md:
        text = f"```mermaid\n{text}```\n"
    if a.o:
        with open(a.o, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{len(out)} righe -> {a.o}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()

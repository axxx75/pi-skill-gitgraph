#!/usr/bin/env python3
"""Storia git -> Mermaid gitGraph: rami, fork e merge ricostruiti.

Destinazioni, esclusive: --png FILE (render locale con mmdc, niente stdout) oppure -o FILE (file,
avvolto nel fence ```mermaid con --md) oppure stdout (Mermaid puro, col fence con --md). --png
non si combina con -o/--md: chiedere due destinazioni e' un errore (exit 2), non uno scarto
silenzioso. --linear disattiva la ricostruzione: soli commit in ordine parents-first. Tutto
locale: nessuna chiamata di rete; l'unico servizio esterno e' mermaid.live, e solo se ci incolli
il grafo. Dettagli: README.md.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

LABEL_LEN_DEFAULT = 32  # caratteri dell'etichetta, ellissi compresa
PNG_SIZE = 1600  # larghezza del PNG renderizzato da mmdc
WINDOW_DEFAULT = 30  # -n di default: commit letti da git log (finestra di ricostruzione)
MAIN_NAMES = ("main", "master")  # trunk noti: ordine dei tip e fallback quando HEAD non risolve
SEP = "\x1f"  # separatore dei campi del log: '|' e' un carattere legittimo in un subject

# Warning su stderr = contratto macchina (SKILL.md, README): la frase resta invariata,
# l'hint in coda dice cosa fare. Unica fonte: i test la verificano, non la riscrivono.
WARN_LOST = ("warning: {n} commit fuori dalle catene principali "
             "(grafo incompleto: rilancia con -n {window} o --linear)\n")
WARN_DEFERRED = ("warning: {n} merge non ricostruiti "
                 "(serve una finestra piu' ampia: -n {window})\n")

# Ordine di risoluzione di Chromium: unica fonte, references/png-setup.md §2 lo ripete
CHROME_PATTERNS = (
    "~/.pi/agent/skills/pi-skills/browser-tools/chrome/*/chrome-linux64/chrome",
    "~/.cache/puppeteer/chrome/*/chrome-linux64/chrome",
    "~/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)


class GitError(RuntimeError):
    """Errore fatale (git o input): main() lo traduce in sys.exit, il chiamante lo cattura."""


def git(repo, *args, strict=True):
    r = subprocess.run(["git", "-C", repo, *args],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 and strict:
        raise GitError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def is_worktree(repo):
    """`git rev-parse --is-inside-work-tree` senza GitError: su un path che non e' un repo
    (nessuna directory, bare) deve arrivare il messaggio dedicato, non l'errore grezzo di git."""
    return git(repo, "rev-parse", "--is-inside-work-tree", strict=False).strip() == "true"


def slug(branch):
    """Nome ramo per Mermaid: solo [A-Za-z0-9_-], fallback "branch" se resta vuoto."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", branch) or "branch"


# In Mermaid '#' apre un'entita' numerica, '\\' e '`' hanno un significato proprio: dentro
# una stringa tra doppi apici rompono il render con un errore che non nomina il commit.
_MERMAID_ESCAPES = {'"': "'", "\\": "#92;", "#": "#35;", "`": "#96;"}


def escape(text):
    """Testo preso da git -> testo sicuro dentro una stringa Mermaid tra doppi apici.

    I caratteri non stampabili (controlli, formati) non sono testo: diventano il glifo
    di sostituzione, cosi' nessuno spezza il parser restando invisibile nel diagramma.
    """
    out = []
    for ch in str(text):
        out.append(_MERMAID_ESCAPES.get(ch) or (ch if ch.isprintable() else "#65533;"))
    return "".join(out)


def label(text, limit=LABEL_LEN_DEFAULT):
    """Soggetto su una riga (spazi collassati, escape Mermaid), troncato a `limit` caratteri
    DOPO la normalizzazione, ellissi compresa, a confine di parola (limit <= 0: intero).

    Unico punto di escaping: ogni testo di git finisce qui (via tag_of), mentre i nomi
    ramo arrivano gia' ridotti a [A-Za-z0-9_-] da slug() e gli hash sono esadecimali.
    `limit` conta i caratteri del soggetto, `…` incluso: l'escape puo' allungare l'etichetta.
    """
    text = " ".join(str(text).split())
    if limit <= 0 or len(text) <= limit:
        return escape(text)
    cut = text[:limit - 1].rsplit(" ", 1)[0]
    if len(cut) * 2 < limit:  # confine di parola troppo vicino all'inizio: taglio duro
        cut = text[:limit - 1]
    return escape(cut + "…")


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
    return sorted(tips, key=lambda t: t[0] not in MAIN_NAMES)


def chrome_bin():
    """Chromium gia' presente: mmdc non deve scaricarne uno suo."""
    env = os.environ.get("PUPPETEER_EXECUTABLE_PATH")
    if env and os.path.exists(env):
        return env
    # in ordine: browser-tools dell'ecosistema pi, cache puppeteer/playwright, chromium di sistema
    for pattern in CHROME_PATTERNS:
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return None


def render_png(mermaid, out):
    """Mermaid -> PNG via mmdc; esce con una riga se mmdc o Chromium mancano.

    --no-sandbox nel puppeteer.json: il Chromium locale gira in container/CI dove il
    sandbox non ha namespace utente; l'input e' l'.mmd scritto qui, non HTML esterno.
    """
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
                            "--size", str(PNG_SIZE), "-b", "white", "-q"],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            sys.exit(f"mmdc fallito: {r.stderr.strip() or r.stdout.strip()}")


def check_out(path):
    """Path di uscita utilizzabile: errore in stile CLI (una riga, exit 1), mai un traceback."""
    parent = os.path.dirname(os.path.abspath(path))
    if os.path.isdir(path):
        sys.exit(f"{path}: e' una directory, serve un file")
    if not os.path.isdir(parent):
        sys.exit(f"{path}: directory inesistente ({parent})")


def write_atomic(path, text):
    """`<path>.tmp` + os.replace (stesso filesystem): una scrittura fallita non tronca il file."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:
        sys.exit(f"{path}: scrittura fallita: {e.strerror or e}")
    finally:
        # nessun .tmp orfano, anche su KeyboardInterrupt/SystemExit (dopo il replace e' un no-op)
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def read_graph(repo, n, linear=False):
    """Legge da git i dati che render() consuma: unica porta verso git del modulo."""
    if not is_worktree(repo):
        raise GitError(f"{repo}: non e' un repository git")

    # commit -> ([parents], subject), dal piu' recente al piu' vecchio
    log = git(repo, "log", "--all", "--topo-order", f"-n{n}",
              f"--pretty=format:%h{SEP}%H{SEP}%P{SEP}%s")
    short, commits = {}, {}
    # split("\n") e non splitlines(): git separa i commit con \n, mentre splitlines()
    # spezza anche su \x0b, \x0c, \x85, U+2028 e simili, che possono stare in un subject
    for line in log.split("\n"):
        if not line:
            continue
        if line.count(SEP) < 3:
            raise GitError(f"log git non interpretabile: {line!r}")
        # maxsplit: un campo in piu' resta nel subject invece di rompere l'unpacking
        h, full, parents, subject = line.split(SEP, 3)
        short[full] = h
        commits[full] = (parents.split(), subject)
    if not commits:
        raise GitError("nessun commit trovato")

    # tag git reali (annotati e leggeri): commit -> nomi tag
    tags = {}
    for line in git(repo, "for-each-ref", "refs/tags",
                    "--format=%(objecttype) %(refname:short) %(objectname) %(*objectname)").splitlines():
        # maxsplit: il nome di un ref non puo' contenere spazi (git check-ref-format),
        # quindi uno spazio oltre il terzo campo e' un formato inatteso: dirlo, non perderlo
        fields = line.split(" ", 3)
        if len(fields) < 3 or (len(fields) == 4 and " " in fields[3]):
            raise GitError(f"tag non interpretabile: {line!r}")
        kind, tag, obj, deref = fields + [""] * (4 - len(fields))
        tags.setdefault(deref if kind == "tag" else obj, []).append(tag)

    # HEAD puo' non risolvere (ref puntato ma mai committato): non e' fatale
    head = git(repo, "rev-parse", "--abbrev-ref", "HEAD", strict=False).strip()
    if linear:
        return commits, short, tags, [], head
    return commits, short, tags, branch_tips(repo), head


def render(commits, short, tags, tips, linear=False, label_len=LABEL_LEN_DEFAULT,
           head="", warn=None, window=WINDOW_DEFAULT) -> list[str]:
    """commits/short/tags/tips gia' letti da git -> righe Mermaid (nessun I/O).

    Linear: una fila parents-first. Altrimenti Graph ricostruisce le lane nello stesso
    ordine di sempre (header, walk, settle, report_lost); lo stato vive sull'istanza.
    """
    # il trunk e' quello di HEAD: "main" resta solo il fallback dichiarato (HEAD non risolve,
    # oppure e' il literal "HEAD" di un checkout detached)
    trunk = head if head not in ("", "HEAD") else MAIN_NAMES[0]
    g = Graph(commits, short, tags, label_len, warn, trunk, window)
    if linear:
        # ordine parents-first, senza rami: il nome serve solo all'etichetta del ramo
        g.header(slug(trunk))
        for h in reversed(list(commits)):
            g.commit_line(h)
        return g.out

    g.claim(tips)
    g.header(g.uname(g.start_branch))
    g.walk(g.start, g.start_branch)
    g.settle()        # ex while True + ready()
    g.report_lost()   # ex reti di sicurezza
    return g.out


class Graph:
    """Ricostruzione delle lane: ogni struttura mutata e' un campo, non una cattura di closure."""

    def __init__(self, commits, short, tags, label_len=LABEL_LEN_DEFAULT, warn=None,
                 trunk=MAIN_NAMES[0], window=WINDOW_DEFAULT):
        self.commits, self.short, self.tags = commits, short, tags
        self.label_len = label_len
        self.trunk = trunk  # ramo di ripiego quando nessun tip rivendica la radice
        self.window = window  # solo per l'hint: -n raddoppiato nei warning
        self.say = warn or (lambda _msg: None)
        self.out = []
        self.owner = {}  # commit -> ramo che lo rivendica
        self.names, self.taken = {}, set()  # unica mappa raw -> nome Mermaid (nessuna collisione)
        self.children = {}
        for h, (parents, _) in commits.items():
            for p in parents:
                if p in commits:
                    self.children.setdefault(p, []).append(h)
        self.heads, self.finished, self.deferred = {}, set(), set()
        self.state = {"cur": None, "made": set()}
        self.start = self.start_branch = ""

    def emit(self, line):
        self.out.append("    " + line)

    def tag_of(self, h, fallback):
        """Primo tag, mai spezzato: i tag in piu' diventano "+N"; subject troncato se non c'e' tag."""
        if h not in self.tags:
            return label(fallback, self.label_len)
        first = label(self.tags[h][0], self.label_len)
        return f"{first} +{len(self.tags[h]) - 1}" if len(self.tags[h]) > 1 else first

    def commit_line(self, h):
        self.emit(f'commit id: "{self.short[h]}" tag: "{self.tag_of(h, self.commits[h][1])}"')

    def header(self, branch_name):
        self.out.append('%%{init: {"gitGraph": {"mainBranchName": "'
                        + branch_name + '"}}}%%')
        self.out.append("gitGraph")

    def uname(self, branch):
        """raw -> nome Mermaid unico: nomi diversi non possono collassare in una lane."""
        if branch not in self.names:
            base = slug(branch)
            cand, i = base, 1
            while cand in self.taken:
                i += 1
                cand = f"{base}_{i}"
            if cand != base:
                self.say(f'warning: ramo "{branch}": "{base}" occupato, uso "{cand}"\n')
            self.names[branch] = cand
            self.taken.add(cand)
        return self.names[branch]

    def parents_of(self, h):
        return [p for p in self.commits[h][0] if p in self.commits]

    def claim(self, tips):
        """Assegna owner e lane di partenza; i nomi li rivendica la frontiera per prima."""
        for ref, sha in tips:
            self.uname(ref)  # la frontiera rivendica i nomi per prima (main/master in testa)
            # catena first-parent in-finestra: con --topo-order un genitore fuori da
            # commits ha tutti gli antenati fuori, quindi si chiude come faceva rev-list
            while sha in self.commits:
                self.owner.setdefault(sha, ref)
                par = self.commits[sha][0]
                sha = par[0] if par else None

        # catene laterali senza ref (tipiche dei merge PR): lane dedicata al merge
        for m in self.commits:
            par = self.parents_of(m)
            if len(par) < 2:
                continue
            p = par[1]
            while p in self.commits and p not in self.owner:
                self.owner[p] = f"merge_{self.short[m]}"
                p = self.commits[p][0][0] if self.commits[p][0] else None

        roots = [h for h in self.commits if not self.parents_of(h)]
        self.start = roots[-1] if roots else next(reversed(self.commits))
        self.start_branch = self.owner.get(self.start, self.trunk)
        # stato in un solo dominio (nomi Mermaid): lane corrente + lane gia' emesse
        first = self.uname(self.start_branch)
        self.state = {"cur": first, "made": {first}}

    def switch(self, branch):
        n = self.uname(branch)
        if self.state["cur"] == n:
            return
        if n in self.state["made"]:
            self.emit(f"checkout {n}")
        else:
            self.emit(f"branch {n}")
            self.state["made"].add(n)
        self.state["cur"] = n

    def emit_commit(self, h, branch):
        par = self.parents_of(h)
        if len(par) > 1:
            side = self.owner.get(par[1]) or next(
                (b for b, tip in self.heads.items() if tip == par[1]), None)
            if side and side != branch and self.heads.get(side) == par[1]:
                self.emit(f'merge {self.uname(side)} id: "{self.short[h]}" '
                          f'tag: "{self.tag_of(h, self.commits[h][1])}"')
                return
        self.commit_line(h)

    def walk(self, h, branch):
        if h in self.finished:
            return
        self.finished.add(h)
        self.emit_commit(h, branch)
        self.heads[branch] = h
        # figli di cui h e' il primo genitore presente: il ramo nasce qui
        kids = [c for c in self.children.get(h, []) if self.parents_of(c)[0] == h]
        # prima i rami che si staccano, poi la continuazione, i merge in coda
        for c in sorted(kids, key=lambda c: (len(self.parents_of(c)) > 1,
                                             self.owner.get(c, branch) == branch)):
            cb = self.owner.get(c, branch)
            par = self.parents_of(c)
            if len(par) > 1 and self.heads.get(self.owner.get(par[1])) != par[1]:
                self.switch(cb)   # lane creata al fork point, poi si torna indietro
                self.switch(branch)
                self.deferred.add(c)
                continue
            self.switch(cb)
            self.walk(c, cb)
            self.switch(branch)

    def ready(self, h):
        return h not in self.finished and all(p in self.finished for p in self.parents_of(h))

    def settle(self):
        """Unico worklist: riprende i commit sbloccati finche' ne restano; `deferred`
        e' solo il set dei merge mai ricostruiti (diagnostica, dedup gratuito).

        Terminazione: il primo `h` di `todo` e' ancora `ready` (nessuna mutazione tra
        la list comprehension e il loop), quindi `walk` lo marca in `finished`: ogni
        giro cresce `len(finished)` di almeno 1 (i successivi possono essere gia'
        finiti dal `walk` ricorsivo). `finished` e' monotono e limitato da
        `len(commits)`, quindi il ciclo esce sempre, anche su input degenere.

        Cambio dichiarato rispetto alla lista: il set deduplica, quindi un commit con
        lo stesso genitore ripetuto (es. `c00 -> c02, c02`, che finisce due volte in
        `children[c02]` e veniva accodato due volte, con una sola `remove`) non lascia
        piu' un falso "warning: N merge non ricostruiti". Caso non creabile con git
        normale (`commit-tree` scarta i parent duplicati): raggiungibile solo via
        `.git/info/grafts`; stdout invariato.
        """
        while True:
            todo = [h for h in reversed(list(self.commits)) if self.ready(h)]
            if not todo:
                return
            for h in todo:
                if not self.ready(h):  # finito nel frattempo dal walk ricorsivo
                    continue
                self.deferred.discard(h)
                cb = self.owner.get(h, self.start_branch)
                self.switch(cb)
                self.walk(h, cb)

    def report_lost(self):
        """Reti di sicurezza: nulla sparisce in silenzio, i buchi diventano warning."""
        # conteggio derivato: nella CLI finished e' sottoinsieme di commits, il max(0, ...)
        # copre un chiamante che inietta hash estranei (nessun conteggio negativo)
        lost = max(0, len(self.commits) - len(self.finished))
        if lost:
            self.say(WARN_LOST.format(n=lost, window=self.window * 2))
            self.switch(self.start_branch)
            for h in reversed(list(self.commits)):
                if h not in self.finished:
                    self.commit_line(h)
        if self.deferred:
            self.say(WARN_DEFERRED.format(n=len(self.deferred), window=self.window * 2))
        # un checkout finale non disegna nulla
        while self.out and self.out[-1].strip().startswith("checkout "):
            self.out.pop()


def main():
    """Entry point CLI: argomenti, I/O (stdout / -o / --png) e GitError -> sys.exit.

    Qui nessuna logica di disegno: read_graph() legge da git, render() produce le righe.
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", nargs="?", default=".", help="path del repository")
    ap.add_argument("-n", type=int, default=WINDOW_DEFAULT,
                    help="finestra di ricostruzione in commit (default 30): alzarla fa rientrare "
                         "i merge, piu' rami = piu' catene da percorrere")
    ap.add_argument("-o", metavar="FILE", help="scrive su file invece che su stdout")
    ap.add_argument("--png", metavar="FILE",
                    help="renderizza un PNG con mmdc (chromium gia' presente, nessun download)")
    ap.add_argument("--md", action="store_true",
                    help="avvolge l'output in un fence ```mermaid (file .md per la preview)")
    ap.add_argument("--linear", action="store_true",
                    help="fila indiana: un solo ramo, nessuna ricostruzione dei merge")
    ap.add_argument("--label-len", type=int, default=LABEL_LEN_DEFAULT,
                    help="caratteri massimi per etichetta, troncata a confine di parola "
                         "(default 32, 0 = soggetto intero)")
    a = ap.parse_args()
    if a.n < 1:
        ap.error("serve -n >= 1")
    if a.png and (a.o or a.md):
        # due destinazioni sono un errore: -o/--md non vanno piu' scartati in silenzio
        ap.error("--png non combinabile con -o/--md: scegli una destinazione")
    if a.png:
        check_out(a.png)
    elif a.o:
        check_out(a.o)

    try:
        commits, short, tags, tips, head = read_graph(a.repo, a.n, a.linear)
        out = render(commits, short, tags, tips, linear=a.linear,
                     label_len=a.label_len, head=head, window=a.n,
                     warn=lambda msg: sys.stderr.write(msg))
    except GitError as e:
        sys.exit(str(e))

    text = "\n".join(out) + "\n"
    if a.png:
        render_png(text, a.png)
        print(f"png -> {a.png}", file=sys.stderr)
        return
    if a.md:
        text = f"```mermaid\n{text}```\n"
    if a.o:
        write_atomic(a.o, text)
        # conteggio dei soli commit, non delle direttive Mermaid; path assoluto: dice dov'e' il file
        n_commits = sum(1 for line in out if "commit id:" in line)
        print(f"{n_commits} commit -> {os.path.abspath(a.o)}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()

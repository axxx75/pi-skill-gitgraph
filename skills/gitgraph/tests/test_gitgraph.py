#!/usr/bin/env python3
"""Unit test della logica pura di gitgraph.py (render) e degli errori tipizzati.

Fixture = dict letterali con la stessa forma dei dati letti da git, cosi' i test
non dipendono da git ne' dal filesystem (unica eccezione: il caso GitError).
    python3 -m unittest discover -s skills/gitgraph/tests
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "scripts"))
import gitgraph  # noqa: E402  (path del modulo deciso sopra)


def linear_fixture():
    """Storia lineare c1 <- c2 <- c3, nell'ordine in cui la da' git log."""
    commits = {
        "c3": (["c2"], "terzo commit con soggetto molto lungo davvero"),
        "c2": (["c1"], "secondo"),
        "c1": ([], "primo"),
    }
    return commits, {"c3": "a3", "c2": "a2", "c1": "a1"}


def init(name):
    return gitgraph.init_directive(name)


class RenderLinearTest(unittest.TestCase):
    def test_linear_output_esatto(self):
        commits, short = linear_fixture()
        self.assertEqual(
            gitgraph.render(commits, short, {}, [], linear=True, head="main"),
            [
                init("main"),
                "gitGraph",
                '    commit id: "a1" tag: "primo"',
                '    commit id: "a2" tag: "secondo"',
                '    commit id: "a3" tag: "terzo commit con soggetto…"',
            ],
        )

    def test_head_non_risolto_ricade_su_main(self):
        commits, short = linear_fixture()
        for head in ("", "HEAD"):
            out = gitgraph.render(commits, short, {}, [], linear=True, head=head)
            self.assertEqual(out[0], init("main"))

    def test_nome_ramo_sanificato(self):
        commits, short = linear_fixture()
        out = gitgraph.render(commits, short, {}, [], linear=True, head="feature/x")
        self.assertEqual(out[0], init("feature_x"))


class RenderLaneTest(unittest.TestCase):
    def test_merge_apre_la_lane_e_la_chiude(self):
        # main: A <- M(merge di feature)  feature: A <- X
        commits = {
            "M": (["A", "X"], "merge del ramo"),
            "X": (["A"], "lavoro in feature"),
            "A": ([], "radice"),
        }
        short = {"M": "a4", "X": "a3", "A": "a2"}
        warnings = []
        out = gitgraph.render(commits, short, {}, [("main", "M"), ("feature", "X")],
                              warn=warnings.append)
        self.assertEqual(
            out,
            [
                init("main"),
                "gitGraph",
                '    commit id: "a2" tag: "radice"',
                "    branch feature",
                '    commit id: "a3" tag: "lavoro in feature"',
                "    checkout main",
                '    merge feature id: "a4" tag: "merge del ramo"',
            ],
        )
        self.assertEqual(warnings, [])

    def test_collisione_nomi_ramo_da_lane_distinte(self):
        # P0-02: feature/x e feature_x sanificano allo stesso nome Mermaid
        commits = {
            "X": (["A"], "x"),
            "Y": (["A"], "y"),
            "A": ([], "a"),
        }
        short = {"X": "a3", "Y": "a2", "A": "a1"}
        warnings = []
        out = gitgraph.render(
            commits, short, {},
            [("main", "A"), ("feature/x", "X"), ("feature_x", "Y")],
            warn=warnings.append)
        self.assertEqual(
            out,
            [
                init("main"),
                "gitGraph",
                '    commit id: "a1" tag: "a"',
                "    branch feature_x",
                '    commit id: "a3" tag: "x"',
                "    checkout main",
                "    branch feature_x_2",
                '    commit id: "a2" tag: "y"',
            ],
        )
        self.assertEqual(
            warnings,
            ['warning: ramo "feature_x": "feature_x" occupato, uso "feature_x_2"\n'])


class SettleTest(unittest.TestCase):
    """P1-03: un solo worklist; `deferred` e' un set che settle() prosciuga."""

    COMMITS = {
        "N": (["M"], "n"),
        "M": (["B", "X"], "merge f"),   # secondo genitore non piu' testa della lane f
        "Y": (["X"], "y"),
        "X": (["B"], "x"),
        "B": (["A"], "b"),
        "A": ([], "a"),
    }

    def test_merge_differito_ripreso_da_settle(self):
        g = gitgraph.Graph(self.COMMITS, {h: h.lower() for h in self.COMMITS}, {},
                           warn=self.fail)
        g.claim([("main", "N"), ("f", "Y")])
        g.header(g.uname(g.start_branch))
        g.walk(g.start, g.start_branch)
        self.assertEqual(g.deferred, {"M"})  # walk lo rimanda: heads[f] e' Y, non X
        g.settle()  # invariante: ogni giro aggiunge a finished, quindi termina
        self.assertEqual(g.deferred, set())
        self.assertEqual(g.finished, set(self.COMMITS))

    def test_report_lost_conteggio_derivato_da_finished(self):
        commits = {"C": (["B"], "c"), "B": (["A"], "b"), "A": ([], "a")}
        warnings = []
        g = gitgraph.Graph(commits, {h: h.lower() for h in commits}, {},
                           warn=warnings.append)
        g.claim([])
        g.header("main")
        g.finished.add("A")  # scenario: catena camminata solo in parte
        g.report_lost()
        self.assertEqual(warnings,
                         [gitgraph.WARN_LOST.format(n=2, window=gitgraph.WINDOW_DEFAULT * 2)])
        self.assertEqual([line for line in g.out if ' id: "' in line],
                         ['    commit id: "b" tag: "b"',
                          '    commit id: "c" tag: "c"'])

    def test_genitore_duplicato_non_lascia_warning_falso(self):
        # caso non creabile da git normale (solo via .git/info/grafts), dichiarato
        # nel docstring di settle(): il set deduplica, il vecchio falso warning sparisce
        commits = {"c00": (["c02", "c02"], "0"),
                   "c01": (["c02"], "1"),
                   "c02": (["out2"], "2")}
        warnings = []
        g = gitgraph.Graph(commits, {h: h for h in commits}, {},
                           warn=warnings.append)
        g.claim([("side", "c01"), ("main", "c01")])
        g.header(g.uname(g.start_branch))
        g.walk(g.start, g.start_branch)
        g.settle()
        g.report_lost()
        self.assertEqual(g.deferred, set())
        self.assertEqual(warnings, [])

    def test_report_lost_non_negativo_se_finished_esce_da_commits(self):
        commits = {"C": (["B"], "c"), "B": (["A"], "b"), "A": ([], "a")}
        warnings = []
        g = gitgraph.Graph(commits, {h: h.lower() for h in commits}, {},
                           warn=warnings.append)
        g.claim([])
        g.header("main")
        g.finished.update(set(commits) | {"fuori"})  # hash non in commits
        g.report_lost()
        self.assertEqual(warnings, [])


class SwitchStateTest(unittest.TestCase):
    """P2-08: un checkout in coda (ritorno alla lane di partenza) non resta nell'output."""

    def test_checkout_finale_rimosso(self):
        commits = {"X": (["A"], "x"), "A": ([], "a")}
        out = gitgraph.render(commits, {"X": "a2", "A": "a1"}, {},
                              [("main", "A"), ("side", "X")])
        self.assertEqual(out[-1], '    commit id: "a2" tag: "x"')
        self.assertFalse([line for line in out if line.strip().startswith("checkout ")])


class RenderLabelTest(unittest.TestCase):
    SUBJECT = "feat: configurazione molto lunga delle etichette nei diagrammi"

    def fixture(self):
        return {"c2": (["c1"], self.SUBJECT), "c1": ([], "breve")}, {"c2": "b2", "c1": "b1"}

    def tags_of(self, out):
        return [line.partition(' tag: "')[2].rstrip('"') for line in out if ' tag: "' in line]

    def test_troncatura_a_confine_di_parola(self):
        # P0-03: il taglio non deve collassare il testo utile (default 32)
        commits, short = self.fixture()
        out = gitgraph.render(commits, short, {}, [], linear=True, head="main")
        self.assertEqual(self.tags_of(out), ["breve", "feat: configurazione molto…"])

    def test_label_len_configurabile(self):
        commits, short = self.fixture()
        for limit, expected in ((12, "feat: confi…"), (0, self.SUBJECT)):
            out = gitgraph.render(commits, short, {}, [], linear=True, head="main",
                                  label_len=limit)
            self.assertEqual(self.tags_of(out)[1], expected)

    def test_multi_tag_annotato_una_volta(self):
        # P0-03: primo tag + "+N", i tag successivi non compaiono
        commits, short = self.fixture()
        out = gitgraph.render(commits, short, {"c2": ["t1", "t2", "t3"]}, [],
                              linear=True, head="main")
        tags = self.tags_of(out)
        self.assertEqual(tags, ["breve", "t1 +2"])
        # "git2" della palette contiene "t2": si controllano i tag, non tutto l'output
        self.assertNotIn("t2", " ".join(tags))

    def test_virgolette_nel_subject_rese(self):
        commits = {"c1": ([], 'fix "rotto" qui')}
        out = gitgraph.render(commits, {"c1": "a1"}, {}, [], linear=True, head="main")
        self.assertEqual(out[2], '    commit id: "a1" tag: "fix \'rotto\' qui"')


class EscapeTest(unittest.TestCase):
    """P2-01: un solo punto di escaping; '#'/backslash/backtick/controlli non rompono il render."""

    def tags_of(self, out):
        return [line.partition(' tag: "')[2].rstrip('"') for line in out if ' tag: "' in line]

    def render_one(self, subject, tags=None):
        return self.tags_of(gitgraph.render({"c1": ([], subject)}, {"c1": "a1"},
                                            tags or {}, [], linear=True, head="main"))

    def test_metacaratteri_e_controlli_nel_subject(self):
        self.assertEqual(self.render_one('foo"bar\\baz\x01 qux'),
                         ["foo'bar#92;baz#65533; qux"])

    def test_hash_e_backtick_nel_nome_tag(self):
        self.assertEqual(self.render_one("x", {"c1": ["v1#2`"]}), ["v1#35;2#96;"])

    def test_testo_normale_non_cambia(self):
        self.assertEqual(self.render_one("fix: rotella 2/3 (ok)"),
                         ["fix: rotella 2/3 (ok)"])


class FlagPolicyTest(unittest.TestCase):
    """P2-04: --png e' esclusivo con -o/--md, -n >= 1, e si rifiuta prima di leggere git."""

    def rejected(self, *args):
        argv = ["gitgraph.py", *args]
        with mock.patch.object(gitgraph.sys, "argv", argv), \
                mock.patch.object(gitgraph, "read_graph") as read, \
                mock.patch.object(gitgraph, "render_png") as render_png, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                gitgraph.main()
        read.assert_not_called()
        render_png.assert_not_called()
        return cm.exception.code, err.getvalue()

    def test_png_con_o_e_un_errore(self):
        code, err = self.rejected(".", "--png", "g.png", "-o", "g.md")
        self.assertEqual(code, 2)  # exit di argparse: nessun file scritto
        self.assertIn("non combinabile con -o/--md", err)

    def test_png_con_md_e_un_errore(self):
        code, err = self.rejected(".", "--png", "g.png", "--md")
        self.assertEqual(code, 2)
        self.assertIn("non combinabile con -o/--md", err)

    def test_n_minore_di_uno_e_un_errore(self):
        for n in ("0", "-1"):
            code, err = self.rejected(".", "-n", n)
            self.assertEqual(code, 2)
            self.assertIn("serve -n >= 1", err)

    def test_o_con_md_resta_valido(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "g.md")
            argv = ["gitgraph.py", ".", "-o", path, "--md"]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph",
                                      return_value=linear_fixture() + ({}, [], "")):
                gitgraph.main()  # nessun SystemExit
            with open(path, encoding="utf-8") as f:
                self.assertTrue(f.read().startswith("```mermaid\n"))


class OutputMessageTest(unittest.TestCase):
    """P2-06: il messaggio di -o conta i commit (non le righe Mermaid) e dice il path assoluto."""

    def test_conteggio_commit_e_path_assoluto(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "g.mmd")
            argv = ["gitgraph.py", ".", "-o", path, "--md"]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph",
                                      return_value=linear_fixture() + ({}, [], "")), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                gitgraph.main()
        # --md aggiunge due fence e l'init non e' un commit: il conteggio e' 3
        self.assertEqual(err.getvalue(), f"3 commit -> {os.path.abspath(path)}\n")


class ContractTextTest(unittest.TestCase):
    """P2-06: warning e percorsi Chromium hanno una sola fonte; la doc li ripete,
    questo test impedisce che le copie divergano in silenzio."""

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    PHRASES = ("commit fuori dalle catene principali", "merge non ricostruiti")

    def read(self, *parts):
        with open(os.path.join(self.ROOT, *parts), encoding="utf-8") as f:
            return f.read()

    def test_warning_restano_il_contratto_di_skill_md(self):
        for const, phrase in zip((gitgraph.WARN_LOST, gitgraph.WARN_DEFERRED), self.PHRASES):
            with self.subTest(phrase=phrase):
                text = const.format(n=3, window=60)
                self.assertTrue(text.startswith(f"warning: 3 {phrase}"), text)
                # l'hint dice cosa fare, dopo la frase contrattuale (D3: frase invariata)
                self.assertIn("-n 60", text)

    def test_frasi_dei_warning_citate_in_readme_e_skill(self):
        for doc in ("README.md", "skills/gitgraph/SKILL.md"):
            text = self.read(*doc.split("/"))
            for phrase in self.PHRASES:
                with self.subTest(doc=doc, phrase=phrase):
                    self.assertIn(phrase, text)

    def test_requisito_pi_dichiarato_nel_frontmatter(self):
        frontmatter = self.read("skills", "gitgraph", "SKILL.md").split("---\n")[1]
        line = next(l for l in frontmatter.splitlines() if l.startswith("compatibility:"))
        self.assertIn("pi >= 1.4", line)

    def test_percorsi_chromium_allineati_alla_doc(self):
        doc = self.read("skills", "gitgraph", "references", "png-setup.md")
        for pattern in gitgraph.CHROME_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, doc)


class TrunkTest(unittest.TestCase):
    """P2-04: il trunk viene da HEAD, non da un "main" cablato."""

    COMMITS = {"c2": (["c1"], "secondo"), "c1": ([], "radice")}
    SHORT = {"c2": "a2", "c1": "a1"}

    def test_head_reale_sostituisce_il_fallback(self):
        out = gitgraph.render(self.COMMITS, self.SHORT, {}, [], head="develop")
        self.assertEqual(out[0], init("develop"))

    def test_head_non_risolto_ricade_sul_fallback_dichiarato(self):
        for head in ("", "HEAD"):
            out = gitgraph.render(self.COMMITS, self.SHORT, {}, [], head=head)
            self.assertEqual(out[0], init(gitgraph.MAIN_NAMES[0]))

    def test_linear_usa_lo_stesso_fallback(self):
        out = gitgraph.render(self.COMMITS, self.SHORT, {}, [], linear=True, head="")
        self.assertEqual(out[0], init(gitgraph.MAIN_NAMES[0]))


class WorktreeTest(unittest.TestCase):
    """P2-05: il messaggio "non e' un repository git" deve essere raggiungibile."""

    def test_path_inesistente_messaggio_dedicato(self):
        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "manca")
            with self.assertRaises(gitgraph.GitError) as cm:
                gitgraph.read_graph(missing, 10)
        self.assertIn("non e' un repository git", str(cm.exception))
        self.assertNotIn("fatal", str(cm.exception))  # niente errore grezzo di git

    def test_bare_repo_rifiutato_con_lo_stesso_messaggio(self):
        with tempfile.TemporaryDirectory() as d:
            gitgraph.git(d, "init", "-q", "--bare")
            with self.assertRaisesRegex(gitgraph.GitError, "non e' un repository git"):
                gitgraph.read_graph(d, 10)

    def test_is_worktree_falso_non_solleva(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(gitgraph.is_worktree(os.path.join(d, "manca")))


class GitErrorTest(unittest.TestCase):
    def test_git_solleva_errore_tipizzato(self):
        with tempfile.TemporaryDirectory() as d:
            gitgraph.git(d, "init", "-q")
            with self.assertRaises(gitgraph.GitError) as cm:
                gitgraph.git(d, "rev-parse", "HEAD")
            self.assertIsInstance(cm.exception, RuntimeError)
            self.assertIn("git rev-parse HEAD", str(cm.exception))

    def test_git_strict_false_non_solleva(self):
        with tempfile.TemporaryDirectory() as d:
            gitgraph.git(d, "init", "-q")
            gitgraph.git(d, "rev-parse", "HEAD", strict=False)  # nessun GitError

    def test_repo_non_valido(self):
        with mock.patch.object(gitgraph, "git", return_value="false\n"):
            with self.assertRaisesRegex(gitgraph.GitError, "non e' un repository git"):
                gitgraph.read_graph(".", 10)

    def test_nessun_commit(self):
        # worktree, heads, remotes, log
        with mock.patch.object(gitgraph, "git", side_effect=["true\n", "", "", ""]):
            with self.assertRaisesRegex(gitgraph.GitError, "nessun commit trovato"):
                gitgraph.read_graph(".", 10)

    def test_main_traduce_giterror_in_exit(self):
        with mock.patch.object(gitgraph.sys, "argv", ["gitgraph.py", "."]), \
                mock.patch.object(gitgraph, "read_graph",
                                  side_effect=gitgraph.GitError("boom")):
            with self.assertRaises(SystemExit) as cm:
                gitgraph.main()
        self.assertEqual(cm.exception.code, "boom")


class BranchTipsTest(unittest.TestCase):
    """P2-03: dei remoti contano solo i ref di origin; i fork/upstream non aprono lane."""

    def tips(self, heads="", remotes=""):
        def fake(repo, *args):
            return heads if args[-1] == "refs/heads/" else remotes
        with mock.patch.object(gitgraph, "git", fake):
            return gitgraph.branch_tips(".")

    def test_solo_origin_quando_esiste(self):
        tips = self.tips(heads="refs/heads/main a1 \n",
                         remotes="refs/remotes/origin/dev a2 \n"
                                 "refs/remotes/upstream/fork a9 \n")
        self.assertEqual(tips, [("main", "a1"), ("origin/dev", "a2")])

    def test_senza_origin_restano_i_remoti_presenti(self):
        self.assertEqual(self.tips(remotes="refs/remotes/upstream/dev a2 \n"),
                         [("upstream/dev", "a2")])

    def test_ramo_locale_vince_sul_remoto_omonimo(self):
        self.assertEqual(self.tips(heads="refs/heads/main a1 \n",
                                   remotes="refs/remotes/origin/main a1 \n"),
                         [("main", "a1")])

    def test_origin_non_sparisce_se_duplica_il_locale(self):
        # retry 2: origin/main == main (clone normale) non deve far scattare il ripiego
        # sui remoti presenti, altrimenti i commit di upstream rientrano nella finestra
        tips = self.tips(heads="refs/heads/main a1 \n",
                         remotes="refs/remotes/origin/main a1 \n"
                                 "refs/remotes/upstream/fork a9 \n")
        self.assertEqual(tips, [("main", "a1")])

    def test_symref_ignorato(self):
        # due righe vere: il ref puntato da origin/HEAD resta una lane
        self.assertEqual(self.tips(remotes="refs/remotes/origin/HEAD a1 refs/remotes/origin/main\n"
                                            "refs/remotes/origin/main a1 \n"),
                         [("origin/main", "a1")])


class RefWindowIntTest(unittest.TestCase):
    """P2-03 retry 2: finestra sui ref tenuti, su repository git veri."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def g(self, repo, *args):
        return gitgraph.git(repo, "-c", "user.email=t@t.t", "-c", "user.name=t", *args)

    def commit(self, repo, name):
        with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
            f.write(name)
        self.g(repo, "add", "-A")
        self.g(repo, "commit", "-qm", name)
        return self.g(repo, "rev-parse", "HEAD").strip()

    def init(self, name):
        repo = self.path(name)
        os.makedirs(repo)
        self.g(repo, "init", "-q", "-b", "main")
        return repo

    def test_clone_con_origin_uguale_a_main_non_riammette_upstream(self):
        src = self.init("src")
        first = self.commit(src, "uno")
        work = self.path("work")
        gitgraph.git(self.tmp.name, "clone", "-q", src, work)
        self.assertEqual(self.g(work, "rev-parse", "HEAD").strip(), first)
        upstream = self.init("upstream")
        self.commit(upstream, "solo upstream")
        self.g(work, "remote", "add", "upstream", upstream)
        self.g(work, "fetch", "-q", "upstream")

        commits, _, _, tips, _ = gitgraph.read_graph(work, 300)
        self.assertEqual(list(commits), [first])
        self.assertEqual(tips, [("main", first)])
        warnings = []
        gitgraph.render(commits, {first: "a1"}, {}, tips, warn=warnings.append)
        self.assertEqual(warnings, [])

    def test_commit_raggiungibile_solo_da_un_tag_resta_nella_finestra(self):
        repo = self.init("tag")
        self.commit(repo, "uno")
        tree = self.g(repo, "rev-parse", "HEAD^{tree}").strip()
        only_tag = self.g(repo, "commit-tree", tree, "-m", "solo tag").strip()
        self.g(repo, "tag", "solo", only_tag)

        commits, _, tags, tips, _ = gitgraph.read_graph(repo, 300)
        self.assertIn(only_tag, commits)
        out = gitgraph.render(commits, {h: h[:7] for h in commits}, tags, tips)
        self.assertIn(f'commit id: "{only_tag[:7]}"', "\n".join(out))


class ReadGraphParsingTest(unittest.TestCase):
    """P2-07: campi del log separati da SEP e ref senza unpacking fragile."""

    S = "\x1f"  # gitgraph.SEP: il formato del log e' un contratto, non un dettaglio interno

    def read(self, log, refs="tag v1 A1 A1\n"):
        # ordine delle chiamate a git in read_graph(): worktree, heads, remotes, log, tag, HEAD
        with mock.patch.object(gitgraph, "git",
                               side_effect=["true\n", "refs/heads/main a1 \n", "", log,
                                            refs, "main\n"]):
            return gitgraph.read_graph(".", 10)

    def test_subject_con_pipe_intatto(self):
        commits, _, _, tips, _ = self.read(f"a1{self.S}A1{self.S}{self.S}fix | tabella\n")
        self.assertEqual(commits["A1"], ([], "fix | tabella"))
        self.assertEqual(tips, [("main", "a1")])

    def test_campo_in_piu_resta_nel_subject(self):
        # maxsplit: il resto del log e' soggetto, mai un ValueError da unpacking
        commits = self.read(f"a1{self.S}A1{self.S}{self.S}a{self.S}b\n")[0]
        self.assertEqual(commits["A1"], ([], f"a{self.S}b"))

    def test_subject_con_separatore_di_riga_resta_una_sola_riga(self):
        # splitlines() spezzava anche su \x0b: la coda senza SEP era un ValueError
        commits = self.read(f"a1{self.S}A1{self.S}{self.S}prima\x0bdopo\n")[0]
        self.assertEqual(commits, {"A1": ([], "prima\x0bdopo")})
        self.assertEqual(gitgraph.label(commits["A1"][1]), "prima dopo")

    def test_riga_troncata_e_un_errore_leggibile(self):
        with self.assertRaisesRegex(gitgraph.GitError, "log git non interpretabile"):
            self.read(f"a1{self.S}A1{self.S}\n")

    def test_tag_con_spazio_e_un_errore_leggibile(self):
        # git non crea un ref con spazio (check-ref-format): il formato si prova diretto
        for refs in ("commit release 1.0 A1 A1\n", "commit release 1.0 A1 \n"):
            with self.assertRaises(gitgraph.GitError) as cm:
                self.read(f"a1{self.S}A1{self.S}{self.S}s\n", refs)
            self.assertIn("tag non interpretabile", str(cm.exception))

    def test_tag_annotato_mappato_sul_commit(self):
        tags = self.read(f"a1{self.S}A1{self.S}{self.S}s\n")[2]
        self.assertEqual(tags, {"A1": ["v1"]})


class OutputPathTest(unittest.TestCase):
    """P1-06: path di uscita invalido -> una riga su stderr ed exit 1; scrittura atomica."""

    def test_check_out_valido_non_esce(self):
        with tempfile.TemporaryDirectory() as d:
            gitgraph.check_out(os.path.join(d, "grafo.mmd"))  # nessun SystemExit

    def test_check_out_directory_inesistente(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "manca", "grafo.mmd")
            with self.assertRaises(SystemExit) as cm:
                gitgraph.check_out(path)
        self.assertIsInstance(cm.exception.code, str)
        self.assertIn("directory inesistente", cm.exception.code)
        self.assertIn(path, cm.exception.code)

    def test_check_out_path_e_una_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                gitgraph.check_out(d)
        self.assertIn("e' una directory", cm.exception.code)

    def test_o_su_directory_inesistente_messaggio_cli(self):
        with tempfile.TemporaryDirectory() as d:
            argv = ["gitgraph.py", ".", "-o", os.path.join(d, "manca", "g.mmd")]
            with mock.patch.object(gitgraph.sys, "argv", argv):
                with self.assertRaises(SystemExit) as cm:
                    gitgraph.main()
        self.assertIsInstance(cm.exception.code, str)  # non un traceback
        self.assertIn("directory inesistente", cm.exception.code)

    def test_png_su_directory_inesistente_non_arriva_a_git(self):
        # il difetto era: mmdc falliva e l'errore vero restava nascosto
        with tempfile.TemporaryDirectory() as d:
            argv = ["gitgraph.py", ".", "--png", os.path.join(d, "manca", "g.png")]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph") as read:
                with self.assertRaises(SystemExit) as cm:
                    gitgraph.main()
        read.assert_not_called()
        self.assertIn("directory inesistente", cm.exception.code)

    def test_png_valido_arriva_al_render(self):
        with tempfile.TemporaryDirectory() as d:
            png = os.path.join(d, "g.png")
            argv = ["gitgraph.py", ".", "--png", png]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph",
                                      return_value=linear_fixture() + ({}, [], "")), \
                    mock.patch.object(gitgraph, "render_png") as render_png, \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                gitgraph.main()  # nessun SystemExit, riga alt su stdout
        self.assertEqual(render_png.call_args[0][1], png)

    def test_write_atomic_contenuto_esatto_e_nessun_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "grafo.mmd")
            gitgraph.write_atomic(path, "gitGraph\n")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "gitGraph\n")
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_write_atomic_sovrascrive_senza_append(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "grafo.mmd")
            gitgraph.write_atomic(path, "vecchio contenuto piu' lungo\n")
            gitgraph.write_atomic(path, "nuovo\n")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "nuovo\n")

    def test_replace_fallito_lascia_il_file_intatto_e_nessun_tmp(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "grafo.mmd")
            gitgraph.write_atomic(path, "vecchio\n")
            with mock.patch.object(gitgraph.os, "replace",
                                   side_effect=OSError(28, "No space left on device")):
                with self.assertRaises(SystemExit) as cm:
                    gitgraph.write_atomic(path, "nuovo\n")
            self.assertIn("scrittura fallita", cm.exception.code)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "vecchio\n")  # niente troncamento
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_interrupt_a_meta_scrittura_non_lascia_tmp_orfano(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "grafo.mmd")
            gitgraph.write_atomic(path, "vecchio\n")
            with mock.patch.object(gitgraph.os, "replace", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    gitgraph.write_atomic(path, "nuovo\n")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "vecchio\n")
            self.assertFalse(os.path.exists(path + ".tmp"))


class InitDirectiveTest(unittest.TestCase):
    """P2-13: palette alto contrasto, showCommitLabel e font sono nella direttiva init."""

    def payload(self, line):
        return json.loads(line[len("%%{init: "):-len("}%%")])

    def test_palette_contrasto_e_show_commit_label(self):
        payload = self.payload(gitgraph.init_directive("main"))
        self.assertEqual(payload["theme"], gitgraph.THEME_DEFAULT)
        self.assertEqual(payload["gitGraph"],
                         {"mainBranchName": "main", "showCommitLabel": True})
        self.assertEqual(payload["themeVariables"]["git0"], "#0b4f9c")
        self.assertEqual(payload["themeVariables"]["fontSize"],
                         f"{gitgraph.FONT_DEFAULT}px")

    def test_tema_e_font_scelti_dall_utente(self):
        payload = self.payload(gitgraph.init_directive("develop", theme="dark", font=22))
        self.assertEqual(payload["theme"], "dark")
        self.assertEqual(payload["themeVariables"]["fontSize"], "22px")

    def test_render_propaga_tema_e_font(self):
        commits, short = linear_fixture()
        out = gitgraph.render(commits, short, {}, [], linear=True, head="main",
                              theme="forest", font=20)
        payload = self.payload(out[0])
        self.assertEqual(payload["theme"], "forest")
        self.assertEqual(payload["themeVariables"]["fontSize"], "20px")


class PNGOutputTest(unittest.TestCase):
    """P2-13: --png stampa la riga alt e propaga width, tema e font al render."""

    def run_png(self, *args):
        with tempfile.TemporaryDirectory() as d:
            png = os.path.join(d, "grafo.png")
            argv = ["gitgraph.py", ".", "--png", png, *args]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph",
                                      return_value=linear_fixture() + ({}, [], "")), \
                    mock.patch.object(gitgraph, "render_png") as render_png, \
                    contextlib.redirect_stdout(io.StringIO()) as out, \
                    contextlib.redirect_stderr(io.StringIO()):
                gitgraph.main()
        return out.getvalue(), render_png.call_args

    def test_riga_alt_su_stdout(self):
        out, call = self.run_png()
        self.assertEqual(out, "![Storia git: 3 commit su 1 ramo](grafo.png)\n")
        self.assertTrue(call[0][1].endswith("grafo.png"))  # render_png riceve il path

    def test_leve_propagate_al_render(self):
        _, call = self.run_png("--width", "800", "--theme", "dark", "--font", "20")
        self.assertEqual(call[0][2], 800)  # width
        self.assertEqual(call[0][3], "#1e1e1e")  # sfondo del tema dark

    def test_width_o_font_non_positivi_sono_errori(self):
        for flag in ("--width", "--font"):
            argv = ["gitgraph.py", ".", "--png", "g.png", flag, "0"]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph") as read, \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    gitgraph.main()
            self.assertEqual(cm.exception.code, 2)
            read.assert_not_called()


class SandboxGateTest(unittest.TestCase):
    """P2-02: sandbox Chromium attiva di default; GITGRAPH_NO_SANDBOX=1 e' l'unico gate."""

    def render(self, env_value):
        captured = {}

        def fake_run(argv, **kwargs):
            with open(argv[argv.index("-p") + 1], encoding="utf-8") as f:
                captured["config"] = json.load(f)
            with open(argv[argv.index("-o") + 1], "w", encoding="utf-8") as f:
                f.write("png")
            return gitgraph.subprocess.CompletedProcess(argv, 0, "", "")

        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {gitgraph.NO_SANDBOX_ENV: env_value}), \
                mock.patch.object(gitgraph.shutil, "which", return_value="/finto/mmdc"), \
                mock.patch.object(gitgraph, "chrome_bin", return_value="/finto/chrome"), \
                mock.patch.object(gitgraph.subprocess, "run", side_effect=fake_run):
            gitgraph.render_png("gitGraph\n", os.path.join(d, "out.png"))
        return captured["config"]

    def test_sandbox_attiva_di_default(self):
        for value in ("", "0", "true"):
            with self.subTest(value=value):
                self.assertEqual(self.render(value)["args"], [])

    def test_flag_esplicito_disattiva_la_sandbox(self):
        config = self.render("1")
        self.assertEqual(config["args"], ["--no-sandbox", "--disable-setuid-sandbox"])
        self.assertEqual(config["executablePath"], "/finto/chrome")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Unit test della logica pura di gitgraph.py (render) e degli errori tipizzati.

Fixture = dict letterali con la stessa forma dei dati letti da git, cosi' i test
non dipendono da git ne' dal filesystem (unica eccezione: il caso GitError).
    python3 -m unittest discover -s skills/gitgraph/tests
"""

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
    return f'%%{{init: {{"gitGraph": {{"mainBranchName": "{name}"}}}}}}%%'


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
        self.assertEqual(warnings, ["warning: 2 commit fuori dalle catene principali\n"])
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
        self.assertNotIn("t2", "\n".join(out))

    def test_virgolette_nel_subject_rese(self):
        commits = {"c1": ([], 'fix "rotto" qui')}
        out = gitgraph.render(commits, {"c1": "a1"}, {}, [], linear=True, head="main")
        self.assertEqual(out[2], '    commit id: "a1" tag: "fix \'rotto\' qui"')


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
        with mock.patch.object(gitgraph, "git", side_effect=["true\n", ""]):
            with self.assertRaisesRegex(gitgraph.GitError, "nessun commit trovato"):
                gitgraph.read_graph(".", 10)

    def test_main_traduce_giterror_in_exit(self):
        with mock.patch.object(gitgraph.sys, "argv", ["gitgraph.py", "."]), \
                mock.patch.object(gitgraph, "read_graph",
                                  side_effect=gitgraph.GitError("boom")):
            with self.assertRaises(SystemExit) as cm:
                gitgraph.main()
        self.assertEqual(cm.exception.code, "boom")


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

    def test_png_valido_ignora_o_invalido(self):
        # --png vince su -o: validare un path che main() ignora bloccherebbe il lavoro buono
        with tempfile.TemporaryDirectory() as d:
            png = os.path.join(d, "g.png")
            argv = ["gitgraph.py", ".", "--png", png,
                    "-o", os.path.join(d, "manca", "g.mmd")]
            with mock.patch.object(gitgraph.sys, "argv", argv), \
                    mock.patch.object(gitgraph, "read_graph",
                                      return_value=linear_fixture() + ({}, [], "")), \
                    mock.patch.object(gitgraph, "render_png") as render_png:
                gitgraph.main()  # nessun SystemExit
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


if __name__ == "__main__":
    unittest.main()

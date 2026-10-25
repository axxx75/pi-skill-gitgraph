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


if __name__ == "__main__":
    unittest.main()

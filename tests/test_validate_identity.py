"""Install-time identity gate (briefing-lifecycle audit, stage-(i) — gate root-cause #4).

`_validate` let a lobotomized edge report HEALTHY because it never composed the briefing nor
asserted identity. Per docs/briefing-lifecycle-audit.md stage-(i), HEALTHY must imply the edge has
its initial tattoos (Personality + Method), the Idiom glossary floor (← ground_truth.documents),
and the REAL declared Source roster — and the log-fed sections render their honest empty markers.

`check_identity` composes the briefing (briefing.compose_briefing, the single fail-closed gate): a
raised BriefingIdentityError (thin agent.yaml identity, absent doctrine, all-missing ground_truth,
empty/malformed source roster) → ok=False; on success it asserts the four REQUIRED sections are
present + non-empty, and that the log-fed empty markers render (compose did not crash). It returns a
("identity", ok, detail) triple like the other checks, so a failure makes the install NOT HEALTHY.

Pure: tmp dirs + a throwaway log only; no real venv / neo4j (CONTRACT C1 — never real state/).
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _validate    # noqa: E402


def _complete_agent_yaml(p):
    """A genotype agent.yaml with full identity + a declared source + a ground_truth document — the
    stage-(i) floor (mirrors the real install: identity, sources, ground_truth.documents)."""
    canon = p.parent / "CONTEXT.md"
    canon.write_text("# Canon\n\n**beat** — the mentor's work cycle (the live glossary term).")
    p.write_text(textwrap.dedent("""\
        name: ed
        mission: "Mentor to the edge-of-chaos PM."
        voice: "Direct, technical, skeptical."
        sources:
          - name: exa
            kind: api
            description: "Neural/semantic web + paper search."
        ground_truth:
          inject_into_load: true
          documents:
        """) + f'    - "{canon}"\n')
    return p


def _genotype_memory(home):
    """The genotype doctrine docs + an empty state/ — the fail-closed inputs compose requires."""
    mem = home / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    (mem / "personality.md").write_text("# Personality — ed\n\nAnalytical and skeptical.")
    (mem / "method.md").write_text("# Feynman Method\n\nDerive before researching.")
    (mem / "canone.md").write_text("# O cânone\n\nO report do DSPy — visto e amplificado.")
    (home / "state").mkdir(parents=True, exist_ok=True)
    return mem


def _thin_agent_yaml(p):
    """A lobotomized agent.yaml: no identity fields, no ground_truth, no sources — the kind of
    install the gate must catch so it never reaches HEALTHY."""
    p.write_text("graph_group: x\n")
    return p


class IdentityGateFailsTheLobotomy(unittest.TestCase):
    """A thin agent.yaml (missing identity / no ground_truth / no sources) → check_identity FAILs,
    and validate_install therefore does NOT report HEALTHY (the lobotomy is caught up front)."""

    def test_thin_agent_yaml_makes_check_identity_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = _thin_agent_yaml(home / "agent.yaml")
            log = home / "log.jsonl"
            name, ok, detail = _validate.check_identity(
                home, {}, agent_yaml=ay, memory=mem, log=log)
            self.assertEqual(name, "identity")
            self.assertFalse(ok)                              # fail-closed → ok is False
            self.assertTrue(detail)                           # carries the BriefingIdentityError message

    def test_validate_install_not_healthy_on_thin_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = _thin_agent_yaml(home / "agent.yaml")
            log = home / "log.jsonl"
            for sub in ("blog/entries", "state", "memory", "threads", "secrets"):
                (home / sub).mkdir(parents=True, exist_ok=True)
            checks = _validate.validate_install(
                home, {"sources": [], "routers": {}}, home / "secrets", provisioned=False,
                agent_yaml=ay, memory=mem, log=log)
            by = {c[0]: c for c in checks}
            self.assertIn("identity", by)
            self.assertFalse(by["identity"][1])              # identity check failed
            _, healthy = _validate.format_report(checks)
            self.assertFalse(healthy)                         # → install NOT HEALTHY

    def test_absent_doctrine_fails_closed(self):
        # personality/method docs missing → BriefingIdentityError → identity FAIL
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "memory").mkdir(parents=True, exist_ok=True)   # empty memory/, no docs
            (home / "state").mkdir(parents=True, exist_ok=True)
            ay = _complete_agent_yaml(home / "agent.yaml")
            name, ok, detail = _validate.check_identity(
                home, {}, agent_yaml=ay, memory=home / "memory", log=home / "log.jsonl")
            self.assertFalse(ok)
            self.assertIn("doctrine", detail.lower())


class IdentityGateFailsClosedOnAnyComposeException(unittest.TestCase):
    """Gate finding (1): check_identity must fail CLOSED on ANY compose exception, not only the
    typed BriefingIdentityError. A non-typed failure (e.g. an AttributeError from a malformed
    config) used to return ok=None — advisory — which format_report counts as non-failing →
    HEALTHY. ANY import/compose exception is a FAIL (ok=False), never a downgrade to advisory."""

    def test_non_typed_compose_exception_makes_check_identity_fail_not_advisory(self):
        # force compose_briefing to raise a generic (non-BriefingIdentityError) exception
        sys.path.insert(0, str(REPO / "tools"))
        import briefing
        orig = briefing.compose_briefing
        briefing.compose_briefing = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("boom — a non-typed compose failure"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                mem = _genotype_memory(home)
                ay = _complete_agent_yaml(home / "agent.yaml")
                name, ok, detail = _validate.check_identity(
                    home, {}, agent_yaml=ay, memory=mem, log=home / "log.jsonl")
                self.assertEqual(name, "identity")
                self.assertIs(ok, False)         # FAIL closed, NOT None (advisory)
                self.assertTrue(detail)
        finally:
            briefing.compose_briefing = orig

    def test_non_typed_compose_exception_makes_install_not_healthy(self):
        sys.path.insert(0, str(REPO / "tools"))
        import briefing
        orig = briefing.compose_briefing
        briefing.compose_briefing = lambda *a, **k: (_ for _ in ()).throw(
            AttributeError("'str' object has no attribute 'get'"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                mem = _genotype_memory(home)
                ay = _complete_agent_yaml(home / "agent.yaml")
                for sub in ("blog/entries", "state", "memory", "threads", "secrets"):
                    (home / sub).mkdir(parents=True, exist_ok=True)
                checks = _validate.validate_install(
                    home, {"sources": [], "routers": {}}, home / "secrets", provisioned=False,
                    agent_yaml=ay, memory=mem, log=home / "log.jsonl")
                by = {c[0]: c for c in checks}
                self.assertIs(by["identity"][1], False)       # identity FAIL, not advisory
                _, healthy = _validate.format_report(checks)
                self.assertFalse(healthy)                     # → install NOT HEALTHY
        finally:
            briefing.compose_briefing = orig

    def test_non_list_sources_in_agent_yaml_fails_via_check_identity(self):
        # the integration of finding (2)+(1): a non-list `sources:` in the ACTUAL agent.yaml
        # reaches source_roster during compose; it must surface as an identity FAIL (not advisory,
        # not HEALTHY) whether the typed raise or the broad catch fires.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = home / "agent.yaml"
            (home / "CONTEXT.md").write_text("# Canon\n\n**beat** — term.")
            ay.write_text(textwrap.dedent("""\
                name: ed
                mission: "Mentor."
                voice: "Direct."
                sources: just-a-string
                ground_truth:
                  documents:
                """) + f'    - "{home / "CONTEXT.md"}"\n')
            name, ok, detail = _validate.check_identity(
                home, {}, agent_yaml=ay, memory=mem, log=home / "log.jsonl")
            self.assertEqual(name, "identity")
            self.assertIs(ok, False)
            self.assertTrue(detail)


class ValidateInstallThreadsTheAppliedAgentYaml(unittest.TestCase):
    """Gate finding (3): validate_install must accept an `agent_yaml` path and thread it down to
    check_identity (→ compose/source_roster), so edge-apply validates the ACTUAL applied config,
    not the checkout default. A thin temp agent.yaml threaded through → identity FAIL; a complete
    one → identity OK."""

    def test_thin_agent_yaml_threaded_through_validate_install_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = _thin_agent_yaml(home / "agent.yaml")
            for sub in ("blog/entries", "state", "memory", "threads", "secrets"):
                (home / sub).mkdir(parents=True, exist_ok=True)
            checks = _validate.validate_install(
                home, {"sources": [], "routers": {}}, home / "secrets", provisioned=False,
                agent_yaml=ay, memory=mem, log=home / "log.jsonl")
            by = {c[0]: c for c in checks}
            self.assertIs(by["identity"][1], False)           # thin applied config → identity FAIL
            _, healthy = _validate.format_report(checks)
            self.assertFalse(healthy)

    def test_complete_agent_yaml_threaded_through_validate_install_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = _complete_agent_yaml(home / "agent.yaml")
            for sub in ("blog/entries", "state", "memory", "threads", "secrets"):
                (home / sub).mkdir(parents=True, exist_ok=True)
            checks = _validate.validate_install(
                home, {"sources": [], "routers": {}}, home / "secrets", provisioned=False,
                agent_yaml=ay, memory=mem, log=home / "log.jsonl")
            by = {c[0]: c for c in checks}
            self.assertIs(by["identity"][1], True)            # complete applied config → identity OK


class IdentityGatePassesTheCompleteGenotype(unittest.TestCase):
    """A complete genotype + agent.yaml (identity + ground_truth + sources + docs) → check_identity
    OK, and validate_install reports HEALTHY: the four REQUIRED sections render non-empty and the
    log-fed sections render their honest empty markers (compose did not crash)."""

    def test_complete_genotype_check_identity_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = _complete_agent_yaml(home / "agent.yaml")
            name, ok, detail = _validate.check_identity(
                home, {}, agent_yaml=ay, memory=mem, log=home / "log.jsonl")
            self.assertEqual(name, "identity")
            self.assertTrue(ok)
            self.assertIn("identity composed", detail.lower())

    def test_validate_install_healthy_on_complete_genotype(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            mem = _genotype_memory(home)
            ay = _complete_agent_yaml(home / "agent.yaml")
            for sub in ("blog/entries", "state", "memory", "threads", "secrets"):
                (home / sub).mkdir(parents=True, exist_ok=True)
            (home / "skills").mkdir(parents=True, exist_ok=True)
            (home / "blog").mkdir(parents=True, exist_ok=True)
            (home / "blog" / "server.py").write_text("# blog\n")
            checks = _validate.validate_install(
                home, {"sources": [], "routers": {}}, home / "secrets", provisioned=False,
                agent_yaml=ay, memory=mem, log=home / "log.jsonl")
            by = {c[0]: c for c in checks}
            self.assertTrue(by["identity"][1])               # identity OK
            _, healthy = _validate.format_report(checks)
            self.assertTrue(healthy)                          # → INSTALL HEALTHY


class IdentityGateAssertsTheStageISections(unittest.TestCase):
    """On a successful compose, check_identity must catch a MISSING required section even if the
    composer did not raise — the gate asserts the stage-(i) sections itself (Personality, Method,
    the Idiom floor, the real Source roster), and that the log-fed empty markers rendered."""

    def test_missing_required_section_in_composed_text_fails(self):
        # a composed text lacking a required section header → FAIL (the assert leg, not the raise leg)
        captured = "## Idiom — the mentee's terms\n\n**beat** — term.\n## 4. Source orientation\n- exa"
        name, ok, detail = _validate._assert_identity_sections(captured)
        self.assertFalse(ok)
        self.assertIn("personality", detail.lower())

    def test_complete_composed_text_passes_the_assert(self):
        good = ("### Personality\n\nx\n### Method\n\ny\n"
                "## Idiom — the mentee's terms\n\n**beat** — term.\n"
                "## 4. Source orientation\n\n**Declared roster**\n- **exa** (api) — exa\n"
                "## Objective — the anchor\n\n_no confirmed objective yet._\n"
                "## 1. Direction\n\n_no direction set yet._\n"
                "## Direcionamento — the rolling steer\n\n_no direcionamento report yet._\n"
                "## 3. Corpus — what I already did\n\n_no corpus yet._\n")
        name, ok, detail = _validate._assert_identity_sections(good)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)

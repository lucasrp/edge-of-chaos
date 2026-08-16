"""S3 (grounding iteration) — agent.yaml sources[].interfaces[] + acts: (E3), roadmap replaced (E5).

E3: the freeform `via` seam is superseded by a structured, read-only `interfaces[]` list per
source — {interface_id, via, idiom?, canary?, dry_semantics?} — and a separate top-level `acts:`
section (HITL, e.g. gdrive-upload) that the harvester NEVER reads. Recognizers (S4) and the
canary battery (S5) derive from interfaces[].via / interfaces[].canary; the prose description
stays free (the briefing's never-blank floor is untouched).

The loader (tools/sources.py) is doctor-style: it COLLECTS findings (warnings/errors), never
raises on shape problems — a source without interfaces is a DECLARED degradation (warning), an
act smuggled into sources[] is an ERROR collected, an interface declared without its key
installed is a VISIBLE dead leg (warning), never a silent one.

E5: state/source-roadmap.md is REPLACED (stale file from another era — vboxuser HOME, xai route
as THE x route). The new skeleton: roster rendered from agent.yaml truth (never-blank floor),
measured idiom/canary rows (R2.5/R2.6), operator intent priors, yield seed lines with provenance
seed:loopR-2026-07-01 (R4.5), and NO Voz anywhere in the roster (Voz is directive, not a read).
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import sources  # noqa: E402

# O fenotipo e OUTPUT do onboarding e e gitignored: no genotipo nao existe, e a classe
# RealAgentYaml morria com FileNotFoundError antes de validar qualquer coisa. A fixture
# versionada e um roster completo e igual em qualquer host, entao o que se mede volta a
# ser o VALIDADOR (canary, idiom, secret_ref, acts fora de sources) em vez da instalacao
# de quem apertou enter.
AGENT_YAML = REPO / "tests" / "fixtures" / "roster.agent.yaml"
ROADMAP = REPO / "state" / "source-roadmap.md"


def _write_yaml(tmp, text):
    p = Path(tmp) / "agent.yaml"
    p.write_text(textwrap.dedent(text))
    return p


def _errors(findings):
    return [f for f in findings if f["level"] == "error"]


def _warnings(findings):
    return [f for f in findings if f["level"] == "warning"]


class LoaderValidSchema(unittest.TestCase):
    """A well-formed source with interfaces loads whole: canary/idiom/dry_semantics readable
    per interface, zero error findings."""

    YAML = """
    name: t
    sources:
      - name: pond
        kind: api
        secret_ref: pond.env:POND_KEY
        description: a test pond
        interfaces:
          - interface_id: skim
            via: "GET https://pond.example/skim?q=..."
            idiom:
              max_terms: 3
              style: "short queries"
            canary:
              query: "frog"
              params: {max_results: 10}
              pass_when: "hit_count == 10"
            dry_semantics: false-dry-prone
          - interface_id: dive
            via: "POST https://pond.example/dive"
    """

    def test_interfaces_parse_with_canary_idiom_dry_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, self.YAML))
        self.assertEqual(_errors(findings), [])
        self.assertEqual([s["name"] for s in srcs], ["pond"])
        ifaces = {i["interface_id"]: i for i in srcs[0]["interfaces"]}
        self.assertEqual(set(ifaces), {"skim", "dive"})
        skim = ifaces["skim"]
        self.assertEqual(skim["via"], "GET https://pond.example/skim?q=...")
        self.assertEqual(skim["idiom"]["max_terms"], 3)
        self.assertEqual(skim["canary"]["query"], "frog")
        self.assertEqual(skim["canary"]["params"]["max_results"], 10)
        self.assertEqual(skim["canary"]["pass_when"], "hit_count == 10")
        self.assertEqual(skim["dry_semantics"], "false-dry-prone")
        # optional fields absent → None / default, never KeyError (S4/S5 read them blind)
        dive = ifaces["dive"]
        self.assertIsNone(dive["idiom"])
        self.assertIsNone(dive["canary"])
        self.assertIsNone(dive["dry_semantics"])
        self.assertTrue(dive["installed"])

    def test_source_prose_fields_pass_through(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, _ = sources.load_sources(_write_yaml(td, self.YAML))
        self.assertEqual(srcs[0]["kind"], "api")
        self.assertEqual(srcs[0]["secret_ref"], "pond.env:POND_KEY")
        self.assertEqual(srcs[0]["description"], "a test pond")


class LoaderDegradesDeclared(unittest.TestCase):
    """Doctor-style: shape problems are COLLECTED, never raised."""

    def test_source_without_interfaces_is_legacy_tolerated_with_warning(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: legacy
                kind: api
                description: an old-style source
                via: "GET https://old.example"
            """))
        self.assertEqual([s["name"] for s in srcs], ["legacy"])      # stays valid
        self.assertEqual(srcs[0]["interfaces"], [])                  # declared degradation
        self.assertEqual(_errors(findings), [])
        self.assertTrue(any("legacy" in w["where"] and "interfaces" in w["msg"]
                            for w in _warnings(findings)))

    def test_act_inside_sources_is_an_error_collected_not_raised(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: reader
                kind: api
                description: a legit read source
                interfaces:
                  - {interface_id: pull, via: "GET https://x.example"}
              - name: sneaky-upload
                kind: cli
                description: a write pretending to be a read
                hitl: true
                interfaces:
                  - interface_id: push
                    via: "rclone copy local remote:"
            """))
        errs = _errors(findings)
        self.assertTrue(any("act" in e["msg"].lower() for e in errs), errs)
        # the act-shaped entry is DROPPED from the read roster — no write via may exit in
        # src["interfaces"] by ANY path (E3/R1.3: S4 derives recognizers from exactly that list)
        self.assertEqual([s["name"] for s in srcs], ["reader"])
        every_iface = [i for s in srcs for i in s["interfaces"]]
        self.assertNotIn("push", [i["interface_id"] for i in every_iface])
        self.assertFalse(any("rclone copy" in i["via"] for i in every_iface))

    def test_write_interface_inside_sources_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: mixed
                kind: cli
                description: read source with a smuggled write leg
                interfaces:
                  - interface_id: read-ok
                    via: "rclone ls remote:"
                  - interface_id: push
                    via: "rclone copy local remote:"
                    mode: write
            """))
        errs = _errors(findings)
        self.assertTrue(any("act" in e["msg"].lower() for e in errs), errs)
        # the read leg survives; the write leg never enters the read-only list
        ids = [i["interface_id"] for i in srcs[0]["interfaces"]]
        self.assertIn("read-ok", ids)
        self.assertNotIn("push", ids)

    def test_malformed_interface_dropped_with_error(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: holey
                kind: api
                description: has one good and one broken interface
                interfaces:
                  - interface_id: good
                    via: "GET https://x.example"
                  - interface_id: no-via
            """))
        self.assertEqual([i["interface_id"] for i in srcs[0]["interfaces"]], ["good"])
        self.assertTrue(_errors(findings))

    def test_unknown_dry_semantics_is_a_warning_value_kept_visible(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: odd
                kind: api
                description: bad enum
                interfaces:
                  - interface_id: i
                    via: "GET https://x.example"
                    dry_semantics: sometimes-dry
            """))
        self.assertEqual(_errors(findings), [])
        self.assertTrue(any("dry_semantics" in w["msg"] for w in _warnings(findings)))
        self.assertEqual(srcs[0]["interfaces"][0]["dry_semantics"], "sometimes-dry")

    def test_duplicate_interface_id_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: dup
                kind: api
                description: duplicated id
                interfaces:
                  - {interface_id: same, via: "GET a"}
                  - {interface_id: same, via: "GET b"}
            """))
        self.assertTrue(any("same" in e["msg"] for e in _errors(findings)))

    def test_missing_file_and_missing_sources_collect_not_raise(self):
        srcs, findings = sources.load_sources(Path("/nonexistent/agent.yaml"))
        self.assertEqual(srcs, [])
        self.assertTrue(_errors(findings))
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, "name: t\n"))
        self.assertEqual(srcs, [])
        self.assertTrue(_errors(findings))

    def test_interface_declared_without_key_installed_is_a_visible_dead_leg(self):
        with tempfile.TemporaryDirectory() as td:
            srcs, findings = sources.load_sources(_write_yaml(td, """
            sources:
              - name: bird
                kind: api
                secret_ref: bird.env:BIRD_KEY
                description: has an upgrade leg without its key
                interfaces:
                  - interface_id: v1
                    via: "GET https://bird.example/v1"
                  - interface_id: v2-fancy
                    via: "POST https://fancy.example"
                    secret_ref: fancy.env:FANCY_KEY
                    installed: false
            """))
        ifaces = {i["interface_id"]: i for i in srcs[0]["interfaces"]}
        self.assertFalse(ifaces["v2-fancy"]["installed"])            # visible in the list…
        self.assertTrue(any("v2-fancy" in w["msg"] for w in _warnings(findings)))  # …and flagged


class LoaderActs(unittest.TestCase):
    """acts: HITL-only writes, a separate book the harvester never reads (E1.3/E3)."""

    YAML = """
    sources:
      - name: r
        kind: cli
        description: read side
        interfaces:
          - {interface_id: ls, via: "rclone ls remote:"}
    acts:
      - name: r-upload
        via: "rclone copy <local> remote:<dest>"
        hitl: true
        description: "HITL only — rclone copy, NEVER the Drive MCP (hangs on uploads)"
    """

    def test_acts_load_separately_and_never_leak_into_sources(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_yaml(td, self.YAML)
            srcs, s_findings = sources.load_sources(p)
            acts, a_findings = sources.load_acts(p)
        self.assertEqual([a["name"] for a in acts], ["r-upload"])
        self.assertTrue(acts[0]["hitl"])
        self.assertEqual(_errors(a_findings), [])
        self.assertNotIn("r-upload", [s["name"] for s in srcs])

    def test_act_without_hitl_true_is_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            acts, findings = sources.load_acts(_write_yaml(td, """
            acts:
              - name: quiet-write
                via: "cp a b"
            """))
        self.assertTrue(any("hitl" in f["msg"].lower() for f in findings))

    def test_act_without_via_is_dropped_with_error(self):
        with tempfile.TemporaryDirectory() as td:
            acts, findings = sources.load_acts(_write_yaml(td, """
            acts:
              - name: no-via
                hitl: true
            """))
        self.assertEqual(acts, [])
        self.assertTrue(_errors(findings))

    def test_no_acts_section_is_fine(self):
        with tempfile.TemporaryDirectory() as td:
            acts, findings = sources.load_acts(_write_yaml(td, "name: t\n"))
        self.assertEqual(acts, [])
        self.assertEqual(_errors(findings), [])


class RealAgentYaml(unittest.TestCase):
    """The shipped agent.yaml under the new schema — the measured data of R2.5/R2.6 lives here."""

    @classmethod
    def setUpClass(cls):
        cls.srcs, cls.findings = sources.load_sources(AGENT_YAML)
        cls.by_name = {s["name"]: s for s in cls.srcs}

    def _iface(self, source, interface_id):
        for i in self.by_name[source]["interfaces"]:
            if i["interface_id"] == interface_id:
                return i
        self.fail(f"{source} has no interface {interface_id}")

    def test_roster_and_interfaces(self):
        self.assertEqual(_errors(self.findings), [])
        expect = {
            "exa": {"search-deep", "contents"},
            "x": {"v2-recent", "xai-responses"},
            "hn": {"algolia-search"},
            "arxiv": {"api-query"},
            "github": {"gh-cli"},
            "gdrive-consortium": {"rclone-read"},
        }
        for name, ifaces in expect.items():
            self.assertIn(name, self.by_name)
            self.assertEqual({i["interface_id"] for i in self.by_name[name]["interfaces"]},
                             ifaces, name)
        # no legacy-source warning: every shipped source is structured
        self.assertFalse(any("without" in w["msg"] and "interfaces" in w["msg"]
                             for w in _warnings(self.findings)))

    def test_exa_search_deep_never_dry_with_fast_canary(self):
        i = self._iface("exa", "search-deep")
        self.assertEqual(i["dry_semantics"], "never-dry")
        self.assertEqual(i["canary"]["params"]["type"], "fast")
        self.assertEqual(i["canary"]["params"]["numResults"], 1)

    def test_x_v2_recent_measured_idiom_and_canary(self):
        i = self._iface("x", "v2-recent")
        self.assertEqual(i["dry_semantics"], "false-dry-prone")
        self.assertEqual(i["idiom"]["max_terms"], 3)
        self.assertEqual(i["canary"]["query"], "AI lang:en -is:retweet")
        self.assertEqual(i["canary"]["params"]["max_results"], 10)
        self.assertIn("hit_count == 10", i["canary"]["pass_when"])

    def test_xai_responses_is_a_visible_dead_leg(self):
        i = self._iface("x", "xai-responses")
        self.assertFalse(i["installed"])
        self.assertTrue(any("xai-responses" in w["msg"] for w in _warnings(self.findings)))

    def test_arxiv_api_query_canary_and_https_idiom(self):
        i = self._iface("arxiv", "api-query")
        self.assertEqual(i["canary"]["params"]["search_query"], "cat:cs.CL")
        self.assertEqual(i["canary"]["params"]["sortBy"], "lastUpdatedDate")
        self.assertEqual(i["canary"]["params"]["max_results"], 1)
        self.assertTrue(i["idiom"]["https_only"])

    def test_gdrive_read_only_in_sources_upload_is_an_act(self):
        i = self._iface("gdrive-consortium", "rclone-read")
        self.assertNotIn("WRITE", i["via"])
        acts, findings = sources.load_acts(AGENT_YAML)
        self.assertEqual(_errors(findings), [])
        ups = [a for a in acts if a["name"] == "gdrive-upload"]
        self.assertEqual(len(ups), 1)
        self.assertTrue(ups[0]["hitl"])
        self.assertIn("rclone copy", ups[0]["via"])
        blob = ups[0]["via"] + (ups[0].get("description") or "")
        self.assertIn("MCP", blob)                                   # rclone-not-MCP warning kept

    def test_briefing_roster_still_composes_from_restructured_yaml(self):
        """The fail-closed briefing floor (name+kind+description) survives the restructure."""
        import briefing
        roster = briefing.source_roster(AGENT_YAML)
        names = [r["name"] for r in roster]
        for n in ("claude-sessions", "exa", "x", "hn", "arxiv", "github", "gdrive-consortium"):
            self.assertIn(n, names)

    def test_validate_required_refs_still_sees_api_secret_refs(self):
        import yaml as _yaml
        import _validate
        cfg = _yaml.safe_load(AGENT_YAML.read_text())
        refs = _validate._required_refs(cfg)
        self.assertIn("exa.env:EXA_API_KEY", refs)
        self.assertIn("keys.env:X_BEARER_TOKEN", refs)


class RoadmapReplaced(unittest.TestCase):
    """state/source-roadmap.md — the new machine-readable skeleton (E5, R8.1)."""

    @classmethod
    def setUpClass(cls):
        # state/source-roadmap.md e ESTADO DE INSTALL, nao artefato de genotipo: ele e escrito
        # pela operacao (linhas de yield datadas, intent priors, medicoes de canary) e por isso
        # legitimamente NAO existe num clone limpo. Antes, a classe inteira morria de
        # FileNotFoundError no setUpClass — um vermelho que so dizia "este host nao e um install".
        #
        # Pular aqui NAO e afrouxar: as assercoes seguem valendo integralmente onde o arquivo
        # existe. Fabricar um roadmap de fixture seria pior — o conteudo que estes testes cobram
        # (provenance seed:loopR-2026-07-01, o datapoint de reCAPTCHA, os priors do operador) e
        # historia operacional real, e inventa-la para ficar verde seria falsificar evidencia.
        if not ROADMAP.is_file():
            raise unittest.SkipTest(
                f"{ROADMAP} ausente — estado de install, nao de genotipo; as assercoes deste "
                "arquivo so sao aplicaveis num install real")
        cls.text = ROADMAP.read_text()
        cls.parsed = sources.parse_roadmap(cls.text)

    def test_roster_rendered_from_agent_yaml_truth(self):
        srcs, _ = sources.load_sources(AGENT_YAML)
        for s in srcs:
            self.assertIn(s["name"], self.parsed,
                          f"roadmap misses a declared source section: {s['name']}")

    def test_no_voz_anywhere_in_the_roster(self):
        self.assertNotIn("Voz", self.text)                           # E5: Voz is directive, not a read
        self.assertNotIn("voz", self.text.lower().replace("vozes", ""))

    def test_stale_era_markers_gone(self):
        self.assertNotIn("vboxuser", self.text)

    def test_seed_yield_rows_carry_provenance(self):
        notes = self.parsed["exa"]["yield_notes"]
        self.assertTrue(notes, "exa must carry the R4.5 seed datapoints")
        for n in notes:
            self.assertEqual(n["provenance"], "seed:loopR-2026-07-01")
        blob = " ".join(n["text"] for n in notes)
        self.assertIn("PMC", blob)                                   # the reCAPTCHA datapoint
        self.assertTrue("reCAPTCHA" in blob or "recaptcha" in blob.lower())

    def test_canary_spec_readable_per_measured_source(self):
        for name in ("x", "exa", "arxiv"):
            canary = self.parsed[name]["fields"].get("canary", "")
            self.assertIn("pass_when", canary, f"{name} canary spec must carry pass_when")
        # unmeasured sources declare honestly instead of inventing
        for name in ("hn", "github", "gdrive-consortium"):
            fields = self.parsed[name]["fields"]
            blob = " ".join(fields.values())
            self.assertIn("NOT YET MEASURED", blob, name)

    def test_operator_intent_priors_present(self):
        self.assertIn("exploração", self.parsed["x"]["fields"].get("intent priors", ""))
        self.assertIn("científico", self.parsed["arxiv"]["fields"].get("intent priors", ""))
        self.assertIn("deep-research", self.parsed["exa"]["fields"].get("intent priors", ""))

    def test_header_names_s8_deepening_and_regeneration_path(self):
        head = self.text.split("##", 1)[0]
        self.assertIn("S8", head)
        self.assertIn("agent.yaml", head)
        self.assertIn("tools/sources.py", head)


if __name__ == "__main__":
    unittest.main()

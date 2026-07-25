"""Ticket C — the `prototype` genus (interactive single-file HTML+JS Artefato) and its
STANDALONE publish path.

The live close path sanitizes raw-html (render.sanitize_raw_html strips <script>) — right for
every prose genus, fatal for an interactive page. The prototype genus therefore publishes its
page through a SEPARATE seam, `publisher.publish_prototype_page`: the single-file page lands
INTACT (script and all) at a CONTENT-ADDRESSED name (`<slug>.proto.<sha256[:12]>.html` under
blog/entries — served by the existing /e/ route, no server change), and the seam is restricted
to skill="prototype" so no other genus can ride raw script through it.

These tests pin: byte-intact script, content addressing (idempotent same-content, new address
on changed content, never an in-place overwrite), the genus restriction, slug/containment
safety, the zero-external-dep bar (single-file: no CDN/script-src/stylesheet/img/iframe from
the network; plain <a href> links stay legal), and the roster/descriptor/skill registration.
"""
import hashlib
import inspect
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import producer_descriptor as pd  # noqa: E402
import eventlog  # noqa: E402
import publisher  # noqa: E402
import cortex_config  # noqa: E402
import cortex_mcp  # noqa: E402

PAGE = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'><title>kuramoto</title>"
    "<style>body{margin:0}</style></head>"
    "<body><canvas id='c'></canvas>"
    "<script>const N=12; let phase=[...Array(N)].map((_,i)=>i); "
    "function step(k){ /* the coupling IS the lesson */ } step(0.5);</script>"
    "</body></html>"
)


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class StandalonePageLandsIntactAndContentAddressed(unittest.TestCase):
    def test_script_survives_byte_intact_at_content_addressed_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp)
            self.assertEqual(out.name, f"kuramoto-demo.proto.{_digest(PAGE)}.html")
            self.assertEqual(out.parent, Path(tmp).resolve())
            self.assertEqual(out.read_text(), PAGE)  # intact — the <script> untouched

    def test_same_content_is_idempotent_changed_content_is_a_new_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp)
            again = publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp)
            self.assertEqual(first, again)
            changed = PAGE.replace("k=0.5", "k=0.9").replace("step(0.5)", "step(0.9)")
            second = publisher.publish_prototype_page(
                "kuramoto-demo", changed, skill="prototype", blog_dir=tmp)
            self.assertNotEqual(first, second)          # immutable: never overwritten in place
            self.assertEqual(first.read_text(), PAGE)   # the old address still serves old bytes
            self.assertEqual(second.read_text(), changed)

    def test_differing_bytes_at_the_same_address_are_refused(self):
        # adversarial finding 4 (SINAL): a preseeded/tampered file at the content address must never
        # be served silently — the "link points to the reviewed bytes" claim depends on it.
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp)
            out.write_text(PAGE.replace("coupling IS the lesson", "gotcha"))  # tamper in place
            with self.assertRaises(ValueError):
                publisher.publish_prototype_page(
                    "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp)

    def test_proto_name_can_never_collide_with_a_close_published_entry(self):
        # normal entries are <slug>.html with SLUG_RE forbidding dots; the ".proto." infix
        # makes the two namespaces disjoint inside the same blog dir.
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp)
            self.assertIn(".proto.", out.name)
            self.assertFalse(publisher.SLUG_RE.match(out.stem))

    def test_standalone_page_records_a_first_class_asset_when_log_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp, log=log)
            assets = eventlog.artefato_assets_at(log=log)
            asset_slug = f"kuramoto-demo-proto-{_digest(PAGE)}"
            self.assertIn(asset_slug, assets)
            asset = assets[asset_slug]
            self.assertEqual(asset["kind"], "html")
            self.assertEqual(asset["role"], "prototype")
            self.assertEqual(asset["parent_slug"], "kuramoto-demo")
            self.assertEqual(Path(asset["path"]).name, out.name)

    def test_same_standalone_page_does_not_duplicate_the_asset_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp, log=log)
            publisher.publish_prototype_page(
                "kuramoto-demo", PAGE, skill="prototype", blog_dir=tmp, log=log)
            self.assertEqual(len(eventlog.read(types=["artefato.asset"], log=log)), 1)

    def test_javascript_asset_is_content_addressed_and_eventlogged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = publisher.publish_artifact_asset(
                "kuramoto-app", "console.log('ok');", kind="js", skill="prototype",
                parent_slug="kuramoto-demo", blog_dir=tmp, log=log)
            self.assertRegex(out.name, r"^kuramoto-app\.js\.[0-9a-f]{12}\.js$")
            assets = eventlog.artefato_assets_at(log=log)
            self.assertEqual(len(assets), 1)
            asset = next(iter(assets.values()))
            self.assertEqual(asset["kind"], "js")
            self.assertEqual(asset["media_type"], "text/javascript")
            self.assertEqual(asset["parent_slug"], "kuramoto-demo")


class TheSeamIsRosterWide(unittest.TestCase):
    """Ticket 05 supersedes the prototype-only restriction: JS/image are liberated in ANY
    genus (single-file is the one hard rule left), so every roster genus rides this seam;
    only an out-of-roster skill is refused (tests/test_three_act.py pins the roster leg)."""

    def test_out_of_roster_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            for skill in ("", "not-a-genus", None):
                with self.assertRaises(ValueError):
                    publisher.publish_prototype_page(
                        "kuramoto-demo", PAGE, skill=skill, blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_bad_slug_or_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for slug in ("../evil", "UPPER", "", "a/b", "dot.dot", None):
                with self.assertRaises(ValueError):
                    publisher.publish_prototype_page(
                        slug, PAGE, skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_a_fragment_is_refused_the_page_must_be_a_full_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                publisher.publish_prototype_page(
                    "frag", "<script>alert(1)</script>", skill="prototype", blog_dir=tmp)


class ZeroExternalDeps(unittest.TestCase):
    def _page_with(self, tag):
        return PAGE.replace("<canvas id='c'></canvas>", tag)

    def test_network_resource_loads_are_refused(self):
        offenders = [
            '<script src="https://cdn.example.com/three.min.js"></script>',
            "<link rel='stylesheet' href='http://example.com/x.css'>",
            '<img src="//example.com/x.png">',
            '<iframe src="https://example.com"></iframe>',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for tag in offenders:
                with self.assertRaises(ValueError, msg=tag):
                    publisher.publish_prototype_page(
                        "dep", self._page_with(tag), skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_a_plain_outbound_link_is_legal_it_is_not_a_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = self._page_with('<a href="https://example.com/paper">the paper</a>')
            out = publisher.publish_prototype_page(
                "linked", page, skill="prototype", blog_dir=tmp)
            self.assertEqual(out.read_text(), page)

    def test_external_fetch_import_and_css_import_are_refused(self):
        # 04-C follow-up (rubrica: single-file lint MECÂNICO): the attribute regex missed the
        # runtime/CSS loaders — fetch(), JS module import (the modern CDN vector: esm.run),
        # dynamic import(), CSS @import. All external (http/https/protocol-relative) → refused.
        offenders = [
            "<script>fetch('https://api.example.com/data.json')</script>",
            '<script>fetch("//cdn.example.com/x.json")</script>',
            "<script type='module'>import * as THREE from 'https://esm.run/three';</script>",
            "<script>import('https://cdn.example.com/mod.js')</script>",
            "<style>@import url('https://fonts.example.com/x.css');</style>",
            '<style>@import "//example.com/x.css";</style>',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for tag in offenders:
                with self.assertRaises(ValueError, msg=tag):
                    publisher.publish_prototype_page(
                        "dep", self._page_with(tag), skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_importmap_css_url_and_bare_module_loads_are_refused(self):
        # codex adversarial lint #2/#3/#4/#5 (SINAL): the modern CDN vectors the first two
        # regexes miss — inline importmap pointing at a CDN, CSS url()/unquoted @import url()
        # to the network, side-effect import and re-export from a CDN.
        offenders = [
            '<script type="importmap">{"imports":{"three":"https://esm.run/three"}}</script>',
            '<style>body{background:url("https://cdn.example.com/bg.png")}</style>',
            "<style>@font-face{font-family:X;src:url('https://fonts.gstatic.com/x.woff2')}</style>",
            "<style>@import url(https://fonts.example.com/x.css);</style>",
            '<script type="module">import "https://esm.run/polyfill";</script>',
            '<script type="module">export * from "https://esm.run/lib";</script>',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for tag in offenders:
                with self.assertRaises(ValueError, msg=tag):
                    publisher.publish_prototype_page(
                        "dep", self._page_with(tag), skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_data_uri_relative_fetch_and_local_import_stay_legal(self):
        # data-URI and inline are the genus' whole point; a same-page relative fetch is not a
        # NETWORK dependency (the lint is external-only, like the attribute leg).
        legal = [
            '<img src="data:image/png;base64,iVBORw0KGgo=">',
            "<script>fetch('data:application/json,{}')</script>",
            "<script>const importante = 1; // prose mentioning @import or fetch is fine</script>",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for i, tag in enumerate(legal):
                out = publisher.publish_prototype_page(
                    f"legal-{i}", self._page_with(tag), skill="prototype", blog_dir=tmp)
                self.assertTrue(out.exists(), msg=tag)


class PrototypeIsAFirstClassGenus(unittest.TestCase):
    def test_prototype_is_in_the_producer_roster(self):
        self.assertIn("prototype", publisher.PRODUCER_ROSTER)

    def test_prototype_declares_a_descriptor(self):
        # declaration-only registration (test_new_producer_is_declarative): the presentation
        # floor is empty — the page itself and the skill's semantic gates ARE the bar.
        self.assertEqual(pd.require_descriptor("prototype"), {"require": []})


class RunsCleanIsAVeto(unittest.TestCase):
    """04-C follow-up (rubrica: roda-sem-erro MECÂNICO, veto — hoje é rito, não veto). The
    publish seam takes an injected `run_errors_fn(page_html)` returning: a list of console/page
    errors (non-empty → VETO, nothing written), [] (clean → publish), or None (harness
    unavailable → honest degrade: OBSERVE, publish proceeds). The live adapter is
    publisher.headless_page_errors (playwright in the pw-venv), the default."""

    def test_console_or_page_errors_veto_the_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                publisher.publish_prototype_page(
                    "broken", PAGE, skill="prototype", blog_dir=tmp,
                    run_errors_fn=lambda html: ["pageerror: ReferenceError: foo is not defined"])
            self.assertEqual(list(Path(tmp).iterdir()), [])  # vetoed BEFORE anything lands

    def test_a_clean_run_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_prototype_page(
                "clean", PAGE, skill="prototype", blog_dir=tmp, run_errors_fn=lambda html: [])
            self.assertTrue(out.exists())

    def test_unavailable_harness_degrades_to_observe_not_veto(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_prototype_page(
                "degraded", PAGE, skill="prototype", blog_dir=tmp, run_errors_fn=lambda html: None)
            self.assertTrue(out.exists())  # observed, never vetoed

    def test_a_raising_harness_also_degrades_it_never_aborts_the_publish(self):
        # codex adversarial slice-3 #3 (SINAL): a BROKEN harness must behave like a MISSING one
        # (observe, publish) — only a page that PROVABLY errors is vetoed.
        def boom(page_html):
            raise RuntimeError("harness exploded")
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_prototype_page(
                "harness-broken", PAGE, skill="prototype", blog_dir=tmp, run_errors_fn=boom)
            self.assertTrue(out.exists())

    def test_the_live_headless_adapter_is_the_default(self):
        sig = inspect.signature(publisher.publish_prototype_page)
        self.assertIs(sig.parameters["run_errors_fn"].default, publisher.headless_page_errors)


class LiveHeadlessAdapter(unittest.TestCase):
    """Integration leg for publisher.headless_page_errors — skipped honestly when the pw-venv
    harness is not on this box (the adapter itself returns None then)."""

    @classmethod
    def setUpClass(cls):
        cls.clean = publisher.headless_page_errors(PAGE)
        if cls.clean is None:
            raise unittest.SkipTest("headless harness unavailable (degrade honesto)")

    def test_a_clean_page_reports_no_errors(self):
        self.assertEqual(self.clean, [])

    def test_a_throwing_script_is_reported(self):
        broken = PAGE.replace("step(0.5);", "step(0.5); nope.does.not.exist();")
        errors = publisher.headless_page_errors(broken)
        self.assertTrue(errors, "a ReferenceError must surface as a page error")

    def test_a_console_error_is_reported(self):
        noisy = PAGE.replace("step(0.5);", "step(0.5); console.error('boom');")
        errors = publisher.headless_page_errors(noisy)
        self.assertTrue(errors, "console.error must surface")

    def test_a_late_async_error_is_reported(self):
        # codex adversarial slice-3 #1 (SINAL): an error a few hundred ms after load (setTimeout,
        # nested rAF init) is the honest-producer bug this gate exists for — the settle window
        # must outlast it.
        late = PAGE.replace(
            "step(0.5);",
            "step(0.5); setTimeout(() => { throw new Error('late boom'); }, 350);")
        self.assertTrue(publisher.headless_page_errors(late),
                        "an error 350ms after load must surface")

    def test_a_funny_tmpdir_never_false_vetoes(self):
        # codex adversarial slice-3 #6 (SINAL): a TMPDIR with space/# must not truncate the
        # file:// URL and turn a good page into a load failure.
        old = tempfile.tempdir
        with tempfile.TemporaryDirectory() as base:
            funny = Path(base) / "with space#hash"
            funny.mkdir()
            tempfile.tempdir = str(funny)
            try:
                self.assertEqual(publisher.headless_page_errors(PAGE), [])
            finally:
                tempfile.tempdir = old


class PrototypeIsAGrantedSubject(unittest.TestCase):
    """Pre-existing gap (ticket 05's note): prototype is a first-class producer but was left out
    of the cortex self-door allowlist — second-class at recall/consolidação. Same leg as lazer
    (test_three_act.py codex adversarial #8): BOTH mirrors, config-side and server-side."""

    def test_prototype_is_granted_in_config_and_server(self):
        self.assertIn("prototype", cortex_config.GRANTED_SUBJECTS)
        self.assertIn("prototype", cortex_mcp.GRANTED_SUBJECTS)

    def test_the_two_mirrors_never_drift(self):
        # codex adversarial lint #8 (SINAL): two hand-maintained allowlists; membership tests
        # alone would let a future edit land in one mirror only.
        self.assertEqual(cortex_config.GRANTED_SUBJECTS, cortex_mcp.GRANTED_SUBJECTS)


class SkillDocCarriesTheRiteAndTheGate(unittest.TestCase):
    """The SKILL.md is the genus' contract with the producer. Pin the load-bearing tokens:
    the relicário bar (single-file, zero-dep, runs), the render→ver→revisar rite, the
    semantic gate 'a interatividade ensina?', the never-forced clause, and the pipeline
    conformance (scaffold + pipeline + close through tools/publisher.py, standalone page
    via publish_prototype_page)."""

    @classmethod
    def setUpClass(cls):
        cls.text = (REPO / "skills" / "prototype" / "SKILL.md").read_text()
        cls.low = cls.text.lower()

    def test_references_the_shared_scaffold_pipeline_and_publisher(self):
        for token in ("scaffold", "pipeline", "tools/publisher.py", "publish_prototype_page"):
            self.assertIn(token, self.text)

    def test_declares_the_relicario_bar(self):
        for token in ("single-file", "zero-dep", "self-contained"):
            self.assertIn(token, self.low)

    def test_declares_the_render_ver_revisar_rite(self):
        self.assertTrue(re.search(r"render\s*→\s*ver\s*→\s*revisar", self.low),
                        "the rite render→ver→revisar must be named")

    def test_declares_the_teaching_gate_and_the_never_forced_clause(self):
        self.assertIn("a interatividade ensina", self.low)
        self.assertTrue(re.search(r"never forced|nunca forçada", self.low))

    def test_close_snippet_binds_lineage_like_every_producer(self):
        # the same anti-drift pins test_lineage_producer_docs enforces on the roster docs.
        self.assertIn("'lineage':lineage", self.text)
        self.assertIn("lineage=art['lineage']", self.text)
        self.assertIn("lineage=[{'type':'builds_on','slug':", self.text)


if __name__ == "__main__":
    unittest.main()

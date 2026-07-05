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
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import producer_descriptor as pd  # noqa: E402
import publisher  # noqa: E402

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


class PrototypeIsAFirstClassGenus(unittest.TestCase):
    def test_prototype_is_in_the_producer_roster(self):
        self.assertIn("prototype", publisher.PRODUCER_ROSTER)

    def test_prototype_declares_a_descriptor(self):
        # declaration-only registration (test_new_producer_is_declarative): the presentation
        # floor is empty — the page itself and the skill's semantic gates ARE the bar.
        self.assertEqual(pd.require_descriptor("prototype"), {"require": []})


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

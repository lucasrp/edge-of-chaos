"""PAR B+C — the printable APOSTILA as a build SUBPRODUCT of the artefato
(docs/agencia/implementacao/05-fluxo-3atos-multiartefato.md §REVISÃO DO PAR: form A dominated;
winner = single-file interactive + apostila from the SAME data; the operator loves paper).

The apostila is the print-matter sibling of the single-file page: same DATA, sliders and
interaction PRECOMPUTED into static tables, print-CSS A4 (the régua is
drafts/grounding-exp/formC-apostila.html). It publishes through a NEW seam,
`publisher.publish_apostila_page`, as a content-addressed sibling
`<slug>.apostila.<sha256[:12]>.html` under the same blog dir (served by the existing /e/
route), linked from the artefato ("versão pra imprimir").

These tests pin: content addressing (idempotent, new address on change, tamper refusal),
the roster/slug/fragment/zero-dep bars shared with the proto seam, the two apostila-specific
bars (NO <script> — print matter is static, the interaction must already be tables; @page
print CSS present — the A4 marker), the default-ON-for-prototype policy helper, and the
"versão pra imprimir" link block rendering through the canonical palette without crashing.
"""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import publisher  # noqa: E402
import render  # noqa: E402

# The régua shape (formC-apostila.html): @page A4, break-inside:avoid on repeatable units,
# the slider's sweep PRECOMPUTED into a static table, verbatim source in the footer.
APOSTILA = (
    "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
    "<title>quatro jeitos — apostila</title>"
    "<style>@page{size:A4;margin:18mm 16mm}"
    "body{font:11.5pt/1.6 Georgia,serif}"
    ".caso{break-inside:avoid}"
    "table{border-collapse:collapse}</style></head>"
    "<body><h1>quatro jeitos</h1>"
    "<table><tr><th>braço</th><th>vence (de 624)</th></tr>"
    "<tr><td>v8_estru</td><td>624</td></tr><tr><td>baseline</td><td>0</td></tr></table>"
    "<p class='fn'>Fonte: structured_20260620T144124Z.json — verbatim.</p>"
    "</body></html>"
)


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class ApostilaLandsContentAddressed(unittest.TestCase):
    def test_bytes_intact_at_the_apostila_sibling_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_apostila_page(
                "quatro-jeitos", APOSTILA, skill="prototype", blog_dir=tmp)
            self.assertEqual(out.name, f"quatro-jeitos.apostila.{_digest(APOSTILA)}.html")
            self.assertEqual(out.parent, Path(tmp).resolve())
            self.assertEqual(out.read_text(), APOSTILA)

    def test_idempotent_same_bytes_new_address_on_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = publisher.publish_apostila_page(
                "quatro-jeitos", APOSTILA, skill="prototype", blog_dir=tmp)
            again = publisher.publish_apostila_page(
                "quatro-jeitos", APOSTILA, skill="prototype", blog_dir=tmp)
            self.assertEqual(first, again)
            changed = APOSTILA.replace("quatro jeitos", "cinco jeitos")
            second = publisher.publish_apostila_page(
                "quatro-jeitos", changed, skill="prototype", blog_dir=tmp)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_text(), APOSTILA)  # old address immutable
            self.assertEqual(second.read_text(), changed)

    def test_differing_bytes_at_the_same_address_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_apostila_page(
                "quatro-jeitos", APOSTILA, skill="prototype", blog_dir=tmp)
            out.write_text(APOSTILA.replace("624", "999"))  # tamper in place
            with self.assertRaises(ValueError):
                publisher.publish_apostila_page(
                    "quatro-jeitos", APOSTILA, skill="prototype", blog_dir=tmp)

    def test_namespace_is_disjoint_from_entries_and_proto_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_apostila_page(
                "quatro-jeitos", APOSTILA, skill="prototype", blog_dir=tmp)
            self.assertIn(".apostila.", out.name)
            self.assertNotIn(".proto.", out.name)
            self.assertFalse(publisher.SLUG_RE.match(out.stem))  # dots: never a close entry


class ApostilaSharesTheSeamBars(unittest.TestCase):
    def test_out_of_roster_bad_slug_and_fragment_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            for skill in ("", "not-a-genus", None):
                with self.assertRaises(ValueError):
                    publisher.publish_apostila_page(
                        "quatro-jeitos", APOSTILA, skill=skill, blog_dir=tmp)
            # "slug\n": re.match + $ accepts a trailing newline (codex adversarial) —
            # the seam must reject it before it lands in a filename.
            for slug in ("../evil", "UPPER", "", "a/b", "dot.dot", None, "quatro-jeitos\n"):
                with self.assertRaises(ValueError):
                    publisher.publish_apostila_page(
                        slug, APOSTILA, skill="prototype", blog_dir=tmp)
            with self.assertRaises(ValueError):
                publisher.publish_apostila_page(
                    "frag", "<table></table>", skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_external_resource_loads_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = APOSTILA.replace(
                "<h1>quatro jeitos</h1>",
                "<h1>quatro jeitos</h1><img src='https://cdn.example.com/x.png'>")
            with self.assertRaises(ValueError):
                publisher.publish_apostila_page(
                    "dep", page, skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_any_roster_genus_may_publish_an_apostila(self):
        # NÃO obrigatório e não exclusivo: opcional pra qualquer artefato do roster.
        with tempfile.TemporaryDirectory() as tmp:
            out = publisher.publish_apostila_page(
                "quatro-jeitos", APOSTILA, skill="report", blog_dir=tmp)
            self.assertTrue(out.exists())


class ApostilaIsStaticPrintMatter(unittest.TestCase):
    def test_live_code_is_refused_interaction_must_already_be_tables(self):
        # régua rule (5): apostila = subproduto do MESMO dado, pré-computado — nunca JS vivo.
        # codex adversarial #1/#2: not only <script> — on* handlers, javascript: URLs and
        # CSS network reach (@import / url(http…)) are live/networked too; all refused.
        offenders = [
            "<script>let x=1;</script>",
            "<img src=x onerror=alert(1)>",
            "<svg onload=alert(1)></svg>",
            "<a href='javascript:alert(1)'>x</a>",
            "<style>@import 'https://evil.example/x.css';</style>",
            "<style>body{background:url(https://evil.example/x.png)}</style>",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            for tag in offenders:
                page = APOSTILA.replace("</body>", tag + "</body>")
                with self.assertRaises(ValueError, msg=tag):
                    publisher.publish_apostila_page(
                        "quatro-jeitos", page, skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_missing_page_print_css_is_refused_but_casing_is_free(self):
        # @page{size:A4…} is the print-matter marker (the régua carries it); codex
        # adversarial #3: the check must be case-insensitive (CSS is).
        with tempfile.TemporaryDirectory() as tmp:
            page = APOSTILA.replace("@page{size:A4;margin:18mm 16mm}", "")
            with self.assertRaises(ValueError):
                publisher.publish_apostila_page(
                    "quatro-jeitos", page, skill="prototype", blog_dir=tmp)
            self.assertEqual(list(Path(tmp).iterdir()), [])
            upper = APOSTILA.replace("@page{", "@PAGE{")
            out = publisher.publish_apostila_page(
                "quatro-jeitos", upper, skill="prototype", blog_dir=tmp)
            self.assertTrue(out.exists())


class DefaultOnForPrototype(unittest.TestCase):
    def test_default_is_on_for_prototype_off_elsewhere(self):
        self.assertTrue(publisher.apostila_wanted("prototype"))
        for skill in ("report", "research", "map", "plan", "discovery", "grill", "lazer"):
            self.assertFalse(publisher.apostila_wanted(skill), skill)

    def test_producer_param_overrides_the_default_both_ways(self):
        self.assertTrue(publisher.apostila_wanted("report", param=True))
        self.assertFalse(publisher.apostila_wanted("prototype", param=False))


class LinkedFromTheArtefato(unittest.TestCase):
    def test_link_block_names_the_print_version_and_renders_a_real_anchor(self):
        block = publisher.apostila_link_block("quatro-jeitos.apostila.abc123def456.html")
        self.assertIn("imprimir", block["text"].lower())
        # the block must ride the canonical palette without crashing the publish, and the
        # URL must land as an actual <a href> (codex adversarial: render_text only linkifies
        # markdown [text](url) — a bare /e/... string is dead text, not a link).
        html_out = render.spec_to_html(
            {"sections": [{"title": "demo", "blocks": [block]}]})
        self.assertIn('href="/e/quatro-jeitos.apostila.abc123def456.html"', html_out)

    def test_link_block_accepts_the_published_path_and_refuses_a_funny_name(self):
        # codex adversarial #5: the lead will naturally pass publish_apostila_page's return
        # (a Path) — accept it; anything not shaped <slug>.apostila.<sha12>.html is refused
        # (no markdown/structure injection, no pointing at .proto./close entries).
        block = publisher.apostila_link_block(
            Path("/x/blog/entries/quatro-jeitos.apostila.abc123def456.html"))
        self.assertIn("(/e/quatro-jeitos.apostila.abc123def456.html)", block["text"])
        for bad in ("evil.proto.abc123def456.html", "entry.html",
                    "a.apostila.ZZZ.html", "a.apostila.abc123def456.html](x)[", ""):
            with self.assertRaises(ValueError, msg=bad):
                publisher.apostila_link_block(bad)


if __name__ == "__main__":
    unittest.main()

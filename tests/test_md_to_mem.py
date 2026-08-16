"""md-to-mem — Voz em documento + rail de canonicidade do grill (issue #130, spec md-to-mem.md).

Canal de injeção deliberada de conteúdo curado do operador na memória do cortex — a metade de
escrita que faltava, sobre trilhos existentes (log-nativo ADR-0006). Três peças pequenas:
inject barato (sem close/genus/review), canonicidade como gesto da curadoria de thread
(canon.elected/retired via grill_writeback), e relevância top-K na pesquisa (fiação embedding).

Rodam DIRETO: `tools/edge-python tests/test_md_to_mem.py` (`-m unittest` acha 0). Puro Python,
nenhuma chamada externa: onde um teste precisa de embedding, injeta vetores fixos.

Invariantes I1–I8 (mapeiam as aceitações a–m da issue) marcados por classe.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog        # noqa: E402
import md_to_mem       # noqa: E402
import grill_writeback  # noqa: E402
import briefing        # noqa: E402


# ─────────────────────────── S1 — eventos + fold (eventlog.docs_at) ───────────────────────────

class DocsFoldInjectAndRetire(unittest.TestCase):
    """S1: doc.injected abre um doc vivo; doc.retired o retira das janelas SEM apagar (o log
    preserva). O body vive verbatim NO evento (replay/prune-safe)."""

    def test_inject_then_retire_leaves_live_empty_body_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("doc.injected", "doc:v10", {"slug": "v10", "body": "corpo verbatim",
                            "threads": [], "sha256": "x", "author": "operador"}, log=log)
            self.assertEqual([d["slug"] for d in eventlog.docs_at(log=log)["live"]], ["v10"])
            self.assertEqual(eventlog.docs_at(log=log)["live"][0]["body"], "corpo verbatim")
            eventlog.append("doc.retired", "doc:v10", {"slug": "v10", "reason": "obsoleto"}, log=log)
            self.assertEqual(eventlog.docs_at(log=log)["live"], [])
            # o log preserva: o evento de injeção continua lá (I2 — sai da janela, não apaga)
            self.assertTrue(any(e["type"] == "doc.injected" for e in eventlog.read(log=log)))

    def test_body_verbatim_and_threads_carried(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            body = "# Título\n\nlinha 1\nlinha 2\n"
            eventlog.append("doc.injected", "doc:h", {"slug": "h", "body": body,
                            "threads": ["cluster:v10"], "sha256": "s", "author": "operador"}, log=log)
            d = eventlog.docs_at(log=log)["live"][0]
            self.assertEqual(d["body"], body)
            self.assertEqual(d["threads"], ["cluster:v10"])


class CanonFoldElectAndRetire(unittest.TestCase):
    """S1: canon.elected marca um objeto (md|artefato|experimento) como canônico; canon.retired
    o des-elege. O fold devolve o conjunto vivo do canon."""

    def test_elect_then_retire_canon(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("canon.elected", "canon:md:v10",
                            {"kind": "md", "ref": "v10", "thread": "cluster:v10"}, log=log)
            eventlog.append("canon.elected", "canon:artefato:r1",
                            {"kind": "artefato", "ref": "r1", "thread": None}, log=log)
            canon = eventlog.docs_at(log=log)["canon"]
            self.assertEqual({(c["kind"], c["ref"]) for c in canon},
                             {("md", "v10"), ("artefato", "r1")})
            eventlog.append("canon.retired", "canon:md:v10",
                            {"kind": "md", "ref": "v10", "reason": "thread encerrada"}, log=log)
            canon = eventlog.docs_at(log=log)["canon"]
            self.assertEqual({(c["kind"], c["ref"]) for c in canon}, {("artefato", "r1")})

    def test_empty_log_folds_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            self.assertEqual(eventlog.docs_at(log=log), {"live": [], "canon": []})


# ─────────────────────────── S2 — inject (md_to_mem.inject) ───────────────────────────

class InjectIsOneCommandNoGate(unittest.TestCase):
    """I1 (a,i): inject é 1 comando, sem gate além da validação mecânica. Emite doc.injected,
    projeta state/docs/<slug>.md, NUNCA passa por close/genus/review."""

    def test_inject_text_emits_event_and_projects_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = md_to_mem.inject("corpo do handoff", slug="v10", log=log,
                                   docs_dir=Path(tmp) / "docs")
            self.assertEqual(out["slug"], "v10")
            self.assertEqual(out["author"], "operador")
            self.assertEqual([d["slug"] for d in eventlog.docs_at(log=log)["live"]], ["v10"])
            proj = Path(tmp) / "docs" / "v10.md"
            self.assertTrue(proj.exists())
            self.assertEqual(proj.read_text(), "corpo do handoff")

    def test_inject_from_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            src = Path(tmp) / "handoff.md"
            src.write_text("# Handoff\n\nconteúdo")
            md_to_mem.inject(src, slug="ho", log=log, docs_dir=Path(tmp) / "docs")
            self.assertEqual(eventlog.docs_at(log=log)["live"][0]["body"], "# Handoff\n\nconteúdo")

    def test_sha256_matches_body(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            md_to_mem.inject("abc", slug="s", log=log, docs_dir=Path(tmp) / "docs")
            d = eventlog.docs_at(log=log)["live"][0]
            self.assertEqual(d["sha256"], hashlib.sha256("abc".encode("utf-8")).hexdigest())


class InjectValidatesMechanically(unittest.TestCase):
    """S2: validação mecânica — cap 64KB recusa loud; slug único entre docs VIVOS (re-inject
    recusa apontando doc.retired primeiro); body vazio recusa."""

    def test_over_cap_refuses_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                md_to_mem.inject("x" * (64 * 1024 + 1), slug="big", log=log,
                                 docs_dir=Path(tmp) / "docs")

    def test_duplicate_live_slug_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            md_to_mem.inject("v1", slug="dup", log=log, docs_dir=Path(tmp) / "docs")
            with self.assertRaises(ValueError):
                md_to_mem.inject("v2", slug="dup", log=log, docs_dir=Path(tmp) / "docs")

    def test_reinject_after_retire_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            md_to_mem.inject("v1", slug="s", log=log, docs_dir=Path(tmp) / "docs")
            eventlog.append("doc.retired", "doc:s", {"slug": "s", "reason": "r"}, log=log)
            md_to_mem.inject("v2", slug="s", log=log, docs_dir=Path(tmp) / "docs")  # not raised
            self.assertEqual(eventlog.docs_at(log=log)["live"][0]["body"], "v2")

    def test_empty_body_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                md_to_mem.inject("   ", slug="e", log=log, docs_dir=Path(tmp) / "docs")


class InjectThreadRefs(unittest.TestCase):
    """I7 (j,k): thread-ref existente pendura (duas vias, docs_for_thread); inexistente RECUSA
    loud (nunca cria); sem ref entra solto de primeira classe."""

    def test_no_ref_enters_loose_first_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            md_to_mem.inject("solto", slug="loose", log=log, docs_dir=Path(tmp) / "docs")
            self.assertEqual(eventlog.docs_at(log=log)["live"][0]["threads"], [])

    def test_existing_thread_hangs_two_ways(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # a thread EXISTE = há uma direction.set kind=thread com esse id (log-nativo)
            eventlog.set_direction("cluster:v10", "thread viva", kind="thread", log=log, title="thread viva")
            md_to_mem.inject("idx", slug="v10doc", threads=["cluster:v10"], log=log,
                             docs_dir=Path(tmp) / "docs")
            self.assertIn("v10doc", md_to_mem.docs_for_thread("cluster:v10", log=log))

    def test_nonexistent_thread_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                md_to_mem.inject("x", slug="s", threads=["cluster:ghost"], log=log,
                                 docs_dir=Path(tmp) / "docs")


# ─────────────────────────── S3 — canon rail no grill (grill_writeback) ───────────────────────────

class CanonRailIsGrillGesture(unittest.TestCase):
    """I2/I5/I6 (b,e,g,h): eleger/des-eleger canon é açúcar sobre append_event do grill — NUNCA
    do inject. Vale para md|artefato|experimento (rail geral). Nenhuma duração é declarada."""

    def test_elect_canon_appends_grill_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.elect_canon("md", "v10", thread="cluster:v10", log=log)
            canon = eventlog.docs_at(log=log)["canon"]
            self.assertEqual([(c["kind"], c["ref"]) for c in canon], [("md", "v10")])

    def test_elect_then_retire_canon(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.elect_canon("artefato", "r1", log=log)
            grill_writeback.retire_canon("artefato", "r1", reason="esfriou de propósito", log=log)
            self.assertEqual(eventlog.docs_at(log=log)["canon"], [])

    def test_elect_rejects_unknown_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with self.assertRaises(ValueError):
                grill_writeback.elect_canon("planilha", "x", log=log)

    def test_no_ttl_field_anywhere(self):
        """I6 (h): nenhum caminho declara duração — o payload do canon não tem TTL/expiração."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            grill_writeback.elect_canon("md", "v10", log=log)
            p = [e for e in eventlog.read(log=log) if e["type"] == "canon.elected"][0]["payload"]
            self.assertFalse(any(k in p for k in ("ttl", "expires", "expiry", "until")))


# ─────────────────────────── S4/S5 — briefing/wake + relevância ───────────────────────────

def _fixed_embed(vectors):
    """Embedder mock: mapeia texto→vetor fixo por substring-match (nunca chamada externa)."""
    def embed(text):
        for key, vec in vectors.items():
            if key in text:
                return vec
        return [0.0, 0.0, 0.0]
    return embed


class BriefingCanonSection(unittest.TestCase):
    """I5 (e,f): índices das threads VIVAS na Direction sobem SEMPRE na seção Documentos canônicos;
    thread fora da Direction desce sem apagar."""

    def test_live_thread_index_always_shows(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("cluster:v10", "thread viva", kind="thread", log=log, title="thread viva")
            md_to_mem.inject("índice v10", slug="v10doc", threads=["cluster:v10"], log=log,
                             docs_dir=Path(tmp) / "docs")
            grill_writeback.elect_canon("md", "v10doc", thread="cluster:v10", log=log)
            section = briefing._section_docs(log=log, embed_fn=_fixed_embed({}))
            self.assertIn("v10doc", section)

    def test_thread_out_of_direction_drops_from_top(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("cluster:v10", "thread viva", kind="thread", log=log, title="thread viva")
            md_to_mem.inject("índice v10", slug="v10doc", threads=["cluster:v10"], log=log,
                             docs_dir=Path(tmp) / "docs")
            grill_writeback.elect_canon("md", "v10doc", thread="cluster:v10", log=log)
            eventlog.drop("cluster:v10", log=log)  # thread sai da Direction
            # sem provider de embedding a degradação é por thread+recência; a thread morta não é
            # mais uma thread viva, então o índice não sobe pelo trilho de índice-de-thread-viva.
            live = md_to_mem.live_thread_indices(log=log)
            self.assertNotIn("v10doc", [d["slug"] for d in live])


class RelevanceTopK(unittest.TestCase):
    """I8 (l,m): canon 10× maior não engorda o briefing (top-K por relevância); doc da thread A
    não aparece em wake só-thread-B; consulta tocando A o traz."""

    def test_topk_limits_and_ranks_by_relevance(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # três docs canônicos SOLTOS (sem thread viva); só o mais relevante ao contexto sobe
            vecs = {"contexto vivo": [1.0, 0.0], "sobre A": [1.0, 0.05],
                    "sobre B": [0.0, 1.0], "sobre C": [1.0, 0.6]}
            for slug, body in (("a", "sobre A"), ("b", "sobre B"), ("c", "sobre C")):
                md_to_mem.inject(body, slug=slug, log=log, docs_dir=Path(tmp) / "docs")
                grill_writeback.elect_canon("md", slug, log=log)
            ranked = md_to_mem.relevant_docs("contexto vivo", log=log, embed_fn=_fixed_embed(vecs), k=2)
            self.assertEqual([d["slug"] for d in ranked], ["a", "c"])  # top-2 by cosine, B excluded

    def test_thread_A_doc_absent_in_thread_B_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("cluster:A", "thread A", kind="thread", log=log, title="thread A")
            eventlog.set_direction("cluster:B", "thread B", kind="thread", log=log, title="thread B")
            md_to_mem.inject("doc de A", slug="da", threads=["cluster:A"], log=log,
                             docs_dir=Path(tmp) / "docs")
            grill_writeback.elect_canon("md", "da", thread="cluster:A", log=log)
            vecs = {"doc de A": [1.0, 0.0], "só sobre B": [0.0, 1.0]}
            ranked = md_to_mem.relevant_docs("só sobre B", log=log, embed_fn=_fixed_embed(vecs), k=5)
            self.assertNotIn("da", [d["slug"] for d in ranked])


class DarkProviderDegradesDeclared(unittest.TestCase):
    """S5: provider de embedding dark → degradação DECLARADA (fallback thread+recência), nunca
    silenciosa. O briefing NOMEIA a degradação."""

    def test_dark_provider_declares_degradation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            md_to_mem.inject("qualquer", slug="d", log=log, docs_dir=Path(tmp) / "docs")
            grill_writeback.elect_canon("md", "d", log=log)

            def dark(_text):
                raise RuntimeError("no openai key")
            section = briefing._section_docs(log=log, embed_fn=dark)
            self.assertIn("degrada", section.lower())


# ─────────────────────────── S6 — projeção grafo (best-effort) ───────────────────────────

class GraphEpisodePayload(unittest.TestCase):
    """S6: o episódio projetado carrega provenance_class='asserted' + author='operador' (classe
    EXISTENTE do axis, não estende o enum); falha na projeção é reportada, nunca fatal."""

    def test_episode_payload_shape_and_provenance_class(self):
        payload = md_to_mem.graph_episode_payload("v10", "corpo", ["cluster:v10"])
        self.assertEqual(payload["provenance_class"], "asserted")
        self.assertEqual(payload["author"], "operador")
        self.assertEqual(payload["slug"], "v10")
        # o guard do cortex_provenance aceita 'asserted' como classe válida do axis
        import cortex_provenance
        self.assertIn(payload["provenance_class"], cortex_provenance.PROVENANCE_CLASSES)

    def test_inject_project_failure_never_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            # graph unreachable (no neo4j) — inject ainda retorna e o log fica current
            out = md_to_mem.inject("x", slug="s", log=log, docs_dir=Path(tmp) / "docs")
            self.assertEqual(out["slug"], "s")


if __name__ == "__main__":
    unittest.main()

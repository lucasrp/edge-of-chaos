"""harvest — the transcript harvester, the grounding iteration's spine (S4, design-emissao C).

Golden fixtures under tests/fixtures/harvest/ are REAL transcript lines from this machine's
store (~/.claude/projects/), sanitized (long bodies truncated) but byte-faithful in structure:
the exa+X multi-curl (one Bash, two queries), the arxiv double-curl (http:// — the measured
idiom violation), WebSearch empty + with hits, a gh call, an unrecognized curl, a spilled
tool-result pointer, and a subagent meta.json joined to its parent Agent tool_use.

recognize() is PURE (no I/O) — harvest()/session_floor() do the store walking, pointer
following and dispatch mapping. Every emitted row must fold through S1's fold_grounding.
"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import harvest    # noqa: E402
import eventlog   # noqa: E402
import sources    # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "harvest"


def load_fixture(name):
    return [json.loads(line) for line in (FIX / name).read_text().splitlines() if line.strip()]


def tool_use_of(obj):
    for b in obj.get("message", {}).get("content", []) or []:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            return b
    raise AssertionError("fixture line carries no tool_use block")


def recognize_fixture(name, recognizers=None):
    """The golden-path recognize() run: fixture tool_use + its resolved result."""
    tu_line, res_line = load_fixture(name)[:2]
    block = tool_use_of(tu_line)
    result = harvest.result_payload(res_line, block["id"])
    rows = harvest.recognize(block, result, recognizers or _RECS,
                             session_id=tu_line.get("sessionId"), transcript_line=0,
                             ts=tu_line.get("timestamp"))
    return rows


ROSTER_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "roster.agent.yaml"


def _seam_sources():
    """O roster DECLARADO deste módulo — sempre a fixture, nunca o agent.yaml do host.

    Este módulo testa o CÓDIGO do harvest: dado um roster, a tabela de recognizers sai certa e o
    reconhecimento dobra as invocações certas. Para isso o roster tem que ser conhecido e fixo.

    Antes ele vinha de `sources.load_sources()`, isto é, do agent.yaml de quem estivesse rodando
    a suíte. O resultado dependia do host: num genótipo (que POR CONTRATO não tem agent.yaml) a
    tabela nascia vazia e 90 dos 226 testes falhavam; num install de roster mínimo, 89. Nenhum
    desses números dizia nada sobre o harvest — diziam quem apertou enter.

    Validar o roster REAL de um install é outra coisa, e tem dono: test_sources.RealAgentYaml."""
    srcs, findings = sources.load_sources(ROSTER_FIXTURE)
    errors = [f for f in findings if f.get("level") == "error"]
    assert srcs and not errors, f"fixture de roster inválida: {errors}"
    return srcs


def _seam_recognizers():
    return harvest.build_recognizers(sources=_seam_sources())


_RECS = _seam_recognizers()


class RecognizersDeriveFromTheS3Seam(unittest.TestCase):
    """One seam, two projections (design-emissao §2): the recognizer table derives from
    sources.load_sources() interfaces[].via — plus the built-in pseudo-sources. An interface
    declared without its key (installed: false) still yields a recognizer: recognition is
    observation, never permission."""

    def test_url_recognizers_cover_the_declared_interfaces(self):
        pairs = {(r["source"], r["interface"]) for r in _RECS["url"]}
        self.assertIn(("exa", "search-deep"), pairs)
        self.assertIn(("exa", "contents"), pairs)
        self.assertIn(("x", "v2-recent"), pairs)
        self.assertIn(("x", "xai-responses"), pairs)   # installed: false — still recognizable
        self.assertIn(("hn", "algolia-search"), pairs)
        self.assertIn(("arxiv", "api-query"), pairs)

    def test_cli_recognizers_cover_gh_and_rclone_read_prefixes(self):
        by_src = {r["source"]: r for r in _RECS["cli"]}
        self.assertIn("gh api", by_src["github"]["prefixes"])
        self.assertIn("gh search", by_src["github"]["prefixes"])
        self.assertNotIn("gh repo list", by_src["github"]["prefixes"])  # not in the via
        self.assertIn("rclone ls", by_src["gdrive-consortium"]["prefixes"])
        # D6: the FULL declared remote literal, never just the remote name
        self.assertEqual(by_src["gdrive-consortium"]["require_remote"],
                         "gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:")

    def test_builtin_pseudo_sources_present(self):
        self.assertEqual(_RECS["tools"]["WebSearch"]["source"], "websearch-native")
        self.assertEqual(_RECS["tools"]["WebFetch"]["source"], "webfetch-native")

    def test_acts_never_yield_recognizers(self):
        # gdrive-upload lives in acts: (E3) — no recognizer may claim an upload as a read
        for r in _RECS["url"] + _RECS["cli"]:
            self.assertNotIn("upload", r["interface"])


class GoldenExaXMultiQuery(unittest.TestCase):
    """The REAL probe command (2026-07-01): ONE Bash tool call carrying an exa POST curl AND an
    X GET curl — the E2b case: one tool call with N queries = N rows, distinct occurrence
    indexes, each with its OWN byte-identical query_literal."""

    def test_two_rows_two_occurrences(self):
        rows = recognize_fixture("exa_x_multiquery.jsonl")
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["raw_ref"][3], rows[1]["raw_ref"][3])
        self.assertEqual({r["source"] for r in rows}, {"exa", "x"})

    def test_exa_row_query_literal_is_byte_identical_from_the_curl_body(self):
        exa = [r for r in recognize_fixture("exa_x_multiquery.jsonl") if r["source"] == "exa"][0]
        self.assertEqual(exa["interface"], "search-deep")
        self.assertEqual(exa["query_literal"],
                         "OpenTelemetry GenAI agent tool call semantic conventions")
        self.assertEqual(exa["dry_semantics"], "never-dry")
        # exa has no mechanical hit pattern — unknown, never coerced to 0 (None≠0 sacred)
        self.assertIsNone(exa["hits"])
        self.assertNotIn("dry", exa)

    def test_x_row_query_literal_raw_and_idiom_conforme(self):
        x = [r for r in recognize_fixture("exa_x_multiquery.jsonl") if r["source"] == "x"][0]
        self.assertEqual(x["interface"], "v2-recent")
        # byte-identical: the RAW percent-encoded value as typed in the command, never re-typed
        self.assertEqual(x["query_literal"], "exa%20search")
        # idiom check is mechanical on a DECODED working copy: 2 terms <= max_terms 3
        self.assertIs(x["idiom_conforme"], True)
        # the command truncates the X response (head -c 400) before result_count — unknown
        self.assertIsNone(x["hits"])

    def test_rows_carry_recognizer_rev_and_fold_shaped_raw_ref(self):
        for r in recognize_fixture("exa_x_multiquery.jsonl"):
            self.assertEqual(r["recognizer_rev"], harvest.RECOGNIZER_REV)
            self.assertIsNotNone(eventlog._raw_ref_key(r["raw_ref"]),
                                 f"raw_ref must be E2b fold-keyable: {r['raw_ref']}")


class GoldenArxivDoubleCurl(unittest.TestCase):
    """REAL arxiv double-curl over http:// — two occurrences AND the measured idiom violation
    (https_only: http → 301 with empty body)."""

    def test_two_rows_each_with_its_own_query(self):
        rows = recognize_fixture("arxiv_curl.jsonl")
        self.assertEqual([r["source"] for r in rows], ["arxiv", "arxiv"])
        self.assertEqual([r["query_literal"] for r in rows],
                         ["all:%22LexRubric%22", "ti:%22Provenance-Grounded%20Gating%22"])

    def test_http_scheme_violates_the_declared_https_only_idiom(self):
        for r in recognize_fixture("arxiv_curl.jsonl"):
            self.assertIs(r["idiom_conforme"], False)

    def test_no_totalresults_in_output_means_hits_unknown(self):
        for r in recognize_fixture("arxiv_curl.jsonl"):
            self.assertIsNone(r["hits"])


class GoldenWebSearch(unittest.TestCase):
    """WebSearch is a built-in pseudo-source: query_literal = input.query byte-identical;
    hits parsed from toolUseResult.results (the REAL empty case folds as a dry suspect)."""

    def test_empty_results_is_zero_hits_and_dry_suspect(self):
        rows = recognize_fixture("websearch_empty.jsonl")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["source"], "websearch-native")
        self.assertEqual(r["query_literal"],
                         "Graphiti temporal knowledge graph documentation Zep 2026")
        self.assertEqual(r["hits"], 0)
        self.assertEqual(r["dry"], "suspect")

    def test_link_results_counted_as_hits(self):
        r = recognize_fixture("websearch_hits.jsonl")[0]
        self.assertEqual(r["hits"], 10)   # the real result: 10 {title,url} links
        self.assertNotIn("dry", r)


class GoldenGhCall(unittest.TestCase):
    """REAL gh command with three invocations: `gh api` and `gh search` match the via's
    read prefixes; `gh repo list` is NOT in the via — never guessed into recognition."""

    def test_matched_prefixes_yield_rows_with_the_invocation_as_query(self):
        rows = recognize_fixture("gh_call.jsonl")
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["query_literal"].startswith("gh api user/orgs"))
        self.assertTrue(rows[1]["query_literal"].startswith("gh search repos --owner ORG-XY"))
        for r in rows:
            self.assertEqual((r["source"], r["interface"]), ("github", "gh-cli"))
            self.assertIsNone(r["hits"])   # gh output has no mechanical count — unknown


class GoldenUnrecognizedCurl(unittest.TestCase):
    """Enxerto B2 — the blindness tally: a network-shaped call no recognizer claims yields NO
    row (never a guessed source) but IS visible to the tally."""

    def test_no_rows_but_tallied(self):
        tu_line, _ = load_fixture("unrecognized_curl.jsonl")
        block = tool_use_of(tu_line)
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        # `gh release list` is in the command too — NOT a declared read prefix: no row for it
        self.assertEqual(rows, [])
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual(len(unrec), 2)   # the REAL probe curls the unknown host twice
        for _, host in unrec:
            self.assertIn("search.windows.net", host)

    def test_localhost_is_not_network_shaped(self):
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": "curl -s http://localhost:8766/health"}}
        self.assertEqual(harvest.unrecognized_urls(block, _RECS), [])


class GoldenSubagentMetaJoin(unittest.TestCase):
    """The REAL meta.json ↔ parent Agent tool_use join: meta.toolUseId names the parent
    tool_use whose prompt is the intent declaration — the MECHANICAL mapped tier."""

    def test_meta_joins_to_the_parent_agent_tool_use(self):
        meta = json.loads((FIX / "agent-acdc7f9683d08adc2.meta.json").read_text())
        parent = load_fixture("subagent_parent_agent.jsonl")[0]
        block = tool_use_of(parent)
        self.assertEqual(block["name"], "Agent")
        self.assertEqual(block["id"], meta["toolUseId"])
        self.assertTrue(block["input"]["prompt"])   # the intent declaration exists

    def test_subagent_transcript_carries_the_parent_session_id(self):
        first = load_fixture("subagent_first_line.jsonl")[0]
        self.assertEqual(first["sessionId"], "2316d983-5ed1-45d0-afbc-b2014031d1f6")
        self.assertTrue(first["isSidechain"])


class SpilledToolResultPointerIsFollowed(unittest.TestCase):
    """A large result spills to <session>/tool-results/<x>.txt and the transcript carries a
    `<persisted-output>` pointer (REAL format in the fixture) — the harvester follows it."""

    def test_real_fixture_pointer_format_parses(self):
        _, res_line = load_fixture("spilled_pointer.jsonl")
        # the REAL spill shape: message content carries the <persisted-output> pointer AND
        # toolUseResult carries a first-class persistedOutputPath (verified 2026-07-02)
        text = harvest.content_text(res_line, "toolu_01V1gpgz5B7XztRbrxuTawTN")
        self.assertIn("<persisted-output>", text)
        self.assertIsNotNone(harvest._POINTER_RE.search(text))
        self.assertIn("persistedOutputPath", res_line["toolUseResult"])

    def test_persisted_output_path_is_preferred_when_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            spill = Path(tmp) / "full.txt"
            spill.write_text("the FULL spilled output")
            line = {"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "preview only"}]},
                    "toolUseResult": {"stdout": "truncated preview", "stderr": "",
                                      "persistedOutputPath": str(spill),
                                      "persistedOutputSize": 23}}
            self.assertEqual(harvest.result_payload(line, "t1"), "the FULL spilled output")

    def test_follow_pointer_reads_the_spilled_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            spill = Path(tmp) / "abc123.txt"
            spill.write_text('{"meta":{"result_count":7}}')
            text = ("<persisted-output>\nOutput too large (43.6KB). "
                    f"Full output saved to: {spill}\n\nPreview (first 2KB):\n---\npreview")
            self.assertEqual(harvest.follow_pointer(text), '{"meta":{"result_count":7}}')

    def test_missing_spill_file_degrades_to_the_pointer_text(self):
        text = ("<persisted-output>\nOutput too large (1KB). "
                "Full output saved to: /nonexistent/gone.txt\n\nPreview:")
        self.assertEqual(harvest.follow_pointer(text), text)   # degrade, never raise

    def test_hits_parse_through_a_followed_pointer(self):
        cmd = ('curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai&max_results=10" '
               '-H "Authorization: Bearer $T"')
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        with tempfile.TemporaryDirectory() as tmp:
            spill = Path(tmp) / "big.txt"
            spill.write_text('{"data":[...],"meta":{"result_count":10}}')
            pointer = f"<persisted-output>\nFull output saved to: {spill}\n\nPreview:"
            rows = harvest.recognize(block, harvest.follow_pointer(pointer), _RECS,
                                     session_id="s", transcript_line=0)
            self.assertEqual(rows[0]["hits"], 10)


class MalformedInputsNeverRaise(unittest.TestCase):
    """Per-recognizer malformed cases: recognize() is fail-dark — a corrupt block yields no
    rows (harvest counts it), never a raise."""

    def test_malformed_tool_use_shapes(self):
        # (a WebSearch with a corrupt/absent input is NOT here: the attempt still ran and is
        # counted with query_literal None — see the next test)
        for block in (None, "x", {}, {"name": "Bash"}, {"name": "Bash", "id": "t", "input": None},
                      {"name": "Bash", "id": "t", "input": {"command": 42}},
                      {"name": "Bash", "id": "", "input": {"command": "curl https://api.exa.ai/search"}}):
            self.assertEqual(harvest.recognize(block, None, _RECS,
                                               session_id="s", transcript_line=0), [],
                             f"malformed block must yield no rows: {block!r}")

    def test_websearch_without_query_still_counts_the_attempt(self):
        block = {"type": "tool_use", "id": "t1", "name": "WebSearch", "input": {}}
        rows = harvest.recognize(block, {"results": []}, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["query_literal"])

    def test_garbage_result_means_hits_unknown_never_zero(self):
        cmd = 'curl "https://api.twitter.com/2/tweets/search/recent?query=ai&max_results=10"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        for result in (None, 42, [], {"stdout": 7}, "no counts here"):
            rows = harvest.recognize(block, result, _RECS, session_id="s", transcript_line=0)
            self.assertIsNone(rows[0]["hits"], f"garbage result {result!r} must be unknown")
            self.assertNotIn("dry", rows[0])


class RawRefIsStable(unittest.TestCase):
    """E2b: raw_ref is BRUTE location — the same line re-parsed yields the SAME refs (retro-
    harvest re-minerates and the fold dedups; an unstable ref would defeat supersedes)."""

    def test_same_line_reparsed_same_refs(self):
        a = [tuple(r["raw_ref"]) for r in recognize_fixture("exa_x_multiquery.jsonl")]
        b = [tuple(r["raw_ref"]) for r in recognize_fixture("exa_x_multiquery.jsonl")]
        self.assertEqual(a, b)
        self.assertEqual(len(set(a)), 2)

    def test_occurrence_index_is_position_not_recognizer_order(self):
        # the exa curl comes FIRST in the command text: its occurrence index is the smaller one
        rows = recognize_fixture("exa_x_multiquery.jsonl")
        by_src = {r["source"]: r["raw_ref"][3] for r in rows}
        self.assertLess(by_src["exa"], by_src["x"])


class ScriptAwareCoarseRecognition(unittest.TestCase):
    """Enxerto B2: a KNOWN script that reads a source gets a coarse row — attribution
    opaque-script, query_literal null (the script's query is opaque to the transcript)."""

    def test_known_script_yields_opaque_row(self):
        recs = dict(_RECS)
        recs["scripts"] = {"edge-x": {"source": "x", "interface": "v2-recent"}}
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": "edge-x 'ai agents' --limit 5"}}
        rows = harvest.recognize(block, "whatever", recs, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attribution"], "opaque-script")
        self.assertIsNone(rows[0]["query_literal"])
        self.assertIsNone(rows[0]["hits"])


# --- harvest(): the effectful walk -----------------------------------------------------------

X_STDOUT = '{"data":[{"id":"1","text":"t"}],"meta":{"newest_id":"1","result_count":4}}'


def _tool_pair(sid, tuid, ts, command=None, name="Bash", inp=None, stdout=X_STDOUT):
    """One assistant tool_use line + its user tool_result line, in the REAL store shape."""
    use = {"type": "assistant", "sessionId": sid, "timestamp": ts,
           "message": {"role": "assistant", "content": [
               {"type": "tool_use", "id": tuid, "name": name,
                "input": inp if inp is not None else {"command": command}}]}}
    res = {"type": "user", "sessionId": sid, "timestamp": ts,
           "message": {"role": "user", "content": [
               {"type": "tool_result", "tool_use_id": tuid, "content": stdout}]},
           "toolUseResult": {"stdout": stdout, "stderr": "", "interrupted": False}}
    return [use, res]


X_CMD = ('curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai%20agents&max_results=10" '
         '-H "Authorization: Bearer $X_BEARER_TOKEN"')


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o) + "\n" for o in lines))


def _log_line(seq, ts, type, payload):
    return json.dumps({"seq": seq, "ts": ts, "type": type,
                       "subject": "dispatch" if type == "dispatch.open" else "artefato:x",
                       "payload": payload}) + "\n"


class HarvestWalksTheStore(unittest.TestCase):
    """harvest(): incremental cursor walk over ALL project dirs + subagents/ (E7), rows emitted
    as grounding.manifest events that fold through S1, dispatch mapping by session anchor +
    interval (E1), idempotence + retro-harvest dedup (E2/E2b)."""

    def _store(self, tmp):
        """Two project dirs (E7) + a subagent. sessA has TWO dispatches with interleaved reads
        (the plan's fixture): d1 [10:00→11:00 publish], gap, d2 [12:00→open-ended). The main
        transcript also carries the parent Agent tool_use (toolu_p1) whose prompt the subagent's
        meta.json joins to — the VERIFIED mapped chain (gate 3)."""
        store = Path(tmp) / "projects"
        _write(store / "-proj-a" / "sessA.jsonl",
               _tool_pair("sessA", "toolu_p1", "2026-07-01T10:20:00.000Z", name="Agent",
                          inp={"prompt": "read the world about agents"}, stdout="explorer done")
               + _tool_pair("sessA", "toolu_a1", "2026-07-01T10:30:00.000Z", X_CMD)      # → d1
               + _tool_pair("sessA", "toolu_a2", "2026-07-01T11:30:00.000Z", X_CMD)    # gap → orphan
               + _tool_pair("sessA", "toolu_a3", "2026-07-01T12:30:00.000Z", X_CMD))   # → d2
        _write(store / "-proj-b" / "sessB.jsonl",
               _tool_pair("sessB", "toolu_b1", "2026-07-01T10:40:00.000Z", name="WebSearch",
                          inp={"query": "agents"}, stdout="")
               )
        # sessB's WebSearch result needs the structured toolUseResult
        lines = [json.loads(x) for x in (store / "-proj-b" / "sessB.jsonl").read_text().splitlines()]
        lines[1]["toolUseResult"] = {"query": "agents", "results": [], "durationSeconds": 1.0}
        _write(store / "-proj-b" / "sessB.jsonl", lines)
        # subagent of sessA (E7 glob + mapped attribution)
        sub = store / "-proj-a" / "sessA" / "subagents"
        _write(sub / "agent-x1.jsonl",
               _tool_pair("sessA", "toolu_s1", "2026-07-01T10:45:00.000Z", X_CMD))
        (sub / "agent-x1.meta.json").write_text(json.dumps(
            {"agentType": "ed-explorer", "description": "read the world", "toolUseId": "toolu_p1"}))
        return store

    def _log(self, tmp):
        log = Path(tmp) / "log.jsonl"
        log.write_text(
            _log_line(1, "2026-07-01T10:00:00+00:00", "dispatch.open",
                      {"dispatch_id": "d1", "session_id": "sessA", "theme": "tema",
                       "intent": "why-d1", "geometry": "themed"})
            + _log_line(2, "2026-07-01T11:00:00+00:00", "artefato.published",
                        {"slug": "art1", "dispatch_id": "d1"})
            + _log_line(3, "2026-07-01T12:00:00+00:00", "dispatch.open",
                        {"dispatch_id": "d2", "session_id": "sessA", "geometry": "ambient"}))
        return log

    def test_end_to_end_rows_fold_through_s1(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, log = self._store(tmp), self._log(tmp)
            cursors = Path(tmp) / "cursors.json"
            n = harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS)
            self.assertEqual(n, 5)   # a1 a2 a3 + subagent + sessB websearch
            g = eventlog.grounding_at(log=log)
            attempts = sum(c["attempts"] for c in g["cells"].values())
            self.assertEqual(attempts, 5)
            self.assertEqual(g["corrupt"], 0, "every emitted row must fold cleanly (E2b shape)")
            # the X rows parsed result_count=4 — hits KNOWN; websearch empty = dry suspect
            ws = [c for c in g["cells"].values() if c["source"] == "websearch-native"][0]
            self.assertEqual(ws["hits"], 0)
            self.assertEqual(ws["dry"], {"suspect": 1})

    def test_dispatch_interval_mapping_never_last_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, log = self._store(tmp), self._log(tmp)
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            rows = {tuple(e["payload"]["raw_ref"])[2]: e["payload"]
                    for e in eventlog.read(types=["grounding.manifest"], log=log)}
            self.assertEqual(rows["toolu_a1"]["dispatch_id"], "d1")
            self.assertEqual(rows["toolu_a1"]["geometry"], "themed")
            self.assertEqual(rows["toolu_a1"]["intent"], "why-d1")
            self.assertEqual(rows["toolu_a1"]["attribution"], "declared")
            # 11:30 sits AFTER d1 was consumed and BEFORE d2 opened: orphan, NEVER "last open" (E1)
            self.assertIsNone(rows["toolu_a2"]["dispatch_id"])
            self.assertEqual(rows["toolu_a2"]["attribution"], "orphan")
            self.assertEqual(rows["toolu_a3"]["dispatch_id"], "d2")
            # d2 declared nothing — inside its interval but not declared: honest unknown
            self.assertEqual(rows["toolu_a3"]["attribution"], "unknown")
            # sessB never appears in any dispatch.open: its rows are orphans too
            self.assertIsNone(rows["toolu_b1"]["dispatch_id"])

    def test_subagent_rows_are_mapped_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, log = self._store(tmp), self._log(tmp)
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            rows = {tuple(e["payload"]["raw_ref"])[2]: e["payload"]
                    for e in eventlog.read(types=["grounding.manifest"], log=log)}
            sub = rows["toolu_s1"]
            self.assertEqual(sub["attribution"], "mapped")    # meta.json→toolUseId join
            self.assertEqual(sub["dispatch_id"], "d1")        # parent session anchor at 10:45
            self.assertEqual(sub["subagent"]["toolUseId"], "toolu_p1")

    def test_idempotent_second_run_emits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, log = self._store(tmp), self._log(tmp)
            cursors = Path(tmp) / "c.json"
            harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS)
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS), 0)

    def test_retro_harvest_cursor_reset_emits_zero_and_fold_dedups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, log = self._store(tmp), self._log(tmp)
            cursors = Path(tmp) / "c.json"
            harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS)
            before = eventlog.grounding_at(log=log)
            cursors.unlink()   # retro-harvest: cursor reset re-reads the whole store
            n = harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS)
            self.assertEqual(n, 0, "already-emitted raw_refs are never re-emitted")
            after = eventlog.grounding_at(log=log)
            self.assertEqual(
                sum(c["attempts"] for c in before["cells"].values()),
                sum(c["attempts"] for c in after["cells"].values()))

    def test_none_hits_preserved_through_the_fold(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD,
                              stdout="truncated — no result_count here"))
            log = Path(tmp) / "log.jsonl"
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            g = eventlog.grounding_at(log=log)
            cell = list(g["cells"].values())[0]
            self.assertIsNone(cell["hits"])
            self.assertEqual(cell["hits_unknown"], 1)

    def test_unrecognized_network_calls_are_tallied_not_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z",
                              'curl -s "https://unknown-api.example.com/v1/search?q=x"'))
            log = Path(tmp) / "log.jsonl"
            n = harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            self.assertEqual(n, 0)
            evs = eventlog.read(types=["grounding.unmanifested"], log=log)
            self.assertEqual(len(evs), 1)
            self.assertEqual(evs[0]["payload"]["count"], 1)
            self.assertIn("unknown-api.example.com", evs[0]["payload"]["by_host"])
            # retro-run does not re-tally the same occurrence
            Path(tmp, "c.json").unlink()
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            evs = eventlog.read(types=["grounding.unmanifested"], log=log)
            self.assertEqual(sum(e["payload"]["count"] for e in evs), 1)

    def test_unpaired_tool_use_is_held_back_then_emitted_when_its_result_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            pair = _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD)
            f = store / "-p" / "s1.jsonl"
            _write(f, pair[:1])                        # tool_use flushed, result not yet
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors,
                                             store_root=store, recognizers=_RECS), 0)
            with f.open("a") as fh:                    # the writer completes the pair
                fh.write(json.dumps(pair[1]) + "\n")
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors,
                                             store_root=store, recognizers=_RECS), 1)
            row = eventlog.read(types=["grounding.manifest"], log=log)[0]["payload"]
            self.assertEqual(row["hits"], 4)           # emitted WITH its result, never early-frozen

    def test_store_absent_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                harvest.harvest(log=Path(tmp) / "log.jsonl",
                                cursors_path=Path(tmp) / "c.json",
                                store_root=Path(tmp) / "missing")

    def test_corrupt_transcript_line_is_dark_counted_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            pair = _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD)
            f = store / "-p" / "s1.jsonl"
            _write(f, pair)
            raw = f.read_text()
            f.write_text('{"type": "assistant", "message": TRUNCATED\n' + raw)
            log = Path(tmp) / "log.jsonl"
            n = harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            self.assertEqual(n, 1, "the valid pair around the corrupt line still harvests")


class RetroSupersedeVersionsTheInterpretation(unittest.TestCase):
    """Codex S4 gate D1 (E2b): a retro-harvest with a HIGHER recognizer_rev over a reset
    cursor must EMIT superseding rows for known raw_refs — the raw history is never
    rewritten, the interpretation is versioned and the fold's max (recognizer_rev, seq)
    projects the new one. Same/lower rev stays a no-op."""

    def _run(self, tmp, recs):
        store = Path(tmp) / "projects"
        if not store.exists():
            _write(store / "-p" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD))
        log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
        if cursors.exists():
            cursors.unlink()   # retro-harvest: cursor reset
        return harvest.harvest(log=log, cursors_path=cursors, store_root=store,
                               recognizers=recs), log

    def test_higher_rev_supersedes_and_fold_projects_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            n1, log = self._run(tmp, _RECS)
            self.assertEqual(n1, 1)
            # rev+1 AND a corrected interpretation (the lens was wrong, say)
            recs2 = _seam_recognizers()
            recs2["rev"] = harvest.RECOGNIZER_REV + 1
            for r in recs2["url"]:
                if r["source"] == "x":
                    r["lens"] = "atividade"
            n2, log = self._run(tmp, recs2)
            self.assertEqual(n2, 1, "the better recognizer re-mines the known occurrence")
            evs = eventlog.read(types=["grounding.manifest"], log=log)
            self.assertEqual(len(evs), 2)
            sup = evs[-1]["payload"]
            self.assertEqual(sup["supersedes"], sup["raw_ref"],
                             "a reinterpretation targets the SAME brute occurrence (E2b)")
            self.assertEqual(sup["recognizer_rev"], harvest.RECOGNIZER_REV + 1)
            g = eventlog.grounding_at(log=log)
            self.assertEqual(sum(c["attempts"] for c in g["cells"].values()), 1,
                             "still ONE occurrence — reinterpreted, never duplicated")
            winner = [c for c in g["cells"].values() if c["attempts"] == 1][0]
            self.assertEqual(winner["lens"], "atividade", "the fold projects the new rev")

    def test_same_rev_retro_run_stays_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, _RECS)
            n2, _ = self._run(tmp, _RECS)
            self.assertEqual(n2, 0)

    def test_lower_rev_never_downgrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs_hi = _seam_recognizers()
            recs_hi["rev"] = harvest.RECOGNIZER_REV + 5
            self._run(tmp, recs_hi)
            n2, log = self._run(tmp, _RECS)   # older recognizer re-run over reset cursor
            self.assertEqual(n2, 0, "a worse recognizer never re-emits (fold rank aside)")


class UnmanifestedTallyIsDurableAndBounded(unittest.TestCase):
    """Codex S4 gate D2+D3: the blind-leg tally lands in the SAME per-file batch as the
    manifests, BEFORE the cursor advances (a crash between them re-emits and the refs-dedup
    absorbs it — never a lost tally, ADR-0006); and one event is BOUNDED to
    _UNMANIFESTED_CHUNK refs (a giant retro-run never writes one giant fragile line)."""

    def test_tally_lands_in_the_same_batch_as_the_file_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            cmd = (X_CMD + ' ; curl -s "https://unknown-api.example.com/v1/search?q=x"')
            _write(store / "-p" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", cmd))
            log = Path(tmp) / "log.jsonl"
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            evs = eventlog.read(log=log)
            types = [e["type"] for e in evs]
            self.assertIn("grounding.manifest", types)
            self.assertIn("grounding.unmanifested", types)
            seqs = [e["seq"] for e in evs
                    if e["type"] in ("grounding.manifest", "grounding.unmanifested")]
            self.assertEqual(seqs, list(range(seqs[0], seqs[0] + len(seqs))),
                             "one indivisible append_batch per file — no crash window "
                             "between the rows and their blind-leg tally")

    def test_tally_only_file_still_lands_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z",
                              'curl -s "https://unknown-api.example.com/a?q=1"'))
            log = Path(tmp) / "log.jsonl"
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            evs = eventlog.read(types=["grounding.unmanifested"], log=log)
            self.assertEqual(len(evs), 1)

    def test_refs_per_event_bounded_by_the_chunk_constant(self):
        old = harvest._UNMANIFESTED_CHUNK
        harvest._UNMANIFESTED_CHUNK = 3
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store = Path(tmp) / "projects"
                cmd = " ; ".join(f'curl -s "https://unknown-{i}.example.com/a?q=1"'
                                 for i in range(7))
                _write(store / "-p" / "s1.jsonl",
                       _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", cmd))
                log = Path(tmp) / "log.jsonl"
                harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
                evs = eventlog.read(types=["grounding.unmanifested"], log=log)
                self.assertEqual(len(evs), 3)                       # ceil(7/3)
                self.assertEqual(sum(e["payload"]["count"] for e in evs), 7)
                for e in evs:
                    self.assertLessEqual(len(e["payload"]["refs"]), 3)
                    self.assertEqual(e["payload"]["count"], len(e["payload"]["refs"]))
        finally:
            harvest._UNMANIFESTED_CHUNK = old


class RcloneFromGuardIsNotSubstringMatched(unittest.TestCase):
    """Codex S4 gates D4+D6: the FROM-remote read-guard requires the FULL declared remote
    literal on shlex-tokenized args — a local dir NAMED like the remote must never make an
    upload read-match (D4), a DIFFERENT drive behind the same remote name must not fold into
    this source (D6), and the destination must not be the remote."""

    def _rows(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS,
                                             session_id="s", transcript_line=0)
                if r["source"] == "gdrive-consortium"]

    def test_upload_with_remote_named_local_dir_is_not_a_read(self):
        # the repro: source is a LOCAL dir whose name contains the remote prefix
        cmd = 'rclone copy gdrive-export/ "gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:dest"'
        self.assertEqual(self._rows(cmd), [])

    def test_plain_upload_is_not_a_read(self):
        cmd = "rclone copy /home/x/file.pdf 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:atas'"
        self.assertEqual(self._rows(cmd), [])

    def test_copy_from_remote_to_local_is_a_read(self):
        cmd = "rclone copy 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:atas' /tmp/dest"
        rows = self._rows(cmd)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "rclone-read")

    def test_ls_of_a_quoted_remote_path_with_spaces_is_a_read(self):
        cmd = "rclone ls 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:pasta com espaço' 2>&1"
        self.assertEqual(len(self._rows(cmd)), 1)

    def test_remote_to_remote_copy_is_not_a_read(self):
        cmd = ("rclone copy 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:src' "
               "'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:dst'")
        self.assertEqual(self._rows(cmd), [])

    def test_untokenizable_invocation_fails_closed_without_raising(self):
        cmd = "rclone ls 'gdrive,team_drive=X:unbalanced"
        self.assertEqual(self._rows(cmd), [])

    # Codex S4 gate D6: the guard requires the FULL declared remote literal, never just the
    # remote NAME — a different drive reached through the same rclone remote must not fold
    # into the consortium source (source-boundary violation: someone's personal Drive would
    # contaminate the consortium's Atividade lens).
    def test_personal_folder_on_the_same_remote_name_is_not_this_source(self):
        self.assertEqual(self._rows("rclone ls 'gdrive:Personal Folder'"), [])

    def test_another_team_drive_is_not_this_source(self):
        self.assertEqual(
            self._rows("rclone ls 'gdrive,team_drive=OTHER123xyz:docs'"), [])

    def test_the_declared_team_drive_is_this_source(self):
        rows = self._rows("rclone lsd 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:'")
        self.assertEqual(len(rows), 1)

    def test_recognizer_carries_the_full_remote_literal(self):
        rec = [r for r in _RECS["cli"] if r["source"] == "gdrive-consortium"][0]
        self.assertEqual(rec["require_remote"], "gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:")


class ExpiredUnpairedToolUseDoesNotPinTheCursor(unittest.TestCase):
    """Codex S4 gates D5+D7: only the ACTUAL live tail holds the watermark back. A cancelled
    tool_use with ANY complete JSON line after it (a later result, or plain dialogue — the
    writer moved on either way) is EXPIRED: counted, skipped, and the cursor advances past
    it — the incremental promise survives a cancelled call."""

    def test_cancelled_call_expires_and_later_calls_emit(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            cancelled = _tool_pair("s1", "t_dead", "2026-07-01T09:00:00.000Z", X_CMD)[:1]
            complete = _tool_pair("s1", "t_live", "2026-07-01T10:00:00.000Z", X_CMD)
            f = store / "-p" / "s1.jsonl"
            _write(f, cancelled + complete)
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            n = harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS)
            self.assertEqual(n, 1, "the later complete call still emits")
            rows = eventlog.read(types=["grounding.manifest"], log=log)
            self.assertEqual(rows[0]["payload"]["raw_ref"][2], "t_live")
            # the cursor advanced PAST the cancelled call — no eternal full re-scan
            # (#62: the cursor value is now a stat triple {lines,size,mtime}, was a bare int)
            saved = json.loads(cursors.read_text())
            self.assertEqual(saved[str(f)]["lines"], 3)
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors,
                                             store_root=store, recognizers=_RECS), 0)

    def test_live_tail_unpaired_still_holds(self):
        # the pre-existing behavior stays: NO activity after the unpaired use = a writer
        # mid-flush; the watermark holds so the pair emits complete next run
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            pair = _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD)
            f = store / "-p" / "s1.jsonl"
            _write(f, pair[:1])
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors,
                                             store_root=store, recognizers=_RECS), 0)
            self.assertEqual(json.loads(cursors.read_text())[str(f)]["lines"], 0)

    def test_cancelled_then_plain_line_expires_without_any_later_result(self):
        # Codex S4 gate D7: "the writer moved on" = ANY complete JSON line after the
        # tool_use — a cancelled call followed by ordinary dialogue (no tool_result ever
        # again) must expire, not pin the cursor forever
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            cancelled = _tool_pair("s1", "t_dead", "2026-07-01T09:00:00.000Z", X_CMD)[:1]
            plain = [{"type": "assistant", "sessionId": "s1",
                      "timestamp": "2026-07-01T09:01:00.000Z",
                      "message": {"role": "assistant",
                                  "content": [{"type": "text", "text": "moving on"}]}}]
            f = store / "-p" / "s1.jsonl"
            _write(f, cancelled + plain)
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors,
                                             store_root=store, recognizers=_RECS), 0)
            self.assertEqual(json.loads(cursors.read_text())[str(f)]["lines"], 2,
                             "the cursor advances past the cancelled call")


class SessionFloorLocatesByIndex(unittest.TestCase):
    """session_floor (for S6): the pure recognize() run over ONE live session, located by
    INDEX across ALL project dirs (E7 — a worktree changes the project-dir slug, so the path
    is searched, never derived). Never raises — dark is a counted, honest answer."""

    def test_floor_counts_recognized_reads_including_subagents(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-some-other-slug" / "sessF.jsonl",
                   _tool_pair("sessF", "t1", "2026-07-01T10:00:00.000Z", X_CMD))
            sub = store / "-some-other-slug" / "sessF" / "subagents"
            _write(sub / "agent-z.jsonl",
                   _tool_pair("sessF", "t2", "2026-07-01T10:05:00.000Z", X_CMD))
            floor = harvest.session_floor("sessF", recognizers=_RECS, store_root=store)
            self.assertFalse(floor["dark"])
            self.assertEqual(floor["reads"], 2)
            self.assertEqual(len(floor["recognized"]), 2)

    def test_unknown_session_is_dark_with_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            (store / "-p").mkdir(parents=True)
            floor = harvest.session_floor("nope", store_root=store)
            self.assertTrue(floor["dark"])
            self.assertEqual(floor["reads"], 0)
            self.assertIn("not found", floor["reason"])

    def test_absent_store_is_dark_never_a_raise(self):
        floor = harvest.session_floor("sess", store_root="/nonexistent/projects")
        self.assertTrue(floor["dark"])


class McpIsRecognizedOnlyWhenDeclared(unittest.TestCase):
    """Codex S4 gate 2: the generic `mcp__*` recognizer is GONE (it turned ANY MCP call into a
    row, resurrecting a hardcoded primitive that could fold a recall/mutating tool as grounding).
    An MCP tool is a row ONLY when agent.yaml DECLARES it a read-only interface."""

    _SRC = [{"name": "cortex", "description": "the Cortex graph. Lens: Atividade.",
             "interfaces": [{"interface_id": "recall",
                             "via": "mcp__cortex__recall — read-only",
                             "dry_semantics": "real"}]}]

    def test_undeclared_mcp_call_yields_no_row(self):
        block = {"type": "tool_use", "id": "t1", "name": "mcp__cortex__mutate_graph",
                 "input": {"query": "delete everything"}}
        # neither the repo's real recognizers nor a table that declares a DIFFERENT mcp tool
        self.assertEqual(harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0), [])
        recs = harvest.build_recognizers(sources=self._SRC)
        self.assertEqual(harvest.recognize(block, None, recs, session_id="s", transcript_line=0), [])

    def test_declared_read_only_mcp_interface_is_recognized(self):
        recs = harvest.build_recognizers(sources=self._SRC)
        self.assertEqual(recs["tools"]["mcp__cortex__recall"]["source"], "cortex")
        self.assertEqual(recs["tools"]["mcp__cortex__recall"]["lens"], "atividade")
        block = {"type": "tool_use", "id": "t1", "name": "mcp__cortex__recall",
                 "input": {"query": "space-0 subgraph"}}
        rows = harvest.recognize(block, None, recs, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["source"], rows[0]["interface"]), ("cortex", "recall"))
        self.assertEqual(rows[0]["query_literal"], "space-0 subgraph")


class GhWritesAreNotReads(unittest.TestCase):
    """Codex S4 gate 7: a CLI invocation is a read only in a provably read-only form — an explicit
    mutating method (`gh api -X POST/…`) or a POST-implying field flag is a WRITE, never folded."""

    def _rows(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "github"]

    def test_gh_api_post_is_not_a_read(self):
        self.assertEqual(self._rows("gh api -X POST repos/o/r/issues -f title=x"), [])

    def test_gh_api_delete_and_patch_are_not_reads(self):
        self.assertEqual(self._rows("gh api --method DELETE repos/o/r/issues/1"), [])
        self.assertEqual(self._rows("gh api -XPATCH repos/o/r"), [])

    def test_gh_api_field_flag_defaults_to_post_and_is_not_a_read(self):
        self.assertEqual(self._rows("gh api repos/o/r/labels -f name=bug"), [])

    # gate R2-2: the =-joined and GLUED field forms also make `gh api` default to POST
    def test_gh_api_equals_joined_field_is_not_a_read(self):
        self.assertEqual(self._rows("gh api repos/o/r/issues --field=title=x"), [])
        self.assertEqual(self._rows("gh api repos/o/r/issues --raw-field=body=y"), [])
        self.assertEqual(self._rows("gh api repos/o/r/issues --input=payload.json"), [])

    def test_gh_api_glued_short_field_is_not_a_read(self):
        self.assertEqual(self._rows("gh api repos/o/r/issues -ftitle=x"), [])
        self.assertEqual(self._rows("gh api repos/o/r/issues -Fbody=@file"), [])

    def test_explicit_get_overrides_the_field_implication(self):
        # the ONLY exception (R2-2): an explicit GET keeps a field-carrying gh api a read
        rows = self._rows("gh api --method GET search/issues --field=q=harvest")
        self.assertEqual(len(rows), 1)
        rows = self._rows("gh api -X GET search/issues -fq=harvest")
        self.assertEqual(len(rows), 1)

    # gate R3-1: explicit method is an ALLOW-LIST — only GET reads; HEAD/garbage fail CLOSED
    def test_head_method_fails_closed(self):
        self.assertEqual(self._rows("gh api --method HEAD user"), [])
        self.assertEqual(self._rows("gh api --method HEAD repos/o/r -f title=x"), [])

    def test_garbage_method_fails_closed(self):
        self.assertEqual(self._rows("gh api --method GEET user"), [])
        self.assertEqual(self._rows("gh api --method=GEET user -fq=x"), [])

    def test_glued_xhead_fails_closed(self):
        self.assertEqual(self._rows("gh api -XHEAD repos/o/r --input=payload.json"), [])

    # R6-2 sibling (the sweep): a header VALUE `-X` + `GET` must never launder a field-write
    # into the explicit-GET allow-list — arg-consuming gh flags skip their value token
    def test_header_value_cannot_masquerade_as_explicit_get(self):
        self.assertEqual(self._rows('gh api repos/o/r -f a=b -H -X GET'), [])

    def test_header_with_a_real_value_stays_a_read(self):
        rows = self._rows('gh api user -H "X-GitHub-Api-Version: 2022-11-28"')
        self.assertEqual(len(rows), 1)

    def test_plain_gh_api_get_is_a_read(self):
        rows = self._rows("gh api user/orgs")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "gh-cli")

    # S4 gate r7 (manager's SIBLING SWEEP): the gh arg-consuming table is the higher-stakes
    # sibling — a missing flag lets a dash-leading value launder a WRITE into the GET allow-list.
    def test_gh_arg_flags_enumerated(self):
        # deliberate exact pin (audited against `gh help api` 2.88) — the complete value-consuming
        # gh-api flags EXCEPT the method/field ones with dedicated branches; booleans absent
        self.assertEqual(harvest._GH_ARG_FLAGS,
                         ("-H", "--header", "-q", "--jq", "-t", "--template",
                          "--hostname", "--cache", "-p", "--preview"))

    def test_jq_value_cannot_launder_a_field_write_into_a_get(self):
        # -f a=b makes gh api default to POST (a write); -q (--jq) must EAT the `-X`, leaving
        # `GET` a positional — the method stays unset, the field write is NOT laundered to a read
        self.assertEqual(self._rows("gh api repos/o/r -f a=b -q -X GET"), [])

    def test_other_arg_flags_skip_dash_leading_values(self):
        # each arg-consuming gh flag must EAT `-X`, leaving `GET` a positional — so a preceding
        # `-f` field write is NOT laundered into the explicit-GET allow-list (without the skip the
        # `-X GET` would override the field and fake a read)
        for flag in ("--cache", "-t", "--template", "-p", "--preview", "--hostname"):
            cmd = f"gh api repos/o/r -f a=b {flag} -X GET"
            self.assertEqual(self._rows(cmd), [], flag)


class PostBodyAssociatesWithTheWholeCurlInvocation(unittest.TestCase):
    """Codex S4 gate 8: a POST body typed BEFORE its URL (`curl -d '{"query":"x"}' URL`) is still
    found — the URL associates with the whole curl invocation via shlex, not only the tail."""

    def _exa(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "exa"]
        return rows

    def test_body_before_url(self):
        cmd = "curl -s -X POST -d '{\"query\":\"deep dive on OTel\"}' https://api.exa.ai/search"
        rows = self._exa(cmd)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "deep dive on OTel")

    def test_body_after_url_still_works(self):
        cmd = "curl -s https://api.exa.ai/search -d '{\"query\":\"after the url\"}'"
        self.assertEqual(self._exa(cmd)[0]["query_literal"], "after the url")


class CliBranchUsesTheQuoteAwareSpan(unittest.TestCase):
    """Codex S4 gate R3-2 (sibling-sweep rule in action): ONE quote-aware invocation-span seam
    for BOTH the url and the cli branches — the old `re.search(r"[;&|\\n]")` cutter truncated a
    cli invocation at a QUOTED separator (`gh search repos "foo & bar"` → unbalanced quote →
    fail-closed → 0 rows for a real read)."""

    def _rows(self, cmd, source):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == source]

    def test_gh_with_quoted_ampersand_is_a_read(self):
        rows = self._rows('gh search repos "foo & bar" --limit 5', "github")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], 'gh search repos "foo & bar" --limit 5')

    def test_rclone_with_quoted_ampersand_in_the_path_is_a_read(self):
        cmd = "rclone ls 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:pasta & docs'"
        rows = self._rows(cmd, "gdrive-consortium")
        self.assertEqual(len(rows), 1)

    def test_quoted_prose_naming_a_prefix_is_not_a_read(self):
        # sibling sweep of R3-2: the prefix-start regex is not quote-aware either — a prefix
        # matched INSIDE a quoted string must not row (the head-of-invocation rule)
        self.assertEqual(self._rows('git commit -m "run; gh api user"', "github"), [])

    def test_quoted_prose_naming_a_known_script_is_not_a_run(self):
        recs = dict(_RECS)
        recs["scripts"] = {"edge-x": {"source": "x", "interface": "v2-recent"}}
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": 'echo "run; edge-x foo" > notes.txt'}}
        self.assertEqual(harvest.recognize(block, None, recs, session_id="s", transcript_line=0),
                         [])


class UnquotedUrlIsTrimmedToTheShellWord(unittest.TestCase):
    """Codex S4 gate R3-3: _URL_RE eats past an unquoted `&`, but the SHELL splits there — bytes
    after it never reach curl and must never reach query_literal (the manifest would otherwise
    claim a query that was never asked)."""

    def _x_rows(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "x"]

    def test_bytes_after_unquoted_ampersand_never_reach_query_literal(self):
        # unquoted: the shell backgrounds at `&`; curl receives only …?max_results=10
        cmd = "curl -s https://api.twitter.com/2/tweets/search/recent?max_results=10&query=ai"
        rows = self._x_rows(cmd)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["query_literal"],
                          "query=ai sits past the shell word boundary — curl never sent it")

    def test_quoted_url_keeps_its_full_query(self):
        cmd = 'curl -s "https://api.twitter.com/2/tweets/search/recent?max_results=10&query=ai"'
        rows = self._x_rows(cmd)
        self.assertEqual(rows[0]["query_literal"], "ai")


class RedirectionAmpersandIsNotABoundary(unittest.TestCase):
    """Codex S4 gate R3-4 (BLOCKING): an `&` inside a redirection operator (`2>&1`, `>&`, `&>`,
    `&>>`) is I/O plumbing, not a command boundary — splitting there hid the flags after it and
    let `… 2>&1 -X POST` read as GET (a WRITE emitted a row)."""

    def _x_rows(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "x"]

    def test_post_after_2_gt_amp_1_is_seen_and_no_row(self):
        cmd = ('curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai" 2>&1 -X POST '
               '-d \'{"x":1}\'')
        self.assertEqual(self._x_rows(cmd), [])

    def test_plain_get_with_2_gt_amp_1_still_rows(self):
        cmd = 'curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai" 2>&1'
        rows = self._x_rows(cmd)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_amp_gt_redirect_stays_inside_the_invocation(self):
        cmd = 'curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai" &> /tmp/log'
        self.assertEqual(len(self._x_rows(cmd)), 1)

    def test_background_ampersand_still_separates(self):
        # the control: a REAL background `&` (no redirection around it) still bounds — the
        # -X POST belongs to the SECOND command, so the first (GET) still rows
        cmd = ('curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai" & '
               'curl -s -X POST https://api.exa.ai/search -d \'{"query":"q2"}\'')
        rows = self._x_rows(cmd)
        self.assertEqual(len(rows), 1)


class MethodMismatchLandsInTheBlindTally(unittest.TestCase):
    """Sibling sweep of R2-3 (the standing rule): a write-shaped call to a declared host yields
    no row — but it must not silently VANISH; it lands in the unrecognized tally (a network
    call the manifest does not cover, `perna cega nunca silencia` B2)."""

    def test_post_to_a_get_declared_host_is_tallied(self):
        cmd = 'curl -s -X POST "https://api.twitter.com/2/tweets/search/recent?query=ai" -d "{}"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        self.assertEqual([r for r in harvest.recognize(block, None, _RECS,
                                                       session_id="s", transcript_line=0)
                          if r["source"] == "x"], [])
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual(len(unrec), 1)
        self.assertIn("api.twitter.com", unrec[0][1])

    def test_method_matched_read_is_not_tallied(self):
        cmd = 'curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        self.assertEqual(harvest.unrecognized_urls(block, _RECS), [])


class DanglingMethodFlagFailsClosed(unittest.TestCase):
    """Codex S4 gate R4-1: a trailing `-X`/`--method`/`--request` with NO value states an intent
    to set a method we cannot see — it must fail CLOSED (no row; the curl case lands in the
    blind tally), never default to GET/read."""

    def _block(self, cmd):
        return {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}

    def test_gh_trailing_method_is_not_a_read(self):
        for cmd in ("gh api user --method", "gh api user -X"):
            rows = [r for r in harvest.recognize(self._block(cmd), None, _RECS,
                                                 session_id="s", transcript_line=0)
                    if r["source"] == "github"]
            self.assertEqual(rows, [], f"dangling method flag must fail closed: {cmd!r}")

    def test_curl_trailing_x_is_no_row_and_tallied(self):
        cmd = 'curl "https://api.twitter.com/2/tweets/search/recent?query=ai" -X'
        block = self._block(cmd)
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(rows, [], "an unknowable method must never fold as GET")
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual(len(unrec), 1)   # the blind leg never silences (B2)
        self.assertIn("api.twitter.com", unrec[0][1])

    def test_curl_method_is_none_on_dangling_flag(self):
        self.assertIsNone(harvest._curl_method("curl https://x.example/a --request"))
        self.assertIsNone(harvest._curl_method("curl https://x.example/a -X"))


class ContinuationLineCliReadIsRecognized(unittest.TestCase):
    """Codex S4 gate R4-2: `true && \\<newline>gh api user` RUNS gh — the `\\`-newline between
    the separator and the prefix is a line continuation (whitespace to the shell), so the
    head-of-invocation check must treat it as whitespace, for cli prefixes AND known scripts
    (a CLI read never enters the url tally, so dropping it here loses the read SILENTLY)."""

    def test_gh_after_continuation_line_is_a_read(self):
        cmd = "true && \\\ngh api user"
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "github"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "gh api user")

    def test_script_after_continuation_line_is_a_run(self):
        recs = dict(_RECS)
        recs["scripts"] = {"edge-x": {"source": "x", "interface": "v2-recent"}}
        cmd = "true && \\\nedge-x 'ai agents'"
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, recs, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["attribution"], "opaque-script")

    def test_quoted_prose_before_the_prefix_still_rejects(self):
        # the head rule keeps rejecting NON-continuation content (the R3 sibling holds)
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": 'git commit -m "x; gh api user"'}}
        self.assertEqual([r for r in harvest.recognize(block, None, _RECS,
                                                       session_id="s", transcript_line=0)
                          if r["source"] == "github"], [])


class DualMethodInterfacesResolveByMethodKey(unittest.TestCase):
    """Codex S4 gate R4-3 + the structural fix: a source may LEGALLY declare GET and POST
    interfaces on the SAME host/path — the effective method is part of the recognizer MATCH
    KEY, so each call resolves to ITS interface (no mismatch-tally misfire) and neither is
    blind-tallied."""

    _DUAL = {"sources": [{
        "name": "dual", "description": "a dual-method API. Lens: Mundo.",
        "interfaces": [
            {"interface_id": "get-search", "via": "GET https://api.dual.example/search?q=..."},
            {"interface_id": "post-search",
             "via": "POST https://api.dual.example/search (JSON body)"}]}]}

    def _recs(self):
        srcs, findings = sources.validate_sources(self._DUAL)
        self.assertFalse([f for f in findings if f["level"] == "error"], findings)
        return harvest.build_recognizers(sources=srcs)

    def _run(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        recs = self._recs()
        return (harvest.recognize(block, None, recs, session_id="s", transcript_line=0),
                harvest.unrecognized_urls(block, recs))

    def test_get_call_resolves_to_the_get_interface(self):
        rows, unrec = self._run('curl -s "https://api.dual.example/search?q=x"')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "get-search")
        self.assertEqual(rows[0]["query_literal"], "x")
        self.assertEqual(unrec, [])

    def test_post_call_resolves_to_the_post_interface_never_tallied(self):
        rows, unrec = self._run(
            "curl -s -X POST https://api.dual.example/search -d '{\"query\":\"y\"}'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "post-search")
        self.assertEqual(rows[0]["query_literal"], "y")
        self.assertEqual(unrec, [], "a legally-declared POST must not misfire into the tally")

    def test_delete_call_matches_neither_and_is_tallied(self):
        rows, unrec = self._run('curl -s -X DELETE "https://api.dual.example/search?q=x"')
        self.assertEqual(rows, [])
        self.assertEqual(len(unrec), 1)


class MethodMatchKeyIsCaseFoldedAndSymmetric(unittest.TestCase):
    """S4 gate r7 + manager's note: the method match key is CASE-FOLDED on BOTH sides. codex
    spotted the -X branch upper()s the captured value; the resolution keeps that fold and makes
    the DECLARED side (build_recognizers) fold identically — a standard method matches regardless
    of spelling, while a CUSTOM method survives folding and dies at the key."""

    def _rows(self, cmd, source, recs=None):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, recs or _RECS,
                                             session_id="s", transcript_line=0)
                if r["source"] == source]

    def test_lowercase_method_matches_a_get_declared_via(self):
        # (a) `curl -Xget URL` is a real GET — folds to the GET-declared x via → exactly ONE row
        # (manager override of codex: keep the row, dropping it would LOSE the attribution)
        cmd = 'curl -Xget "https://api.twitter.com/2/tweets/search/recent?query=ai"'
        self.assertEqual(len(self._rows(cmd, "x")), 1)

    def test_custom_method_against_a_post_via_is_no_row(self):
        # (b) `-XPOST-FOO` survives folding ("POST-FOO" != "POST") → rejected → blind tally
        cmd = "curl -XPOST-FOO https://api.exa.ai/search -d '{\"query\":\"q\"}'"
        self.assertEqual(self._rows(cmd, "exa"), [])
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        self.assertEqual(len(harvest.unrecognized_urls(block, _RECS)), 1)

    def test_lowercase_declared_via_matches_observed_uppercase(self):
        # (c) SYMMETRY: a source whose via spells the method LOWERCASE still matches an observed
        # uppercase GET — proves the fold is on the DECLARED side too, not luck of the default
        src = [{"name": "lower", "description": "a lowercase-via API. Lens: Mundo.",
                "interfaces": [{"interface_id": "get-x",
                                "via": "get https://api.lower.example/x?q=..."}]}]
        recs = harvest.build_recognizers(sources=src)
        self.assertEqual(recs["url"][0]["method"], "GET")   # declared side canonicalized
        rows = self._rows('curl "https://api.lower.example/x?q=1"', "lower", recs=recs)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "1")

    def test_lowercase_post_via_folds_and_body_field_is_set(self):
        # the fold happens BEFORE the POST→body_field derivation: a lowercase `post` via still
        # gets body_field="query" (the =="POST" check sees the canonical form)
        src = [{"name": "lowpost", "description": "a lowercase POST API. Lens: Mundo.",
                "interfaces": [{"interface_id": "post-x",
                                "via": "post https://api.lowpost.example/s (JSON body)"}]}]
        recs = harvest.build_recognizers(sources=src)
        self.assertEqual(recs["url"][0]["method"], "POST")
        self.assertEqual(recs["url"][0]["body_field"], "query")


class EscapedAmpersandKeepsTheQuery(unittest.TestCase):
    """Codex S4 gate R4-4: in an unquoted URL a `\\`-escaped `&` reaches curl as a literal `&`
    — the word does NOT split there, so the query after it is REAL and must be extracted (the
    R3-3 trim applies only to UNescaped separators)."""

    def _x_rows(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "x"]

    def test_escaped_ampersand_query_is_extracted(self):
        cmd = "curl -s https://api.twitter.com/2/tweets/search/recent?max_results=10\\&query=ai"
        rows = self._x_rows(cmd)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai",
                         "curl received query=ai — the escaped & is part of the shell word")

    def test_unescaped_ampersand_still_trims(self):
        # the R3-3 control stays: an UNescaped & splits the word, query=ai never reached curl
        cmd = "curl -s https://api.twitter.com/2/tweets/search/recent?max_results=10&query=ai"
        rows = self._x_rows(cmd)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["query_literal"])


class CurlMethodFlagTableIsComplete(unittest.TestCase):
    """Codex S4 gate R5-1 + manager's note: the flag→method table in _curl_method is THE one
    place — this ENUMERATION pins it, so a future method-changing curl flag fails here loudly
    instead of silently defaulting to GET."""

    def test_table_enumerated(self):
        # deliberate exact pin — extending the table means extending THIS test
        self.assertEqual(harvest._CURL_FLAG_METHODS, {
            "-I": "HEAD", "--head": "HEAD",
            "-F": "POST", "--form": "POST", "--form-string": "POST", "--json": "POST",
            "-T": "PUT", "--upload-file": "PUT"})

    def test_every_table_flag_maps_end_to_end(self):
        for flag, method in harvest._CURL_FLAG_METHODS.items():
            got = harvest._curl_method(f"curl {flag} val https://api.pond.dev/a")
            self.assertEqual(got, method, f"{flag} must imply {method}")

    def test_head_probe_is_no_row_and_tallied(self):
        # the codex probe verbatim: -I is a HEAD, not a GET — no row, visible in the tally
        cmd = 'curl -I "https://api.twitter.com/2/tweets/search/recent?query=ai"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(rows, [])
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual(len(unrec), 1)
        self.assertIn("api.twitter.com", unrec[0][1])

    def test_form_and_upload_are_not_get_reads(self):
        for cmd in ('curl -F "data=@f" "https://api.twitter.com/2/tweets/search/recent?query=x"',
                    'curl -T file.txt "https://api.twitter.com/2/tweets/search/recent?query=x"'):
            block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
            rows = [r for r in harvest.recognize(block, None, _RECS,
                                                 session_id="s", transcript_line=0)
                    if r["source"] == "x"]
            self.assertEqual(rows, [], cmd)
            self.assertEqual(len(harvest.unrecognized_urls(block, _RECS)), 1, cmd)

    def test_bundled_short_flags_are_seen(self):
        # -sI bundles HEAD; -sX POST bundles an explicit method; -sd '{}' bundles data
        self.assertEqual(harvest._curl_method("curl -sI https://api.pond.dev/a"), "HEAD")
        self.assertEqual(harvest._curl_method("curl -sX POST https://api.pond.dev/a"), "POST")
        self.assertEqual(harvest._curl_method("curl -sd '{}' https://api.pond.dev/a"), "POST")

    def test_glued_header_value_is_not_misread_as_flags(self):
        # -HX-Api-Key:… is a HEADER whose value starts with X — the bundle scan stops at the
        # arg-consuming H, never misreading the value as -X
        self.assertEqual(
            harvest._curl_method("curl -HX-Api-Key:secret https://api.pond.dev/a"), "GET")

    def test_conflicting_implied_methods_fail_closed(self):
        self.assertIsNone(harvest._curl_method("curl -I -T f https://api.pond.dev/a"))


class GluedCustomMethodIsVerbatim(unittest.TestCase):
    """Codex S4 gate R6-1 + manager's note (i): a glued `-X<val>` is taken VERBATIM as the
    effective method — curl sends it as-is — and the method-in-key match rejects an unknown
    method naturally (no row, blind tally); never special-cased to None or GET."""

    def test_glued_custom_method_is_verbatim(self):
        self.assertEqual(harvest._curl_method("curl -XPOST-FOO https://api.pond.dev/a"),
                         "POST-FOO")
        self.assertEqual(harvest._curl_method("curl -X POST-FOO https://api.pond.dev/a"),
                         "POST-FOO")   # spaced form, same verbatim rule

    def test_glued_custom_method_is_no_row_and_tallied(self):
        # the codex repro: curl really sends POST-FOO — never a GET read of x/v2-recent
        cmd = 'curl -XPOST-FOO "https://api.twitter.com/2/tweets/search/recent?query=ai"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(rows, [])
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual(len(unrec), 1)
        self.assertIn("api.twitter.com", unrec[0][1])

    def test_glued_known_method_still_matches_its_interface(self):
        # the control: -XPOST glued resolves to the POST-declared exa interface
        cmd = "curl -XPOST https://api.exa.ai/search -d '{\"query\":\"q\"}'"
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "exa"]
        self.assertEqual(len(rows), 1)


class ArgConsumingLongFlagsSkipTheirValue(unittest.TestCase):
    """Codex S4 gate R6-2 + manager's note (ii): EVERY arg-consuming long flag skips its value
    token — `curl --json -XGET URL` sends POST with the BODY `-XGET`; the value must never be
    parsed as flags. The long table mirrors _CURL_ARG_SHORTS and is pinned by enumeration."""

    def test_arg_consuming_longs_enumerated(self):
        # S4 gate r9 finding 2: this is a CHANGE-DETECTOR — the table was hand-audited against
        # curl 8.5.0 `curl --help all` (every option with an arg placeholder `<…>`/`[…]` minus
        # `--help`), and this asserts it equals a second copy of that literal, so a DROP or a
        # future version drift fails LOUD here. It CANNOT catch a flag that was omitted from BOTH
        # copies — test_arg_consumers_are_a_superset_of_live_curl (below) closes that gap.
        self.assertEqual(harvest._CURL_ARG_LONGS, frozenset((
            "--abstract-unix-socket", "--alt-svc", "--aws-sigv4", "--cacert", "--capath",
            "--cert", "--cert-type", "--ciphers", "--config", "--connect-timeout",
            "--connect-to", "--continue-at", "--cookie", "--cookie-jar", "--create-file-mode",
            "--crlfile", "--curves", "--data", "--data-ascii", "--data-binary", "--data-raw",
            "--data-urlencode", "--delegation", "--dns-interface", "--dns-ipv4-addr",
            "--dns-ipv6-addr", "--dns-servers", "--doh-url", "--dump-header", "--egd-file",
            "--engine", "--etag-compare", "--etag-save", "--expect100-timeout", "--form",
            "--form-string", "--ftp-account", "--ftp-alternative-to-user", "--ftp-method",
            "--ftp-port", "--ftp-ssl-ccc-mode", "--happy-eyeballs-timeout-ms", "--header",
            "--hostpubmd5", "--hostpubsha256", "--hsts", "--interface", "--ipfs-gateway",
            "--json", "--keepalive-time", "--key", "--key-type", "--krb", "--libcurl",
            "--limit-rate", "--local-port", "--login-options", "--mail-auth", "--mail-from",
            "--mail-rcpt", "--max-filesize", "--max-redirs", "--max-time", "--netrc-file",
            "--noproxy", "--oauth2-bearer", "--output", "--output-dir", "--parallel-max",
            "--pass", "--pinnedpubkey", "--preproxy", "--proto", "--proto-default",
            "--proto-redir", "--proxy", "--proxy-cacert", "--proxy-capath", "--proxy-cert",
            "--proxy-cert-type", "--proxy-ciphers", "--proxy-crlfile", "--proxy-header",
            "--proxy-key", "--proxy-key-type", "--proxy-pass", "--proxy-pinnedpubkey",
            "--proxy-service-name", "--proxy-tls13-ciphers", "--proxy-tlsauthtype",
            "--proxy-tlspassword", "--proxy-tlsuser", "--proxy-user", "--proxy1.0", "--pubkey",
            "--quote",
            "--random-file", "--range", "--rate", "--referer", "--request", "--request-target",
            "--resolve", "--retry", "--retry-delay", "--retry-max-time", "--sasl-authzid",
            "--service-name", "--socks4", "--socks4a", "--socks5", "--socks5-gssapi-service",
            "--socks5-hostname", "--speed-limit", "--speed-time", "--stderr", "--telnet-option",
            "--tftp-blksize", "--time-cond", "--tls-max", "--tls13-ciphers", "--tlsauthtype",
            "--tlspassword", "--tlsuser", "--trace", "--trace-ascii", "--trace-config",
            "--unix-socket", "--upload-file", "--url", "--url-query", "--user", "--user-agent",
            "--variable", "--write-out")))

    def test_json_consumes_a_dash_leading_body(self):
        # the codex repro: the body IS `-XGET` — effective method POST, never GET
        self.assertEqual(harvest._curl_method("curl --json -XGET https://api.pond.dev/a"),
                         "POST")

    def test_json_dash_body_is_never_a_get_row(self):
        cmd = 'curl --json -XGET "https://api.twitter.com/2/tweets/search/recent?query=ai"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(rows, [])   # POST against the GET-declared x via
        self.assertEqual(len(harvest.unrecognized_urls(block, _RECS)), 1)

    def test_form_flags_with_spaced_dash_leading_values(self):
        self.assertEqual(harvest._curl_method("curl --form -Xv https://u.example/a"), "POST")
        self.assertEqual(harvest._curl_method("curl --form-string -Xv https://u.example/a"),
                         "POST")
        self.assertEqual(harvest._curl_method("curl --upload-file -f https://u.example/a"),
                         "PUT")

    def test_generic_long_value_is_not_misread_as_flags(self):
        # --header consumes `-XPOST` as its VALUE — the call stays a GET read (a row)
        self.assertEqual(harvest._curl_method("curl --header -XPOST https://u.example/a"),
                         "GET")

    def test_codex_named_longs_consume_a_dash_leading_value(self):
        # S4 gate r7 (codex repro): the flags that WERE missing — a dash-leading value must be
        # eaten, method resolves from the REST (`-d` → POST), never read as `-XGET`.
        # --request-target sets the wire target (arg-consuming), it does NOT itself imply a method.
        for flag in ("--connect-to", "--proxy-header", "--url-query", "--request-target"):
            cmd = f'curl {flag} -XGET https://api.pond.dev/a -d "{{}}"'
            self.assertEqual(harvest._curl_method(cmd), "POST", flag)


class ArgConsumingShortFlagsSkipTheirValue(unittest.TestCase):
    """S4 gate r7 (manager's SIBLING SWEEP): the short arg-consuming table was incomplete —
    `curl -x -XGET URL -d "{}"` had -x (--proxy) NOT skip its dash-leading value, so `-XGET`
    was misread as an explicit GET. The COMPLETE value-consuming short set from `man curl` is
    now pinned by enumeration; every dash-leading value is skipped, method resolves from the rest."""

    def test_arg_consuming_shorts_enumerated(self):
        # S4 gate r9 finding 2: a CHANGE-DETECTOR — hand-audited against curl 8.5.0 (the five
        # dedicated-branch shorts X/K/d/F/T and optional-arg h EXCLUDED; booleans O/I/G/s… absent),
        # asserted against a second copy of the literal so a DROP/version-drift fails LOUD. An
        # ORIGINAL omission is caught by test_arg_consumers_are_a_superset_of_live_curl (below).
        self.assertEqual(harvest._CURL_ARG_SHORTS, set("ACDEHPQUYbcemortuwxyz"))

    def test_codex_named_shorts_consume_a_dash_leading_value(self):
        # the codex repro `-x -XGET` plus the shorts codex named (r C Q Y y): each eats the
        # dash-leading `-XGET`, `-d` implies POST — never a fabricated GET
        for flag in ("-x", "-r", "-C", "-Q", "-Y", "-y"):
            cmd = f'curl {flag} -XGET https://api.pond.dev/a -d "{{}}"'
            self.assertEqual(harvest._curl_method(cmd), "POST", flag)

    def test_proxy_dash_value_is_never_a_get_row(self):
        # end-to-end: -x eats -XGET, the -d body makes it POST → no GET row against the x GET via
        cmd = ('curl -x -XGET "https://api.twitter.com/2/tweets/search/recent?query=ai" '
               '-d "{}"')
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(rows, [])
        self.assertEqual(len(harvest.unrecognized_urls(block, _RECS)), 1)

    def test_removed_boolean_short_does_not_swallow_the_method(self):
        # -O (--remote-name) is a BOOLEAN — it must NOT consume the following `-X POST`
        # (the old table wrongly listed it, swallowing the method into a default GET)
        self.assertEqual(harvest._curl_method("curl -O -X POST https://api.pond.dev/a"), "POST")


class ArgConsumerTablesAreASupersetOfLiveCurl(unittest.TestCase):
    """S4 gate r9 finding 2: the literal enumeration tests are change-detectors — they cannot catch
    a value-consuming flag omitted from BOTH the code and its copied assertion. This closes that
    gap by REGENERATING the arg-consuming set from the live `curl --help all` on the deployment box
    and asserting the code's tables are a SUPERSET (no live arg-consumer is missing). It pins to
    curl 8.5.x (the audited version) and SKIPS elsewhere so other dev boxes / CI never break —
    catching an original omission here, and failing LOUD if a future curl grows a new arg flag."""

    def _live_curl_arg_flags(self):
        import shutil
        import subprocess
        exe = shutil.which("curl")
        if not exe:
            self.skipTest("curl absent — regeneration guard is deployment-box only")
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True).stdout
        m = re.search(r"curl (\d+\.\d+)\.\d+", ver)
        if not m or m.group(1) != "8.5":
            self.skipTest(f"curl is not 8.5.x (audited version) — got {ver.splitlines()[0]!r}")
        out = subprocess.run([exe, "--help", "all"], capture_output=True, text=True).stdout
        # each option line: optional `-x, ` short, a `--long`, then a REQUIRED `<…>` placeholder
        # (a value-consumer). `[…]` optional-arg placeholders (only --proxy/--preproxy here) are
        # NOT `<…>` and are deliberately not derived — the finding scopes the live set to `<…>`.
        line_re = re.compile(
            r"^\s*(?:-(?P<short>[A-Za-z]), )?(?P<long>--[a-z0-9][a-z0-9.-]*)(?P<ph> <[^>]*>)?")
        longs, shorts = set(), set()
        for ln in out.splitlines():
            m = line_re.match(ln)
            if not m or not m.group("ph"):
                continue
            longs.add(m.group("long"))
            if m.group("short"):
                shorts.add(m.group("short"))
        return longs, shorts

    def test_arg_consumers_are_a_superset_of_live_curl(self):
        longs, shorts = self._live_curl_arg_flags()
        # --help is the one `<…>`-shaped OPTIONAL-arg flag (its `<category>` is optional) — excluded
        # by name; the long forms of the dedicated-branch flags (--request/--config/--data/--form/
        # --upload-file) stay in _CURL_ARG_LONGS for parity, so no long subtraction beyond --help.
        longs.discard("--help")
        missing_longs = longs - harvest._CURL_ARG_LONGS
        self.assertEqual(missing_longs, set(),
                         f"live curl 8.5.0 has arg-consuming long flag(s) the code omits: "
                         f"{sorted(missing_longs)}")
        # the five dedicated-branch shorts (X/K/d/F/T) and optional-arg h are handled before the
        # _CURL_ARG_SHORTS set — subtract them from the live set before the superset check
        shorts -= set("XKdFTh")
        missing_shorts = shorts - harvest._CURL_ARG_SHORTS
        self.assertEqual(missing_shorts, set(),
                         f"live curl 8.5.0 has arg-consuming short flag(s) the code omits: "
                         f"{sorted(missing_shorts)}")


class ConfigFlagMakesTheMethodUnknowable(unittest.TestCase):
    """Codex S4 gate R6-3 + manager's note (iii): `-K/--config` loads method/data from a file
    outside the transcript's sight — the method is UNKNOWABLE → None → matches nothing → the
    blind tally picks the call up (fail-closed, never a fabricated GET read)."""

    def test_config_forms_return_none(self):
        for cmd in ("curl -K cfg https://api.pond.dev/a",
                    "curl -Kcfg https://api.pond.dev/a",       # glued
                    "curl -sK cfg https://api.pond.dev/a",     # bundled
                    "curl --config cfg https://api.pond.dev/a",
                    "curl --config=cfg https://api.pond.dev/a"):
            self.assertIsNone(harvest._curl_method(cmd), cmd)

    def test_config_call_is_no_row_and_tallied(self):
        # the codex probe: a local config with request="POST" really sends POST
        cmd = 'curl -K cfg "https://api.twitter.com/2/tweets/search/recent?query=ai"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        self.assertEqual(rows, [])
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual(len(unrec), 1)
        self.assertIn("api.twitter.com", unrec[0][1])


class ParenViaIsLegalOperatorData(unittest.TestCase):
    """Codex S4 gate R5-2 + manager's split: interfaces[].via is OPERATOR DATA, not shell — its
    URL is the whole whitespace-delimited token, parens and all. A legit paren via derives the
    full path + query_param, and the (quoted) call recognizes end-to-end; the shell side stays
    strict (an UNQUOTED paren still bounds the invocation)."""

    _PAREN = {"sources": [{
        "name": "paren", "description": "a paren API. Lens: Mundo.",
        "interfaces": [{"interface_id": "search",
                        "via": "GET https://api.paren.example/v1/search(foo)?q=..."}]}]}

    def _recs(self):
        srcs, findings = sources.validate_sources(self._PAREN)
        self.assertFalse([f for f in findings if f["level"] == "error"], findings)
        return harvest.build_recognizers(sources=srcs)

    def test_recognizer_derives_the_full_paren_path_and_query_param(self):
        rec = [r for r in self._recs()["url"] if r["source"] == "paren"][0]
        self.assertEqual(rec["host"], "api.paren.example")
        self.assertEqual(rec["path"], "/v1/search(foo)")   # the `)` is PART of the via URL
        self.assertEqual(rec["query_param"], "q")

    def test_quoted_paren_call_recognizes_end_to_end(self):
        cmd = 'curl -s "https://api.paren.example/v1/search(foo)?q=hello"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        recs = self._recs()
        rows = harvest.recognize(block, None, recs, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "search")
        self.assertEqual(rows[0]["query_literal"], "hello")
        self.assertEqual(harvest.unrecognized_urls(block, recs), [])

    def test_unquoted_subshell_paren_still_trims(self):
        # the shell control: an UNQUOTED `)` is a separator — the span-trim cuts it off the URL
        cmd = "echo $(curl -s https://api.twitter.com/2/tweets/search/recent?query=ai)"
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "x"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")   # the `)` never entered the URL


class LocalHostFilterIsExactMatch(unittest.TestCase):
    """Codex S4 gate R5-3: the local-host filter compares the EXACT hostname / IP class, never
    a substring of netloc — an external host merely CONTAINING a local marker must reach the
    blind tally (B2: an unknown external call is never invisible)."""

    def _unrec(self, url):
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": f'curl -s "{url}"'}}
        return harvest.unrecognized_urls(block, _RECS)

    def test_lookalike_hosts_are_tallied(self):
        for url in ("https://notlocalhost.example.com/v1?q=x",
                    "https://api.localhost.evil/v1?q=x",
                    "https://0.0.0.0.evil.example/v1?q=x",
                    "https://127.0.0.1.evil.example/v1?q=x"):
            unrec = self._unrec(url)
            self.assertEqual(len(unrec), 1, f"{url} is EXTERNAL — must be tallied")

    def test_real_local_hosts_are_still_filtered(self):
        for url in ("http://localhost:8766/health",
                    "http://127.0.0.1:8788/graph",
                    "http://[::1]:8080/x",
                    "http://0.0.0.0:9000/y",
                    "http://foo.localhost/z"):   # RFC 6761 *.localhost suffix is local
            self.assertEqual(self._unrec(url), [], f"{url} is local — never tallied")


class SpillPointerIsConfinedToTheSession(unittest.TestCase):
    """Codex S4 gate 9: a spilled tool-result pointer can name ANY local file ≤4MB — a followed
    spill is confined to the session's own tool-results/ dir, rejecting external paths and
    symlinks that escape it (an unconfined spill would exfiltrate arbitrary local files)."""

    def test_external_path_is_not_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "sess" / "tool-results"
            base.mkdir(parents=True)
            secret = Path(tmp) / "secret.txt"
            secret.write_text("EXFILTRATED")
            line = {"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": "preview only"}]},
                    "toolUseResult": {"stdout": "the safe stdout", "stderr": "",
                                      "persistedOutputPath": str(secret)}}
            # confined: the external spill is rejected, we fall to the in-line stdout
            self.assertEqual(harvest.result_payload(line, "t1", allowed_base=base), "the safe stdout")
            # unconfined (a direct/pure caller opting out) still follows — the harvest walk supplies base
            self.assertEqual(harvest.result_payload(line, "t1"), "EXFILTRATED")

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "sess" / "tool-results"
            base.mkdir(parents=True)
            outside = Path(tmp) / "outside.txt"
            outside.write_text("ESCAPED")
            link = base / "spill.txt"
            link.symlink_to(outside)   # a symlink INSIDE tool-results/ pointing OUT
            text = ("<persisted-output>\nOutput too large (9KB). "
                    f"Full output saved to: {link}\n\nPreview:")
            self.assertEqual(harvest.follow_pointer(text, allowed_base=base), text)   # not followed

    def test_in_session_spill_is_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "sess" / "tool-results"
            base.mkdir(parents=True)
            spill = base / "abc.txt"
            spill.write_text('{"meta":{"result_count":9}}')
            text = ("<persisted-output>\nFull output saved to: "
                    f"{spill}\n\nPreview:")
            self.assertEqual(harvest.follow_pointer(text, allowed_base=base),
                             '{"meta":{"result_count":9}}')


class CorruptCursorIsVisibleDegradationNotACrash(unittest.TestCase):
    """Codex S4 gate 5: a corrupt cursor file must not crash the harvest — it is reset to {} (the
    ranked/brute dedup makes the whole re-read a no-op) and reported, never a bare json.loads."""

    def test_corrupt_cursor_resets_and_dedups(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD))
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS), 1)
            cursors.write_text("{ this is not: valid json ]]]")   # a corrupt cursor lands
            # no crash; resets to {}, re-reads the whole store, dedup absorbs it → 0 new rows
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS), 0)
            self.assertEqual(len(eventlog.read(types=["grounding.manifest"], log=log)), 1)
            # and a valid cursor was written back
            self.assertIsInstance(json.loads(cursors.read_text()), dict)


class CorruptCursorValuesAreClampedNotCrashed(unittest.TestCase):
    """Codex S4 gate R2-1 (corrupt cursor, round 2): a VALID-JSON cursor file can still carry a
    corrupt per-file VALUE — a string, null, a bool, a negative or non-int number. Each shape
    clamps THAT entry to 0 (visible degradation; the ranked/brute dedup absorbs the re-scan),
    never an int() crash and never a scan from an invalid offset."""

    def _rerun_with_cursor_value(self, value):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            f = store / "-p" / "s1.jsonl"
            _write(f, _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD))
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            self.assertEqual(harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS), 1)
            cursors.write_text(json.dumps({str(f): value}))   # valid JSON, corrupt VALUE
            n = harvest.harvest(log=log, cursors_path=cursors, store_root=store, recognizers=_RECS)
            self.assertEqual(n, 0, f"clamped re-scan with cursor value {value!r} must dedup to 0")
            self.assertEqual(len(eventlog.read(types=["grounding.manifest"], log=log)), 1)
            saved = json.loads(cursors.read_text())[str(f)]   # #62: the value is a stat triple now
            self.assertIsInstance(saved["lines"], int)   # a valid watermark was written back
            self.assertGreaterEqual(saved["lines"], 0)

    def test_string_value(self):
        self._rerun_with_cursor_value("bad")

    def test_null_value(self):
        self._rerun_with_cursor_value(None)

    def test_negative_value(self):
        self._rerun_with_cursor_value(-5)

    def test_bool_value(self):
        self._rerun_with_cursor_value(True)

    def test_float_value(self):
        self._rerun_with_cursor_value(3.7)


class UrlRecognizerIsMethodAware(unittest.TestCase):
    """Codex S4 gate R2-3: host/path alone must not claim a URL occurrence — the curl's EFFECTIVE
    method (-X/--request explicit > -G forces GET > -d implies POST > GET) must equal the method
    the via DECLARES, else no row (a write-shaped call against a GET interface is not that read)."""

    def _rows(self, cmd, source):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == source]

    def test_post_against_get_declared_via_is_no_row(self):
        cmd = ('curl -s -X POST "https://api.twitter.com/2/tweets/search/recent?query=ai" '
               '-d \'{"x":1}\'')
        self.assertEqual(self._rows(cmd, "x"), [])

    def test_implicit_post_via_data_against_get_via_is_no_row(self):
        cmd = 'curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai" -d \'{"x":1}\''
        self.assertEqual(self._rows(cmd, "x"), [])

    def test_dash_g_with_data_is_effective_get_and_rows(self):
        # -G moves the -d payload into the query string: effective GET, matches the GET via
        cmd = ('curl -s -G "https://api.twitter.com/2/tweets/search/recent" '
               '--data-urlencode "query=ai agents"')
        self.assertEqual(len(self._rows(cmd, "x")), 1)

    def test_get_against_post_declared_via_is_no_row(self):
        # exa declares POST; a bare GET fetch of the same URL is not that interface's read
        self.assertEqual(self._rows("curl -s https://api.exa.ai/search", "exa"), [])

    def test_declared_methods_derived_from_the_via(self):
        methods = {(r["source"], r["interface"]): r["method"] for r in _RECS["url"]}
        self.assertEqual(methods[("x", "v2-recent")], "GET")
        self.assertEqual(methods[("exa", "search-deep")], "POST")


class MalformedHitCountRegexIsFailDark(unittest.TestCase):
    """Codex S4 gate R2-4: the declared hit_count regex is operator DATA and can be malformed —
    no capture group, two groups, or a non-numeric capture must fold as hits=None (fail-dark),
    never an int() crash."""

    def _hits(self, hit_count, stdout):
        cfg = {"sources": [{"name": "pond", "description": "a pond. Lens: Mundo.",
                            "interfaces": [{"interface_id": "api",
                                            "via": "GET https://api.pond.dev/search?q=...",
                                            "hit_count": hit_count}]}]}
        srcs, _ = sources.validate_sources(cfg)
        recs = harvest.build_recognizers(sources=srcs)
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": 'curl -s "https://api.pond.dev/search?q=x"'}}
        rows = harvest.recognize(block, stdout, recs, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)   # the row still exists — only the count goes dark
        return rows[0]["hits"]

    def test_no_capture_group_is_unknown(self):
        self.assertIsNone(self._hits(r'"total":\s*\d+', '{"total": 5}'))

    def test_two_capture_groups_is_unknown(self):
        self.assertIsNone(self._hits(r'"(total)":\s*(\d+)', '{"total": 5}'))

    def test_non_numeric_capture_is_unknown(self):
        self.assertIsNone(self._hits(r'"total":\s*"(\w+)"', '{"total": "many"}'))

    def test_unparseable_regex_is_unknown(self):
        self.assertIsNone(self._hits(r'"total": (\d+', '{"total": 5}'))

    def test_valid_single_numeric_group_still_counts(self):
        self.assertEqual(self._hits(r'"total":\s*(\d+)', '{"total": 5}'), 5)


class ConsumedDispatchClosesWithoutUsableTs(unittest.TestCase):
    """Codex S4 gate R2-5: a dispatch CONSUMED by seq+identity whose publish carries no usable
    clock (absent ts, or skewed BEFORE the open) must still CLOSE — conservatively at its own
    start (zero-width), so no later row can map into an interval that should be over."""

    def _harvest_row(self, publish_ts):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "sessP.jsonl",
                   _tool_pair("sessP", "tP", "2026-07-01T10:30:00.000Z", X_CMD))
            log = Path(tmp) / "log.jsonl"
            log.write_text(
                _log_line(1, "2026-07-01T10:00:00+00:00", "dispatch.open",
                          {"dispatch_id": "dP", "session_id": "sessP",
                           "theme": "t", "intent": "why"})
                + _log_line(2, publish_ts, "artefato.published",
                            {"slug": "artP", "dispatch_id": "dP"}))
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            return eventlog.read(types=["grounding.manifest"], log=log)[0]["payload"]

    def test_publish_with_missing_ts_still_closes_by_seq_and_identity(self):
        row = self._harvest_row(None)   # the consuming publish has NO ts at all
        self.assertIsNone(row["dispatch_id"], "consumed dispatch must not stay open-ended")
        self.assertEqual(row["attribution"], "orphan")

    def test_publish_skewed_before_the_open_still_closes(self):
        row = self._harvest_row("2026-07-01T09:00:00+00:00")   # skew: publish ts < open ts
        self.assertIsNone(row["dispatch_id"])
        self.assertEqual(row["attribution"], "orphan")

    def test_unconsumed_dispatch_still_open_ended(self):
        # the control: without the consuming publish the interval stays open and the row maps
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "sessP.jsonl",
                   _tool_pair("sessP", "tP", "2026-07-01T10:30:00.000Z", X_CMD))
            log = Path(tmp) / "log.jsonl"
            log.write_text(_log_line(1, "2026-07-01T10:00:00+00:00", "dispatch.open",
                                     {"dispatch_id": "dP", "session_id": "sessP",
                                      "theme": "t", "intent": "why"}))
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            row = eventlog.read(types=["grounding.manifest"], log=log)[0]["payload"]
            self.assertEqual(row["dispatch_id"], "dP")


class ContractSignatureTakesProjectDirs(unittest.TestCase):
    """Codex S4 gate 4: the contract seam `harvest(log, cursors_path, project_dirs)` — the explicit
    list of store project dirs — is exercised; store_root stays a back-compat shorthand."""

    def test_project_dirs_positional_walks_exactly_those_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-proj-x" / "s1.jsonl",
                   _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z", X_CMD))
            _write(store / "-proj-y" / "s2.jsonl",
                   _tool_pair("s2", "t2", "2026-07-01T10:00:00.000Z", X_CMD))
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            # contract signature, positional: only -proj-x is swept
            n = harvest.harvest(log, cursors, [store / "-proj-x"], recognizers=_RECS)
            self.assertEqual(n, 1)
            refs = {tuple(e["payload"]["raw_ref"])[2]
                    for e in eventlog.read(types=["grounding.manifest"], log=log)}
            self.assertEqual(refs, {"t1"})   # -proj-y never entered

    def test_absent_project_dirs_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                harvest.harvest(Path(tmp) / "log.jsonl", Path(tmp) / "c.json",
                                [Path(tmp) / "missing-a", Path(tmp) / "missing-b"])


class StaleMetaFallsBackFromMapped(unittest.TestCase):
    """Codex S4 gate 3: `mapped` is granted ONLY on the VERIFIED chain meta.json → toolUseId →
    a parent Agent tool_use whose input.prompt exists. A stale/corrupt meta (its toolUseId names
    no such Agent tool_use) falls to declared/unknown — never a fabricated mapped tier."""

    def test_meta_pointing_at_no_agent_tool_use_is_not_mapped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            # the parent transcript exists but carries NO Agent tool_use for the meta's toolUseId
            _write(store / "-proj" / "sessM.jsonl",
                   _tool_pair("sessM", "toolu_x", "2026-07-01T10:30:00.000Z", X_CMD))
            sub = store / "-proj" / "sessM" / "subagents"
            _write(sub / "agent-y.jsonl",
                   _tool_pair("sessM", "toolu_s", "2026-07-01T10:40:00.000Z", X_CMD))
            (sub / "agent-y.meta.json").write_text(json.dumps(
                {"agentType": "ed-explorer", "description": "x", "toolUseId": "toolu_ghost"}))
            log = Path(tmp) / "log.jsonl"
            log.write_text(_log_line(1, "2026-07-01T10:00:00+00:00", "dispatch.open",
                                     {"dispatch_id": "dM", "session_id": "sessM",
                                      "theme": "t", "intent": "why"}))
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store, recognizers=_RECS)
            rows = {tuple(e["payload"]["raw_ref"])[2]: e["payload"]
                    for e in eventlog.read(types=["grounding.manifest"], log=log)}
            sub_row = rows["toolu_s"]
            self.assertNotEqual(sub_row["attribution"], "mapped", "stale meta must not map")
            self.assertEqual(sub_row["attribution"], "declared")   # inside dM, which declared theme
            # the subagent provenance is still attached — the read IS a subagent's, only the tier falls
            self.assertEqual(sub_row["subagent"]["toolUseId"], "toolu_ghost")


# --- golden fixtures: the mandatory two-dispatch interleaved + subagent case ------------------

GOLD_SID = "sessG-2f1c8a90-real-shape"
GOLD_SLUG = "-home-roberto-edge-wt-grounding"


def _lay_golden_store(tmp):
    """Lay the golden fixture files (REAL store shape, sanitized) into a temp store: a main
    session transcript, a subagent transcript + meta.json, and the S2 dispatch log with anchors."""
    store = Path(tmp) / "projects"
    proj = store / GOLD_SLUG
    (proj / GOLD_SID / "subagents").mkdir(parents=True)
    (proj / f"{GOLD_SID}.jsonl").write_text((FIX / "golden_session_main.jsonl").read_text())
    (proj / GOLD_SID / "subagents" / "agent-g.jsonl").write_text(
        (FIX / "golden_session_sub.jsonl").read_text())
    (proj / GOLD_SID / "subagents" / "agent-g.meta.json").write_text(
        (FIX / "golden_session_sub.meta.json").read_text())
    log = Path(tmp) / "log.jsonl"
    log.write_text((FIX / "golden_dispatch_log.jsonl").read_text())
    return store, proj, log


class GoldenTwoDispatchInterleaved(unittest.TestCase):
    """The mandatory case as GOLDEN fixtures (Codex S4 gate 10): a real-shaped main transcript +
    a real subagent transcript + its meta.json + the S2 dispatch log with anchors, harvested end
    to end. Two dispatches interleaved (dG1 [10:00→11:00 publish], gap, dG2 [12:00→)), the
    subagent's read mapped through the VERIFIED meta→Agent-prompt chain, an out-of-interval read
    as orphan, duplicate queries as distinct occurrence indexes, mapping by the monotonic session
    ANCHOR (never wall clock), corrupt cursor absorbed."""

    def _rows_by_tuid(self, log):
        return {tuple(e["payload"]["raw_ref"])[2]: e["payload"]
                for e in eventlog.read(types=["grounding.manifest"], log=log)}

    def test_end_to_end_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, proj, log = _lay_golden_store(tmp)
            n = harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", project_dirs=[proj], recognizers=_RECS)
            self.assertEqual(n, 5)   # r1, s1(subagent), r2, r3×2 duplicate queries
            rows = self._rows_by_tuid(log)
            # r1 read inside dG1 — the dispatch declared theme/intent → declared, anchor-mapped
            self.assertEqual(rows["toolu_r1"]["dispatch_id"], "dG1")
            self.assertEqual(rows["toolu_r1"]["attribution"], "declared")
            self.assertEqual(rows["toolu_r1"]["geometry"], "themed")
            # subagent read — mapped through the VERIFIED meta.json → Agent prompt chain
            self.assertEqual(rows["toolu_s1"]["dispatch_id"], "dG1")
            self.assertEqual(rows["toolu_s1"]["attribution"], "mapped")
            self.assertEqual(rows["toolu_s1"]["subagent"]["toolUseId"], "toolu_agent_1")
            # the gap read (after dG1 consumed, before dG2) → orphan, NEVER "last open" (E1)
            self.assertIsNone(rows["toolu_r2"]["dispatch_id"])
            self.assertEqual(rows["toolu_r2"]["attribution"], "orphan")

    def test_duplicate_queries_are_distinct_occurrence_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, proj, log = _lay_golden_store(tmp)
            harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", project_dirs=[proj], recognizers=_RECS)
            r3 = [e["payload"] for e in eventlog.read(types=["grounding.manifest"], log=log)
                  if e["payload"]["raw_ref"][2] == "toolu_r3"]
            self.assertEqual(len(r3), 2)   # ONE tool call, TWO duplicate queries → TWO rows (E2b)
            self.assertNotEqual(r3[0]["raw_ref"][3], r3[1]["raw_ref"][3])   # distinct occ index
            self.assertEqual({r["query_literal"] for r in r3}, {"ai%20agents"})
            self.assertEqual({r["dispatch_id"] for r in r3}, {"dG2"})

    def test_folds_cleanly_and_corrupt_cursor_is_absorbed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, proj, log = _lay_golden_store(tmp)
            cursors = Path(tmp) / "c.json"
            harvest.harvest(log=log, cursors_path=cursors, project_dirs=[proj], recognizers=_RECS)
            g = eventlog.grounding_at(log=log)
            self.assertEqual(g["corrupt"], 0, "every golden row folds cleanly (E2b shape)")
            cursors.write_text("]] corrupt [[")
            self.assertEqual(
                harvest.harvest(log=log, cursors_path=cursors, project_dirs=[proj], recognizers=_RECS), 0,
                "corrupt cursor resets, dedup absorbs the whole re-read")


class SourcesAreOperatorDataNotCodeKnowledge(unittest.TestCase):
    """Voz invariant (gate 11 — the Overleaf test): a source is OPERATOR DATA; the code never
    knows one by name. A brand-new source declared ONLY in agent.yaml (never seen by the codebase)
    must be harvested with ZERO code change — recognized, query extracted, folded and
    dispatch-mapped like any built-in. Its hit-count too, when the interface declares one."""

    _OVERLEAF = {"sources": [{
        "name": "overleaf", "description": "Overleaf projects. Lens: Atividade.",
        "interfaces": [{"interface_id": "v2-search",
                        "via": "GET https://api.overleaf.com/v2/search?q=...",
                        "hit_count": r'"total"\s*:\s*(\d+)'}]}]}

    def _recs(self):
        srcs, findings = sources.validate_sources(self._OVERLEAF)
        self.assertFalse([f for f in findings if f["level"] == "error"], findings)
        return harvest.build_recognizers(sources=srcs)

    def test_never_seen_source_is_recognized_from_agent_yaml_alone(self):
        recs = self._recs()
        pairs = {(r["source"], r["interface"]) for r in recs["url"]}
        self.assertIn(("overleaf", "v2-search"), pairs)   # derived from via, no code knew it
        cmd = 'curl -s "https://api.overleaf.com/v2/search?q=lyx%20export"'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, '{"total":7,"items":[]}', recs,
                                 session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["source"], rows[0]["interface"]), ("overleaf", "v2-search"))
        self.assertEqual(rows[0]["query_literal"], "lyx%20export")   # byte-identical from the URL
        self.assertEqual(rows[0]["lens"], "atividade")               # from the prose, mechanically
        self.assertEqual(rows[0]["hits"], 7)                         # from the DECLARED hit_count

    def test_never_seen_source_folds_and_dispatch_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "sO.jsonl",
                   _tool_pair("sO", "tO", "2026-07-01T10:30:00.000Z",
                              'curl -s "https://api.overleaf.com/v2/search?q=x"',
                              stdout='{"total":3}'))
            log = Path(tmp) / "log.jsonl"
            log.write_text(_log_line(1, "2026-07-01T10:00:00+00:00", "dispatch.open",
                                     {"dispatch_id": "dO", "session_id": "sO",
                                      "theme": "t", "intent": "why"}))
            n = harvest.harvest(log=log, cursors_path=Path(tmp) / "c.json", store_root=store,
                                recognizers=self._recs())
            self.assertEqual(n, 1)
            row = eventlog.read(types=["grounding.manifest"], log=log)[0]["payload"]
            self.assertEqual(row["source"], "overleaf")
            self.assertEqual(row["dispatch_id"], "dO")        # dispatch-mapped like any built-in
            self.assertEqual(row["attribution"], "declared")
            g = eventlog.grounding_at(log=log)
            self.assertEqual(g["corrupt"], 0)                 # folds cleanly through S1


class HarvestKnowsNoSourceByName(unittest.TestCase):
    """Voz invariant (gate 12 — the no-hardcode guard): tools/harvest.py must not special-case any
    DECLARED source by name or host — all recognition derives from agent.yaml interfaces[].via.
    The ONLY sanctioned literals are the harness-native pseudo-source tool names (WebSearch/
    WebFetch) and generic protocol machinery. This guard parses the module and asserts no declared
    source's host (nor the concrete host/script hardcodes this slice removed) appears as a
    NON-docstring string literal in the recognizer logic — plus (NIT R2-6) that no literal
    EXACTLY equals a declared source name or interface_id (exact match, not substring: a
    short name like "x" must not false-positive on unrelated strings that contain an x)."""

    def _code_literals(self):
        """Every NON-docstring string constant in tools/harvest.py (docstrings excluded — prose
        may name sources as EXAMPLES; the invariant is about LOGIC, not explanation)."""
        import ast
        tree = ast.parse((REPO / "tools" / "harvest.py").read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", [])
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docstrings.add(id(body[0].value))
        return [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings]

    def test_no_declared_source_identity_in_recognizer_logic(self):
        from urllib.parse import urlsplit
        literals = "\n".join(self._code_literals()).lower()
        # forbidden identity = every declared source's URL host (straight from agent.yaml — self-
        # maintaining) + the concrete host/script literals this slice removed from the code
        forbidden = {"api.twitter.com", "export.arxiv.org", "hn.algolia.com", "edge-x", "api.x.ai"}
        srcs = _seam_sources()
        for s in srcs:
            for iface in s.get("interfaces", []) or []:
                # R5-2: the via is operator data — parse it with the VIA grammar, not the shell's
                m = harvest._VIA_URL_RE.search(iface.get("via") or "")
                if m:
                    host = urlsplit(m.group(0)).netloc
                    if host:
                        forbidden.add(host.lower())
        leaked = sorted(t for t in forbidden if t and t in literals)
        self.assertEqual(leaked, [],
                         f"harvest.py hardcodes declared-source identity in its logic: {leaked} "
                         "— derive from agent.yaml interfaces[].via instead")

    def test_no_literal_equals_a_declared_source_name_or_interface_id(self):
        # NIT R2-6: EXACT-match check on top of the host-substring one — a code literal that IS
        # a declared source name / interface_id would special-case that source in logic
        lit_values = set(self._code_literals())
        declared = set()
        srcs = _seam_sources()
        for s in srcs:
            declared.add(s.get("name"))
            for iface in s.get("interfaces", []) or []:
                declared.add(iface.get("interface_id"))
        declared.discard(None)
        self.assertTrue(declared, "guard must not run vacuous — agent.yaml declares sources")
        leaked = sorted(lit_values & declared)
        self.assertEqual(leaked, [],
                         f"harvest.py carries a declared source name / interface_id as a code "
                         f"literal: {leaked} — source identity is operator data, never code")


class UrlBranchGatesOnHttpClientAndOperand(unittest.TestCase):
    """S4 gate r8 Finding A: a URL is a read ONLY when its enclosing invocation's command word is
    a generic HTTP client AND the URL is a positional operand (or a --url value) — killing the
    `echo "https://…"` and `curl -H "Referer: https://…"` phantoms that trusted any URL substring
    anywhere in the command. Both gates derive from the SAME _curl_scan walk as the method."""

    X_URL = "https://api.twitter.com/2/tweets/search/recent?query=ai"

    def _x_rows(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == "x"]

    def test_echoed_url_is_not_a_read(self):
        # (a) command word `echo` is not an HTTP client — the URL was printed, never fetched
        self.assertEqual(self._x_rows(f'echo "{self.X_URL}"'), [])

    def test_url_in_a_header_value_is_not_a_read(self):
        # (b) the x-url is the value of -H (a header), not the fetched operand; example.invalid IS
        # the operand but matches no interface — so no x row, and no phantom
        cmd = f'curl -H "Referer: {self.X_URL}" https://example.invalid/'
        self.assertEqual(self._x_rows(cmd), [])

    def test_positional_operand_still_rows(self):
        # (c) regression guard: a legit positional-operand curl still rows with its query
        rows = self._x_rows(f"curl '{self.X_URL}'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_url_flag_value_rows(self):
        # (d) `--url <val>` is a URL operand too — it rows
        rows = self._x_rows(f"curl --url '{self.X_URL}'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_header_value_url_is_not_even_tallied(self):
        # sibling sweep: the -H value URL was never fetched, so it is neither a row NOR a phantom
        # network tally — only example.invalid (the real operand, unknown host) is tallied
        cmd = f'curl -H "Referer: {self.X_URL}" https://example.invalid/'
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual([h for _, h in unrec], ["example.invalid"])

    def test_untokenizable_curl_fails_closed_to_the_visible_tally(self):
        # standing rule: unparseable input fails CLOSED — a network-shaped curl we cannot tokenize
        # (unbalanced quote) is still visible in the blind tally, never silently dropped
        cmd = 'curl "https://unknown-api.example.com/v1/search?q=x'   # unterminated quote
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        self.assertEqual(self._x_rows(cmd), [])   # no confident row
        unrec = harvest.unrecognized_urls(block, _RECS)
        self.assertEqual([h for _, h in unrec], ["unknown-api.example.com"])


class ShellCommentBytesAreNotTokens(unittest.TestCase):
    """S4 gate r9 Finding 1: a bash comment (word-start unquoted `#` to end-of-line) is NOT
    tokens — a `http(s)://…` or a `curl`/`gh` word riding in a comment was never run, so it must
    yield no phantom ROW, no phantom TALLY, and must not flip a real read's method/guard. The fix
    lives at the shared span seam (`_sep_positions` truncates every invocation span at the comment;
    `_comment_regions` drops matches that START in a comment) so ALL four consumers benefit at once
    — the url/operand path, `unrecognized_urls`, `_cli_read_ok` and `_remote_read_match`."""

    HN = "https://hn.algolia.com/api/v1/search?query="   # a GET url interface with query_param

    def _probe(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        rows = harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
        unrec = harvest.unrecognized_urls(block, _RECS)
        return [(r["source"], r["query_literal"]) for r in rows], [h for _, h in unrec]

    # --- the three PROVEN wrong cases: no phantom row AND no phantom tally ------------------------
    def test_comment_url_after_a_real_read_is_no_row(self):
        rows, unrec = self._probe(f"curl -s https://example.org/ok  # {self.HN}LEAKED")
        self.assertNotIn(("hn", "LEAKED"), rows)          # the comment url never rowed
        self.assertNotIn("hn.algolia.com", unrec)         # nor tallied
        self.assertEqual(unrec, ["example.org"])          # only the real (unknown) operand tallies

    def test_bare_client_then_comment_url_is_no_row(self):
        rows, unrec = self._probe(f"curl # {self.HN}Z")
        self.assertEqual(rows, [])
        self.assertEqual(unrec, [])

    def test_comment_url_yields_no_phantom_tally(self):
        # the real operand still rows; the comment's phantom host is NOT tallied
        rows, unrec = self._probe(f"curl {self.HN}real # https://phantom.example.com/x")
        self.assertEqual(rows, [("hn", "real")])
        self.assertEqual(unrec, [])                        # phantom.example.com never happened

    def test_commented_out_client_word_is_no_row(self):
        # robustness beyond the coincidence that a comment's first word is a bare url: a whole
        # `# curl <url>` is dead — the `_in_comment` drop, not first-token luck, kills it
        rows, unrec = self._probe(f"curl {self.HN}real # curl {self.HN}EVIL")
        self.assertEqual(rows, [("hn", "real")])
        self.assertEqual(unrec, [])

    # --- must-not-break guards -------------------------------------------------------------------
    def test_url_fragment_hash_is_not_a_comment(self):
        # `#anchor` is glued inside the url word (and quoted) — a fragment, never a comment
        rows, _ = self._probe(f"curl '{self.HN}frag#anchor'")
        self.assertEqual(rows, [("hn", "frag#anchor")])

    def test_hash_inside_a_quoted_word_is_literal(self):
        # the `#` inside the -H value is literal; the real operand still rows
        rows, _ = self._probe(f'curl -H "X: a#b" {self.HN}q')
        self.assertEqual(rows, [("hn", "q")])

    def test_echoed_hash_prose_is_unaffected(self):
        rows, unrec = self._probe("echo '# not a comment'")
        self.assertEqual((rows, unrec), ([], []))

    # --- the CLI-guard sibling sweep (the paths the fix must ALSO cover) --------------------------
    def test_trailing_comment_does_not_flip_a_read_guard_to_write(self):
        # `_cli_read_ok` must not see the comment's `-X POST`: the span truncates at `#`, so the
        # real `gh api user` stays a read row (the guard never reads a mutating method from a comment)
        rows, _ = self._probe("gh api user # -X POST")
        self.assertEqual(rows, [("github", "gh api user")])

    def test_commented_out_cli_prefix_is_no_row(self):
        # a `# gh api user` tail must not phantom-row (the boundary regex + head check + the
        # comment being dead all agree)
        rows, _ = self._probe("echo hi # gh api user")
        self.assertEqual(rows, [])
        rows, _ = self._probe("echo hi # ; gh api user")   # a `;` riding in the comment mustn't split
        self.assertEqual(rows, [])

    def test_comment_ends_at_newline_next_line_still_reads(self):
        rows, _ = self._probe(f"curl {self.HN}A # note\ncurl {self.HN}B")
        self.assertEqual(rows, [("hn", "A"), ("hn", "B")])

    def test_comment_regions_is_quote_aware(self):
        # the seam itself: a `#` in quotes / glued in a word is not a comment region
        self.assertEqual(harvest._comment_regions("curl 'http://h/p#frag'"), [])
        self.assertEqual(harvest._comment_regions('curl -H "X: a#b" https://h'), [])
        self.assertEqual(harvest._comment_regions("curl https://h # note"), [(15, 21)])
        self.assertEqual(harvest._comment_regions("a #x\nb #y"), [(2, 4), (7, 9)])

    # --- escaped-preceder guard: a `#` after a `\`-escape-consumed byte is a LITERAL `#` ----------
    def test_escaped_space_before_hash_is_not_a_comment(self):
        # `\ ` makes the space part of the WORD, so the `#` glued after it is a literal `#`, not a
        # comment. bash passes TWO real args (`https://real.example #x`, `https://phantom.example`);
        # the trailing real url must TALLY again — the old scan opened a phantom comment and dropped it
        cmd = r"curl https://real.example\ #x https://phantom.example"
        self.assertEqual(harvest._comment_regions(cmd), [])   # seam: no phantom comment
        self.assertEqual(harvest._sep_positions(cmd), [])     # sibling seam agrees
        _, unrec = self._probe(cmd)
        self.assertIn("phantom.example", unrec)               # the dropped url is tallied again

    def test_escaped_newline_continuation_before_hash_is_not_a_comment(self):
        # `\`+newline is a REMOVED line-continuation → the args join and the `#` after it is literal
        # (the realistic trigger). bash args `https://a#x`, `https://b.example`; the trailing url
        # must TALLY again, not be swallowed by a phantom end-of-line comment
        cmd = "curl https://a\\\n#x https://b.example"
        self.assertEqual(harvest._comment_regions(cmd), [])
        self.assertEqual(harvest._sep_positions(cmd), [])
        _, unrec = self._probe(cmd)
        self.assertIn("b.example", unrec)

    def test_genuine_word_start_hash_after_unescaped_ws_is_still_a_comment(self):
        # the fix is surgical: an UNescaped whitespace/`;`/`&`/newline before `#` still opens a
        # comment, so a phantom url after it is still dropped, and a `\#` literal arg is unaffected
        rows, unrec = self._probe(f"curl {self.HN}real # https://phantom.example")
        self.assertEqual(rows, [("hn", "real")])
        self.assertNotIn("phantom.example", unrec)
        _, unrec2 = self._probe(r"curl \# https://c.example")   # `\#` is a literal arg, no comment
        self.assertIn("c.example", unrec2)


class DeclaredMethodCaptureIsSymmetric(unittest.TestCase):
    """S4 gate r8 Finding C: the declared method is the VERBATIM word immediately before the URL
    in the via (`.upper()`), symmetric with _curl_scan's observed-side capture — so HEAD/OPTIONS/
    custom methods are captured, never silently folded to GET by the old fixed whitelist that
    omitted HEAD (which let a plain GET curl match a HEAD via while `curl -I` was tallied)."""

    def _recs(self, method_word):
        src = [{"name": "probe", "description": "a probe API. Lens: Mundo.",
                "interfaces": [{"interface_id": "check",
                                "via": f"{method_word} https://api.head.example/check?q=..."}]}]
        return harvest.build_recognizers(sources=src)

    def _rows(self, cmd, recs):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, recs, session_id="s", transcript_line=0)
                if r["source"] == "probe"]

    def test_declared_head_is_captured_and_matches_dash_I(self):
        recs = self._recs("HEAD")
        self.assertEqual(recs["url"][0]["method"], "HEAD")   # not folded to GET
        self.assertEqual(
            len(self._rows('curl -I "https://api.head.example/check?q=ai"', recs)), 1)

    def test_declared_head_does_not_match_a_plain_get(self):
        recs = self._recs("HEAD")   # GET ≠ HEAD → no row (the call is a GET, the via is HEAD)
        self.assertEqual(self._rows('curl "https://api.head.example/check?q=ai"', recs), [])

    def test_lowercase_options_via_matches_dash_X_options(self):
        recs = self._recs("options")   # symmetry: lowercase declared OPTIONS ↔ observed -X OPTIONS
        self.assertEqual(recs["url"][0]["method"], "OPTIONS")
        self.assertEqual(
            len(self._rows('curl -X OPTIONS "https://api.head.example/check?q=ai"', recs)), 1)


class HttpClientAllowListIsClientKnowledgeNotSource(unittest.TestCase):
    """S4 gate r8 (E8/Voz binding): the HTTP-client allow-list is CLIENT knowledge (curl/wget/…),
    subject-blind protocol machinery — NOT source knowledge. A brand-new synthetic source declared
    ONLY in agent.yaml (the codebase has never seen it) is harvested via `curl` with ZERO code
    change, while the SAME URL in an `echo` is neither a read nor a phantom network tally."""

    _SRC = [{"name": "synthsrc", "description": "a never-seen source. Lens: Atividade.",
             "interfaces": [{"interface_id": "api",
                             "via": "GET https://overleaf-fake.example/api?q=..."}]}]

    def _recs(self):
        return harvest.build_recognizers(sources=self._SRC)

    def test_new_source_via_curl_rows_with_zero_code_change(self):
        recs = self._recs()
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": 'curl -s "https://overleaf-fake.example/api?q=lyx"'}}
        rows = harvest.recognize(block, None, recs, session_id="s", transcript_line=0)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["source"], rows[0]["interface"]), ("synthsrc", "api"))
        self.assertEqual(rows[0]["query_literal"], "lyx")

    def test_same_url_echoed_is_neither_a_read_nor_a_tally(self):
        recs = self._recs()
        block = {"type": "tool_use", "id": "t1", "name": "Bash",
                 "input": {"command": 'echo "https://overleaf-fake.example/api?q=lyx"'}}
        self.assertEqual(harvest.recognize(block, None, recs, session_id="s", transcript_line=0), [])
        self.assertEqual(harvest.unrecognized_urls(block, recs), [])   # echo never fetched it


class ExecWrapperPrefixesDoNotDropTheFetch(unittest.TestCase):
    """S4 gate r11 Finding 1: an exec-wrapper prefix (`timeout`/`sudo`/`env`/`nice`/…) pushes the
    HTTP client out of first position — command_word must be read THROUGH the wrapper, else the
    fetch vanishes from BOTH the manifest AND the blind tally (defeating the B2 no-silent-vanish
    invariant). The wrapper is subject-blind shell machinery (E8-safe), same category as the
    _HTTP_CLIENTS allow-list. Over-skipping can only DROP (never a phantom)."""

    def _rows(self, cmd, src):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == src]

    def _tally(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [h for _, h in harvest.unrecognized_urls(block, _RECS)]

    def test_timeout_wrapped_exa_post_rows(self):
        rows = self._rows('timeout 30 curl -X POST https://api.exa.ai/search -d \'{"query":"x"}\'',
                          "exa")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "x")

    def test_env_assignment_wrapped_exa_post_rows(self):
        rows = self._rows('env EXA_KEY=k curl -X POST https://api.exa.ai/search -d \'{"query":"y"}\'',
                          "exa")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "y")

    def test_sudo_wrapped_x_get_rows(self):
        rows = self._rows("sudo curl https://api.twitter.com/2/tweets/search/recent?query=ai", "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_nice_wrapped_hn_get_rows(self):
        rows = self._rows("nice curl https://hn.algolia.com/api/v1/search?query=z", "hn")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "z")

    def test_sudo_flag_and_arg_wrapped_rows(self):
        # `-u www` is a wrapper flag + its value — command_word must skip PAST both to reach curl
        rows = self._rows(
            "sudo -u www curl https://api.twitter.com/2/tweets/search/recent?query=ai", "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_timeout_echo_is_still_excluded(self):
        # a wrapper + a NON-client command (echo) — the URL was printed, never fetched: the skip
        # lands on `echo`, correctly NO row and NO phantom tally (the fail-closed direction)
        cmd = "timeout echo https://api.exa.ai/search"
        self.assertEqual(self._rows(cmd, "exa"), [])
        self.assertEqual(self._tally(cmd), [])

    def test_wrapper_feeds_the_blind_tally_on_an_undeclared_method(self):
        # exa declares POST; a WRAPPED GET is undeclared → no row, but the wrapper path must still
        # tally it (a network call the manifest does not cover must never silently vanish, B2)
        cmd = "timeout 30 curl https://api.exa.ai/search"
        self.assertEqual(self._rows(cmd, "exa"), [])
        self.assertEqual(self._tally(cmd), ["api.exa.ai"])


class FullPathBuiltinAndUppercaseSchemeDoNotDropTheFetch(unittest.TestCase):
    """S4 gate r12 (INVARIANT B): a real fetch must land in the manifest row OR the blind tally,
    never vanish from BOTH. Three recognition-surface leaks closed: B-1 a full-path/relative-path
    client (`/usr/bin/curl`, `./curl`, `sudo /usr/bin/curl`) — basename-normalized before the
    client/wrapper membership tests; B-2 the `command`/`exec` shell builtins that launch a client;
    B-3 an uppercase URL scheme (`HTTPS://`) that curl fetches case-insensitively. Anti-phantom
    (INVARIANT A) held throughout: basename/builtin peeling onto a non-client, or an EXACT-basename
    near-miss (`mycurl`/`curl.sh`), still emits NO row and NO tally."""

    _X = "https://api.twitter.com/2/tweets/search/recent?query=ai"

    def _rows(self, cmd, src):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == src]

    def _tally(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [h for _, h in harvest.unrecognized_urls(block, _RECS)]

    # --- B-1: full-path / relative-path clients (and wrappers) basename-normalize -----------------
    def test_full_path_curl_rows(self):
        rows = self._rows("/usr/bin/curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_relative_path_curl_rows(self):
        rows = self._rows("./curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_sudo_full_path_curl_rows(self):
        # the wrapper AND the client are both full-path — both basenames must normalize
        rows = self._rows("sudo /usr/bin/curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_full_path_wget_tallies_undeclared_host(self):
        # a full-path wget to an UNDECLARED host: no row, but the client is recognized so the
        # network call still reaches the blind tally (never vanishes from both)
        cmd = "/usr/bin/wget https://real.example/p"
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), ["real.example"])

    def test_mycurl_is_not_a_client_exact_basename(self):
        # EXACT basename match: `mycurl` != `curl` — not a client, no row AND no phantom tally
        cmd = "mycurl " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    def test_curl_dot_sh_is_not_a_client_exact_basename(self):
        cmd = "curl.sh " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    def test_full_path_echo_is_not_a_phantom(self):
        # basename peel lands on a non-client (echo) — the URL was printed, never fetched
        cmd = "/usr/bin/echo " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    # --- B-2: `command` / `exec` shell builtins launch a client ----------------------------------
    def test_command_builtin_rows(self):
        rows = self._rows("command curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_exec_builtin_rows(self):
        rows = self._rows("exec curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_exec_dash_a_name_reaches_curl(self):
        # `exec -a NAME curl`: -a is a non-glued flag whose bare value NAME is skipped, landing on curl
        rows = self._rows("exec -a mycurl curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_command_echo_is_not_a_phantom(self):
        cmd = "command echo " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    # --- B-3: uppercase URL scheme is extracted and still satisfies https_only --------------------
    def test_uppercase_scheme_rows_and_satisfies_https_only(self):
        rows = self._rows("curl HTTPS://export.arxiv.org/api/query?search_query=ai", "arxiv")
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["idiom_conforme"], True)   # HTTPS:// still satisfies https_only

    def test_mixed_case_scheme_is_extracted(self):
        rows = self._rows("curl Https://api.twitter.com/2/tweets/search/recent?query=ai", "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")


class BareEnvAssignmentPrefixIsSkipped(unittest.TestCase):
    """S4 gate r13: a leading BARE `NAME=VALUE` env-assignment run (no `env` keyword) sets env for
    the command — `_command_word` must skip PAST it. ONE root fixes two violations: INVARIANT A —
    an assignment whose VALUE is a path-to-a-client (`X=/usr/bin/curl echo …`) must be CONSUMED,
    not basenamed to `curl` (before r13 the basename turned this gap into an active phantom);
    INVARIANT B — the common shell idiom `DEBUG=1 curl …` / `HTTPS_PROXY=… curl …` (a REAL fetch)
    must land on `curl` and produce rows/tally instead of vanishing from BOTH."""

    _X = "https://api.twitter.com/2/tweets/search/recent?query=ai"

    def _rows(self, cmd, src):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == src]

    def _tally(self, cmd):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [h for _, h in harvest.unrecognized_urls(block, _RECS)]

    # --- INVARIANT A: bare assignment with a path-to-client VALUE is NOT a phantom ----------------
    def test_assignment_path_value_then_echo_is_not_a_phantom(self):
        # X=/usr/bin/curl sets env; echo runs (prints the URL, never fetches) — NO row, NO tally
        cmd = "X=/usr/bin/curl echo " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    def test_assignment_path_value_bare_url_is_not_a_phantom(self):
        # FOO=/usr/bin/curl then a bare URL (no command) — assignment consumed, lands on the URL
        # token (a non-client) → NO row, NO tally
        cmd = "FOO=/usr/bin/curl " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    def test_plain_assignment_then_echo_is_not_a_phantom(self):
        cmd = "X=1 echo " + self._X
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), [])

    # --- INVARIANT B: bare assignment before a REAL client → rows/tally, never vanish -------------
    def test_debug_flag_then_curl_rows(self):
        rows = self._rows("DEBUG=1 curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_https_proxy_then_curl_rows(self):
        rows = self._rows("HTTPS_PROXY=http://p curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_two_assignments_then_curl_rows(self):
        rows = self._rows("DEBUG=1 NO_COLOR=1 curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_bare_assignment_then_curl_undeclared_host_tallies(self):
        cmd = "DEBUG=1 curl https://real.example/p"
        self.assertEqual(self._rows(cmd, "x"), [])
        self.assertEqual(self._tally(cmd), ["real.example"])

    # --- assignment-only (no command ran): no row, no tally --------------------------------------
    def test_assignment_only_is_neither_row_nor_tally(self):
        for cmd in ("X=1", "X=1 Y=2", "X=/usr/bin/curl"):
            self.assertEqual(self._rows(cmd, "x"), [], cmd)
            self.assertEqual(self._tally(cmd), [], cmd)

    # --- assignment + wrapper co-occur (leading assignment, then wrapper, then in-wrapper) --------
    def test_assignment_then_sudo_curl_rows(self):
        rows = self._rows("DEBUG=1 sudo curl " + self._X, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query_literal"], "ai")

    def test_env_in_wrapper_assignment_still_rows(self):
        # regression guard: the in-wrapper assignment skip (`env X=1 curl`, `sudo X=1 curl`) survives
        for cmd in ("env X=1 curl " + self._X, "sudo X=1 curl " + self._X):
            rows = self._rows(cmd, "x")
            self.assertEqual(len(rows), 1, cmd)
            self.assertEqual(rows[0]["query_literal"], "ai", cmd)


class RcloneFilterFlagIsNotAGhWrite(unittest.TestCase):
    """S4 gate r11 Finding 2: `_cli_read_ok`'s `-f`/`-F`=field and `-X`=method write-semantics are
    gh-SPECIFIC — rclone's `-f` is `--filter` (a READ). Scoping the gh guard to the declared gh
    prefix (E8: keyed off agent.yaml, never a source name) stops rclone `-f` reads being dropped,
    WITHOUT weakening gh write-detection."""

    def _rows(self, cmd, src):
        block = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": cmd}}
        return [r for r in harvest.recognize(block, None, _RECS, session_id="s", transcript_line=0)
                if r["source"] == src]

    def test_rclone_filter_short_flag_read_still_rows(self):
        rows = self._rows(
            "rclone lsd 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:docs' -f '+ *.pdf'",
            "gdrive-consortium")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["interface"], "rclone-read")

    def test_rclone_filter_long_flag_read_still_rows(self):
        rows = self._rows(
            "rclone lsd 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:docs' --filter '+ *.pdf'",
            "gdrive-consortium")
        self.assertEqual(len(rows), 1)

    def test_rclone_no_flag_read_still_rows(self):
        rows = self._rows("rclone lsd 'gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:docs'",
                          "gdrive-consortium")
        self.assertEqual(len(rows), 1)

    def test_gh_field_write_is_still_a_write(self):
        # the scoping must NOT weaken gh: `gh api -f x=y` still defaults to POST → not a read
        self.assertEqual(self._rows("gh api -f x=y /repos", "github"), [])


if __name__ == "__main__":
    unittest.main()

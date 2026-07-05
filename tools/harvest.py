"""harvest — the transcript harvester, the grounding iteration's spine (S4). Genotype tool.

Design C won the emission seam (docs/grounding/design-emissao.md): the manifest is not EMITTED
by the agent (testimony) nor by a read-gate (chokepoint, cicatriz #248) — it is HARVESTED from
the substrate's own execution record, the Claude transcript store, where the command that ran
is byte-identical and the result is parseable. There is no act of emitting to forget.

Three layers, one seam:

  - `recognize()` — PURE (no I/O): one tool_use block + its resolved result → the manifest
    rows it contains. One tool call with N queries = N rows (E2b occurrence_index). Recognizers
    DERIVE from `sources.load_sources()` interfaces[].via — the same agent.yaml seam the canary
    battery (S5) reads: one seam, two projections.

    INVARIANT (Voz): sources are OPERATOR DATA — this module NEVER knows a source by name. Every
    host, path, query-param, hit-count pattern and lens is DERIVED at runtime from the declared
    agent.yaml interface (via/idiom/canary/hit_count), so a brand-new source the codebase has
    never seen (declare Overleaf in YOUR agent.yaml) is harvested with ZERO code change. The ONLY
    sanctioned literals in the recognizer logic are the harness-INTRINSIC pseudo-source tool names
    (WebSearch/WebFetch — Anthropic's native tools, not operator-declared) and generic protocol
    machinery (curl/http/shlex parsing, HTTP query-param conventions). An MCP tool is recognized
    ONLY when agent.yaml DECLARES it a read-only interface (never a generic `mcp__*` catch-all —
    that resurrected a hardcoded primitive and could fold a mutating/recall tool as grounding). A
    KNOWN_SCRIPTS entry earns a coarse `opaque-script` row (B2) — the CATEGORY, never a hardcoded
    per-source script name (a script is opaque precisely because we cannot know its source).
  - `harvest()` — the incremental walk: cursor per transcript file (sweep's watermark + flock
    idiom, ADR-0008), glob over ALL project dirs + their subagents/ (E7 — a worktree changes
    the project-dir slug, so nothing is derived from HOME/cwd), dedup against already-emitted
    raw_refs RANKED by (recognizer_rev, seq) — a cursor reset / retro-harvest at the SAME rev
    emits 0 new rows, while a HIGHER rev re-emits known occurrences as `supersedes` rows
    (E2b: the interpretation is versioned, never the raw history; the fold projects the best
    rank), dispatch mapping by session anchor + interval
    (E1: a row outside every interval gets dispatch_id null + attribution orphan, NEVER "the
    last open"). Emission: ONE `grounding.manifest` event per row — the shape fold_grounding
    consumes — batched per transcript file through `eventlog.append_batch` (atomic per file,
    still one event per row). Fail-dark per row (counted, printed); raises ONLY on an absent
    store (ADR-0015: a harvest that cannot see the substrate must not look like it ran).
  - `session_floor()` — the pure recognize() run over ONE live session (S6 injects it as
    floor_fn): locator by INDEX across all project dirs (E7), subagents included (a fanned
    explorer's read is the dispatch's read). Never raises — dark is an honest, counted answer.

Attribution ladder on each row (design-emissao §2): `mapped` (subagents/agent-*.meta.json →
toolUseId → the parent Agent tool_use whose prompt declares the intent — mechanical) >
`declared` (the dispatch.open carried theme/intent, enxerto A2) > `opaque-script` (a known
script whose query the transcript cannot see, B2) > `unknown` (honest); `orphan` when the row
maps into NO dispatch interval. `hits: None` is sacred — unknown is never coerced to 0; a
parsed 0 marks the row `dry: suspect` (B1 taxonomy is a FOLD, never written here).

raw_ref (E2b) = (session_id, transcript_line, tool_use_id, occurrence_index) — BRUTE location.
occurrence_index is the occurrence's CHARACTER OFFSET inside the command text: recognizer-table
independent (a positional 0..N-1 would renumber when a new recognizer learns a host — that
would leak interpretation into the brute key and break supersedes' targeting).
"""
import fcntl
import ipaddress
import json
import math
import os
import re
import shlex
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cortex                       # noqa: E402
import eventlog                     # noqa: E402
import sources as sources_mod       # noqa: E402
import _envconf                     # noqa: E402  # EDGE_GROUNDING_FLOOR knob (S6)

# Bumped when a recognizer's INTERPRETATION changes (E2b): retro-mining with a better rev emits
# `supersedes` rows and fold_grounding ranks max (recognizer_rev, seq) — the raw history is
# never rewritten, the interpretation is versioned.
RECOGNIZER_REV = 1

STORE_ROOT = Path.home() / ".claude" / "projects"
CURSORS = REPO / "state" / "harvest-cursors.json"

# Opaque-script recognition (B2) is a CATEGORY, not a source registry: a script is opaque
# precisely because the transcript cannot see its query, so we CANNOT know its source by its
# name. No per-source script name is ever hardcoded here (Voz invariant — sources are operator
# data); the table is empty by default and only an operator-supplied recognizers["scripts"]
# populates it. The house rule (scaffold S8) is that such scripts LOG the query to stdout, at
# which point the logged URL is recognized generically like any other read.
KNOWN_SCRIPTS = {}

# a URL word: plain URL bytes, PLUS `\`-escaped chars inside an unquoted word (R4-4:
# `…?max_results=10\&query=ai` delivers `&query=ai` to curl — the escaped `&` is part of the
# word, so the extraction must see it; `\` before a NEWLINE is a continuation, not swallowed,
# because `.` does not match newline)
# The scheme is CASE-INSENSITIVE (S4 gate r12 B-3): curl fetches `HTTPS://…`/`Https://…` (schemes
# are case-insensitive), so the extractor must see them too — else the URL vanishes from BOTH the
# manifest row and the blind tally (INVARIANT B). Aligns with `_curl_scan`'s operand detector,
# which already lowercases (`t[:8].lower()`). Only the scheme is folded; the rest stays exact.
_URL_RE = re.compile(r"(?i:https?)://(?:\\.|[^\s\"'`\\<>])+")
# via URLs are OPERATOR DATA, not shell (R5-2 structural split): the URL in an interfaces[].via
# is simply the whitespace-delimited token, parens and all (`…/search(foo)?q=...` is legal) —
# the escape/quote-aware word grammar above belongs to the SHELL scanner only. In the shell
# grammar `)` is allowed IN the word: an UNQUOTED `)` is an invocation separator, so the R3-3
# span-trim cuts it; a QUOTED one (the paren-via call) survives.
_VIA_URL_RE = re.compile(r"https?://\S+")
# generic HTTP query-param name conventions — first present wins, but a declared canary's params
# always take precedence (see _query_param_of); never a per-source special-case
_QUERY_PARAM_NAMES = ("query", "search_query", "q")
# the REAL spill pointer format (verified against the store 2026-07-02):
# "<persisted-output>\nOutput too large (43.6KB). Full output saved to: <path>\n\nPreview..."
_POINTER_RE = re.compile(r"Full output saved to:\s*(\S+)")
_MAX_SPILL_BYTES = 4_000_000   # a spilled result is bounded; never slurp an unbounded file
# where a CLI invocation starts inside a compound command: line start, or after ; & | ( ` \n
_CLI_BOUNDARY = r"(?:^|[;&|(`]\s*|\n\s*)"
# the shell separators that BOUND one invocation inside a compound Bash command (gate 8)
_INVOCATION_SEPS = set(";&|`\n()")
# the chars a bash comment `#` may follow to START a word (and thus a comment): whitespace, a
# shell separator, or start-of-string. A `#` glued INSIDE a word (`http://h/p#frag`, `foo#bar`)
# or inside quotes is NOT a comment (S4 gate r9 finding 1).
_COMMENT_PRECEDERS = set(" \t\n\r\f\v") | _INVOCATION_SEPS


def _sep_positions(cmd):
    """QUOTE-AWARE positions of the shell separators that bound invocations in a compound
    command (gates 8 + R2-3 + R3-4): an `&` inside a quoted URL's query string, or a `;` inside
    a quoted -d body, bounds NOTHING — only an unquoted separator splits; a backslash-escaped
    char (including the `\\`-continued newline — a curl's -d body often sits on the continued
    line) never separates; and an `&` that is part of a REDIRECTION operator (`>&`, `<&`, `&>`,
    `&>>` — so `2>&1` too) is I/O plumbing INSIDE the invocation, never a command boundary
    (R3-4 BLOCKING: splitting at `2>&1` hides the flags after it — `… 2>&1 -X POST` would read
    as GET and a WRITE-shaped call would emit a row). One linear scan tracking '…'/"…" state.

    A word-start unquoted `#` opens a bash comment (S4 gate r9 finding 1): it BOUNDS the preceding
    invocation (recorded like a separator, so the span truncates there — every span consumer stops
    before the comment bytes) and the scan skips to end-of-line, so a `;`/`&&` RIDING in the
    comment never splits a phantom invocation. Matches that START inside a comment are dropped by
    the caller via `_comment_regions` — a boundary alone would turn a `# curl …` tail into a
    phantom span."""
    seps, in_s, in_d, i, esc = [], False, False, 0, -1
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and not in_s:   # escape (single quotes are literal — no escapes inside)
            esc = i + 1              # the byte the `\` consumes is part of the WORD, not word-start
            i += 2
            continue
        if in_s:
            in_s = c != "'"
        elif in_d:
            in_d = c != '"'
        elif c == "'":
            in_s = True
        elif c == '"':
            in_d = True
        elif c == "#" and (i == 0 or (cmd[i - 1] in _COMMENT_PRECEDERS and i - 1 != esc)):
            seps.append(i)               # comment start bounds the invocation before it
            nl = cmd.find("\n", i)
            if nl < 0:
                break                    # comment runs to end-of-string
            i = nl                       # resume at the newline (recorded as its own separator)
            continue
        elif c in _INVOCATION_SEPS:
            if c == "&" and ((i > 0 and cmd[i - 1] in "><")
                             or (i + 1 < len(cmd) and cmd[i + 1] == ">")):
                pass   # redirection operator (`>&` `<&` `&>` `&>>`) — not a boundary (R3-4)
            else:
                seps.append(i)
        i += 1
    return seps


def _comment_regions(cmd):
    """QUOTE-AWARE [start, end) spans of the bash comments in a compound command (S4 gate r9
    finding 1): a word-start unquoted `#` opens a comment that runs to the next `\\n` (exclusive)
    or end-of-string. Mirrors `_sep_positions`' quote/escape tracking so the two agree on which
    `#` is a comment. Callers drop any match whose START offset lands in a comment — the shell
    never tokenizes those bytes, so a URL or `curl` word riding in a comment was never fetched."""
    regions, in_s, in_d, i, esc = [], False, False, 0, -1
    while i < len(cmd):
        c = cmd[i]
        if c == "\\" and not in_s:
            esc = i + 1              # the byte the `\` consumes is part of the WORD, not word-start
            i += 2
            continue
        if in_s:
            in_s = c != "'"
        elif in_d:
            in_d = c != '"'
        elif c == "'":
            in_s = True
        elif c == '"':
            in_d = True
        elif c == "#" and (i == 0 or (cmd[i - 1] in _COMMENT_PRECEDERS and i - 1 != esc)):
            nl = cmd.find("\n", i)
            end = len(cmd) if nl < 0 else nl
            regions.append((i, end))
            i = end
            continue
        i += 1
    return regions


def _in_comment(off, regions):
    """True iff char `off` lies inside one of the comment spans (blocking a phantom match)."""
    return any(s <= off < e for s, e in regions)


def _invocation_span(cmd, off, seps):
    """The [start, end) of the shell invocation containing char `off`, given the command's
    quote-aware separator positions."""
    start = 0
    for j in seps:
        if j < off:
            start = j + 1
        else:
            return start, j
    return start, len(cmd)


def _at_invocation_head(cmd, a, start):
    """True iff a prefix/script match at `start` sits at the HEAD of its invocation (span start
    `a`) — only whitespace or `\\`-newline LINE CONTINUATIONS between them (R4-2: `true && \\
    gh api user` RUNS gh; the continuation is whitespace to the shell, so it is whitespace to
    the head-check too). Anything else there (quoted prose, an argument position) is not a call
    — the ONE head rule for the cli and scripts branches alike."""
    return not cmd[a:start].replace("\\\n", " ").strip()


# --- recognizer table: derived from the S3 seam --------------------------------------------------

def _lens_of(source):
    """The lens a source's prose DECLARES — mechanical, never guessed: exactly one of
    Mundo/Atividade named in the description maps; a source naming both (exa, github — the
    lens is chosen per query) or neither derives `unknown` (honest, countable)."""
    desc = source.get("description")
    names = set(re.findall(r"\b(Mundo|Atividade)\b", desc)) if isinstance(desc, str) else set()
    return names.pop().lower() if len(names) == 1 else "unknown"


def _query_param_of(urlparts, iface):
    """The query-carrying URL param for a GET interface: first preferred name present in the
    via's own query string, else in the declared canary params (arxiv's via URL is bare but its
    canary names search_query) — declared data only, never supposed."""
    names = {p.split("=", 1)[0] for p in urlparts.query.split("&") if p}
    canary = iface.get("canary")
    if isinstance(canary, dict):
        params = canary.get("params")
        if isinstance(params, dict):
            names |= set(params)
        if canary.get("query"):
            names.add("query")
    for cand in _QUERY_PARAM_NAMES:
        if cand in names:
            return cand
    return None


def _cli_spec(via):
    """(prefixes, require_remote) from a cli-shaped via. Two declared forms:
    'gh api / gh search / ... — read-only' (alternatives joined by ' / ') and
    'rclone ls/lsd/copy FROM <remote>' (subcommands slashed into one token). Only the
    DECLARED prefixes recognize — `gh repo list` is not in the via, so it never matches.
    require_remote is the FULL declared remote literal (Codex S4 gate D6 — e.g.
    `gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:`, never just the remote NAME `gdrive`): the same
    rclone remote name reaches OTHER drives (a personal folder, another team_drive), and a
    read of those must not fold into THIS source (source-boundary/lens contamination)."""
    head = via.split("—")[0].strip()
    prefixes = []
    if " / " in head:
        prefixes = [alt.strip() for alt in head.split(" / ") if alt.strip()]
    else:
        toks = head.split()
        if len(toks) >= 2 and "/" in toks[1] and not toks[1].startswith("-"):
            prefixes = [f"{toks[0]} {sub}" for sub in toks[1].split("/") if sub]
        elif toks:
            prefixes = [toks[0]]
    m = re.search(r"FROM\s+'([^']+)'", via)
    return prefixes, (m.group(1) if m else None)


def build_recognizers(sources=None):
    """The recognizer table — one seam, two projections (design-emissao §2): DERIVED from
    `sources.load_sources()` interfaces[].via (S3/E3 — acts never enter: load_sources already
    drops them), plus the built-in pseudo-sources for the native tools. An interface declared
    without its key (installed: false) still derives a recognizer — recognition is observation
    of what RAN, never permission. Returns {"rev", "url": [...], "cli": [...], "tools": {...},
    "scripts": {...}}."""
    if sources is None:
        sources, _ = sources_mod.load_sources()
    url_recs, cli_recs = [], []
    tools = {
        "WebSearch": {"source": "websearch-native", "interface": "native", "lens": "mundo",
                      "idiom": None, "dry_semantics": None},
        "WebFetch": {"source": "webfetch-native", "interface": "native", "lens": "mundo",
                     "idiom": None, "dry_semantics": None},
    }
    for s in sources or []:
        lens = _lens_of(s)
        for iface in s.get("interfaces", []) or []:
            via = iface.get("via") or ""
            base = {"source": s.get("name"), "interface": iface.get("interface_id"),
                    "lens": lens, "idiom": iface.get("idiom"),
                    "dry_semantics": iface.get("dry_semantics")}
            head = via.split("—")[0].strip()
            first = head.split()[0] if head.split() else ""
            # R5-2: the via is OPERATOR DATA, not shell — its URL is the whole whitespace-
            # delimited token (parens and all), never the shell scanner's word grammar
            m = _VIA_URL_RE.search(via)
            if m:
                parts = urlsplit(m.group(0))
                # the DECLARED method is the bare word token IMMEDIATELY preceding the URL in the
                # via ("GET https://…" / "HEAD https://…" / "post https://…"); absent → GET
                # (R2-3: the recognizer is method-aware, so a write-shaped curl against a GET
                # interface never folds as that read).
                # S4 gate r8 (manager's note, Finding C): SYMMETRIC verbatim capture, mirroring the
                # observed side (_curl_scan captures the -X value verbatim then .upper()s). The old
                # fixed whitelist (GET|POST|PUT|PATCH|DELETE) silently omitted HEAD — a declared
                # `HEAD …` via stored GET, so a plain `curl <url>` (GET) falsely matched it and
                # `curl -I` (HEAD) was tallied. Taking the preceding word verbatim + .upper()
                # captures HEAD, OPTIONS and any custom method, symmetric with the observed side
                # (a custom method survives folding and dies at the key). Non-method-shaped or
                # absent → GET.
                before = via[:m.start()].split()
                tok = before[-1] if before else ""
                method = tok.upper() if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", tok) else "GET"
                url_recs.append({**base, "host": parts.netloc, "path": parts.path,
                                 "method": method,
                                 "query_param": _query_param_of(parts, iface),
                                 # a POST interface carries its query in the -d body (exa)
                                 "body_field": "query" if method == "POST" else None,
                                 # the DECLARED response hit-count regex (agent.yaml, one capture
                                 # group) — the count lives in operator data, never a hardcoded host
                                 "hit_count": iface.get("hit_count")})
            elif first.startswith("mcp__"):
                # a DECLARED read-only MCP interface (E3): recognized ONLY because agent.yaml
                # NAMES this tool — keyed by the MCP tool name, so an UNdeclared mcp__* call is
                # never guessed into a row (no generic catch-all primitive).
                tools[first] = dict(base)
            else:
                prefixes, remote = _cli_spec(via)
                if prefixes:
                    cli_recs.append({**base, "prefixes": prefixes, "require_remote": remote})
    return {"rev": RECOGNIZER_REV, "url": url_recs, "cli": cli_recs, "tools": tools,
            "scripts": dict(KNOWN_SCRIPTS)}


# --- pure recognition ----------------------------------------------------------------------------

def _match_url(url_recs, url, method):
    """The recognizer claiming a URL: host equality + longest declared path prefix (so
    /contents and /search on one host stay DISTINCT interfaces, R2.2d) + the call's EFFECTIVE
    METHOD equal to the declared one — the method is part of the MATCH KEY, never a post-hoc
    check scattered across sites (R4 structural: post-hoc checking kept breeding siblings). A
    dual declaration (GET and POST interfaces on the same host/path, R4-3) resolves naturally
    to the right interface; an unknown/None effective method (untokenizable invocation,
    dangling `-X`) matches NOTHING — fail-closed, the caller's blind tally picks it up. Scheme
    is NOT part of identity — the arxiv http:// call is the same interface violating its
    https_only idiom."""
    if method is None:
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    best = None
    for r in url_recs:
        if (parts.netloc == r["host"] and parts.path.startswith(r["path"])
                and r.get("method", "GET") == method):
            if best is None or len(r["path"]) > len(best["path"]):
                best = r
    return best


def _idiom_check(rec, query_literal, url=None):
    """The MECHANICAL idiom conformity of one occurrence vs the interface's DECLARED idiom
    (B1 second factor). Only mechanically checkable keys attest: `max_terms` (term count on a
    DECODED working copy — the stored literal stays raw) and `https_only` (scheme of the URL
    as typed). Prose-only idioms (style) attest NOTHING → None, which the fold treats as
    not-attested, never as a violation (S1 anti-coercion)."""
    idiom = rec.get("idiom")
    if not isinstance(idiom, dict):
        return None
    checks = []
    mt = idiom.get("max_terms")
    if isinstance(mt, int) and not isinstance(mt, bool) and isinstance(query_literal, str):
        checks.append(len(unquote_plus(query_literal).split()) <= mt)
    if idiom.get("https_only") and isinstance(url, str):
        # scheme is case-insensitive (S4 gate r12 B-3 sibling): `HTTPS://…` still satisfies
        # https_only — fold the scheme before the prefix test, matching _URL_RE / _curl_scan
        checks.append(url.lower().startswith("https://"))
    return all(checks) if checks else None


def _text_of(result):
    """The parseable TEXT of a resolved result: a str is itself; a dict's stdout when str
    (the Bash toolUseResult shape); anything else has no text (None — unknown, never '')."""
    if isinstance(result, str):
        return result
    if isinstance(result, dict) and isinstance(result.get("stdout"), str):
        return result["stdout"]
    return None


def _hit_pattern(rec):
    """The compiled hit-count regex an interface DECLARED (agent.yaml `hit_count`), or None. The
    pattern is operator DATA and can be malformed (gates 11 + R2-4) — never trusted: an
    unparseable regex, or one without EXACTLY ONE capture group (zero groups capture the whole
    match, two are ambiguous — findall would return tuples and poison int()), degrades to None
    (fail-dark), so a bad declaration blinds the count, never crashes the harvest."""
    hc = rec.get("hit_count")
    if not isinstance(hc, str):
        return None
    try:
        pattern = re.compile(hc)
    except re.error:
        return None
    return pattern if pattern.groups == 1 else None


def _hit_int(v):
    """One captured hit-count value → non-negative int, or None (gate R2-4): the capture is
    operator-declared regex output — a non-numeric capture must fold as unknown, never int()-crash
    a row into the dark counter."""
    return int(v) if isinstance(v, str) and v.isdigit() else None


def _bash_hits(rec, n_same_rec, idx_same_rec, result_text):
    """Hit count of ONE url-occurrence from a SHARED bash stdout — conservative (None≠0
    sacred): the interface's DECLARED pattern (agent.yaml hit_count) must match UNAMBIGUOUSLY.
    N occurrences of the same interface with exactly N pattern matches zip in order (sequential
    curls print sequentially — the real multi-curl case); a single occurrence takes the first
    match; anything else — including a malformed declared pattern or a non-numeric capture
    (R2-4) — is unknown, never guessed."""
    pattern = _hit_pattern(rec)
    if pattern is None or result_text is None:
        return None
    matches = pattern.findall(result_text)
    if len(matches) == n_same_rec:
        return _hit_int(matches[idx_same_rec])
    if n_same_rec == 1 and matches:
        return _hit_int(matches[0])
    return None


def _websearch_hits(result):
    """WebSearch hit count from the REAL toolUseResult shape ({query, results, durationSeconds},
    results = mixed list of {content: [{title, url}...]} dicts and prose strings — verified in
    the store): an EMPTY results list is a clean 0; link dicts count; a non-empty list with no
    parseable links is UNKNOWN (a prose answer is not a measured drought — None≠0)."""
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        return None
    results = result["results"]
    if not results:
        return 0
    links = 0
    for r in results:
        if isinstance(r, dict) and isinstance(r.get("content"), list):
            links += sum(1 for i in r["content"] if isinstance(i, dict) and "url" in i)
    return links if links > 0 else None


_DATA_FLAGS = ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--data-urlencode")
_CURL_DATA_LONG = ("--data", "--data-raw", "--data-binary", "--data-ascii", "--data-urlencode")
# THE ONE PLACE curl flags map to an implied method (R5-1, manager's note): a flag that changes
# the method without -X lands HERE — pinned by an ENUMERATION test, so a future flag fails the
# test loudly instead of silently defaulting to GET. Values must be the UPPERCASE method.
_CURL_FLAG_METHODS = {
    "-I": "HEAD", "--head": "HEAD",
    "-F": "POST", "--form": "POST", "--form-string": "POST", "--json": "POST",
    "-T": "PUT", "--upload-file": "PUT",
}
# short flags that CONSUME a value (glued or next token): the bundle scan must STOP at them —
# scanning past would misread the VALUE's chars as flags (`-x -XGET` is a proxy value, not -X;
# `-HX-Api-Key: v` is a header, not -X). S4 gate r7 (manager's SIBLING SWEEP): audited against
# `man curl` 8.5 — EVERY value-consuming short is here so no missing flag reopens the class. The
# five with dedicated branches are EXCLUDED (handled before this set): `X` (--request → method),
# `K` (--config → None, R6-3), `d` (--data → POST), `F`/`T` (--form/--upload-file → implied). `h`
# (--help, OPTIONAL arg) is EXCLUDED so a bare `-h` never swallows the next flag (help issues no
# request anyway). Boolean shorts (`-O` --remote-name, `-I`, `-G`, `-s`, …) are NOT here.
# Pinned by an enumeration test.
_CURL_ARG_SHORTS = set("ACDEHPQUYbcemortuwxyz")
# long flags that CONSUME a value, spaced or =-joined (R6-2, manager's note — the mirror of
# _CURL_ARG_SHORTS): the walk SKIPS the value token of EVERY arg-consuming flag, so a
# dash-leading value (`--json -XGET URL` — the BODY is `-XGET`; `--request-target -XGET URL` —
# the wire target — `--connect-to/--proxy-header/--url-query …`) is never parsed as flags. With
# the S4 gate r8 structural change these tables ALSO gate operand extraction (which token is the
# URL), so completeness protects the method AND the operand gate.
# Hand-audited against curl 8.5.0 `curl --help all` on this box (S4 gate r8): every option whose
# synopsis shows an arg placeholder (`<…>` or `[…]`), minus `--help` (its `<category>` is OPTIONAL
# so a bare `--help` must not swallow the next token). `--request`/`--config` have dedicated
# branches above but stay here for parity; `--get`/`--head`/booleans have no placeholder and are
# absent. (`--expand-*`/arg-consuming `--haproxy-clientip` from newer curl do NOT exist on 8.5.0 —
# `--haproxy-clientip` is boolean here; folding a boolean in would wrongly skip the next token.)
# The literal enumeration test is a CHANGE-DETECTOR (a DROP or version drift fails LOUD there); the
# regeneration test (skipped off curl 8.5.x) is what catches an ORIGINAL omission on this box.
_CURL_ARG_LONGS = frozenset((
    "--abstract-unix-socket", "--alt-svc", "--aws-sigv4", "--cacert", "--capath", "--cert",
    "--cert-type", "--ciphers", "--config", "--connect-timeout", "--connect-to",
    "--continue-at", "--cookie", "--cookie-jar", "--create-file-mode", "--crlfile", "--curves",
    "--data", "--data-ascii", "--data-binary", "--data-raw", "--data-urlencode",
    "--delegation", "--dns-interface", "--dns-ipv4-addr", "--dns-ipv6-addr", "--dns-servers",
    "--doh-url", "--dump-header", "--egd-file", "--engine", "--etag-compare", "--etag-save",
    "--expect100-timeout", "--form", "--form-string", "--ftp-account",
    "--ftp-alternative-to-user", "--ftp-method", "--ftp-port", "--ftp-ssl-ccc-mode",
    "--happy-eyeballs-timeout-ms", "--header", "--hostpubmd5", "--hostpubsha256", "--hsts",
    "--interface", "--ipfs-gateway", "--json", "--keepalive-time", "--key", "--key-type",
    "--krb", "--libcurl", "--limit-rate", "--local-port", "--login-options", "--mail-auth",
    "--mail-from", "--mail-rcpt", "--max-filesize", "--max-redirs", "--max-time",
    "--netrc-file", "--noproxy", "--oauth2-bearer", "--output", "--output-dir",
    "--parallel-max", "--pass", "--pinnedpubkey", "--preproxy", "--proto", "--proto-default",
    "--proto-redir", "--proxy", "--proxy-cacert", "--proxy-capath", "--proxy-cert",
    "--proxy-cert-type", "--proxy-ciphers", "--proxy-crlfile", "--proxy-header", "--proxy-key",
    "--proxy-key-type", "--proxy-pass", "--proxy-pinnedpubkey", "--proxy-service-name",
    "--proxy-tls13-ciphers", "--proxy-tlsauthtype", "--proxy-tlspassword", "--proxy-tlsuser",
    "--proxy-user", "--proxy1.0", "--pubkey", "--quote", "--random-file", "--range", "--rate",
    "--referer",
    "--request", "--request-target", "--resolve", "--retry", "--retry-delay",
    "--retry-max-time", "--sasl-authzid", "--service-name", "--socks4", "--socks4a",
    "--socks5", "--socks5-gssapi-service", "--socks5-hostname", "--speed-limit",
    "--speed-time", "--stderr", "--telnet-option", "--tftp-blksize", "--time-cond",
    "--tls-max", "--tls13-ciphers", "--tlsauthtype", "--tlspassword", "--tlsuser", "--trace",
    "--trace-ascii", "--trace-config", "--unix-socket", "--upload-file", "--url",
    "--url-query", "--user", "--user-agent", "--variable", "--write-out",
))


# the generic HTTP clients whose FIRST token gates a URL into the manifest (S4 gate r8): a URL
# only counts as a read when its enclosing invocation's command word is one of these. This is
# CLIENT knowledge — subject-blind, the protocol machinery, NOT source knowledge (Voz/E8: a
# source is operator data named in agent.yaml, never here) — so `echo "https://…"` /
# `git commit -m "…https://…"` no longer phantom-emit, with ZERO source-specific code.
_HTTP_CLIENTS = frozenset(("curl", "wget", "http", "https", "xh", "curlie"))


# generic exec-wrapper prefixes that LAUNCH another command (S4 gate r11 Finding 1): a wrapper
# pushes the real client out of first position (`timeout 30 curl …`, `sudo curl …`,
# `env KEY=v curl …`), so the command word must be read THROUGH them. Like _HTTP_CLIENTS this is
# subject-blind shell machinery — coreutils launchers (env/nice/nohup/stdbuf/timeout), util-linux
# schedulers (ionice/setsid/chrt/taskset), privilege launchers (sudo/doas) and the `time` keyword —
# every one takes the "[options] COMMAND [args]" shape. E8-safe: NOT source knowledge (no source is
# named here), same category as _HTTP_CLIENTS. Peeling only moves command_word; the method + operand
# walk already handles wrappers correctly (their tokens are bare non-URL non-flag → never operands).
# `command`/`exec` (S4 gate r12 B-2) are the shell builtins that LAUNCH a command with the same
# `[options] COMMAND [args]` shape — `command curl …` / `exec curl …` peel to the real client.
# `exec -a NAME curl` also resolves: `-a` is a non-glued flag whose bare VALUE (NAME) is skipped by
# the generic flag-value rule in _command_word, landing on curl.
_EXEC_WRAPPERS = frozenset(("timeout", "sudo", "env", "nice", "nohup", "stdbuf", "ionice",
                            "time", "doas", "setsid", "chrt", "taskset", "command", "exec"))
# wrappers that take a bare POSITIONAL numeric/duration arg BEFORE the command (timeout DURATION,
# nice adjustment, ionice/chrt priority, taskset mask) — skipped so it is not mistaken for the
# command word. Everything else in the wrapper region is a flag or an env-assignment.
_WRAPPER_NUMARG = frozenset(("timeout", "nice", "ionice", "chrt", "taskset"))
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")           # NAME=VALUE env-assignment prefix
_NUM_DURATION = re.compile(r"^(?:0x[0-9A-Fa-f]+|[0-9][0-9.,\-]*[smhd]?)$")  # 30 / 30s / 0x3 / 0-3


def _basename(word):
    """The trailing path component of a command word (S4 gate r12 B-1): `/usr/bin/curl`→`curl`,
    `./curl`→`curl`, `curl`→`curl`. Pure shell/path machinery, subject-blind (E8-safe). Used ONLY
    for client/wrapper membership tests — raw tokens, offsets and operands are untouched. The match
    stays EXACT on the basename, so `mycurl`/`curl.sh`/`notcurl` remain non-clients."""
    return word.rsplit("/", 1)[-1]


def _command_word(texts):
    """The EFFECTIVE command word, looking THROUGH leading exec-wrapper prefixes (S4 gate r11
    Finding 1): the first token that is neither a wrapper name nor one of a wrapper's args. In a
    wrapper region we skip flags (`-…`), env-assignments (`NAME=VALUE`), a numeric/duration
    positional for _WRAPPER_NUMARG wrappers, and a non-glued flag's following bare VALUE (so
    `sudo -u www curl` reaches `curl`). Over-skipping can only land on a non-client token → a DROP
    (the same fail-closed outcome as today), never a phantom. `texts[0]` on empty/all-wrapper
    input (fail-closed to today's behaviour).

    The returned word AND every wrapper-membership test are BASENAME-normalized (S4 gate r12 B-1):
    `/usr/bin/curl`→`curl`, `./curl`→`curl`, so a full-path/relative-path client is gated by the
    caller instead of vanishing from BOTH manifest and tally (INVARIANT B), and a full-path wrapper
    (`/usr/bin/sudo`, `/usr/bin/timeout`) peels correctly. Basename is pure path machinery,
    subject-blind (E8-safe). Match stays EXACT on the basename, so `mycurl`/`curl.sh`/`notcurl`
    remain non-clients (no new phantom — INVARIANT A).

    A leading BARE env-assignment run (`DEBUG=1 curl …`, `HTTPS_PROXY=http://p curl …`, and
    `NAME=v NAME2=w cmd …`) sets env for the command WITHOUT the `env` wrapper keyword (S4 gate
    r13): skip ALL such assignments FIRST so the command word is read past them. Skipping (not
    basename-ing) the assignment closes BOTH violations of one root — INVARIANT A: an assignment
    whose VALUE is a path-to-a-client (`X=/usr/bin/curl echo …`) is consumed, not basenamed to
    `curl` → lands on `echo` → NO phantom; INVARIANT B: `DEBUG=1 curl` lands on `curl` → rows/tally
    instead of vanishing. Assignment-only input (`X=1`, `X=1 Y=2`) consumes every token → no
    command ran → the fallback returns a non-client (no row/tally, correct)."""
    i, n = 0, len(texts)
    while i < n and _ENV_ASSIGN.match(texts[i]):   # leading NAME=VALUE env-assignments (bare, no `env`)
        i += 1
    while i < n and _basename(texts[i]) in _EXEC_WRAPPERS:
        wrapper = _basename(texts[i])
        i += 1
        while i < n:
            t = texts[i]
            if t.startswith("-"):
                i += 1
                # a non-glued flag (`-u`, no `=`) may take the next bare token as its value; skip
                # it unless that token is itself a flag / env-assign / another wrapper (which begin
                # a new region, never a flag value). Excess skipping is a DROP, never a phantom.
                if "=" not in t and i < n and not texts[i].startswith("-") \
                        and not _ENV_ASSIGN.match(texts[i]) and _basename(texts[i]) not in _EXEC_WRAPPERS:
                    i += 1
                continue
            if _ENV_ASSIGN.match(t):
                i += 1
                continue
            if wrapper in _WRAPPER_NUMARG and _NUM_DURATION.match(t):
                i += 1
                continue
            break   # first real token — the command, or the next wrapper (outer loop re-checks)
    # i>=n means every token was consumed as an assignment/wrapper/flag → NO command ran; return
    # texts[0] RAW (never basename it — a consumed `X=/usr/bin/curl` must not resolve to `curl`).
    return _basename(texts[i]) if i < n else (texts[0] if texts else None)


def _curl_tokens(invocation):
    """POSIX-shlex-faithful tokenizer returning (dequoted_text, start, end) per token — or None
    when a quote/escape is unbalanced (untokenizable → fail closed). `start`/`end` are raw char
    offsets in `invocation` (end is just past the token's last raw char, quotes included).
    shlex.split gives no offsets, and the S4 gate r8 operand gate must connect a dequoted URL
    value back to its char position (the E2b occurrence offset), so this ONE scanner carries both
    the text (for the method walk) and the span (for the operand gate). Validated to agree with
    shlex.split on the whole curl test battery."""
    toks, i, n = [], 0, len(invocation)
    text, start = None, 0            # text is None between tokens
    while i < n:
        c = invocation[i]
        if c in " \t\n\r\f\v":
            if text is not None:
                toks.append((text, start, i))
                text = None
            i += 1
            continue
        if text is None:
            text, start = "", i
        if c == "\\":                # outside quotes: backslash escapes the next char verbatim
            if i + 1 >= n:
                return None          # trailing backslash — shlex raises; fail closed
            if invocation[i + 1] == "\n":
                i += 2               # line continuation — removed
                continue
            text += invocation[i + 1]
            i += 2
        elif c == "'":               # single quotes: literal until the next ' (no escapes)
            j = invocation.find("'", i + 1)
            if j < 0:
                return None
            text += invocation[i + 1:j]
            i = j + 1
        elif c == '"':               # double quotes: backslash escapes only " and \ (shlex posix)
            i += 1
            while i < n and invocation[i] != '"':
                if invocation[i] == "\\" and i + 1 < n and invocation[i + 1] in '"\\':
                    text += invocation[i + 1]
                    i += 2
                else:
                    text += invocation[i]
                    i += 1
            if i >= n:
                return None          # unbalanced double quote
            i += 1
        else:
            text += c
            i += 1
    if text is not None:
        toks.append((text, start, i))
    return toks


def _curl_scan(invocation):
    """ONE positional walk over one HTTP-client invocation — one seam, TWO projections (S4 gate
    r8, mirrors build_recognizers' one-seam-two-projections idiom): returns
    (command_word, effective_method, operand_spans).

      - command_word: the first REAL command token — leading exec-wrapper prefixes (`timeout`/
        `sudo`/`env`/… — _EXEC_WRAPPERS, S4 gate r11) are peeled first (the caller gates it against
        _HTTP_CLIENTS). Only command_word looks through wrappers; the method + operand walk below
        already handles them (wrapper tokens are bare non-URL non-flag → never operands).
      - effective_method (R2-3 + R4-1 + R5-1 + R6): explicit `-X`/`--request` wins, value CAPTURED
        byte-verbatim (spaced/glued/=-joined, R6-1) then CASE-FOLDED (`.upper()`) for the match key
        (S4 gate r7): a custom method survives folding and dies at the key, a standard method
        matches its declared interface regardless of spelling; else an IMPLYING flag
        (_CURL_FLAG_METHODS); else `-G/--get` forces GET; else a data flag implies POST; else GET.
        None on anything UNKNOWABLE — untokenizable, a DANGLING `-X`/`--request` (R4-1),
        CONFLICTING implied (`-I -T …`), or `-K/--config` (R6-3, external config).
      - operand_spans: the (start, end) of each POSITIONAL URL operand (a bare non-flag token
        that is a URL) PLUS any `--url`/`--url=` value. The SAME arg-consuming tables
        (_CURL_ARG_SHORTS/_CURL_ARG_LONGS) that skip a flag's value for the method ALSO keep that
        token out of the operands — one walk, so the two can never drift (a `-H`/`-e`/`--referer`
        value URL is skipped for BOTH, killing the `-H "Referer: https://…"` phantom).

    Unknowable no longer short-circuits the walk: it sets a flag and the scan continues so the
    URL operand is still located (the blind tally needs it — a config/dangling call whose URL is a
    real operand must still be tallied), while the method resolves to None at the end."""
    toks = _curl_tokens(invocation)
    if toks is None:
        return None, None, []
    texts = [t for t, _, _ in toks]
    command = _command_word(texts)   # S4 gate r11: read THROUGH leading exec-wrapper prefixes
    method, implied, has_data, force_get, unknowable = None, set(), False, False, False
    operands = []
    i = 0
    while i < len(texts):
        t = texts[i]
        if t.startswith("--"):
            base, eq, val = t.partition("=")
            if base == "--config":
                unknowable = True     # R6-3: config sets method/data outside our sight
                if not eq and i + 1 < len(texts):
                    i += 1            # skip the config-file token
            elif base == "--url":
                if eq:
                    operands.append((toks[i][1], toks[i][2]))   # --url=<val>: this token IS the URL
                elif i + 1 < len(texts):
                    i += 1
                    operands.append((toks[i][1], toks[i][2]))   # --url <val>: the next token is the URL
                # dangling --url: no value to record
            elif base == "--request":
                if eq:
                    method = val      # byte-verbatim, possibly "" — folded at the key
                elif i + 1 < len(texts):
                    i += 1
                    method = texts[i]
                else:
                    unknowable = True  # R4-1: dangling --request
            elif base == "--get":
                force_get = True
            else:
                if base in _CURL_DATA_LONG:
                    has_data = True
                if base in _CURL_FLAG_METHODS:
                    implied.add(_CURL_FLAG_METHODS[base])
                if base in _CURL_ARG_LONGS and not eq and i + 1 < len(texts):
                    i += 1            # R6-2: its value is the NEXT token — never flags/operand
        elif t.startswith("-") and len(t) > 1:
            # a short-flag token, possibly BUNDLED (-sIL) or glued to a value (R6-1)
            chars, j = t[1:], 0
            while j < len(chars):
                ch = chars[j]
                if ch == "X":
                    rest = chars[j + 1:]
                    if rest:
                        method = rest  # byte-verbatim — folded at the key
                    elif i + 1 < len(texts):
                        i += 1
                        method = texts[i]
                    else:
                        unknowable = True  # R4-1: dangling -X
                    break
                if ch == "K":
                    unknowable = True      # R6-3: -K <config> — method unknowable
                    if j == len(chars) - 1 and i + 1 < len(texts):
                        i += 1             # skip the spaced config-file token
                    break                  # glued -Kcfg: the rest is the config path
                if ch == "d":
                    has_data = True
                    if j == len(chars) - 1 and i + 1 < len(texts):
                        i += 1             # -d VALUE — skip the data token
                    break
                if ch in ("F", "T"):
                    implied.add(_CURL_FLAG_METHODS["-" + ch])
                    if j == len(chars) - 1 and i + 1 < len(texts):
                        i += 1
                    break
                if ch in _CURL_ARG_SHORTS:
                    if j == len(chars) - 1 and i + 1 < len(texts):
                        i += 1             # its value is the next token — never flags/operand
                    break
                if ch == "I":
                    implied.add("HEAD")
                elif ch == "G":
                    force_get = True
                j += 1
        else:
            # a POSITIONAL token — a URL operand of the client (the fetched URL), never a flag
            low = t[:8].lower()
            if low.startswith("http://") or low.startswith("https://"):
                operands.append((toks[i][1], toks[i][2]))
        i += 1
    if unknowable:
        method_result = None          # fail-closed: matches no recognizer, blind tally picks it up
    elif method is not None:
        method_result = method.upper()  # S4 gate r7: symmetric case-fold with the declared side
    elif len(implied) > 1:
        method_result = None          # conflicting implied — ambiguous, fail closed (R5-1)
    elif implied:
        method_result = next(iter(implied))
    elif force_get:
        method_result = "GET"
    else:
        method_result = "POST" if has_data else "GET"
    return command, method_result, operands


def _curl_method(invocation):
    """The EFFECTIVE HTTP method projection of _curl_scan (kept as the named seam the recognizer
    match key and the blind tally read); None on anything unknowable — fail closed."""
    return _curl_scan(invocation)[1]


def _post_body_field(bf, invocation):
    """The POST body field's byte value from a curl invocation's -d/--data body. The URL is
    associated with the WHOLE curl invocation (Codex S4 gate 8: `curl -d '{"query":"x"}' URL`
    carries the body BEFORE the URL, so a segment that starts at the URL misses it). shlex pulls
    each data body out of the invocation; a raw-regex fallback covers unparseable quoting. None
    when the field is absent."""
    pat = re.compile(r'"' + re.escape(bf) + r'"\s*:\s*"((?:[^"\\]|\\.)*)"')
    try:
        toks = shlex.split(invocation)
    except ValueError:
        toks = []
    for i, t in enumerate(toks):
        body = None
        if t in _DATA_FLAGS and i + 1 < len(toks):
            body = toks[i + 1]
        else:
            for fl in _DATA_FLAGS:
                if t.startswith(fl + "="):
                    body = t.split("=", 1)[1]
                    break
        if body is not None:
            m = pat.search(body)
            if m:
                return m.group(1)
    m = pat.search(invocation)   # fallback: quoting shlex could not tokenize
    return m.group(1) if m else None


def _extract_query(rec, url, invocation):
    """The byte-identical query_literal of one url-occurrence — EXTRACTED, never re-typed:
    a GET interface's declared param is cut RAW from the URL as typed (percent-encoding kept);
    a POST interface's body field is cut from the occurrence's own curl INVOCATION (gate 8: the
    whole curl command, so a -d body typed BEFORE the URL is still found). Unextractable → None,
    still a row."""
    qp = rec.get("query_param")
    if qp:
        m = re.search(r"[?&]" + re.escape(qp) + r"=([^&\s\"']*)", url)
        if m:
            return m.group(1)
    bf = rec.get("body_field")
    if bf:
        return _post_body_field(bf, invocation)
    return None


# gh flags that CONSUME a spaced value (R6-2 sibling — the mirror of _CURL_ARG_LONGS for the
# gh guard): the walk skips their value token so a dash-leading value (`-H "-X"`) can never
# masquerade as a method/field flag and launder a write into the GET allow-list. S4 gate r7
# (manager's SIBLING SWEEP): audited against `gh help api` 2.88 — the COMPLETE set of
# value-consuming gh-api flags EXCEPT those with dedicated branches above (`-X`/`--method` →
# method; `-f`/`-F`/`--field`/`--raw-field`/`--input` → field). Booleans (`-i`/--include,
# --paginate, --silent, --slurp, --verbose, --help) are absent. Pinned by an enumeration test.
_GH_ARG_FLAGS = ("-H", "--header", "-q", "--jq", "-t", "--template",
                 "--hostname", "--cache", "-p", "--preview")


def _cli_read_ok(invocation, prefix):
    """A CLI invocation counts as a READ only in a provably read-only form (Codex S4 gates 7 +
    R2-2): an explicit mutating HTTP method (`-X POST/PUT/PATCH/DELETE`, `--method …`, glued or
    =-joined) is a WRITE; and absent an explicit method, a field-sending flag — spaced (`-f x=y`,
    `--field x=y`), =-joined (`--field=x=y`, `--raw-field=…`, `--input=…`) or GLUED short form
    (`-fx=y`, `-Fx=y`) — makes `gh api` DEFAULT to POST, also a write. An EXPLICIT method is a
    read ONLY when it is exactly GET (R3-1: `HEAD`, a typo like `GEET`, or any method this guard
    does not know must fail CLOSED — an allow-list of provably-read forms, never a deny-list of
    known writes; the deny-list let `--method HEAD` override field flags). A DANGLING method
    flag (`… --method` / `… -X` as the last token, R4-1) states an intent to set a method whose
    value we cannot see — fail CLOSED, never "no method = read". Arg-consuming flags
    (_GH_ARG_FLAGS + the spaced field flags) have their value token SKIPPED (R6-2 sibling: a
    header value `-X` followed by `GET` must never read as an explicit-GET override).
    shlex-parsed; an untokenizable invocation fails CLOSED.

    S4 gate r11 Finding 2: the `-f`/`-F`=field and `-X`/`--method`=HTTP-method facts above are
    gh-SPECIFIC and must NOT be imposed on other CLIs (rclone's `-f` is `--filter`, a READ; its
    `-t`/`-p` differ from gh's too). The gh write-semantics apply ONLY when the DECLARED prefix's
    tool is `gh` (keyed off the recognizer's agent.yaml prefix, never a source name — E8-safe);
    any other cli read is governed by its own guard (rclone → _remote_read_match) and passes here.
    Untokenizable input still fails CLOSED for every tool."""
    try:
        toks = shlex.split(invocation)
    except ValueError:
        return False
    if (prefix.split()[0] if prefix else None) != "gh":
        return True   # non-gh: gh's -f=field / -X=method write-semantics do not apply; the
        # tool-appropriate guard (e.g. _remote_read_match for rclone) already vetted the read
    method, field = None, False
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ("-X", "--method"):
            if i + 1 >= len(toks):
                return False   # R4-1: dangling method flag — value unseen, fail closed
            i += 1
            method = toks[i]
        elif t.startswith("-X") and len(t) > 2:
            method = t[2:]
        elif t.startswith("--method="):
            method = t.split("=", 1)[1]
        elif (t in ("-f", "-F", "--field", "--raw-field", "--input")
              or t.startswith(("--field=", "--raw-field=", "--input="))
              or (len(t) > 2 and t[0] == "-" and t[1] in "fF")):
            # the last arm is the GLUED short form (-fkey=val / -Fkey=val); a long flag never
            # enters it ("--…"[1] is "-", not f/F)
            field = True
            if t in ("-f", "-F", "--field", "--raw-field", "--input") and i + 1 < len(toks):
                i += 1   # its spaced value is data — never flags (R6-2 sibling)
        elif t in _GH_ARG_FLAGS and i + 1 < len(toks):
            i += 1       # its value is never flags (R6-2 sibling)
        i += 1
    if method is not None:
        return method.upper() == "GET"   # allow-list (R3-1): only explicit GET reads
    return not field


def _base_row(session_id, transcript_line, tuid, occ, rec, ts, rev, **extra):
    """One manifest row in the shape fold_grounding consumes (S1): the E2b brute raw_ref +
    the interpreted payload. geometry/intent/dispatch_id/attribution are FINALIZED by harvest
    (dispatch mapping needs the log); recognize emits the recognizer-level defaults."""
    row = {"raw_ref": [session_id, transcript_line, tuid, occ],
           "source": rec.get("source"), "interface": rec.get("interface"),
           "lens": rec.get("lens") or "unknown", "geometry": "ambient", "intent": None,
           "dispatch_id": None, "attribution": "unknown",
           "query_literal": None, "hits": None, "idiom_conforme": None,
           "dry_semantics": rec.get("dry_semantics"), "tool": None,
           "ts": ts, "recognizer_rev": rev}
    row.update(extra)
    if row["hits"] == 0:
        # born-marked dry: hits==0 already triggers the fold's taxonomy; the marker makes the
        # row self-describing. seca-VERIFICADA is never written here — it is a fold (B1).
        row["dry"] = "suspect"
    return row


def _remote_read_match(invocation, prefix, remote):
    """Codex S4 gate D4+D6 — the FROM-remote read-guard, by the FULL declared literal, never
    substring or bare remote name: a FROM-remote via (rclone read) matches ONLY when the
    SOURCE argument STARTS WITH the complete declared remote spec (e.g.
    `gdrive,team_drive=0ANpsQbmPpJ3WUk9PVA:`) AND the destination, when present (copy), is
    NOT that remote. `rclone copy <local> gdrive,…:` is the upload act; `rclone copy
    gdrive-export/ gdrive,…:dest` is an upload whose LOCAL dir merely names the remote (D4);
    `rclone ls 'gdrive:Personal Folder'` / another team_drive reach a DIFFERENT drive through
    the same remote name and must not fold into THIS source (D6 — source boundary, lens
    contamination); a remote→remote copy writes the remote too. Args are shlex-tokenized (a
    quoted remote path with spaces survives as one arg); an untokenizable invocation fails
    CLOSED — a call we cannot parse must never be classified as a read."""
    try:
        toks = shlex.split(invocation)
    except ValueError:
        return False
    args = [t for t in toks[len(prefix.split()):] if not t.startswith("-")]

    def _is_remote(arg):
        return arg.startswith(remote)
    if not args or not _is_remote(args[0]):
        return False
    return not (len(args) > 1 and _is_remote(args[1]))


def _bash_rows(cmd, tool_result, recognizers, session_id, transcript_line, tuid, ts, rev):
    """All rows inside ONE Bash command: url-occurrences (each URL claimed by a recognizer),
    cli invocations (declared prefixes only), and known-script coarse rows. occurrence_index =
    char offset of the occurrence in the command (brute, recognizer-independent). ONE
    quote-aware invocation-span seam (`_sep_positions`/`_invocation_span`) bounds BOTH the url
    and the cli branches (R3-2 — never two cutters), URLs are TRIMMED to their invocation's end
    (R3-3: in an unquoted URL the shell splits at `&`, so bytes after it never reach curl and
    must never reach query_literal), and a prefix/script match must sit at its invocation's
    HEAD (sibling sweep: `git commit -m "run; gh api user"` must not row on quoted prose;
    a `\\`-newline continuation before the prefix is whitespace to the shell — R4-2)."""
    rows = []
    result_text = _text_of(tool_result)
    # url occurrences, each with its ENCLOSING curl invocation (gate 8: shell separators bound the
    # invocation, so a -d body typed BEFORE the URL is still inside it — not just the tail after)
    seps = _sep_positions(cmd)
    comments = _comment_regions(cmd)
    claimed = []
    for m in _URL_RE.finditer(cmd):
        off = m.start()
        if _in_comment(off, comments):
            continue   # a URL riding in a `#` comment was never fetched (S4 gate r9 finding 1)
        a, b = _invocation_span(cmd, off, seps)
        url = m.group(0)[:max(0, b - off)]   # R3-3: what the SHELL passes, not what regex ate
        if not url:
            continue
        seg = cmd[a:b]
        # S4 gate r8 (two gates, one seam): a URL is a read ONLY when its enclosing invocation
        # is a generic HTTP client AND the URL is a POSITIONAL operand (or a --url value) of it —
        # not prose in an `echo`, not a `-H "Referer: https://…"` header value. Both derive from
        # the SAME _curl_scan walk the method comes from.
        command, method, operands = _curl_scan(seg)
        if command not in _HTTP_CLIENTS:
            continue   # gate 1: the command word is not an HTTP client — echo/git/…, never a read
        if not any(s <= off - a < e for s, e in operands):
            continue   # gate 2: the URL is an arg-consuming flag's value, not the fetched operand
        # R4 structural: the effective method enters the MATCH KEY — a dual GET/POST
        # declaration resolves to the right interface; None (dangling -X) matches nothing
        rec = _match_url(recognizers.get("url", []), url, method)
        if rec is None:
            continue
        claimed.append((off, url, seg, rec))
    per_rec = {}
    for off, url, seg, rec in claimed:
        per_rec.setdefault(id(rec), []).append(off)
    for off, url, seg, rec in claimed:
        same = per_rec[id(rec)]
        q = _extract_query(rec, url, seg)
        rows.append(_base_row(
            session_id, transcript_line, tuid, off, rec, ts, rev,
            tool="Bash", query_literal=q,
            hits=_bash_hits(rec, len(same), same.index(off), result_text),
            idiom_conforme=_idiom_check(rec, q, url=url)))
    # cli invocations — only the DECLARED read prefixes recognize (E3: never an act)
    for rec in recognizers.get("cli", []):
        for prefix in rec.get("prefixes", []):
            for m in re.finditer(_CLI_BOUNDARY + "(" + re.escape(prefix) + r")\b", cmd):
                start = m.start(1)
                a, b = _invocation_span(cmd, start, seps)   # R3-2: the SAME span seam as urls
                if not _at_invocation_head(cmd, a, start):
                    continue   # not at its invocation's head — quoted prose, not a call
                invocation = cmd[start:b].strip()
                remote = rec.get("require_remote")
                if remote and not _remote_read_match(invocation, prefix, remote):
                    continue
                if not _cli_read_ok(invocation, prefix):
                    continue   # gate 7: a mutating method (-X POST/…) / POST-implying field is a WRITE
                    # (gh-only, r11 Finding 2); non-gh reads are governed by their own guard above
                rows.append(_base_row(
                    session_id, transcript_line, tuid, start, rec, ts, rev,
                    tool="Bash", query_literal=invocation,
                    idiom_conforme=_idiom_check(rec, invocation)))
    # known scripts — coarse, opacity declared (B2); same head rule as the cli branch
    for script, spec in (recognizers.get("scripts") or {}).items():
        for m in re.finditer(_CLI_BOUNDARY + "(" + re.escape(script) + r")\b", cmd):
            start = m.start(1)
            a, _b = _invocation_span(cmd, start, seps)
            if not _at_invocation_head(cmd, a, start):
                continue   # quoted/mid-invocation mention of the script name is not a run
            rows.append(_base_row(
                session_id, transcript_line, tuid, start, spec, ts, rev,
                tool="Bash", attribution="opaque-script"))
    rows.sort(key=lambda r: r["raw_ref"][3])
    return rows


def recognize(tool_use, tool_result, recognizers, session_id=None, transcript_line=None,
              ts=None):
    """PURE: one tool_use block + its RESOLVED result (the caller follows spill pointers —
    `result_payload`) → the manifest rows it contains, [] when nothing recognizable. One tool
    call with N queries = N rows (E2b). A malformed block yields [] — fail-dark belongs to the
    caller's counting, never a raise here."""
    if not isinstance(tool_use, dict):
        return []
    tuid = tool_use.get("id")
    name = tool_use.get("name")
    if not (isinstance(tuid, str) and tuid and isinstance(name, str)):
        return []
    inp = tool_use.get("input")
    inp = inp if isinstance(inp, dict) else {}
    rev = recognizers.get("rev", RECOGNIZER_REV)
    if name == "Bash":
        cmd = inp.get("command")
        if not isinstance(cmd, str):
            return []
        return _bash_rows(cmd, tool_result, recognizers, session_id, transcript_line,
                          tuid, ts, rev)
    if name in (recognizers.get("tools") or {}):
        rec = recognizers["tools"][name]
        if name == "WebSearch":
            q = inp.get("query")
            hits = _websearch_hits(tool_result)
        elif name == "WebFetch":   # a fetch is not a search; hits semantics undefined → unknown
            q = inp.get("url")
            hits = None
        else:   # a DECLARED read-only MCP tool — its query is in input.query; hits undefined
            q = inp.get("query")
            hits = None
        return [_base_row(session_id, transcript_line, tuid, 0, rec, ts, rev, tool=name,
                          query_literal=q if isinstance(q, str) else None, hits=hits)]
    return []


def _is_local_host(hostname):
    """EXACT local-host classification (R5-3 — the substring check silenced external calls:
    `notlocalhost.example.com`, `api.localhost.evil`, `0.0.0.0.evil.example` all CONTAIN a local
    marker but are network-shaped and must reach the blind tally, B2). Local = the exact name
    `localhost`, an RFC 6761 `*.localhost` suffix, or an IP literal that is loopback/unspecified
    (127.0.0.0/8, ::1, 0.0.0.0, ::) — classified by ipaddress, never by string containment. A
    non-IP, non-localhost name is EXTERNAL (fail toward the tally: visible, never silenced)."""
    if not hostname:
        return False
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def unrecognized_urls(tool_use, recognizers):
    """Enxerto B2, the blindness tally: (offset, host) of every network-shaped URL in a Bash
    command that yields NO manifest row — counted and visible (the panel's blind leg), never a
    guessed row. Local hosts (EXACT hostname match / IP class — R5-3, never substring) are not
    network-shaped. Sibling sweep of R3-3 + R2-3: the URL is trimmed to its quote-aware
    invocation span (the SAME seam as _bash_rows — bytes past an unquoted `&` never reached the
    network, and could otherwise fake the host), and the match is the SAME method-keyed one
    _bash_rows uses (R4): a call to a declared host with a method no interface declares — or an
    unknowable method (dangling `-X`) — lands HERE, a network call the manifest does not cover
    must never silently vanish."""
    if not isinstance(tool_use, dict) or tool_use.get("name") != "Bash":
        return []
    inp = tool_use.get("input")
    cmd = inp.get("command") if isinstance(inp, dict) else None
    if not isinstance(cmd, str):
        return []
    out = []
    seps = _sep_positions(cmd)
    comments = _comment_regions(cmd)
    for m in _URL_RE.finditer(cmd):
        off = m.start()
        if _in_comment(off, comments):
            continue   # a URL riding in a `#` comment was never fetched — no phantom tally
        a, b = _invocation_span(cmd, off, seps)
        url = m.group(0)[:max(0, b - off)]
        if not url:
            continue
        try:
            parts = urlsplit(url)
            host, hostname = parts.netloc, parts.hostname
        except ValueError:
            continue
        if not host or _is_local_host(hostname):
            continue
        # S4 gate r8 sibling sweep: the tally covers a network call the manifest does not claim —
        # so it applies the SAME two gates as _bash_rows, but fails CLOSED. When the invocation
        # TOKENIZES (command is not None), a URL in an `echo`, or the value of a `-H`/`--referer`
        # flag, was NEVER fetched → skipped (not a network call, no phantom tally). When it does
        # NOT tokenize (command None), the call is unparseable — fail closed: it falls through to
        # the method-keyed match (None method claims nothing → tallied), visible, never silenced.
        command, method, operands = _curl_scan(cmd[a:b])
        if command is not None:
            if command not in _HTTP_CLIENTS:
                continue
            if not any(s <= off - a < e for s, e in operands):
                continue
        # R4 structural: the SAME method-keyed match as _bash_rows — whatever it does not
        # claim (unknown host, no interface with this method, None method) lands here
        if _match_url(recognizers.get("url", []), url, method) is None:
            out.append((off, host))
    return out


# --- result resolution (the one I/O the recognizer's caller does) --------------------------------

def content_text(line_obj, tuid):
    """The tool_result CONTENT text for a tool_use_id inside one parsed transcript line —
    a bare string or joined text blocks; None when absent."""
    for b in (line_obj.get("message", {}) or {}).get("content", []) or []:
        if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") == tuid:
            c = b.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return "".join(x.get("text", "") for x in c
                               if isinstance(x, dict) and x.get("type") == "text")
    return None


def _spill_ok(spill, allowed_base):
    """Codex S4 gate 9 — a spilled tool-result pointer may point at ANY local file ≤4MB, so a
    followed spill is confined to the session's own `tool-results/` dir: True iff `spill`, RESOLVED
    (symlinks followed — a symlink inside tool-results/ escaping outside is rejected too), sits
    inside `allowed_base` (also resolved). `allowed_base` None means UNCONFINED — the pure/direct
    callers (tests, in-process) opt out; the harvest walk ALWAYS supplies the session's dir."""
    if allowed_base is None:
        return True
    try:
        rp = Path(spill).resolve()
        base = Path(allowed_base).resolve()
    except OSError:
        return False
    return rp == base or base in rp.parents


def follow_pointer(text, allowed_base=None):
    """Resolve a `<persisted-output>` spill pointer (the REAL store format) to the spilled
    file's content. Degrade, never raise: an unreadable/absent spill — or one that escapes
    `allowed_base` (gate 9) — returns the pointer text itself (the preview inside it is still
    parseable evidence)."""
    if not isinstance(text, str) or "<persisted-output>" not in text:
        return text
    m = _POINTER_RE.search(text)
    if not m:
        return text
    try:
        if _spill_ok(m.group(1), allowed_base):
            p = Path(m.group(1))
            if p.is_file() and p.stat().st_size <= _MAX_SPILL_BYTES:
                return p.read_text(errors="replace")
    except OSError:
        pass
    return text


def result_payload(line_obj, tuid, follow=True, allowed_base=None):
    """The RESOLVED result recognize() consumes, from one parsed tool-result transcript line:
    prefer toolUseResult's first-class spill path (persistedOutputPath — the FULL output),
    then its structured dict (WebSearch) or stdout, then the message content text; spill
    pointers followed (`follow=False` for a pure look at what the line itself carries).
    `allowed_base` (gate 9) confines a followed spill to the session's `tool-results/` dir — the
    harvest walk supplies it; None (pure/direct callers) is unconfined."""
    tur = line_obj.get("toolUseResult")
    if isinstance(tur, dict):
        spill = tur.get("persistedOutputPath")
        if follow and isinstance(spill, str) and _spill_ok(spill, allowed_base):
            try:
                p = Path(spill)
                if p.is_file() and p.stat().st_size <= _MAX_SPILL_BYTES:
                    return p.read_text(errors="replace")
            except OSError:
                pass
        if isinstance(tur.get("stdout"), str):
            return follow_pointer(tur["stdout"], allowed_base) if follow else tur["stdout"]
        return tur
    if isinstance(tur, str):
        return follow_pointer(tur, allowed_base) if follow else tur
    text = content_text(line_obj, tuid)
    return follow_pointer(text, allowed_base) if follow else text


# --- dispatch mapping (E1: identity by session anchor + interval, never "last open") -------------

def _parse_ts(v):
    """A transcript/event timestamp → aware datetime, or None (a row with an unreadable clock
    maps to NO interval — orphan, never a fabricated join)."""
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def dispatch_intervals(log=eventlog.LOG):
    """Per-session dispatch intervals from the log, keyed on the MONOTONIC SESSION ANCHOR that
    S2's `dispatch.open` records (session_id + the open event's own `seq`), NEVER wall clock
    (Codex S4 gate 1 / E1: skew/replay/late-publish corrupt a ts-ordered join). Each open
    (payload: dispatch_id + session_id anchor + declared theme/intent/geometry) opens an interval;
    the session's dispatches are ordered by the anchor `seq`, and each interval CLOSES at the
    earliest-by-SEQ of (the `artefato.published` that consumes ITS dispatch_id — matched by
    IDENTITY, never ts-proximity, and only when it came AFTER the open in seq order) and the next
    open of the SAME session. A `dispatch.open` with NO session_id anchor forms no interval (its
    would-be rows are orphans — the anchor is absent). An unconsumed latest dispatch stays
    open-ended. A row between a consume and the next open sits in NO interval: orphan (E1 —
    reconstruction by 'last open' is exactly what this forbids).

    The interval's ts-window is derived from those seq-chosen boundary events purely to LOCATE a
    transcript row, which carries no event-log seq — its one cross-axis locator is its own
    transcript clock (a within-session, single-machine comparison, unaffected by cross-machine
    skew). `min()` over the boundary tss clamps a late/skewed publish to the next open so intervals
    never overlap; the SEQ ordering + dispatch_id identity above are what make the STRUCTURE robust.
    A dispatch CONSUMED by seq+identity whose publish carries NO usable clock (absent ts, or
    skewed BEFORE the open) still CLOSES — conservatively at its own start, zero-width (R2-5):
    rows never map into a dispatch whose close we cannot locate in time; they orphan instead
    (the same fail-closed posture as an unreadable row clock — never a fabricated join, and
    never an interval that outlives its own consumption)."""
    evs = eventlog.read(types=["dispatch.open", "artefato.published"], log=log)
    consumed = {}   # dispatch_id -> (seq, ts) of the EARLIEST-by-seq consuming published (identity)
    opens = []
    for e in evs:
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        did = p.get("dispatch_id")
        if not (isinstance(did, str) and did):
            continue
        seq = eventlog._event_seq(e)
        ts = _parse_ts(e.get("ts"))
        if e.get("type") == "dispatch.open":
            sid = p.get("session_id")
            if isinstance(sid, str) and sid:   # the anchor — absent → no interval (orphan)
                opens.append({"session_id": sid, "dispatch_id": did, "start": ts, "seq": seq,
                              "theme": p.get("theme"), "intent": p.get("intent"),
                              "geometry": p.get("geometry")})
        elif did not in consumed or seq < consumed[did][0]:
            consumed[did] = (seq, ts)
    by_session = {}
    for o in opens:
        by_session.setdefault(o["session_id"], []).append(o)
    intervals = {}
    for sid, lst in by_session.items():
        lst.sort(key=lambda o: o["seq"])   # the MONOTONIC ANCHOR orders the session's dispatches
        for i, o in enumerate(lst):
            start = o["start"]
            cons = consumed.get(o["dispatch_id"])
            consumed_by_seq = cons is not None and cons[0] > o["seq"]
            cons_ts = cons[1] if consumed_by_seq else None
            next_ts = lst[i + 1]["start"] if i + 1 < len(lst) else None
            cons_usable = cons_ts is not None and (start is None or cons_ts >= start)
            if consumed_by_seq and not cons_usable:
                # R2-5: consumed by IDENTITY+SEQ but the publish clock is absent/skewed-before-
                # open — close conservatively at start (zero-width): the dispatch is OVER, and
                # rows we cannot place inside it orphan rather than map into an interval the
                # missing clock would otherwise leave open forever
                end = start
            else:
                ends = [t for t in (cons_ts, next_ts)
                        if t is not None and (start is None or t >= start)]
                end = min(ends) if ends else None
            intervals.setdefault(sid, []).append({**o, "end": end})
    return intervals


def _map_dispatch(intervals, session_id, ts):
    """The interval a row's (session anchor, timestamp) falls in — start inclusive, end
    exclusive; None when outside every interval (orphan). An interval whose open carried an
    unreadable clock (start None) can locate no row → skipped (those rows orphan)."""
    if ts is None:
        return None
    for iv in intervals.get(session_id, []):
        if iv["start"] is not None and iv["start"] <= ts and (iv["end"] is None or ts < iv["end"]):
            return iv
    return None


def _finalize(row, intervals, subagent_meta, meta_verified=False):
    """Stamp dispatch identity + attribution tier onto one recognized row. Ladder:
    inside an interval → opaque-script kept (the query is what is opaque) > mapped (the subagent
    meta.json join, ONLY when its chain is VERIFIED — gate 3, `meta_verified`) > declared (the
    dispatch declared theme/intent) > unknown; outside every interval → dispatch_id null + orphan
    (E1). The subagent block is still attached for provenance even when the chain does not verify
    — the read IS a subagent's, only its attribution tier falls back."""
    sid = row["raw_ref"][0]
    iv = _map_dispatch(intervals, sid, _parse_ts(row.get("ts")))
    if subagent_meta:
        row["subagent"] = {k: subagent_meta.get(k)
                           for k in ("agentType", "description", "toolUseId")}
    if iv is None:
        row["dispatch_id"] = None
        row["attribution"] = "orphan"
        return row
    row["dispatch_id"] = iv["dispatch_id"]
    if isinstance(iv.get("geometry"), str):
        row["geometry"] = iv["geometry"]
    if isinstance(iv.get("intent"), str):
        row["intent"] = iv["intent"]
    if row["attribution"] != "opaque-script":
        if meta_verified:
            row["attribution"] = "mapped"
        elif iv.get("theme") or iv.get("intent"):
            row["attribution"] = "declared"
        else:
            row["attribution"] = "unknown"
    return row


# --- the incremental walk -------------------------------------------------------------------------

def _store_files(project_dirs):
    """E7: every session transcript across ALL given project dirs (never derived from HOME/cwd —
    a worktree changes the slug) — each dir's top-level session transcripts + every subagents/
    transcript under it."""
    files = []
    for d in project_dirs:
        d = Path(d)
        files += sorted(d.glob("*.jsonl"))
        files += sorted(d.glob("*/subagents/*.jsonl"))
    return files


def _subagent_meta(path):
    """The sibling agent-*.meta.json of a subagents/ transcript ({agentType, description,
    toolUseId} joining to the parent's Agent tool_use) — None when absent/corrupt."""
    if path.parent.name != "subagents":
        return None
    meta = path.with_name(path.stem + ".meta.json")
    try:
        obj = json.loads(meta.read_text())
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def _session_tool_results(path):
    """The session's own `tool-results/` dir for `path` — the ONLY dir a spilled tool-result
    pointer may resolve into (gate 9). A subagent transcript shares its parent session's dir."""
    session_dir = path.parent.parent if path.parent.name == "subagents" else path.with_suffix("")
    return session_dir / "tool-results"


def _meta_chain_valid(path, meta):
    """Codex S4 gate 3 — the `mapped` tier's chain PROVEN, not assumed: meta.json → toolUseId →
    the parent transcript's Agent tool_use whose `input.prompt` declares the intent. A stale/
    corrupt meta (toolUseId names no Agent tool_use, or one with no prompt) fails this check, so
    `_finalize` falls the row to `declared`/`unknown` instead of a fabricated `mapped`. The parent
    transcript is the session file beside the subagents/ dir (…/<slug>/<sid>.jsonl)."""
    if not (isinstance(meta, dict) and isinstance(meta.get("toolUseId"), str) and meta["toolUseId"]):
        return False
    if path.parent.name != "subagents":
        return False
    parent = path.parent.parent.parent / f"{path.parent.parent.name}.jsonl"
    tuid = meta["toolUseId"]
    try:
        lines = parent.read_text(errors="replace").splitlines()
    except OSError:
        return False
    for ln in lines:
        try:
            obj = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        for b in (obj.get("message", {}) or {}).get("content", []) or []:
            if (isinstance(b, dict) and b.get("type") == "tool_use"
                    and b.get("id") == tuid and b.get("name") == "Agent"):
                inp = b.get("input")
                prompt = inp.get("prompt") if isinstance(inp, dict) else None
                return isinstance(prompt, str) and bool(prompt.strip())
    return False


def _fallback_session_id(path):
    """The session a transcript belongs to, from its LOCATION: the parent session for a
    subagents/ file (…/<sid>/subagents/agent-x.jsonl), its own stem otherwise. Used only when
    a line carries no sessionId of its own."""
    if path.parent.name == "subagents":
        return path.parent.parent.name
    return path.stem


def _scan_file(path, start, recognizers):
    """One transcript's delta since its cursor → (recognized rows, unrecognized tallies,
    dark count, new watermark, expired count). The sweep's tail idiom: a truncated FINAL line
    is left for the next run. An unpaired tool_use holds the watermark back ONLY while it is
    the LIVE tail (emitting early would freeze hits=None forever under first-emission-wins);
    once ANY complete JSON line lands AFTER it the writer has moved on — the call was
    cancelled, it EXPIRES: counted, skipped, cursor advances (Codex S4 gates D5+D7 — a dead
    call must never pin the file to eternal full re-scans, and a session that continues with
    plain dialogue, no further tool_result ever, moves on just the same)."""
    lines = path.read_text(errors="replace").splitlines()
    watermark = len(lines)
    if watermark > start:
        try:
            json.loads(lines[-1])
        except ValueError:
            watermark -= 1
    meta = _subagent_meta(path)
    meta_valid = _meta_chain_valid(path, meta)   # gate 3: the mapped chain PROVEN, not assumed
    allowed_base = _session_tool_results(path)    # gate 9: confine followed spills to this dir
    fallback_sid = _fallback_session_id(path)
    uses, results, dark = [], {}, 0
    last_complete = -1   # the last COMPLETE line — the D7 "writer moved on" horizon
    for n in range(start, watermark):
        try:
            obj = json.loads(lines[n])
        except ValueError:
            continue   # a crashed writer's interior line — noise, as sessions._turns_from_lines
        last_complete = n
        if not isinstance(obj, dict):
            continue
        content = (obj.get("message", {}) or {}).get("content")
        if not isinstance(content, list):
            continue
        if obj.get("type") == "assistant":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    uses.append((n, obj, b))
        elif obj.get("type") == "user":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    results[b.get("tool_use_id")] = obj
    rows, unrec = [], []
    live_unpaired, expired = [], 0
    for n, obj, block in uses:
        tuid = block.get("id")
        if tuid not in results:
            if n < last_complete:
                expired += 1   # a complete line landed after it: the writer moved on (D7)
            else:
                live_unpaired.append(n)   # the ACTUAL tail: a writer mid-flush, hold for it
            continue
        sid = obj.get("sessionId") if isinstance(obj.get("sessionId"), str) else fallback_sid
        try:
            resolved = result_payload(results[tuid], tuid, allowed_base=allowed_base)
            recognized = recognize(block, resolved, recognizers, session_id=sid,
                                   transcript_line=n, ts=obj.get("timestamp"))
            for r in recognized:
                rows.append((r, meta, meta_valid))
            for off, host in unrecognized_urls(block, recognizers):
                unrec.append(([sid, n, tuid, off], host))
        except Exception:   # noqa: BLE001 — fail-dark PER ROW, counted, never fatal (R2.2e)
            dark += 1
    if live_unpaired:
        watermark = min(watermark, min(live_unpaired))
    return rows, unrec, dark, watermark, expired


def _known_refs(log):
    """The dedup base, RANKED (Codex S4 gate D1): {raw_ref: best (recognizer_rev, seq) rank
    already in the log} — a supersede event ranks onto its TARGET (the same identity the fold
    competes on, cortex.supersede_rank). Same-or-lower rev re-harvests are no-ops (E2:
    retro-harvest is re-FOLD, never re-append); a HIGHER rev emits a `supersedes` row —
    the versioned interpretation E2b promises. Unmanifested tallies dedup by the same brute
    key (a plain set — a tally has no interpretation to version)."""
    refs, unrec = {}, set()
    for e in eventlog.read(types=["grounding.manifest", "grounding.unmanifested"], log=log):
        p = e.get("payload")
        if not isinstance(p, dict):
            continue
        if e.get("type") == "grounding.unmanifested":
            for r in p.get("refs") or []:
                k = eventlog._raw_ref_key(r)
                if k:
                    unrec.add(k)
            continue
        target = (eventlog._raw_ref_key(p.get("supersedes"))
                  or eventlog._raw_ref_key(p.get("raw_ref")))
        if target:
            rank = cortex.supersede_rank(p, e)
            if target not in refs or rank > refs[target]:
                refs[target] = rank
    return refs, unrec


# refs per grounding.unmanifested event (Codex S4 gate D3): a giant retro-run over a big
# store fans into several BOUNDED events instead of one giant fragile JSONL line — each chunk
# self-describing (count == len(refs), its own by_host slice), all dedupable by brute ref.
_UNMANIFESTED_CHUNK = 200


def _cursor_start(v):
    """One cursor entry → ({"lines","size","mtime"}, was_valid). The cursor VALUE is a stat
    TRIPLE now (S4 #62): the line watermark PLUS the (size, mtime) of the file that produced it,
    so an unchanged file is stat-skipped whole (no read/parse) on the next walk. A legacy bare
    int is read as {lines: v} with unknown size/mtime — which forces exactly one self-healing
    re-read (its stat can't match an unknown), never a crash on the format change.

    Gate R2-1 (preserved): a VALID-JSON file can still carry a corrupt VALUE ("bad", null, true,
    -5, 3.7 — bare OR a dict whose `lines` is one of those). Only a non-bool int >= 0 lines is a
    scan offset; anything else clamps to 0 (full re-scan of that file, the ranked/brute dedup
    absorbs it) with was_valid=False so the caller FLAGS the degradation — never an int() crash
    and never a scan from an invalid offset."""
    if isinstance(v, dict):
        lines = v.get("lines")
        if isinstance(lines, int) and not isinstance(lines, bool) and lines >= 0:
            size = v.get("size")
            size = size if isinstance(size, int) and not isinstance(size, bool) and size >= 0 else None
            mtime = v.get("mtime")
            mtime = mtime if isinstance(mtime, (int, float)) and not isinstance(mtime, bool) else None
            return {"lines": lines, "size": size, "mtime": mtime}, True
        return {"lines": 0, "size": None, "mtime": None}, False
    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        return {"lines": v, "size": None, "mtime": None}, True
    return {"lines": 0, "size": None, "mtime": None}, False


# incremental durable cursor (S4 #62): the whole cursor dict is re-written atomically every
# _CURSOR_FLUSH_EVERY advanced files (and once after the loop/break), so a budget cap or a crash
# keeps every completed file's watermark — progress is never lost to a single end-of-walk flush
# that never arrives (the #62 timeout-loses-everything bug).
_CURSOR_FLUSH_EVERY = 25


def _write_cursors_atomic(cursors_path, cursors):
    """Re-write the whole cursor dict atomically (tmp + os.replace) — a reader (or a crash) never
    sees a half-written cursor file (D2 durability, S4 #62)."""
    tmp = cursors_path.with_name(cursors_path.name + ".tmp")
    tmp.write_text(json.dumps(cursors, indent=2, sort_keys=True))
    os.replace(tmp, cursors_path)


def _unmanifested_events(new_unrec, rev):
    """The blind-leg tally as CHUNKED (type, subject, payload) events (D3), ready for the
    same per-file append_batch as the manifests (D2)."""
    events = []
    for i in range(0, len(new_unrec), _UNMANIFESTED_CHUNK):
        chunk = new_unrec[i:i + _UNMANIFESTED_CHUNK]
        by_host = {}
        for _, host in chunk:
            by_host[host] = by_host.get(host, 0) + 1
        events.append(("grounding.unmanifested", "grounding",
                       {"count": len(chunk), "by_host": by_host,
                        "refs": [r for r, _ in chunk], "recognizer_rev": rev}))
    return events


def harvest(log=eventlog.LOG, cursors_path=CURSORS, project_dirs=None, store_root=None,
            recognizers=None):
    """The harvester's incremental walk (design-emissao C, the spine): cursor per transcript
    file under an exclusive flock (the sweep's cursors idiom — two overlapping harvests must
    not double-emit), over ALL project dirs + subagents/ (E7). `project_dirs` is the contract
    seam (the explicit list of store project dirs to sweep); `store_root` is the back-compat
    shorthand for "every dir under this root". Emits ONE `grounding.manifest` event per
    recognized row (the exact shape fold_grounding consumes); unclaimed network-shaped calls
    land as CHUNKED `grounding.unmanifested` tallies (B2/D3). Rows AND tallies of one file go in
    ONE append_batch, BEFORE that file's cursor advances (D2, ADR-0006: a crash between append
    and cursor-save re-emits and the ranked/brute dedup absorbs it — an event is never lost to a
    cursor that outran it). Returns the number of manifest rows emitted.

    Retro-supersede (D1, E2b): a run whose recognizers carry a HIGHER rev than a known
    raw_ref's best rank re-emits it as a `supersedes` row — the interpretation is versioned,
    the fold projects max (recognizer_rev, seq); same/lower rev stays a no-op.

    Raises ONLY on an absent store (ADR-0015: a harvest that cannot see the substrate must not
    look like it ran). A CORRUPT cursor is a VISIBLE degradation (gates 5 + R2-1), never a
    crash — at BOTH grains: an unparseable/non-object FILE resets to {}, and a valid-JSON file
    whose per-file VALUE is corrupt (non-int, bool, negative) clamps THAT entry to 0 — either
    way flagged + printed, and the ranked/brute dedup makes the re-read a no-op. Everything
    else is fail-dark per row, counted and printed."""
    if project_dirs is not None:
        dirs = [Path(p) for p in project_dirs]
        if not any(d.is_dir() for d in dirs):
            raise FileNotFoundError(
                f"no transcript project dir exists among {[str(d) for d in dirs]} — the "
                "harvester's substrate (ADR-0015: fail loud, never scan an absent store as "
                "'nothing new')")
    else:
        store_root = Path(store_root) if store_root is not None else STORE_ROOT
        if not store_root.is_dir():
            raise FileNotFoundError(
                f"transcript store absent: {store_root} — the harvester's substrate (ADR-0015: "
                "fail loud, never scan a nonexistent store as 'nothing new')")
        dirs = sorted(p for p in store_root.iterdir() if p.is_dir())
    if recognizers is None:
        recognizers = build_recognizers()
    current_rev = recognizers.get("rev", RECOGNIZER_REV)
    if isinstance(current_rev, bool) or not isinstance(current_rev, (int, float)):
        current_rev = RECOGNIZER_REV
    # bounded walk (S4 #62): the budget is read INSIDE harvest() so the env var works per-call;
    # a non-numeric budget FAILS LOUD (raise) — never a silent default that hides a bad env.
    budget_raw = os.environ.get("EDGE_HARVEST_BUDGET_S", "20")
    try:
        budget = float(budget_raw)
    except (TypeError, ValueError):
        raise ValueError(
            f"EDGE_HARVEST_BUDGET_S={budget_raw!r} is not a number — the harvest budget must be a "
            "numeric seconds value (fail loud, never default silently)")
    if not math.isfinite(budget) or budget < 0:
        # nan/inf/negative would make `time.monotonic() > deadline` never trip → the walk goes
        # unbounded again (the #62 hang) while holding the lock. Reject LOUD, never silently un-cap.
        raise ValueError(
            f"EDGE_HARVEST_BUDGET_S={budget_raw!r} is not a finite non-negative number — "
            "nan/inf/negative would un-bound the harvest walk (#62); fail loud.")
    total = dark_total = expired_total = unrec_total = 0
    corrupt_cursor = False
    capped = False
    cursors_path = Path(cursors_path)
    cursors_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = cursors_path.with_name(cursors_path.name + ".lock")
    with lock_path.open("w") as lk:
        # NON-BLOCKING (S4 #62): the harvest is a degrade-dark grounding leg, never a chokepoint.
        # If another instance holds the cursor lock, this wake goes DARK and retries next time —
        # it must NOT block the wake behind an O(store) walk it does not own.
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("harvest: outra instância segura o cursor lock — DARK este wake, retry no "
                  "próximo", file=sys.stderr)
            return 0
        try:
            # the dedup base + dispatch intervals load UNDER THE LOCK (gate 6): a concurrent
            # harvest must never read a stale known-set/intervals and re-emit a row the other
            # writer already landed — the whole read-base / scan / cursor-save is serialized.
            known, known_unrec = _known_refs(log)
            intervals = dispatch_intervals(log)
            try:
                cursors = json.loads(cursors_path.read_text()) if cursors_path.exists() else {}
                if not isinstance(cursors, dict):
                    raise ValueError("cursor file is not a JSON object")
            except (ValueError, OSError):
                cursors = {}   # gate 5: corrupt cursor = visible degradation, not a crash
                corrupt_cursor = True
            deadline = time.monotonic() + budget
            since_flush = 0
            for path in _store_files(dirs):
                if time.monotonic() > deadline:
                    capped = True   # budget spent — stop here, the persisted cursors resume us
                    break
                key = str(path)
                entry, cursor_ok = _cursor_start(cursors.get(key, 0))
                if not cursor_ok:
                    corrupt_cursor = True   # R2-1: corrupt VALUE clamped to 0, flagged visible
                try:
                    st = os.stat(path)
                except OSError:
                    dark_total += 1   # an unstattable transcript is a dark leg, not a crash
                    continue
                # stat-skip (S4 #62): an unchanged file (size AND mtime match the cursor's) is not
                # read or parsed at all — its cursor entry is carried forward VERBATIM into the
                # rewritten dict (else the next run re-reads it). Legacy/unknown size/mtime never
                # matches, so it forces one self-healing read.
                if entry["size"] == st.st_size and entry["mtime"] == st.st_mtime:
                    cursors[key] = {"lines": entry["lines"], "size": entry["size"],
                                    "mtime": entry["mtime"]}
                    continue
                try:
                    rows, unrec, dark, watermark, expired = _scan_file(
                        path, entry["lines"], recognizers)
                except OSError:
                    dark_total += 1   # an unreadable transcript is a dark leg, not a crash
                    continue
                dark_total += dark
                expired_total += expired
                batch = []
                for row, meta, meta_valid in rows:
                    ref = eventlog._raw_ref_key(row["raw_ref"])
                    if ref is None:
                        continue
                    if ref in known:
                        if current_rev <= known[ref][0]:
                            continue   # same/lower rev: the retro-run is a no-op (E2)
                        # D1: a BETTER recognizer reinterprets the SAME brute occurrence —
                        # the fold's max (recognizer_rev, seq) will project this row
                        row["supersedes"] = row["raw_ref"]
                    known[ref] = (current_rev, float("inf"))
                    batch.append(("grounding.manifest", "grounding",
                                  _finalize(row, intervals, meta, meta_verified=meta_valid)))
                n_rows = len(batch)
                new_unrec = []
                for ref_list, host in unrec:
                    k = eventlog._raw_ref_key(ref_list)
                    if k and k not in known_unrec:
                        known_unrec.add(k)
                        new_unrec.append((ref_list, host))
                batch.extend(_unmanifested_events(new_unrec, current_rev))
                if batch:
                    # ONE indivisible write per file, BEFORE the cursor advances (D2)
                    eventlog.append_batch(batch, log=log)
                    total += n_rows
                    unrec_total += len(new_unrec)
                # cursor advances AFTER the append (D2) — the stat triple that produced watermark
                cursors[key] = {"lines": watermark, "size": st.st_size, "mtime": st.st_mtime}
                since_flush += 1
                if since_flush >= _CURSOR_FLUSH_EVERY:
                    # incremental durable flush (S4 #62): a cap/crash after here keeps this batch
                    _write_cursors_atomic(cursors_path, cursors)
                    since_flush = 0
            _write_cursors_atomic(cursors_path, cursors)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    print(f"harvest: {total} row(s) emitted"
          + (f", {unrec_total} unrecognized network call(s) tallied" if unrec_total else "")
          + (f", {dark_total} dark row(s) (counted, skipped)" if dark_total else "")
          + (f", {expired_total} expired unpaired tool_use(s)" if expired_total else "")
          + (f", CAPPED at {budget:g}s budget (progress saved, next wake resumes)" if capped else "")
          + (", corrupt cursor state reset (dedup absorbs the re-read)" if corrupt_cursor else ""))
    return total


# --- the close's floor (S6 injects this — no close.py changes here) -------------------------------

def session_floor(session_id, recognizers=None, store_root=None):
    """The genus floor's mechanical evidence (enxerto A1): the PURE recognize() run over ONE
    live session's transcript — located by INDEX across ALL project dirs (E7: the project-dir
    slug is never derived), subagents included (a fanned explorer's read IS the dispatch's
    read). Returns {"reads", "recognized", "dark", "reason"} and NEVER raises: a floor that
    cannot see is a counted `grounding.floor_dark` (S6), not a crash in the close."""
    try:
        root = Path(store_root) if store_root is not None else STORE_ROOT
        if not root.is_dir():
            return {"reads": 0, "recognized": [], "dark": True,
                    "reason": f"transcript store absent: {root}"}
        mains = sorted(root.glob(f"*/{session_id}.jsonl"))
        if not mains:
            return {"reads": 0, "recognized": [], "dark": True,
                    "reason": f"transcript not found for session {session_id!r} in any "
                              "project dir (E7 index)"}
        if recognizers is None:
            recognizers = build_recognizers()
        files = mains + sorted(root.glob(f"*/{session_id}/subagents/*.jsonl"))
        recognized = []
        for path in files:
            rows, _, _, _, _ = _scan_file(path, 0, recognizers)
            recognized.extend(row for row, _, _ in rows)
        return {"reads": len(recognized), "recognized": recognized,
                "dark": False, "reason": None}
    except Exception as e:   # noqa: BLE001 — the floor NEVER raises into the close
        return {"reads": 0, "recognized": [], "dark": True,
                "reason": f"{type(e).__name__}: {e}"}


# The exact violation string the gate surfaces (design-close §6). A NAMED gap so the genus bounce
# message tells the live agent precisely what to cure (go read a source mid-session and re-close).
FLOOR_VIOLATION = ("grounding-floor: dispatch themed sem nenhuma leitura de fonte "
                   "reconhecida na sessão")


def close_floor(*, log=None, store_root=None, session_id=None, child_session=None,
                recognizers=None, knob=None):
    """The floor_fn injected into `close.run_close` (S6, design-close §6). Consumes the
    EDGE_GROUNDING_FLOOR knob — 0=off (→ []), 1=observe (count the would-be violation as
    `grounding.floor` / darkness as `grounding.floor_dark`, but NEVER block → []), 2=gate (return the
    named violation on a THEMED dispatch with ZERO recognized source-reads). Decides THEMED via the
    LAST dispatch.open geometry for the session (S2/enxerto A2), then runs `session_floor`'s pure
    recognize over the live transcript.

    Fail-OPEN is DELIBERATE (inverse of genus — §6): env absent (close run outside a Claude session),
    transcript absent, undeclared geometry, or CLAUDE_CODE_CHILD_SESSION set (reads may live in the
    parent transcript, not identifiable today) → [] + a COUNTED `grounding.floor_dark` event, never a
    block (a fail-closed floor would kill every close run out-of-session — tests, operator). Ambient
    geometry NEVER gates (R3.2) — a deliberate non-gate, not an instrument failure, so it is NOT dark.
    NEVER raises into the close. log/store_root/session_id/child_session/knob are injectable for tests;
    live they default to eventlog.LOG / STORE_ROOT / the CLAUDE_CODE_* env."""
    try:
        if knob is None:
            # B.4 (ticket B): default 0=off → 1=OBSERVE — o primeiro degrau honesto: o
            # instrumento liga (conta violação/darkness), o veto (2=gate) continua opt-in.
            knob = _envconf.env_int("EDGE_GROUNDING_FLOOR", 1)
        if knob <= 0:
            return []
        if log is None:
            log = eventlog.LOG
        if session_id is None:
            session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if child_session is None:
            child_session = os.environ.get("CLAUDE_CODE_CHILD_SESSION")
        if not session_id:
            return _floor_dark("session-id absent (close run outside a Claude session)", log)
        if child_session:
            return _floor_dark("CLAUDE_CODE_CHILD_SESSION set — reads may live in the parent "
                               "transcript, not identifiable today", log)
        geometry = _last_geometry(session_id, log)
        if geometry is None:
            return _floor_dark("undeclared geometry (no dispatch.open declared a geometry for "
                               "this session)", log)
        if geometry != "themed":
            return []   # ambient NEVER gates (R3.2) — a deliberate non-gate, not darkness
        floor = session_floor(session_id, recognizers=recognizers, store_root=store_root)
        if floor.get("dark"):
            return _floor_dark(floor.get("reason") or "floor dark", log)
        if floor.get("reads"):
            return []   # themed WITH a recognized read — the floor is satisfied
        # themed + ZERO recognized reads = the floor violation
        if knob >= 2:
            return [FLOOR_VIOLATION]
        # observe (knob == 1): COUNT the would-be violation, never block
        _emit_floor_event("grounding.floor",
                          {"session_id": session_id,
                           "reason": "themed dispatch, zero recognized reads"}, log)
        return []
    except Exception:  # noqa: BLE001 — the floor NEVER raises into the close (fail-open by design)
        return []


def _floor_dark(reason, log):
    """Fail-OPEN dark: emit a COUNTED `grounding.floor_dark` event (never silent — enxerto B2) and
    return [] so the close never blocks on an instrument it cannot see (§6)."""
    _emit_floor_event("grounding.floor_dark", {"reason": reason}, log)
    return []


def _emit_floor_event(type_, payload, log):
    """Best-effort event emit — darkness/observation must be counted, but a broken log never crashes
    the close (the floor decision itself is the contract)."""
    try:
        eventlog.append(type_, "grounding", payload, log=log)
    except Exception:  # noqa: BLE001
        pass


def _last_geometry(session_id, log):
    """The geometry declared by the LATEST (by seq) dispatch.open for this session, or None when no
    dispatch.open names the session OR none declared a geometry → undeclared → dark (§6)."""
    try:
        evs = eventlog.read(types=["dispatch.open"], log=log)
    except Exception:  # noqa: BLE001 — an unreadable log is undeclared → dark
        return None
    best_seq, geometry = None, None
    for e in evs:
        p = e.get("payload")
        if not isinstance(p, dict) or p.get("session_id") != session_id:
            continue
        seq = eventlog._event_seq(e)
        if best_seq is None or seq > best_seq:
            best_seq, geometry = seq, p.get("geometry")
    return geometry

# Debugging Log

Errors that must not recur. READ at start of autonomous sessions. WRITE when errors occur.

---

## 2026-04-07: edge-consult broken (genotype)

**Error:** `ModuleNotFoundError: No module named '_shared.openai_client'` in `tools/edge-consult.py:35`
**Impact:** Adversarial sanity check (mandatory per pre-skill.md and report-template.md) cannot run. Research published without cross-model review.
**Root cause:** The `_shared` package isn't importable from the script's execution context. Likely a missing `__init__.py` or PYTHONPATH issue in the tools directory.
**Action:** Genotype issue — file GitHub issue in lucasrp/edge-of-chaos with [genotype] prefix. DO NOT fix in place.
**Status:** Open.

## 2026-04-07: OpenAI API key invalid for embeddings

**Error:** `Error code: 401 - Incorrect API key provided` during `edge-index` embedding step.
**Impact:** Documents indexed in FTS5 (full-text search works) but without vector embeddings. Hybrid search degrades to FTS-only.
**Root cause:** `AGENT_OPENAI_API_KEY` or configured key is expired/invalid.
**Action:** Check `secrets/keys.env` for the OpenAI key. Refresh if expired.
**Status:** Open.

## 2026-04-07: MCP source primitives not implemented (code 127)

**Error:** All MCP source tools (arxiv, exa, hackernews, grok, fleet-ssh, moltbook) return `{"error": "not implemented", "code": 127}`.
**Impact:** External source access limited to `edge-x` (X/Twitter) and `WebSearch`. Boot ritual delta-load cannot use primary sources.
**Root cause:** Primitives in `tools/primitives/` are stubs — the actual implementations haven't been written yet.
**Action:** These are genotype. Implementation needed per `docs/TOOL_CONTRACT.md`. Not blocking but limits source diversity.
**Status:** Open — expected during bootstrap phase.

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
**Status:** RESOLVED 2026-04-09. Operator provided new key via Drive. Updated in secrets/keys.env, tested OK, backed up to Drive.

## 2026-04-09: heartbeat.sh — claude command not found

**Error:** `heartbeat.sh: line 30: claude: command not found` in systemd timer log.
**Impact:** Automated heartbeat timer fails silently. Only manual `/ed-heartbeat` works.
**Root cause:** The systemd service runs in a restricted environment without the user's PATH. `claude` CLI is likely in a directory not in systemd's PATH.
**Action:** Genotype issue — heartbeat.sh needs full path to claude binary or PATH setup. File GitHub issue.
**Status:** Open.

## 2026-04-09: Grok API credits exhausted

**Error:** `429 - Your team has either used all available credits or reached its monthly spending limit` on grok-4.20-multi-agent-beta-0309.
**Impact:** edge-consult runs GPT-only. Adversarial review loses the second perspective.
**Root cause:** Heavy use during this session (multiple edge-consult calls). Monthly credit limit reached.
**Action:** Operator needs to purchase more Grok credits or wait for monthly reset.
**Status:** Open — notify operator.

## 2026-04-09: arXiv API rate limiting (429)

**Error:** `HTTP Error 429: Too Many Requests` when calling arXiv Atom API.
**Impact:** arxiv primitive works but gets rate-limited during heavy use. Multiple calls in quick succession fail.
**Root cause:** arXiv API enforces aggressive rate limits. Need 3-5 second delays between calls.
**Action:** Add exponential backoff to the arxiv primitive. Not blocking — will self-resolve with spacing.
**Status:** Open — primitive is functional, just needs backoff logic.


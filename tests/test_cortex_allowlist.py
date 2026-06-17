"""Per-cognition allowlist (Slice 4) — R6/N5: cortex_* is GRANTED to the lead beat and the self-reading
fan it dispatches, and DENIED to the delta/world subject (REQUISITES §4, N5, Appendix-A acceptance c).

ADR-0014's self/world split, restated for a STANDING tool: a read-only door does NOT stop the
IN-CONTEXT mixing of world-new delta beside recalled-self (the contamination forms before any write),
so the deny is a v1 REQUIREMENT, not an optional tightening. Two enforcement layers, BOTH committed:
  - server-side (tools/cortex_mcp): a server constructed for a denied subject withholds cortex_*
    entirely (Slice 2) — and is FAIL-CLOSED for an unknown subject in a denied-by-default config.
  - config-side (tools/cortex_config): the generated --mcp-config + the delta subagent's disallowedTools
    so a delta/world dispatch never even inherits the tool name (the harness half).
"""
import json
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_config  # noqa: E402
import cortex_mcp  # noqa: E402


class TheMcpConfigRegistersTheCortexServer(unittest.TestCase):
    """F1/N2 — the generated --mcp-config is a {"mcpServers": {"cortex": {...}}} doc registering the
    stdio server (command edge-python, args [tools/cortex_mcp.py]) with a per-call timeout (N1)."""

    def test_config_shape_registers_cortex_as_a_stdio_server(self):
        # a GRANTED subject's config registers the server (fail-closed: a subject is required).
        cfg = cortex_config.mcp_config(group="edge-test", home="/home/x/edge", subject="lead")
        self.assertIn("cortex", cfg["mcpServers"])
        srv = cfg["mcpServers"]["cortex"]
        self.assertTrue(srv["command"].endswith("edge-python"))
        self.assertEqual(srv["args"], ["/home/x/edge/tools/cortex_mcp.py"])   # absolute from home
        # an EXPLICIT group is baked into the server's env (a genotype install passes its own group)
        self.assertEqual(srv["env"]["EDGE_GROUP"], "edge-test")
        # N1 — a per-server tool timeout (ms) so a slow tool can't hang the harness
        self.assertIn("timeout", srv)

    def test_the_server_script_arg_is_absolute_from_home(self):
        # codex final [P2]: the script path must be ABSOLUTE from home, not the cwd-dependent relative
        # "tools/cortex_mcp.py" — else --mcp-config from any other directory fails to start the server.
        cfg = cortex_config.mcp_config(group="g", home="/home/x/edge", subject="lead")
        args = cfg["mcpServers"]["cortex"]["args"]
        self.assertEqual(args, ["/home/x/edge/tools/cortex_mcp.py"],
                         "the server script must be an absolute path rooted at home (cwd-independent)")

    def test_group_resolves_from_target_home_and_overrides_stale_inherited_env(self):
        # codex final [P2 x2]: with no explicit --group, the group is resolved from the TARGET home's
        # agent.yaml and BAKED into EDGE_GROUP — overriding any stale EDGE_GROUP the MCP subprocess
        # would inherit from the launcher env (the cross-install misroute). The baked value is the
        # target's own identity, NOT the launcher's, even with a foreign EDGE_GROUP set in the env.
        import os
        import tempfile
        import textwrap
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "agent.yaml").write_text(textwrap.dedent("""
                name: target-install
                graph_group: target-group
            """))
            saved = os.environ.get("EDGE_GROUP")
            os.environ["EDGE_GROUP"] = "launcher-group"   # a stale inherited value
            try:
                cfg = cortex_config.mcp_config(home=home, subject="lead")   # no explicit group
            finally:
                if saved is None:
                    os.environ.pop("EDGE_GROUP", None)
                else:
                    os.environ["EDGE_GROUP"] = saved
            self.assertEqual(cfg["mcpServers"]["cortex"]["env"]["EDGE_GROUP"], "target-group",
                             "the baked group must be the TARGET home's, overriding stale inherited env")

    def test_an_explicit_group_is_baked_into_edge_group(self):
        cfg = cortex_config.mcp_config(group="given-group", home="/h", subject="lead")
        self.assertEqual(cfg["mcpServers"]["cortex"]["env"]["EDGE_GROUP"], "given-group")

    def test_the_tool_names_are_namespaced_under_the_server(self):
        # MCP namespaces a server's tools as mcp__<server>__<tool>; the allowlist patterns key on it.
        self.assertEqual(cortex_config.tool_name("cortex_recall"), "mcp__cortex__cortex_recall")
        # the server-wide glob MUST be the documented mcp__<server>__* form (valid in both subagent
        # disallowedTools and skill disallowed-tools / permission rules) — NOT the bare mcp__cortex,
        # which the permission-rule syntax does not treat as a server-wide matcher (codex Slice-4 [high]).
        self.assertEqual(cortex_config.SERVER_TOOL_GLOB, "mcp__cortex__*")


class TheLeadAndSelfFanAreGranted(unittest.TestCase):
    """N5 — the lead beat and its in-cognition self-reading fan (recall/report/map/plan/...) GET the
    door. The config grants the whole server to the lead via build_beat_command's --mcp-config."""

    def test_build_beat_command_registers_the_cortex_mcp_config(self):
        cmd = cortex_config.build_beat_command("/usr/bin/claude", config_path="/tmp/cortex.mcp.json")
        self.assertIn("--mcp-config", cmd)
        self.assertIn("/tmp/cortex.mcp.json", cmd)
        # the base beat invocation is preserved
        self.assertIn("-p", cmd)
        self.assertIn("--dangerously-skip-permissions", cmd)

    def test_the_lead_allowlist_includes_the_cortex_server(self):
        allowed = cortex_config.allowed_tools(subject="lead")
        self.assertIn("mcp__cortex__*", allowed)

    def test_a_self_reading_producer_is_granted(self):
        for subj in ("recall", "report", "map", "plan", "research"):
            with self.subTest(subject=subj):
                self.assertIn("mcp__cortex__*", cortex_config.allowed_tools(subject=subj))


class TheDeltaWorldSubjectIsDenied(unittest.TestCase):
    """N5/R6 — the delta/world subject is DENIED cortex_*. The deny is expressed as the subagent
    disallowedTools (the harness removes mcp__cortex from the inherited pool) AND enforced server-side."""

    def test_delta_disallowed_tools_remove_the_cortex_server(self):
        denied = cortex_config.disallowed_tools(subject="delta")
        self.assertIn("mcp__cortex__*", denied,
                      "the delta/world subject must have cortex_* removed (disallowed-tools)")

    def test_delta_is_not_in_the_allowlist(self):
        self.assertNotIn("mcp__cortex__*", cortex_config.allowed_tools(subject="delta"))

    def test_a_world_or_source_reading_explorer_is_denied(self):
        # codex final-round [high]: not only `delta` — ANY world/source-reading subject (the explorers
        # a producer fans for the world) is denied the self door. The allowlist is fail-closed, so an
        # explorer/source/world subject is not granted, and disallowed_tools removes the server for it.
        for subj in ("explorer", "source", "world", "delta"):
            with self.subTest(subject=subj):
                self.assertEqual(cortex_config.allowed_tools(subject=subj), [])
                self.assertIn("mcp__cortex__*", cortex_config.disallowed_tools(subject=subj))

    def test_the_scaffold_instructs_the_explorer_deny(self):
        # the genotype mechanism: the ONE shared dispatch-shape (the scaffold) instructs that a
        # world-reading explorer subagent is fanned WITHOUT the self door (disallowed-tools), so the
        # boundary is mechanical across EVERY producer, not only the standalone delta skill.
        text = (REPO / "skills" / "_shared" / "scaffold.md").read_text()
        self.assertRegex(text, r"disallowed-tools:\s*mcp__cortex__\*",
                         "the scaffold must instruct the explorer/world-reader deny (N5/R6)")

    def test_every_world_reading_dispatch_path_carries_the_cortex_deny(self):
        # codex final-round [high]: scan EVERY skill that fans a world/source-reading explorer/lead
        # subagent — each such dispatch path must carry the cortex deny (disallowed-tools:
        # mcp__cortex__*), so no granted self-cognition leaks the self door into a world-reading fan.
        # A skill that FANS world-readers is detected by the dispatch idiom; the shared scaffold's
        # instruction covers the producers that funnel through it, grill carries its own.
        import re
        skills_dir = REPO / "skills"
        # an AFFIRMATIVE world-reading dispatch (not a prohibition like wake's "do NOT fan explorers").
        DISPATCH = re.compile(r"firing one explorer subagent|lead[- ]subagent (?:chases|per lead)|"
                              r"explorers go out and bring back|fan explorers out", re.I)
        NEGATED = re.compile(r"do\s+\*?\*?not\*?\*?\s+fan explorers", re.I)
        DENY = re.compile(r"disallowed-tools:\s*mcp__cortex__\*")
        offenders = []
        for sk in skills_dir.glob("*/SKILL.md"):
            text = sk.read_text()
            if NEGATED.search(text):
                continue                       # a skill that explicitly does NOT fan world-readers
            if DISPATCH.search(text) and not DENY.search(text):
                # the producers funnel through the scaffold's deny — accept a scaffold pointer too.
                if "scaffold" not in text.lower():
                    offenders.append(sk.parent.name)
        self.assertEqual(offenders, [],
                         f"these world-reading dispatch skills lack the cortex deny (N5/R6): {offenders}")

    def test_the_delta_skill_frontmatter_declares_the_deny_with_the_skill_key(self):
        # the genotype artifact the harness reads: skills/delta/SKILL.md is a SKILL, so the deny rides
        # the SKILL frontmatter key `disallowed-tools` (kebab-case) — NOT the subagent camelCase
        # `disallowedTools` — with the server-wide glob (codex Slice-4 [high]).
        text = (REPO / "skills" / "delta" / "SKILL.md").read_text()
        self.assertRegex(text, r"disallowed-tools:.*mcp__cortex__\*",
                         "the delta skill frontmatter must deny the cortex door via disallowed-tools (R6/N5)")
        self.assertNotRegex(text, r"disallowedTools:",
                            "a skill must not use the subagent camelCase key (it would be ignored)")


class FailClosedForUnknownSubject(unittest.TestCase):
    """codex Slice-4 [medium] — the server-side deny is REAL, not contingent on a glob the client might
    bypass: the generated config bakes EDGE_CORTEX_SUBJECT into the server env, and a world-typed
    config omits the cortex server entirely. Defense in depth that does not default open."""

    def test_server_denies_an_explicitly_denied_subject(self):
        srv = cortex_mcp.CortexServer(group="g", subject="delta",
                                      recall_fn=lambda group=None: {}, surf_fn=lambda s, group=None: [],
                                      fold_fn=lambda: {"nodes": [], "edges": []})
        self.assertEqual(srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"], [])

    def test_world_is_a_denied_subject_alias(self):
        self.assertIn("world", cortex_config.DENIED_SUBJECTS)
        self.assertIn("delta", cortex_config.DENIED_SUBJECTS)


class PolicyIsAllowlistNotDenylist(unittest.TestCase):
    """codex Slice-4 [high] — N5 fail-closed: the policy is an ALLOWLIST (grant-known-self), not a
    denylist. An omitted/unknown/typo subject gets NOTHING — never the door by default. Mirrored in
    the MCP server so a directly-launched server is fail-closed too."""

    def test_an_unknown_subject_is_not_granted(self):
        for bad in ("worldreader", "deltaa", "explorer", "scout", "intake", "unknown"):
            with self.subTest(subject=bad):
                self.assertEqual(cortex_config.allowed_tools(subject=bad), [],
                                 "an unknown subject must NOT receive the cortex door (fail-closed)")

    def test_an_omitted_subject_is_not_granted(self):
        self.assertEqual(cortex_config.allowed_tools(subject=None), [],
                         "an omitted subject must fail closed — no door without an explicit grant")

    def test_mcp_config_omits_cortex_for_an_unknown_subject(self):
        cfg = cortex_config.mcp_config(group="g", home="/h", subject="explorer")
        self.assertNotIn("cortex", cfg["mcpServers"],
                         "an unknown subject's config must not register the cortex server (fail-closed)")

    def test_mcp_config_omits_cortex_for_an_omitted_subject(self):
        cfg = cortex_config.mcp_config(group="g", home="/h", subject=None)
        self.assertNotIn("cortex", cfg["mcpServers"])

    def test_the_granted_self_cognitions_are_explicit(self):
        # the explicit grant set: lead + the self-reading fan; delta/world are absent by construction.
        self.assertIn("lead", cortex_config.GRANTED_SUBJECTS)
        self.assertIn("recall", cortex_config.GRANTED_SUBJECTS)
        self.assertNotIn("delta", cortex_config.GRANTED_SUBJECTS)
        self.assertNotIn("world", cortex_config.GRANTED_SUBJECTS)

    def test_write_config_requires_a_subject(self):
        # write_config must carry the subject through (no unscoped server env). It rejects an omitted one.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cortex.mcp.json"
            with self.assertRaises(Exception):
                cortex_config.write_config(p, group="g", home="/h")   # subject omitted → refuse

    def test_server_is_fail_closed_for_an_unknown_subject(self):
        # the MCP server mirrors the allowlist: an unknown subject sees NO tools (not default-open).
        srv = cortex_mcp.CortexServer(group="g", subject="explorer",
                                      recall_fn=lambda group=None: {}, surf_fn=lambda s, group=None: [],
                                      fold_fn=lambda: {"nodes": [], "edges": []})
        self.assertEqual(srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"], [],
                         "a server with an unknown subject must fail closed (no tools)")

    def test_the_generated_server_env_bakes_the_subject_for_server_side_enforcement(self):
        # the server constructed from this config reads EDGE_CORTEX_SUBJECT — so even if the client
        # glob is bypassed, a server launched in a world config denies (defense in depth, not glob-only).
        cfg = cortex_config.mcp_config(group="g", home="/home/x/edge", subject="lead")
        self.assertEqual(cfg["mcpServers"]["cortex"]["env"]["EDGE_CORTEX_SUBJECT"], "lead")

    def test_a_world_typed_config_omits_the_cortex_server_entirely(self):
        # the strongest deny: the delta/world dispatch gets NO cortex server in its --mcp-config at all,
        # so there is nothing to inherit even before disallowed-tools is consulted.
        cfg = cortex_config.mcp_config(group="g", home="/home/x/edge", subject="delta")
        self.assertNotIn("cortex", cfg["mcpServers"],
                         "a world-typed config must not register the cortex server at all (R6/N5)")


if __name__ == "__main__":
    unittest.main()

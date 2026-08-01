"""Hermes é a 4ª CLI padrão (operador 2026-07-25) — paridade com claude/codex/grok.

Hermes descobre user-skills de HERMES_HOME/skills/<name>/SKILL.md (mesma convenção
SKILL.md). Os wrappers são finos e apontam pro contrato canônico do install — mesmo
shape dos wrappers grok/codex. Genérico: nada de ed — qualquer install de qualquer
usuário do hermes provisiona igual.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _hermes_provision  # noqa: E402
import surfaces_cfg  # noqa: E402


class WrapperRender(unittest.TestCase):
    def test_wrapper_points_to_canonical_contract(self):
        out = _hermes_provision.render_hermes_skill(
            slug="wake", prefix="ed", canonical_skill=Path("/x/skills/wake/SKILL.md"),
            edge_group="hive")
        self.assertIn("name: ed-wake", out)
        self.assertIn("EDGE_GROUP=hive", out)
        self.assertIn("EDGE_HOME=/x", out)
        self.assertIn("working directory `/x`", out)
        self.assertIn("/x/skills/wake/SKILL.md", out)
        self.assertIn("canonical contract", out)
        self.assertIn("human-facing orientation", out)
        self.assertIn("ask what the operator wants to work on", out)
        self.assertIn("Do not start work before their reply", out)

    def test_terminal_invariant_is_wake_only(self):
     out = _hermes_provision.render_hermes_skill(
      slug="recall", prefix="ed", canonical_skill=Path("/x/skills/recall/SKILL.md"),
      edge_group="hive")
     self.assertNotIn("WAKE TERMINAL INVARIANT", out)

    def test_every_canonical_skill_gets_a_thin_wrapper(self):
     skills = Path(__file__).parents[1] / "skills"
     for canonical in sorted(skills.glob("*/SKILL.md")):
      slug = canonical.parent.name
      with self.subTest(slug=slug):
       out = _hermes_provision.render_hermes_skill(
        slug, "Steve", canonical, edge_group="hive")
       self.assertIn(f"name: Steve-{slug}", out)
       self.assertIn(str(canonical.resolve()), out)
       self.assertLess(len(out), 5_000)

    def test_mentor_wrapper_preserves_cadence_invariants(self):
        out = _hermes_provision.render_hermes_skill(
            slug="mentor", prefix="Steve", canonical_skill=Path("/x/skills/mentor/SKILL.md"),
            edge_group="hive")
        self.assertIn("HERMES PREFLIGHT SHORT-CIRCUIT", out)
        self.assertIn("before any tool call", out)
        self.assertNotIn("Read `", out)
        self.assertIn("opt-in portfolio orientation", out)
        self.assertIn("completed native mentor read", out)
        self.assertIn("configured memory provider", out)
        self.assertIn("Honcho tools are one implementation, not a requirement", out)
        self.assertIn("HERMES PREFLIGHT SHORT-CIRCUIT", out)
        self.assertIn("before any tool call", out)
        self.assertNotIn("Read `", out)
        self.assertIn("first user-facing mentor response", out)
        self.assertIn("before any user-facing mentor", out)
        self.assertIn("$EDGE_HOME/tools/mentor_preflight.py", out)
        self.assertIn("single mandatory read door", out)
        self.assertIn("emit no mentor response and ask no question", out)
        self.assertIn("generic orientation rule does not apply to mentor", out)
        self.assertIn("instruction to keep reading", out)
        self.assertIn("lint agenda as evidence", out)
        self.assertIn("never a menu", out)
        self.assertIn("persona writeback, steers, synthesis, and traceable inscription", out)
        self.assertIn("advice alone is not completion", out)
        self.assertIn("Do not stop and ask them to say continue", out)
        self.assertIn("Do not force a closing question", out)
        self.assertIn("never invent a writeback or inscription", out)


class HermesProvisionTest(unittest.TestCase):
    def test_configure_group_seeds_once_and_preserves_blank_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(_hermes_provision.configure_hermes_group(root, "hive"))
            self.assertIn("edge_group: hive", (root / "config.yaml").read_text())
            (root / "config.yaml").write_text("edge_group:\nother: kept\n")
            self.assertFalse(_hermes_provision.configure_hermes_group(root, "other-hive"))
            self.assertEqual((root / "config.yaml").read_text(), "edge_group:\nother: kept\n")

    def test_reconcile_installs_only_enabled_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "skills" / "wake").mkdir(parents=True)
            (repo / "skills" / "wake" / "SKILL.md").write_text("---\nname: wake\n---\nx")
            (root / "config.yaml").write_text("edge_group: hive\n")
            off = root / "profiles" / "off"
            off.mkdir(parents=True)
            (off / "config.yaml").write_text("edge_group: null\n")
            # null is origin-only, therefore still enabled.
            result = _hermes_provision.reconcile_hermes_profiles(
                {"skill_prefix": "ed", "tool_prefix": "edge"}, repo, root / "edge", root)
            self.assertIn("hermes skills", result["default"][0])
            self.assertIn("hermes skills", result["off"][0])


    def test_resolve_provision_cfg_loads_name_from_agent_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            edge = Path(tmp) / "edge"
            edge.mkdir()
            (edge / "agent.yaml").write_text("name: Steve\n")
            resolved = _hermes_provision.resolve_provision_cfg({}, edge)
            self.assertEqual(resolved.get("name"), "Steve")
            self.assertEqual(_hermes_provision.hermes_prefixes(resolved), ["Steve"])

    def test_hermes_prefixes_refuse_empty_identity(self):
        with self.assertRaises(ValueError):
            _hermes_provision.hermes_prefixes({})

    def test_empty_cfg_provision_uses_agent_yaml_not_edge_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            edge = root / "edge"
            hermes = root / "hermes"
            (repo / "skills" / "research").mkdir(parents=True)
            (repo / "skills" / "research" / "SKILL.md").write_text("# research\n")
            (edge / "skills" / "research").mkdir(parents=True)
            (edge / "skills" / "research" / "SKILL.md").write_text("# research\n")
            (edge / "agent.yaml").write_text("name: Steve\n")
            (hermes / "skills").mkdir(parents=True)
            # stale wrong-prefix managed wrapper must be removed
            stale = hermes / "skills" / "edge-research"
            stale.mkdir()
            (stale / "SKILL.md").write_text(
                "Canonical contract: " + str(edge / "skills") + "\n"
            )
            rows = _hermes_provision.provision_hermes({}, repo, edge, hermes)
            self.assertTrue((hermes / "skills" / "Steve-research" / "SKILL.md").is_file())
            self.assertFalse(stale.exists())
            self.assertTrue(any("wrappers" in r for r in rows))
            body = (hermes / "skills" / "Steve-research" / "SKILL.md").read_text()
            self.assertIn("name: Steve-research", body)

    def test_install_hermes_plugin_empty_cfg_reads_agent_yaml_for_skill_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edge = root / "edge"
            edge.mkdir()
            (edge / "agent.yaml").write_text("name: Steve\n")
            (root / "repo" / ".claude" / "agents").mkdir(parents=True)
            (root / "repo" / ".claude" / "agents" / "explorer.md").write_text("# explorer\n")
            plugin = _hermes_provision.install_hermes_plugin({}, root / "repo", edge, root)
            text = (plugin / "__init__.py").read_text()
            self.assertIn("SKILL_PREFIX = 'Steve'", text)

    def test_startup_plugin_is_installable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin({"name": "Steve"}, root / "repo", root / "edge", root)
            self.assertTrue((plugin / "plugin.yaml").is_file())
            compile((plugin / "__init__.py").read_text(), str(plugin / "__init__.py"), "exec")
            text = (plugin / "__init__.py").read_text()
            self.assertIn("ctx.register_hook('pre_llm_call', mentor_preflight)", text)
            self.assertIn("ctx.register_hook('pre_llm_call', recall_preflight)", text)
            self.assertIn("ctx.register_hook('pre_llm_call', assemble_preflight)", text)
            self.assertIn("ctx.register_hook('pre_llm_call', delta_preflight)", text)
            self.assertIn("ctx.register_hook('pre_llm_call', mark_session_active)", text)
            self.assertIn("ctx.register_hook('post_llm_call', mark_session_inactive)", text)
            self.assertIn("ctx.register_hook('pre_tool_call', mark_session_active)", text)
            self.assertIn("ctx.register_hook('post_tool_call', mark_session_inactive)", text)
            self.assertIn("HERMES_SESSION_ID", text)
            self.assertIn("tools' / 'mentor_preflight.py'", text)
            self.assertIn("subprocess.run", text)
            self.assertIn("command = f'/{SKILL_PREFIX}-{slug}'", text)
            self.assertIn("SKILL_PREFIX", text)
            self.assertIn(
                "_current_turn_invokes(user_message, conversation_history, 'mentor')",
                text,
            )
            self.assertIn("def wake_preflight", text)
            self.assertIn("tools' / 'predispatch.py'", text)
            self.assertIn("'--origin', 'user_requested'", text)
            self.assertIn("cwd=str(EDGE_HOME)", text)
            self.assertEqual(text.count("timeout=180"), 6)
            self.assertEqual(text.count("cwd=str(EDGE_HOME)"), 6)
            self.assertIn("def _edge_env", text)
            self.assertIn("_secrets.load_env", text)
            self.assertIn("EDGE_GROUP=_active_edge_group()", text)
            self.assertIn("EOC WAKE PREFLIGHT", text)
            self.assertIn("result.stdout[:6000]", text)
            self.assertIn("result.stdout[recall_at:recall_at + 6000]", text)
            self.assertIn("wake preflight missing DISPATCH_ID or Recall section", text)
            self.assertIn("ctx.register_hook('pre_llm_call', wake_preflight)", text)
            self.assertIn("_current_turn_invokes(user_message, conversation_history, 'recall')", text)
            self.assertIn("_invokes(user_message, 'wake')", text)
            self.assertIn("compose_recall_brief", text)
            self.assertIn("EOC RECALL PREFLIGHT", text)
            self.assertIn("Return that brief verbatim", text)

    def test_assemble_preflight_uses_canonical_predispatch_and_supplies_judgment_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edge = root / "edge"
            plugin = _hermes_provision.install_hermes_plugin({"name": "Steve"}, root / "repo", edge, root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            raw = "DISPATCH_ID=dispatch-assemble\n# Briefing\n## 5. Knowledge clusters\n"
            completed = type("Completed", (), {"stdout": raw})()
            with mock.patch("subprocess.run", return_value=completed) as run, \
                    mock.patch.dict(namespace, {"_active_edge_group": lambda: "hive"}):
                payload = namespace["assemble_preflight"](
                    user_message="/Steve-assemble", session_id="sid")
            context = payload["context"]
            self.assertIn("EOC ASSEMBLE PREFLIGHT", context)
            self.assertIn("Recap", context)
            self.assertIn("Dig sources actually used", context)
            self.assertIn("DISPATCH_ID=dispatch-assemble", context)
            self.assertLess(len(context.encode()), 4_500)
            cache = edge / "state" / "live" / "hermes-preflight" / "sid-assemble.md"
            self.assertTrue(cache.is_file())
            self.assertIn("## 5. Knowledge clusters", cache.read_text())
            self.assertEqual(run.call_args.args[0][-2:], ["--origin", "user_requested"])
            self.assertEqual(run.call_args.kwargs["cwd"], str(edge))
            self.assertIsNone(namespace["assemble_preflight"]("/Steve-assembler", "sid"))

    def test_assemble_preflight_stops_at_next_section_when_recall_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edge = root / "edge"
            plugin = _hermes_provision.install_hermes_plugin({"name": "Steve"}, root / "repo", edge, root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            # Simulate predispatch output WITHOUT a # Recall section
            raw = "DISPATCH_ID=dispatch-no-recall\n# Briefing\n## 5. Knowledge clusters\nclusters here\n# Grounding\n## Per-source yield\nyield data\n"
            completed = type("Completed", (), {"stdout": raw})()
            with mock.patch("subprocess.run", return_value=completed) as run, \
                    mock.patch.dict(namespace, {"_active_edge_group": lambda: "hive"}):
                payload = namespace["assemble_preflight"](
                    user_message="/Steve-assemble", session_id="norecall")
            context = payload["context"]
            self.assertIn("EOC ASSEMBLE PREFLIGHT", context)
            self.assertIn("DISPATCH_ID=dispatch-no-recall", context)
            # The cache should contain briefing but NOT grounding
            cache = edge / "state" / "live" / "hermes-preflight" / "norecall-assemble.md"
            self.assertTrue(cache.is_file())
            cached = cache.read_text()
            self.assertIn("## 5. Knowledge clusters", cached)
            self.assertNotIn("# Grounding", cached)
            self.assertNotIn("Per-source yield", cached)

    def test_producer_preflight_injects_rito_contract_and_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edge = root / "edge"
            plugin = _hermes_provision.install_hermes_plugin({"name": "Steve"}, root / "repo", edge, root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            raw = "DISPATCH_ID=dispatch-producer\n# Briefing\n## 5. Knowledge clusters\n# Recall\nrecall brief\n"
            completed = type("Completed", (), {"stdout": raw, "returncode": 0, "stderr": ""})()
            direction = edge / "state" / "direction.md"
            direction.parent.mkdir(parents=True, exist_ok=True)
            direction.write_text("# Direction\nactive goal: test\n")
            with mock.patch("subprocess.run", return_value=completed) as run, \
                    mock.patch.dict(namespace, {"_active_edge_group": lambda: "hive"}):
                payload = namespace["producer_preflight"](
                    user_message="/Steve-research", session_id="prod-sid")
            context = payload["context"]
            self.assertIn("[EoC producer=research preflight]", context)
            self.assertIn("DISPATCH_ID=dispatch-producer", context)
            self.assertIn("rito.run_rito", context)
            self.assertIn("publisher.publish_rito", context)
            self.assertIn("blog/entries", context)
            self.assertIn("ACCEPTANCE: PASS|FAIL", context)
            self.assertIn("resume=False", context)
            self.assertIn("WIPE state/rito/", context)
            self.assertIn("real LLM transport", context)
            # close.run_close is mentioned only as forbidden path, not as the contract
            self.assertIn("Do NOT call close.run_close", context)
            self.assertNotIn("close.run_close(artefato", context)
            self.assertLess(len(context.encode()), 4_500)
            cache = edge / "state" / "live" / "hermes-preflight" / "prod-sid-producer-research.md"
            self.assertTrue(cache.is_file())
            cached = cache.read_text()
            self.assertIn("# Direction", cached)
            self.assertIn("DISPATCH_ID=dispatch-producer", cached)
            cmd = run.call_args.args[0]
            self.assertIn("--origin", cmd)
            self.assertEqual(cmd[cmd.index("--origin") + 1], "user_requested")
            self.assertNotIn("--group", cmd)
            self.assertEqual(run.call_args.kwargs["env"]["EDGE_GROUP"], "hive")
            self.assertIsNone(namespace["producer_preflight"]("/Steve-mentor", "prod-sid"))

    def test_producer_preflight_matches_expanded_current_user_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            edge = root / "edge"
            plugin = _hermes_provision.install_hermes_plugin(
                {"name": "Steve"}, root / "repo", edge, root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            raw = "DISPATCH_ID=desktop-dispatch\n# Briefing\n## Current\n# Recall\nold\n"
            completed = type(
                "Completed", (), {"stdout": raw, "returncode": 0, "stderr": ""})()
            direction = edge / "state" / "direction.md"
            direction.parent.mkdir(parents=True, exist_ok=True)
            direction.write_text("# Direction\n")
            expanded = (
                '[IMPORTANT: The user has invoked the "Steve-research" skill, '
                'indicating this workflow must be followed.]\nTopic: short test'
            )
            history = [{"role": "user", "content": expanded}]
            with mock.patch("subprocess.run", return_value=completed), \
                    mock.patch.dict(namespace, {"_active_edge_group": lambda: "hive"}):
                payload = namespace["producer_preflight"](
                    user_message="Topic: short test",
                    session_id="desktop-sid",
                    conversation_history=history,
                )
            self.assertIn("[EoC producer=research preflight]", payload["context"])
            self.assertTrue((edge / "state" / "live" / "hermes-preflight" /
                             "desktop-sid-producer-research.md").is_file())
            trace_path = edge / "state" / "live" / "hermes-preflight" / "hook-trace.jsonl"
            trace = trace_path.read_text()
            self.assertIn('"matched": "research"', trace)
            self.assertIn('"current_has_important": true', trace)
            self.assertNotIn("desktop-sid", trace)
            self.assertNotIn("Topic: short test", trace)
            self.assertEqual(trace_path.stat().st_mode & 0o777, 0o600)

    def test_current_turn_match_does_not_retrigger_old_history_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin(
                {"name": "Steve"}, root / "repo", root / "edge", root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            history = [
                {"role": "user", "content": '[IMPORTANT: The user has invoked the "Steve-research" skill, indicating ...]'},
                {"role": "assistant", "content": "prior response"},
                {"role": "user", "content": "ordinary follow-up"},
            ]
            self.assertFalse(namespace["_current_turn_invokes"](
                "ordinary follow-up", history, "research"))

    def test_current_turn_match_does_not_retrigger_when_current_turn_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin(
                {"name": "Steve"}, root / "repo", root / "edge", root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            history = [
                {"role": "user", "content": '[IMPORTANT: The user has invoked the "Steve-research" skill, indicating ...]'},
                {"role": "assistant", "content": "prior response"},
            ]
            self.assertFalse(namespace["_current_turn_invokes"](
                "ordinary follow-up", history, "research"))

    def test_current_turn_match_supports_multimodal_user_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin(
                {"name": "Steve"}, root / "repo", root / "edge", root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            user_message = [{"type": "input_text", "text": "analyze this"}]
            history = [{"role": "user", "content": [
                {"type": "input_text", "text": '[IMPORTANT: The user has invoked the "Steve-research" skill, indicating ...]\nanalyze this'},
                {"type": "image_url", "image_url": "https://example.invalid/image.png"},
            ]}]
            self.assertTrue(namespace["_current_turn_invokes"](
                user_message, history, "research"))

    def test_delta_preflight_injects_world_only_roster_without_running_world_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            edge = root / "edge"
            (repo / ".claude" / "agents").mkdir(parents=True)
            (repo / ".claude" / "agents" / "explorer.md").write_text("WORLD only")
            plugin = _hermes_provision.install_hermes_plugin({"name": "Steve"}, repo, edge, root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            roadmap = edge / "state" / "source-roadmap.md"
            roster = [{"name": "github", "kind": "cli", "interfaces": [{"interface_id": "gh", "via": "gh"}]}]
            with mock.patch.object(namespace["sources"], "render_source_roadmap", return_value=roadmap), \
                    mock.patch.object(namespace["sources"], "load_sources", return_value=(roster, [])):
                payload = namespace["delta_preflight"]("/Steve-delta", "sid")
            context = payload["context"]
            self.assertIn("EOC DELTA PREFLIGHT", context)
            self.assertIn("WORLD only", context)
            self.assertIn("delegate_task", context)
            self.assertIn("SOURCE_ROSTER=", context)
            self.assertIn("orientation, not evidence", context)
            self.assertIsNone(namespace["delta_preflight"]("/Steve-deltaware", "sid"))

    def test_wake_preflight_runs_canonical_driver_and_bounds_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            edge = root / "edge"
            plugin = _hermes_provision.install_hermes_plugin({"name": "Steve"}, repo, edge, root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            raw = (
                "DISPATCH_ID=dispatch-1\n# Briefing\n" + "identity direction\n" * 1000
                + "\n# Recall\n" + "portfolio recent-work\n" * 1000
            )
            completed = type("Completed", (), {"stdout": raw})()
            with mock.patch("subprocess.run", return_value=completed) as run, \
                    mock.patch.dict(namespace, {"_active_edge_group": lambda: "hive"}):
                result = namespace["wake_preflight"](
                    user_message="/Steve-wake", session_id="20260731_133507_2e3e32")
            command = run.call_args.args[0]
            kwargs = run.call_args.kwargs
            self.assertEqual(command[-2:], ["--origin", "user_requested"])
            self.assertEqual(kwargs["cwd"], str(edge))
            self.assertEqual(kwargs["env"]["EDGE_HOME"], str(edge))
            self.assertEqual(kwargs["env"]["EDGE_GROUP"], "hive")
            self.assertEqual(kwargs["timeout"], 180)
            context = result["context"]
            self.assertLess(len(context.encode()), 15_000)
            self.assertGreaterEqual(context.count("DISPATCH_ID=dispatch-1"), 2)
            self.assertIn("[BRIEFING PROJECTION]", context)
            self.assertIn("[RECALL PROJECTION]", context)

    def test_wake_preflight_fails_closed_without_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin(
                {"name": "Steve"}, root / "repo", root / "edge", root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            completed = type("Completed", (), {"stdout": "DISPATCH_ID=dispatch-1\nbriefing"})()
            release = mock.Mock()
            with mock.patch("subprocess.run", return_value=completed), \
                    mock.patch.dict(namespace, {
                        "_active_edge_group": lambda: "hive",
                        "mark_session_inactive": release,
                    }):
                with self.assertRaisesRegex(RuntimeError, "missing DISPATCH_ID or Recall"):
                    namespace["wake_preflight"](
                        user_message="/Steve-wake", session_id="20260731_133507_2e3e32")
            release.assert_called_once_with(session_id="20260731_133507_2e3e32")

    def test_preflight_command_detection_respects_command_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin(
                {"name": "Steve"}, root / "repo", root / "edge", root)
            namespace = {"__name__": "generated_eoc_plugin"}
            exec((plugin / "__init__.py").read_text(), namespace)
            inv = namespace["_invokes"]
            self.assertTrue(inv("/Steve-wake", "wake"))
            self.assertTrue(inv("/Steve-wake now", "wake"))
            self.assertFalse(inv("/Steve-wake-anything", "wake"))
            self.assertFalse(inv("prefix /Steve-wake", "wake"))
            # Desktop skill invoke: comma after "skill", not space/newline
            desktop = (
                '[IMPORTANT: The user has invoked the "Steve-research" skill, '
                "indicating they want you to follow its instructions. "
                "The full skill content is loaded below.]\n\n---\nname: Steve-research"
            )
            self.assertTrue(inv(desktop, "research"))
            self.assertFalse(inv(desktop, "wake"))
            # Compaction can embed the IMPORTANT block mid-message
            compacted = (
                "[CONTEXT COMPACTION — REFERENCE ONLY]\n"
                "Historical snapshot...\n"
                + desktop
            )
            self.assertTrue(inv(compacted, "research"))
            # Edge wrapper prefix form
            self.assertTrue(
                inv("Steve-research: Edge `research` skill (`/Steve-research`).", "research")
            )

    def test_provisions_prefixed_wrappers_under_hermes_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "skills" / "wake").mkdir(parents=True)
            (repo / "skills" / "wake" / "SKILL.md").write_text("---\nname: wake\n---\nx")
            (repo / "skills" / "_shared").mkdir()
            (repo / "skills" / "_shared" / "pipeline.md").write_text("y")
            edge_home = root / "home"
            hermes_home = root / ".hermes"
            hermes_home.mkdir()
            (hermes_home / "config.yaml").write_text("edge_group: ''\n")
            cfg = {"skill_prefix": "Steve", "tool_prefix": "edge"}
            legacy = hermes_home / "skills" / "edge-wake"
            legacy.mkdir(parents=True)
            installed_skill = edge_home / "skills" / "wake" / "SKILL.md"
            installed_skill.parent.mkdir(parents=True)
            installed_skill.write_text("canonical installed copy")
            (legacy / "SKILL.md").write_text(_hermes_provision.render_hermes_skill(
                "wake", "edge", installed_skill))
            foreign = hermes_home / "skills" / "edge-foreign"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("third-party skill")
            _hermes_provision.provision_hermes(cfg, repo, edge_home, hermes_home)
            _hermes_provision.reconcile_hermes_profiles(cfg, repo, edge_home, hermes_home)
            self.assertTrue(
                (hermes_home / "skills" / "Steve-wake" / "SKILL.md").is_file())
            self.assertFalse((hermes_home / "skills" / "edge-wake").exists())
            self.assertTrue(foreign.exists())
            # _shared não vira wrapper
            self.assertFalse((hermes_home / "skills" / "Steve-_shared").exists())


class SurfaceDetection(unittest.TestCase):
    def test_hermes_detected_by_home_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".hermes").mkdir()
            out = surfaces_cfg.detect_installed_surfaces(env={}, home=home)
            self.assertTrue(out["hermes"])
            self.assertFalse(out["grok"])

    def test_hermes_home_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            alt = Path(tmp) / "alt-hermes"
            alt.mkdir()
            out = surfaces_cfg.detect_installed_surfaces(
                env={"HERMES_HOME": str(alt)}, home=Path(tmp))
            self.assertTrue(out["hermes"])

    def test_installed_hermes_enters_the_surfaces_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".hermes").mkdir()
            block = surfaces_cfg.surfaces_block_for_installed(env={}, home=home)
            self.assertEqual(block["hermes"], {"enabled": True, "home": "~/.hermes"})


    def test_dig_preflight_materializes_plan_and_injects_protocol_context(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = Path(td) / "repo"
            edge_home = Path(td) / "edge"
            (repo / "skills").mkdir(parents=True)
            (repo / ".claude" / "agents").mkdir(parents=True)
            (repo / ".claude" / "agents" / "explorer.md").write_text(
                "---\nname: explorer\ndisallowedTools: mcp__cortex__*\n---\nRead the WORLD only.\n"
            )
            (edge_home / "state").mkdir(parents=True)
            plugin = root / "plugins" / "edge-of-chaos" / "__init__.py"
            _hermes_provision.install_hermes_plugin({"name": "Steve", "graph_group": "default"}, repo, edge_home, root)
            namespace = {"__file__": str(plugin)}
            exec(compile(plugin.read_text(), str(plugin), "exec"), namespace)
            completed = mock.Mock(stdout="BRIEFING\n", stderr="", returncode=0)
            roadmap = edge_home / "state" / "source-roadmap.md"
            roadmap.parent.mkdir(parents=True, exist_ok=True)
            roadmap.write_text("# Source Roadmap\n\n## github — cli\n")
            roster = [{"name": "github", "kind": "cli", "interfaces": [{"interface_id": "gh-cli", "via": "gh search"}]}]
            with mock.patch("subprocess.run", return_value=completed) as run, \
                    mock.patch.object(namespace["sources"], "render_source_roadmap", return_value=roadmap), \
                    mock.patch.object(namespace["sources"], "load_sources", return_value=(roster, [])), \
                    mock.patch.dict(namespace, {"_active_edge_group": lambda: "hive"}):
                payload = namespace["dig_preflight"]("/Steve-dig", "sid")
            ctx = payload["context"]
            self.assertIn("DIG PREFLIGHT READY", ctx)
            self.assertIn("delegate_task", ctx)
            self.assertIn("PRISMA", ctx)
            self.assertIn("explorer_contract", ctx)
            self.assertIn("source.signal", ctx)
            self.assertIn("memory_index", ctx)
            self.assertIn("event_log", ctx)
            self.assertIn("SOURCE_ROSTER=", ctx)
            self.assertIn("do not call skill_view", ctx)
            self.assertEqual(run.call_args.kwargs["cwd"], str(edge_home))
            self.assertEqual(run.call_args.kwargs["env"]["EDGE_GROUP"], "hive")
            self.assertEqual(run.call_args.kwargs["timeout"], 180)
            self.assertIsNone(namespace["dig_preflight"]("/Steve-digest", "sid"))


if __name__ == "__main__":
    unittest.main()

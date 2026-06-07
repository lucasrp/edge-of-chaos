"""_identity — derive install identity from agent.yaml, never from a baked-in literal (#21).

agent.yaml is the SOLE identity source. The genotype carries no install literal: the graph
group, the edge_home paths, and the Neo4j password are all derived here. Two postures, matching
briefing.py (the operator's existing approach):

  - RUNTIME degrades on a missing value — `os.environ.get(...)` with NO literal default; a tool
    that can't resolve its group/password just darkens the graph leg (like briefing.graph_clusters
    returning None when EDGE_GROUP is unset). The beat never crashes on a missing identity.
  - INSTALL fails loud — `require_group` / `require_neo4j_password` raise, naming the gap, so
    edge-apply provisions a real identity rather than silently writing into a cross-tenant group.

Group precedence: EDGE_GROUP env (host override) → agent.yaml name/codename. No baked-in group
default (the cross-tenant bug, #21). Password: EDGE_NEO4J_PASSWORD env → the install's generated
secret; no literal default (CONTRACT C4)."""
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENT_YAML = REPO / "agent.yaml"


def _cfg(agent_yaml=AGENT_YAML):
    import yaml
    p = Path(agent_yaml)
    return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}


def group(agent_yaml=AGENT_YAML):
    """The graph group for THIS install. EDGE_GROUP (host override) → agent.yaml name/codename.
    Returns None when nothing resolves — the runtime degrade posture (no cross-tenant default)."""
    g = os.environ.get("EDGE_GROUP")
    if g:
        return g
    cfg = _cfg(agent_yaml)
    return cfg.get("name") or cfg.get("codename") or None


def require_group(agent_yaml=AGENT_YAML):
    """Install posture: the group MUST resolve, or fail loud (no silent cross-tenant write)."""
    g = group(agent_yaml)
    if not g:
        raise RuntimeError(
            "no graph group: set EDGE_GROUP or agent.yaml `name`/`codename` "
            "(the genotype carries no identity default — would mix tenants)")
    return g


def edge_home(cfg=None, agent_yaml=AGENT_YAML):
    """The install root for THIS host, from agent.yaml `edge_home` (no baked-in path literal)."""
    cfg = _cfg(agent_yaml) if cfg is None else cfg
    home = cfg.get("edge_home")
    if not home:
        raise RuntimeError("agent.yaml declares no `edge_home` (the install root)")
    return Path(os.path.expanduser(str(home)))


def neo4j_password():
    """The Neo4j password for THIS host. EDGE_NEO4J_PASSWORD env (the install's generated secret)
    → None. No literal default (CONTRACT C4): a missing password degrades the graph at runtime
    and fails loud at install (require_neo4j_password)."""
    return os.environ.get("EDGE_NEO4J_PASSWORD") or None


def require_neo4j_password():
    """Install posture: the Neo4j password MUST be present, or fail loud (no literal default)."""
    pw = neo4j_password()
    if not pw:
        raise RuntimeError(
            "no EDGE_NEO4J_PASSWORD: the per-host Neo4j secret is unset "
            "(the genotype ships no default password — CONTRACT C4)")
    return pw


def neo4j_conn():
    """(uri, user, password) for the local graph — password from the env secret (no literal)."""
    return (os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687"),
            os.environ.get("EDGE_NEO4J_USER", "neo4j"),
            neo4j_password())

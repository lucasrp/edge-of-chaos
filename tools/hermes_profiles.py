"""Resolve Edge membership for Hermes profiles without changing other surfaces."""
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Membership:
    profile_name: str
    enabled: bool
    edge_group: str | None


def _yaml(path):
    try:
        value = yaml.safe_load(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def membership(hermes_home, profile_name):
    """Resolve global default + profile override; blank means profile-local."""
    root = Path(hermes_home)
    global_cfg = _yaml(root / "config.yaml")
    local_path = root / "profiles" / profile_name / "config.yaml"
    local_cfg = _yaml(local_path) if profile_name != "default" else {}
    source = local_cfg if "edge_group" in local_cfg else global_cfg
    if "edge_group" not in source:
        return Membership(profile_name, False, None)
    value = source["edge_group"]
    if value is None or (isinstance(value, str) and not value.strip()):
        return Membership(profile_name, True, profile_name)
    if not isinstance(value, str):
        raise ValueError(f"edge_group for Hermes profile {profile_name!r} must be a string or blank")
    return Membership(profile_name, True, value.strip())

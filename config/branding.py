"""Shared branding loader — genotype reads phenotype from here."""

import os
from pathlib import Path

_BRANDING_CACHE = None

_DEFAULTS = {
    "agent_name": "agent",
    "org_name": "",
    "org_short": "",
    "logo_filename": "",
    "css_var_prefix": "brand",
    "colors": {
        "primary": "#2b6cb0",
        "green": "#38a169",
        "yellow": "#ed8936",
        "web_blue": "#2b6cb0",
        "web_blue_dark": "#1a365d",
        "logo_blue": "#2b6cb0",
    },
    "blog": {
        "port": 8766,
        "host": "127.0.0.1",
        "auth_enabled": False,
        "auth_user": "",
        "auth_pass": "",
    },
    "memory_project_dir": "",
    "skill_prefix": "agent",
}


def load_branding(config_path=None):
    """Load branding config. Caches after first call."""
    global _BRANDING_CACHE
    if _BRANDING_CACHE is not None:
        return _BRANDING_CACHE

    if config_path is None:
        config_path = Path(os.environ.get(
            "BRANDING_CONFIG",
            Path.home() / "edge" / "config" / "branding.yaml"
        ))
    else:
        config_path = Path(config_path)

    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            # Merge with defaults (shallow for top-level, deep for dicts)
            result = dict(_DEFAULTS)
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(result.get(k), dict):
                    result[k] = {**result[k], **v}
                else:
                    result[k] = v
            _BRANDING_CACHE = result
            return result
        except Exception:
            pass

    _BRANDING_CACHE = dict(_DEFAULTS)
    return _BRANDING_CACHE

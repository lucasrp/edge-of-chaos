"""_secrets — load an install's secrets/*.env into the process environment.

The install WRITES per-host secrets into env_dir (neo4j.env #22 + the operator's delivered api keys);
the runtime must LOAD them, or every secret-bearing tool darkens — exactly how the graph went dark:
EDGE_NEO4J_PASSWORD sat in secrets/neo4j.env but never reached os.environ. This sources every *.env in
env_dir. An env var ALREADY SET WINS (an explicit override is never clobbered); no baked-in values (C4).
Supersedes the ad-hoc per-tool OPENAI_API_KEY loading (wiki_render / sweep) with one mechanism.
"""
import os
from pathlib import Path


def load_env(env_dir, overwrite=False):
    """Source KEY=value lines from every <env_dir>/*.env into os.environ. Returns the keys set.
    Skips blanks/comments, strips an `export ` prefix and surrounding quotes. Missing dir → no-op."""
    env_dir = Path(env_dir)
    loaded = []
    if not env_dir.is_dir():
        return loaded
    for f in sorted(env_dir.glob("*.env")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and (overwrite or k not in os.environ):
                os.environ[k] = v
                loaded.append(k)
    return loaded

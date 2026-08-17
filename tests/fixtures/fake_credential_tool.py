#!/usr/bin/env python3
"""Separate fake tool: report path readability only, never file content."""
import json
from pathlib import Path
import sys


path = Path(sys.argv[1])
readable = False
try:
    with path.open("rb") as stream:
        stream.read(1)
    readable = True
except OSError:
    pass
print(json.dumps({"tool_rereadable": readable, "tool_process": True}, sort_keys=True))

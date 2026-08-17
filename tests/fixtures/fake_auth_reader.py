#!/usr/bin/env python3
"""Readability probe for a synthetic file; never returns file content."""
import json
from pathlib import Path
import sys


path = Path(sys.argv[1])
expected = sys.argv[2].encode()
try:
    value = path.read_bytes()
    readable = True
    matched = value == expected
except (OSError, PermissionError):
    readable = False
    matched = False
print(json.dumps({
    "readable": readable,
    "matched_expected_synthetic_value": matched,
    "content_returned": False,
}), flush=True)

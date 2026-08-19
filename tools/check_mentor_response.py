#!/usr/bin/env python3
import json
import re
import sys

text = open(sys.argv[1]).read().lower()
payload = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None
front_lines = [line for line in text.splitlines() if ("->" in line or "→" in line)]
community_names = [item["name"].lower() for item in payload.get("communities", [])] if payload else []
session_ids = [item["session_id"].lower() for item in payload.get("recent_hermes_work", [])] if payload else []
front_section = text.split("## frentes comparadas", 1)[-1].split("\n## ", 1)[0] if "## frentes comparadas" in text else ""
front_bullets = [line for line in front_section.splitlines() if line.lstrip().startswith(("-", "*"))]
checks = {
    "three_work_fronts": (len({sid for sid in session_ids if sid in text}) >= 3
                          or len(front_lines) >= 3 or len(front_bullets) >= 3),
    "leveling": any(term in text for term in ("level", "nível", "estágio", "stage")),
    "cortex_community": any(name in text for name in community_names),
    "cross_front_pattern": "padrão" in text or "pattern" in text,
    "priority": "prioridade" in text or "priority" in text,
    "next_step": any(term in text for term in ("próximo passo", "next step", "agora:", "ação concreta", "ação imediata", "intervenção executável")),
    "not_generic_question": not text.rstrip().endswith("?"),
}
print(json.dumps(checks, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)

#!/bin/bash
# capture-diffs.sh -- Capture diffs from autonomy persistence files and post to blog API
#
# Usage: capture-diffs.sh <slug>
#   slug: the blog entry slug to associate diffs with
#
# Tracked directories (git repos):
#   ~/.claude/projects/memory/     (working-state, breaks, proposals, etc.)
#   ~/.claude/skills/              (SKILL.md files)
#   ~/edge/notes/             (research notes)

SLUG="${1:-}"
if [ -z "$SLUG" ]; then
  echo "Usage: $0 <slug>"
  exit 1
fi

# Use Python for all diff processing (bash is unreliable with special chars in diffs)
export CAPTURE_SLUG="$SLUG"
python3 << 'PYEOF'
import subprocess, json, os, sys

slug = os.environ.get("CAPTURE_SLUG", "")

# NOTE: Adjust these paths to match your project structure
TRACKED = {
    os.path.expanduser("~/.claude/projects/memory"): "memory",
    os.path.expanduser("~/.claude/skills"): "skills",
    os.path.expanduser("~/edge/notes"): "notes",
    os.path.expanduser("~/edge/autonomy"): "autonomy",
}

BLOG_API = "http://localhost:8766/api/diffs"
all_diffs = []

for dirpath, prefix in TRACKED.items():
    git_dir = os.path.join(dirpath, ".git")
    if not os.path.isdir(git_dir):
        continue

    # Stage all changes
    subprocess.run(["git", "add", "-A"], cwd=dirpath, capture_output=True)

    # Get staged diff
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=3"],
        cwd=dirpath, capture_output=True, text=True
    )
    diff_output = result.stdout.strip()
    if not diff_output:
        continue

    # Split by file
    current_file = None
    current_lines = []

    for line in diff_output.split("\n"):
        if line.startswith("diff --git a/"):
            # Save previous
            if current_file and current_lines:
                all_diffs.append({
                    "path": f"{prefix}/{current_file}",
                    "diff": "\n".join(current_lines)
                })
            # Extract filename: "diff --git a/foo.md b/foo.md"
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) > 1 else line.split("a/", 1)[-1].split(" ")[0]
            current_lines = [line]
        else:
            current_lines.append(line)

    # Last file
    if current_file and current_lines:
        all_diffs.append({
            "path": f"{prefix}/{current_file}",
            "diff": "\n".join(current_lines)
        })

    # Commit as new baseline
    subprocess.run(
        ["git", "commit", "-m", f"auto: captured for blog entry {slug}"],
        cwd=dirpath, capture_output=True
    )

if not all_diffs:
    print("No changes detected in tracked directories")
    sys.exit(0)

# Post to blog API
import urllib.request

payload = json.dumps({"slug": slug, "files": all_diffs}).encode("utf-8")
try:
    req = urllib.request.Request(
        BLOG_API,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        response = resp.read().decode("utf-8")
except Exception as e:
    response = json.dumps({"error": str(e)})

print(f"Captured {len(all_diffs)} file diffs for entry: {slug}")
for d in all_diffs:
    lines = d["diff"].split("\n")
    adds = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    print(f"  {d['path']}: +{adds} -{dels}")
print(f"API response: {response}")
PYEOF

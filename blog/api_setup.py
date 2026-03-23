"""Setup API — endpoints for the setup tab."""

import json
import os
import re
import shutil
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, render_template, request

from blog.setup_examples import EDITABLE_FILES, SYSTEM_FILES, GROUP_ORDER

setup_bp = Blueprint("setup", __name__)

# ─── Paths ───────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent  # edge dir


def _resolve_path(rel_path: str) -> Path:
    """Resolve a relative path to absolute, handling edge dir."""
    return ROOT / rel_path


def _read_file(path: Path) -> str | None:
    """Read file content, return None if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return None


def _detect_status(content: str | None) -> str:
    """Detect file status from content."""
    if content is None:
        return "missing"
    if not content.strip():
        return "empty"
    if "{{" in content or "PLACEHOLDER" in content:
        return "placeholder"
    return "configured"


def _dir_info(path: Path) -> dict:
    """Get info about a directory (count + recent files)."""
    if not path.is_dir():
        return {"count": 0, "recent": [], "exists": False}
    try:
        files = sorted(path.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
        files = [f for f in files if f.is_file() and not f.name.startswith(".")]
        return {
            "count": len(files),
            "recent": [f.name for f in files[:5]],
            "exists": True,
        }
    except OSError:
        return {"count": 0, "recent": [], "exists": False}


def _secrets_status() -> dict:
    """Check which secrets are configured (present/missing) without exposing values."""
    secrets_file = ROOT / "secrets" / "_shared.yaml"
    if not secrets_file.exists():
        return {"_file_exists": False}

    try:
        with open(secrets_file) as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {"_file_exists": False}

    result = {"_file_exists": True}

    # Flatten nested YAML to check each key
    def _check(obj, prefix=""):
        if not isinstance(obj, dict):
            return
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            full_key = f"{prefix}{k}" if prefix else k
            if isinstance(v, dict):
                # Check if it has an api_key or token field
                for secret_field in ("api_key", "bot_token", "app_token",
                                     "webhook_url", "personal_access_token",
                                     "secret_key", "publishable_key",
                                     "webhook_secret", "api_token", "chat_id"):
                    if secret_field in v:
                        val = v[secret_field]
                        result[f"{full_key}.{secret_field}"] = "configured" if val else "missing"
                _check(v, f"{full_key}.")
            elif isinstance(v, str) and any(
                kw in k for kw in ("key", "token", "secret", "pass", "url")
            ):
                result[full_key] = "configured" if v else "missing"

    _check(data)
    return result


# ─── Allowed editable paths (security) ───────────────────────────────────────

EDITABLE_PATHS = {f["path"] for f in EDITABLE_FILES}


# ─── Routes ──────────────────────────────────────────────────────────────────

@setup_bp.route("/api/setup/files")
def setup_files():
    """Return all files grouped, with content and status."""
    groups = {}

    # Editable files
    for f in EDITABLE_FILES:
        path = _resolve_path(f["path"])
        content = _read_file(path)
        status = _detect_status(content)

        group_key = f["group"]
        if group_key not in groups:
            groups[group_key] = {
                "label": f["group_label"],
                "editable": True,
                "files": [],
            }

        groups[group_key]["files"].append({
            "path": f["path"],
            "purpose": f["purpose"],
            "owner": f["owner"],
            "status": status,
            "editable": True,
            "content": content or "",
            "example": f.get("example", ""),
        })

    # System files
    for f in SYSTEM_FILES:
        path = _resolve_path(f["path"])
        is_dir = f.get("is_dir", False)

        group_key = f["group"]
        if group_key not in groups:
            groups[group_key] = {
                "label": f["group_label"],
                "editable": False,
                "files": [],
            }

        entry = {
            "path": f["path"],
            "purpose": f["purpose"],
            "owner": f["owner"],
            "managed_by": f.get("managed_by", ""),
            "editable": False,
            "is_dir": is_dir,
        }

        if is_dir:
            entry["dir_info"] = _dir_info(path)
            entry["status"] = "configured" if entry["dir_info"]["exists"] else "missing"
        else:
            content = _read_file(path)
            entry["content"] = content or ""
            entry["status"] = _detect_status(content)

        groups[group_key]["files"].append(entry)

    # Order groups
    ordered = []
    for key, label, editable in GROUP_ORDER:
        if key in groups:
            ordered.append({"key": key, **groups[key]})

    return jsonify({"groups": ordered})


@setup_bp.route("/api/setup/save", methods=["POST"])
def setup_save():
    """Save an editable file. Rejects read-only files."""
    data = request.get_json()
    if not data or "path" not in data or "content" not in data:
        return jsonify({"error": "Missing path or content"}), 400

    rel_path = data["path"]

    if rel_path not in EDITABLE_PATHS:
        return jsonify({"error": f"File '{rel_path}' is read-only (system-managed)"}), 403

    path = _resolve_path(rel_path)

    # Backup before saving
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)

    # Ensure parent dir exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write
    path.write_text(data["content"], encoding="utf-8")

    return jsonify({"ok": True, "path": rel_path, "status": _detect_status(data["content"])})


@setup_bp.route("/api/setup/secrets-status")
def secrets_status():
    """Return status of each secret (configured/missing) without exposing values."""
    return jsonify(_secrets_status())

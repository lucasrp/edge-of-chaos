from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any


class LLMClient:
    def __init__(self, *, role: str = "default") -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        role_key = "EDGE_MODEL_" + re.sub(r"[^A-Z0-9]+", "_", role.upper()).strip("_")
        self.model = (
            os.environ.get(role_key)
            or os.environ.get("OPENAI_MODEL")
            or os.environ.get("EDGE_OPENAI_MODEL")
            or ""
        )
        if self.base_url.rstrip("/") == "https://api.openai.com/v1" and self.model.startswith("gpt_"):
            self.model = self.model.replace("gpt_", "gpt-", 1).replace("_", ".")
        self.last_provider = "none"
        self.last_error = ""

    def available(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, *, system: str, prompt: str) -> dict[str, Any] | None:
        if not self.available():
            return self._complete_claude_json(system=system, prompt=prompt)
        if not self.model:
            self.last_error = "openai:model-not-configured"
            return self._complete_claude_json(system=system, prompt=prompt)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.last_error = self._http_error(exc)
            return self._complete_claude_json(system=system, prompt=prompt)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.last_error = f"openai:{type(exc).__name__}"
            return self._complete_claude_json(system=system, prompt=prompt)
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        parsed = self._parse_json_object(content)
        if parsed is not None:
            self.last_provider = f"openai:{self.model}"
            self.last_error = ""
            return parsed
        self.last_error = "openai:invalid-json"
        return self._complete_claude_json(system=system, prompt=prompt)

    def complete_text(self, *, system: str, prompt: str) -> str | None:
        if not self.available():
            return self._complete_claude_text(system=system, prompt=prompt)
        if not self.model:
            self.last_error = "openai:model-not-configured"
            return self._complete_claude_text(system=system, prompt=prompt)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.last_error = self._http_error(exc)
            return self._complete_claude_text(system=system, prompt=prompt)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            self.last_error = f"openai:{type(exc).__name__}"
            return self._complete_claude_text(system=system, prompt=prompt)
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if content:
            self.last_provider = f"openai:{self.model}"
            self.last_error = ""
            return content
        self.last_error = "openai:empty-response"
        return content or self._complete_claude_text(system=system, prompt=prompt)

    def _complete_claude_json(self, *, system: str, prompt: str) -> dict[str, Any] | None:
        text = self._complete_claude_text(
            system=system + "\nReturn only one valid JSON object. No Markdown fences.",
            prompt=prompt,
        )
        if not text:
            return None
        return self._parse_json_object(text)

    def _complete_claude_text(self, *, system: str, prompt: str) -> str | None:
        if os.environ.get("EDGE_DISABLE_CLAUDE_FALLBACK") == "1":
            self.last_error = self.last_error or "claude:disabled"
            return None
        claude = shutil.which("claude")
        if not claude:
            self.last_error = self.last_error or "claude:not-found"
            return None
        full_prompt = f"{system}\n\n{prompt}"
        try:
            result = subprocess.run(
                [claude, "-p", full_prompt, "--max-turns", "1"],
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("EDGE_CLAUDE_TIMEOUT_SEC", "120")),
            )
        except subprocess.TimeoutExpired:
            self.last_error = "claude:timeout"
            return None
        except OSError as exc:
            self.last_error = f"claude:{type(exc).__name__}"
            return None
        if result.returncode != 0:
            self.last_error = f"claude:exit-{result.returncode}"
            return None
        self.last_provider = "claude-cli"
        return (result.stdout or "").strip() or None

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> str:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except OSError:
            body = ""
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return f"openai:http-{exc.code}"
        error = payload.get("error") if isinstance(payload, dict) else {}
        if not isinstance(error, dict):
            return f"openai:http-{exc.code}"
        code = str(error.get("code") or error.get("type") or "").strip()
        return f"openai:http-{exc.code}" + (f":{code}" if code else "")

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.S)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None

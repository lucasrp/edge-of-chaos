"""Adapter LLM mínimo do v0 — openai-compatible (provider+key → cliente) + probe.

provider → base_url (registry). probe() faz uma chamada real mínima e classifica,
tratando a diferença max_tokens (gpt-3.5/4) vs max_completion_tokens (gpt-5/o1/o3).

Issue #55: provider `codex` (assinatura, sem chave de API) completa via `codex exec`
não-interativo; e falha de TRANSPORTE (401/403/429/insufficient_quota/CLI ausente) sobe
como LLMTransportError tipado — o close distingue infra de veredito de conteúdo.
"""
import subprocess
import tempfile
from pathlib import Path

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

# Providers cobrados por ASSINATURA (CLI local, sem secret_ref) — fora do registry de base_url.
SUBSCRIPTION_PROVIDERS = ("codex",)

# Status HTTP que são sempre transporte/bilhetagem/auth — nunca um juízo sobre o conteúdo.
_TRANSPORT_STATUSES = (401, 403, 429)


class LLMTransportError(Exception):
    """Falha de infra do completer (auth/quota/rede/CLI) — NUNCA um veredito de conteúdo.

    O close trata isto como erro de infra visível (sobe + loga), jamais como strike/reprovação
    do revisor; quota morta deixa de ser indistinguível de "o revisor não gostou"."""

    def __init__(self, detail, status=None):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _classify_transport(exc):
    """Erro do SDK openai-compatible → LLMTransportError se for infra; senão None."""
    status = getattr(exc, "status_code", None)
    if status in _TRANSPORT_STATUSES or "insufficient_quota" in str(exc):
        return LLMTransportError(str(exc)[:300], status=status)
    return None


def _codex_exec(prompt: str, model, max_tokens: int) -> str:
    """Uma completion via `codex exec` não-interativo (assinatura; sem chave de API).

    Sandbox read-only + --ephemeral (não persiste sessão) + -o <tmp> (só a mensagem final,
    sem log de agente no stdout). max_tokens não é exposto pelo CLI — fica a cargo do modelo.
    Qualquer falha (binário ausente, não-logado, exit != 0) é TRANSPORTE."""
    with tempfile.NamedTemporaryFile(mode="r", suffix=".codex-out", delete=False) as out:
        out_path = out.name
    try:
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
               "--ephemeral", "-o", out_path]
        if model:
            cmd += ["-m", str(model)]
        cmd.append("-")
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise LLMTransportError(
                f"codex exec exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        return Path(out_path).read_text().strip()
    except FileNotFoundError:
        raise LLMTransportError("codex CLI ausente no host (provider codex requer o binário)")
    except subprocess.TimeoutExpired:
        raise LLMTransportError("codex exec timeout (600s)")
    finally:
        Path(out_path).unlink(missing_ok=True)


class CodexClient:
    """Cliente do provider `codex`: completions pela assinatura via CLI, sem chave.

    `exec_fn(prompt, model, max_tokens) -> str` é o seam injetável (testes offline);
    o real é `_codex_exec`. Não expõe endpoint de embedding (limitação da assinatura)."""

    def __init__(self, exec_fn=None):
        self.exec_fn = exec_fn or _codex_exec


def resolve_base_url(router: dict):
    """base_url explícito vence; senão deriva do provider."""
    return router.get("base_url") or PROVIDER_BASE_URLS.get(router.get("provider"))


def make_client(router: dict, api_key: str):
    if router.get("provider") in SUBSCRIPTION_PROVIDERS:
        return CodexClient()
    from openai import OpenAI
    base = resolve_base_url(router)
    if not base:
        raise ValueError(f"provider sem base_url no registry: {router.get('provider')!r}")
    return OpenAI(base_url=base, api_key=api_key)


def complete(client, model: str, prompt: str, max_tokens: int = 800) -> str:
    """Texto de uma chamada chat. Trata max_completion_tokens (gpt-5) vs max_tokens.

    Falha de infra (auth/quota/CLI) sobe como LLMTransportError; o resto sobe intacto."""
    if isinstance(client, CodexClient):
        return client.exec_fn(prompt, model, max_tokens)
    last = None
    for tok_param in ("max_completion_tokens", "max_tokens"):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                **{tok_param: max_tokens},
            )
            return r.choices[0].message.content or ""
        except LLMTransportError:
            raise
        except Exception as e:
            transport = _classify_transport(e)
            if transport is not None:
                raise transport from e
            last = e
            status = getattr(e, "status_code", None)
            msg = str(e)
            if status == 400 and ("nsupported parameter" in msg or "not supported" in msg):
                continue
            raise
    raise last


def probe(client, model: str, kind: str = "chat") -> dict:
    """Chamada mínima real. Retorna {ok, status, detail}.

    kind="embedding" usa o endpoint de embeddings; senão chat.completions, tentando
    max_completion_tokens (gpt-5/o1/o3) e trocando para max_tokens se rejeitado.
    Erros reais (401/403/429) são reportados direto. No provider codex, chat proba via
    exec mínimo; embedding é sempre não-suportado (assinatura não expõe o endpoint)."""
    if isinstance(client, CodexClient):
        if kind == "embedding":
            return {"ok": False, "status": None,
                    "detail": "codex não expõe endpoint de embedding — rota precisa de chave de API"}
        try:
            client.exec_fn("Responda exatamente: ok", model, 16)
            return {"ok": True, "status": 200, "detail": "OK (codex exec)"}
        except LLMTransportError as e:
            return {"ok": False, "status": e.status, "detail": e.detail[:140]}
    if kind == "embedding":
        try:
            client.embeddings.create(model=model, input="ok")
            return {"ok": True, "status": 200, "detail": "OK (embedding)"}
        except Exception as e:
            return {"ok": False, "status": getattr(e, "status_code", None), "detail": str(e)[:140]}

    last = {"ok": False, "status": None, "detail": "sem tentativa"}
    for tok_param in ("max_completion_tokens", "max_tokens"):
        try:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ok"}],
                **{tok_param: 16},
            )
            return {"ok": True, "status": 200, "detail": f"OK ({tok_param})"}
        except Exception as e:
            status = getattr(e, "status_code", None)
            msg = str(e)
            last = {"ok": False, "status": status, "detail": msg[:140]}
            if status == 400 and ("nsupported parameter" in msg or "not supported" in msg):
                continue  # mismatch de parâmetro de token → tenta o outro
            return last  # erro real (auth/crédito/modelo) → reporta
    return last

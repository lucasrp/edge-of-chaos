"""Adapter LLM mínimo do v0 — openai-compatible (provider+key → cliente) + probe.

provider → base_url (registry). probe() faz uma chamada real mínima e classifica,
tratando a diferença max_tokens (gpt-3.5/4) vs max_completion_tokens (gpt-5/o1/o3).

Issue #55: provider `codex` (assinatura, sem chave de API) completa via `codex exec`
não-interativo; e falha de TRANSPORTE (401/403/429/insufficient_quota/CLI ausente) sobe
como LLMTransportError tipado — o close distingue infra de veredito de conteúdo.
"""
import os
import shutil
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
# O edge é MULTI-CLI: roda no codex, no claude e no grok, cada um pela sua assinatura, sem chave de API.
SUBSCRIPTION_PROVIDERS = ("codex", "claude", "grok", "hermes")

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
    source_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    source_auth = source_home / "auth.json"
    if not source_auth.is_file():
        raise LLMTransportError(
            f"codex CLI sem autenticação legível em {source_auth}"
        )

    # A completion pode ser chamada de dentro do sandbox de outro `codex exec`.  Reusar o
    # CODEX_HOME real nesse caso falha porque o app-server precisa escrever estado efêmero ali.
    # Damos ao filho um home descartável contendo somente auth (0600), sem config/MCP/rules do
    # operador.  O TemporaryDirectory apaga auth + resposta inclusive em erro/timeout.
    with tempfile.TemporaryDirectory(prefix="edge-codex-completer-") as tmp:
        tmp_home = Path(tmp)
        tmp_auth = tmp_home / "auth.json"
        shutil.copyfile(source_auth, tmp_auth)
        tmp_auth.chmod(0o600)
        out_path = tmp_home / "last-message.txt"
        cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only",
               "--ephemeral", "--ignore-user-config", "-o", str(out_path)]
        if model:
            cmd += ["-m", str(model)]
        cmd.append("-")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(tmp_home)
        try:
            r = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, timeout=600, env=env
            )
        except FileNotFoundError:
            raise LLMTransportError("codex CLI ausente no host (provider codex requer o binário)")
        except subprocess.TimeoutExpired:
            raise LLMTransportError("codex exec timeout (600s)")
        if r.returncode != 0:
            raise LLMTransportError(
                f"codex exec exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        return out_path.read_text().strip()


# Instrução de sistema que mantém o -p como completer PURO: o modelo não tem tools
# (--tools ""), mas sem isto ele emite sintaxe de tool-use como TEXTO ao tentar usá-las.
_CLAUDE_COMPLETER_SYSPROMPT = (
    "You are a text-completion endpoint. Return only the completion for the user "
    "content. Never call, describe, or emit tool-use syntax; you have no tools."
)


def _claude_exec(prompt: str, model, max_tokens: int) -> str:
    """Uma completion via `claude -p` (print mode, não-interativo) — o host que roda o
    Claude Code se usa a si mesmo como writer, pela assinatura, sem chave de API.

    `--tools ""` desliga TODAS as tools internas (allowlist vazia do conjunto built-in;
    verificado: nada executa) + `--strict-mcp-config` (sem --mcp-config → ignora todo MCP,
    fechando a fuga por tool de MCP). `--setting-sources ""` não carrega settings do host
    (sem poluição de CLAUDE.md/hooks); `--no-session-persistence` não deixa a completion
    headless suja o session store do host. auth OAuth/keychain fica intacta (ao contrário de
    --bare, que exige ANTHROPIC_API_KEY). Prompt por stdin (robusto p/ prompts de vários KB,
    como o gêmeo codex). max_tokens não é exposto pelo CLI — fica a cargo do modelo.
    Qualquer falha (binário ausente, não-logado, exit != 0) é TRANSPORTE."""
    cmd = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--no-session-persistence",
           "--setting-sources", "", "--append-system-prompt", _CLAUDE_COMPLETER_SYSPROMPT]
    if model:
        cmd += ["--model", str(model)]
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise LLMTransportError("claude CLI ausente no host (provider claude requer o binário)")
    except subprocess.TimeoutExpired:
        raise LLMTransportError("claude -p timeout (600s)")
    if r.returncode != 0:
        raise LLMTransportError(
            f"claude -p exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    return r.stdout.strip()


# Instrução de sistema do grok como completer: mantém o -p como analista PURO que RETORNA TEXTO,
# com o diferencial do provider — acesso NATIVO ao X ligado, para embasar o veredito adversarial.
_GROK_COMPLETER_SYSPROMPT = (
    "You are a text-completion endpoint with LIVE access to X (Twitter) search. Return only the "
    "completion for the user content. When the task asks you to ground a claim, run an X search and "
    "cite the handles/links you used. Never write files or emit tool-use syntax as text."
)


def _grok_exec(prompt: str, model, max_tokens: int) -> str:
    """Uma completion via `grok --prompt-file` (single-turn headless) — assinatura, sem chave de API.

    O diferencial do provider grok: acesso NATIVO ao X (busca ao vivo) fica LIGADO (jamais
    --disable-web-search) — é o que o torna o adversário que embasa o veredito numa busca no X.
    Prompt por arquivo (robusto p/ prompts de vários KB, como o -o do gêmeo codex). max_tokens não é
    exposto pelo CLI — fica a cargo do modelo. Qualquer falha (binário ausente, exit != 0) é TRANSPORTE."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".grok-in", delete=False) as f:
        f.write(prompt)
        in_path = f.name
    try:
        cmd = ["grok", "--always-approve",
               "--system-prompt-override", _GROK_COMPLETER_SYSPROMPT, "--prompt-file", in_path]
        if model:
            cmd += ["-m", str(model)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise LLMTransportError(
                f"grok exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        return r.stdout.strip()
    except FileNotFoundError:
        raise LLMTransportError("grok CLI ausente no host (provider grok requer o binário)")
    except subprocess.TimeoutExpired:
        raise LLMTransportError("grok timeout (900s)")
    finally:
        Path(in_path).unlink(missing_ok=True)


def _hermes_exec(prompt: str, model, max_tokens: int) -> str:
    """Uma completion via `hermes -z` (one-shot: prompt entra, só o texto final sai) —
    assinatura/conta própria do usuário, sem chave nossa. 4ª CLI padrão (2026-07-25).

    Modelo em branco usa o default do `hermes setup` DO USUÁRIO (genérico por construção);
    `-m` só quando a rota declara. Prompt via argv (o CLI não expõe prompt-file; ARG_MAX
    de ~2MB cobre os prompts de review). max_tokens fica a cargo do modelo. Falha
    (binário ausente, exit != 0) é TRANSPORTE."""
    cmd = ["hermes", "-z", prompt]
    if model:
        cmd += ["-m", str(model)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise LLMTransportError(
                f"hermes exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
        return r.stdout.strip()
    except FileNotFoundError:
        raise LLMTransportError("hermes CLI ausente no host (provider hermes requer o binário)")
    except subprocess.TimeoutExpired:
        raise LLMTransportError("hermes timeout (900s)")


class SubscriptionClient:
    """Cliente de provider por ASSINATURA (CLI local, sem chave): completions via
    `exec_fn(prompt, model, max_tokens) -> str`, o seam injetável (testes offline).
    Não expõe endpoint de embedding (limitação da assinatura). `name` rotula o probe."""

    name = "assinatura"
    _default_exec = None

    def __init__(self, exec_fn=None):
        self.exec_fn = exec_fn or type(self)._default_exec


class CodexClient(SubscriptionClient):
    """Provider `codex`: completions pela assinatura via `codex exec`, sem chave."""
    name = "codex"
    _default_exec = staticmethod(_codex_exec)


class ClaudeClient(SubscriptionClient):
    """Provider `claude`: completions pela assinatura via `claude -p`, sem chave."""
    name = "claude"
    _default_exec = staticmethod(_claude_exec)


class GrokClient(SubscriptionClient):
    """Provider `grok`: completions pela assinatura via `grok --prompt-file`, sem chave.
    Acesso NATIVO ao X ligado — o adversário que embasa o veredito numa busca no X."""
    name = "grok"
    _default_exec = staticmethod(_grok_exec)


class HermesClient(SubscriptionClient):
    """Provider `hermes`: completions via `hermes -z` (Nous), conta do próprio usuário.
    Modelo default vem do hermes setup do usuário — nunca hardcoded aqui."""
    name = "hermes"
    _default_exec = staticmethod(_hermes_exec)


def resolve_base_url(router: dict):
    """base_url explícito vence; senão deriva do provider."""
    return router.get("base_url") or PROVIDER_BASE_URLS.get(router.get("provider"))


_SUBSCRIPTION_CLIENTS = {"codex": CodexClient, "claude": ClaudeClient, "grok": GrokClient,
                         "hermes": HermesClient}


def make_client(router: dict, api_key: str):
    provider = router.get("provider")
    if provider in SUBSCRIPTION_PROVIDERS:
        return _SUBSCRIPTION_CLIENTS[provider]()
    from openai import OpenAI
    base = resolve_base_url(router)
    if not base:
        raise ValueError(f"provider sem base_url no registry: {router.get('provider')!r}")
    return OpenAI(base_url=base, api_key=api_key)


def complete(client, model: str, prompt: str, max_tokens: int = 800) -> str:
    """Texto de uma chamada chat. Trata max_completion_tokens (gpt-5) vs max_tokens.

    Falha de infra (auth/quota/CLI) sobe como LLMTransportError; o resto sobe intacto."""
    if isinstance(client, SubscriptionClient):
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
    if isinstance(client, SubscriptionClient):
        if kind == "embedding":
            return {"ok": False, "status": None,
                    "detail": f"{client.name} não expõe endpoint de embedding — rota precisa de chave de API"}
        try:
            client.exec_fn("Responda exatamente: ok", model, 16)
            return {"ok": True, "status": 200, "detail": f"OK ({client.name} exec)"}
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

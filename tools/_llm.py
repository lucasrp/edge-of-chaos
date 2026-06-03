"""Adapter LLM mínimo do v0 — openai-compatible (provider+key → cliente) + probe.

provider → base_url (registry). probe() faz uma chamada real mínima e classifica,
tratando a diferença max_tokens (gpt-3.5/4) vs max_completion_tokens (gpt-5/o1/o3).
"""

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
}


def resolve_base_url(router: dict):
    """base_url explícito vence; senão deriva do provider."""
    return router.get("base_url") or PROVIDER_BASE_URLS.get(router.get("provider"))


def make_client(router: dict, api_key: str):
    from openai import OpenAI
    base = resolve_base_url(router)
    if not base:
        raise ValueError(f"provider sem base_url no registry: {router.get('provider')!r}")
    return OpenAI(base_url=base, api_key=api_key)


def probe(client, model: str, kind: str = "chat") -> dict:
    """Chamada mínima real. Retorna {ok, status, detail}.

    kind="embedding" usa o endpoint de embeddings; senão chat.completions, tentando
    max_completion_tokens (gpt-5/o1/o3) e trocando para max_tokens se rejeitado.
    Erros reais (401/403/429) são reportados direto.
    """
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

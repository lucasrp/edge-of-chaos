"""llm_routes — o registry por-rota de LLM que o dashboard e os drivers consomem (issue #55).

Um módulo fundo atrás de quatro chamadas: `routes()` (estado provider/modelo/credencial por
rota do agent.yaml), `probe_route()` (chamada mínima real via _llm.probe), `set_provider()`
(troca de provider por CIRURGIA DE LINHA no agent.yaml — os comentários do fenótipo são do
operador e sobrevivem; um yaml.dump os destruiria) e `completer_for()` (a cadeia inteira
router→secret→client→complete resolvida num só lugar — o driver de close/conductor deixa de
hardcodar provider/chave).

A rota `embedding` NUNCA aceita provider de assinatura (codex não expõe endpoint de
embedding) — recusa na troca, aviso no dashboard, em vez de falha silenciosa best-effort.
"""
import os
import shutil
from pathlib import Path

import _llm
import _identity as _id_state

# Config root (agent.yaml + secrets/): EDGE_HOME-first num install geno/home separado
# (finding do sandbox 2026-07-25); legado home==repo inalterado.
REPO = _id_state.identity_path("agent.yaml").parent

# A rota que exige endpoint de embedding — fora do alcance dos providers de assinatura.
EMBEDDING_ROUTE = "embedding"

KNOWN_PROVIDERS = tuple(_llm.PROVIDER_BASE_URLS) + _llm.SUBSCRIPTION_PROVIDERS


def _load_routers(repo):
    import yaml
    cfg = yaml.safe_load((Path(repo) / "agent.yaml").read_text()) or {}
    return cfg.get("routers") or {}


def _secret_value(repo, secret_ref):
    """Resolve 'file.env:KEY' → valor, olhando env (override explícito vence, como em
    _secrets.load_env) e depois secrets/<file>. None se ausente/vazio."""
    if not secret_ref or ":" not in secret_ref:
        return None
    fname, key = secret_ref.split(":", 1)
    if os.environ.get(key):
        return os.environ[key]
    f = Path(repo) / "secrets" / fname
    if not f.is_file():
        return None
    for line in f.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith(f"{key}="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            return v or None
    return None


def routes(repo=REPO):
    """O estado de cada rota do agent.yaml, na ordem do arquivo: provider, modelo e saúde
    da credencial ('ok' | 'ausente' | 'assinatura' | 'codex CLI ausente'), mais as flags
    que o dashboard renderiza (subscription, embedding_route)."""
    out = []
    for route, r in _load_routers(repo).items():
        provider = r.get("provider")
        subscription = provider in _llm.SUBSCRIPTION_PROVIDERS
        if subscription:
            credential = "assinatura" if shutil.which(provider) else f"{provider} CLI ausente"
        else:
            credential = "ok" if _secret_value(repo, r.get("secret_ref")) else "ausente"
        out.append({
            "route": route,
            "provider": provider,
            "model": r.get("model"),
            "secret_ref": r.get("secret_ref"),
            "credential": credential,
            "subscription": subscription,
            "embedding_route": route == EMBEDDING_ROUTE,
        })
    return out


def _llm_mod():
    """Seam de teste: o módulo _llm por trás do adapter (mock aqui, nunca no import)."""
    return _llm


def embed_fn(repo=REPO):
    """O adapter de embeddings do fenótipo: `routers.embedding` → callable text→vector.

    make_client honra base_url explícito antes do registry (_llm.resolve_base_url), então
    openai direto, openrouter e azure/custom entram todos por esta única porta. Rota
    ausente ou sem chave resolvida → None (o caller escurece, como sempre)."""
    r = _load_routers(repo).get(EMBEDDING_ROUTE)
    if not r:
        return None
    key = _secret_value(repo, r.get("secret_ref"))
    if not key:
        return None
    client = _llm_mod().make_client(r, key)
    model = r.get("model") or "text-embedding-3-small"
    return lambda text: client.embeddings.create(
        model=model, input=text).data[0].embedding


def probe_route(route, repo=REPO):
    """Chamada mínima REAL na rota (reusa _llm.probe). Retorna {ok, status, detail}."""
    routers = _load_routers(repo)
    if route not in routers:
        return {"ok": False, "status": None, "detail": f"rota desconhecida: {route!r}"}
    r = routers[route]
    try:
        client = _llm.make_client(r, _secret_value(repo, r.get("secret_ref")))
    except Exception as e:  # noqa: BLE001 — provider fora do registry etc.
        return {"ok": False, "status": None, "detail": str(e)[:140]}
    kind = "embedding" if route == EMBEDDING_ROUTE else "chat"
    return _llm.probe(client, r.get("model"), kind=kind)


def set_provider(route, provider, repo=REPO, model=None):
    """Troca o provider (e opcionalmente o modelo) de UMA rota no agent.yaml do host,
    por cirurgia de linha — todo o resto do arquivo (comentários inclusos) intacto.
    Recusa rota/provider desconhecidos e provider de assinatura na rota embedding."""
    if provider not in KNOWN_PROVIDERS:
        raise ValueError(f"provider desconhecido: {provider!r} (conheço {KNOWN_PROVIDERS})")
    routers = _load_routers(repo)
    if route not in routers:
        raise ValueError(f"rota desconhecida: {route!r} (agent.yaml tem {tuple(routers)})")
    if route == EMBEDDING_ROUTE and provider in _llm.SUBSCRIPTION_PROVIDERS:
        raise ValueError("a rota embedding não roteia via assinatura (sem endpoint de "
                         "embedding) — precisa de chave de API ou modelo local")

    path = Path(repo) / "agent.yaml"
    lines = path.read_text().splitlines(keepends=True)
    out, in_routers, in_route, route_indent = [], False, False, 0
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if not in_routers:
            in_routers = stripped.startswith("routers:")
        elif stripped and not line[0].isspace():
            in_routers = False          # saiu do bloco routers (nova chave top-level)
        if in_routers and stripped.split("#")[0].strip() == f"{route}:":
            in_route, route_indent = True, indent
        elif in_route and stripped and indent <= route_indent:
            in_route = False            # saiu do sub-bloco da rota
        if in_route and stripped.startswith("provider:"):
            line = f"{' ' * indent}provider: {provider}\n"
        elif in_route and model and stripped.startswith("model:"):
            line = f"{' ' * indent}model: {model}\n"
        out.append(line)
    path.write_text("".join(out))
    return {"route": route, "provider": provider, "model": model}


def completer_for(route, repo=None, max_tokens=4000, exec_fn=None):
    """O completer pronto da rota: `fn(prompt) -> str`, com provider/chave resolvidos do
    agent.yaml + secrets do host. Rota de API sem chave viva → LLMTransportError JÁ AQUI
    (infra explícita, não uma reprovação de revisor lá na frente). `exec_fn` é o seam de
    teste do caminho codex."""
    routers = _load_routers(repo)
    if route not in routers:
        raise ValueError(f"rota desconhecida: {route!r}")
    r = routers[route]
    if r.get("provider") in _llm.SUBSCRIPTION_PROVIDERS:
        client = _llm._SUBSCRIPTION_CLIENTS[r["provider"]](exec_fn=exec_fn)
    else:
        key = _secret_value(repo, r.get("secret_ref"))
        if not key:
            raise _llm.LLMTransportError(
                f"rota {route!r} ({r.get('provider')}): credencial ausente "
                f"({r.get('secret_ref')})")
        client = _llm.make_client(r, key)
    model = r.get("model")
    return lambda prompt: _llm.complete(client, model, prompt, max_tokens=max_tokens)

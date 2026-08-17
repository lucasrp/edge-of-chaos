#!/usr/bin/env python3
"""Registro de Atividades — 4 níveis epistemológicos (v2, pós-veredito Codex 2026-08-17).

Ver o fazer ≠ interpretar o fazer. Este módulo separa os dois MECANICAMENTE em
quatro níveis; nada sobe de nível sozinho, e todo registro só pode citar níveis
iguais ou inferiores (regra imposta em código, `Registry.add`):

- **N1 — evento** (fato observável, determinístico): voz-turno | tool-call |
  commit | spawn, com evidência endereçável (arquivo jsonl + linha + sha1 do
  arquivo no momento da leitura, ou hash de commit) e, para ações, `agencia`
  derivada mecanicamente (nunca chutada; sem sinal → `desconhecido`).
- **N2 — correlação** (mecânica, determinística, versionada): nomes DESCRITIVOS
  da sequência, zero psicologia. Catálogo em `THRESHOLDS` (congelado).
- **N3 — inferência** (LLM via seam `complete_fn`, injetável): claim com
  `confianca` + ≥1 alternativa inocente. Sem completer → DEGRADA DECLARADO
  para N2-only (campo `degradacoes` da projeção), nunca silencioso.
- **N4 — hipótese de mentoria** (confirmável pelo operador): `falsificacao`
  obrigatória; no relatório, N4 `proposta` só aparece como PERGUNTA.

Privacidade: redaction NA INGESTÃO (`redigir`) — nenhum byte de segredo
persiste. Verbatim persistido: só turnos humanos, teto 500 chars. Tool calls:
nome + arquivos + classe do comando + cabeça (2 tokens), NUNCA payload integral.
O renderer re-aplica a redaction (cinto e suspensório) e PROÍBE "não ocorreu":
ausência renderiza "não observado em {superfícies}".

Métricas definidas: `min_ativos` = soma de gaps entre eventos consecutivos do
transcript principal com teto 300s (sensibilidade anexa: tetos 120s e 600s);
`voz×ação` = proporção de EVENTOS por trilho (unidade: eventos, não tempo).

Proxies mecânicos declarados (nunca leituras de cognição):
- "turno humano imperativo" (agência): turno humano de texto que NÃO termina em
  "?", ocorrido ≤120s antes da ação.
- "turno assistant longo" (D2): entrada assistant com ≥800 chars de texto.
- "entrega com perguntas" (D5): último turno assistant da sessão com ≥2 "?" e
  nenhum turno humano posterior nas superfícies varridas.

Custo LLM bounded: nomear ≤1 call/cluster, N3 ≤1 call/correlação, N4 ≤1
call/padrão, teto global 60 calls por backfill (`OrcamentoLLM`).

CLI: scan | backfill | eval | list | show | report. NUNCA escreve em
state/events/ (guarda `_guard_estado`).
"""
import argparse
import glob as _glob
import hashlib
import html as _html
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Versões e thresholds CONGELADOS (estágio 0 roda contra estes valores;
# mudar qualquer um exige nova rodada de avaliação cega — §3 do brief v2)
# ---------------------------------------------------------------------------

DETECTOR_VERSION = "n2-v2.0"
CLUSTER_VERSION = "cluster-v2.0"
MIN_ATIVOS_CAP_S = 300.0
MIN_ATIVOS_SENSIBILIDADE_S = (120.0, 600.0)
VERBATIM_CAP = 500
LLM_TETO_GLOBAL = 60
PADRAO_DORMENTE_DIAS = 14

THRESHOLDS = {
    "resposta-curta-seguida-de-acao": {"max_chars_voz": 6, "janela_s": 120},
    "pergunta-explicacao-resposta-curta": {
        "min_chars_explicacao": 800, "max_chars_resposta": 6, "janela_s": 1800},
    "leituras-repetidas-de-estado-externo": {"min_repeticoes": 3, "janela_s": 3600},
    "sessoes-com-abertura-semelhante": {"jaccard_min": 0.6},
    "entrega-com-perguntas-sem-turno-de-resposta-observado": {"min_perguntas": 2},
    "rajada-de-turnos-curtos": {"min_turnos": 3, "max_chars": 15, "janela_s": 600},
}

EVAL_PRECISAO_MIN = 0.8
EVAL_CONCORDANCIA_MIN = 0.7

# ---------------------------------------------------------------------------
# Redaction — NA INGESTÃO (Codex #11). Aplicada antes de qualquer byte
# persistir fora do host de origem; re-aplicada no renderer.
# ---------------------------------------------------------------------------

# Padrões aterrados no dig-1 (2026-08-17, grok/petertosh) nos rule sets de
# campo: gitleaks (config/gitleaks.toml — generic-api-key keyword rule, AWS
# `AKIA…`, prefixos ghp_/gho_/github_pat_/xox?-/sk-) e detect-secrets (Yelp;
# KeywordDetector, BasicAuthDetector para URL com credencial). Diferença
# deliberada: gitleaks usa o marcador `T3BlbkFJ` p/ chave OpenAI (anti-FP de
# DETECÇÃO); aqui o objetivo é REDAÇÃO — recall > precisão — então o prefixo
# `sk-` é redigido inteiro mesmo com falso positivo ocasional.
_RE_SEGREDOS = [
    # keyword→valor (gitleaks generic-api-key + detect-secrets KeywordDetector;
    # cobre `password=…`, `token: …`, `secret …`)
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer|credential)"
               r"[=:\s]\s*\S+"),
    # tokens nus (formatos conhecidos dos dois rule sets), sem exigir keyword
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{6,}|sk-ant-[A-Za-z0-9_\-]{6,}"
               r"|ghp_[A-Za-z0-9]{10,}|gho_[A-Za-z0-9]{10,}"
               r"|github_pat_[A-Za-z0-9_]{10,}"
               r"|xox[bapors]-[A-Za-z0-9\-]{5,}"
               r"|AKIA[0-9A-Z]{16}"  # charset detect-secrets ([0-9A-Z]) ⊃ gitleaks ([A-Z2-7])
               r"|eyJ[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,})"),
    # valores de env com nome sensível (KEY/TOKEN/SECRET/PASS/CRED)
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|CRED)[A-Z0-9_]*"
               r"=\S+"),
    # URL com credencial embutida — forma do BasicAuthDetector (detect-secrets
    # basic_auth.py): userinfo sem os delimitadores reservados da RFC 3986 §2.2.
    # gitleaks NÃO tem regra genérica scheme://user:pass@ (dig-1, perna A).
    re.compile(r"://[^:/?#\[\]@!$&'()*+,;=\s]+:[^:/?#\[\]@!$&'()*+,;=\s]+@"),
]
_MASK = "***"


def redigir(texto):
    """Substitui padrões de segredo por *** — chamada na INGESTÃO, sempre."""
    if not texto:
        return texto
    for rx in _RE_SEGREDOS:
        texto = rx.sub(_MASK, texto)
    return texto


def achados_de_segredo(texto):
    """Cinto-e-suspensório: lista matches remanescentes num texto já redigido."""
    hits = []
    for rx in _RE_SEGREDOS:
        hits.extend(m.group(0)[:24] for m in rx.finditer(texto or ""))
    return hits


# ---------------------------------------------------------------------------
# Guarda do event log de produção
# ---------------------------------------------------------------------------

class EscritaProibida(Exception):
    pass


def _guard_estado(path):
    p = str(Path(path).resolve())
    if "/state/events/" in p + "/" or p.endswith("/log.jsonl"):
        raise EscritaProibida(
            f"recusado: {p} — este módulo NUNCA escreve no event log de produção")
    return Path(path)


# ---------------------------------------------------------------------------
# Registry — a regra dos níveis imposta em código (Codex #19, #6)
# ---------------------------------------------------------------------------

class CitacaoInvalida(Exception):
    pass


def _citacoes(rec):
    return list(rec.get("instancias") or []) + list(rec.get("base") or [])


class Registry:
    """Guarda todos os registros N1..N4 e impõe: cita-se só para BAIXO.

    - genérico: todo id citado existe e tem nivel ≤ o do registro citante;
    - estrito por schema: N2.instancias só N1; N3.base só N1/N2; N4.base só N3.
    """

    _BASE_PERMITIDA = {2: {1}, 3: {1, 2}, 4: {3}}

    def __init__(self):
        self.by_id = {}

    def add(self, rec):
        nivel = rec.get("nivel")
        if nivel not in (1, 2, 3, 4):
            raise CitacaoInvalida(f"{rec.get('id')}: nivel inválido {nivel!r}")
        cits = _citacoes(rec)
        if nivel == 1 and cits:
            raise CitacaoInvalida(f"{rec['id']}: N1 não cita ninguém")
        if nivel > 1 and not cits:
            raise CitacaoInvalida(f"{rec['id']}: N{nivel} exige citações")
        for cid in cits:
            alvo = self.by_id.get(cid)
            if alvo is None:
                raise CitacaoInvalida(f"{rec['id']}: cita id desconhecido {cid}")
            if alvo["nivel"] > nivel:
                raise CitacaoInvalida(
                    f"{rec['id']} (N{nivel}) cita {cid} (N{alvo['nivel']}): "
                    "só se cita nível igual ou inferior")
            if alvo["nivel"] not in self._BASE_PERMITIDA[nivel]:
                raise CitacaoInvalida(
                    f"{rec['id']} (N{nivel}) cita {cid} (N{alvo['nivel']}): "
                    f"schema permite base em {sorted(self._BASE_PERMITIDA[nivel])}")
        self.by_id[rec["id"]] = rec
        return rec

    def nivel(self, n):
        return [r for r in self.by_id.values() if r["nivel"] == n]


def _rid(prefixo, *partes):
    h = hashlib.sha1("|".join(str(p) for p in partes).encode()).hexdigest()[:12]
    return f"{prefixo}-{h}"


# ---------------------------------------------------------------------------
# Orçamento LLM (Codex #17)
# ---------------------------------------------------------------------------

class OrcamentoLLM:
    def __init__(self, teto=LLM_TETO_GLOBAL):
        self.teto = teto
        self.usadas = 0
        self.negadas = 0
        self.por_categoria = Counter()

    def permitir(self, categoria):
        if self.usadas >= self.teto:
            self.negadas += 1
            return False
        self.usadas += 1
        self.por_categoria[categoria] += 1
        return True

    def dump(self):
        return {"teto": self.teto, "usadas": self.usadas, "negadas": self.negadas,
                "por_categoria": dict(self.por_categoria)}


# ---------------------------------------------------------------------------
# Scanner — jsonl → eventos N1 (redigidos na ingestão)
# ---------------------------------------------------------------------------

def _parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha1_arquivo(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 16), b""):
            h.update(bloco)
    return h.hexdigest()


_RX_COMMIT_BRACKET = re.compile(r"\[[^\]\n]{1,60}\s([0-9a-f]{7,40})\]")
_RX_COMMIT_RANGE = re.compile(r"\.\.([0-9a-f]{7,40})\b")


def classificar_comando(cmd):
    c = (cmd or "").strip()
    if re.search(r"\bgit\s+(commit|push)\b", c):
        return "commit"
    if re.search(r"(>>?|\btee\b|\bmv\b|\bcp\b|\brm\b|\bmkdir\b|\btouch\b"
                 r"|\bgit\s+(add|checkout|switch|branch|merge|rebase|stash)\b"
                 r"|\b(pip|npm|apt|cargo)\s+install\b)", c):
        return "escrita"
    if re.search(r"^(cat|ls|head|tail|grep|rg|find|wc|ps|df|du|stat|file|which"
                 r"|env|curl|wget|ssh|jq|sed|awk|tree|git)\b", c.split("&&")[0].strip()):
        return "leitura"
    return "execucao"


def _texto_de(content):
    """Extrai texto humano de message.content (str ou lista de blocos text)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _eh_voz(entry, texto):
    t = (texto or "").strip()
    if not t or t.startswith("<") or t.startswith("Caveat:") \
            or t.startswith("[Request interrupted"):
        return False
    if entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    origem = (entry.get("origin") or {}).get("kind")
    if origem and origem != "human":
        return False
    return True


def derivar_agencia(ts_acao, sidechain, vozes):
    """Mecânica, nunca chutada (Codex #10).

    executor: 'agente' — tool calls no transcript são executados pelo agente.
    autorizacao: sidechain → 'autonomo'; turno humano de texto que não termina
    em '?' ≤120s antes → 'autorizado'; sem sinal → 'desconhecido'.
    revisao_humana: sem sinal mecânico nas superfícies varridas → 'desconhecido'.
    """
    if sidechain:
        aut, regra = "autonomo", "sidechain"
    else:
        aut, regra = "desconhecido", "sem-sinal"
        for ts_voz, texto in reversed(vozes):
            if ts_voz is None or ts_acao is None:
                continue
            d = ts_acao - ts_voz
            if 0 <= d <= 120 and not texto.rstrip().endswith("?"):
                aut, regra = "autorizado", f"voz-nao-interrogativa-{d:.0f}s-antes"
                break
            if ts_voz < ts_acao - 120:
                break
    return {"executor": "agente", "autorizacao": aut,
            "revisao_humana": "desconhecido", "regra": regra}


def scan_arquivo(path, host, arquivo_rel=None, sidechain=False, session_id=None):
    """Um jsonl → sessão com eventos N1 (todos já redigidos).

    `sidechain=True` (arquivos <sessao>/subagents/agent-*.jsonl): só ações,
    com agencia autonomo; turnos 'user' são prompts do agente, não voz.
    """
    arquivo_rel = arquivo_rel or os.path.basename(path)
    session_id = session_id or Path(path).stem
    sha1 = _sha1_arquivo(path)
    eventos, vozes, assistant_turnos, ts_todos = [], [], [], []
    pendentes = {}  # tool_use_id -> (n1, classe)
    cwd, uuids_vistos, linhas_puladas = "", set(), 0

    atual = {"uuid": None, "sha256_linha": None}

    def ev_base(kind, ts, linha):
        return {"nivel": 1, "session_id": session_id, "host": host,
                "ts": _iso(ts) if ts else None, "kind": kind,
                "evidencia": {"arquivo_jsonl": arquivo_rel, "linha": linha,
                              # sha1 do ARQUIVO = read_generation — audita "o
                              # que o parser viu em T"; NUNCA endereço de um
                              # recorte (dig-1, perna B: Filebeat/Vector
                              # fingerprint; jsonl é mutável por contrato)
                              "sha1_arquivo_no_momento_da_leitura": sha1,
                              # endereço de conteúdo da linha COMO LIDA (na
                              # cópia de trabalho já redigida): sessionId +
                              # uuid + hash da linha é a citação estável do
                              # ecossistema (dig-1, perna B)
                              "uuid": atual["uuid"],
                              "sha256_linha_lida": atual["sha256_linha"]}}

    with open(path, encoding="utf-8", errors="replace") as fh:
        for linha_n, linha in enumerate(fh, 1):
            if not linha.endswith("\n"):
                # última linha parcial (append em andamento): só linhas
                # terminadas em \n são consumidas — dig-1, perna B
                linhas_puladas += 1
                continue
            try:
                e = json.loads(linha)
            except Exception:
                linhas_puladas += 1
                continue
            atual["uuid"] = e.get("uuid")
            atual["sha256_linha"] = hashlib.sha256(
                linha.encode("utf-8", "replace")).hexdigest()[:16]
            u = e.get("uuid")
            if u and u in uuids_vistos:
                continue
            if u:
                uuids_vistos.add(u)
            ts = _parse_ts(e.get("timestamp"))
            if ts is not None:
                ts_todos.append(ts)
            cwd = e.get("cwd") or cwd
            eh_side = bool(sidechain or e.get("isSidechain"))
            tipo = e.get("type")
            msg = e.get("message") or {}
            content = msg.get("content")

            if tipo == "user":
                texto = _texto_de(content)
                if not eh_side and _eh_voz(e, texto) and ts is not None:
                    texto_red = redigir(texto)[:VERBATIM_CAP]
                    ev = ev_base("voz-turno", ts, linha_n)
                    ev["id"] = _rid("n1", session_id, arquivo_rel, linha_n, "voz")
                    ev["conteudo_redigido"] = {"texto": texto_red,
                                               "chars": len(texto.strip())}
                    eventos.append(ev)
                    vozes.append((ts, texto.strip(), ev["id"], linha_n))
                # tool_results: procurar hash de commit p/ tool calls pendentes
                if isinstance(content, list):
                    for b in content:
                        if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                            continue
                        tuid = b.get("tool_use_id")
                        par = pendentes.pop(tuid, None)
                        if not par:
                            continue
                        n1_tc, classe = par
                        if classe != "commit":
                            continue
                        rtxt = _texto_de(b.get("content")) if not isinstance(
                            b.get("content"), str) else b.get("content")
                        m = (_RX_COMMIT_BRACKET.search(rtxt or "")
                             or _RX_COMMIT_RANGE.search(rtxt or ""))
                        if m and ts is not None:
                            h = m.group(1)
                            n1_tc["conteudo_redigido"]["commits_detectados"] = \
                                n1_tc["conteudo_redigido"].get(
                                    "commits_detectados", []) + [h]
                            ev = ev_base("commit", ts, linha_n)
                            ev["id"] = _rid("n1", session_id, arquivo_rel,
                                            linha_n, "commit", h)
                            ev["conteudo_redigido"] = {"hash": h,
                                                       "origem": "tool_result"}
                            ev["evidencia"]["commit_hash"] = h
                            ev["agencia"] = dict(n1_tc["agencia"])
                            eventos.append(ev)

            elif tipo == "assistant" and isinstance(content, list):
                texto = _texto_de(content)
                if texto.strip() and ts is not None and not eh_side:
                    assistant_turnos.append({
                        "ts": ts, "linha": linha_n, "chars": len(texto),
                        "n_perguntas": texto.count("?")})
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    if ts is None:
                        continue
                    nome = b.get("name") or "?"
                    inp = b.get("input") or {}
                    kind = "spawn" if nome in ("Task", "Agent") else "tool-call"
                    classe, arquivos, cabeca = None, [], None
                    if nome == "Bash":
                        cmd = inp.get("command") or ""
                        classe = classificar_comando(cmd)
                        cabeca = redigir(" ".join(cmd.strip().split()[:2]))[:80]
                    elif nome in ("Edit", "Write", "NotebookEdit"):
                        classe = "escrita"
                        if inp.get("file_path") or inp.get("notebook_path"):
                            arquivos = [inp.get("file_path")
                                        or inp.get("notebook_path")]
                    elif nome == "Read":
                        classe = "leitura"
                        if inp.get("file_path"):
                            arquivos = [inp.get("file_path")]
                    else:
                        classe = "outro"
                    ev = ev_base(kind, ts, linha_n)
                    ev["id"] = _rid("n1", session_id, arquivo_rel, linha_n,
                                    kind, b.get("id") or nome)
                    ev["conteudo_redigido"] = {
                        "tool": nome, "classe": classe,
                        "arquivos": [redigir(a)[:200] for a in arquivos],
                        "comando_cabeca": cabeca, "sidechain": eh_side}
                    ev["agencia"] = derivar_agencia(
                        ts, eh_side, [(t, x) for t, x, _, _ in vozes])
                    eventos.append(ev)
                    if b.get("id"):
                        pendentes[b["id"]] = (ev, classe)

    abertura = ""
    for _, t, _, _ in vozes:
        if len(t) >= 8:
            abertura = redigir(t)[:200]
            break
    if not abertura and vozes:
        abertura = redigir(vozes[0][1])[:200]

    return {"session_id": session_id, "host": host, "arquivo": arquivo_rel,
            "sha1": sha1, "cwd": cwd, "sidechain": sidechain,
            "eventos": eventos, "vozes": vozes,
            "assistant_turnos": assistant_turnos, "ts_todos": sorted(ts_todos),
            "abertura": abertura, "linhas_puladas": linhas_puladas}


def tempo_ativo_s(ts_list, cap):
    ts = sorted(t for t in ts_list if t is not None)
    return sum(min(b - a, cap) for a, b in zip(ts, ts[1:]))


# ---------------------------------------------------------------------------
# Detectores N2 — nomes descritivos, sequência e não cognição (Codex #3)
# ---------------------------------------------------------------------------

def _mk_n2(reg, forma, instancias, params, janela, extra=None):
    n1s = [reg.by_id[i] for i in instancias]
    rec = {"id": _rid("n2", forma, *sorted(instancias)), "nivel": 2,
           "forma": forma, "instancias": instancias,
           "params": dict(THRESHOLDS[forma], **(params or {})),
           "detector_version": DETECTOR_VERSION,
           "janela": janela,
           "sessoes": sorted({r["session_id"] for r in n1s}),
           "hosts": sorted({r["host"] for r in n1s}),
           "dias": sorted({(r["ts"] or "")[:10] for r in n1s if r["ts"]})}
    if extra:
        rec.update(extra)
    return reg.add(rec)


def _eh_acao_escrita(ev):
    if ev["kind"] == "commit":
        return True
    if ev["kind"] not in ("tool-call", "spawn"):
        return False
    c = ev["conteudo_redigido"]
    return c.get("classe") in ("escrita", "commit")


def detectar_sessao(sessao, reg):
    """Detectores intra-sessão (D1, D2, D3, D5, D6) sobre os N1 já registrados."""
    out = []
    th = THRESHOLDS
    vozes = sessao["vozes"]  # (ts, texto, n1_id, linha)
    acoes = [e for e in sessao["eventos"] if e["kind"] != "voz-turno"
             and e["ts"] is not None]
    acoes.sort(key=lambda e: e["ts"])

    # D1 resposta-curta-seguida-de-acao
    p = th["resposta-curta-seguida-de-acao"]
    for ts, texto, vid, linha in vozes:
        if 0 < len(texto) <= p["max_chars_voz"]:
            for ac in acoes:
                d = _parse_ts(ac["ts"]) - ts
                if 0 < d <= p["janela_s"] and _eh_acao_escrita(ac) \
                        and not ac["conteudo_redigido"].get("sidechain"):
                    out.append(_mk_n2(
                        reg, "resposta-curta-seguida-de-acao", [vid, ac["id"]],
                        {"delta_s": round(d, 1), "chars_voz": len(texto)},
                        {"de": _iso(ts), "ate": ac["ts"]}))
                    break

    # D2 pergunta-explicacao-resposta-curta
    p = th["pergunta-explicacao-resposta-curta"]
    ats = sorted(sessao["assistant_turnos"], key=lambda a: a["ts"])
    for i, (ts, texto, vid, linha) in enumerate(vozes):
        if not texto.rstrip().endswith("?"):
            continue
        expl = next((a for a in ats if a["ts"] > ts
                     and a["chars"] >= p["min_chars_explicacao"]), None)
        if not expl:
            continue
        resp = next(((ts2, t2, vid2) for ts2, t2, vid2, _ in vozes[i + 1:]
                     if ts2 > expl["ts"] and 0 < len(t2) <= p["max_chars_resposta"]
                     and ts2 - ts <= p["janela_s"]), None)
        if resp:
            out.append(_mk_n2(
                reg, "pergunta-explicacao-resposta-curta", [vid, resp[2]],
                {"assistant_linha": expl["linha"], "assistant_chars": expl["chars"]},
                {"de": _iso(ts), "ate": _iso(resp[0])}))

    # D3 leituras-repetidas-de-estado-externo
    p = th["leituras-repetidas-de-estado-externo"]
    por_cabeca = defaultdict(list)
    for ac in acoes:
        c = ac["conteudo_redigido"]
        if c.get("tool") == "Bash" and c.get("classe") == "leitura" \
                and c.get("comando_cabeca"):
            por_cabeca[c["comando_cabeca"]].append(ac)
    for cabeca, lst in por_cabeca.items():
        i = 0
        while i < len(lst):
            j = i
            while j + 1 < len(lst) and _parse_ts(lst[j + 1]["ts"]) - \
                    _parse_ts(lst[i]["ts"]) <= p["janela_s"]:
                j += 1
            if j - i + 1 >= p["min_repeticoes"]:
                grupo = lst[i:j + 1]
                out.append(_mk_n2(
                    reg, "leituras-repetidas-de-estado-externo",
                    [g["id"] for g in grupo],
                    {"comando_cabeca": cabeca, "n_repeticoes": len(grupo)},
                    {"de": grupo[0]["ts"], "ate": grupo[-1]["ts"]}))
            i = j + 1

    # D5 entrega-com-perguntas-sem-turno-de-resposta-observado
    p = th["entrega-com-perguntas-sem-turno-de-resposta-observado"]
    if ats and vozes:
        ultimo = ats[-1]
        if ultimo["n_perguntas"] >= p["min_perguntas"] \
                and not any(ts > ultimo["ts"] for ts, _, _, _ in vozes):
            out.append(_mk_n2(
                reg, "entrega-com-perguntas-sem-turno-de-resposta-observado",
                [vozes[-1][2]],
                {"assistant_linha": ultimo["linha"],
                 "n_perguntas": ultimo["n_perguntas"]},
                {"de": _iso(vozes[-1][0]), "ate": _iso(ultimo["ts"])}))

    # D6 rajada-de-turnos-curtos
    p = th["rajada-de-turnos-curtos"]
    curtos = [(ts, vid) for ts, t, vid, _ in vozes if 0 < len(t) <= p["max_chars"]]
    i = 0
    while i < len(curtos):
        j = i
        while j + 1 < len(curtos) and curtos[j + 1][0] - curtos[i][0] <= p["janela_s"]:
            j += 1
        if j - i + 1 >= p["min_turnos"]:
            out.append(_mk_n2(
                reg, "rajada-de-turnos-curtos", [v for _, v in curtos[i:j + 1]],
                {"n_turnos": j - i + 1},
                {"de": _iso(curtos[i][0]), "ate": _iso(curtos[j][0])}))
        i = j + 1
    return out


def _tokens(texto):
    return set(re.findall(r"[a-zà-ú0-9\-]{3,}", (texto or "").lower()))


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detectar_cross_sessao(sessoes, reg):
    """D4 sessoes-com-abertura-semelhante (dias distintos)."""
    out = []
    p = THRESHOLDS["sessoes-com-abertura-semelhante"]
    abertos = []
    for s in sessoes:
        if s["sidechain"] or not s["vozes"]:
            continue
        ts, _, vid, _ = s["vozes"][0]
        abertos.append((s, _tokens(s["abertura"]), ts, vid))
    for i in range(len(abertos)):
        for j in range(i + 1, len(abertos)):
            (sa, ta, tsa, va), (sb, tb, tsb, vb) = abertos[i], abertos[j]
            jac = _jaccard(ta, tb)
            dia_a, dia_b = _iso(tsa)[:10], _iso(tsb)[:10]
            if jac >= p["jaccard_min"] and dia_a != dia_b:
                out.append(_mk_n2(
                    reg, "sessoes-com-abertura-semelhante", [va, vb],
                    {"jaccard": round(jac, 3)},
                    {"de": _iso(min(tsa, tsb)), "ate": _iso(max(tsa, tsb))}))
    return out


# ---------------------------------------------------------------------------
# Camada 1 — clustering sessão→Atividade (determinístico primeiro; Codex #12)
# ---------------------------------------------------------------------------

def _touch(sessao):
    evs = sessao["eventos"]
    voz = [e for e in evs if e["kind"] == "voz-turno"]
    acao = [e for e in evs if e["kind"] != "voz-turno"]
    side = [e for e in acao if e["conteudo_redigido"].get("sidechain")]
    ts = sessao["ts_todos"]
    ferramentas = Counter(e["conteudo_redigido"].get("tool") for e in acao
                          if e["kind"] in ("tool-call", "spawn"))
    arquivos = Counter(a for e in acao
                       for a in e["conteudo_redigido"].get("arquivos", []))
    commits = [e["conteudo_redigido"]["hash"] for e in evs if e["kind"] == "commit"]
    sens = {f"cap_{int(c)}s": round(tempo_ativo_s(ts, c) / 60, 1)
            for c in MIN_ATIVOS_SENSIBILIDADE_S}
    return {
        "session_id": sessao["session_id"], "host": sessao["host"],
        "arquivo": sessao["arquivo"],
        "ts_start": _iso(ts[0]) if ts else None,
        "ts_end": _iso(ts[-1]) if ts else None,
        "min_ativos": {
            "cap_s": int(MIN_ATIVOS_CAP_S),
            "minutos": round(tempo_ativo_s(ts, MIN_ATIVOS_CAP_S) / 60, 1),
            "sensibilidade": sens,
            "base": "gaps entre timestamps consecutivos do transcript principal"},
        "n_eventos_voz": len(voz), "n_eventos_acao": len(acao),
        "n_eventos_acao_sidechain": len(side),
        "top_ferramentas": ferramentas.most_common(5),
        "top_arquivos": [(redigir(a), n) for a, n in arquivos.most_common(5)],
        "commits": commits}


def clusterizar(sessoes, complete_fn=None, orcamento=None):
    """Determinístico primeiro: cwd; merge por similaridade de abertura.

    LLM só para NOMEAR (≤1 call/cluster). merges/splits logados com razão.
    """
    principais = [s for s in sessoes if not s["sidechain"]]
    log = []
    grupos = defaultdict(list)
    for s in principais:
        chave = s["cwd"] or f"sem-cwd:{s['session_id'][:8]}"
        grupos[chave].append(s)
        log.append({"acao": "atribuir", "session_id": s["session_id"],
                    "cluster": chave, "razao": "cwd idêntico",
                    "cluster_version": CLUSTER_VERSION})
    # merge entre grupos com aberturas semelhantes
    chaves = sorted(grupos)
    merged, dono = {}, {}
    for c in chaves:
        dono[c] = c
    p = THRESHOLDS["sessoes-com-abertura-semelhante"]
    for i in range(len(chaves)):
        for j in range(i + 1, len(chaves)):
            a, b = chaves[i], chaves[j]
            jac = max((_jaccard(_tokens(sa["abertura"]), _tokens(sb["abertura"]))
                       for sa in grupos[a] for sb in grupos[b]), default=0.0)
            if jac >= p["jaccard_min"]:
                raiz_a, raiz_b = dono[a], dono[b]
                if raiz_a != raiz_b:
                    for k, v in dono.items():
                        if v == raiz_b:
                            dono[k] = raiz_a
                    log.append({"acao": "merge", "de": raiz_b, "para": raiz_a,
                                "razao": f"abertura jaccard {jac:.2f} >= "
                                         f"{p['jaccard_min']}",
                                "cluster_version": CLUSTER_VERSION})
    finais = defaultdict(list)
    for c in chaves:
        finais[dono[c]].extend(grupos[c])

    atividades = []
    for chave, ss in sorted(finais.items()):
        ss.sort(key=lambda s: s["ts_todos"][0] if s["ts_todos"] else 0)
        abertura_ref = max((s["abertura"] for s in ss), key=len, default="")
        nome = None
        if complete_fn and orcamento and orcamento.permitir("nomear-cluster"):
            try:
                resp = complete_fn(
                    "Nomeie em no máximo 6 palavras, descritivas e sem "
                    "diagnóstico psicológico, a Atividade de trabalho cujas "
                    "aberturas de sessão são:\n"
                    + "\n".join(f"- {s['abertura'][:160]}" for s in ss[:5])
                    + "\nResponda SÓ o nome.")
                nome = redigir((resp or "").strip().splitlines()[0])[:80] or None
            except Exception as ex:
                log.append({"acao": "nomear-falhou", "cluster": chave,
                            "razao": str(ex)[:120]})
        if not nome:
            nome = (abertura_ref[:60] or chave)
        atividades.append({
            "ulid": _rid("atv", chave), "nome": nome,
            "finalidade": abertura_ref[:160],
            "estado": "aberta",
            "hosts": sorted({s["host"] for s in ss}),
            "cwd": chave, "cluster_version": CLUSTER_VERSION,
            "sessions": [_touch(s) for s in ss],
            "session_ids": [s["session_id"] for s in ss]})
    return atividades, log


# ---------------------------------------------------------------------------
# Camada 3 — fold de padrões (estados; diversidade; Codex #13)
# ---------------------------------------------------------------------------

def fold_padroes(reg, agora_ts=None):
    agora_ts = agora_ts or datetime.now(tz=timezone.utc).timestamp()
    padroes = []
    por_forma = defaultdict(list)
    for n2 in reg.nivel(2):
        por_forma[n2["forma"]].append(n2)
    for forma, lst in sorted(por_forma.items()):
        sessoes = sorted({s for n2 in lst for s in n2["sessoes"]})
        dias = sorted({d for n2 in lst for d in n2["dias"]})
        hosts = sorted({h for n2 in lst for h in n2["hosts"]})
        vistos = sorted(x for n2 in lst for x in (n2["janela"]["de"],
                                                  n2["janela"]["ate"]) if x)
        first_seen, last_seen = (vistos[0], vistos[-1]) if vistos else (None, None)
        if any(n2.get("invalid_at") for n2 in lst):
            estado = "invalidado"
        elif len(sessoes) < 2 and len(dias) < 2:
            estado = "mesma-cena"
        elif last_seen and (agora_ts - _parse_ts(last_seen)) > \
                PADRAO_DORMENTE_DIAS * 86400:
            estado = "dormente"
        else:
            estado = "ativo"
        padroes.append({
            "forma": forma, "instancias": [n2["id"] for n2 in lst],
            "n": len(lst),
            "diversidade": {"sessoes": len(sessoes), "dias": len(dias),
                            "hosts": len(hosts)},
            "first_seen": first_seen, "last_seen": last_seen,
            "estado": estado, "detector_version": DETECTOR_VERSION})
    return padroes


# ---------------------------------------------------------------------------
# N3 / N4 — via seam complete_fn (degradação declarada sem ele)
# ---------------------------------------------------------------------------

def _json_do_llm(texto):
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _resumo_instancia(n1):
    c = n1.get("conteudo_redigido") or {}
    if n1["kind"] == "voz-turno":
        que = f"voz: \"{(c.get('texto') or '')[:80]}\" ({c.get('chars')} chars)"
    elif n1["kind"] == "commit":
        que = f"commit {c.get('hash')}"
    else:
        que = (f"{c.get('tool')}({c.get('classe')}) "
               f"{c.get('comando_cabeca') or ''} "
               f"{' '.join(c.get('arquivos') or [])[:80]}").strip()
    return f"- [{n1['kind']} @ {n1['ts']}] {que}"


def inferir_n3(reg, complete_fn, orcamento, model="injetado"):
    """≤1 call por correlação; claim com confiança + alternativas inocentes.

    O prompt EMBUTE o resumo redigido das instâncias N1 — sem isso o modelo
    responde meta-reclamações de "transcript não fornecido" (observado no
    backfill de 2026-08-17)."""
    out = []
    for n2 in sorted(reg.nivel(2), key=lambda r: r["id"]):
        if not orcamento.permitir("n3"):
            break
        evid = "\n".join(_resumo_instancia(reg.by_id[i])
                         for i in n2["instancias"][:8])
        try:
            resp = complete_fn(
                "Você anota correlações mecânicas em transcripts de trabalho. "
                "NUNCA afirme cognição; um claim é 'compatível com', nunca "
                "'prova'. A evidência resumida (redigida) está ABAIXO — não "
                "peça o transcript; se ela for pouca, devolva um claim "
                "modesto com confiança baixa. Correlação:\n"
                f"forma: {n2['forma']}\nparams: {json.dumps(n2['params'])}\n"
                f"janela: {json.dumps(n2['janela'])}\n"
                f"instancias:\n{evid}\n"
                "Responda SÓ JSON: {\"claim\": \"...\", \"confianca\": 0.0-1.0, "
                "\"alternativas\": [\">=1 explicação inocente\"]}")
        except Exception:
            continue
        j = _json_do_llm(resp)
        if not j or not j.get("claim") or not j.get("alternativas"):
            continue
        rec = {"id": _rid("n3", n2["id"]), "nivel": 3,
               "claim": redigir(str(j["claim"]))[:400],
               "confianca": max(0.0, min(1.0, float(j.get("confianca", 0.5)))),
               "alternativas": [redigir(str(a))[:200]
                                for a in j["alternativas"]][:4],
               "base": [n2["id"]], "detector_version": DETECTOR_VERSION,
               "model": model}
        out.append(reg.add(rec))
    return out


N3_CONFIANCA_MIN_PARA_N4 = 0.2  # N3 degenerado (confiança ~0) não sobe a N4


def hipotetizar_n4(reg, complete_fn, orcamento, model="injetado"):
    """≤1 call por padrão (forma) com N3s; status nasce 'proposta'.

    Só N3 com confiança ≥ N3_CONFIANCA_MIN_PARA_N4 entra na base — filtro
    declarado (não é leitura de cognição: usa a incerteza que o próprio N3
    declara)."""
    out = []
    por_forma = defaultdict(list)
    for n3 in reg.nivel(3):
        if n3["confianca"] < N3_CONFIANCA_MIN_PARA_N4:
            continue
        for bid in n3["base"]:
            por_forma[reg.by_id[bid]["forma"]].append(n3)
    for forma, n3s in sorted(por_forma.items()):
        if not orcamento.permitir("n4"):
            break
        try:
            resp = complete_fn(
                "Você formula hipóteses de mentoria CONFIRMÁVEIS pelo "
                "mentorado — a correção dele sempre vence. As inferências "
                "abaixo são todo o insumo disponível; não peça mais contexto. "
                f"Padrão observado: '{forma}'. Inferências:\n"
                + "\n".join(f"- {n3['claim']} (confiança {n3['confianca']})"
                            for n3 in n3s[:5])
                + "\nResponda SÓ JSON: {\"hipotese\": \"frase interrogativa "
                  "dirigida ao mentorado sobre COMO ELE TRABALHA, terminando "
                  "em ?\", \"falsificacao\": "
                  "\"que observação a derrubaria\"}")
        except Exception:
            continue
        j = _json_do_llm(resp)
        if not j or not j.get("hipotese") or not j.get("falsificacao"):
            continue
        rec = {"id": _rid("n4", forma, *sorted(n3["id"] for n3 in n3s)),
               "nivel": 4, "hipotese": redigir(str(j["hipotese"]))[:400],
               "falsificacao": redigir(str(j["falsificacao"]))[:300],
               "base": sorted({n3["id"] for n3 in n3s}), "status": "proposta",
               "model": model,
               "criado_em": datetime.now(tz=timezone.utc).isoformat()}
        out.append(reg.add(rec))
    return out


# ---------------------------------------------------------------------------
# Estágio 0 — avaliação cega (Codex #20, #15)
# ---------------------------------------------------------------------------

PERGUNTA_MECANICA = ("A sequência descrita ocorre de fato nesta evidência? "
                     "Responda exatamente uma opção: sim | nao | "
                     "evidencia-insuficiente.")


_DESCRICOES_MECANICAS = {
    # lambdas: só a forma do n2 tem seus params acessados (avaliação preguiçosa)
    "resposta-curta-seguida-de-acao": lambda p:
        f"turno humano com <= {p['max_chars_voz']} chars seguido, em ate "
        f"{p['janela_s']}s, de tool call de escrita/commit",
    "pergunta-explicacao-resposta-curta": lambda p:
        f"turno humano interrogativo, depois entrada assistant com >= "
        f"{p['min_chars_explicacao']} chars, depois turno humano com <= "
        f"{p['max_chars_resposta']} chars",
    "leituras-repetidas-de-estado-externo": lambda p:
        f">= {p['min_repeticoes']} execucoes Bash de leitura com a mesma "
        f"cabeca de comando em <= {p['janela_s']}s",
    "sessoes-com-abertura-semelhante": lambda p:
        f"aberturas de duas sessoes em dias distintos com jaccard >= "
        f"{p['jaccard_min']}",
    "entrega-com-perguntas-sem-turno-de-resposta-observado": lambda p:
        f"ultima entrada assistant da sessao com >= {p['min_perguntas']} "
        "'?' e nenhum turno humano posterior nesta sessao",
    "rajada-de-turnos-curtos": lambda p:
        f">= {p['min_turnos']} turnos humanos com <= {p['max_chars']} chars "
        f"em <= {p['janela_s']}s",
}


def _descricao_mecanica(n2):
    p = n2["params"]
    f = n2["forma"]
    d = _DESCRICOES_MECANICAS[f](p)
    return d + f" (observado: {json.dumps({k: v for k, v in p.items() if k not in THRESHOLDS[f]}, ensure_ascii=False)})"


def _trecho(workdir, arquivo_rel, linha, contexto=1):
    """Linhas cruas (da cópia de trabalho JÁ redigida) ao redor da âncora."""
    caminho = Path(workdir) / arquivo_rel
    linhas = []
    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            for n, l in enumerate(fh, 1):
                if abs(n - linha) <= contexto:
                    linhas.append({"linha": n, "conteudo": redigir(l.strip())[:700]})
                if n > linha + contexto:
                    break
    except OSError as ex:
        linhas.append({"linha": linha, "conteudo": f"[trecho indisponível: {ex}]"})
    return linhas


def eval_preparar(reg, workdir, max_amostra=30, seed=17):
    """Amostra estratificada por forma (round-robin determinístico)."""
    import random
    rnd = random.Random(seed)
    por_forma = defaultdict(list)
    for n2 in reg.nivel(2):
        por_forma[n2["forma"]].append(n2)
    for lst in por_forma.values():
        lst.sort(key=lambda r: r["id"])
        rnd.shuffle(lst)
    itens, rodada = [], 0
    while len(itens) < max_amostra and any(por_forma.values()):
        for forma in sorted(por_forma):
            if por_forma[forma] and len(itens) < max_amostra:
                n2 = por_forma[forma].pop()
                trechos = []
                for iid in n2["instancias"][:6]:
                    n1 = reg.by_id[iid]
                    ev = n1["evidencia"]
                    trechos.append({
                        "ancora": {"arquivo": ev["arquivo_jsonl"],
                                   "linha": ev["linha"], "kind": n1["kind"]},
                        "linhas": _trecho(workdir, ev["arquivo_jsonl"],
                                          ev["linha"])})
                itens.append({
                    "item": len(itens) + 1, "n2_id": n2["id"],
                    "forma": n2["forma"],
                    "descricao_mecanica": _descricao_mecanica(n2),
                    "pergunta": PERGUNTA_MECANICA,
                    "evidencia": trechos})
        rodada += 1
    return {"pergunta": PERGUNTA_MECANICA,
            "thresholds_congelados": {
                "precisao_min": EVAL_PRECISAO_MIN,
                "concordancia_min": EVAL_CONCORDANCIA_MIN,
                "detector_version": DETECTOR_VERSION,
                "thresholds": THRESHOLDS},
            "itens": itens}


_CLASSES_EVAL = ("sim", "nao", "evidencia-insuficiente")


def _normalizar_rotulo(r):
    t = str(r or "").strip().lower().replace("ã", "a").replace("ê", "e")
    if t.startswith("sim"):
        return "sim"
    if t.startswith("nao") or t.startswith("não") or t == "no":
        return "nao"
    if "insuficiente" in t or "insufficient" in t:
        return "evidencia-insuficiente"
    return None


def cohen_kappa(pares):
    """κ de Cohen (3 classes) sobre pares (a, b) — Cohen 1960 (dig-1, perna C).

    κ = (p_o − p_e) / (1 − p_e), com p_e das distribuições marginais de cada
    rotulador. Retorna (p_o, kappa|None) — None quando p_e = 1 (degenerado,
    esperado com n pequeno; reportar p_o e as contagens cruas nesse caso).
    """
    pares = [(a, b) for a, b in pares if a in _CLASSES_EVAL and b in _CLASSES_EVAL]
    n = len(pares)
    if not n:
        return None, None
    p_o = sum(1 for a, b in pares if a == b) / n
    ma, mb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    p_e = sum((ma[c] / n) * (mb[c] / n) for c in _CLASSES_EVAL)
    if abs(1 - p_e) < 1e-9:
        return round(p_o, 3), None
    return round(p_o, 3), round((p_o - p_e) / (1 - p_e), 3)


def eval_ingerir(amostra, labels_a, labels_b):
    """Precisão (vs consenso unânime) + concordância por forma; demote.

    Metodologia do dig-1 (perna C — Cohen 1960; Landis & Koch 1977; McHugh
    2012; Artstein & Poesio 2008):
    - ouro = SÓ itens unânimes (desacordo declarado como n descartado, nunca
      resolvido pelo voto do detector);
    - precisão = sim-unânime / (sim-unânime + nao-unânime); itens com ouro
      evidencia-insuficiente FICAM FORA do denominador;
    - concordância: p_o (proporção observada) é o threshold CONGELADO
      (≥ EVAL_CONCORDANCIA_MIN); κ de Cohen reportado junto, com matriz de
      confusão crua e a
      ressalva de n pequeno (IC largo em n≈30; κ por forma pode ser
      degenerado — reportado como null, nunca imputado).
    """
    la = {l["item"]: _normalizar_rotulo(l["resposta"])
          for l in labels_a["labels"]}
    lb = {l["item"]: _normalizar_rotulo(l["resposta"])
          for l in labels_b["labels"]}
    por_forma = defaultdict(lambda: {"n": 0, "concordam": 0, "sim": 0,
                                     "nao": 0, "insuficiente": 0,
                                     "sem_consenso": 0, "pares": []})
    todos_pares = []
    for item in amostra["itens"]:
        f = por_forma[item["forma"]]
        f["n"] += 1
        a, b = la.get(item["item"]), lb.get(item["item"])
        if a is not None and b is not None:
            f["pares"].append((a, b))
            todos_pares.append((a, b))
        if a is None or b is None or a != b:
            f["sem_consenso"] += 1
            continue
        f["concordam"] += 1
        if a == "sim":
            f["sim"] += 1
        elif a == "nao":
            f["nao"] += 1
        else:
            f["insuficiente"] += 1
    resultado = {}
    for forma, f in sorted(por_forma.items()):
        pares = f.pop("pares")
        conc = f["concordam"] / f["n"] if f["n"] else 0.0
        _, kappa = cohen_kappa(pares)
        confusao = Counter(f"{a}|{b}" for a, b in pares)
        denom = f["sim"] + f["nao"]
        prec = f["sim"] / denom if denom else None
        confiavel = (prec is not None and prec >= EVAL_PRECISAO_MIN
                     and conc >= EVAL_CONCORDANCIA_MIN)
        resultado[forma] = dict(
            f, concordancia=round(conc, 3), kappa=kappa,
            confusao=dict(confusao),
            precisao=(round(prec, 3) if prec is not None else None),
            veredicto="confiavel" if confiavel else "experimental")
    p_o_global, kappa_global = cohen_kappa(todos_pares)
    return {"thresholds_congelados": amostra["thresholds_congelados"],
            "rotuladores": [labels_a.get("rotulador", "a"),
                            labels_b.get("rotulador", "b")],
            "amostra": len(amostra["itens"]), "por_forma": resultado,
            "global": {"p_o": p_o_global, "kappa": kappa_global,
                       "n_pares": len(todos_pares),
                       "nota": "κ de Cohen 3-classes agregado; em n≈30 o IC é "
                               "largo (Sim & Wright 2005) — ler junto com as "
                               "contagens cruas, nunca sozinho"},
            "avaliado_em": datetime.now(tz=timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Cobertura honesta (Codex #18)
# ---------------------------------------------------------------------------

def montar_cobertura(hosts, parseadas, puladas, janela):
    return {"hosts_varridos": sorted(hosts),
            "sessoes_parseadas": parseadas,
            "sessoes_puladas": puladas,
            "janela": janela,
            "nota": "superfícies fora desta lista NÃO foram varridas; "
                    "ausência aqui nunca significa que não ocorreu"}


def superficies_de(cobertura):
    j = cobertura.get("janela") or {}
    return (f"{', '.join(cobertura.get('hosts_varridos', ['?']))} "
            f"({cobertura.get('sessoes_parseadas', 0)} sessões parseadas, "
            f"janela {str(j.get('de'))[:10]}–{str(j.get('ate'))[:10]})")


def ausencia(cobertura):
    """A ÚNICA frase de ausência permitida (Codex #18)."""
    return f"não observado em {superficies_de(cobertura)}"


# ---------------------------------------------------------------------------
# Pipeline / persistência
# ---------------------------------------------------------------------------

def pipeline(workdir, host, complete_fn=None, janela_dias=7, agora_ts=None,
             model="injetado"):
    """Cópia de trabalho (já redigida) → registry + projeção completa."""
    workdir = Path(workdir)
    arquivos = sorted(str(p) for p in workdir.rglob("*.jsonl"))
    principais = [a for a in arquivos if "/subagents/" not in a]
    sub = [a for a in arquivos if "/subagents/" in a]
    reg = Registry()
    orc = OrcamentoLLM()
    sessoes, puladas = [], []
    for a in principais:
        rel = os.path.relpath(a, workdir)
        try:
            s = scan_arquivo(a, host, arquivo_rel=rel)
        except Exception as ex:
            puladas.append({"arquivo": rel, "razao": f"erro de parse: {ex}"})
            continue
        if not s["vozes"]:
            puladas.append({"arquivo": rel,
                            "razao": "sem turno humano de voz"})
            continue
        sessoes.append(s)
    por_id = {s["session_id"]: s for s in sessoes}
    for a in sub:
        rel = os.path.relpath(a, workdir)
        m = re.search(r"([0-9a-f\-]{36})/subagents/", a)
        pai = por_id.get(m.group(1)) if m else None
        if not pai:
            puladas.append({"arquivo": rel, "razao": "subagente sem sessão-mãe "
                            "parseada"})
            continue
        try:
            ss = scan_arquivo(a, host, arquivo_rel=rel, sidechain=True,
                              session_id=pai["session_id"])
        except Exception as ex:
            puladas.append({"arquivo": rel, "razao": f"erro de parse: {ex}"})
            continue
        pai["eventos"].extend(ss["eventos"])

    for s in sessoes:
        for ev in s["eventos"]:
            reg.add(ev)
    n2s = []
    for s in sessoes:
        n2s.extend(detectar_sessao(s, reg))
    n2s.extend(detectar_cross_sessao(sessoes, reg))

    degradacoes = []
    if complete_fn is None:
        degradacoes.append(
            "N3/N4 não gerados e clusters sem nome LLM: completer ausente — "
            "degradação DECLARADA para N2-only (brief v2 §4)")
    atividades, cluster_log = clusterizar(sessoes, complete_fn, orc)
    if complete_fn is not None:
        inferir_n3(reg, complete_fn, orc, model=model)
        hipotetizar_n4(reg, complete_fn, orc, model=model)
        if orc.negadas:
            degradacoes.append(
                f"orçamento LLM esgotado: {orc.negadas} chamadas negadas "
                f"(teto {orc.teto})")

    agora_ts = agora_ts or datetime.now(tz=timezone.utc).timestamp()
    padroes = fold_padroes(reg, agora_ts)
    ts_all = [t for s in sessoes for t in s["ts_todos"]]
    janela = {"de": _iso(min(ts_all)) if ts_all else None,
              "ate": _iso(max(ts_all)) if ts_all else None,
              "criterio": f"mtime nos últimos {janela_dias} dias"}
    cobertura = montar_cobertura([host], len(sessoes), puladas, janela)

    # índice N2 por sessão → atividade
    n2_por_sessao = defaultdict(list)
    for n2 in reg.nivel(2):
        for sid in n2["sessoes"]:
            n2_por_sessao[sid].append(n2["id"])
    for atv in atividades:
        atv["n2_ids"] = sorted({i for sid in atv["session_ids"]
                                for i in n2_por_sessao.get(sid, [])})
        voz = sum(t["n_eventos_voz"] for t in atv["sessions"])
        aca = sum(t["n_eventos_acao"] for t in atv["sessions"])
        atv["voz_acao"] = {"voz": voz, "acao": aca, "unidade": "eventos",
                           "nota": "proporção de EVENTOS por trilho; não é "
                                   "tempo nem tokens"}
        atv["cobertura"] = cobertura

    projecao = {
        "gerado_em": datetime.now(tz=timezone.utc).isoformat(),
        "cluster_version": CLUSTER_VERSION,
        "detector_version": DETECTOR_VERSION,
        "thresholds": THRESHOLDS,
        "cobertura": cobertura,
        "degradacoes": degradacoes,
        "orcamento_llm": orc.dump(),
        "atividades": atividades,
        "cluster_log": cluster_log,
        "padroes": padroes,
        "contagens": {f"n{n}": len(reg.nivel(n)) for n in (1, 2, 3, 4)},
        "eval_estagio0": None}
    return reg, projecao


def persistir(state_dir, reg, projecao):
    state = _guard_estado(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    avisos = []
    ordem = sorted(reg.by_id.values(), key=lambda r: (r["nivel"], r["id"]))
    with open(state / "atividades.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"tipo": "run", "gerado_em": projecao["gerado_em"],
                             "detector_version": DETECTOR_VERSION,
                             "cluster_version": CLUSTER_VERSION},
                            ensure_ascii=False) + "\n")
        for rec in ordem:
            linha = json.dumps(rec, ensure_ascii=False, sort_keys=True)
            hits = achados_de_segredo(linha)
            if hits:  # cinto-e-suspensório: nunca persistir; redigir e avisar
                linha = redigir(linha)
                avisos.append({"id": rec["id"], "redaction_tardia": len(hits)})
            fh.write(linha + "\n")
    if avisos:
        projecao.setdefault("degradacoes", []).append(
            f"redaction tardia aplicada em {len(avisos)} registros "
            "(deveria ter ocorrido na ingestão; investigar)")
        projecao["avisos_redaction"] = avisos
    proj_txt = json.dumps(projecao, ensure_ascii=False, indent=1, sort_keys=True)
    proj_txt = redigir(proj_txt)
    (state / "atividades.json").write_text(proj_txt, encoding="utf-8")
    return state


# ---------------------------------------------------------------------------
# Renderer — proíbe "não ocorreu"; N4 proposta só como pergunta
# ---------------------------------------------------------------------------

class RendererViolation(Exception):
    pass


_FRASES_PROIBIDAS = ("não ocorreu", "nao ocorreu", "não aconteceu",
                     "nao aconteceu")


def _esc(s):
    return _html.escape(redigir(str(s if s is not None else "")))


def _vb(s):
    """Verbatim do operador — escapado, redigido, marcado (fora do guard)."""
    return f'<span class="vb">{_esc(s)}</span>'


def render_report(reg, projecao, eval_estagio0=None):
    cob = projecao["cobertura"]
    aus = ausencia(cob)
    eval_por_forma = (eval_estagio0 or {}).get("por_forma", {})

    def veredicto(forma):
        if not eval_estagio0:
            return "experimental (estágio 0 pendente)"
        v = eval_por_forma.get(forma, {}).get("veredicto")
        if v == "confiavel":
            return "confiavel"
        if v == "experimental":
            return "experimental (estágio 0 reprovado)"
        return "experimental (não amostrado no estágio 0)"

    n4s = reg.nivel(4)
    n3s = {r["id"]: r for r in reg.nivel(3)}
    H = []
    H.append("<meta charset='utf-8'><title>Registro de Atividades — análise "
             "profunda (v2)</title><style>body{font-family:system-ui;margin:2em "
             "auto;max-width:60em;line-height:1.5;padding:0 1em}code,.anc{font-"
             "family:monospace;font-size:.85em;background:#f2f2f2;padding:0 "
             ".3em}.vb{background:#fffbe6;font-style:italic}table{border-"
             "collapse:collapse}td,th{border:1px solid #ccc;padding:.3em .6em;"
             "text-align:left}h2{border-bottom:1px solid #ddd;padding-bottom:"
             ".2em}.aviso{color:#8a6d3b;background:#fcf8e3;padding:.5em}"
             ".exp{color:#777}</style>")
    H.append("<h1>Registro de Atividades — análise profunda</h1>")
    H.append(f"<p>Gerado em {_esc(projecao['gerado_em'])} · detectores "
             f"<code>{_esc(DETECTOR_VERSION)}</code> · clustering "
             f"<code>{_esc(CLUSTER_VERSION)}</code></p>")

    # Cobertura (seção fixa)
    H.append("<h2>Cobertura</h2>")
    H.append(f"<p>Hosts varridos: <b>{_esc(', '.join(cob['hosts_varridos']))}"
             f"</b> · sessões parseadas: {cob['sessoes_parseadas']} · janela: "
             f"{_esc(cob['janela'].get('de'))} → {_esc(cob['janela'].get('ate'))} "
             f"({_esc(cob['janela'].get('criterio'))})</p>")
    if cob["sessoes_puladas"]:
        H.append("<p>Sessões/arquivos pulados:</p><ul>")
        for p in cob["sessoes_puladas"]:
            H.append(f"<li><code>{_esc(p['arquivo'])}</code> — "
                     f"{_esc(p['razao'])}</li>")
        H.append("</ul>")
    H.append(f"<p class='aviso'>Tudo que não aparece neste relatório: "
             f"{_esc(aus)}. Ausência de registro nunca é registro de "
             f"ausência.</p>")
    for d in projecao.get("degradacoes", []):
        H.append(f"<p class='aviso'>Degradação declarada: {_esc(d)}</p>")

    # Por Atividade
    H.append("<h2>Atividades</h2>")
    for atv in projecao["atividades"]:
        H.append(f"<h3>{_esc(atv['nome'])}</h3>")
        H.append(f"<p><code>{_esc(atv['ulid'])}</code> · estado "
                 f"{_esc(atv['estado'])} · hosts {_esc(', '.join(atv['hosts']))}"
                 f" · cwd <code>{_esc(atv['cwd'])}</code></p>")
        va = atv["voz_acao"]
        H.append(f"<p>voz×ação: {va['voz']}×{va['acao']} "
                 f"(unidade: {va['unidade']}; {_esc(va['nota'])})</p>")
        H.append("<table><tr><th>sessão</th><th>início</th><th>fim</th>"
                 "<th>min ativos (teto 300s)</th><th>sens. 120/600s</th>"
                 "<th>voz</th><th>ação</th><th>commits</th></tr>")
        for t in atv["sessions"]:
            ma = t["min_ativos"]
            sens = ma["sensibilidade"]
            H.append(
                f"<tr><td><code>{_esc(t['session_id'][:8])}</code></td>"
                f"<td>{_esc((t['ts_start'] or '')[:16])}</td>"
                f"<td>{_esc((t['ts_end'] or '')[:16])}</td>"
                f"<td>{ma['minutos']}</td>"
                f"<td>{sens.get('cap_120s')}/{sens.get('cap_600s')}</td>"
                f"<td>{t['n_eventos_voz']}</td>"
                f"<td>{t['n_eventos_acao']} ({t['n_eventos_acao_sidechain']} "
                f"sidechain)</td>"
                f"<td>{_esc(', '.join(c[:7] for c in t['commits'][:6]))}"
                f"</td></tr>")
        H.append("</table>")
        # N2 navegáveis até a âncora
        confiaveis = [i for i in atv["n2_ids"]
                      if veredicto(reg.by_id[i]["forma"]) == "confiavel"]
        outros = [i for i in atv["n2_ids"] if i not in set(confiaveis)]
        if confiaveis:
            H.append("<p>Correlações (N2, estágio 0: confiáveis) — contagem "
                     "descritiva com instâncias; nunca diagnóstico:</p><ul>")
            for i in confiaveis:
                H.append("<li>" + _linha_n2(reg, reg.by_id[i]) + "</li>")
            H.append("</ul>")
        if outros:
            H.append("<details><summary class='exp'>Correlações "
                     "experimentais (fora do relatório principal) — "
                     f"{len(outros)}</summary><ul>")
            for i in outros:
                n2 = reg.by_id[i]
                H.append(f"<li class='exp'>{_esc(n2['forma'])} "
                         f"[{_esc(veredicto(n2['forma']))}] — "
                         + _linha_n2(reg, n2) + "</li>")
            H.append("</ul></details>")
        if not atv["n2_ids"]:
            H.append(f"<p>Correlações: {_esc(aus)}.</p>")

    # Padrões
    H.append("<h2>Padrões (o que se repete)</h2>")
    H.append("<p>Padrão cita instâncias, nunca as substitui. Estado "
             "<code>mesma-cena</code> = ainda sem diversidade (≥2 sessões ou "
             "≥2 dias).</p>")
    H.append("<table><tr><th>forma</th><th>n</th><th>diversidade "
             "(sessões/dias/hosts)</th><th>first→last</th><th>estado</th>"
             "<th>estágio 0</th></tr>")
    for p in projecao["padroes"]:
        d = p["diversidade"]
        H.append(f"<tr><td>{_esc(p['forma'])}</td><td>{p['n']}</td>"
                 f"<td>{d['sessoes']}/{d['dias']}/{d['hosts']}</td>"
                 f"<td>{_esc((p['first_seen'] or '')[:10])}→"
                 f"{_esc((p['last_seen'] or '')[:10])}</td>"
                 f"<td>{_esc(p['estado'])}</td>"
                 f"<td>{_esc(veredicto(p['forma']))}</td></tr>")
    H.append("</table>")
    if not projecao["padroes"]:
        H.append(f"<p>Padrões: {_esc(aus)}.</p>")

    # Estágio 0
    H.append("<h2>Estágio 0 — avaliação cega dos detectores</h2>")
    if eval_estagio0:
        tc = eval_estagio0["thresholds_congelados"]
        H.append(f"<p>Rotuladores cegos: {_esc(', '.join(eval_estagio0['rotuladores']))} · "
                 f"amostra {eval_estagio0['amostra']} · thresholds congelados "
                 f"antes da rodada: precisão ≥ {tc['precisao_min']}, "
                 f"concordância ≥ {tc['concordancia_min']}.</p>")
        H.append("<table><tr><th>forma</th><th>n</th><th>precisão</th>"
                 "<th>concordância (p_o)</th><th>κ</th><th>veredicto</th></tr>")
        for forma, f in sorted(eval_estagio0["por_forma"].items()):
            H.append(f"<tr><td>{_esc(forma)}</td><td>{f['n']}</td>"
                     f"<td>{f['precisao'] if f['precisao'] is not None else '—'}"
                     f"</td><td>{f['concordancia']}</td>"
                     f"<td>{f.get('kappa') if f.get('kappa') is not None else '—'}</td>"
                     f"<td>{_esc(f['veredicto'])}</td></tr>")
        H.append("</table>")
        g = eval_estagio0.get("global") or {}
        if g:
            H.append(f"<p>Agregado: p_o {g.get('p_o')} · κ de Cohen "
                     f"{g.get('kappa') if g.get('kappa') is not None else '—'} "
                     f"(3 classes, {g.get('n_pares')} pares). "
                     f"{_esc(g.get('nota', ''))}</p>")
        H.append("<p>O caso 7fed4159/17s é TESTE DE REGRESSÃO do detector "
                 "genérico, nunca evidência de validade.</p>")
    else:
        H.append(f"<p>Estágio 0 ainda não executado — TODAS as formas estão "
                 f"marcadas experimentais. Métricas: {_esc(aus)}.</p>")

    # N3
    if n3s:
        H.append("<h2>Inferências (N3) — com incerteza declarada</h2><ul>")
        for n3 in sorted(n3s.values(), key=lambda r: -r["confianca"]):
            alts = "; ".join(n3["alternativas"])
            H.append(f"<li>{_esc(n3['claim'])} <i>(confiança "
                     f"{n3['confianca']:.2f}; alternativas inocentes: "
                     f"{_esc(alts)}; base {_esc(', '.join(n3['base']))})</i></li>")
        H.append("</ul>")

    # N4 — SÓ perguntas quando proposta
    H.append("<h2>Perguntas ao operador (hipóteses N4 — a sua correção "
             "vence)</h2>")
    if n4s:
        H.append("<ul>")
        for n4 in n4s:
            if n4["status"] == "confirmada":
                H.append(f"<li>[confirmada] {_esc(n4['hipotese'])}</li>")
            elif n4["status"] in ("contestada", "expirada"):
                H.append(f"<li class='exp'>[{_esc(n4['status'])}] "
                         f"{_esc(n4['hipotese'])}</li>")
            else:
                hip = str(n4["hipotese"]).strip()
                if not hip.endswith("?"):
                    hip = hip.rstrip(".") + " — confere?"
                H.append(f"<li><b>Pergunta:</b> {_esc(hip)} "
                         f"<i>(o que a derrubaria: "
                         f"{_esc(n4['falsificacao'])})</i></li>")
        H.append("</ul>")
    else:
        H.append(f"<p>Hipóteses N4: {_esc(aus)} — sem completer ou sem base "
                 f"N3 nesta rodada.</p>")

    # Limites (seção fixa — Codex #9, #23)
    H.append("<h2>Limites desta medição</h2><ul>"
             "<li>O que ela NÃO vê: trabalho fora do terminal (leitura, papel, "
             "conversa, outra tela), revisão silenciosa, sessões fora da "
             "janela/hosts varridos, qualquer coisa apagada por compaction do "
             "jsonl.</li>"
             "<li>Correlação temporal não é causalidade: cada N2 descreve uma "
             "SEQUÊNCIA; a leitura cognitiva vive em N3/N4 com incerteza e "
             "alternativas.</li>"
             "<li>Como ela pode ser jogada: turnos artificialmente longos, "
             "pausas para burlar o teto de gap, commits fragmentados. Por isso "
             "contagens NUNCA são meta nem score do operador.</li>"
             "<li>Agência sem sinal mecânico fica <code>desconhecido</code> — "
             "nunca é chutada.</li></ul>")

    html_final = "\n".join(H)
    guard = re.sub(r"<span class=\"vb\">.*?</span>", "", html_final, flags=re.S)
    baixo = guard.lower()
    for frase in _FRASES_PROIBIDAS:
        if frase in baixo:
            raise RendererViolation(
                f"renderer produziu frase proibida fora de verbatim: {frase!r}")
    return html_final


def _linha_n2(reg, n2):
    ancs = []
    for iid in n2["instancias"][:4]:
        n1 = reg.by_id[iid]
        ev = n1["evidencia"]
        extra = f" commit {ev['commit_hash'][:7]}" if ev.get("commit_hash") else ""
        ag = n1.get("agencia")
        agtxt = (f" · agência: executor={ag['executor']}, "
                 f"autorização={ag['autorizacao']}" if ag else "")
        rotulo = n1["conteudo_redigido"].get("texto") \
            if n1["kind"] == "voz-turno" else \
            f"{n1['conteudo_redigido'].get('tool', n1['kind'])}" \
            f"({n1['conteudo_redigido'].get('classe', '')})"
        vb = _vb(rotulo[:60]) if n1["kind"] == "voz-turno" else _esc(rotulo)
        ancs.append(f"{vb} <span class='anc'>{_esc(ev['arquivo_jsonl'])}:"
                    f"{ev['linha']}{_esc(extra)}</span>{_esc(agtxt)}")
    obs = {k: v for k, v in n2["params"].items()
           if k not in THRESHOLDS[n2["forma"]]}
    return (f"<code>{_esc(n2['forma'])}</code> "
            f"[{_esc(n2['janela']['de'][:16])}] {_esc(json.dumps(obs, ensure_ascii=False))}"
            f"<br>&nbsp;&nbsp;instâncias: " + " ; ".join(ancs))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _complete_cmd_fn(cmd):
    def f(prompt):
        r = subprocess.run(cmd, shell=True, input=prompt,
                           capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            raise RuntimeError(f"complete-cmd falhou: {r.stderr[:200]}")
        return r.stdout
    return f


def _carregar_estado(state_dir):
    state = Path(state_dir)
    projecao = json.loads((state / "atividades.json").read_text())
    reg = Registry()
    with open(state / "atividades.jsonl", encoding="utf-8") as fh:
        for linha in fh:
            rec = json.loads(linha)
            if rec.get("nivel") in (1, 2, 3, 4):
                reg.add(rec)
    return reg, projecao


def _cmd_backfill(args):
    complete_fn = _complete_cmd_fn(args.complete_cmd) if args.complete_cmd else None
    reg, projecao = pipeline(args.workdir, args.host, complete_fn,
                             janela_dias=args.janela_dias,
                             model=args.complete_cmd or "nenhum")
    state = persistir(args.state, reg, projecao)
    html = render_report(reg, projecao, None)
    (state / "report.html").write_text(html, encoding="utf-8")
    print(json.dumps({"state": str(state), **projecao["contagens"],
                      "atividades": len(projecao["atividades"]),
                      "padroes": len(projecao["padroes"]),
                      "degradacoes": projecao["degradacoes"],
                      "orcamento_llm": projecao["orcamento_llm"]},
                     ensure_ascii=False, indent=1))


def _cmd_eval(args):
    state = Path(args.state)
    reg, projecao = _carregar_estado(state)
    if args.acao == "prepare":
        amostra = eval_preparar(reg, args.workdir, max_amostra=args.max)
        Path(args.out).write_text(redigir(json.dumps(
            amostra, ensure_ascii=False, indent=1)), encoding="utf-8")
        print(f"amostra: {len(amostra['itens'])} itens → {args.out}")
    else:  # ingest
        amostra = json.loads(Path(args.amostra).read_text())
        la = json.loads(Path(args.labels[0]).read_text())
        lb = json.loads(Path(args.labels[1]).read_text())
        ev = eval_ingerir(amostra, la, lb)
        _guard_estado(state)
        (state / "eval.json").write_text(
            json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
        projecao["eval_estagio0"] = ev
        (state / "atividades.json").write_text(redigir(json.dumps(
            projecao, ensure_ascii=False, indent=1, sort_keys=True)),
            encoding="utf-8")
        html = render_report(reg, projecao, ev)
        (state / "report.html").write_text(html, encoding="utf-8")
        print(json.dumps(ev["por_forma"], ensure_ascii=False, indent=1))


def _cmd_list(args):
    _, projecao = _carregar_estado(args.state)
    for atv in projecao["atividades"]:
        print(f"{atv['ulid']}  {len(atv['sessions'])} sessões  "
              f"voz×ação {atv['voz_acao']['voz']}×{atv['voz_acao']['acao']}  "
              f"{atv['nome'][:60]}")


def _cmd_show(args):
    reg, projecao = _carregar_estado(args.state)
    for atv in projecao["atividades"]:
        if atv["ulid"] == args.atividade or args.atividade in atv["nome"]:
            print(json.dumps(atv, ensure_ascii=False, indent=1))
            for i in atv["n2_ids"]:
                print(json.dumps(reg.by_id[i], ensure_ascii=False))
            return
    print("atividade não encontrada", file=sys.stderr)
    sys.exit(1)


def _cmd_report(args):
    reg, projecao = _carregar_estado(args.state)
    ev = None
    evp = Path(args.state) / "eval.json"
    if evp.exists():
        ev = json.loads(evp.read_text())
    html = render_report(reg, projecao, ev)
    out = Path(args.out or (Path(args.state) / "report.html"))
    _guard_estado(out.parent)
    out.write_text(html, encoding="utf-8")
    print(out)


def _cmd_scan(args):
    linhas = []
    for pat in args.glob:
        for f in sorted(_glob.glob(pat)):
            s = scan_arquivo(f, args.host)
            if not s["vozes"]:
                continue
            linhas.append({
                "session": s["session_id"][:8],
                "min_ativos": round(tempo_ativo_s(
                    s["ts_todos"], MIN_ATIVOS_CAP_S) / 60, 1),
                "voz": len([e for e in s["eventos"]
                            if e["kind"] == "voz-turno"]),
                "acao": len([e for e in s["eventos"]
                             if e["kind"] != "voz-turno"]),
                "abertura": s["abertura"][:80]})
    print(json.dumps(linhas, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="atividades",
        description="Registro de Atividades — 4 níveis epistemológicos (v2)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="varre jsonl e imprime resumo por sessão")
    p.add_argument("glob", nargs="+")
    p.add_argument("--host", default="?")
    p.set_defaults(fn=_cmd_scan)

    p = sub.add_parser("backfill", help="pipeline completo sobre cópia de "
                       "trabalho redigida")
    p.add_argument("--workdir", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--janela-dias", type=int, default=7)
    p.add_argument("--complete-cmd", default=None,
                   help="comando shell: prompt no stdin → completion no stdout "
                        "(seam complete_fn); ausente → N2-only declarado")
    p.set_defaults(fn=_cmd_backfill)

    p = sub.add_parser("eval", help="estágio 0 — avaliação cega")
    p.add_argument("acao", choices=["prepare", "ingest"])
    p.add_argument("--state", required=True)
    p.add_argument("--workdir", help="cópia de trabalho (prepare)")
    p.add_argument("--out", help="arquivo da amostra (prepare)")
    p.add_argument("--amostra", help="arquivo da amostra (ingest)")
    p.add_argument("--labels", nargs=2, help="dois arquivos de rótulos (ingest)")
    p.add_argument("--max", type=int, default=30)
    p.set_defaults(fn=_cmd_eval)

    p = sub.add_parser("list")
    p.add_argument("--state", required=True)
    p.set_defaults(fn=_cmd_list)

    p = sub.add_parser("show")
    p.add_argument("atividade")
    p.add_argument("--state", required=True)
    p.set_defaults(fn=_cmd_show)

    p = sub.add_parser("report")
    p.add_argument("--state", required=True)
    p.add_argument("--out", default=None)
    p.set_defaults(fn=_cmd_report)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()

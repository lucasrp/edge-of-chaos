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
# R4 item 3: o antecedente (proposta do assistant) EXPIRA — aceite 3h depois
# ou com tool calls no meio não é adjacência DAMSL
ANTECEDENTE_EXPIRA_S = 300.0

# ---------------------------------------------------------------------------
# R5: TRECHO — o grão de afiliação ("a sessão pode ter várias atividades").
# Sessão = contêiner físico; trecho = [ts_start, ts_end) de eventos dentro
# dela; Atividade = cluster de TRECHOS cross-sessão/host. Cortes MECÂNICOS
# primeiro, versionados; LLM só arbitra corte AMBÍGUO dentro do orçamento.
# ---------------------------------------------------------------------------
SEGMENT_VERSION = "seg-v1.0"
# dig-5 B: 15 min é o corte de retomada consolidado em logs de desenvolvedor
# (Parnin & Rugaber ICPC 2009/11 ≥15min; Sanchez/Cruz 15min, café ~12min;
# Meyer TSE 2017 15min; Astromskis ~14min). Gaps <5min são "pensar" (Xia TSE
# 2018, Minelli); a convenção web de 30min é o erro barato (Catledge&Pitkow).
# Declarado na UI como o teto de 300s do min_ativos.
GAP_CORTE_S = 900.0
# dig-5 A: over-segmentation é o modo default de falha (TextTiling BOR≈1.9-2×
# o gold; Coen 2025) → limiar conservador (estilo HC de Hearst): só corta em
# mudança de cwd SUSTENTADA. N=5 ≈ metade do fragmento de atividade de
# Kevic & Fritz (ICSME 2017, ~8.7 elementos) — digressão de 1-2 eventos não
# corta.
N_CWD_SUSTENTADO = 5
N_CWD_AMBIGUO = 3  # [3,5) eventos no cwd novo = candidato AMBÍGUO (LLM arbitra)
# marcadores explícitos de fronteira na VOZ — lexicon FECHADO e versionado;
# inclui a forma literal do operador ("vamos continuar a atividade 1. a
# atividade 2 ta superada", 03/08)
_RX_MARCADOR_FRONTEIRA = re.compile(
    r"(?i)(?:^(?:agora vamos\b|vamos (?:continuar|voltar|para|pra)\b|"
    r"mudando (?:de|para|pra)\b|voltando (?:ao|à|a |para|pra)\b|"
    r"pr[oó]ximo assunto\b|outra coisa[:,]|mudar de assunto\b|"
    r"fechando (?:a|o)\b|encerrando\b|nova atividade\b)"
    r"|\batividade \d+\b"
    r"|\batividade \d+ (?:ta|tá|est[aá]) (?:superada|encerrada|fechada|"
    r"conclu[ií]da)\b)")

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
    # keyword→valor (gitleaks generic-api-key + detect-secrets KeywordDetector).
    # Finding R1 #9: exigir separador `=`/`:` OU valor com FORMA de segredo
    # (≥8 chars do charset de token contendo dígito) — "token de validação"
    # (prosa) não dispara mais; "token abc123xyz" e "password=hunter2" sim.
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd|bearer|"
               r"credential)\b"
               r"(?:[=:]\s*\S+|\s+(?=\S*\d)[A-Za-z0-9_\-/+=.]{8,})"),
    # tokens nus (formatos conhecidos dos rule sets), sem exigir keyword.
    # Finding R1 #10: famílias completadas — Google AIza, GitLab glpat-,
    # Stripe sk_live_/pk_live_, npm_ (gitleaks.toml traz todas).
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{6,}|sk-ant-[A-Za-z0-9_\-]{6,}"
               r"|ghp_[A-Za-z0-9]{10,}|gho_[A-Za-z0-9]{10,}"
               r"|github_pat_[A-Za-z0-9_]{10,}"
               r"|xox[bapors]-[A-Za-z0-9\-]{5,}"
               r"|AKIA[0-9A-Z]{16}"  # charset detect-secrets ([0-9A-Z]) ⊃ gitleaks ([A-Z2-7])
               r"|AIza[0-9A-Za-z_\-]{35}"
               r"|glpat-[A-Za-z0-9_\-]{20,}"
               r"|(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"
               r"|npm_[A-Za-z0-9]{36}"
               r"|eyJ[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,})"),
    # blocos PEM (BEGIN…END na mesma linha lógica; em jsonl o \n vem escapado)
    re.compile(r"-----BEGIN [A-Z ]{0,24}PRIVATE KEY-----"
               r"(?:.|\\n)*?-----END [A-Z ]{0,24}PRIVATE KEY-----", re.S),
    re.compile(r"-----BEGIN [A-Z ]{0,24}PRIVATE KEY-----\S{0,4096}"),
    # valores de env com nome sensível (KEY/TOKEN/SECRET/PASS/CRED)
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|CRED)[A-Z0-9_]*"
               r"=\S+"),
    # URL com credencial embutida — forma do BasicAuthDetector (detect-secrets
    # basic_auth.py): userinfo sem os delimitadores reservados da RFC 3986 §2.2.
    # gitleaks NÃO tem regra genérica scheme://user:pass@ (dig-1, perna A).
    re.compile(r"://[^:/?#\[\]@!$&'()*+,;=\s]+:[^:/?#\[\]@!$&'()*+,;=\s]+@"),
    # NEW-1 (dig-3 perna A): credencial em FLAG de CLI (gitleaks curl-auth /
    # trufflehog: keyword+context é o padrão de campo).
    # Flags longas: o valor é sempre mascarado.
    re.compile(r"(?i)(?<=\s)--(?:password|passwd|pass|token|secret|api-key|"
               r"auth-token)(?:[= ]\s*)(?!-)\S+"),
    # -p/-P curtas (cypher-shell/mysql/psql): só valor com CARA de segredo
    # (≥8 chars, letra+dígito, sem '/', charset de token) — `mkdir -p /x` e
    # `ssh -p 22` não disparam.
    re.compile(r"(?<=\s)-[pP]\s+(?=\S*\d)(?=\S*[A-Za-z])"
               r"[A-Za-z0-9+_=.\-]{8,}(?=\s|$)"),
    # curl-style -u user:pass
    re.compile(r"(?<=\s)-u\s+[^\s:@/]+:\S+"),
]

# --- NEW-1, camada de ENTROPIA (dig-3 perna A: detect-secrets
# HexHighEntropyString default H>3.0; Base64HighEntropyString H>4.5; gitleaks
# decode hex≥32/b64; UUID hifenizado filtrado por forma). Aplicada SÓ a campos
# de CONTEÚDO (voz, comandos, cargas do eval) — nunca à serialização de
# registros, cujos campos de evidência carregam sha1/sha256 legítimos (o erro
# do generic do trufflehog é banir 64-hex nu; aqui o hash de evidência é dado).
_RX_HEX_LONGO = re.compile(r"\b[a-fA-F0-9]{32,}\b")
# R4 item 2 (NEWER-1): SEM `/` e SEM `-` no charset — um path
# (/tmp/claude-…/tasks/x.output) virava um token gigante de "b64" e era
# mascarado, fundindo cabeças de comando distintas num grupo D3 fabricado.
# Segmento de path fica tokenizado nas barras/hífens; segredo b64 real ≥24
# entre separadores continua caindo.
_RX_B64_LONGO = re.compile(r"\b[A-Za-z0-9+][A-Za-z0-9+=_]{23,}\b")


def _entropia_shannon(s):
    if not s:
        return 0.0
    contagens = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in contagens.values())


def _mascarar_entropia(texto):
    def _hex(m):
        t = m.group(0)
        return _MASK if _entropia_shannon(t) > 3.0 else t

    def _b64(m):
        t = m.group(0)
        if re.fullmatch(r"[a-fA-F0-9]+", t) or "-" in t and re.fullmatch(
                r"[0-9a-fA-F\-]+", t):
            return t  # hex puro já tratado; forma de UUID não é segredo b64
        return _MASK if _entropia_shannon(t) > 4.5 else t

    texto = _RX_HEX_LONGO.sub(_hex, texto)
    texto = _RX_B64_LONGO.sub(_b64, texto)
    return texto
_MASK = "***"


def redigir(texto, entropia=False):
    """Substitui padrões de segredo por *** — chamada na INGESTÃO, sempre.

    `entropia=True` liga a camada de alta-entropia (NEW-1) para campos de
    CONTEÚDO (voz, comandos, cargas do eval). Fica desligada na serialização
    de registros inteiros, onde sha1/sha256 de evidência são dados legítimos
    (dig-3 perna A: contexto separa hash de password, não o alfabeto)."""
    if not texto:
        return texto
    for rx in _RE_SEGREDOS:
        texto = rx.sub(_MASK, texto)
    if entropia:
        texto = _mascarar_entropia(texto)
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
        # colisão de id (finding R1 #17): sobrescrever silenciosamente é
        # proibido; re-add idempotente do MESMO conteúdo é permitido
        existente = self.by_id.get(rec.get("id"))
        if existente is not None and existente != rec:
            raise CitacaoInvalida(
                f"{rec['id']}: id duplicado com conteúdo divergente")
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


# Classificação de comando POR SEGMENTO (finding R1 #1; dig-2 perna A: prática
# consolidada Codex `is_safe_git_command` / Claude Code read-only classifiers —
# split em `&&`/`||`/`;`/`|`, classificar cada segmento, RO só se TODOS RO;
# redirect julgado por fd/destino: `2>/dev/null`/`2>&1` NÃO são escrita,
# `> /dev/null` não persiste nada, `> arquivo` sim; git com allowlist de
# subcomandos de leitura).

_RX_ASPAS = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`")
_RX_SEP_SEGMENTO = re.compile(r"&&|\|\||;|\|&|\|")
_RX_STDERR_REDIR = re.compile(r"\d+>&\d+|\d+>>?\s*\S+|>&\d+")
_RX_REDIR_SAIDA = re.compile(r"(?:&>>?|>>|(?<![<>])>(?!>))\s*(\S+)")
_DEV_SAIDAS_INOCUAS = frozenset(("/dev/null", "/dev/stdout", "/dev/stderr",
                                 "/dev/tty"))
_GIT_LEITURA = frozenset(("status", "log", "diff", "show", "blame", "describe",
                          "rev-parse", "ls-files", "ls-remote", "shortlog",
                          "reflog", "grep"))
_GIT_BRANCH_FLAGS_RO = frozenset(("-a", "-r", "-v", "-vv", "--list",
                                  "--show-current", "--contains", "--merged"))
# NEW-2: `ssh` NÃO é mais head de leitura — o comando remoto é classificado
# recursivamente (dig-3 perna B: payload remoto nunca herda "safe" sem parse;
# unparseable → unknown/execucao, nunca leitura)
_LEITURA_HEADS = frozenset(("cat ls head tail grep rg find wc ps df du stat "
                            "file which env jq sed awk tree diff sort uniq cut "
                            "tr pgrep pstree top free uptime date md5sum sha1sum "
                            "sha256sum hostname whoami pwd echo printf test "
                            "readlink basename dirname uname getent id nproc "
                            "curl less more column comm strings xxd od").split())
_ESCRITA_PALAVRAS = re.compile(
    r"\b(tee|mv|cp|rm|rmdir|mkdir|touch|ln|chmod|chown|truncate|dd|rsync|scp)\b"
    r"|\bsed\s+(-[a-zA-Z]*\s+)*-i\b"
    r"|\b(pip3?|npm|apt|apt-get|cargo|yarn|pnpm)\s+(install|add|remove|update)\b"
    r"|\bcurl\b[^|;&]*\s(-o|-O|--output)\b"
    r"|\bwget\b(?![^|;&]*-q?O\s*-)")
_WRAPPERS_1 = frozenset(("sudo", "nohup", "time", "nice", "command"))


# NEW-2 (dig-3 perna B): payloads entre aspas são EXTRAÍDOS LITERALMENTE
# (nunca shlex+rejoin — o pitfall do unwrap) e o comando interno de
# ssh/bash -c/docker exec é classificado recursivamente; herdar `leitura`
# exige parse limpo do payload; payload ilegível/vazio → execucao (unknown).
_RX_ASPAS_CAPTURA = re.compile(r"'([^']*)'|\"([^\"]*)\"|`([^`]*)`")
_RX_PLACEHOLDER = re.compile(r"__Q(\d+)__")
# flags do ssh que consomem argumento (dig-3 B: "flags que comem argumento")
_SSH_FLAGS_COM_ARG = frozenset(("-o", "-i", "-p", "-l", "-F", "-E", "-J",
                                "-L", "-R", "-D", "-W", "-b", "-c", "-e",
                                "-m", "-Q", "-S"))
_DOCKER_FLAGS_COM_ARG = frozenset(("-e", "--env", "-u", "--user", "-w",
                                   "--workdir", "--name", "--network",
                                   "--entrypoint"))
_DOCKER_LEITURA = frozenset(("ps", "images", "inspect", "logs", "top",
                             "stats", "version", "info", "diff"))


def _com_placeholders(cmd):
    payloads = []

    def _sub(m):
        payloads.append(next(g for g in m.groups() if g is not None))
        return f" __Q{len(payloads) - 1}__ "

    return _RX_ASPAS_CAPTURA.sub(_sub, cmd or ""), payloads


def _restaurar(toks, payloads):
    partes = []
    for t in toks:
        m = _RX_PLACEHOLDER.fullmatch(t)
        partes.append(payloads[int(m.group(1))] if m else t)
    return " ".join(partes)


def _classificar_segmento(seg, payloads, prof):
    s = seg.strip()
    if not s:
        return None
    sem_stderr = _RX_STDERR_REDIR.sub(" ", s)
    toks = sem_stderr.split()
    while toks:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]):
            toks = toks[1:]  # prefixos VAR=val
        elif toks[0] in _WRAPPERS_1 or toks[0] == "env":
            toks = toks[1:]
        elif toks[0] == "timeout":
            toks = toks[1:]
            if toks and toks[0] == "-k":
                toks = toks[2:]
            if toks and re.match(r"^\d+[smhd]?$", toks[0]):
                toks = toks[1:]
        else:
            break
    if not toks:
        return None
    head = toks[0].rsplit("/", 1)[-1]

    if head == "git":
        sub = toks[1] if len(toks) > 1 else ""
        resto = toks[2:]
        if sub.startswith("-"):
            # flag global (-C/--git-dir/-c/--paginate…): Codex trata como
            # não-RO — conservador, vira escrita (dig-2 perna A)
            return "escrita"
        if sub in ("commit", "push"):
            return "commit"
        if sub in _GIT_LEITURA:
            return "leitura"
        if sub == "branch" and all(t in _GIT_BRANCH_FLAGS_RO for t in resto):
            return "leitura"
        if sub == "stash" and resto[:1] in (["list"], ["show"]):
            return "leitura"
        if sub == "remote" and (not resto or resto[0] in ("-v", "show")):
            return "leitura"
        return "escrita"  # add/checkout/switch/merge/rebase/stash/fetch/pull…

    if head == "ssh":
        resto = toks[1:]
        while resto and resto[0].startswith("-"):
            resto = resto[2:] if resto[0] in _SSH_FLAGS_COM_ARG else resto[1:]
        resto = resto[1:]  # host
        if not resto:
            return "execucao"  # ssh interativo/ilegível: unknown, não leitura
        return classificar_comando(_restaurar(resto, payloads), prof + 1)

    if head in ("bash", "sh", "zsh", "dash"):
        if "-c" in toks:
            i = toks.index("-c")
            if i + 1 < len(toks):
                # R4 item 4: payload COMPLETO após -c (o recorte [i+1:i+2]
                # perdia o resto quando o unwrap externo já tinha diluído as
                # aspas — `docker exec c sh -c "echo ok > f"`)
                return classificar_comando(
                    _restaurar(toks[i + 1:], payloads), prof + 1)
        return "execucao"

    if head == "docker":
        sub = toks[1] if len(toks) > 1 else ""
        if sub in _DOCKER_LEITURA:
            return "leitura"
        if sub in ("exec", "run"):
            resto = toks[2:]
            while resto and resto[0].startswith("-"):
                resto = (resto[2:] if resto[0] in _DOCKER_FLAGS_COM_ARG
                         else resto[1:])
            resto = resto[1:]  # container/imagem
            if not resto:
                return "execucao"
            return classificar_comando(_restaurar(resto, payloads), prof + 1)
        return "execucao"

    m = _RX_REDIR_SAIDA.search(sem_stderr)
    if m and m.group(1) not in _DEV_SAIDAS_INOCUAS:
        return "escrita"
    if _ESCRITA_PALAVRAS.search(sem_stderr):
        return "escrita"
    if "$(" in sem_stderr:  # substituição embutida: não afirmar leitura
        return "execucao"
    if head in _LEITURA_HEADS:
        return "leitura"
    return "execucao"


_PRIORIDADE_CLASSE = {"commit": 3, "escrita": 2, "execucao": 1, "leitura": 0}


def classificar_comando(cmd, prof=0):
    """Classe do comando inteiro = classe mais privilegiada entre os segmentos
    (RO só se todos os segmentos são RO — dig-2 perna A); comandos aninhados
    (ssh/bash -c/docker exec) classificados recursivamente (NEW-2), com teto
    de profundidade fail-closed."""
    if prof > 3:
        return "execucao"
    texto, payloads = _com_placeholders(cmd)
    classes = [c for c in (_classificar_segmento(seg, payloads, prof)
                           for seg in _RX_SEP_SEGMENTO.split(texto)) if c]
    if not classes:
        return "execucao"
    return max(classes, key=lambda c: _PRIORIDADE_CLASSE[c])


def _texto_de(content):
    """Extrai texto humano de message.content (str ou lista de blocos text)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


# NEW-4 (dig-3 perna C: exclusão por protocol_marker com motivo logado — em
# log de agente "o motivo é o dado"): turnos de despacho/protocolo NÃO são voz
# do operador; marcadores MECÂNICOS de forma, nunca leitura de conteúdo.
_RX_PROTOCOLO = re.compile(
    r"^(AUTHORITATIVE DISPATCH PLAN|Base directory for this skill"
    r"|<command-name>|<system-reminder>)"
    r"|^.{0,200}?AUTHORITATIVE DISPATCH PLAN", re.S)


def _eh_protocolo(texto):
    return bool(_RX_PROTOCOLO.search((texto or "").strip()))


def _eh_voz(entry, texto):
    t = (texto or "").strip()
    if not t or t.startswith("<") or t.startswith("Caveat:") \
            or t.startswith("[Request interrupted"):
        return False
    if _eh_protocolo(t):
        return False
    if entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    origem = (entry.get("origin") or {}).get("kind")
    if origem and origem != "human":
        return False
    return True


# Lexicons FECHADOS e declarados (finding R1 #6; dig-2 perna C: DAMSL/SWBD
# accept/acknowledge vs conventional-opening vs action-directive; prática
# Prow/lgtm = regex-âncora + ANTECEDENTE + identidade — nunca classificador de
# sentimento). `ok` só autoriza com antecedente (proposta do assistant antes).
_GRANT_LEX = frozenset((
    "ok", "okay", "sim", "pode", "vai", "manda", "bora", "dale", "isso",
    "blz", "beleza", "go", "yes", "y", "lgtm", "aprovado", "aprovo",
    "confirmo", "fechou", "fechado", "show", "perfeito", "pode ir",
    "pode sim", "vai la", "vai lá", "manda ver", "manda bala", "ship it",
    "go ahead", "faz isso", "isso mesmo", "toca"))
_GREETING_LEX = frozenset((
    "oi", "iae", "eai", "e ai", "e aí", "opa", "ola", "olá", "hey", "hi",
    "hello", "salve", "bom dia", "boa tarde", "boa noite", "fala"))
_IMPERATIVO_V1 = frozenset((
    # PT (2ª/3ª sing.) + EN, verbo-inicial = action-directive (SWBD-DAMSL)
    "faz", "faça", "roda", "rode", "cria", "crie", "publica", "publique",
    "escreve", "escreva", "commita", "commit", "sobe", "suba", "aplica",
    "aplique", "executa", "execute", "gera", "gere", "corrige", "corrija",
    "adiciona", "adicione", "remove", "remova", "deleta", "delete",
    "atualiza", "atualize", "testa", "teste", "instala", "instale", "abre",
    "abra", "fecha", "feche", "muda", "mude", "troca", "troque", "usa",
    "use", "manda", "mande", "termina", "termine", "continua", "continue",
    "refaz", "refaça", "conserta", "conserte", "implementa", "implemente",
    "run", "make", "create", "write", "push", "apply", "fix", "add",
    "update", "install", "generate", "deploy", "refactor", "build", "start",
    "stop", "merge", "rebase", "revert"))


def _normalizar_voz(texto):
    return re.sub(r"[\s]+", " ",
                  re.sub(r"[.!,;…]+$", "", (texto or "").strip().lower()))


def derivar_agencia(ts_acao, sidechain, vozes):
    """Mecânica, nunca chutada (Codex #10; finding R1 #6).

    executor: 'agente' — tool calls no transcript são executados pelo agente.
    autorizacao:
      sidechain → 'autonomo';
      turno humano ≤120s antes que seja (a) aceite do lexicon fechado COM
      antecedente de texto do assistant (proposta antes do aceite — trava do
      dig-2/DAMSL), ou (b) imperativo verbo-inicial do lexicon fechado
      → 'autorizado';
      saudação, interrogativa, ou voz sem marcador → 'desconhecido' (voz
      próxima NÃO é autorização; nunca chutado).
    revisao_humana: sem sinal mecânico nas superfícies varridas →
      'desconhecido'.

    `vozes`: lista de (ts, texto, tem_antecedente_assistant).
    """
    if sidechain:
        return {"executor": "agente", "autorizacao": "autonomo",
                "revisao_humana": "desconhecido", "regra": "sidechain"}
    aut, regra = "desconhecido", "sem-sinal"
    for ts_voz, texto, tem_antecedente in reversed(vozes):
        if ts_voz is None or ts_acao is None:
            continue
        d = ts_acao - ts_voz
        if ts_voz < ts_acao - 120:
            break
        if not (0 <= d <= 120):
            continue
        t = _normalizar_voz(texto)
        if t.endswith("?"):
            regra = "voz-interrogativa-proxima-nao-autoriza"
            break
        if t in _GREETING_LEX:
            regra = "saudacao-nao-autoriza"
            break
        if t in _GRANT_LEX and tem_antecedente:
            aut = "autorizado"
            regra = f"aceite-lexicon-com-antecedente-{d:.0f}s-antes"
            break
        primeira = t.split(" ", 1)[0] if t else ""
        if primeira in _IMPERATIVO_V1:
            aut = "autorizado"
            regra = f"imperativo-verbo-inicial-{d:.0f}s-antes"
            break
        regra = ("aceite-sem-antecedente-nao-autoriza"
                 if t in _GRANT_LEX else "voz-proxima-sem-marcador")
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
    cwds = Counter()          # cwd MODAL, não o último (finding R1 #18)
    fluxo = []                # R5: stream transiente (ts, linha, cwd) dos
    #                           eventos main-chain — insumo da segmentação;
    #                           nunca persistido
    ts_linhas = []            # R5: (ts, linha) de TODA linha main com ts —
    #                           detecção de gap ancorável em linha
    cabecas_brutas = {}       # R4 item 2: chave de agrupamento D3 vem do
    #                           comando NÃO-redigido; só a cabeça redigida
    #                           persiste (este dict é transiente, nunca sai
    #                           do processo)
    # NEW-6 + R4 item 3: antecedente por ADJACÊNCIA real (DAMSL
    # proposta→aceite), CONSUMÍVEL: guarda o TS do último texto do assistant;
    # é limpo por voz humana E por tool_call intermediário, e expira em
    # ANTECEDENTE_EXPIRA_S — nunca um bool sticky.
    assistant_texto_pendente = None  # ts | None
    turnos_protocolo = 0      # NEW-4: turnos de protocolo/despacho excluídos

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
                ts_linhas.append((ts, linha_n))
            cwd = e.get("cwd") or cwd
            if e.get("cwd"):
                cwds[e["cwd"]] += 1
            eh_side = bool(sidechain or e.get("isSidechain"))
            tipo = e.get("type")
            msg = e.get("message") or {}
            content = msg.get("content")

            if tipo == "user":
                texto = _texto_de(content)
                if not eh_side and _eh_protocolo(texto):
                    turnos_protocolo += 1
                if not eh_side and _eh_voz(e, texto) and ts is not None:
                    texto_red = redigir(texto, entropia=True)[:VERBATIM_CAP]
                    ev = ev_base("voz-turno", ts, linha_n)
                    ev["id"] = _rid("n1", session_id, arquivo_rel, linha_n, "voz")
                    ev["conteudo_redigido"] = {"texto": texto_red,
                                               "chars": len(texto.strip())}
                    eventos.append(ev)
                    fluxo.append((ts, linha_n, cwd))
                    tem_antecedente = (
                        assistant_texto_pendente is not None
                        and 0 <= ts - assistant_texto_pendente
                        <= ANTECEDENTE_EXPIRA_S)
                    vozes.append((ts, texto.strip(), ev["id"], linha_n,
                                  tem_antecedente))
                    assistant_texto_pendente = None  # voz consome a adjacência
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
                    assistant_texto_pendente = ts
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    if ts is None:
                        continue
                    nome = b.get("name") or "?"
                    inp = b.get("input") or {}
                    kind = "spawn" if nome in ("Task", "Agent") else "tool-call"
                    classe, arquivos, cabeca = None, [], None
                    cabeca_bruta = None
                    if nome == "Bash":
                        cmd = inp.get("command") or ""
                        classe = classificar_comando(cmd)
                        cabeca_bruta = " ".join(cmd.strip().split()[:2])[:120]
                        cabeca = redigir(cabeca_bruta, entropia=True)[:80]
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
                        ts, eh_side, [(t, x, a) for t, x, _, _, a in vozes])
                    eventos.append(ev)
                    if not eh_side:
                        fluxo.append((ts, linha_n, cwd))
                        # R4 item 3: tool_call intermediário consome a
                        # adjacência proposta→aceite
                        assistant_texto_pendente = None
                    if cabeca_bruta is not None:
                        cabecas_brutas[ev["id"]] = cabeca_bruta
                    if b.get("id"):
                        pendentes[b["id"]] = (ev, classe)

    abertura = ""
    for _, t, _, _, _ in vozes:
        if len(t) >= 8:
            abertura = redigir(t, entropia=True)[:200]
            break
    if not abertura and vozes:
        abertura = redigir(vozes[0][1], entropia=True)[:200]
    if cwds:
        cwd = cwds.most_common(1)[0][0]  # modal (finding R1 #18)

    return {"session_id": session_id, "host": host, "arquivo": arquivo_rel,
            "sha1": sha1, "cwd": cwd, "sidechain": sidechain,
            "eventos": eventos, "vozes": vozes,
            "assistant_turnos": assistant_turnos, "ts_todos": sorted(ts_todos),
            "abertura": abertura, "linhas_puladas": linhas_puladas,
            "turnos_protocolo": turnos_protocolo,
            "cabecas_brutas": cabecas_brutas, "fluxo": fluxo,
            "ts_linhas": ts_linhas}


def tempo_ativo_s(ts_list, cap):
    ts = sorted(t for t in ts_list if t is not None)
    return sum(min(b - a, cap) for a, b in zip(ts, ts[1:]))


def tempo_ativo_atribuido_s(ts_sessao, ts_ini, ts_fim, cap):
    """R5 (conservação de tempo): cada gap pertence ao trecho onde COMEÇA
    (t_i ∈ [ts_ini, ts_fim)), com o mesmo teto — a soma sobre os trechos de
    uma sessão é EXATAMENTE o cômputo da sessão inteira."""
    ts = sorted(t for t in ts_sessao if t is not None)
    total = 0.0
    for a, b in zip(ts, ts[1:]):
        if a >= ts_ini and (ts_fim is None or a < ts_fim):
            total += min(b - a, cap)
    return total


# ---------------------------------------------------------------------------
# R5 — segmentação da sessão em TRECHOS (cortes mecânicos primeiro,
# versionados; LLM só arbitra candidato AMBÍGUO). Sobre-segmentar é o modo
# default de falha (dig-5 A) — na dúvida, NÃO corta; 1 trecho/sessão é
# resultado honesto.
# ---------------------------------------------------------------------------

def _runs_de_cwd(fluxo):
    """Compressão do fluxo em runs de cwd igual (cwd vazio herda o anterior)."""
    runs = []
    for i, (ts, linha, cwd) in enumerate(fluxo):
        c = cwd or (runs[-1][0] if runs else "")
        if runs and runs[-1][0] == c:
            runs[-1][2] += 1
        else:
            runs.append([c, i, 1])
    return runs  # [cwd, idx_inicial_no_fluxo, n_eventos]


def segmentar(sessao, complete_fn=None, orcamento=None):
    """Sessão → lista de trechos (dicts com a mesma forma de uma sessão,
    para _touch/clusterizar). Sinais de corte, nesta ordem de varredura:

    1. gap de inatividade > GAP_CORTE_S (dig-5 B: 15 min, Parnin/Sanchez/
       Meyer), medido sobre TODOS os timestamps main-chain (assistant
       trabalhando não é inatividade); âncora = linha onde a sessão retoma;
    2. marcador explícito de fronteira na voz (lexicon fechado
       _RX_MARCADOR_FRONTEIRA, versionado em SEGMENT_VERSION);
    3. mudança de cwd SUSTENTADA (≥N_CWD_SUSTENTADO eventos — dig-5 A:
       limiar conservador estilo HC); [N_CWD_AMBIGUO, N_CWD_SUSTENTADO) é
       candidato AMBÍGUO: LLM arbitra dentro do orçamento; sem completer →
       NÃO corta (declarado).

    Reentrada em atividade anterior abre trecho NOVO que clusteriza de volta
    à mesma Atividade (dig-5 C: XES concept:instance / ativações do Mylyn —
    id estável na tarefa, não no intervalo; contiguidade define o segmento).
    """
    fluxo = sorted(sessao.get("fluxo") or [], key=lambda x: x[0])
    ts_todos = sessao["ts_todos"]
    cortes = []

    # 1. gap — sobre ts_linhas (todas as linhas main com ts)
    ts_linhas = sorted(sessao.get("ts_linhas") or [], key=lambda x: x[0])
    for (t1, _l1), (t2, l2) in zip(ts_linhas, ts_linhas[1:]):
        if t2 - t1 > GAP_CORTE_S:
            cortes.append({"ts": t2, "linha": l2, "sinal": "gap",
                           "detalhe": f"inatividade {t2 - t1:.0f}s > "
                                      f"{GAP_CORTE_S:.0f}s"})

    # 2. marcador de voz (nunca no primeiro turno da sessão)
    for i, (ts, texto, _vid, linha, _a) in enumerate(sessao["vozes"]):
        if i == 0 or ts is None:
            continue
        m = _RX_MARCADOR_FRONTEIRA.search(texto[:200])
        if m:
            cortes.append({"ts": ts, "linha": linha,
                           "sinal": "marcador-de-voz",
                           "detalhe": redigir(m.group(0), entropia=True)[:60]})

    # 3. cwd sustentado (runs; digressão curta não corta)
    runs = _runs_de_cwd(fluxo)
    if runs:
        base = runs[0][0]
        for cwd, idx, n in runs[1:]:
            if cwd == base or not cwd:
                continue
            ts_c, linha_c, _ = fluxo[idx]
            if n >= N_CWD_SUSTENTADO:
                cortes.append({"ts": ts_c, "linha": linha_c,
                               "sinal": "cwd-sustentado",
                               "detalhe": f"{n} eventos em {cwd}"})
                base = cwd
            elif n >= N_CWD_AMBIGUO and complete_fn and orcamento \
                    and orcamento.permitir("segmentar-arbitrar"):
                try:
                    resp = complete_fn(
                        "Num log de trabalho, o diretório mudou de "
                        f"'{base}' para '{cwd}' por {n} eventos "
                        "consecutivos. Isso é o início de uma atividade "
                        "DISTINTA ou uma digressão da mesma atividade? "
                        "Responda exatamente DISTINTA ou DIGRESSAO.")
                except Exception:
                    resp = ""
                if "DISTINTA" in (resp or "").upper():
                    cortes.append({"ts": ts_c, "linha": linha_c,
                                   "sinal": "cwd-ambiguo-arbitrado-llm",
                                   "detalhe": f"{n} eventos em {cwd}"})
                    base = cwd
            # senão: candidato ambíguo sem completer → NÃO corta (dig-5 A)

    # consolidar: ordenar, dedupe por ts, descartar corte no início
    t0 = ts_todos[0] if ts_todos else None
    vistos, cortes_finais = set(), []
    for c in sorted(cortes, key=lambda c: (c["ts"], c["linha"])):
        if t0 is None or c["ts"] <= t0:
            continue
        if c["ts"] in vistos:
            continue
        vistos.add(c["ts"])
        cortes_finais.append(dict(c, segment_version=SEGMENT_VERSION))

    # montar trechos [b_i, b_{i+1})
    bordas = [t0] + [c["ts"] for c in cortes_finais] + [None]
    trechos = []
    for k in range(len(bordas) - 1):
        ini, fim = bordas[k], bordas[k + 1]
        if ini is None:
            continue

        def _dentro(ts):
            return ts is not None and ts >= ini and (fim is None or ts < fim)

        evs = [e for e in sessao["eventos"] if _dentro(_parse_ts(e["ts"]))]
        vzs = [v for v in sessao["vozes"] if _dentro(v[0])]
        fl = [f for f in fluxo if _dentro(f[0])]
        linha_start = (min(f[1] for f in fl) if fl
                       else (cortes_finais[k - 1]["linha"] if k > 0 else 1))
        abertura = next((redigir(t, entropia=True)[:200]
                         for _, t, _, _, _ in vzs if len(t) >= 8), "")
        if not abertura and vzs:
            abertura = redigir(vzs[0][1], entropia=True)[:200]
        if not abertura:
            abertura = sessao["abertura"]
        cwds_t = Counter(c for _, _, c in fl if c)
        trechos.append({
            "trecho_id": f"tre-{sessao['session_id'][:8]}-L{linha_start}",
            "segment_version": SEGMENT_VERSION,
            "session_id": sessao["session_id"], "host": sessao["host"],
            "arquivo": sessao["arquivo"], "sha1": sessao["sha1"],
            "sidechain": False,
            "cwd": (cwds_t.most_common(1)[0][0] if cwds_t
                    else sessao["cwd"]),
            "corte": cortes_finais[k - 1] if k > 0 else None,
            "eventos": evs, "vozes": vzs,
            "assistant_turnos": [a for a in sessao["assistant_turnos"]
                                 if _dentro(a["ts"])],
            "ts_todos": [t for t in ts_todos if _dentro(t)],
            "abertura": abertura,
            "span": {"ts_start": _iso(ini),
                     "ts_end": _iso(fim) if fim is not None else None,
                     "linha_start": linha_start},
            # segundos SEM arredondar — a conservação (Σ trechos == sessão)
            # é exata; arredondamento só na renderização
            "segundos_ativos_atribuidos": {
                int(cap): tempo_ativo_atribuido_s(ts_todos, ini, fim, cap)
                for cap in (MIN_ATIVOS_CAP_S,) + MIN_ATIVOS_SENSIBILIDADE_S},
        })
    return trechos, cortes_finais


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


def _trecho_de(sessao, ts):
    """trecho_id do timestamp dentro da sessão (None sem segmentação)."""
    for tr in sessao.get("trechos") or []:
        ini = _parse_ts(tr["span"]["ts_start"])
        fim = (_parse_ts(tr["span"]["ts_end"])
               if tr["span"]["ts_end"] else None)
        if ts is not None and ini is not None and ts >= ini \
                and (fim is None or ts < fim):
            return tr["trecho_id"]
    return None


def detectar_sessao(sessao, reg):
    """Detectores intra-sessão (D1, D2, D3, D5, D6) sobre os N1 já registrados."""
    out = []
    th = THRESHOLDS
    vozes = sessao["vozes"]  # (ts, texto, n1_id, linha, tem_antecedente)
    acoes = [e for e in sessao["eventos"] if e["kind"] != "voz-turno"
             and e["ts"] is not None]
    acoes.sort(key=lambda e: e["ts"])

    # D1 resposta-curta-seguida-de-acao
    p = th["resposta-curta-seguida-de-acao"]
    for ts, texto, vid, linha, _a in vozes:
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

    # D2 pergunta-explicacao-resposta-curta — dedup (finding R1 #4): a
    # resposta é o turno humano IMEDIATAMENTE seguinte à pergunta (nenhum
    # turno humano intervém) e cada resposta resolve no máximo uma pergunta.
    p = th["pergunta-explicacao-resposta-curta"]
    ats = sorted(sessao["assistant_turnos"], key=lambda a: a["ts"])
    for i, (ts, texto, vid, linha, _a) in enumerate(vozes):
        if not texto.rstrip().endswith("?") or i + 1 >= len(vozes):
            continue
        ts2, t2, vid2, _, _ = vozes[i + 1]
        if not (0 < len(t2) <= p["max_chars_resposta"]
                and 0 < ts2 - ts <= p["janela_s"]):
            continue
        expl = next((a for a in ats if ts < a["ts"] < ts2
                     and a["chars"] >= p["min_chars_explicacao"]), None)
        if expl:
            out.append(_mk_n2(
                reg, "pergunta-explicacao-resposta-curta", [vid, vid2],
                {"assistant_linha": expl["linha"], "assistant_chars": expl["chars"]},
                {"de": _iso(ts), "ate": _iso(ts2)}))

    # D3 leituras-repetidas-de-estado-externo — SEM sidechain (finding R1 #5):
    # ação de subagente não entra no padrão do operador (Codex #4)
    p = th["leituras-repetidas-de-estado-externo"]
    por_cabeca = defaultdict(list)
    brutas = sessao.get("cabecas_brutas") or {}
    for ac in acoes:
        c = ac["conteudo_redigido"]
        if c.get("tool") == "Bash" and c.get("classe") == "leitura" \
                and c.get("comando_cabeca") and not c.get("sidechain"):
            # R4 item 2: agrupar pela cabeça BRUTA (transiente) — a redação
            # (***) fundia cabeças distintas num grupo fabricado.
            # R5: a chave inclui o TRECHO — grupo nunca cruza um corte
            # (não conta em dobro através da fronteira)
            por_cabeca[(brutas.get(ac["id"], c["comando_cabeca"]),
                        _trecho_de(sessao, _parse_ts(ac["ts"])))].append(ac)
    for (cabeca, _trecho), lst in por_cabeca.items():
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
                    # persistir SÓ a cabeça redigida (a bruta é transiente)
                    {"comando_cabeca": redigir(cabeca, entropia=True)[:80],
                     "n_repeticoes": len(grupo)},
                    {"de": grupo[0]["ts"], "ate": grupo[-1]["ts"]}))
            i = j + 1

    # D5 entrega-com-perguntas-sem-turno-de-resposta-observado
    p = th["entrega-com-perguntas-sem-turno-de-resposta-observado"]
    if ats and vozes:
        ultimo = ats[-1]
        if ultimo["n_perguntas"] >= p["min_perguntas"] \
                and not any(ts > ultimo["ts"] for ts, _, _, _, _ in vozes):
            out.append(_mk_n2(
                reg, "entrega-com-perguntas-sem-turno-de-resposta-observado",
                [vozes[-1][2]],
                {"assistant_linha": ultimo["linha"],
                 "n_perguntas": ultimo["n_perguntas"]},
                {"de": _iso(vozes[-1][0]), "ate": _iso(ultimo["ts"])}))

    # D6 rajada-de-turnos-curtos — SEM turnos interrogativos (finding R1 #16:
    # rajada de perguntas curtas sobrepunha D2 nos mesmos turnos); R5: a
    # janela não cruza um corte de trecho
    p = th["rajada-de-turnos-curtos"]
    curtos = [(ts, vid, _trecho_de(sessao, ts)) for ts, t, vid, _, _ in vozes
              if 0 < len(t) <= p["max_chars"]
              and not t.rstrip().endswith("?")]
    i = 0
    while i < len(curtos):
        j = i
        while j + 1 < len(curtos) \
                and curtos[j + 1][0] - curtos[i][0] <= p["janela_s"] \
                and curtos[j + 1][2] == curtos[i][2]:
            j += 1
        if j - i + 1 >= p["min_turnos"]:
            out.append(_mk_n2(
                reg, "rajada-de-turnos-curtos",
                [v for _, v, _ in curtos[i:j + 1]],
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
        ts, _, vid, _, _ = s["vozes"][0]
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
    """Touch de um trecho (R5) ou de uma sessão inteira (fallback legado).

    Trecho traz `segundos_ativos_atribuidos` (gap pertence ao trecho onde
    começa — conservação exata); sessão sem segmentação cai no cômputo
    clássico sobre ts_todos."""
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
    seg = sessao.get("segundos_ativos_atribuidos")
    if seg:
        minutos = round(seg[int(MIN_ATIVOS_CAP_S)] / 60, 1)
        sens = {f"cap_{int(c)}s": round(seg[int(c)] / 60, 1)
                for c in MIN_ATIVOS_SENSIBILIDADE_S}
        base = ("gaps atribuídos ao trecho onde começam (conservação: soma "
                "dos trechos == sessão), teto idem")
    else:
        minutos = round(tempo_ativo_s(ts, MIN_ATIVOS_CAP_S) / 60, 1)
        sens = {f"cap_{int(c)}s": round(tempo_ativo_s(ts, c) / 60, 1)
                for c in MIN_ATIVOS_SENSIBILIDADE_S}
        base = "gaps entre timestamps consecutivos do transcript principal"
    t = {
        "session_id": sessao["session_id"], "host": sessao["host"],
        "arquivo": sessao["arquivo"],
        "ts_start": _iso(ts[0]) if ts else None,
        "ts_end": _iso(ts[-1]) if ts else None,
        "min_ativos": {
            "cap_s": int(MIN_ATIVOS_CAP_S), "minutos": minutos,
            "sensibilidade": sens, "base": base},
        "n_eventos_voz": len(voz), "n_eventos_acao": len(acao),
        "n_eventos_acao_sidechain": len(side),
        "top_ferramentas": ferramentas.most_common(5),
        "top_arquivos": [(redigir(a), n) for a, n in arquivos.most_common(5)],
        "commits": commits}
    if sessao.get("trecho_id"):
        t["trecho_id"] = sessao["trecho_id"]
        t["segment_version"] = sessao.get("segment_version")
        t["span"] = sessao.get("span")
        t["corte"] = sessao.get("corte")
    return t


# NEW-7: adjetivos de juízo/caráter proibidos em nome de Atividade — nome
# descreve o TRABALHO, nunca julga o trabalhador (Codex #3 reentrando pelo
# nome do cluster)
_RX_NOME_JUIZO = re.compile(
    r"(?i)(autorit|mec[aâ]nic|obedien|submiss|impulsiv|apressad|preguiç|"
    r"descuidad|negligen|compulsiv|obsessiv|ansios|irrefletid|servil|"
    r"passiv|rob[oó]tic|autom[aá]tic|cego|acr[ií]tic|displicent)")


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
        touches = [_touch(s) for s in ss]
        # NEW-7: fallback DETERMINÍSTICO de nome (basename do cwd + top file)
        top_arq = next((os.path.basename(a) for t in touches
                        for a, _ in t["top_arquivos"][:1]), "")
        nome_fallback = (os.path.basename(chave.rstrip("/")) or chave)
        if top_arq:
            nome_fallback += f" · {top_arq}"
        nome = None
        if complete_fn and orcamento and orcamento.permitir("nomear-cluster"):
            try:
                resp = complete_fn(
                    "Nomeie em no máximo 6 palavras, descritivas e sem "
                    "diagnóstico psicológico, a Atividade de trabalho cujas "
                    "aberturas de sessão são:\n"
                    + "\n".join(f"- {s['abertura'][:160]}" for s in ss[:5])
                    + "\nResponda SÓ o nome.")
                nome = redigir((resp or "").strip().splitlines()[0],
                               entropia=True)[:80] or None
            except Exception as ex:
                log.append({"acao": "nomear-falhou", "cluster": chave,
                            "razao": str(ex)[:120]})
        # NEW-7: nome com juízo de caráter é rejeitado mecanicamente; idem
        # nome que não é nome (markup/vazio — ex.: completer devolvendo
        # "<function_calls>")
        if nome and (_RX_NOME_JUIZO.search(nome) or nome.startswith("<")
                     or not re.search(r"[A-Za-zÀ-ú0-9]", nome)):
            log.append({"acao": "nome-rejeitado", "cluster": chave,
                        "nome_llm": nome,
                        "razao": "juízo de caráter ou markup no nome (NEW-7); "
                                 "fallback determinístico aplicado"})
            nome = None
        if not nome:
            nome = (abertura_ref[:60] or nome_fallback) \
                if not complete_fn else nome_fallback
        atividades.append({
            "ulid": _rid("atv", chave), "nome": nome,
            "finalidade": abertura_ref[:160],
            "estado": "aberta",
            "hosts": sorted({s["host"] for s in ss}),
            "cwd": chave, "cluster_version": CLUSTER_VERSION,
            "sessions": touches,
            # R5: afiliação por TRECHO; sessões DISTINTAS continuam sendo o
            # grão de diversidade (anti-inflação)
            "session_ids": sorted({s["session_id"] for s in ss}),
            "trecho_ids": [s.get("trecho_id") for s in ss
                           if s.get("trecho_id")]})
    return atividades, log


# ---------------------------------------------------------------------------
# Camada 3 — fold de padrões (estados; diversidade; Codex #13)
# ---------------------------------------------------------------------------

def fold_padroes(reg, agora_ts=None, cobertura=None):
    """Fold N2→padrões. Diversidade (finding R1 #8): UMA sessão cruzando a
    meia-noite NÃO concede diversidade de dias — padrão só sai de `mesma-cena`
    com ≥2 SESSÕES distintas (dias contam apenas quando vêm de sessões
    distintas). Cobertura anexada a cada padrão (Codex #18 / finding #11)."""
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
        elif len(sessoes) < 2:
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
                            "hosts": len(hosts),
                            "nota": "dias de UMA mesma sessão não concedem "
                                    "diversidade (fronteira de sessão manda)"},
            "first_seen": first_seen, "last_seen": last_seen,
            "estado": estado, "detector_version": DETECTOR_VERSION,
            "cobertura": cobertura})
    formas_sem_instancias = sorted(set(THRESHOLDS) - set(por_forma))
    return padroes, formas_sem_instancias


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


# NEW-3: N3/N4 não podem atribuir ao operador execução que os próprios N1
# dizem ser do agente (executor=agente). Checagem MECÂNICA pós-geração.
_RX_ATRIBUICAO_INDEVIDA = re.compile(
    r"(?i)\b(voc[eê]|o\s+operador|operador)\s+(executa|executou|roda|rodou|"
    r"faz|fez|escreve|escreveu|commita|commitou|valida|validou|inspeciona|"
    r"inspecionou|realiza|realizou|trabalha|l[eê]|leu|digita|digitou|"
    r"verifica|verificou|constr[oó]i|construiu|implementa|implementou)\b")


def _quebra_executores(reg, n2):
    """(n_acoes, n_executadas_por_agente) das instâncias N1 do n2."""
    acoes = [reg.by_id[i] for i in n2["instancias"]
             if reg.by_id[i].get("agencia")]
    n_agente = sum(1 for a in acoes
                   if a["agencia"].get("executor") == "agente")
    return len(acoes), n_agente


# R4 item 6 (NEWER-4): base com 0 ações observadas não sustenta texto que
# afirme "ação"/execução — a instância é só voz
_RX_ACAO_SEM_BASE = re.compile(
    r"(?i)\b(a[çc][ãa]o|a[çc][õo]es|executa\w*|execu[çc][ãa]o|agir|"
    r"implementa\w*|commit\w*)\b")


def _atribuicao_invalida(texto, n_acoes, n_agente):
    if n_acoes and n_agente / n_acoes > 0.5:
        return bool(_RX_ATRIBUICAO_INDEVIDA.search(texto or ""))
    if n_acoes == 0:
        return bool(_RX_ACAO_SEM_BASE.search(texto or ""))
    return False


def _bloco_atribuicao(n_acoes, n_agente):
    if n_acoes == 0:
        # R4 item 6: base só de voz — nada de "ação" no texto
        return ("\nATRIBUIÇÃO OBRIGATÓRIA: estas instâncias contêm APENAS "
                "turnos de voz (0 ações observadas). É PROIBIDO afirmar "
                "'ação', execução ou implementação; descreva somente o "
                "padrão de fala/pergunta/confirmação observado.")
    return (f"\nATRIBUIÇÃO OBRIGATÓRIA: {n_agente} de {n_acoes} ações destas "
            "instâncias foram executadas pelo AGENTE DELEGADO "
            "(executor=agente). Atribua a EXECUÇÃO ao agente e o "
            "comando/decisão/observação ao operador. É PROIBIDO escrever "
            "'o operador executou' ou 'você executa/faz/roda' quando o "
            "executor é o agente.")


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


def inferir_n3(reg, complete_fn, orcamento, model="injetado",
               formas_permitidas=None, degradacoes=None):
    """≤1 call por correlação; claim com confiança + alternativas inocentes.

    GATE do estágio 0 (finding R1 #2): só formas com veredicto `confiavel`
    geram N3 — `formas_permitidas` vem do eval; None/vazio → nada sobe.

    O prompt EMBUTE o resumo redigido das instâncias N1 — sem isso o modelo
    responde meta-reclamações de "transcript não fornecido" (observado no
    backfill de 2026-08-17)."""
    out = []
    permitidas = formas_permitidas or set()
    for n2 in sorted(reg.nivel(2), key=lambda r: r["id"]):
        if n2["forma"] not in permitidas:
            continue
        if not orcamento.permitir("n3"):
            break
        evid = "\n".join(_resumo_instancia(reg.by_id[i])
                         for i in n2["instancias"][:8])
        n_acoes, n_agente = _quebra_executores(reg, n2)
        prompt = (
            "Você anota correlações mecânicas em transcripts de trabalho. "
            "NUNCA afirme cognição; um claim é 'compatível com', nunca "
            "'prova'. A evidência resumida (redigida) está ABAIXO — não "
            "peça o transcript; se ela for pouca, devolva um claim "
            "modesto com confiança baixa. Correlação:\n"
            f"forma: {n2['forma']}\nparams: {json.dumps(n2['params'])}\n"
            f"janela: {json.dumps(n2['janela'])}\n"
            f"instancias:\n{evid}\n"
            + _bloco_atribuicao(n_acoes, n_agente)
            + "\nResponda SÓ JSON: {\"claim\": \"...\", \"confianca\": "
              "0.0-1.0, \"alternativas\": [\">=1 explicação inocente\"]}")
        j = None
        for tentativa in range(2):  # NEW-3: 1 regeneração; senão descarta
            try:
                resp = complete_fn(prompt if tentativa == 0 else (
                    prompt + "\nSUA RESPOSTA ANTERIOR VIOLOU a regra de "
                    "ATRIBUIÇÃO OBRIGATÓRIA acima. Reescreva respeitando-a "
                    "à letra."))
            except Exception:
                j = None
                break
            j = _json_do_llm(resp)
            if not j or not j.get("claim") or not j.get("alternativas"):
                j = None
                break
            if not _atribuicao_invalida(str(j["claim"]), n_acoes, n_agente):
                break
            if tentativa == 1 or not orcamento.permitir("n3-retry"):
                if degradacoes is not None:
                    degradacoes.append(
                        f"N3 de {n2['id']} descartado: texto incoerente com "
                        "a base (atribuição indevida ou ação sem ação na "
                        "base — NEW-3/NEWER-4), mesmo após regeneração")
                j = None
        if not j:
            continue
        rec = {"id": _rid("n3", n2["id"]), "nivel": 3,
               "claim": redigir(str(j["claim"]), entropia=True)[:400],
               "executores_da_base": {"acoes": n_acoes,
                                      "executadas_por_agente": n_agente},
               "confianca": max(0.0, min(1.0, float(j.get("confianca", 0.5)))),
               "alternativas": [redigir(str(a))[:200]
                                for a in j["alternativas"]][:4],
               "base": [n2["id"]], "detector_version": DETECTOR_VERSION,
               "model": model}
        out.append(reg.add(rec))
    return out


N3_CONFIANCA_MIN_PARA_N4 = 0.2  # N3 degenerado (confiança ~0) não sobe a N4


def hipotetizar_n4(reg, complete_fn, orcamento, model="injetado",
                   degradacoes=None):
    """≤1 call por padrão (forma) com N3s; status nasce 'proposta'.

    Só N3 com confiança ≥ N3_CONFIANCA_MIN_PARA_N4 entra na base — filtro
    declarado (não é leitura de cognição: usa a incerteza que o próprio N3
    declara). NEW-3: mesma checagem mecânica de atribuição dos N3."""
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
        n_acoes = sum(n3.get("executores_da_base", {}).get("acoes", 0)
                      for n3 in n3s)
        n_agente = sum(n3.get("executores_da_base", {})
                       .get("executadas_por_agente", 0) for n3 in n3s)
        prompt = (
            "Você formula hipóteses de mentoria CONFIRMÁVEIS pelo "
            "mentorado — a correção dele sempre vence. As inferências "
            "abaixo são todo o insumo disponível; não peça mais contexto. "
            f"Padrão observado: '{forma}'. Inferências:\n"
            + "\n".join(f"- {n3['claim']} (confiança {n3['confianca']})"
                        for n3 in n3s[:5])
            + _bloco_atribuicao(n_acoes, n_agente)
            + "\nResponda SÓ JSON: {\"hipotese\": \"frase interrogativa "
              "dirigida ao mentorado sobre COMO ELE TRABALHA, terminando "
              "em ?\", \"falsificacao\": "
              "\"que observação a derrubaria\"}")
        j = None
        for tentativa in range(2):  # NEW-3: 1 regeneração; senão descarta
            try:
                resp = complete_fn(prompt if tentativa == 0 else (
                    prompt + "\nSUA RESPOSTA ANTERIOR VIOLOU a regra de "
                    "ATRIBUIÇÃO OBRIGATÓRIA acima. Reescreva respeitando-a "
                    "à letra."))
            except Exception:
                j = None
                break
            j = _json_do_llm(resp)
            if not j or not j.get("hipotese") or not j.get("falsificacao"):
                j = None
                break
            if not _atribuicao_invalida(str(j["hipotese"]), n_acoes,
                                        n_agente):
                break
            if tentativa == 1 or not orcamento.permitir("n4-retry"):
                if degradacoes is not None:
                    degradacoes.append(
                        f"N4 de '{forma}' descartado: texto incoerente com "
                        "a base (atribuição indevida ou ação sem ação na "
                        "base — NEW-3/NEWER-4), mesmo após regeneração")
                j = None
        if not j:
            continue
        rec = {"id": _rid("n4", forma, *sorted(n3["id"] for n3 in n3s)),
               "nivel": 4,
               "hipotese": redigir(str(j["hipotese"]), entropia=True)[:400],
               "executores_da_base": {"acoes": n_acoes,
                                      "executadas_por_agente": n_agente},
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


def _linha_json(workdir, arquivo_rel, linha_alvo):
    caminho = Path(workdir) / arquivo_rel
    try:
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            for n, linha in enumerate(fh, 1):
                if n == linha_alvo:
                    return json.loads(linha)
                if n > linha_alvo:
                    break
    except Exception:
        return None
    return None


def _carga_util(workdir, arquivo_rel, linha):
    """O fato julgado, COMPLETO, minimizado e redigido (findings R1 #3/#7).

    Extrai SÓ os campos load-bearing da linha ancorada: texto humano, texto
    do assistant (integral até 4000 chars, com chars_total), comando integral
    de tool_use, file_path. Bytes de thinking/signature/tool_result NUNCA
    entram no pacote — o caminho do eval passa pela mesma minimização e
    redaction do resto (brief v2 §2)."""
    j = _linha_json(workdir, arquivo_rel, linha)
    if not isinstance(j, dict):
        return {"linha": linha, "indisponivel": True}
    msg = j.get("message") or {}
    content = msg.get("content")
    out = {"linha": linha, "ts": j.get("timestamp"), "tipo": j.get("type")}
    textos, tools = [], []
    if isinstance(content, str):
        textos.append(content)
    elif isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                textos.append(b.get("text") or "")
            elif b.get("type") == "tool_use":
                inp = b.get("input") or {}
                tc = {"tool": b.get("name")}
                if inp.get("command"):
                    tc["comando_completo"] = redigir(inp["command"],
                                                     entropia=True)[:4000]
                for k in ("file_path", "notebook_path"):
                    if inp.get(k):
                        tc["file_path"] = redigir(inp[k])[:300]
                tools.append(tc)
    texto = "\n".join(t for t in textos if t)
    if texto:
        campo = ("texto_humano" if j.get("type") == "user"
                 else "texto_assistant")
        out[campo] = redigir(texto, entropia=True)[:4000]
        out["chars_total"] = len(texto)
    if tools:
        out["tool_calls"] = tools
    return out


def _itens_catch(seed_base, arquivo_ref=None):
    """Catch trials (dig-2 perna B: gold seeding, Oleson 2011/Snow 2008) —
    itens sintéticos com rótulo conhecido, um deles com ERRO TENTADOR (pernas
    de timing batem, mas o comando é só leitura → gold `nao`). Excluídos do
    IAA e da precisão; medem atenção/aterramento do rotulador.

    NEW-5: âncoras com FORMA idêntica às reais (id n2-<12hex>, arquivo do
    corpus, linha inteira plausível, uuid) — indistinguíveis no pacote; o
    gold vive só no pré-registro."""
    import random
    rnd = random.Random(f"catch-{seed_base}")
    arquivo = arquivo_ref or "sessao-desconhecida.jsonl"
    # linhas CRESCENTES por item — jsonl append-only tem linha↑ ⇔ ts↑; âncora
    # fora de ordem denuncia o item sintético (apontado pelos rotuladores R3)
    linhas_iter = iter(sorted(rnd.sample(range(180, 6100), 8)))

    def _anc(kind):
        return {"arquivo": arquivo, "linha": next(linhas_iter),
                "kind": kind,
                "uuid": (f"{rnd.getrandbits(32):08x}-{rnd.getrandbits(16):04x}"
                         f"-4{rnd.getrandbits(12):03x}"
                         f"-8{rnd.getrandbits(12):03x}"
                         f"-{rnd.getrandbits(48):012x}")}

    def _item(forma, sufixo, descricao, evidencia):
        return {"n2_id": _rid("n2", "catch", seed_base, sufixo, forma),
                "forma": forma, "descricao_mecanica": descricao,
                "pergunta": PERGUNTA_MECANICA, "evidencia": evidencia}

    t0 = "2026-08-12T14:03:10.287000+00:00"
    a1, a2 = _anc("voz-turno"), _anc("tool-call")
    catch1 = _item(
        "resposta-curta-seguida-de-acao", "a",
        "turno humano com <= 6 chars seguido, em ate 120s, de tool call de "
        "escrita/commit (observado: {\"delta_s\": 12.0, \"chars_voz\": 2})",
        [{"ancora": a1,
          "carga": {"linha": a1["linha"], "tipo": "user", "ts": t0,
                    "texto_humano": "ok", "chars_total": 2}},
         {"ancora": a2,
          "carga": {"linha": a2["linha"], "tipo": "assistant",
                    "ts": "2026-08-12T14:03:22.301000+00:00",
                    "tool_calls": [{"tool": "Bash", "comando_completo":
                                    "tail -n 50 servidor.log 2>/dev/null"}]}}])
    evid2 = []
    for m in (1, 3, 5):
        a = _anc("tool-call")
        evid2.append({"ancora": a,
                      "carga": {"linha": a["linha"], "tipo": "assistant",
                                "ts": f"2026-08-12T15:0{m}:11.44{m}000+00:00",
                                "tool_calls": [{"tool": "Bash",
                                                "comando_completo":
                                                f"grep -c padrao arquivo{m}.log"}]}})
    catch2 = _item(
        "leituras-repetidas-de-estado-externo", "b",
        ">= 3 execucoes Bash de leitura com a mesma cabeca de comando em <= "
        "3600s (observado: {\"comando_cabeca\": \"grep -c\", "
        "\"n_repeticoes\": 3})",
        evid2)
    return [(catch1, "nao"), (catch2, "sim")]


def eval_preparar(reg, workdir, max_amostra=30, seed=17, com_catch=True):
    """Amostra estratificada por forma (round-robin determinístico), pacotes
    com o fato julgado completo (finding R1 #3), catch trials semeados e
    RECIBO DE PRÉ-REGISTRO (finding R1 #14): hash sha256 do bloco congelado
    gravado ANTES de qualquer rótulo.

    Retorna (amostra, pre_registro). O pre_registro NÃO é entregue aos
    rotuladores (contém o gold dos catch)."""
    import random
    rnd = random.Random(seed)
    por_forma = defaultdict(list)
    for n2 in reg.nivel(2):
        por_forma[n2["forma"]].append(n2)
    populacao = sum(len(v) for v in por_forma.values())
    for lst in por_forma.values():
        lst.sort(key=lambda r: r["id"])
        rnd.shuffle(lst)
    itens = []
    while len(itens) < max_amostra and any(por_forma.values()):
        for forma in sorted(por_forma):
            if por_forma[forma] and len(itens) < max_amostra:
                n2 = por_forma[forma].pop()
                evid = []
                for iid in n2["instancias"][:6]:
                    n1 = reg.by_id[iid]
                    ev = n1["evidencia"]
                    evid.append({
                        "ancora": {"arquivo": ev["arquivo_jsonl"],
                                   "linha": ev["linha"], "kind": n1["kind"],
                                   "uuid": ev.get("uuid")},
                        "carga": _carga_util(workdir, ev["arquivo_jsonl"],
                                             ev["linha"])})
                # D2: a explicação do assistant é perna julgada — entra no
                # pacote (finding R1 #3), via assistant_linha dos params
                if n2["forma"] == "pergunta-explicacao-resposta-curta" \
                        and n2["params"].get("assistant_linha"):
                    arq = reg.by_id[n2["instancias"][0]]["evidencia"][
                        "arquivo_jsonl"]
                    evid.append({
                        "ancora": {"arquivo": arq,
                                   "linha": n2["params"]["assistant_linha"],
                                   "kind": "assistant-explicacao"},
                        "carga": _carga_util(
                            workdir, arq, n2["params"]["assistant_linha"])})
                itens.append({
                    "n2_id": n2["id"], "forma": n2["forma"],
                    "descricao_mecanica": _descricao_mecanica(n2),
                    "pergunta": PERGUNTA_MECANICA,
                    "evidencia": evid})
    catch_gold = {}
    if com_catch:
        arquivos_reais = Counter(
            e["ancora"].get("arquivo") for i in itens
            for e in i["evidencia"] if e.get("ancora", {}).get("arquivo"))
        arquivo_ref = (arquivos_reais.most_common(1)[0][0]
                       if arquivos_reais else None)
        for item, gold in _itens_catch(seed, arquivo_ref):
            pos = rnd.randrange(len(itens) + 1) if itens else 0
            itens.insert(pos, item)
            catch_gold[item["n2_id"]] = gold
    for n, item in enumerate(itens, 1):
        item["item"] = n
    bloco = {"precisao_min": EVAL_PRECISAO_MIN,
             "concordancia_min": EVAL_CONCORDANCIA_MIN,
             "detector_version": DETECTOR_VERSION,
             "thresholds": THRESHOLDS}
    bloco_txt = json.dumps(bloco, sort_keys=True, ensure_ascii=False)
    pre_registro = {
        "gravado_em": datetime.now(tz=timezone.utc).isoformat(),
        "sha256_bloco_congelado": hashlib.sha256(
            bloco_txt.encode()).hexdigest(),
        "bloco": bloco,
        "catch_gold_por_item": {i["item"]: catch_gold[i["n2_id"]]
                                for i in itens if i["n2_id"] in catch_gold},
        "populacao_n2": populacao,
        "tipo_amostra": ("censo" if len(itens) - len(catch_gold) >= populacao
                         else "amostra")}
    amostra = {"pergunta": PERGUNTA_MECANICA,
               "thresholds_congelados": bloco,
               "itens": itens}
    return amostra, pre_registro


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


def eval_ingerir(amostra, labels_a, labels_b, pre_registro=None):
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
    pre_registro = pre_registro or {}
    catch_gold = {int(k): v for k, v in
                  (pre_registro.get("catch_gold_por_item") or {}).items()}
    # recibo de pré-registro (finding R1 #14): o bloco congelado da amostra
    # tem que bater com o hash gravado ANTES dos rótulos
    hash_agora = hashlib.sha256(json.dumps(
        amostra["thresholds_congelados"], sort_keys=True,
        ensure_ascii=False).encode()).hexdigest()
    pre_ok = (pre_registro.get("sha256_bloco_congelado") == hash_agora
              if pre_registro else None)
    catch_acertos = {"a": 0, "b": 0, "n": len(catch_gold)}
    for item_n, gold in catch_gold.items():
        if la.get(item_n) == gold:
            catch_acertos["a"] += 1
        if lb.get(item_n) == gold:
            catch_acertos["b"] += 1
    por_forma = defaultdict(lambda: {"n": 0, "concordam": 0, "sim": 0,
                                     "nao": 0, "insuficiente": 0,
                                     "sem_consenso": 0, "pares": []})
    todos_pares = []
    for item in amostra["itens"]:
        if item["item"] in catch_gold:
            continue  # catch fora do IAA e da precisão (dig-2 perna B)
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
    n_reais = len(amostra["itens"]) - len(catch_gold)
    prevalencia = Counter(a for a, _ in todos_pares)
    return {"thresholds_congelados": amostra["thresholds_congelados"],
            "pre_registro": {
                "verificado": pre_ok,
                "sha256_bloco_congelado": pre_registro.get(
                    "sha256_bloco_congelado"),
                "gravado_em": pre_registro.get("gravado_em")},
            "rotuladores": [labels_a.get("rotulador", "a"),
                            labels_b.get("rotulador", "b")],
            "amostra": n_reais,
            "tipo_amostra": pre_registro.get("tipo_amostra") or "amostra",
            "populacao_n2": pre_registro.get("populacao_n2"),
            "catch_trials": dict(
                catch_acertos,
                nota="itens sintéticos com gold pré-registrado (um com erro "
                     "tentador); fora do IAA e da precisão — medem "
                     "atenção/aterramento (Oleson 2011, Snow 2008)"),
            "por_forma": resultado,
            "global": {"p_o": p_o_global, "kappa": kappa_global,
                       "taxa_desacordo": (round(1 - p_o_global, 3)
                                          if p_o_global is not None else None),
                       "n_pares": len(todos_pares),
                       "prevalencia_rotulador_a": dict(prevalencia),
                       "nota": "κ de Cohen 3-classes agregado; em n≈30 o IC é "
                               "largo (Sim & Wright 2005) — ler junto com as "
                               "contagens cruas e a prevalência (Feinstein & "
                               "Cicchetti 1990), nunca sozinho"},
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
             model="injetado", eval_estagio0=None):
    """Cópia de trabalho (já redigida) → registry + projeção completa.

    `eval_estagio0` (resultado de eval_ingerir): GATE dos N3/N4 (finding R1
    #2) — sem ele, NENHUM N3/N4 é gerado (degradação declarada); com ele, só
    formas `confiavel` sobem."""
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
            razao = ("sessão de protocolo/despacho: turnos humanos são plano "
                     "de despacho/skill, não voz do operador (NEW-4)"
                     if s.get("turnos_protocolo")
                     else "sem turno humano de voz")
            puladas.append({"arquivo": rel, "razao": razao})
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

    # R5: segmentar ANTES da detecção (D3/D6 respeitam fronteiras de trecho)
    todos_trechos, seg_recibos = [], []
    for s in sessoes:
        trechos, cortes = segmentar(s, complete_fn, orc)
        s["trechos"] = trechos
        todos_trechos.extend(trechos)
        soma_s = sum(t["segundos_ativos_atribuidos"][int(MIN_ATIVOS_CAP_S)]
                     for t in trechos)
        sessao_s = tempo_ativo_s(s["ts_todos"], MIN_ATIVOS_CAP_S)
        seg_recibos.append({
            "session_id": s["session_id"], "arquivo": s["arquivo"],
            "n_trechos": len(trechos),
            "cortes": cortes,
            "conservacao_s": {"soma_trechos": round(soma_s, 3),
                              "sessao": round(sessao_s, 3),
                              "delta": round(soma_s - sessao_s, 6)}})

    n2s = []
    for s in sessoes:
        n2s.extend(detectar_sessao(s, reg))
    n2s.extend(detectar_cross_sessao(sessoes, reg))
    # R5: N2 ganha refs de trecho (âncoras N1 intactas; ids N2 idem)
    spans_por_sessao = {s["session_id"]: s for s in sessoes}
    for n2 in reg.nivel(2):
        trs = set()
        for iid in n2["instancias"]:
            n1 = reg.by_id[iid]
            s = spans_por_sessao.get(n1["session_id"])
            if s:
                tid = _trecho_de(s, _parse_ts(n1["ts"]))
                if tid:
                    trs.add(tid)
        n2["trechos"] = sorted(trs)

    degradacoes = []
    if complete_fn is None:
        degradacoes.append(
            "N3/N4 não gerados e clusters sem nome LLM: completer ausente — "
            "degradação DECLARADA para N2-only (brief v2 §4)")
    formas_confiaveis = {
        f for f, v in ((eval_estagio0 or {}).get("por_forma") or {}).items()
        if v.get("veredicto") == "confiavel"}
    formas_presentes = {n2["forma"] for n2 in reg.nivel(2)}
    if eval_estagio0 is None:
        degradacoes.append(
            "estágio 0 pendente: NENHUM N3/N4 gerado (gate do finding R1 #2; "
            "rode eval e repasse o resultado via --eval)")
    else:
        reprovadas = sorted(formas_presentes - formas_confiaveis)
        if reprovadas:
            degradacoes.append(
                "formas sem selo `confiavel` no estágio 0 — N3/N4 NÃO "
                f"gerados para: {', '.join(reprovadas)}")
    atividades, cluster_log = clusterizar(todos_trechos, complete_fn, orc)
    if complete_fn is not None and formas_confiaveis:
        inferir_n3(reg, complete_fn, orc, model=model,
                   formas_permitidas=formas_confiaveis,
                   degradacoes=degradacoes)
        hipotetizar_n4(reg, complete_fn, orc, model=model,
                       degradacoes=degradacoes)
        if orc.negadas:
            degradacoes.append(
                f"orçamento LLM esgotado: {orc.negadas} chamadas negadas "
                f"(teto {orc.teto})")

    agora_ts = agora_ts or datetime.now(tz=timezone.utc).timestamp()
    ts_all = [t for s in sessoes for t in s["ts_todos"]]
    janela = {"de": _iso(min(ts_all)) if ts_all else None,
              "ate": _iso(max(ts_all)) if ts_all else None,
              "criterio": f"mtime nos últimos {janela_dias} dias"}
    cobertura = montar_cobertura([host], len(sessoes), puladas, janela)
    padroes, formas_sem_instancias = fold_padroes(reg, agora_ts, cobertura)

    # índice N2 por TRECHO → atividade (R5); fallback por sessão para N2
    # sem refs de trecho
    n2_por_trecho = defaultdict(list)
    n2_por_sessao = defaultdict(list)
    for n2 in reg.nivel(2):
        if n2.get("trechos"):
            for tid in n2["trechos"]:
                n2_por_trecho[tid].append(n2["id"])
        else:
            for sid in n2["sessoes"]:
                n2_por_sessao[sid].append(n2["id"])
    for atv in atividades:
        ids = {i for tid in atv.get("trecho_ids", [])
               for i in n2_por_trecho.get(tid, [])}
        ids |= {i for sid in atv["session_ids"]
                for i in n2_por_sessao.get(sid, [])}
        atv["n2_ids"] = sorted(ids)
        voz = sum(t["n_eventos_voz"] for t in atv["sessions"])
        aca_total = sum(t["n_eventos_acao"] for t in atv["sessions"])
        aca_side = sum(t["n_eventos_acao_sidechain"] for t in atv["sessions"])
        # finding R1 #12: manchete NÃO mistura operador e delegado
        atv["voz_acao"] = {"voz": voz, "acao": aca_total - aca_side,
                           "acao_delegada_sidechain": aca_side,
                           "unidade": "eventos",
                           "nota": "proporção de EVENTOS por trilho; 'acao' "
                                   "exclui subagentes (delegado ao lado); "
                                   "não é tempo nem tokens"}
        atv["cobertura"] = cobertura

    projecao = {
        "gerado_em": datetime.now(tz=timezone.utc).isoformat(),
        "cluster_version": CLUSTER_VERSION,
        "detector_version": DETECTOR_VERSION,
        "segmentacao": {
            "segment_version": SEGMENT_VERSION,
            "gap_corte_s": GAP_CORTE_S,
            "n_cwd_sustentado": N_CWD_SUSTENTADO,
            "n_cwd_ambiguo": N_CWD_AMBIGUO,
            "marcadores_lexicon": _RX_MARCADOR_FRONTEIRA.pattern,
            "por_sessao": seg_recibos,
            "nota": "cortes mecânicos primeiro (gap 900s=15min dig-5 B; cwd "
                    "sustentado ≥5 eventos dig-5 A; marcador de voz de "
                    "lexicon fechado); LLM só arbitra candidato ambíguo; "
                    "1 trecho/sessão sem sinal é resultado honesto"},
        "thresholds": THRESHOLDS,
        "cobertura": cobertura,
        "degradacoes": degradacoes,
        "orcamento_llm": orc.dump(),
        "atividades": atividades,
        "cluster_log": cluster_log,
        "padroes": padroes,
        "formas_sem_instancias": formas_sem_instancias,
        "contagens": {f"n{n}": len(reg.nivel(n)) for n in (1, 2, 3, 4)},
        "eval_estagio0": eval_estagio0}
    return reg, projecao


def persistir(state_dir, reg, projecao):
    state = _guard_estado(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    avisos = []
    ordem = sorted(reg.by_id.values(), key=lambda r: (r["nivel"], r["id"]))
    marcas = 0
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
            marcas += linha.count(_MASK)
            fh.write(linha + "\n")
    # finding R1 #9: *** é artefato de redaction, marcado e CONTADO — nunca
    # passa por conteúdo original
    projecao["redaction"] = {
        "marcas_no_estado": marcas,
        "nota": "toda ocorrência de *** nos arquivos persistidos é artefato "
                "de redaction, não conteúdo original"}
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
    if projecao.get("redaction"):
        r = projecao["redaction"]
        H.append(f"<p>Redaction: {r['marcas_no_estado']} marcas "
                 f"<code>***</code> no estado persistido — {_esc(r['nota'])}."
                 f"</p>")
    # R5: recibos de segmentação — cada corte ancorado (arquivo+linha) para
    # conferência contra o jsonl cru; conservação de tempo declarada
    seg = projecao.get("segmentacao")
    if seg:
        H.append(f"<p>Segmentação <code>{_esc(seg['segment_version'])}</code>"
                 f": gap &gt; {seg['gap_corte_s']:.0f}s (15 min, prática de "
                 f"logs de desenvolvedor) · cwd sustentado ≥ "
                 f"{seg['n_cwd_sustentado']} eventos · marcadores de voz de "
                 f"lexicon fechado · sem sinal → 1 trecho (honesto).</p>")
        H.append("<ul>")
        for r in seg.get("por_sessao", []):
            cons = r["conservacao_s"]
            H.append(f"<li><code>{_esc(r['session_id'][:8])}</code>: "
                     f"{r['n_trechos']} trecho(s); conservação "
                     f"Σtrechos {cons['soma_trechos']}s = sessão "
                     f"{cons['sessao']}s (Δ {cons['delta']}s)")
            if r["cortes"]:
                H.append("<ul>" + "".join(
                    f"<li>corte <b>{_esc(c['sinal'])}</b> em "
                    f"<span class='anc'>{_esc(r['arquivo'])}:{c['linha']}"
                    f"</span> ({_esc(str(c.get('detalhe', ''))[:80])})</li>"
                    for c in r["cortes"]) + "</ul>")
            H.append("</li>")
        H.append("</ul>")

    # finding R1 #11: "rodou, 0 hits" ≠ "não rodou" — distinção explícita
    fsi = projecao.get("formas_sem_instancias") or []
    if fsi:
        H.append("<p>Detectores que RODARAM nas superfícies varridas e "
                 "voltaram com 0 instâncias: "
                 + ", ".join(f"<code>{_esc(f)}</code>" for f in fsi)
                 + f" — 0 instâncias em {_esc(superficies_de(cob))} "
                   "(o detector rodou; isto não é afirmação sobre outras "
                   "superfícies).</p>")

    # Por Atividade
    H.append("<h2>Atividades</h2>")
    for atv in projecao["atividades"]:
        H.append(f"<h3>{_esc(atv['nome'])}</h3>")
        H.append(f"<p><code>{_esc(atv['ulid'])}</code> · estado "
                 f"{_esc(atv['estado'])} · hosts {_esc(', '.join(atv['hosts']))}"
                 f" · cwd <code>{_esc(atv['cwd'])}</code></p>")
        va = atv["voz_acao"]
        H.append(f"<p>voz×ação: {va['voz']}×{va['acao']} "
                 f"(+{va.get('acao_delegada_sidechain', 0)} ações delegadas a "
                 f"subagentes, fora da manchete) "
                 f"(unidade: {va['unidade']}; {_esc(va['nota'])})</p>")
        H.append("<table><tr><th>sessão</th><th>trecho</th><th>início</th>"
                 "<th>fim</th>"
                 "<th>min ativos (teto 300s)</th><th>sens. 120/600s</th>"
                 "<th>voz</th><th>ação</th><th>commits</th></tr>")
        for t in atv["sessions"]:
            ma = t["min_ativos"]
            sens = ma["sensibilidade"]
            corte = t.get("corte")
            tr_lbl = (t.get("trecho_id", "—") or "—")
            if corte:
                tr_lbl += f" ({corte['sinal']})"
            H.append(
                f"<tr><td><code>{_esc(t['session_id'][:8])}</code></td>"
                f"<td><code>{_esc(tr_lbl)}</code></td>"
                f"<td>{_esc((t['ts_start'] or '')[:16])}</td>"
                f"<td>{_esc((t['ts_end'] or '')[:16])}</td>"
                f"<td>{ma['minutos']}</td>"
                f"<td>{sens.get('cap_120s')}/{sens.get('cap_600s')}</td>"
                f"<td>{t['n_eventos_voz']}</td>"
                f"<td>{t['n_eventos_acao']} ({t['n_eventos_acao_sidechain']} "
                f"sidechain)</td>"
                # NEW-8: âncoras de aceitação nunca somem num "+N" — até 12
                # commits renderizam TODOS
                f"<td>{_esc(', '.join(c[:7] for c in t['commits'][:12]))}"
                f"{_esc(' +' + str(len(t['commits']) - 12) if len(t['commits']) > 12 else '')}"
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
        tc = eval_estagio0.get("thresholds_congelados") or {
            "precisao_min": EVAL_PRECISAO_MIN,
            "concordancia_min": EVAL_CONCORDANCIA_MIN}
        tipo = eval_estagio0.get("tipo_amostra", "amostra")
        pop = eval_estagio0.get("populacao_n2")
        H.append(f"<p>Rotuladores cegos: {_esc(', '.join(eval_estagio0.get('rotuladores', ['?'])))} · "
                 f"{_esc(tipo)} de {eval_estagio0.get('amostra', '—')} itens"
                 f"{f' (população N2 = {pop})' if pop else ''} · thresholds "
                 f"congelados antes da rodada: precisão ≥ {tc['precisao_min']}, "
                 f"concordância ≥ {tc['concordancia_min']}.</p>")
        pr = eval_estagio0.get("pre_registro") or {}
        if pr.get("sha256_bloco_congelado"):
            ver = {True: "verificado", False: "FALHOU",
                   None: "sem recibo"}[pr.get("verificado")]
            H.append(f"<p>Pré-registro: sha256 <code>"
                     f"{_esc(pr['sha256_bloco_congelado'][:16])}…</code> "
                     f"gravado em {_esc(pr.get('gravado_em'))} — {_esc(ver)}."
                     f"</p>")
        ct = eval_estagio0.get("catch_trials") or {}
        if ct.get("n"):
            H.append(f"<p>Catch trials (gold pré-registrado, fora das "
                     f"métricas): rotulador A {ct['a']}/{ct['n']} · "
                     f"rotulador B {ct['b']}/{ct['n']}."
                     + (f" {_esc(ct['contexto'])}" if ct.get("contexto")
                        else "") + "</p>")
        H.append("<table><tr><th>forma</th><th>n</th><th>precisão</th>"
                 "<th>concordância (p_o)</th><th>κ</th><th>veredicto</th></tr>")
        for forma, f in sorted(eval_estagio0["por_forma"].items()):
            H.append(f"<tr><td>{_esc(forma)}</td><td>{f.get('n', '—')}</td>"
                     f"<td>{f.get('precisao') if f.get('precisao') is not None else '—'}"
                     f"</td><td>{f.get('concordancia', '—')}</td>"
                     f"<td>{f.get('kappa') if f.get('kappa') is not None else '—'}</td>"
                     f"<td>{_esc(f.get('veredicto', '—'))}</td></tr>")
        H.append("</table>")
        g = eval_estagio0.get("global") or {}
        if g:
            H.append(f"<p>Agregado: p_o {g.get('p_o')} · taxa de desacordo "
                     f"{g.get('taxa_desacordo')} · κ de Cohen "
                     f"{g.get('kappa') if g.get('kappa') is not None else '—'} "
                     f"(3 classes, {g.get('n_pares')} pares) · prevalência "
                     f"{_esc(json.dumps(g.get('prevalencia_rotulador_a', {}), ensure_ascii=False))}. "
                     f"{_esc(g.get('nota', ''))}</p>")
        H.append("<p>O caso 7fed4159/17s é TESTE DE REGRESSÃO do detector "
                 "genérico, nunca evidência de validade.</p>")
    else:
        H.append(f"<p>Estágio 0 ainda não executado — TODAS as formas estão "
                 f"marcadas experimentais. Métricas: {_esc(aus)}.</p>")

    # GATE de render (finding R1 #2): N3/N4 cuja base toca forma sem selo
    # `confiavel` NÃO entram no relatório principal — declarados na contagem
    def _formas_de_n3(n3):
        return {reg.by_id[b]["forma"] for b in n3["base"] if b in reg.by_id}

    def _n3_confiavel(n3):
        return all(veredicto(f) == "confiavel" for f in _formas_de_n3(n3))

    n3s_gate = [n3 for n3 in n3s.values() if _n3_confiavel(n3)]
    n3s_fora = len(n3s) - len(n3s_gate)
    n4s_gate = [n4 for n4 in n4s
                if all(_n3_confiavel(n3s[b]) for b in n4["base"]
                       if b in n3s)]
    n4s_fora = len(n4s) - len(n4s_gate)

    # N3
    if n3s_gate or n3s_fora:
        H.append("<h2>Inferências (N3) — com incerteza declarada</h2>")
        if n3s_fora:
            H.append(f"<p class='exp'>{n3s_fora} inferência(s) fora do "
                     "relatório principal: base em forma sem selo do "
                     "estágio 0.</p>")
    if n3s_gate:
        H.append("<ul>")
        for n3 in sorted(n3s_gate, key=lambda r: -r["confianca"]):
            alts = "; ".join(n3["alternativas"])
            H.append(f"<li>{_esc(n3['claim'])} <i>(confiança "
                     f"{n3['confianca']:.2f}; alternativas inocentes: "
                     f"{_esc(alts)}; base {_esc(', '.join(n3['base']))})</i></li>")
        H.append("</ul>")

    # N4 — SÓ perguntas quando proposta; gate idem
    H.append("<h2>Perguntas ao operador (hipóteses N4 — a sua correção "
             "vence)</h2>")
    if n4s_fora:
        H.append(f"<p class='exp'>{n4s_fora} hipótese(s) fora do relatório "
                 "principal: base em forma sem selo do estágio 0.</p>")
    n4s = n4s_gate
    if n4s:
        H.append("<ul>")
        for n4 in n4s:
            resp = n4.get("resposta_operador") or {}
            nota_html = (" — resposta do operador: " + _vb(resp["nota"])
                         if resp.get("nota") else "")
            if n4["status"] == "confirmada":
                H.append(f"<li>[confirmada] {_esc(n4['hipotese'])}"
                         f"{nota_html}</li>")
            elif n4["status"] in ("contestada", "expirada"):
                inval = (f" (invalid_at {_esc(n4['invalid_at'][:16])})"
                         if n4.get("invalid_at") else "")
                H.append(f"<li class='exp'>[{_esc(n4['status'])}{inval}] "
                         f"{_esc(n4['hipotese'])}{nota_html}</li>")
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
    ev = json.loads(Path(args.eval).read_text()) if args.eval else None
    reg, projecao = pipeline(args.workdir, args.host, complete_fn,
                             janela_dias=args.janela_dias,
                             model=args.complete_cmd or "nenhum",
                             eval_estagio0=ev)
    state = persistir(args.state, reg, projecao)
    html = render_report(reg, projecao, ev)
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
        amostra, pre_registro = eval_preparar(reg, args.workdir,
                                              max_amostra=args.max)
        # recibo de pré-registro gravado ANTES de qualquer rótulo (finding
        # R1 #14); NÃO entregar aos rotuladores (contém o gold dos catch)
        _guard_estado(state)
        (state / "pre-registro.json").write_text(
            json.dumps(pre_registro, ensure_ascii=False, indent=1),
            encoding="utf-8")
        Path(args.out).write_text(redigir(json.dumps(
            amostra, ensure_ascii=False, indent=1)), encoding="utf-8")
        print(f"amostra: {len(amostra['itens'])} itens → {args.out}; "
              f"pré-registro → {state / 'pre-registro.json'}")
    else:  # ingest
        amostra = json.loads(Path(args.amostra).read_text())
        la = json.loads(Path(args.labels[0]).read_text())
        lb = json.loads(Path(args.labels[1]).read_text())
        prp = Path(args.pre_registro or (state / "pre-registro.json"))
        pre_registro = json.loads(prp.read_text()) if prp.exists() else None
        ev = eval_ingerir(amostra, la, lb, pre_registro)
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


def responder_n4(state_dir, n4_id, veredito, nota=None, agora=None):
    """R4 item 1: resposta do operador a uma hipótese N4 — their correction
    always wins. `veredito`: 'confirmo'|'contesto'. Transição
    proposta→confirmada|contestada; bi-temporal: contestada ganha
    `invalid_at`, NUNCA deleção. Idempotência: já respondida → erro (a
    resposta do operador não é sobrescrevível por ninguém). O desfecho vira
    linha de `respostas.jsonl` (corpus rotulado pelo operador que alimenta
    estágio-0 futuro)."""
    if veredito not in ("confirmo", "contesto"):
        raise ValueError(f"veredito inválido: {veredito!r} "
                         "(use confirmo|contesto)")
    state = _guard_estado(state_dir)
    reg, projecao = _carregar_estado(state)
    n4 = reg.by_id.get(n4_id)
    if n4 is None or n4.get("nivel") != 4:
        raise ValueError(f"{n4_id}: N4 não encontrado no estado")
    if n4.get("status") != "proposta":
        raise ValueError(
            f"{n4_id} já respondida (status={n4['status']}) — a resposta "
            "registrada do operador não se sobrescreve")
    ts = agora or datetime.now(tz=timezone.utc).isoformat()
    novo_status = "confirmada" if veredito == "confirmo" else "contestada"
    nota_red = redigir(nota, entropia=True)[:500] if nota else None
    n4["status"] = novo_status
    n4["resposta_operador"] = {"veredito": veredito, "nota": nota_red,
                               "ts": ts}
    if novo_status == "contestada":
        n4["invalid_at"] = ts
    with open(state / "respostas.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(
            {"n4_id": n4_id, "hipotese": n4["hipotese"],
             "veredito": veredito, "status": novo_status, "nota": nota_red,
             "ts": ts, "base": n4.get("base", []),
             "executores_da_base": n4.get("executores_da_base"),
             "detector_version": DETECTOR_VERSION},
            ensure_ascii=False, sort_keys=True) + "\n")
    persistir(state, reg, projecao)
    evp = state / "eval.json"
    ev = (json.loads(evp.read_text()) if evp.exists()
          else projecao.get("eval_estagio0"))
    (state / "report.html").write_text(render_report(reg, projecao, ev),
                                       encoding="utf-8")
    return n4


def _cmd_responder(args):
    try:
        n4 = responder_n4(args.state, args.n4_id, args.veredito,
                          nota=args.nota)
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"id": n4["id"], "status": n4["status"],
                      "resposta_operador": n4["resposta_operador"]},
                     ensure_ascii=False, indent=1))


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
    p.add_argument("--eval", default=None,
                   help="eval.json do estágio 0 — GATE dos N3/N4 (sem ele, "
                        "nenhum N3/N4 é gerado; degradação declarada)")
    p.set_defaults(fn=_cmd_backfill)

    p = sub.add_parser("eval", help="estágio 0 — avaliação cega")
    p.add_argument("acao", choices=["prepare", "ingest"])
    p.add_argument("--state", required=True)
    p.add_argument("--workdir", help="cópia de trabalho (prepare)")
    p.add_argument("--out", help="arquivo da amostra (prepare)")
    p.add_argument("--amostra", help="arquivo da amostra (ingest)")
    p.add_argument("--labels", nargs=2, help="dois arquivos de rótulos (ingest)")
    p.add_argument("--pre-registro", dest="pre_registro", default=None,
                   help="recibo de pré-registro (default: <state>/pre-registro.json)")
    p.add_argument("--max", type=int, default=30)
    p.set_defaults(fn=_cmd_eval)

    p = sub.add_parser("responder", help="resposta do operador a uma "
                       "hipótese N4 (confirmo|contesto) — their correction "
                       "always wins")
    p.add_argument("n4_id")
    p.add_argument("veredito", choices=["confirmo", "contesto"])
    p.add_argument("--nota", default=None,
                   help="resposta verbatim do operador (opcional)")
    p.add_argument("--state", required=True)
    p.set_defaults(fn=_cmd_responder)

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

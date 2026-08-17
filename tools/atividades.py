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

# R6.1 Front A: tuning GUIADO pela medição de recall (966d854) — toda
# mudança abaixo cita o dado; thresholds novos são PROPOSTA aguardando
# ratificação do operador (marcado no relatório).
DETECTOR_VERSION = "n2-v2.1-proposta"
DETECTOR_VERSION_ANTERIOR = "n2-v2.0"

# Lexicon FECHADO de aceites do operador, construído da voz REAL dos
# corpora (recall D1: p̂=1.0 no pool ≤20 chars — "blz manda", "pode mandar",
# "perfeito" eram perdas do teto de 6 chars). Versionado com o detector.
D1_ACEITE_LEX = frozenset((
    "ok", "sim", "vai", "blz", "bora", "dale", "isso", "show", "fechou",
    "perfeito", "pode", "manda", "faz", "roda", "dispara", "ok pode",
    "pode mandar", "blz manda", "manda ver", "manda bala", "pode ir",
    "vai la", "vai lá", "isso mesmo", "faz isso", "roda ai", "roda aí",
    "dispara o 1", "pode rodar", "pode fazer", "segue", "toca"))
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
# R5.2 finding 5: ida-e-volta não é mudança de emprego — excursão a outro cwd
# que RETORNA ao cwd-base em ≤900s é digressão (sem corte). Aterrado no
# dig-5 B: interrupções curtas no IDE são 3–12min (Meyer TSE 2017); 15min é
# o limiar de retomada (Parnin/Sanchez) — acima disso deixa de ser excursão.
DIGRESSAO_RETORNO_S = 900.0
# R5.2 finding 5: PISO para virar Atividade — cluster precisa de duração
# ativa ≥300s (gaps <5min são "pensar", não emprego — Xia TSE 2018/Minelli)
# E ≥5 eventos (abaixo do próprio limiar de corte sustentado, um cluster
# menor que isso não se sustenta sozinho). Sub-piso dobra na Atividade do
# trecho VIZINHO como digressão — nunca some.
PISO_ATIVIDADE_SEGUNDOS = 300.0
PISO_ATIVIDADE_EVENTOS = 5
# R5.2 finding 1: merge de clusters exige EVIDÊNCIA — prefixo de cwd
# relacionado só conta com o pai em profundidade ≥3 (/home/user NUNCA é
# âncora de merge; /home/user/projeto pode absorver /home/user/projeto/sub)
PROFUNDIDADE_MIN_MERGE_CWD = 3
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
    # D1 v2.1 (recall: 0.080 no espaço relaxado; seeded aceite-7-15 0/3 e
    # execução excluída = perdas reais tipo "dispare o 1"→24s→python3):
    # gatilho = curto ≤6 OU lexicon fechado OU imperativo-verbo-inicial
    # ≤30; classes de ação + execução. Janela MANTIDA em 120s (PROPOSTA):
    # o conceito é imediatismo — a classe 121-600s (seeded 0/3) é um
    # comportamento mais lento que dobrá-la aqui inflaria FP; fica
    # documentada como buraco conhecido para decisão do operador.
    "resposta-curta-seguida-de-acao": {
        "max_chars_voz": 6, "janela_s": 120, "aceite_lexicon": True,
        "imperativo_max_chars": 30,
        "classes_acao": ("escrita", "commit", "execucao")},
    # D2 v2.1: min_chars_explicacao=800 RE-DECLARADO como conceito (≈150+
    # palavras — uma explicação substantiva, não um ack; o recall relaxado
    # 800→1 media outro conceito); resposta aceita o lexicon (recall D2
    # 0.129: respostas 7-20 chars reais tipo "blz perfeito")
    "pergunta-explicacao-resposta-curta": {
        "min_chars_explicacao": 800, "max_chars_resposta": 6,
        "aceite_lexicon": True, "janela_s": 1800},
    # D3 v2.1: MESMO ALVO (verbo + recurso extraído dos args), não mesma
    # cabeça de 2 tokens ("tail -c"≠"tail -n" do mesmo arquivo eram grupos
    # distintos; cabeça "cd" escondia leituras — controle de fundo);
    # min_repeticoes=3 e janela 3600 re-justificados: 3 leituras na mesma
    # hora é a cadência de polling confirmada no estágio-0 (n=9..17, p=1.0)
    "leituras-repetidas-de-estado-externo": {
        "min_repeticoes": 3, "janela_s": 3600, "mesmo_alvo": True},
    "sessoes-com-abertura-semelhante": {"jaccard_min": 0.6},
    "entrega-com-perguntas-sem-turno-de-resposta-observado": {"min_perguntas": 2},
    # D6 v2.1: interrogativas SEGUEM excluídas (R1#16 estava certo);
    # max_chars 15→20 cobre os aceites reais do lexicon ("blz manda"=9,
    # "pode mandar"=11, rajadas de 16-20 no pool relaxado); janela mantida
    "rajada-de-turnos-curtos": {"min_turnos": 3, "max_chars": 20, "janela_s": 600},
    # ----- Front B: catálogo POSITIVO (nomes descritivos; a re-elaboração
    # e o engajamento que o mentor QUER ver) -----
    "resposta-longa-em-voz-propria-apos-explicacao": {
        "min_chars_explicacao": 800, "min_chars_resposta": 300,
        "janela_s": 1800},
    "pergunta-de-aprofundamento-apos-explicacao": {
        "min_chars_explicacao": 800, "min_chars_pergunta": 40,
        "janela_s": 1800},
    "retomada-de-entrega-com-vocabulario-da-entrega": {
        "min_perguntas_entrega": 2, "min_tokens_compartilhados": 3,
        "min_len_token": 4, "janela_s": 3600},
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
        # guarda de custo: o padrão de bloco PEM é quadrático em linhas
        # gigantes que CONTÊM o texto "PRIVATE KEY" sem END (ex.: transcripts
        # que discutem a própria regex) — só roda com o marcador presente
        if "PRIVATE KEY" in rx.pattern and "PRIVATE KEY" not in texto:
            continue
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

    # R6.1 A2: `cd <path>` é wrapper NEUTRO — não classifica o comando
    # composto (a cegueira "cd X && leitura → execucao" escondia leituras
    # do pool do D3; achada pelo controle de fundo)
    if head == "cd" and len(toks) <= 2:
        return None

    # R6.1 A2: heredoc `python3 - <<X` decide por PAYLOAD quando viável
    # (heurística mecânica declarada); sem decisão → execucao-com-nota
    if head in ("python3", "python") and len(toks) > 1 \
            and toks[1] in ("-", "-c"):
        # restaurar payloads (aspas do heredoc/-c viraram placeholders)
        restaurado = _RX_PLACEHOLDER.sub(
            lambda m: payloads[int(m.group(1))], seg)
        if toks[1] == "-c":
            m_c = re.search(r"-c\s+(.*)", restaurado, re.S)
            corpo = m_c.group(1) if m_c else ""
        else:
            m_h = re.search(r"<<-?\s*'?(\w+)'?\s*\n(.*)", restaurado, re.S)
            corpo = m_h.group(2) if m_h else ""
        if corpo:
            if re.search(r"open\([^)]*['\"](w|a|wb|ab)['\"]"
                         r"|\.write\(|\bos\.(remove|rename|makedirs)\b"
                         r"|\bshutil\.|\bsubprocess\b|json\.dump\(",
                         corpo):
                return "escrita"
            if re.search(r"\bjson\.load\b|\bopen\([^)]*\)|\bprint\(",
                         corpo) :
                return "leitura"
        return "execucao"

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
    r"|<command-name>|<system-reminder>"
    # R6.1 Front C: formas de protocolo do host turing — despachos de loop
    # ("You are the R1 IMPLEMENTER…"), invocações de rito/skill
    r"|You are the (?:R\d|\*\*|[A-Z0-9.]+ (?:IMPLEMENTER|VERIFIER|LABELER))"
    r"|Você é (?:o|um) (?:anotador|rotulador|verificador)\b"
    r"|The coordinator sent a message)"
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
    chaves_leitura = {}       # v2.1 D3: (verbo, alvo) bruto por evento —
    #                           transiente, nunca persistido
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
                        "n_perguntas": texto.count("?"),
                        # tokens transientes p/ retomada-de-entrega (nunca
                        # persistidos)
                        "tokens": _tokens(texto)})
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
                        chaves_leitura[ev["id"]] = _chave_leitura(cmd)
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
            "ts_linhas": ts_linhas, "chaves_leitura": chaves_leitura}


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


def segmentar(sessao, complete_fn=None, orcamento=None, model="injetado"):
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

    # 3. cwd sustentado (runs; digressão curta não corta; R5.2 finding 5:
    # excursão que RETORNA ao cwd-base em ≤DIGRESSAO_RETORNO_S também não —
    # ida-e-volta não é mudança de emprego)
    arbitragens = []
    runs = _runs_de_cwd(fluxo)
    if runs:
        base = runs[0][0]
        for r_i, (cwd, idx, n) in enumerate(runs[1:], 1):
            if cwd == base or not cwd:
                continue
            ts_c, linha_c, _ = fluxo[idx]
            dur_run = fluxo[idx + n - 1][0] - ts_c
            proximo_volta = (r_i + 1 < len(runs)
                             and runs[r_i + 1][0] == base)
            if proximo_volta and dur_run <= DIGRESSAO_RETORNO_S:
                continue  # digressão-com-retorno: sem corte (finding 5)
            if n >= N_CWD_SUSTENTADO:
                cortes.append({"ts": ts_c, "linha": linha_c,
                               "sinal": "cwd-sustentado",
                               "detalhe": f"{n} eventos em {cwd}"})
                base = cwd
            elif n >= N_CWD_AMBIGUO and complete_fn and orcamento \
                    and orcamento.permitir("segmentar-arbitrar"):
                prompt = (
                    "Num log de trabalho, o diretório mudou de "
                    f"'{base}' para '{cwd}' por {n} eventos "
                    "consecutivos. Isso é o início de uma atividade "
                    "DISTINTA ou uma digressão da mesma atividade? "
                    "Responda exatamente DISTINTA ou DIGRESSAO.")
                try:
                    resp = complete_fn(prompt)
                except Exception:
                    resp = ""
                # R5.2 finding 10: recibo COMPLETO da arbitragem, cortada
                # ou não — o re-run pode particionar diferente e o operador
                # precisa auditar a decisão
                recibo = {"linha": linha_c, "de": base, "para": cwd,
                          "n_eventos": n, "model": model,
                          "prompt_sha256": hashlib.sha256(
                              prompt.encode()).hexdigest(),
                          "resposta": redigir((resp or "").strip(),
                                              entropia=True)[:120]}
                arbitragens.append(recibo)
                if "DISTINTA" in (resp or "").upper():
                    cortes.append({"ts": ts_c, "linha": linha_c,
                                   "sinal": "cwd-ambiguo-arbitrado-llm",
                                   "detalhe": f"{n} eventos em {cwd}",
                                   "arbitragem": recibo})
                    base = cwd
            # senão: candidato ambíguo sem completer → NÃO corta (dig-5 A)
    sessao["arbitragens"] = arbitragens

    # R5.2 finding 3: corte NUNCA atravessa uma janela voz→ação ≤120s — o
    # corte move para depois da ação (o par causal fica inteiro num trecho)
    vozes_ts = sorted(v[0] for v in sessao["vozes"] if v[0] is not None)
    acoes_seq = sorted(
        (_parse_ts(e["ts"]), e["evidencia"]["linha"])
        for e in sessao["eventos"]
        if e["kind"] != "voz-turno" and e["ts"]
        and not e["conteudo_redigido"].get("sidechain"))
    import bisect as _bisect

    def _mover_se_atravessa(c):
        for _ in range(10):
            i_v = _bisect.bisect_left(vozes_ts, c["ts"]) - 1
            i_a = _bisect.bisect_left(acoes_seq, (c["ts"], -1))
            if i_v < 0 or i_a >= len(acoes_seq):
                return c
            ts_v = vozes_ts[i_v]
            ts_a, linha_a = acoes_seq[i_a]
            if ts_a - ts_v <= 120:
                c = dict(c, ts=ts_a + 1e-3, linha=linha_a,
                         movido=f"corte movido para depois da ação "
                                f"L{linha_a} (janela voz→ação ≤120s)")
                continue
            return c
        return c

    cortes = [_mover_se_atravessa(c) for c in cortes]

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
        # R5.2 finding 9: âncora e start na MESMA base — trecho não-inicial
        # começa exatamente na linha do corte
        if k > 0:
            linha_start = cortes_finais[k - 1]["linha"]
        else:
            linha_start = (min(l for _, l in sessao.get("ts_linhas") or
                               [(0, 1)]) if sessao.get("ts_linhas")
                           else (min(f[1] for f in fl) if fl else 1))
        # R5.2 finding 1: trecho sem voz NUNCA herda a abertura da sessão —
        # string herdada não é evidência e criava a Atividade-gaveta
        abertura = next((redigir(t, entropia=True)[:200]
                         for _, t, _, _, _ in vzs if len(t) >= 8), "")
        if not abertura and vzs:
            abertura = redigir(vzs[0][1], entropia=True)[:200]
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


def _acao_em_classes(ev, classes):
    """v2.1: a ação do D1 qualifica pelas classes DECLARADAS nos thresholds
    (inclui execução — a perda 'dispare o 1'→python3 medida no recall)."""
    if ev["kind"] == "commit":
        return "commit" in classes
    if ev["kind"] not in ("tool-call", "spawn"):
        return False
    return ev["conteudo_redigido"].get("classe") in classes


def _gatilho_aceite(texto, p):
    """v2.1: gatilho do D1 — curto ≤6 (regra v2.0) OU lexicon fechado OU
    imperativo-verbo-inicial ≤30 chars. Retorna o nome do gatilho ou None."""
    t = _normalizar_voz(texto)
    if not t:
        return None
    if t in _GREETING_LEX:
        # correção pós-rotulagem v2.1: "iae" disparava D1 via gatilho curto
        # — saudação nunca é aceite (a mesma lição da agência, R2 finding 6)
        return None
    if len(t) <= p["max_chars_voz"]:
        return "curto"
    if p.get("aceite_lexicon") and t in D1_ACEITE_LEX:
        return "lexicon"
    prim = t.split(" ", 1)[0]
    if len(t) <= p.get("imperativo_max_chars", 0) \
            and prim in _IMPERATIVO_V1 and not t.endswith("?"):
        return "imperativo"
    return None


def _chave_leitura(cmd):
    """v2.1 D3: (verbo, alvo) do comando de leitura — MESMO RECURSO, não
    mesma cabeça de 2 tokens ('tail -c f' e 'tail -n f' são o mesmo
    polling de f; 'cd X && tail f' idem).

    Correção pós-rotulagem v2.1 (bug de EXTRAÇÃO achado pelos rotuladores:
    5/7 nao por alvo='head'/'EOF'): o alvo vem do PRIMEIRO segmento com
    verbo real, cortado ANTES do pipe e do heredoc — nunca um estágio de
    pipe. Heredoc → alvo opaco ''."""
    texto, _p = _com_placeholders(cmd or "")
    texto = texto.split("<<")[0]  # heredoc fora do alvo
    sem = _RX_STDERR_REDIR.sub(" ", texto)
    for seg in re.split(r"&&|\|\||;", sem):
        seg = seg.split("|")[0]  # alvo = 1º estágio do pipe
        toks = seg.split()
        while toks:
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0]) \
                    or toks[0] in _WRAPPERS_1 or toks[0] == "env":
                toks = toks[1:]
            elif toks[0] == "cd":
                toks = toks[2:] if len(toks) > 1 else []
            elif toks[0] == "timeout":
                toks = toks[1:]
                if toks and re.match(r"^\d+[smhd]?$", toks[0]):
                    toks = toks[1:]
            else:
                break
        if not toks:
            continue
        verbo = toks[0].rsplit("/", 1)[-1]
        alvo = next((t for t in reversed(toks[1:])
                     if not t.startswith("-") and not t.startswith(">")
                     and not t.startswith("<")), "")
        return (verbo, alvo)
    return ("?", "?")


def _aplicar_piso(atividades, trechos, log):
    """R5.2 finding 5: cluster abaixo do piso (duração ativa <
    PISO_ATIVIDADE_SEGUNDOS OU eventos < PISO_ATIVIDADE_EVENTOS) não vira
    Atividade — dobra na Atividade do trecho VIZINHO (anterior na sessão;
    senão o seguinte) como digressão, com log. Nunca some."""
    if len(atividades) <= 1:
        return atividades

    def _eventos(atv):
        return sum(t["n_eventos_voz"] + t["n_eventos_acao"]
                   for t in atv["sessions"])

    abaixo = {a["ulid"] for a in atividades
              if a["segundos_ativos_total"] < PISO_ATIVIDADE_SEGUNDOS
              or _eventos(a) < PISO_ATIVIDADE_EVENTOS}
    if not abaixo or len(abaixo) == len(atividades):
        return atividades
    atv_por_trecho = {tid: a for a in atividades
                      for tid in a.get("trecho_ids", [])}
    por_sessao = defaultdict(list)
    for tr in trechos:
        por_sessao[tr["session_id"]].append(tr)
    for lst in por_sessao.values():
        lst.sort(key=lambda t: t["span"]["ts_start"] or "")
    vivos = {a["ulid"]: a for a in atividades if a["ulid"] not in abaixo}
    for a in atividades:
        if a["ulid"] not in abaixo:
            continue
        for tid, touch in zip(a.get("trecho_ids", []), a["sessions"]):
            lst = por_sessao.get(touch["session_id"], [])
            idx = next((i for i, tr in enumerate(lst)
                        if tr["trecho_id"] == tid), None)
            destino = None
            if idx is not None:
                for i in (list(range(idx - 1, -1, -1))
                          + list(range(idx + 1, len(lst)))):
                    cand = atv_por_trecho.get(lst[i]["trecho_id"])
                    if cand and cand["ulid"] not in abaixo:
                        destino = vivos[cand["ulid"]]
                        break
            if destino is None:
                destino = next(iter(vivos.values()))
            touch = dict(touch, digressao_de=a["cwd"])
            destino["sessions"].append(touch)
            destino["trecho_ids"].append(tid)
            destino["segundos_ativos_total"] = round(
                destino["segundos_ativos_total"]
                + (touch["min_ativos"].get("segundos") or 0.0), 3)
            log.append({"acao": "dobrado-no-vizinho", "de": a["cwd"],
                        "para": destino["cwd"], "trecho": tid,
                        "razao": f"sub-piso ({a['segundos_ativos_total']:.0f}s"
                                 f" ativos, {_eventos(a)} eventos; piso "
                                 f"{PISO_ATIVIDADE_SEGUNDOS:.0f}s/"
                                 f"{PISO_ATIVIDADE_EVENTOS}ev)",
                        "cluster_version": CLUSTER_VERSION})
    out = []
    for a in vivos.values():
        a["sessions"].sort(key=lambda t: t["ts_start"] or "")
        a["session_ids"] = sorted({t["session_id"] for t in a["sessions"]})
        out.append(a)
    return sorted(out, key=lambda a: a["ulid"])


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


def _span_de(sessao, ts):
    """Span de comportamento contíguo (mesma Atividade) do timestamp —
    fallback para o trecho quando os spans ainda não foram atribuídos."""
    tid = _trecho_de(sessao, ts)
    spans = sessao.get("spans_por_trecho") or {}
    return spans.get(tid, tid)


def detectar_sessao(sessao, reg):
    """Detectores intra-sessão (D1, D2, D3, D5, D6) sobre os N1 já registrados."""
    out = []
    th = THRESHOLDS
    vozes = sessao["vozes"]  # (ts, texto, n1_id, linha, tem_antecedente)
    acoes = [e for e in sessao["eventos"] if e["kind"] != "voz-turno"
             and e["ts"] is not None]
    acoes.sort(key=lambda e: e["ts"])

    # D1 resposta-curta-seguida-de-acao (v2.1: lexicon + imperativo +
    # classe execução — mudanças citam o recall 0.080/seeded 0-de-3)
    p = th["resposta-curta-seguida-de-acao"]
    for ts, texto, vid, linha, _a in vozes:
        gat = _gatilho_aceite(texto, p)
        if gat:
            for ac in acoes:
                d = _parse_ts(ac["ts"]) - ts
                if 0 < d <= p["janela_s"] \
                        and _acao_em_classes(ac, p["classes_acao"]) \
                        and not ac["conteudo_redigido"].get("sidechain"):
                    out.append(_mk_n2(
                        reg, "resposta-curta-seguida-de-acao", [vid, ac["id"]],
                        {"delta_s": round(d, 1), "chars_voz": len(texto),
                         "gatilho": gat,
                         "classe_acao": ("commit" if ac["kind"] == "commit"
                                         else ac["conteudo_redigido"]
                                         .get("classe"))},
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
        t2n = _normalizar_voz(t2)
        resposta_ok = (0 < len(t2) <= p["max_chars_resposta"]
                       or (p.get("aceite_lexicon") and t2n in D1_ACEITE_LEX))
        if not (resposta_ok and 0 < ts2 - ts <= p["janela_s"]):
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
    chaves_l = sessao.get("chaves_leitura") or {}
    for ac in acoes:
        c = ac["conteudo_redigido"]
        if c.get("tool") == "Bash" and c.get("classe") == "leitura" \
                and c.get("comando_cabeca") and not c.get("sidechain"):
            # R4 item 2: chave BRUTA transiente (redação fundia cabeças).
            # R5.2 finding 4: chave inclui o SPAN de comportamento.
            # v2.1 (Front A3): MESMO ALVO — (verbo, recurso), não cabeça
            # de 2 tokens ('tail -c f'≡'tail -n f'; 'cd X && tail f' idem)
            chave = (chaves_l.get(ac["id"])
                     or _chave_leitura(brutas.get(
                         ac["id"], c["comando_cabeca"])))
            por_cabeca[(chave,
                        _span_de(sessao, _parse_ts(ac["ts"])))].append(ac)
    for (cabeca, _trecho), lst in por_cabeca.items():
        i = 0
        while i < len(lst):
            j = i
            while j + 1 < len(lst) and _parse_ts(lst[j + 1]["ts"]) - \
                    _parse_ts(lst[i]["ts"]) <= p["janela_s"]:
                j += 1
            if j - i + 1 >= p["min_repeticoes"]:
                grupo = lst[i:j + 1]
                verbo, alvo = (cabeca if isinstance(cabeca, tuple)
                               else (cabeca, ""))
                out.append(_mk_n2(
                    reg, "leituras-repetidas-de-estado-externo",
                    [g["id"] for g in grupo],
                    # persistir SÓ o par redigido (o bruto é transiente)
                    {"comando_cabeca": redigir(
                        f"{verbo} {alvo}".strip(), entropia=True)[:80],
                     "verbo": redigir(verbo, entropia=True)[:40],
                     "alvo": redigir(alvo, entropia=True)[:80],
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
    curtos = [(ts, vid, _span_de(sessao, ts)) for ts, t, vid, _, _ in vozes
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

    # ----- Front B (v2.1): formas POSITIVAS -----
    # P1/P2: explicação substantiva (≥800) → PRÓXIMO turno humano é
    # re-elaboração longa em voz própria (≥300, não-interrogativo) ou
    # pergunta de aprofundamento (≥40, interrogativa)
    p1 = th["resposta-longa-em-voz-propria-apos-explicacao"]
    p2 = th["pergunta-de-aprofundamento-apos-explicacao"]
    for i, (ts, texto, vid, _l, _a) in enumerate(vozes):
        ts_ant = vozes[i - 1][0] if i > 0 else None
        expl = next((a for a in reversed(ats)
                     if a["ts"] < ts
                     and a["chars"] >= p1["min_chars_explicacao"]
                     and (ts_ant is None or a["ts"] > ts_ant)), None)
        if not expl:
            continue
        interrog = texto.rstrip().endswith("?")
        if not interrog and len(texto) >= p1["min_chars_resposta"] \
                and ts - expl["ts"] <= p1["janela_s"]:
            out.append(_mk_n2(
                reg, "resposta-longa-em-voz-propria-apos-explicacao", [vid],
                {"chars_resposta": len(texto),
                 "assistant_linha": expl["linha"],
                 "assistant_chars": expl["chars"]},
                {"de": _iso(expl["ts"]), "ate": _iso(ts)}))
        elif interrog and len(texto) >= p2["min_chars_pergunta"] \
                and ts - expl["ts"] <= p2["janela_s"]:
            out.append(_mk_n2(
                reg, "pergunta-de-aprofundamento-apos-explicacao", [vid],
                {"chars_pergunta": len(texto),
                 "assistant_linha": expl["linha"],
                 "assistant_chars": expl["chars"]},
                {"de": _iso(expl["ts"]), "ate": _iso(ts)}))

    # P3: entrega com ≥2 perguntas → turno humano posterior que RETOMA o
    # vocabulário da entrega (sobreposição lexical mecânica)
    p3 = th["retomada-de-entrega-com-vocabulario-da-entrega"]
    vistos_p3 = set()  # um n2 por turno de retomada (id = hash de [vid])
    for a in ats:
        if a["n_perguntas"] < p3["min_perguntas_entrega"]:
            continue
        toks_a = {t for t in (a.get("tokens") or set())
                  if len(t) >= p3["min_len_token"]
                  and t not in _STOPWORDS_OVERLAP}
        if not toks_a:
            continue
        for ts, texto, vid, _l, _ant in vozes:
            if not (0 < ts - a["ts"] <= p3["janela_s"]):
                continue
            comuns = {t for t in _tokens(texto)
                      if len(t) >= p3["min_len_token"]
                      and t not in _STOPWORDS_OVERLAP} & toks_a
            if len(comuns) >= p3["min_tokens_compartilhados"] \
                    and vid not in vistos_p3:
                vistos_p3.add(vid)
                out.append(_mk_n2(
                    reg, "retomada-de-entrega-com-vocabulario-da-entrega",
                    [vid],
                    {"tokens_compartilhados": len(comuns),
                     "entrega_linha": a["linha"],
                     "amostra_tokens": sorted(
                         redigir(t, entropia=True) for t in comuns)[:5]},
                    {"de": _iso(a["ts"]), "ate": _iso(ts)}))
                break
    return out


def _tokens(texto):
    return set(re.findall(r"[a-zà-ú0-9\-]{3,}", (texto or "").lower()))


# correção pós-rotulagem v2.1: sobreposição lexical do P3 sem stopwords
# ("como/isso/sobre" passavam o filtro de ≥4 chars — apontado pelo
# rotulador B no item 19)
_STOPWORDS_OVERLAP = frozenset((
    "como isso sobre para pela pelo pelos pelas essa esse essas esses "
    "aqui depois antes ainda entre cada qual quando quanto seria estava "
    "tinha tambem também porque então entao mesmo mesma muito mais menos "
    "onde tudo nada alguma algum fazer feito being have that this with "
    "from what your").split())


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
    # R5.2 finding 2: cwd modal do trecho PERSISTE — sem ele a afiliação é
    # inauditável (40% dos trechos tinham cwd ≠ do da Atividade)
    t["cwd"] = redigir(sessao.get("cwd") or "", entropia=True)[:200]
    if seg:
        t["min_ativos"]["segundos"] = round(seg[int(MIN_ATIVOS_CAP_S)], 3)
    if sessao.get("trecho_id"):
        t["trecho_id"] = sessao["trecho_id"]
        t["segment_version"] = sessao.get("segment_version")
        t["span"] = sessao.get("span")
        t["corte"] = sessao.get("corte")
    return t


def _cwd_relacionado(a, b):
    """Pai/filho com o pai em profundidade ≥ PROFUNDIDADE_MIN_MERGE_CWD —
    /home/user nunca ancora merge (R5.2 finding 1)."""
    if not a or not b or a == b:
        return False
    pai, filho = (a, b) if len(a) < len(b) else (b, a)
    if not filho.startswith(pai.rstrip("/") + "/"):
        return False
    return len([x for x in pai.strip("/").split("/") if x]) \
        >= PROFUNDIDADE_MIN_MERGE_CWD


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
    # merge entre grupos SÓ com EVIDÊNCIA (R5.2 finding 1 — string herdada
    # nunca é chave; a união transitiva por jaccard 1.00 de aberturas
    # herdadas criou a Atividade-gaveta):
    #   (a) cwd pai/filho com pai em profundidade ≥ PROFUNDIDADE_MIN_MERGE_CWD
    #   (b) ≥1 arquivo tocado em comum
    #   (c) aberturas GENUÍNAS (ambas não-vazias) com jaccard ≥ 0.6
    chaves = sorted(grupos)
    dono = {c: c for c in chaves}
    p = THRESHOLDS["sessoes-com-abertura-semelhante"]

    def _arquivos_do_grupo(chave):
        # (top5, top1) do grupo (finding 1: "shared top files"). Evidência
        # de mesmo emprego exige DOMINÂNCIA MÚTUA: o arquivo top-1 de cada
        # grupo aparece no top-5 do outro. Um hub tocado unilateralmente
        # (o .tex do paper editado 1-2× de work_exp168) não funde; dois
        # grupos cujo trabalho dominante se cruza nos dois sentidos, sim.
        cnt = Counter(a for s in grupos[chave] for e in s["eventos"]
                      for a in (e["conteudo_redigido"].get("arquivos") or [])
                      if a)
        top5 = {a for a, _ in cnt.most_common(5)}
        top1 = cnt.most_common(1)[0][0] if cnt else None
        return top5, top1

    arquivos_grupo = {c: _arquivos_do_grupo(c) for c in chaves}
    for i in range(len(chaves)):
        for j in range(i + 1, len(chaves)):
            a, b = chaves[i], chaves[j]
            razao = None
            (top5_a, top1_a), (top5_b, top1_b) = (arquivos_grupo[a],
                                                  arquivos_grupo[b])
            if _cwd_relacionado(a, b):
                razao = f"cwd relacionado (pai/filho): {a} ↔ {b}"
            elif top1_a and top1_b and top1_a in top5_b \
                    and top1_b in top5_a \
                    and len(grupos[a]) >= 2 and len(grupos[b]) >= 2:
                # um grupo de 1 trecho com trabalho misto é PONTE, não
                # emprego: a transitividade da união por arquivo através
                # dele fundia dois empregos inteiros. Grupo de 1 trecho só
                # funde por cwd pai/filho; se ficar pequeno demais, o piso
                # o dobra como digressão.
                razao = (f"dominância mútua de arquivos: {top1_a[-60:]} ↔ "
                         f"{top1_b[-60:]}")
            else:
                jac = max((_jaccard(_tokens(sa["abertura"]),
                                    _tokens(sb["abertura"]))
                           for sa in grupos[a] for sb in grupos[b]
                           if sa["abertura"] and sb["abertura"]),
                          default=0.0)
                if jac >= p["jaccard_min"]:
                    razao = f"aberturas genuínas com jaccard {jac:.2f}"
            if razao:
                raiz_a, raiz_b = dono[a], dono[b]
                if raiz_a != raiz_b:
                    for k, v in dono.items():
                        if v == raiz_b:
                            dono[k] = raiz_a
                    log.append({"acao": "merge", "de": raiz_b, "para": raiz_a,
                                "razao": razao,
                                "cluster_version": CLUSTER_VERSION})
    finais = defaultdict(list)
    for c in chaves:
        finais[dono[c]].extend(grupos[c])
    # R5.2 finding 2: cadeia de merge auditável por Atividade final
    merges_por_raiz = defaultdict(list)
    for entry in log:
        if entry.get("acao") == "merge":
            merges_por_raiz[dono.get(entry["para"], entry["para"])].append(
                {k: entry[k] for k in ("de", "para", "razao")})

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
            # R5.2 finding 7: o nomeador vê o TRABALHO (cwd, ferramentas,
            # arquivos), não só a primeira frase dita
            ferr = Counter()
            arqs = Counter()
            for t in touches:
                for f, n in t["top_ferramentas"]:
                    ferr[f] += n
                for a, n in t["top_arquivos"]:
                    arqs[a] += n
            try:
                resp = complete_fn(
                    "Nomeie em no máximo 6 palavras, descritivas e sem "
                    "diagnóstico psicológico, a Atividade de TRABALHO com "
                    "esta evidência (o nome descreve o trabalho feito, não "
                    "a conversa):\n"
                    f"diretório: {chave}\n"
                    f"ferramentas mais usadas: "
                    f"{[f for f, _ in ferr.most_common(4)]}\n"
                    f"arquivos mais tocados: "
                    f"{[os.path.basename(a) for a, _ in arqs.most_common(4)]}\n"
                    "primeiras falas nos trechos:\n"
                    + "\n".join(f"- {s['abertura'][:120]}" for s in ss[:3]
                                if s["abertura"])
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
            # R5.2 finding 2: cadeia de merge + finding 8: total em segundos
            "merges": merges_por_raiz.get(chave, []),
            "segundos_ativos_total": round(sum(
                s.get("segundos_ativos_atribuidos", {}).get(
                    int(MIN_ATIVOS_CAP_S),
                    tempo_ativo_s(s["ts_todos"], MIN_ATIVOS_CAP_S))
                for s in ss), 3),
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
        f"turno humano de aceite (<= {p['max_chars_voz']} chars"
        + (", OU do lexicon fechado de aceites, OU imperativo verbo-inicial"
           f" <= {p['imperativo_max_chars']} chars"
           if p.get("aceite_lexicon") else "")
        + f") seguido, em ate {p['janela_s']}s, de tool call de classe "
        + "/".join(p.get("classes_acao", ("escrita", "commit"))),
    "pergunta-explicacao-resposta-curta": lambda p:
        f"turno humano interrogativo, depois entrada assistant com >= "
        f"{p['min_chars_explicacao']} chars, depois turno humano com <= "
        f"{p['max_chars_resposta']} chars",
    "leituras-repetidas-de-estado-externo": lambda p:
        f">= {p['min_repeticoes']} execucoes Bash de leitura com "
        + ("o MESMO verbo e o MESMO alvo (recurso)"
           if p.get("mesmo_alvo") else "a mesma cabeca de comando")
        + f" em <= {p['janela_s']}s",
    "sessoes-com-abertura-semelhante": lambda p:
        f"aberturas de duas sessoes em dias distintos com jaccard >= "
        f"{p['jaccard_min']}",
    "entrega-com-perguntas-sem-turno-de-resposta-observado": lambda p:
        f"ultima entrada assistant da sessao com >= {p['min_perguntas']} "
        "'?' e nenhum turno humano posterior nesta sessao",
    "rajada-de-turnos-curtos": lambda p:
        f">= {p['min_turnos']} turnos humanos com <= {p['max_chars']} chars "
        f"em <= {p['janela_s']}s",
    "resposta-longa-em-voz-propria-apos-explicacao": lambda p:
        f"entrada assistant com >= {p['min_chars_explicacao']} chars "
        f"seguida (proximo turno humano, <= {p['janela_s']}s) de turno "
        f"humano NAO-interrogativo com >= {p['min_chars_resposta']} chars",
    "pergunta-de-aprofundamento-apos-explicacao": lambda p:
        f"entrada assistant com >= {p['min_chars_explicacao']} chars "
        f"seguida (proximo turno humano, <= {p['janela_s']}s) de turno "
        f"humano INTERROGATIVO com >= {p['min_chars_pergunta']} chars",
    "retomada-de-entrega-com-vocabulario-da-entrega": lambda p:
        f"entrada assistant com >= {p['min_perguntas_entrega']} '?' seguida "
        f"(<= {p['janela_s']}s) de turno humano compartilhando >= "
        f"{p['min_tokens_compartilhados']} tokens (>= {p['min_len_token']} "
        f"chars) com ela",
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
                # perna do assistant JULGADA entra no pacote para QUALQUER
                # forma que a ancore nos params (finding R1 #3; o defeito
                # reapareceu nas formas novas do v2.1 — 16×EI)
                linha_assist = (n2["params"].get("assistant_linha")
                                or n2["params"].get("entrega_linha"))
                if linha_assist:
                    arq = reg.by_id[n2["instancias"][0]]["evidencia"][
                        "arquivo_jsonl"]
                    evid.append({
                        "ancora": {"arquivo": arq,
                                   "linha": linha_assist,
                                   "kind": "assistant-perna"},
                        "carga": _carga_util(workdir, arq, linha_assist)})
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


def eval_delta_preparar(amostra_nova, mapa_a, mapa_b, seed=23,
                        arquivo_ref=None, razao=""):
    """R5.2 finding 6: reuso de rótulos por n2_id + pacote de DELTA que
    SEMPRE leva ≥1 catch trial FRESCO (gold no pré-registro, nunca no
    pacote). `mapa_a/b`: {n2_id: resposta} de rodadas anteriores.

    Retorna (delta_amostra, reuso_a, reuso_b, pre_registro_delta)."""
    reuso_a, reuso_b, delta = [], [], []
    for i in amostra_nova["itens"]:
        nid = i["n2_id"]
        if nid in mapa_a and nid in mapa_b:
            reuso_a.append({"item": i["item"], "resposta": mapa_a[nid]})
            reuso_b.append({"item": i["item"], "resposta": mapa_b[nid]})
        else:
            delta.append(dict(i))
    catch_gold = {}
    base_n = max((i["item"] for i in amostra_nova["itens"]), default=0)
    for k, (item, gold) in enumerate(_itens_catch(seed, arquivo_ref), 1):
        item["item"] = base_n + k
        delta.append(item)
        catch_gold[item["item"]] = gold
    bloco = amostra_nova["thresholds_congelados"]
    pre = {"gravado_em": datetime.now(tz=timezone.utc).isoformat(),
           "sha256_bloco_congelado": hashlib.sha256(json.dumps(
               bloco, sort_keys=True, ensure_ascii=False).encode())
           .hexdigest(),
           "delta_n2_ids": sorted(i["n2_id"] for i in delta
                                  if i["item"] not in catch_gold),
           "delta_itens": sorted(i["item"] for i in delta),
           "catch_gold_por_item_delta": catch_gold,
           "labels_reutilizados_por_n2_id": len(reuso_a),
           "razao": razao or "delta = grupos N2 novos/mudados; rótulos "
                             "anteriores valem por n2_id determinístico"}
    delta_amostra = {"pergunta": amostra_nova["pergunta"],
                     "thresholds_congelados": bloco, "itens": delta}
    return delta_amostra, reuso_a, reuso_b, pre


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
# RECALL (Codex #5/#20) — o estágio 0 mede precisão no que DISPAROU; isto
# mede o que os detectores PERDEM. Desenho anti-autoelogio: pool de
# candidatos RELAXADOS congelado e pré-registrado; controle de fundo;
# rotulagem cega; recall semeado por classe de forma; números POR FORMA,
# nunca agregados num escalar lisonjeiro.
# ---------------------------------------------------------------------------

# Fatores de relaxamento CONGELADOS (declarados no pré-registro; mudá-los
# invalida a medição)
RELAXAMENTO = {
    # v2.1: 20→40 mantém relaxado ⊇ congelado (o gatilho imperativo do
    # frozen aceita até 30 chars)
    "resposta-curta-seguida-de-acao": {
        "max_chars_voz": 40, "janela_s": 600,
        "classes": ("escrita", "commit", "execucao")},
    "pergunta-explicacao-resposta-curta": {
        "min_chars_explicacao": 1, "max_chars_resposta": 20,
        "janela_s": 3600},
    "leituras-repetidas-de-estado-externo": {
        "min_repeticoes": 2, "janela_s": 7200},
    "rajada-de-turnos-curtos": {
        "min_turnos": 2, "max_chars": 30, "janela_s": 1200},
}
RECALL_FUNDO_JANELA_S = 900.0
# REGRA DE PARADA do loop de re-rotulagem (correção da rodada de recall):
# no máximo UMA reapresentação por item, e só por defeito de PACOTE
# documentado ANTES de ver a direção dos rótulos; itens reapresentados
# reportam AS DUAS gerações de rótulo.
REAPRESENTACAO_MAX = 1
# classes semeadas fora do escopo POR CONSTRUÇÃO (o 0/3 delas é trivial)
SEEDED_FORA_DE_ESCOPO = {
    "resposta-curta-seguida-de-acao": {
        "frase-longa-de-aceite":
            "31-37 chars > teto RELAXADO de 20 — fora do escopo por "
            "construção; o 0/3 é trivialmente verdadeiro e não conta como "
            "medida de forma"}}


def pode_reapresentar(item_n, historico):
    """Guarda da regra de parada: True só se o item ainda não foi
    reapresentado (REAPRESENTACAO_MAX=1). O merge de rótulos DEVE consultar
    esta guarda antes de aceitar uma nova geração."""
    return historico.get(item_n, 0) < REAPRESENTACAO_MAX


def relaxamento_deltas():
    """Deltas por forma entre o congelado e o relaxado — visíveis ao lado
    de qualquer tabela de recall (o recall é relativo à definição
    AFROUXADA, não ao conceito nomeado)."""
    out = {}
    for forma, rel in RELAXAMENTO.items():
        base = THRESHOLDS[forma]
        out[forma] = {k: {"congelado": base.get(k), "relaxado": v}
                      for k, v in rel.items() if base.get(k) != v}
    return out
RECALL_FORMAS_FORA = {
    "sessoes-com-abertura-semelhante": "cross-sessão; o corpus da janela tem "
                                       "1 sessão de voz — pool vazio por "
                                       "construção",
    "entrega-com-perguntas-sem-turno-de-resposta-observado":
        "1 candidato possível por sessão (o fim dela) — censo trivial, sem "
        "pool relaxável",
    "resposta-longa-em-voz-propria-apos-explicacao":
        "forma nova (v2.1): estágio-0 nesta rodada; entra no harness de "
        "recall numa rodada futura",
    "pergunta-de-aprofundamento-apos-explicacao":
        "forma nova (v2.1): estágio-0 nesta rodada; recall em rodada futura",
    "retomada-de-entrega-com-vocabulario-da-entrega":
        "forma nova (v2.1): estágio-0 nesta rodada; recall em rodada futura"}


def _relaxados_da_sessao(sessao):
    """Candidatos RELAXADOS por forma (mecânicos, params de RELAXAMENTO).
    NUNCA tocam os detectores congelados — implementação paralela."""
    out = []
    vozes = sessao["vozes"]
    acoes = sorted((e for e in sessao["eventos"]
                    if e["kind"] != "voz-turno" and e["ts"] is not None
                    and not e["conteudo_redigido"].get("sidechain")),
                   key=lambda e: e["ts"])
    ats = sorted(sessao["assistant_turnos"], key=lambda a: a["ts"])
    brutas = sessao.get("cabecas_brutas") or {}

    def _rc(forma, instancias, params, de, ate):
        return {"id": _rid("rc", forma, *sorted(instancias)), "forma": forma,
                "instancias": sorted(instancias), "params": params,
                "janela": {"de": _iso(de), "ate": _iso(ate)},
                "session_id": sessao["session_id"]}

    p = RELAXAMENTO["resposta-curta-seguida-de-acao"]
    for ts, texto, vid, _l, _a in vozes:
        if 0 < len(texto) <= p["max_chars_voz"]:
            for ac in acoes:
                d = _parse_ts(ac["ts"]) - ts
                if 0 < d <= p["janela_s"] and (
                        ac["kind"] == "commit"
                        or ac["conteudo_redigido"].get("classe")
                        in p["classes"]):
                    out.append(_rc("resposta-curta-seguida-de-acao",
                                   [vid, ac["id"]],
                                   {"delta_s": round(d, 1),
                                    "chars_voz": len(texto)},
                                   ts, _parse_ts(ac["ts"])))
                    break

    p = RELAXAMENTO["pergunta-explicacao-resposta-curta"]
    for i, (ts, texto, vid, _l, _a) in enumerate(vozes):
        if not texto.rstrip().endswith("?"):
            continue
        for ts2, t2, vid2, _l2, _a2 in vozes[i + 1:]:
            if ts2 - ts > p["janela_s"]:
                break
            if 0 < len(t2) <= p["max_chars_resposta"] and any(
                    ts < a["ts"] < ts2
                    and a["chars"] >= p["min_chars_explicacao"]
                    for a in ats):
                out.append(_rc("pergunta-explicacao-resposta-curta",
                               [vid, vid2], {"delta_s": round(ts2 - ts, 1)},
                               ts, ts2))
                break

    p = RELAXAMENTO["leituras-repetidas-de-estado-externo"]
    por_cabeca = defaultdict(list)
    for ac in acoes:
        c = ac["conteudo_redigido"]
        if c.get("tool") == "Bash" and c.get("classe") == "leitura" \
                and c.get("comando_cabeca"):
            por_cabeca[brutas.get(ac["id"], c["comando_cabeca"])].append(ac)
    for cabeca, lst in por_cabeca.items():
        i = 0
        while i < len(lst):
            j = i
            while j + 1 < len(lst) and _parse_ts(lst[j + 1]["ts"]) - \
                    _parse_ts(lst[i]["ts"]) <= p["janela_s"]:
                j += 1
            if j - i + 1 >= p["min_repeticoes"]:
                grupo = lst[i:j + 1]
                out.append(_rc("leituras-repetidas-de-estado-externo",
                               [g["id"] for g in grupo],
                               {"n_repeticoes": len(grupo),
                                "comando_cabeca": redigir(
                                    cabeca, entropia=True)[:80]},
                               _parse_ts(grupo[0]["ts"]),
                               _parse_ts(grupo[-1]["ts"])))
            i = j + 1

    p = RELAXAMENTO["rajada-de-turnos-curtos"]
    curtos = [(ts, vid) for ts, t, vid, _l, _a in vozes
              if 0 < len(t) <= p["max_chars"]]
    i = 0
    while i < len(curtos):
        j = i
        while j + 1 < len(curtos) \
                and curtos[j + 1][0] - curtos[i][0] <= p["janela_s"]:
            j += 1
        if j - i + 1 >= p["min_turnos"]:
            out.append(_rc("rajada-de-turnos-curtos",
                           [v for _, v in curtos[i:j + 1]],
                           {"n_turnos": j - i + 1},
                           curtos[i][0], curtos[j][0]))
        i = j + 1
    return out


def recall_pool_fn(sessoes, reg):
    """Pool de FN-candidatos: relaxados NÃO detectados pelos congelados.
    'Detectado' = compartilha ≥1 instância N1 com um N2 congelado da MESMA
    forma (regra declarada no pré-registro)."""
    inst_por_forma = defaultdict(set)
    for n2 in reg.nivel(2):
        inst_por_forma[n2["forma"]].update(n2["instancias"])
    pool, relaxados = defaultdict(list), defaultdict(list)
    for s in sessoes:
        for rc in _relaxados_da_sessao(s):
            relaxados[rc["forma"]].append(rc)
            if not (set(rc["instancias"]) & inst_por_forma[rc["forma"]]):
                pool[rc["forma"]].append(rc)
    return pool, relaxados


def _eventos_da_janela(sessao, ini, fim):
    """EVENTOS main-chain estritamente dentro de [ini, fim) — o mesmo
    universo que os detectores veem (sidechain fora, declarado)."""
    out = []
    for e in sessao["eventos"]:
        if e["kind"] != "voz-turno" \
                and e["conteudo_redigido"].get("sidechain"):
            continue
        t = _parse_ts(e["ts"])
        if t is not None and ini <= t < fim:
            out.append(e)
    return sorted(out, key=lambda e: e["ts"])


def recall_janelas_de_fundo(sessoes, relaxados, k=10, seed=7):
    """K janelas aleatórias SEM candidato relaxado (esperado: 0 verdadeiros;
    um 'verdadeiro' aqui = o próprio pool é cego em algum lugar).

    Correção da rodada de recall: a seleção conta EVENTOS main-chain (o que
    o pacote carrega e os detectores veem), nunca linhas-com-ts do
    transcript — o descompasso gerou janelas 'com 51 eventos' e pacote
    vazio."""
    import random
    rnd = random.Random(f"fundo-{seed}")
    intervalos = [(_parse_ts(rc["janela"]["de"]),
                   _parse_ts(rc["janela"]["ate"]))
                  for lst in relaxados.values() for rc in lst]
    janelas = []
    for s in sessoes:
        ts = s["ts_todos"]
        if not ts or ts[-1] - ts[0] < RECALL_FUNDO_JANELA_S:
            continue
        tentativas = 0
        while len(janelas) < k and tentativas < 600:
            tentativas += 1
            ini = rnd.uniform(ts[0], ts[-1] - RECALL_FUNDO_JANELA_S)
            fim = ini + RECALL_FUNDO_JANELA_S
            evs = _eventos_da_janela(s, ini, fim)
            if len(evs) < 3:
                continue
            if any(a is not None and b is not None
                   and a < fim and b > ini for a, b in intervalos):
                continue
            janelas.append({"session_id": s["session_id"],
                            "arquivo": s["arquivo"],
                            "ts_ini": _iso(ini), "ts_fim": _iso(fim),
                            "n_eventos": len(evs)})
    return janelas[:k]


def wilson(sucessos, n, z=1.96):
    """Intervalo de Wilson para proporção (dig-1 C: reportar IC, não só o
    ponto)."""
    if n == 0:
        return None, None
    p = sucessos / n
    denom = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / denom
    meio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centro - meio), min(1.0, centro + meio)


# --- semeadura de formas (Codex FN shapes) --------------------------------

def _linhas_semente(seed_base, t0):
    """Instâncias positivas sintéticas por forma × classe-de-superfície.
    Retorna (linhas_jsonl, manifesto {forma: {classe: [[uuids da instância]]}}).
    Eventos bem-formados, timestamps após t0, grupos espaçados 3600s (nunca
    colidem entre si nem com o corpus real)."""
    import random
    rnd = random.Random(f"semente-{seed_base}")
    linhas, manifesto = [], defaultdict(lambda: defaultdict(list))
    rel = [0]

    def _uid():
        return (f"{rnd.getrandbits(32):08x}-{rnd.getrandbits(16):04x}"
                f"-4{rnd.getrandbits(12):03x}-8{rnd.getrandbits(12):03x}"
                f"-{rnd.getrandbits(48):012x}")

    def _iso_rel(s):
        return _iso(t0 + s).replace("+00:00", "+00:00")

    def _user(s, texto):
        u = _uid()
        linhas.append(json.dumps({
            "type": "user", "uuid": u, "timestamp": _iso_rel(s),
            "cwd": "/home/seed/proj", "isSidechain": False,
            "origin": {"kind": "human"},
            "message": {"role": "user", "content": texto}},
            ensure_ascii=False))
        return u

    def _assist(s, texto):
        u = _uid()
        linhas.append(json.dumps({
            "type": "assistant", "uuid": u, "timestamp": _iso_rel(s),
            "cwd": "/home/seed/proj", "isSidechain": False,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": texto}]}},
            ensure_ascii=False))
        return u

    def _tool(s, nome, inp):
        u = _uid()
        linhas.append(json.dumps({
            "type": "assistant", "uuid": u, "timestamp": _iso_rel(s),
            "cwd": "/home/seed/proj", "isSidechain": False,
            "message": {"role": "assistant",
                        "content": [{"type": "tool_use", "id": f"t-{u[:8]}",
                                     "name": nome, "input": inp}]}},
            ensure_ascii=False))
        return u

    def _bloco():
        # espaçamento > janela relaxada: instâncias semeadas NUNCA se
        # encadeiam entre si (isolamento da medição)
        rel[0] += 7200
        return rel[0]

    # D1 — resposta-curta-seguida-de-acao
    d1 = {
        "in-spec": [("ok", 15), ("sim", 20), ("vai", 30)],
        "aceite-7-15-chars": [("blz manda", 15), ("pode mandar", 20),
                              ("perfeito", 30)],
        "atraso-121-600s": [("ok", 180), ("sim", 300), ("vai", 480)],
        "frase-longa-de-aceite": [
            ("pode mandar ver, ta otimo assim", 15),
            ("perfeito, segue exatamente esse plano", 20),
            ("show, aplica essa versao que fechou", 30)],
    }
    for classe, casos in d1.items():
        for texto, atraso in casos:
            b = _bloco()
            u1 = _user(b, texto)
            u2 = _tool(b + atraso, "Write",
                       {"file_path": "/home/seed/proj/out.md",
                        "content": "x"})
            manifesto["resposta-curta-seguida-de-acao"][classe].append(
                [u1, u2])

    # D2 — pergunta-explicacao-resposta-curta
    d2 = {
        "in-spec": [("ok", 900, 60)],
        "resposta-7-20-chars": [("blz perfeito", 900, 60)],
        "janela-longa": [("ok", 900, 2500)],
        "explicacao-curta": [("ok", 300, 60)],
    }
    for classe, casos in d2.items():
        for texto, chars_expl, atraso_resp in casos * 3:
            b = _bloco()
            u1 = _user(b, "como funciona o mecanismo desse teste aqui?")
            _assist(b + 20, "Explicação:\n" + "e" * chars_expl)
            u3 = _user(b + 20 + atraso_resp, texto)
            manifesto["pergunta-explicacao-resposta-curta"][classe].append(
                [u1, u3])

    # D3 — leituras-repetidas-de-estado-externo. A cabeça (2 primeiros
    # tokens) é ÚNICA por grupo (alvo no 2º token) — grupos semeados nunca
    # se fundem entre si nem com o corpus real
    seq = [0]

    def _alvo():
        seq[0] += 1
        return f"/tmp/seed_{seq[0]:03d}.log"

    d3 = {
        "in-spec": lambda a: [(f"cat {a}",) * 3 + (600,)],
        "cabecas-variadas": lambda a: [(f"cat {a}", f"head {a}",
                                        f"tail {a}", 600)],
        "janela-2x": lambda a: [(f"cat {a}",) * 3 + (2700,)],
        "duas-repeticoes": lambda a: [(f"cat {a}", f"cat {a}", None, 600)],
    }
    for classe, fabrica in d3.items():
        for _rep in range(3):
            c1, c2, c3, gap = fabrica(_alvo())[0]
            b = _bloco()
            us = [_tool(b, "Bash", {"command": c1}),
                  _tool(b + gap, "Bash", {"command": c2})]
            if c3:
                us.append(_tool(b + 2 * gap, "Bash", {"command": c3}))
            manifesto["leituras-repetidas-de-estado-externo"][classe].append(
                us)

    # D6 — rajada-de-turnos-curtos
    d6 = {
        "in-spec": [(["ok", "sim", "vai"], 60)],
        "turnos-16-30-chars": [(["bora fechar essa parte ja",
                                 "manda a proxima etapa agora",
                                 "isso ai, segue o fluxo"], 60)],
        "janela-1200": [(["ok", "sim", "vai"], 450)],
        "rajada-de-2": [(["ok", "sim"], 60)],
    }
    for classe, casos in d6.items():
        for textos, gap in casos * 3:
            b = _bloco()
            us = [_user(b + k * gap, t) for k, t in enumerate(textos)]
            manifesto["rajada-de-turnos-curtos"][classe].append(us)

    return linhas, {f: dict(c) for f, c in manifesto.items()}


def recall_seeded(workdir_semeado, manifesto, host="seed"):
    """Roda os detectores CONGELADOS na cópia semeada e mede
    detected/M por forma × classe (casa por uuid das instâncias)."""
    reg, _proj = pipeline(workdir_semeado, host)
    uuids_detectados = defaultdict(set)
    for n2 in reg.nivel(2):
        for iid in n2["instancias"]:
            u = reg.by_id[iid]["evidencia"].get("uuid")
            if u:
                uuids_detectados[n2["forma"]].add(u)
    tabela = {}
    for forma, classes in manifesto.items():
        tabela[forma] = {}
        for classe, instancias in classes.items():
            det = sum(1 for inst in instancias
                      if set(inst) & uuids_detectados[forma])
            cel = {"m": len(instancias), "detectadas": det,
                   "seeded_recall": round(det / len(instancias), 3)
                   if instancias else None}
            fora = SEEDED_FORA_DE_ESCOPO.get(forma, {}).get(classe)
            if fora:
                cel["fora_do_escopo_por_construcao"] = fora
            tabela[forma][classe] = cel
    return tabela


PERGUNTA_FUNDO = ("Nesta janela de eventos, ocorre DE FATO alguma das "
                  "sequências descritas no campo 'formas_possiveis'? "
                  "Responda exatamente o nome da forma que ocorre, ou "
                  "'nenhuma'.")


def eval_recall_preparar(sessoes, reg_estado, workdir, tp_por_forma,
                         max_por_forma=25, k_fundo=10, seed=11):
    """Monta o pacote de recall: FN-candidatos amostrados + janelas de fundo
    + 2 catch frescos. Retorna (pre_registro, amostra) — o CHAMADOR grava o
    pré-registro ANTES da amostra (cadeia de mtime auditável); nada de campo
    pós-rótulo no recibo (resultado de catch vai em arquivo separado)."""
    import random
    rnd = random.Random(f"recall-{seed}")
    pool, relaxados = recall_pool_fn(sessoes, reg_estado)
    n1_por_id = {e["id"]: e for s in sessoes for e in s["eventos"]}
    itens = []

    def _carga_de_instancia(iid):
        n1 = n1_por_id.get(iid) or reg_estado.by_id.get(iid)
        ev = n1["evidencia"]
        return {"ancora": {"arquivo": ev["arquivo_jsonl"],
                           "linha": ev["linha"], "kind": n1["kind"],
                           "uuid": ev.get("uuid")},
                "carga": _carga_util(workdir, ev["arquivo_jsonl"],
                                     ev["linha"])}

    amostra_ids = {}
    for forma in sorted(pool):
        cands = sorted(pool[forma], key=lambda c: c["id"])
        rnd.shuffle(cands)
        escolhidos = cands[:max_por_forma]
        amostra_ids[forma] = [c["id"] for c in escolhidos]
        sess_por_id = {s["session_id"]: s for s in sessoes}
        for c in escolhidos:
            evid = [_carga_de_instancia(i) for i in c["instancias"][:6]]
            # perna do assistant JULGADA entra no pacote — para QUALQUER
            # forma cujos params ancoram uma linha de assistant (defeito
    # de pacote das rodadas de recall/v2.1: sem ela, EI em massa)
            linha_assist = (c.get("params", {}).get("assistant_linha")
                            or c.get("params", {}).get("entrega_linha"))
            s = sess_por_id.get(c["session_id"])
            if s and not linha_assist \
                    and c["forma"] == "pergunta-explicacao-resposta-curta":
                de = _parse_ts(c["janela"]["de"])
                ate = _parse_ts(c["janela"]["ate"])
                entre = [a for a in s["assistant_turnos"]
                         if de < a["ts"] < ate]
                if entre:
                    linha_assist = max(entre,
                                       key=lambda a: a["chars"])["linha"]
            if s and linha_assist:
                evid.append({
                    "ancora": {"arquivo": s["arquivo"],
                               "linha": linha_assist,
                               "kind": "assistant-perna"},
                    "carga": _carga_util(workdir, s["arquivo"],
                                         linha_assist)})
            itens.append({
                "n2_id": c["id"], "forma": c["forma"],
                "descricao_mecanica": _descricao_relaxada(c),
                "pergunta": PERGUNTA_MECANICA,
                "evidencia": evid})
    # catch frescos (2), indistinguíveis dos itens de FN
    catch_gold = {}
    arquivos_reais = Counter(e["ancora"].get("arquivo") for i in itens
                             for e in i["evidencia"]
                             if e.get("ancora", {}).get("arquivo"))
    arq_ref = (arquivos_reais.most_common(1)[0][0] if arquivos_reais
               else None)
    for item, gold in _itens_catch(f"recall-{seed}", arq_ref):
        pos = rnd.randrange(len(itens) + 1) if itens else 0
        itens.insert(pos, item)
        catch_gold[item["n2_id"]] = gold
    for n, item in enumerate(itens, 1):
        item["item"] = n
    # janelas de fundo (pergunta própria, depois dos itens)
    fundo = recall_janelas_de_fundo(sessoes, relaxados, k=k_fundo, seed=seed)
    formas_possiveis = {f: _DESCRICOES_MECANICAS[f](
        dict(THRESHOLDS[f], **RELAXAMENTO[f])) for f in RELAXAMENTO}
    base_n = len(itens)
    itens_fundo = []
    for k, j in enumerate(fundo, 1):
        s = next(x for x in sessoes if x["session_id"] == j["session_id"])
        ini, fim = _parse_ts(j["ts_ini"]), _parse_ts(j["ts_fim"])
        evs = _eventos_da_janela(s, ini, fim)[:30]
        evid = []
        for e in evs:
            # GARANTIA dura: evidência estritamente dentro da janela
            # declarada (o defeito da 1ª rodada anulou o controle)
            t = _parse_ts(e["ts"])
            if not (ini <= t < fim):
                raise CitacaoInvalida(
                    f"evidência fora da janela de fundo: {e['id']}")
            evid.append(_carga_de_instancia(e["id"]))
        itens_fundo.append({
            "item": base_n + k, "tipo": "janela-de-fundo",
            "pergunta": PERGUNTA_FUNDO,
            "formas_possiveis": formas_possiveis,
            "janela": {"de": j["ts_ini"], "ate": j["ts_fim"]},
            "nota": ("janela vazia (0 eventos main-chain)" if not evid
                     else None),
            "evidencia": evid})
    bloco = {"thresholds_congelados": THRESHOLDS,
             "relaxamento": RELAXAMENTO,
             "detector_version": DETECTOR_VERSION,
             "regra_de_deteccao": "candidato relaxado conta como detectado "
                                  "se compartilha ≥1 instância N1 com um N2 "
                                  "congelado da mesma forma",
             "formas_fora": RECALL_FORMAS_FORA}
    pre = {"gravado_em": datetime.now(tz=timezone.utc).isoformat(),
           "sha256_bloco_congelado": hashlib.sha256(json.dumps(
               bloco, sort_keys=True, ensure_ascii=False).encode())
           .hexdigest(),
           "bloco": bloco,
           "pool_por_forma": {f: len(pool[f]) for f in sorted(pool)},
           "relaxados_por_forma": {f: len(relaxados[f])
                                   for f in sorted(relaxados)},
           "tp_por_forma": tp_por_forma,
           "amostra_ids": amostra_ids,
           "catch_gold_por_item": {i["item"]: catch_gold[i["n2_id"]]
                                   for i in itens
                                   if i["n2_id"] in catch_gold},
           "janelas_de_fundo": fundo,
           "seed": seed}
    amostra = {"pergunta": PERGUNTA_MECANICA,
               "thresholds_congelados": bloco,
               "itens": itens + itens_fundo}
    return pre, amostra


def _descricao_relaxada(c):
    p = dict(THRESHOLDS[c["forma"]], **RELAXAMENTO[c["forma"]])
    d = _DESCRICOES_MECANICAS[c["forma"]](p)
    if c["forma"] == "resposta-curta-seguida-de-acao":
        # o template congelado diz "escrita/commit"; o RELAXADO aceita
        # também execução — dizer explicitamente (defeito da 1ª rodada:
        # a ambiguidade gerou desacordo entre rotuladores)
        d += ("; NESTE CANDIDATO RELAXADO a ação vale se for de classe "
              "escrita, commit OU execução")
    return (d + f" (candidato RELAXADO; observado: "
                f"{json.dumps(c['params'], ensure_ascii=False)})")


def eval_recall_ingerir(amostra, labels_a, labels_b, pre, seeded=None,
                        reapresentados=None):
    """Números por forma — NUNCA agregados num escalar único.

    recall_est = TP / (TP + p̂·pool); IC por Wilson em p̂ propagado
    (recall_lo usa p_hi; recall_hi usa p_lo). Premissas declaradas no
    resultado. Resultado de catch vai SEPARADO (nunca no pré-registro)."""
    la = {l["item"]: str(l["resposta"]).strip().lower()
          for l in labels_a["labels"]}
    lb = {l["item"]: str(l["resposta"]).strip().lower()
          for l in labels_b["labels"]}
    catch_itens = {int(k) for k in pre["catch_gold_por_item"]}
    fundo_itens = {i["item"] for i in amostra["itens"]
                   if i.get("tipo") == "janela-de-fundo"}
    por_forma = defaultdict(lambda: {"amostrados": 0, "sim": 0, "nao": 0,
                                     "insuficiente": 0, "sem_consenso": 0})
    for i in amostra["itens"]:
        if i["item"] in catch_itens or i["item"] in fundo_itens:
            continue
        f = por_forma[i["forma"]]
        f["amostrados"] += 1
        a, b = _normalizar_rotulo(la.get(i["item"])), \
            _normalizar_rotulo(lb.get(i["item"]))
        if a is None or b is None or a != b:
            f["sem_consenso"] += 1
        elif a == "sim":
            f["sim"] += 1
        elif a == "nao":
            f["nao"] += 1
        else:
            f["insuficiente"] += 1
    resultado = {}
    for forma in sorted(set(list(por_forma) + list(pre["pool_por_forma"]))):
        f = por_forma.get(forma, {"amostrados": 0, "sim": 0, "nao": 0,
                                  "insuficiente": 0, "sem_consenso": 0})
        pool = pre["pool_por_forma"].get(forma, 0)
        tp = pre["tp_por_forma"].get(forma, 0)
        denom = f["sim"] + f["nao"]
        p_hat = (f["sim"] / denom) if denom else None
        p_lo, p_hi = wilson(f["sim"], denom) if denom else (None, None)
        est_fn = round(p_hat * pool, 1) if p_hat is not None else None
        rec = (round(tp / (tp + p_hat * pool), 3)
               if p_hat is not None and (tp + p_hat * pool) > 0 else None)
        rec_lo = (round(tp / (tp + p_hi * pool), 3)
                  if p_hi is not None and (tp + p_hi * pool) > 0 else None)
        rec_hi = (round(tp / (tp + p_lo * pool), 3)
                  if p_lo is not None and (tp + p_lo * pool) > 0 else None)
        # UNIDADE CONSISTENTE (correção): tudo no espaço de candidatos
        # relaxados — detectados-relaxados / (detectados-relaxados + p̂·pool)
        relax_total = pre.get("relaxados_por_forma", {}).get(forma, pool)
        det_rel = relax_total - pool
        rec_c = (round(det_rel / (det_rel + p_hat * pool), 3)
                 if p_hat is not None and (det_rel + p_hat * pool) > 0
                 else (None if p_hat is not None else None))
        rec_c_lo = (round(det_rel / (det_rel + p_hi * pool), 3)
                    if p_hi is not None and (det_rel + p_hi * pool) > 0
                    else None)
        rec_c_hi = (round(det_rel / (det_rel + p_lo * pool), 3)
                    if p_lo is not None and (det_rel + p_lo * pool) > 0
                    else None)
        resultado[forma] = dict(
            f, pool_fn=pool, tp_detectados=tp,
            candidatos_relaxados=relax_total,
            detectados_relaxados=det_rel,
            p_fn_amostrado=round(p_hat, 3) if p_hat is not None else None,
            p_wilson=[round(p_lo, 3), round(p_hi, 3)]
            if p_lo is not None else None,
            fn_estimados=est_fn,
            recall_espaco_relaxado=rec_c,
            recall_espaco_relaxado_intervalo=(
                [rec_c_lo, rec_c_hi] if rec_c_lo is not None else None),
            recall_unidade_mista=rec,
            recall_unidade_mista_intervalo=(
                [rec_lo, rec_hi] if rec_lo is not None else None),
            nota_unidades="recall_espaco_relaxado é o número CONSISTENTE "
                          "(numerador e denominador no espaço de candidatos "
                          "relaxados); recall_unidade_mista foi o publicado "
                          "na 1ª versão (TP em N2 congelados ÷ espaço "
                          "relaxado) e fica só para rastreabilidade")
    # fundo: esperado 'nenhuma' unânime
    fundo_res = {"n": len(fundo_itens), "nenhuma_unanime": 0,
                 "achados": [], "sem_consenso": 0}
    for i in amostra["itens"]:
        if i["item"] not in fundo_itens:
            continue
        a = (la.get(i["item"]) or "").strip().lower()
        b = (lb.get(i["item"]) or "").strip().lower()
        if a == b == "nenhuma":
            fundo_res["nenhuma_unanime"] += 1
        elif a == b:
            fundo_res["achados"].append({"item": i["item"], "forma": a,
                                         "janela": i["janela"]})
        else:
            fundo_res["sem_consenso"] += 1
    catch_res = {"a": 0, "b": 0, "n": len(catch_itens)}
    for item_n in catch_itens:
        gold = pre["catch_gold_por_item"][str(item_n)] \
            if str(item_n) in pre["catch_gold_por_item"] \
            else pre["catch_gold_por_item"][item_n]
        if _normalizar_rotulo(la.get(item_n)) == gold:
            catch_res["a"] += 1
        if _normalizar_rotulo(lb.get(item_n)) == gold:
            catch_res["b"] += 1
    recall = {
        "pre_registro_sha256": pre["sha256_bloco_congelado"],
        "relaxamento_deltas": relaxamento_deltas(),
        "leitura": {
            "caveat_central": "o recall é relativo à definição "
                              "DELIBERADAMENTE afrouxada (deltas acima), "
                              "não ao conceito nomeado do detector",
            "resposta-curta-seguida-de-acao":
                "SINAL MAIS FORTE: os FN são perdas genuínas do teto de 6 "
                "chars e da exclusão de execução (ex.: 'dispare o 1'→24s→"
                "python3)",
            "pergunta-explicacao-resposta-curta":
                "mede o CONCEITO RELAXADO: min_chars_explicacao 800→1 "
                "apaga a 'explicação longa' — não leia como recall da forma "
                "nomeada",
            "rajada-de-turnos-curtos":
                "mede o CONCEITO RELAXADO: readmite turnos interrogativos "
                "que o finding R1#16 removeu DE PROPÓSITO",
            "leituras-repetidas-de-estado-externo":
                "boa parte do pool relaxado é 'mesma cabeça 2× em 2h' — "
                "conceito bem mais fraco que o congelado"},
        "regra_de_parada": {
            "reapresentacao_max": REAPRESENTACAO_MAX,
            "regra": "no máximo UMA reapresentação por item, só por defeito "
                     "de PACOTE documentado antes de ver a direção dos "
                     "rótulos; itens reapresentados reportam as duas "
                     "gerações"},
        "premissas": [
            "TP por forma = N2 congelados da forma (precisão 1.0 no "
            "estágio 0 desta janela; TP efetivo = n2 × precisão)",
            "p̂ estimado só em consenso unânime; EI e desacordo ficam fora "
            "do denominador e são reportados",
            "extrapolação linear p̂×pool assume amostra representativa do "
            "pool (amostragem uniforme seeded)",
            "IC de Wilson em p̂ propagado para o recall; sem correção de "
            "população finita (conservador)"],
        "por_forma": resultado,
        "fundo": fundo_res,
        "reapresentados": reapresentados,
        "seeded": seeded,
        "formas_fora": RECALL_FORMAS_FORA,
        "rotuladores": [labels_a.get("rotulador", "a"),
                        labels_b.get("rotulador", "b")],
        "avaliado_em": datetime.now(tz=timezone.utc).isoformat()}
    return recall, catch_res


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

def _carregar_referencia_n2(caminho):
    """{n2_id: forma} de uma referência antiga — atividades.jsonl (registros
    nivel 2) ou arquivo de amostra do eval (itens com n2_id/forma)."""
    ref = {}
    p = Path(caminho)
    if p.suffix == ".jsonl":
        for linha in open(p, encoding="utf-8"):
            try:
                r = json.loads(linha)
            except Exception:
                continue
            if r.get("nivel") == 2:
                ref[r["id"]] = r["forma"]
    else:
        dados = json.loads(p.read_text())
        for i in dados.get("itens", []):
            ref[i["n2_id"]] = i["forma"]
    return ref


def _scan_corpus(workdir, host):
    """Varre a cópia de trabalho → (sessoes com subagentes fundidos, puladas).
    Compartilhado entre pipeline e eval-recall (mesmos ids N1)."""
    workdir = Path(workdir)
    arquivos = sorted(str(p) for p in workdir.rglob("*.jsonl"))
    principais = [a for a in arquivos if "/subagents/" not in a]
    sub = [a for a in arquivos if "/subagents/" in a]
    sessoes, puladas = [], []
    for a in principais:
        rel = os.path.relpath(a, workdir)
        # R6.1 Front C: agent-*.jsonl no topo do projeto é transcript de
        # SUBAGENTE DELEGADO — os turnos "user" são prompts do agente-mãe,
        # não voz do operador; sem vínculo mecânico com a sessão-mãe, fica
        # fora da admissão (razão logada; ações não são contáveis sem o
        # trilho sidechain do pai)
        if os.path.basename(a).startswith("agent-"):
            puladas.append({"arquivo": rel,
                            "razao": "transcript de subagente delegado "
                                     "(agent-*.jsonl fora de subagents/): "
                                     "turnos 'user' são prompts do "
                                     "agente-mãe, não voz do operador"})
            continue
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
    return sessoes, puladas


def pipeline(workdir, host, complete_fn=None, janela_dias=7, agora_ts=None,
             model="injetado", eval_estagio0=None, diff_referencia=None):
    """Cópia de trabalho (já redigida) → registry + projeção completa.

    `eval_estagio0` (resultado de eval_ingerir): GATE dos N3/N4 (finding R1
    #2) — sem ele, NENHUM N3/N4 é gerado (degradação declarada); com ele, só
    formas `confiavel` sobem."""
    reg = Registry()
    orc = OrcamentoLLM()
    sessoes, puladas = _scan_corpus(workdir, host)

    for s in sessoes:
        for ev in s["eventos"]:
            reg.add(ev)

    # R5: segmentar ANTES de tudo; R5.2: clusterizar ANTES da detecção (a
    # contagem de padrões precisa dos spans de comportamento contíguo)
    todos_trechos, seg_recibos = [], []
    for s in sessoes:
        trechos, cortes = segmentar(s, complete_fn, orc, model=model)
        s["trechos"] = trechos
        todos_trechos.extend(trechos)
        soma_s = sum(t["segundos_ativos_atribuidos"][int(MIN_ATIVOS_CAP_S)]
                     for t in trechos)
        sessao_s = tempo_ativo_s(s["ts_todos"], MIN_ATIVOS_CAP_S)
        seg_recibos.append({
            "session_id": s["session_id"], "arquivo": s["arquivo"],
            "n_trechos": len(trechos),
            "cortes": cortes,
            "arbitragens": s.get("arbitragens") or [],
            "conservacao_s": {"soma_trechos": round(soma_s, 3),
                              "sessao": round(sessao_s, 3),
                              "delta": round(soma_s - sessao_s, 6)}})

    # R5.2 finding 4: clusterizar ANTES da detecção
    atividades, cluster_log = clusterizar(todos_trechos, complete_fn, orc)
    # R5.2 finding 5: piso de Atividade — sub-piso dobra no vizinho
    atividades = _aplicar_piso(atividades, todos_trechos, cluster_log)
    # spans de COMPORTAMENTO contíguo: trechos adjacentes da mesma Atividade
    # formam um span; D3/D6 agrupam por span (corte dentro da mesma
    # Atividade não parte o comportamento — finding 4)
    atv_por_trecho = {tid: atv["ulid"] for atv in atividades
                      for tid in atv.get("trecho_ids", [])}
    for s in sessoes:
        spans, span_idx, atv_ant = {}, 0, None
        for tr in sorted(s.get("trechos") or [],
                         key=lambda t: t["span"]["ts_start"] or ""):
            a = atv_por_trecho.get(tr["trecho_id"])
            if a != atv_ant:
                span_idx += 1
                atv_ant = a
            spans[tr["trecho_id"]] = f"{a or 'sem-atv'}#{span_idx}"
        s["spans_por_trecho"] = spans

    n2s = []
    for s in sessoes:
        n2s.extend(detectar_sessao(s, reg))
    n2s.extend(detectar_cross_sessao(sessoes, reg))
    # R5: N2 ganha refs de trecho + DONO ÚNICO (finding 3: o trecho da 1ª
    # instância; âncoras N1 intactas; ids N2 idem)
    spans_por_sessao = {s["session_id"]: s for s in sessoes}
    for n2 in reg.nivel(2):
        trs, dono = [], None
        for iid in n2["instancias"]:
            n1 = reg.by_id[iid]
            s = spans_por_sessao.get(n1["session_id"])
            if s:
                tid = _trecho_de(s, _parse_ts(n1["ts"]))
                if tid:
                    trs.append(tid)
                    if dono is None:
                        dono = tid
        n2["trechos"] = sorted(set(trs))
        n2["trecho_dono"] = dono

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

    # R5.2 finding 4: recibo de diff do n dos padrões contra uma referência
    padroes_diff = None
    if diff_referencia:
        ref = _carregar_referencia_n2(diff_referencia)
        novos = {n2["id"]: n2["forma"] for n2 in reg.nivel(2)}
        padroes_diff = {
            "referencia": os.path.basename(str(diff_referencia)),
            "nota": "ids N2 = hash das instâncias; 'dissolvido' significa "
                    "que o CONJUNTO de instâncias daquele grupo mudou "
                    "(re-derivação por corte/comportamento contíguo), nunca "
                    "que o comportamento sumiu do corpus",
            "por_forma": []}
        for f in sorted(set(ref.values()) | set(novos.values())):
            antes = {i for i, fo in ref.items() if fo == f}
            depois = {i for i, fo in novos.items() if fo == f}
            padroes_diff["por_forma"].append({
                "forma": f, "n_antes": len(antes), "n_depois": len(depois),
                "mantidos": len(antes & depois),
                "dissolvidos": len(antes - depois),
                "novos": len(depois - antes)})

    agora_ts = agora_ts or datetime.now(tz=timezone.utc).timestamp()
    ts_all = [t for s in sessoes for t in s["ts_todos"]]
    janela = {"de": _iso(min(ts_all)) if ts_all else None,
              "ate": _iso(max(ts_all)) if ts_all else None,
              "criterio": f"mtime nos últimos {janela_dias} dias"}
    cobertura = montar_cobertura([host], len(sessoes), puladas, janela)
    padroes, formas_sem_instancias = fold_padroes(reg, agora_ts, cobertura)

    # índice N2 → atividade pelo TRECHO-DONO (R5.2 finding 3: dono único —
    # Σ n2_ids das Atividades == N2 distintos); fallback por sessão só para
    # N2 sem dono
    n2_por_trecho = defaultdict(list)
    n2_por_sessao = defaultdict(list)
    for n2 in reg.nivel(2):
        if n2.get("trecho_dono"):
            n2_por_trecho[n2["trecho_dono"]].append(n2["id"])
        else:
            for sid in n2["sessoes"][:1]:
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
        "padroes_diff": padroes_diff,
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


def render_report(reg, projecao, eval_estagio0=None, recall=None):
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
             f"<code>{_esc(projecao.get('detector_version', DETECTOR_VERSION))}"
             f"</code> · clustering "
             f"<code>{_esc(CLUSTER_VERSION)}</code></p>")
    if str(projecao.get("detector_version",
                        DETECTOR_VERSION)).endswith("-proposta"):
        H.append("<p class='aviso'>Thresholds v2.1 são PROPOSTA guiada pela "
                 "medição de recall — aguardam ratificação do operador; a "
                 "racional de cada mudança está no código e no PR.</p>")

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
                    f"</span> ({_esc(str(c.get('detalhe', ''))[:80])})"
                    + (f" [{_esc(c['movido'])}]" if c.get("movido") else "")
                    + "</li>"
                    for c in r["cortes"]) + "</ul>")
            if r.get("arbitragens"):
                H.append("<ul>" + "".join(
                    f"<li class='exp'>arbitragem LLM em L{a['linha']} "
                    f"({_esc(a['de'])}→{_esc(a['para'])}, {a['n_eventos']} "
                    f"eventos): resposta \"{_esc(a['resposta'][:40])}\" · "
                    f"model {_esc(str(a['model'])[:40])} · prompt sha256 "
                    f"<code>{_esc(a['prompt_sha256'][:12])}…</code></li>"
                    for a in r["arbitragens"]) + "</ul>")
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
        if atv.get("merges"):
            H.append("<p>Cadeia de merge (evidência): "
                     + " · ".join(_esc(m["razao"])[:90]
                                  for m in atv["merges"][:6]) + "</p>")
        seg_tot = atv.get("segundos_ativos_total")
        if seg_tot is not None:
            H.append(f"<p>Tempo ativo total: {seg_tot:.1f}s "
                     f"({seg_tot / 60:.1f} min — exato em segundos; os "
                     f"minutos por trecho abaixo são arredondados a 0.1)</p>")
        H.append("<table><tr><th>sessão</th><th>trecho</th><th>cwd do "
                 "trecho</th><th>início</th>"
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
            if t.get("digressao_de"):
                tr_lbl += " [digressão dobrada]"
            H.append(
                f"<tr><td><code>{_esc(t['session_id'][:8])}</code></td>"
                f"<td><code>{_esc(tr_lbl)}</code></td>"
                f"<td><code>{_esc(t.get('cwd', '—'))}</code></td>"
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
    pd_diff = projecao.get("padroes_diff")
    if pd_diff:
        H.append(f"<p>Recibo de diff do n (vs {_esc(pd_diff['referencia'])})"
                 f": {_esc(pd_diff['nota'])}</p>")
        H.append("<table><tr><th>forma</th><th>n antes</th><th>n depois</th>"
                 "<th>mantidos</th><th>dissolvidos</th><th>novos</th></tr>")
        for d in pd_diff["por_forma"]:
            H.append(f"<tr><td>{_esc(d['forma'])}</td><td>{d['n_antes']}</td>"
                     f"<td>{d['n_depois']}</td><td>{d['mantidos']}</td>"
                     f"<td>{d['dissolvidos']}</td><td>{d['novos']}</td></tr>")
        H.append("</table>")

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

    # Recall (Codex #5/#20) — por forma, nunca agregado num escalar
    if recall:
        H.append("<h2>Recall — o que os detectores PERDEM</h2>")
        H.append(f"<p>Pool de FN-candidatos por relaxamento congelado "
                 f"(pré-registro <code>"
                 f"{_esc(recall['pre_registro_sha256'][:16])}…</code>); "
                 f"rotulagem cega dupla; números POR FORMA — sem agregação "
                 f"lisonjeira.</p>")
        H.append("<p class='aviso'>CAVEAT CENTRAL: o recall abaixo é "
                 "relativo à definição DELIBERADAMENTE afrouxada — os "
                 "deltas por forma estão na tabela; não leia como recall do "
                 "conceito nomeado.</p>")
        H.append("<table><tr><th>forma</th><th>detect. relax.</th>"
                 "<th>pool FN</th><th>amostrados</th><th>p̂ FN</th>"
                 "<th><b>recall (espaço relaxado)</b></th><th>IC</th>"
                 "<th>1ª versão (unidade mista)</th>"
                 "<th>deltas do relaxamento</th><th>leitura</th></tr>")
        deltas = recall.get("relaxamento_deltas") or {}
        leitura = recall.get("leitura") or {}
        for forma, v in sorted(recall["por_forma"].items()):
            ic = v.get("recall_espaco_relaxado_intervalo")
            ictxt = f"{ic[0]}–{ic[1]}" if ic else "—"
            dl = "; ".join(
                f"{k} {d['congelado']}→{d['relaxado']}"
                for k, d in (deltas.get(forma) or {}).items())
            H.append(
                f"<tr><td>{_esc(forma)}</td>"
                f"<td>{v.get('detectados_relaxados', '—')}/"
                f"{v.get('candidatos_relaxados', '—')}</td>"
                f"<td>{v['pool_fn']}</td><td>{v['amostrados']}</td>"
                f"<td>{v['p_fn_amostrado'] if v['p_fn_amostrado'] is not None else '—'}</td>"
                f"<td><b>{v.get('recall_espaco_relaxado') if v.get('recall_espaco_relaxado') is not None else '—'}</b></td>"
                f"<td>{_esc(ictxt)}</td>"
                f"<td class='exp'>{v.get('recall_unidade_mista') if v.get('recall_unidade_mista') is not None else '—'}</td>"
                f"<td>{_esc(dl)}</td>"
                f"<td class='exp'>{_esc(leitura.get(forma, ''))[:180]}</td>"
                f"</tr>")
        H.append("</table>")
        rp = recall.get("regra_de_parada")
        if rp:
            H.append(f"<p class='exp'>Regra de parada da re-rotulagem: "
                     f"{_esc(rp['regra'])}.</p>")
        if recall.get("reapresentados"):
            H.append(f"<p class='exp'>Itens reapresentados (defeito de "
                     f"pacote documentado): "
                     f"{len(recall['reapresentados'].get('itens', []))} — "
                     f"as duas gerações de rótulo estão em recall.json.</p>")
        fu = recall.get("fundo") or {}
        H.append(f"<p>Controle de fundo: {fu.get('nenhuma_unanime', 0)}/"
                 f"{fu.get('n', 0)} janelas 'nenhuma' unânime; achados: "
                 f"{len(fu.get('achados', []))} (achado aqui = o próprio "
                 f"pool é cego); sem consenso: {fu.get('sem_consenso', 0)}."
                 + (f" {_esc(fu['nota'])}" if fu.get("nota") else "")
                 + "</p>")
        if recall.get("fundo_v1_anulado"):
            H.append(f"<p class='aviso'>Controle de fundo v1 ANULADO: "
                     f"{_esc(recall['fundo_v1_anulado']['razao'])}</p>")
        if recall.get("seeded"):
            H.append("<p>Recall semeado (formas-FN do Codex; detectores "
                     "CONGELADOS sobre cópia semeada, apagada ao fim):</p>")
            H.append("<table><tr><th>forma</th><th>classe de superfície</th>"
                     "<th>detectadas/M</th></tr>")
            for forma, classes in sorted(
                    recall["seeded"]["tabela"].items()):
                for classe, r in classes.items():
                    fora = r.get("fora_do_escopo_por_construcao")
                    H.append(f"<tr><td>{_esc(forma)}</td>"
                             f"<td>{_esc(classe)}"
                             + (" <span class='exp'>[fora do escopo por "
                                "construção]</span>" if fora else "")
                             + f"</td><td>{r['detectadas']}/{r['m']}"
                             + ("" if not fora else " (trivial)")
                             + "</td></tr>")
            H.append("</table>")
        for fx, razao in (recall.get("formas_fora") or {}).items():
            H.append(f"<p class='exp'>{_esc(fx)}: fora da medição — "
                     f"{_esc(razao)}</p>")
        for pmsa in recall.get("premissas", []):
            H.append(f"<p class='exp'>Premissa: {_esc(pmsa)}</p>")

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
                             eval_estagio0=ev,
                             diff_referencia=args.diff_referencia)
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


def _cmd_eval_recall(args):
    state = Path(args.state)
    if args.acao == "prepare":
        reg_estado, projecao = _carregar_estado(state)
        sessoes, _pul = _scan_corpus(args.workdir, args.host)
        tp = Counter(n2["forma"] for n2 in reg_estado.nivel(2))
        pre, amostra = eval_recall_preparar(
            sessoes, reg_estado, args.workdir, dict(tp),
            max_por_forma=args.max, k_fundo=args.k_fundo, seed=args.seed)
        _guard_estado(state)
        # cadeia de mtime: recibo PRIMEIRO, amostra DEPOIS, rótulos por
        # último; nenhum campo pós-rótulo no recibo
        (state / "recall-pre-registro.json").write_text(
            json.dumps(pre, ensure_ascii=False, indent=1), encoding="utf-8")
        Path(args.out).write_text(redigir(json.dumps(
            amostra, ensure_ascii=False, indent=1)), encoding="utf-8")
        print(json.dumps({"pool_por_forma": pre["pool_por_forma"],
                          "relaxados_por_forma": pre["relaxados_por_forma"],
                          "tp_por_forma": pre["tp_por_forma"],
                          "itens": len(amostra["itens"]),
                          "fundo": len(pre["janelas_de_fundo"]),
                          "amostra": args.out}, ensure_ascii=False, indent=1))
    elif args.acao == "seeded":
        import shutil as _sh
        origem = max(
            (p for p in Path(args.workdir).rglob("*.jsonl")
             if "/subagents/" not in str(p)),
            key=lambda p: p.stat().st_size)
        with open(origem, encoding="utf-8", errors="replace") as fh:
            ultimo_ts = None
            for linha in fh:
                try:
                    t = _parse_ts(json.loads(linha).get("timestamp"))
                    if t:
                        ultimo_ts = t
                except Exception:
                    continue
        linhas, manifesto = _linhas_semente(args.seed,
                                            (ultimo_ts or 0) + 3600)
        semeado = Path(args.workdir) / "__seeded__" / "proj"
        semeado.mkdir(parents=True, exist_ok=True)
        destino = semeado / origem.name
        _sh.copyfile(origem, destino)
        with open(destino, "a", encoding="utf-8") as fh:
            for linha in linhas:
                fh.write(linha + "\n")
        try:
            tabela = recall_seeded(semeado.parent, manifesto, host=args.host)
        finally:
            _sh.rmtree(semeado.parent)  # cópia semeada NUNCA persiste
        _guard_estado(state)
        (state / "recall-seeded.json").write_text(json.dumps(
            {"seed": args.seed, "m_por_classe": 3,
             "origem": origem.name, "tabela": tabela},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(tabela, ensure_ascii=False, indent=1))
    else:  # ingest
        amostra = json.loads(Path(args.amostra).read_text())
        la = json.loads(Path(args.labels[0]).read_text())
        lb = json.loads(Path(args.labels[1]).read_text())
        pre = json.loads((state / "recall-pre-registro.json").read_text())
        seeded_p = state / "recall-seeded.json"
        seeded = (json.loads(seeded_p.read_text())
                  if seeded_p.exists() else None)
        recall, catch_res = eval_recall_ingerir(amostra, la, lb, pre, seeded)
        _guard_estado(state)
        (state / "recall.json").write_text(json.dumps(
            recall, ensure_ascii=False, indent=1), encoding="utf-8")
        # resultado de catch SEPARADO do pré-registro (recibo limpo)
        (state / "recall-catch-resultado.json").write_text(json.dumps(
            catch_res, ensure_ascii=False, indent=1), encoding="utf-8")
        reg, projecao = _carregar_estado(state)
        evp = state / "eval.json"
        ev = json.loads(evp.read_text()) if evp.exists() else None
        (state / "report.html").write_text(
            render_report(reg, projecao, ev, recall=recall),
            encoding="utf-8")
        print(json.dumps({f: {k: v.get(k) for k in
                              ("tp_detectados", "detectados_relaxados",
                               "pool_fn", "amostrados", "p_fn_amostrado",
                               "recall_espaco_relaxado",
                               "recall_espaco_relaxado_intervalo",
                               "recall_unidade_mista")}
                          for f, v in recall["por_forma"].items()},
                         ensure_ascii=False, indent=1))
        print("fundo:", json.dumps(recall["fundo"], ensure_ascii=False))
        print("catch:", json.dumps(catch_res, ensure_ascii=False))


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
    rcp = Path(args.state) / "recall.json"
    recall = json.loads(rcp.read_text()) if rcp.exists() else None
    html = render_report(reg, projecao, ev, recall=recall)
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
    p.add_argument("--diff-referencia", dest="diff_referencia", default=None,
                   help="atividades.jsonl ou amostra antiga — gera o recibo "
                        "de diff do n dos padrões (R5.2 finding 4)")
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

    p = sub.add_parser("eval-recall", help="mede o RECALL dos detectores "
                       "(pool relaxado + fundo + semeadura; Codex #5/#20)")
    p.add_argument("acao", choices=["prepare", "seeded", "ingest"])
    p.add_argument("--state", required=True)
    p.add_argument("--workdir")
    p.add_argument("--host", default="roberto")
    p.add_argument("--out", help="arquivo da amostra (prepare)")
    p.add_argument("--amostra", help="amostra (ingest)")
    p.add_argument("--labels", nargs=2, help="rótulos A B (ingest)")
    p.add_argument("--max", type=int, default=25)
    p.add_argument("--k-fundo", dest="k_fundo", type=int, default=10)
    p.add_argument("--seed", type=int, default=11)
    p.set_defaults(fn=_cmd_eval_recall)

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

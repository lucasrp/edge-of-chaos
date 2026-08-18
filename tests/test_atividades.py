"""Testes do registro de Atividades v2 — fixtures 100% sintéticas.

Nenhum dado do operador entra no repo. O caso 17s é reproduzido como fixture
SINTÉTICA (teste de regressão do detector genérico, nunca evidência de
validade — brief v2 §3.4).
"""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tools.atividades import (
    CitacaoInvalida, EscritaProibida, OrcamentoLLM, Registry,
    RendererViolation, THRESHOLDS, _guard_estado, ausencia, cohen_kappa,
    derivar_agencia, eval_ingerir, eval_preparar, fold_padroes,
    montar_cobertura, pipeline, persistir, redigir, render_report,
    scan_arquivo, tempo_ativo_s,
)

SID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0001"
SID2 = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeee0002"
BASE = datetime(2026, 8, 11, 21, 0, 0, tzinfo=timezone.utc).timestamp()


def iso(seg):
    return datetime.fromtimestamp(BASE + seg, tz=timezone.utc).isoformat() \
        .replace("+00:00", "Z")


def e_user(seg, texto, uuid):
    return {"type": "user", "uuid": uuid, "timestamp": iso(seg),
            "cwd": "/home/x/proj", "sessionId": SID, "isSidechain": False,
            "origin": {"kind": "human"},
            "message": {"role": "user", "content": texto}}


def e_assistant_text(seg, texto, uuid):
    return {"type": "assistant", "uuid": uuid, "timestamp": iso(seg),
            "cwd": "/home/x/proj", "isSidechain": False,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": texto}]}}


def e_tool(seg, nome, inp, tool_id, uuid):
    return {"type": "assistant", "uuid": uuid, "timestamp": iso(seg),
            "cwd": "/home/x/proj", "isSidechain": False,
            "message": {"role": "assistant",
                        "content": [{"type": "tool_use", "id": tool_id,
                                     "name": nome, "input": inp}]}}


def e_result(seg, tool_id, texto, uuid):
    return {"type": "user", "uuid": uuid, "timestamp": iso(seg),
            "isSidechain": False,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_id,
                 "content": texto}]}}


def escrever(caminho, entradas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as fh:
        for e in entradas:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    return caminho


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atv-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class TestRedacao(Base):
    def test_regexes_de_segredo(self):
        casos = [
            ("minha api_key: abc123xyz", "abc123xyz"),
            ("password=hunter2", "hunter2"),
            ("chave sk-FAKEFAKE1234567890 solta", "sk-FAKE"),
            ("ghp_ABCDEFGH123456789012 token do gh", "ghp_A"),
            ("xoxb-1234-abcdef slack", "xoxb-"),
            ("https://user:senha123@host/x", "senha123"),
            ("export MINHA_API_KEY=segredo9", "segredo9"),
        ]
        for texto, proibido in casos:
            self.assertNotIn(proibido, redigir(texto), texto)
            self.assertIn("***", redigir(texto), texto)

    def test_redacao_na_ingestao_nada_persiste(self):
        """Fixture com sk- falso: NENHUM byte persistido pode conter o segredo."""
        segredo = "sk-FAKEFAKEFAKE12345678901234"
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, f"usa a chave {segredo} e password=hunter2fake", "u1"),
            e_assistant_text(5, "vou usar", "a1"),
            e_tool(10, "Bash", {"command": f"export API_KEY={segredo} && ls"},
                   "t1", "a2"),
            e_result(12, "t1", "ok", "u2"),
            e_user(30, "valeu", "u3"),
        ])
        reg, proj = pipeline(work, "hostX")
        state = self.tmp / "state"
        persistir(state, reg, proj)
        (state / "report.html").write_text(
            render_report(reg, proj), encoding="utf-8")
        for f in state.rglob("*"):
            if f.is_file():
                dados = f.read_bytes()
                self.assertNotIn(b"sk-FAKE", dados, f)
                self.assertNotIn(b"hunter2fake", dados, f)
        # e nos registros em memória também (redigido NA ingestão)
        blob = json.dumps(list(reg.by_id.values()))
        self.assertNotIn("sk-FAKE", blob)
        self.assertNotIn("hunter2fake", blob)


class TestNiveis(Base):
    def _n1(self, reg, i="n1-x"):
        return reg.add({"id": i, "nivel": 1, "session_id": SID, "host": "h",
                        "ts": iso(0), "kind": "voz-turno",
                        "conteudo_redigido": {"texto": "oi"},
                        "evidencia": {"arquivo_jsonl": "a", "linha": 1,
                                      "sha1_arquivo_no_momento_da_leitura": "s"}})

    def test_cadeia_valida(self):
        reg = Registry()
        self._n1(reg)
        n2 = reg.add({"id": "n2-x", "nivel": 2, "forma": "f",
                      "instancias": ["n1-x"], "params": {},
                      "detector_version": "v", "janela": {}})
        n3 = reg.add({"id": "n3-x", "nivel": 3, "claim": "c", "confianca": .5,
                      "alternativas": ["a"], "base": ["n2-x"],
                      "detector_version": "v", "model": "m"})
        reg.add({"id": "n4-x", "nivel": 4, "hipotese": "h?", "base": ["n3-x"],
                 "falsificacao": "f", "status": "proposta"})
        self.assertEqual(len(reg.by_id), 4)

    def test_n2_nao_cita_n2(self):
        reg = Registry()
        self._n1(reg)
        reg.add({"id": "n2-a", "nivel": 2, "forma": "f", "instancias": ["n1-x"],
                 "params": {}, "detector_version": "v", "janela": {}})
        with self.assertRaises(CitacaoInvalida):
            reg.add({"id": "n2-b", "nivel": 2, "forma": "f",
                     "instancias": ["n2-a"], "params": {},
                     "detector_version": "v", "janela": {}})

    def test_n4_nao_cita_n2_nem_n1(self):
        reg = Registry()
        self._n1(reg)
        reg.add({"id": "n2-a", "nivel": 2, "forma": "f", "instancias": ["n1-x"],
                 "params": {}, "detector_version": "v", "janela": {}})
        for base in (["n2-a"], ["n1-x"]):
            with self.assertRaises(CitacaoInvalida):
                reg.add({"id": "n4-z", "nivel": 4, "hipotese": "h?",
                         "base": base, "falsificacao": "f",
                         "status": "proposta"})

    def test_citacao_desconhecida_e_n1_citando(self):
        reg = Registry()
        with self.assertRaises(CitacaoInvalida):
            reg.add({"id": "n2-z", "nivel": 2, "forma": "f",
                     "instancias": ["nao-existe"], "params": {},
                     "detector_version": "v", "janela": {}})
        with self.assertRaises(CitacaoInvalida):
            reg.add({"id": "n1-cita", "nivel": 1, "kind": "voz-turno",
                     "instancias": ["n1-x"], "evidencia": {}})


class TestAgencia(unittest.TestCase):
    def test_imperativo_verbo_inicial_autoriza(self):
        ag = derivar_agencia(100.0, False, [(90.0, "faz o commit", False)])
        self.assertEqual(ag["executor"], "agente")
        self.assertEqual(ag["autorizacao"], "autorizado")

    def test_aceite_lexicon_exige_antecedente(self):
        """Finding R1 #6 (dig-2 C/DAMSL): 'ok' só autoriza COM antecedente."""
        com = derivar_agencia(100.0, False, [(90.0, "ok", True)])
        self.assertEqual(com["autorizacao"], "autorizado")
        sem = derivar_agencia(100.0, False, [(90.0, "ok", False)])
        self.assertEqual(sem["autorizacao"], "desconhecido")

    def test_saudacao_nao_autoriza(self):
        """Finding R1 #6: 'iae' é saudação, nunca autorização."""
        ag = derivar_agencia(100.0, False, [(90.0, "iae", True)])
        self.assertEqual(ag["autorizacao"], "desconhecido")
        self.assertEqual(ag["regra"], "saudacao-nao-autoriza")

    def test_voz_proxima_sem_marcador_nao_autoriza(self):
        ag = derivar_agencia(100.0, False,
                             [(90.0, "hoje o dia rendeu bem", True)])
        self.assertEqual(ag["autorizacao"], "desconhecido")

    def test_pergunta_nao_autoriza(self):
        ag = derivar_agencia(100.0, False, [(90.0, "pode commitar?", True)])
        self.assertEqual(ag["autorizacao"], "desconhecido")

    def test_sem_sinal_vira_desconhecido_nunca_chutado(self):
        ag = derivar_agencia(500.0, False, [(90.0, "faz o commit", True)])
        self.assertEqual(ag["autorizacao"], "desconhecido")
        ag2 = derivar_agencia(100.0, False, [])
        self.assertEqual(ag2["autorizacao"], "desconhecido")

    def test_sidechain_autonomo(self):
        ag = derivar_agencia(100.0, True, [(99.0, "vai", True)])
        self.assertEqual(ag["autorizacao"], "autonomo")


class TestRegressao17s(Base):
    """O caso 17s como fixture SINTÉTICA: a regra GENÉRICA
    resposta-curta-seguida-de-acao deve achá-lo (regressão, não validade)."""

    def test_detector_generico_acha_a_sequencia(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "publica o parágrafo com o gancho formal", "u1"),
            # proposta ADJACENTE ao aceite (R4 item 3: antecedente expira em
            # 300s e é consumido por tool_call/voz no meio)
            e_assistant_text(1500, "Parágrafo pronto:\n" + "x" * 900, "a1"),
            e_user(1552, "ok", "u2"),                       # voz curta, +52s
            e_tool(1569, "Bash",                            # +17s
                   {"command": "python3 escreve.py && git commit -am 'p' "
                               "&& git push"}, "t1", "a2"),
            e_result(1571, "t1", "ok\n   1111111..abc1234  preview -> main",
                     "u3"),
        ])
        reg, proj = pipeline(work, "hostX")
        n2s = [r for r in reg.nivel(2)
               if r["forma"] == "resposta-curta-seguida-de-acao"]
        self.assertEqual(len(n2s), 1)
        n2 = n2s[0]
        self.assertAlmostEqual(n2["params"]["delta_s"], 17.0, delta=0.5)
        n1s = [reg.by_id[i] for i in n2["instancias"]]
        kinds = {r["kind"] for r in n1s}
        self.assertEqual(kinds, {"voz-turno", "tool-call"})
        # âncoras: arquivo+linha da voz (linha 3) e da ação (linha 4)
        linhas = sorted(r["evidencia"]["linha"] for r in n1s)
        self.assertEqual(linhas, [3, 4])
        acao = next(r for r in n1s if r["kind"] == "tool-call")
        self.assertEqual(acao["agencia"]["executor"], "agente")
        self.assertEqual(acao["agencia"]["autorizacao"], "autorizado")
        # o commit vira N1 próprio com o hash
        commits = [r for r in reg.nivel(1) if r["kind"] == "commit"]
        self.assertEqual(len(commits), 1)
        self.assertEqual(commits[0]["evidencia"]["commit_hash"], "abc1234")
        # endereçamento de conteúdo (dig-1 B): uuid + hash da linha lida
        voz = next(r for r in n1s if r["kind"] == "voz-turno")
        self.assertEqual(voz["evidencia"]["uuid"], "u2")
        self.assertRegex(voz["evidencia"]["sha256_linha_lida"],
                         r"^[0-9a-f]{16}$")

    def test_linha_parcial_sem_newline_e_pulada(self):
        """jsonl mutável: última linha sem \\n (append em curso) não entra."""
        work = self.tmp / "work"
        caminho = escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "primeira linha completa da sessão", "u1"),
            e_user(60, "segunda linha completa aqui também", "u2"),
        ])
        with open(caminho, "a", encoding="utf-8") as fh:
            fh.write('{"type": "user", "uuid": "u3", "timestamp": "' +
                     iso(90) + '", "message": {"role": "user", "content"')
        s = scan_arquivo(caminho, "hostX")
        self.assertEqual(len(s["vozes"]), 2)
        self.assertEqual(s["linhas_puladas"], 1)

    def test_acao_fora_da_janela_nao_dispara(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "começa o trabalho de hoje aqui", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(100 + 121, "Write", {"file_path": "/x", "content": "y"},
                   "t1", "a1"),
        ])
        reg, _ = pipeline(work, "hostX")
        self.assertEqual([r for r in reg.nivel(2)
                          if r["forma"] == "resposta-curta-seguida-de-acao"],
                         [])


class TestSidechain(Base):
    def test_acao_de_subagente_e_autonoma_e_nao_e_voz(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "roda o experimento completo agora", "u1"),
            e_assistant_text(10, "rodando", "a1"),
        ])
        escrever(work / "proj" / SID / "subagents" / "agent-a1.jsonl", [
            {"type": "user", "uuid": "su1", "timestamp": iso(20),
             "isSidechain": True,
             "message": {"role": "user", "content": "prompt do agente-mãe"}},
            dict(e_tool(25, "Bash", {"command": "ls -la"}, "st1", "sa1"),
                 isSidechain=True),
        ])
        reg, proj = pipeline(work, "hostX")
        vozes = [r for r in reg.nivel(1) if r["kind"] == "voz-turno"]
        self.assertEqual(len(vozes), 1)  # o prompt do subagente NÃO é voz
        acoes = [r for r in reg.nivel(1) if r["kind"] == "tool-call"]
        self.assertEqual(len(acoes), 1)
        self.assertEqual(acoes[0]["agencia"]["autorizacao"], "autonomo")
        self.assertTrue(acoes[0]["conteudo_redigido"]["sidechain"])


class TestTempoAtivo(unittest.TestCase):
    def test_teto_e_sensibilidade(self):
        ts = [0.0, 100.0, 1000.0]
        self.assertEqual(tempo_ativo_s(ts, 300.0), 400.0)
        self.assertEqual(tempo_ativo_s(ts, 120.0), 220.0)
        self.assertEqual(tempo_ativo_s(ts, 600.0), 700.0)


class TestPadroes(Base):
    def _sessao_rajada(self, work, sid, dia_seg, nome):
        escrever(work / "proj" / f"{sid}.jsonl", [
            e_user(dia_seg, "trabalhando no projeto alpha beta gama", f"{nome}0"),
            dict(e_user(dia_seg + 10, "ok", f"{nome}1"), sessionId=sid),
            dict(e_user(dia_seg + 20, "sim", f"{nome}2"), sessionId=sid),
            dict(e_user(dia_seg + 30, "vai", f"{nome}3"), sessionId=sid),
            dict(e_user(dia_seg + 40, "isso", f"{nome}4"), sessionId=sid),
        ])

    def test_mesma_cena_sem_diversidade(self):
        work = self.tmp / "w1"
        self._sessao_rajada(work, SID, 0, "a")
        _, proj = pipeline(work, "hostX", agora_ts=BASE + 86400)
        p = next(x for x in proj["padroes"]
                 if x["forma"] == "rajada-de-turnos-curtos")
        self.assertEqual(p["estado"], "mesma-cena")
        self.assertEqual(p["diversidade"]["sessoes"], 1)
        self.assertEqual(p["diversidade"]["dias"], 1)

    def test_diversidade_2_dias_vira_ativo(self):
        work = self.tmp / "w2"
        self._sessao_rajada(work, SID, 0, "a")
        self._sessao_rajada(work, SID2, 2 * 86400, "b")
        _, proj = pipeline(work, "hostX", agora_ts=BASE + 3 * 86400)
        p = next(x for x in proj["padroes"]
                 if x["forma"] == "rajada-de-turnos-curtos")
        self.assertEqual(p["estado"], "ativo")
        self.assertGreaterEqual(p["diversidade"]["dias"], 2)
        self.assertEqual(p["n"], 2)

    def test_sem_reforco_14d_vira_dormente(self):
        work = self.tmp / "w3"
        self._sessao_rajada(work, SID, 0, "a")
        self._sessao_rajada(work, SID2, 2 * 86400, "b")
        _, proj = pipeline(work, "hostX", agora_ts=BASE + 20 * 86400)
        p = next(x for x in proj["padroes"]
                 if x["forma"] == "rajada-de-turnos-curtos")
        self.assertEqual(p["estado"], "dormente")


class TestRenderer(Base):
    def _pipeline_simples(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "só um turno de abertura da sessão", "u1"),
            e_assistant_text(10, "resposta", "a1"),
        ])
        return pipeline(work, "hostX")

    def test_ausencia_renderiza_nao_observado(self):
        reg, proj = self._pipeline_simples()
        html = render_report(reg, proj)
        self.assertIn("não observado em", html)
        self.assertNotIn("não ocorreu", html.lower().replace("nao", "não"))
        # sem eval → pendência declarada
        self.assertIn("Estágio 0 ainda não executado", html)

    def test_frase_proibida_fora_de_verbatim_estoura(self):
        reg, proj = self._pipeline_simples()
        proj["atividades"][0]["nome"] = "coisa que não ocorreu aqui"
        with self.assertRaises(RendererViolation):
            render_report(reg, proj)

    def test_verbatim_do_operador_com_a_frase_nao_estoura(self):
        work = self.tmp / "work2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "análise do incidente de ontem no cluster", "u0"),
            e_user(10, "não ocorreu", "u1"),
            e_user(20, "não ocorreu", "u2"),
            e_user(30, "não ocorreu", "u3"),
        ])
        reg, proj = pipeline(work, "hostX")
        formas = {r["forma"] for r in reg.nivel(2)}
        self.assertIn("rajada-de-turnos-curtos", formas)
        html = render_report(reg, proj)  # não deve levantar
        self.assertIn("rajada-de-turnos-curtos", html)


class TestGuardaEval(Base):
    def test_guarda_do_event_log_de_producao(self):
        for ruim in ("/tmp/x/state/events", "/tmp/x/state/events/log.jsonl",
                     "/tmp/qualquer/log.jsonl"):
            with self.assertRaises(EscritaProibida):
                _guard_estado(ruim)
        _guard_estado(self.tmp / "state" / "atividades-backfill")  # ok

    def test_orcamento(self):
        orc = OrcamentoLLM(teto=2)
        self.assertTrue(orc.permitir("a"))
        self.assertTrue(orc.permitir("b"))
        self.assertFalse(orc.permitir("c"))
        d = orc.dump()
        self.assertEqual((d["usadas"], d["negadas"]), (2, 1))

    def test_eval_ingerir_demote(self):
        amostra = {"thresholds_congelados": {"precisao_min": 0.8,
                                             "concordancia_min": 0.7},
                   "itens": [
                       {"item": 1, "forma": "boa", "n2_id": "x"},
                       {"item": 2, "forma": "boa", "n2_id": "y"},
                       {"item": 3, "forma": "ruim", "n2_id": "z"},
                       {"item": 4, "forma": "ruim", "n2_id": "w"},
                   ]}
        la = {"rotulador": "r1", "labels": [
            {"item": 1, "resposta": "sim"}, {"item": 2, "resposta": "sim"},
            {"item": 3, "resposta": "nao"}, {"item": 4, "resposta": "sim"}]}
        lb = {"rotulador": "r2", "labels": [
            {"item": 1, "resposta": "sim"}, {"item": 2, "resposta": "sim"},
            {"item": 3, "resposta": "nao"}, {"item": 4, "resposta": "nao"}]}
        ev = eval_ingerir(amostra, la, lb)
        self.assertEqual(ev["por_forma"]["boa"]["veredicto"], "confiavel")
        self.assertEqual(ev["por_forma"]["boa"]["precisao"], 1.0)
        self.assertEqual(ev["por_forma"]["ruim"]["veredicto"], "experimental")
        self.assertEqual(ev["por_forma"]["ruim"]["precisao"], 0.0)
        # κ agregado (dig-1 C): pares (s,s),(s,s),(n,n),(s,n) → p_o .75, κ .5
        self.assertEqual(ev["global"]["p_o"], 0.75)
        self.assertEqual(ev["global"]["kappa"], 0.5)
        self.assertIn("kappa", ev["por_forma"]["boa"])
        self.assertIn("confusao", ev["por_forma"]["ruim"])

    def test_eval_preparar_descricao_so_da_forma_do_item(self):
        """Regressão: descrições mecânicas são preguiçosas por forma (o dict
        eager estourava KeyError com params de outra forma)."""
        from tools.atividades import eval_preparar
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "abre a sessão de trabalho normal", "u1"),
            e_user(10, "ok", "u2"),
            e_user(20, "sim", "u3"),
            e_user(30, "vai", "u4"),
            e_tool(40, "Write", {"file_path": "/x", "content": "y"},
                   "t1", "a1"),
        ])
        reg, _ = pipeline(work, "hostX")
        amostra, prereg = eval_preparar(reg, work)
        formas = {i["forma"] for i in amostra["itens"]}
        self.assertGreaterEqual(len(formas), 2)
        for i in amostra["itens"]:
            self.assertTrue(i["descricao_mecanica"])
            self.assertTrue(i["evidencia"])
        # pré-registro (finding R1 #14): hash gravado + gold dos catch
        self.assertEqual(len(prereg["sha256_bloco_congelado"]), 64)
        self.assertEqual(len(prereg["catch_gold_por_item"]), 2)
        self.assertIn(prereg["tipo_amostra"], ("censo", "amostra"))

    def test_cohen_kappa(self):
        # concordância perfeita numa classe só → p_e = 1 → κ degenerado (None)
        p_o, k = cohen_kappa([("sim", "sim")] * 5)
        self.assertEqual(p_o, 1.0)
        self.assertIsNone(k)
        # exemplo trabalhado: 2 concordam sim, 1 concorda nao, 1 desacordo
        p_o, k = cohen_kappa([("sim", "sim"), ("sim", "sim"),
                              ("nao", "nao"), ("sim", "nao")])
        self.assertEqual((p_o, k), (0.75, 0.5))
        # rótulo fora das 3 classes é descartado do cálculo
        p_o, k = cohen_kappa([("sim", "talvez")])
        self.assertEqual((p_o, k), (None, None))


class TestDegradacaoDeclarada(Base):
    def test_sem_completer_fica_n2_only_declarado(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "abre a sessão de trabalho normal", "u1"),
            e_assistant_text(10, "ok, na escuta", "a1"),
        ])
        reg, proj = pipeline(work, "hostX", complete_fn=None)
        self.assertEqual(reg.nivel(3), [])
        self.assertEqual(reg.nivel(4), [])
        self.assertTrue(any("degradação DECLARADA" in d
                            for d in proj["degradacoes"]))

    def _fixture_d1(self, work):
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o texto do resumo agora", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])

    @staticmethod
    def _fake_complete(prompt):
        if "hipóteses de mentoria" in prompt:
            return ('{"hipotese": "Você revisa antes do ok?", '
                    '"falsificacao": "um relato de revisão prévia"}')
        if "Nomeie" in prompt:
            return "Fechamento do resumo"
        return ('{"claim": "sequência compatível com aceite rápido", '
                '"confianca": 0.6, "alternativas": ["revisão prévia em '
                'outra superfície"]}')

    _EVAL_OK = {"por_forma": {"resposta-curta-seguida-de-acao":
                              {"veredicto": "confiavel"}}}

    def test_sem_eval_nao_gera_n3_n4_mesmo_com_completer(self):
        """Finding R1 #2: gate do estágio 0 na GERAÇÃO — sem eval, nada sobe."""
        work = self.tmp / "workg"
        self._fixture_d1(work)
        reg, proj = pipeline(work, "hostX", complete_fn=self._fake_complete)
        self.assertEqual(reg.nivel(3), [])
        self.assertEqual(reg.nivel(4), [])
        self.assertTrue(any("estágio 0 pendente" in d
                            for d in proj["degradacoes"]))

    def test_forma_reprovada_nao_gera_n3_n4(self):
        """Finding R1 #2: forma sem selo `confiavel` não gera N3/N4."""
        work = self.tmp / "workr"
        self._fixture_d1(work)
        ev = {"por_forma": {"resposta-curta-seguida-de-acao":
                            {"veredicto": "experimental"}}}
        reg, proj = pipeline(work, "hostX", complete_fn=self._fake_complete,
                             eval_estagio0=ev)
        self.assertEqual(reg.nivel(3), [])
        self.assertEqual(reg.nivel(4), [])
        self.assertTrue(any("sem selo" in d for d in proj["degradacoes"]))

    def test_com_completer_e_eval_aprovado_gera_n3_e_n4(self):
        work = self.tmp / "work"
        self._fixture_d1(work)
        reg, proj = pipeline(work, "hostX", complete_fn=self._fake_complete,
                             eval_estagio0=self._EVAL_OK)
        self.assertGreaterEqual(len(reg.nivel(3)), 1)
        self.assertGreaterEqual(len(reg.nivel(4)), 1)
        n3 = reg.nivel(3)[0]
        self.assertTrue(n3["alternativas"])
        html = render_report(reg, proj, dict(
            self._EVAL_OK,
            por_forma={"resposta-curta-seguida-de-acao": {
                "veredicto": "confiavel", "n": 1, "precisao": 1.0,
                "concordancia": 1.0}},
            thresholds_congelados={
                "precisao_min": 0.8, "concordancia_min": 0.7},
            rotuladores=["a", "b"], amostra=1))
        self.assertIn("Você revisa antes do ok?", html)

    def test_render_gate_esconde_n3_n4_de_forma_reprovada(self):
        """Finding R1 #2 (render): N3/N4 de forma reprovada ficam fora do
        relatório principal mesmo se existirem no estado."""
        work = self.tmp / "workh"
        self._fixture_d1(work)
        reg, proj = pipeline(work, "hostX", complete_fn=self._fake_complete,
                             eval_estagio0=self._EVAL_OK)
        ev_reprovado = dict(
            self._EVAL_OK,
            por_forma={"resposta-curta-seguida-de-acao": {
                "veredicto": "experimental", "n": 1, "precisao": 0.2,
                "concordancia": 1.0}},
            thresholds_congelados={"precisao_min": 0.8,
                                   "concordancia_min": 0.7},
            rotuladores=["a", "b"], amostra=1)
        html = render_report(reg, proj, ev_reprovado)
        self.assertNotIn("sequência compatível com aceite rápido", html)
        self.assertNotIn("Você revisa antes do ok?", html)
        self.assertIn("fora do relatório principal", html)


class TestClassificarComando(unittest.TestCase):
    """Finding R1 #1 — probes do adversarial + regras do dig-2 perna A."""

    def test_stderr_redirect_nao_e_escrita(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("ls -la 2>/dev/null"), "leitura")
        self.assertEqual(cc("tail -c 100 x.log 2>&1"), "leitura")
        self.assertEqual(cc("ls > /dev/null"), "leitura")

    def test_git_leitura_vs_escrita(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("git branch -v"), "leitura")
        self.assertEqual(cc("git stash list"), "leitura")
        self.assertEqual(cc("git log --oneline -5"), "leitura")
        self.assertEqual(cc("git status"), "leitura")
        self.assertEqual(cc("git stash"), "escrita")
        self.assertEqual(cc("git branch -d velha"), "escrita")
        self.assertEqual(cc("git fetch origin"), "escrita")
        self.assertEqual(cc("git commit -m 'x'"), "commit")
        self.assertEqual(cc("git push origin main"), "commit")

    def test_maior_que_dentro_de_aspas_nao_e_redirect(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("jq '.a > .b' f.json"), "leitura")
        # v2.1: python -c que SÓ imprime é inspeção (leitura) — payload
        # decide; o `>` segue não sendo redirect
        self.assertEqual(cc("python3 -c 'print(1>2)'"), "leitura")
        self.assertEqual(cc("grep -E 'a>b' arquivo"), "leitura")

    def test_redirect_para_arquivo_real_e_escrita(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("echo oi > /tmp/x"), "escrita")
        self.assertEqual(cc("cat a >> b.log"), "escrita")

    def test_por_segmento_pega_o_mais_privilegiado(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("cat a | wc -l"), "leitura")
        self.assertEqual(cc("cat a | wc -l && git commit -m 'p'"), "commit")
        self.assertEqual(cc("ls && python3 x.py"), "execucao")
        self.assertEqual(cc("sed -i 's/a/b/' f && cat f"), "escrita")

    def test_ssh_e_wrappers(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("ssh roberto 'ls -la'"), "leitura")
        self.assertEqual(cc("EDGE_HOME=/x timeout 30 pgrep -f beat"),
                         "leitura")
        self.assertEqual(cc("curl -o /tmp/f https://x"), "escrita")


class TestRegressaoD1LeituraNaoDispara(Base):
    """Finding R1 #1/#19: a MESMA forma do caso 17s, mas com comando de
    leitura (tail + stderr-redirect) — o detector NÃO pode disparar."""

    def test_voz_curta_seguida_de_leitura_nao_e_d1(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "acompanha o log do servidor por favor", "u1"),
            e_assistant_text(30, "Acompanhando:\n" + "x" * 900, "a1"),
            e_user(1552, "ok", "u2"),
            e_tool(1569, "Bash",
                   {"command": "tail -n 50 servidor.log 2>/dev/null"},
                   "t1", "a2"),
        ])
        reg, _ = pipeline(work, "hostX")
        self.assertEqual([r for r in reg.nivel(2)
                          if r["forma"] == "resposta-curta-seguida-de-acao"],
                         [])


class TestD2Dedup(Base):
    """Finding R1 #4: uma resposta resolve NO MÁXIMO uma pergunta; nenhum
    turno humano intervém entre pergunta e resposta."""

    def test_uma_resposta_nao_conta_para_duas_perguntas(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "como funciona a projeção ortogonal aqui?", "u1"),
            e_user(60, "e o produto interno entra onde nisso?", "u2"),
            e_assistant_text(90, "Explicação longa:\n" + "y" * 900, "a1"),
            e_user(120, "ok", "u3"),
        ])
        reg, _ = pipeline(work, "hostX")
        d2 = [r for r in reg.nivel(2)
              if r["forma"] == "pergunta-explicacao-resposta-curta"]
        self.assertEqual(len(d2), 1)  # só a pergunta u2 (imediata) pareia

    def test_turno_humano_intermediario_quebra_o_par(self):
        work = self.tmp / "work2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "como funciona a projeção ortogonal aqui?", "u1"),
            e_assistant_text(30, "Explicação longa:\n" + "y" * 900, "a1"),
            e_user(60, "hmm deixa eu pensar um pouco nisso", "u2"),
            e_user(90, "ok", "u3"),
        ])
        reg, _ = pipeline(work, "hostX")
        d2 = [r for r in reg.nivel(2)
              if r["forma"] == "pergunta-explicacao-resposta-curta"]
        self.assertEqual(d2, [])


class TestD3SemSidechain(Base):
    """Finding R1 #5: leituras repetidas de SUBAGENTE não viram padrão do
    operador."""

    def test_leituras_de_subagente_nao_disparam_d3(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "roda o diagnóstico completo por favor", "u1"),
            e_assistant_text(10, "rodando", "a1"),
        ])
        escrever(work / "proj" / SID / "subagents" / "agent-a1.jsonl", [
            dict(e_tool(20 + i * 60, "Bash",
                        {"command": "pgrep -f servico"}, f"t{i}", f"sa{i}"),
                 isSidechain=True)
            for i in range(4)
        ])
        reg, _ = pipeline(work, "hostX")
        d3 = [r for r in reg.nivel(2)
              if r["forma"] == "leituras-repetidas-de-estado-externo"]
        self.assertEqual(d3, [])


class TestEvalPacote(Base):
    """Findings R1 #3/#7: o pacote do eval carrega o fato julgado COMPLETO,
    minimizado e redigido — sem bytes crus de thinking/tool_result."""

    def test_pacote_sem_segredo_e_sem_thinking(self):
        segredo = "sk-FAKEFAKEFAKE12345678901234"
        work = self.tmp / "work"
        entradas = [
            e_user(0, "sobe a configuração nova do serviço", "u1"),
            {"type": "assistant", "uuid": "a0", "timestamp": iso(5),
             "isSidechain": False,
             "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "PENSAMENTO-CRU-NUNCA-SAI",
                  "signature": "ASSINATURA-CRUA-NUNCA-SAI"}]}},
            e_user(100, "ok", "u2"),
            e_tool(110, "Bash",
                   {"command": f"export API_KEY={segredo} && "
                               "git commit -am 'cfg'"}, "t1", "a1"),
        ]
        escrever(work / "proj" / f"{SID}.jsonl", entradas)
        reg, _ = pipeline(work, "hostX")
        amostra, prereg = eval_preparar(reg, work)
        blob = json.dumps(amostra, ensure_ascii=False) + json.dumps(
            prereg, ensure_ascii=False)
        self.assertNotIn("sk-FAKE", blob)
        self.assertNotIn("PENSAMENTO-CRU", blob)
        self.assertNotIn("ASSINATURA-CRUA", blob)
        catch_ns = {int(k) for k in prereg["catch_gold_por_item"]}
        d1 = [i for i in amostra["itens"]
              if i["forma"] == "resposta-curta-seguida-de-acao"
              and i["item"] not in catch_ns]
        self.assertTrue(d1)
        cargas = json.dumps(d1[0]["evidencia"], ensure_ascii=False)
        # o fato julgado (comando integral, redigido) está no pacote
        self.assertIn("git commit -am", cargas)

    def test_ingest_com_pre_registro_e_catch(self):
        work = self.tmp / "work2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o resumo agora por favor", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])
        reg, _ = pipeline(work, "hostX")
        amostra, prereg = eval_preparar(reg, work)
        catch_itens = set(int(k) for k in prereg["catch_gold_por_item"])
        labels = [{"item": i["item"],
                   "resposta": prereg["catch_gold_por_item"].get(
                       str(i["item"]),
                       prereg["catch_gold_por_item"].get(i["item"], "sim"))}
                  for i in amostra["itens"]]
        la = {"rotulador": "a", "labels": labels}
        lb = {"rotulador": "b", "labels": labels}
        ev = eval_ingerir(amostra, la, lb, prereg)
        self.assertTrue(ev["pre_registro"]["verificado"])
        self.assertEqual(ev["catch_trials"]["n"], 2)
        self.assertEqual(ev["catch_trials"]["a"], 2)
        self.assertEqual(ev["amostra"], len(amostra["itens"]) - 2)
        for forma in ev["por_forma"].values():
            pass  # catch fora das métricas: nenhum item catch nas formas
        contados = sum(f["n"] for f in ev["por_forma"].values())
        self.assertEqual(contados, len(amostra["itens"]) - len(catch_itens))


class TestDiversidadeFronteiraDeSessao(Base):
    """Finding R1 #8: UMA sessão cruzando a meia-noite não concede
    diversidade de dias — padrão fica mesma-cena."""

    def test_sessao_unica_cruzando_meia_noite_e_mesma_cena(self):
        work = self.tmp / "work"
        # BASE é 21:00Z; +4h de gap entre rajadas cruza a meia-noite
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "vamos virar a noite nesse projeto", "u0"),
            e_user(10, "ok", "u1"),
            e_user(20, "sim", "u2"),
            e_user(30, "vai", "u3"),
            e_user(4 * 3600 + 10, "bora", "u4"),
            e_user(4 * 3600 + 20, "isso", "u5"),
            e_user(4 * 3600 + 30, "segue", "u6"),
        ])
        _, proj = pipeline(work, "hostX", agora_ts=BASE + 86400)
        p = next(x for x in proj["padroes"]
                 if x["forma"] == "rajada-de-turnos-curtos")
        self.assertGreaterEqual(p["diversidade"]["dias"], 2)
        self.assertEqual(p["diversidade"]["sessoes"], 1)
        self.assertEqual(p["estado"], "mesma-cena")


class TestRedacaoAfinada(unittest.TestCase):
    def test_prosa_comum_nao_e_redigida(self):
        """Finding R1 #9: 'token de validação' é prosa, não segredo."""
        self.assertEqual(redigir("o token de validação do argumento"),
                         "o token de validação do argumento")
        self.assertEqual(redigir("a password do formulário é discutida"),
                         "a password do formulário é discutida")

    def test_valor_com_forma_de_segredo_e_redigido(self):
        self.assertIn("***", redigir("token abc123xyz9"))
        self.assertIn("***", redigir("password=hunter2"))

    def test_familias_completadas(self):
        """Finding R1 #10: AIza, glpat-, sk_live_, npm_, PEM."""
        casos = [
            "AIza" + "A1" * 17 + "b",             # 35 depois do prefixo
            "glpat-" + "x1" * 10 + "abcd",
            "sk_live_" + "a1b2c3d4e5f6",
            "npm_" + "a1" * 18,
            "-----BEGIN PRIVATE KEY-----\\nMIIEvQ==\\n"
            "-----END PRIVATE KEY-----",
        ]
        for c in casos:
            self.assertIn("***", redigir(f"veja {c} aqui"), c)


class TestRajadaSemInterrogativas(Base):
    """Finding R1 #16: rajada de PERGUNTAS curtas não é
    rajada-de-turnos-curtos (sobreporia D2)."""

    def test_perguntas_curtas_nao_disparam_rajada(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "sessão de dúvidas conceituais de hoje", "u0"),
            e_user(10, "e agora?", "u1"),
            e_user(20, "por quê?", "u2"),
            e_user(30, "como?", "u3"),
        ])
        reg, _ = pipeline(work, "hostX")
        self.assertEqual([r for r in reg.nivel(2)
                          if r["forma"] == "rajada-de-turnos-curtos"], [])


class TestRegistryColisao(unittest.TestCase):
    def test_id_duplicado_divergente_estoura(self):
        """Finding R1 #17: sobrescrever id silenciosamente é proibido."""
        reg = Registry()
        base = {"id": "n1-a", "nivel": 1, "kind": "voz-turno",
                "conteudo_redigido": {"texto": "oi"}, "evidencia": {}}
        reg.add(dict(base))
        reg.add(dict(base))  # idempotente: mesmo conteúdo, ok
        with self.assertRaises(CitacaoInvalida):
            reg.add(dict(base, conteudo_redigido={"texto": "outro"}))


class TestNew1CredencialEmFlag(Base):
    """NEW-1 (dig-3 A): credencial em flag de CLI + camada de entropia."""

    def test_flag_p_com_valor_de_segredo(self):
        senha = "3f9a1c7e" * 8  # 64 hex
        red = redigir(f"cypher-shell -u neo4j -p {senha} 'MATCH (n)'")
        self.assertNotIn(senha, red)
        red2 = redigir(f"mysql --password={senha} -h host db")
        self.assertNotIn(senha, red2)

    def test_flags_inocentes_nao_disparam(self):
        for cmd in ("mkdir -p /tmp/x/y", "ssh -p 22 host ls",
                    "grep -P 'pat' f"):
            self.assertEqual(redigir(cmd), cmd, cmd)

    def test_entropia_hex_longo_mascara_uuid_e_sha_curto_nao(self):
        senha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b"
        self.assertIn("***", redigir(f"a senha é {senha}78", entropia=True))
        uuid = "7fed4159-1841-467b-8b28-04272fdb6299"
        self.assertEqual(redigir(f"sessão {uuid}", entropia=True),
                         f"sessão {uuid}")
        sha16 = "ca8926b767123039"
        self.assertEqual(redigir(f"linha {sha16}", entropia=True),
                         f"linha {sha16}")

    def test_pipeline_e_eval_sem_hex64(self):
        """O caso real do R2-verifier: 64-hex depois de -p chega ao pacote."""
        senha = "3f9a1c7e" * 8
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "conecta no neo4j e roda a query agora", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Bash",
                   {"command": f"cypher-shell -u neo4j -p {senha} "
                               "'MATCH (n) RETURN n' && git commit -am 'q'"},
                   "t1", "a1"),
        ])
        reg, proj = pipeline(work, "hostX")
        amostra, prereg = eval_preparar(reg, work)
        state = self.tmp / "state"
        persistir(state, reg, proj)
        blob = json.dumps(amostra) + json.dumps(list(reg.by_id.values()))
        for f in state.rglob("*"):
            if f.is_file():
                self.assertNotIn(senha.encode(), f.read_bytes(), f)
        self.assertNotIn(senha, blob)


class TestNew2ComandoAninhado(unittest.TestCase):
    """NEW-2 (dig-3 B): comando remoto/aninhado classificado por recursão;
    payload ilegível nunca herda leitura."""

    def test_ssh_payload_mutante(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("ssh assertia 'pip install rank-bm25'"),
                         "escrita")
        self.assertEqual(cc("ssh -o BatchMode=yes host "
                            "'timeout 540 python3 run.py'"), "execucao")
        self.assertEqual(cc("ssh host 'git commit -am x'"), "commit")

    def test_ssh_payload_leitura_continua_leitura(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("ssh roberto 'ls -la'"), "leitura")
        self.assertEqual(cc("ssh -i k -p 22 host 'cat /etc/os-release'"),
                         "leitura")

    def test_ssh_sem_payload_e_unknown(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("ssh host"), "execucao")

    def test_bash_c_e_docker_exec(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("bash -c 'rm -rf /tmp/x'"), "escrita")
        self.assertEqual(cc("sh -c 'ls /tmp'"), "leitura")
        self.assertEqual(cc("docker exec -it caixa cat /var/log/app.log"),
                         "leitura")
        self.assertEqual(cc("docker exec caixa touch /x"), "escrita")
        self.assertEqual(cc("docker ps"), "leitura")


class TestNew3Atribuicao(Base):
    """NEW-3: N3/N4 não atribuem ao operador execução do agente."""

    def _fixture(self, work):
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o texto do resumo agora", "u1"),
            e_assistant_text(50, "Proposta de fechamento:\n" + "z" * 900,
                             "a0"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])

    _EVAL_OK = {"por_forma": {"resposta-curta-seguida-de-acao":
                              {"veredicto": "confiavel"}}}

    def test_claim_que_atribui_ao_operador_e_descartado(self):
        work = self.tmp / "w1"
        self._fixture(work)

        def teimoso(prompt):
            if "Nomeie" in prompt:
                return "Fechamento do resumo"
            return ('{"claim": "Você executou a escrita em 10s", '
                    '"confianca": 0.6, "alternativas": ["a"]}')

        reg, proj = pipeline(work, "hostX", complete_fn=teimoso,
                             eval_estagio0=self._EVAL_OK)
        self.assertEqual(reg.nivel(3), [])
        self.assertTrue(any("NEW-3" in d for d in proj["degradacoes"]))

    def test_claim_com_atribuicao_correta_passa(self):
        work = self.tmp / "w2"
        self._fixture(work)

        def correto(prompt):
            if "Nomeie" in prompt:
                return "Fechamento do resumo"
            if "hipóteses de mentoria" in prompt:
                return ('{"hipotese": "O agente executou a escrita sob seu '
                        'comando — você revisa o resultado depois?", '
                        '"falsificacao": "relato de revisão"}')
            return ('{"claim": "o agente delegado executou a escrita 10s '
                    'após o aceite do operador", "confianca": 0.6, '
                    '"alternativas": ["revisão prévia"]}')

        reg, proj = pipeline(work, "hostX", complete_fn=correto,
                             eval_estagio0=self._EVAL_OK)
        # v2.1: "fecha o texto…" (imperativo ≤30) também vira D1 → 2 N3
        self.assertEqual(len(reg.nivel(3)), 2)
        self.assertEqual(reg.nivel(3)[0]["executores_da_base"],
                         {"acoes": 1, "executadas_por_agente": 1})
        self.assertEqual(len(reg.nivel(4)), 1)


class TestNew4SessaoProtocolo(Base):
    """NEW-4: sessão de despacho/protocolo não é voz do operador."""

    def test_dispatch_plan_nao_e_voz_e_sessao_e_pulada_com_razao(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "AUTHORITATIVE DISPATCH PLAN\n\nYou are the executor "
                      "of beat 42. Produce the artefato.", "u1"),
            e_assistant_text(10, "executando o plano", "a1"),
            e_tool(20, "Bash", {"command": "ls"}, "t1", "a2"),
        ])
        escrever(work / "proj2" / f"{SID2}.jsonl", [
            e_user(0, "me explica a projeção ortogonal de novo", "u1"),
        ])
        reg, proj = pipeline(work, "hostX")
        self.assertEqual(len(proj["atividades"]), 1)  # fantasma não entra
        puladas = proj["cobertura"]["sessoes_puladas"]
        self.assertTrue(any("protocolo/despacho" in p["razao"]
                            for p in puladas))

    def test_skill_header_nao_e_voz(self):
        work = self.tmp / "w2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "Base directory for this skill: /x/y", "u1"),
            e_user(10, "roda o beat agora por favor", "u2"),
        ])
        reg, _ = pipeline(work, "hostX")
        vozes = [r for r in reg.nivel(1) if r["kind"] == "voz-turno"]
        self.assertEqual(len(vozes), 1)


class TestNew5CatchIndistinguivel(Base):
    def test_catch_tem_forma_de_item_real(self):
        """NEW-5: id n2-<12hex>, âncora com arquivo/linha/uuid — nada de
        'catch' visível nem linha nula."""
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o resumo agora por favor", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])
        reg, _ = pipeline(work, "hostX")
        amostra, prereg = eval_preparar(reg, work)
        catch_ns = {int(k) for k in prereg["catch_gold_por_item"]}
        for i in amostra["itens"]:
            self.assertRegex(i["n2_id"], r"^n2-[0-9a-f]{12}$", i["n2_id"])
            for e in i["evidencia"]:
                anc = e["ancora"]
                self.assertIsInstance(anc["linha"], int)
                self.assertTrue(anc.get("arquivo"))
                self.assertTrue(anc.get("uuid"))
            if i["item"] in catch_ns:
                self.assertNotIn("catch", json.dumps(i))


class TestNew6Adjacencia(Base):
    def test_turno_humano_no_meio_quebra_antecedente(self):
        """NEW-6: antecedente = assistant-texto IMEDIATAMENTE anterior."""
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "me explica o plano de novo por favor", "u1"),
            e_assistant_text(10, "Plano detalhado:\n" + "p" * 900, "a1"),
            e_user(50, "hmm vou pensar mais um pouco nisso", "u2"),
            e_user(80, "ok", "u3"),
            e_tool(90, "Write", {"file_path": "/x", "content": "y"},
                   "t1", "a2"),
        ])
        reg, _ = pipeline(work, "hostX")
        acao = next(r for r in reg.nivel(1) if r["kind"] == "tool-call")
        # 'ok' não tem antecedente imediato (u2 interveio) → desconhecido
        self.assertEqual(acao["agencia"]["autorizacao"], "desconhecido")

    def test_adjacencia_direta_autoriza(self):
        work = self.tmp / "w2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "me explica o plano de novo por favor", "u1"),
            e_assistant_text(10, "Plano detalhado:\n" + "p" * 900, "a1"),
            e_user(80, "ok", "u3"),
            e_tool(90, "Write", {"file_path": "/x", "content": "y"},
                   "t1", "a2"),
        ])
        reg, _ = pipeline(work, "hostX")
        acao = next(r for r in reg.nivel(1) if r["kind"] == "tool-call")
        self.assertEqual(acao["agencia"]["autorizacao"], "autorizado")


class TestNew7NomeSemJuizo(Base):
    def test_nome_com_juizo_cai_para_fallback_deterministico(self):
        from tools.atividades import clusterizar, scan_arquivo as _sa
        work = self.tmp / "work"
        caminho = escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "despacha os planos da rodada de hoje", "u1"),
            e_tool(10, "Write", {"file_path": "/home/x/proj/plano.md",
                                 "content": "y"}, "t1", "a1"),
        ])
        s = _sa(caminho, "hostX")
        orc = OrcamentoLLM()
        atvs, log = clusterizar(
            [s], complete_fn=lambda p: "Despacho Autoritário de Planos "
                                       "Mecânicos", orcamento=orc)
        self.assertEqual(len(atvs), 1)
        self.assertNotIn("Autoritário", atvs[0]["nome"])
        self.assertIn("proj", atvs[0]["nome"])  # basename do cwd
        self.assertTrue(any(l["acao"] == "nome-rejeitado" for l in log))


class TestNew8CommitsVisiveis(Base):
    def test_ate_12_commits_todos_renderizam(self):
        work = self.tmp / "work"
        entradas = [e_user(0, "sobe a série de commits de hoje", "u1")]
        for i in range(11):
            entradas.append(e_tool(10 + i * 10, "Bash",
                                   {"command": f"git commit -am 'c{i}'"},
                                   f"t{i}", f"a{i}"))
            entradas.append(e_result(12 + i * 10, f"t{i}",
                                     f"ok\n   aaaa{i:03d}..bcd{i:04d}  x -> y",
                                     f"u{i + 10}"))
        escrever(work / "proj" / f"{SID}.jsonl", entradas)
        reg, proj = pipeline(work, "hostX")
        html = render_report(reg, proj)
        commits = proj["atividades"][0]["sessions"][0]["commits"]
        self.assertEqual(len(commits), 11)
        for c in commits:
            self.assertIn(c[:7], html)


class TestR4Responder(Base):
    """R4 item 1: resposta do operador a N4 — transição, idempotência,
    corpus rotulado, render."""

    def _estado_com_n4(self, nome):
        work = self.tmp / f"w-{nome}"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o texto do resumo agora", "u1"),
            e_assistant_text(50, "Proposta:\n" + "z" * 900, "a0"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])

        def fake(prompt):
            if "Nomeie" in prompt:
                return "Fechamento do resumo"
            if "hipóteses de mentoria" in prompt:
                return ('{"hipotese": "O agente executou a escrita sob seu '
                        'comando — você revisa depois?", '
                        '"falsificacao": "relato de revisão"}')
            return ('{"claim": "o agente delegado executou a escrita após '
                    'aceite do operador", "confianca": 0.6, '
                    '"alternativas": ["revisão prévia"]}')

        ev = {"por_forma": {"resposta-curta-seguida-de-acao":
                            {"veredicto": "confiavel"}}}
        reg, proj = pipeline(work, "hostX", complete_fn=fake,
                             eval_estagio0=ev)
        state = self.tmp / f"state-{nome}"
        persistir(state, reg, proj)
        n4_id = reg.nivel(4)[0]["id"]
        return state, n4_id

    def test_confirmo_transiciona_e_registra(self):
        from tools.atividades import responder_n4
        state, n4_id = self._estado_com_n4("c")
        n4 = responder_n4(state, n4_id, "confirmo", nota="isso mesmo")
        self.assertEqual(n4["status"], "confirmada")
        self.assertEqual(n4["resposta_operador"]["nota"], "isso mesmo")
        self.assertNotIn("invalid_at", n4)
        # persistido + corpus rotulado
        linhas = [json.loads(l) for l in
                  open(state / "respostas.jsonl", encoding="utf-8")]
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["veredito"], "confirmo")
        html = (state / "report.html").read_text(encoding="utf-8")
        self.assertIn("[confirmada]", html)
        self.assertIn("isso mesmo", html)

    def test_contesto_bi_temporal_e_idempotencia(self):
        from tools.atividades import responder_n4
        state, n4_id = self._estado_com_n4("x")
        n4 = responder_n4(state, n4_id, "contesto",
                          nota="eu revisei em outra tela")
        self.assertEqual(n4["status"], "contestada")
        self.assertTrue(n4["invalid_at"])  # bi-temporal, nunca deleção
        # o registro continua no estado
        recs = [json.loads(l) for l in
                open(state / "atividades.jsonl", encoding="utf-8")]
        persistido = next(r for r in recs if r.get("id") == n4_id)
        self.assertEqual(persistido["status"], "contestada")
        html = (state / "report.html").read_text(encoding="utf-8")
        self.assertIn("[contestada", html)
        # idempotência: já respondida → erro, nunca sobrescreve
        with self.assertRaises(ValueError):
            responder_n4(state, n4_id, "confirmo")

    def test_veredito_invalido_e_n4_inexistente(self):
        from tools.atividades import responder_n4
        state, n4_id = self._estado_com_n4("v")
        with self.assertRaises(ValueError):
            responder_n4(state, n4_id, "talvez")
        with self.assertRaises(ValueError):
            responder_n4(state, "n4-inexistente99", "confirmo")


class TestR4EntropiaPaths(Base):
    """R4 item 2 (NEWER-1): a máscara de entropia não pode comer paths e
    fundir cabeças de comando D3."""

    PATH = ("/tmp/claude-1001/-home-edgesandbox/"
            "828886a1-cc8d-43c0-b950-b2ba009c34b1/tasks/b2xli4v0j.output")

    def test_path_de_task_fica_intacto(self):
        cmd = f"cat {self.PATH}"
        self.assertEqual(redigir(cmd, entropia=True), cmd)

    def test_segredo_b64_sem_barras_continua_mascarado(self):
        self.assertIn("***", redigir("chave A9zX3kQ8wP1mN5vB7cR2tY6u aqui",
                                     entropia=True))

    def test_leituras_de_arquivos_distintos_nao_viram_grupo(self):
        base = "/tmp/claude-1001/-home-edgesandbox/x/tasks"
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "acompanha as três saídas de task", "u1"),
            e_tool(60, "Bash", {"command": f"cat {base}/b2xli4v0j.output"},
                   "t1", "a1"),
            e_tool(120, "Bash", {"command": f"cat {base}/b4czrssm1.output"},
                   "t2", "a2"),
            e_tool(180, "Bash", {"command": f"cat {base}/b9qwe7rt2.output"},
                   "t3", "a3"),
        ])
        reg, _ = pipeline(work, "hostX")
        d3 = [r for r in reg.nivel(2)
              if r["forma"] == "leituras-repetidas-de-estado-externo"]
        self.assertEqual(d3, [])  # 3 cabeças distintas, nenhum grupo

    def test_mesma_cabeca_continua_agrupando_e_persiste_redigida(self):
        work = self.tmp / "work2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "monitora o processo do beat", "u1"),
        ] + [e_tool(60 * (i + 1), "Bash", {"command": "pgrep -f beat"},
                    f"t{i}", f"a{i}") for i in range(3)])
        reg, _ = pipeline(work, "hostX")
        d3 = [r for r in reg.nivel(2)
              if r["forma"] == "leituras-repetidas-de-estado-externo"]
        self.assertEqual(len(d3), 1)
        # v2.1: chave = (verbo, alvo)
        self.assertEqual(d3[0]["params"]["verbo"], "pgrep")
        self.assertEqual(d3[0]["params"]["alvo"], "beat")


class TestR4Adjacencia(Base):
    """R4 item 3: antecedente consumido por tool_call e expirado por tempo."""

    def test_probe_r2_assistant_cedo_ok_3h_depois(self):
        work = self.tmp / "w1"
        entradas = [
            e_user(0, "roda a rotina completa de hoje", "u1"),
            e_assistant_text(5, "Plano:\n" + "p" * 900, "a0"),
        ]
        for i in range(30):
            entradas.append(e_tool(10 + i * 300, "Bash",
                                   {"command": "pgrep -f x"},
                                   f"t{i}", f"a{i + 1}"))
        entradas += [
            e_user(10800, "ok", "u2"),
            e_tool(10810, "Write", {"file_path": "/x", "content": "y"},
                   "tw", "aw"),
        ]
        escrever(work / "proj" / f"{SID}.jsonl", entradas)
        reg, _ = pipeline(work, "hostX")
        acao = next(r for r in reg.nivel(1)
                    if r["kind"] == "tool-call"
                    and r["conteudo_redigido"].get("tool") == "Write")
        self.assertEqual(acao["agencia"]["autorizacao"], "desconhecido")

    def test_tool_call_no_meio_consome_antecedente(self):
        work = self.tmp / "w2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "me mostra o plano de novo", "u1"),
            e_assistant_text(10, "Plano:\n" + "p" * 900, "a0"),
            e_tool(20, "Bash", {"command": "ls"}, "t0", "a1"),
            e_user(60, "ok", "u2"),
            e_tool(70, "Write", {"file_path": "/x", "content": "y"},
                   "tw", "aw"),
        ])
        reg, _ = pipeline(work, "hostX")
        acao = next(r for r in reg.nivel(1)
                    if r["conteudo_redigido"].get("tool") == "Write")
        self.assertEqual(acao["agencia"]["autorizacao"], "desconhecido")

    def test_antecedente_expira_em_300s(self):
        work = self.tmp / "w3"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "me mostra o plano de novo", "u1"),
            e_assistant_text(10, "Plano:\n" + "p" * 900, "a0"),
            e_user(400, "ok", "u2"),
            e_tool(410, "Write", {"file_path": "/x", "content": "y"},
                   "tw", "aw"),
        ])
        reg, _ = pipeline(work, "hostX")
        acao = next(r for r in reg.nivel(1)
                    if r["conteudo_redigido"].get("tool") == "Write")
        self.assertEqual(acao["agencia"]["autorizacao"], "desconhecido")


class TestR4DoubleUnwrap(unittest.TestCase):
    """R4 item 4: unwrap duplo (docker→sh -c, ssh→sh -c) com payload
    completo após -c."""

    def test_probes_do_verificador(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc('docker exec c sh -c "echo ok > f"'), "escrita")
        self.assertEqual(cc('docker exec c bash -c "git commit -m x"'),
                         "commit")
        self.assertEqual(cc("ssh host \"sh -c 'touch /x'\""), "escrita")

    def test_payload_completo_apos_c(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("bash -c 'cat /a | wc -l'"), "leitura")
        self.assertEqual(cc("sh -c 'ls && rm /x'"), "escrita")


class TestR4AcaoSemBase(unittest.TestCase):
    """R4 item 6 (NEWER-4): base com 0 ações não sustenta texto de 'ação'."""

    def test_zero_acoes_rejeita_texto_de_acao(self):
        from tools.atividades import _atribuicao_invalida
        self.assertTrue(_atribuicao_invalida(
            "Você trabalha em ciclos pergunta-confirmação-ação", 0, 0))
        self.assertTrue(_atribuicao_invalida(
            "padrão compatível com execução imediata", 0, 0))
        self.assertFalse(_atribuicao_invalida(
            "padrão de pergunta seguida de resposta curta", 0, 0))


class TestR5Segmentacao(Base):
    """R5: sessão → trechos; cortes mecânicos versionados, ancorados."""

    def test_gap_15min_corta_e_400s_nao(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "w1"
        caminho = escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "primeira parte do trabalho de hoje", "u1"),
            e_user(60, "seguindo na mesma parte ainda", "u2"),
            e_user(60 + 1000, "voltei do almoço, retomando aqui", "u3"),
            e_user(60 + 1400, "continuando depois de pensar", "u4"),
        ])
        s = _sa(caminho, "hostX")
        trechos, cortes = segmentar(s)
        self.assertEqual(len(trechos), 2)
        self.assertEqual(cortes[0]["sinal"], "gap")
        self.assertEqual(cortes[0]["linha"], 3)  # âncora: linha da retomada
        # 400s (< 900) NÃO corta — u4 fica no trecho 2
        self.assertEqual(len(trechos[1]["vozes"]), 2)
        self.assertEqual(trechos[0]["trecho_id"], f"tre-{SID[:8]}-L1")

    def test_marcador_de_voz_literal_do_operador(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "w2"
        caminho = escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "bom dia, retomando o trabalho no projeto", "u1"),
            e_user(60, "vamos continuar a atividade 1. a atividade 2 ta "
                       "superada", "u2"),
            e_user(120, "então bora nessa parte agora", "u3"),
        ])
        s = _sa(caminho, "hostX")
        trechos, cortes = segmentar(s)
        self.assertEqual(len(trechos), 2)
        self.assertEqual(cortes[0]["sinal"], "marcador-de-voz")
        self.assertEqual(cortes[0]["linha"], 2)

    def test_marcador_no_primeiro_turno_nao_corta(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "w3"
        caminho = escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "vamos continuar a atividade 1 de onde paramos", "u1"),
            e_user(60, "seguindo aqui sem mudança nenhuma", "u2"),
        ])
        s = _sa(caminho, "hostX")
        trechos, _ = segmentar(s)
        self.assertEqual(len(trechos), 1)  # honesto: sem sinal interno

    def test_cwd_sustentado_corta_e_digressao_nao(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "w4"
        entradas = [e_user(0, "trabalhando no projeto principal", "u1")]
        for i in range(5):
            entradas.append(e_tool(10 + i * 10, "Bash",
                                   {"command": "ls"}, f"ta{i}", f"aa{i}"))
        # digressão: 2 eventos noutro cwd — NÃO corta
        for i in range(2):
            entradas.append(dict(
                e_tool(70 + i * 10, "Bash", {"command": "ls"},
                       f"td{i}", f"ad{i}"), cwd="/home/x/digressao"))
        # mudança sustentada: 5 eventos — corta
        for i in range(5):
            entradas.append(dict(
                e_tool(100 + i * 10, "Bash", {"command": "ls"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/outro"))
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = _sa(caminho, "hostX")
        trechos, cortes = segmentar(s)
        self.assertEqual(len(trechos), 2)
        self.assertEqual(cortes[0]["sinal"], "cwd-sustentado")
        self.assertEqual(trechos[0]["cwd"], "/home/x/proj")
        self.assertEqual(trechos[1]["cwd"], "/home/x/outro")

    def test_cwd_ambiguo_sem_completer_nao_corta(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "w5"
        entradas = [e_user(0, "trabalhando no projeto principal", "u1"),
                    e_tool(10, "Bash", {"command": "ls"}, "t0", "a0")]
        for i in range(3):  # 3 eventos: ambíguo
            entradas.append(dict(
                e_tool(30 + i * 10, "Bash", {"command": "ls"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/outro"))
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = _sa(caminho, "hostX")
        trechos, _ = segmentar(s)  # sem completer → conservador
        self.assertEqual(len(trechos), 1)

    def test_conservacao_de_tempo_exata(self):
        work = self.tmp / "w6"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "parte um do dia começa aqui agora", "u1"),
            e_user(200, "seguindo na parte um ainda sim", "u2"),
            e_user(200 + 950, "voltei, parte dois do dia agora", "u3"),
            e_user(200 + 950 + 100, "continuando na parte dois aqui", "u4"),
            e_user(200 + 950 + 100 + 2000, "e a parte três pra fechar", "u5"),
        ])
        reg, proj = pipeline(work, "hostX")
        from tools.atividades import tempo_ativo_s
        rec = proj["segmentacao"]["por_sessao"][0]
        self.assertGreaterEqual(rec["n_trechos"], 2)
        self.assertAlmostEqual(rec["conservacao_s"]["delta"], 0.0, places=6)
        # conservação em TODOS os tetos, direto nos trechos
        import glob as _g
        from tools.atividades import scan_arquivo as _sa, segmentar
        s = _sa(_g.glob(str(work / "proj" / "*.jsonl"))[0], "hostX")
        trechos, _ = segmentar(s)
        for cap in (300, 120, 600):
            soma = sum(t["segundos_ativos_atribuidos"][cap] for t in trechos)
            self.assertAlmostEqual(soma, tempo_ativo_s(s["ts_todos"], cap),
                                   places=9, msg=f"cap {cap}")

    def test_anti_inflacao_trechos_nao_sao_diversidade(self):
        """Sessão cortada em 2 trechos NÃO tira padrão de mesma-cena."""
        work = self.tmp / "w7"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "trabalhando na parte um de hoje", "u0"),
            e_user(10, "ok", "u1"),
            e_user(20, "sim", "u2"),
            e_user(30, "vai", "u3"),
            e_user(2000, "voltando pra outra frente agora", "u4"),
            e_user(2010, "bora", "u5"),
            e_user(2020, "isso", "u6"),
            e_user(2030, "segue", "u7"),
        ])
        reg, proj = pipeline(work, "hostX", agora_ts=BASE + 86400)
        self.assertEqual(
            proj["segmentacao"]["por_sessao"][0]["n_trechos"], 2)
        p = next(x for x in proj["padroes"]
                 if x["forma"] == "rajada-de-turnos-curtos")
        self.assertEqual(p["n"], 2)
        self.assertEqual(p["diversidade"]["sessoes"], 1)
        self.assertEqual(p["estado"], "mesma-cena")

    def test_d3_corte_na_mesma_atividade_nao_parte_o_comportamento(self):
        """R5.2 finding 4: 6 leituras idênticas partidas por gap DENTRO da
        mesma Atividade = UM comportamento (n=6), não dois grupos de 3."""
        work = self.tmp / "w8"
        entradas = [e_user(0, "monitorando o processo em duas levas", "u1")]
        for i in range(3):
            entradas.append(e_tool(10 + i * 60, "Bash",
                                   {"command": "pgrep -f beat"},
                                   f"ta{i}", f"aa{i}"))
        for i in range(3):
            entradas.append(e_tool(1200 + i * 60, "Bash",
                                   {"command": "pgrep -f beat"},
                                   f"tb{i}", f"ab{i}"))
        escrever(work / "proj" / f"{SID}.jsonl", entradas)
        reg, proj = pipeline(work, "hostX")
        self.assertEqual(
            proj["segmentacao"]["por_sessao"][0]["n_trechos"], 2)
        d3 = [r for r in reg.nivel(2)
              if r["forma"] == "leituras-repetidas-de-estado-externo"]
        self.assertEqual(len(d3), 1)
        self.assertEqual(d3[0]["params"]["n_repeticoes"], 6)
        self.assertEqual(len(d3[0]["trechos"]), 2)  # refs aos 2 trechos
        self.assertTrue(d3[0]["trecho_dono"])       # mas UM dono só

    def _fixture_duas_atividades(self, work):
        entradas = [e_user(0, "escrevendo o artigo no latex agora", "u1")]
        for i in range(5):
            entradas.append(dict(
                e_tool(10 + i * 100, "Bash", {"command": "pgrep -f x"},
                       f"ta{i}", f"aa{i}"), cwd="/home/x/latex"))
        entradas.append(dict(
            e_user(500, "agora vamos rodar os experimentos", "u2"),
            cwd="/home/x/exp"))
        for i in range(5):
            entradas.append(dict(
                e_tool(510 + i * 100, "Bash", {"command": "pgrep -f x"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/exp"))
        escrever(work / "proj" / f"{SID}.jsonl", entradas)

    def test_trechos_da_mesma_sessao_clusterizam_por_cwd(self):
        """Paper-shape: latex + outro cwd na MESMA sessão → 2 Atividades."""
        work = self.tmp / "w9"
        self._fixture_duas_atividades(work)
        reg, proj = pipeline(work, "hostX")
        self.assertEqual(len(proj["atividades"]), 2)
        cwds = {a["cwd"] for a in proj["atividades"]}
        self.assertEqual(cwds, {"/home/x/latex", "/home/x/exp"})
        for a in proj["atividades"]:
            self.assertEqual(a["session_ids"], [SID])

    def test_d3_fronteira_de_atividade_parte_o_grupo(self):
        """R5.2 finding 4 (contraparte): leituras através de fronteira de
        ATIVIDADE ficam em grupos separados."""
        work = self.tmp / "w10"
        self._fixture_duas_atividades(work)
        reg, proj = pipeline(work, "hostX")
        d3 = [r for r in reg.nivel(2)
              if r["forma"] == "leituras-repetidas-de-estado-externo"]
        self.assertEqual(len(d3), 2)
        self.assertEqual([r["params"]["n_repeticoes"] for r in d3], [5, 5])


class TestR52Findings(Base):
    """R5.2 — um teste por finding do adversarial R5.1."""

    def test_f1_trecho_sem_voz_nao_herda_abertura(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "f1"
        entradas = [e_user(0, "abrindo o trabalho do dia aqui", "u1")]
        for i in range(5):
            entradas.append(e_tool(10 + i * 10, "Bash", {"command": "ls"},
                                   f"ta{i}", f"aa{i}"))
        for i in range(5):  # trecho novo SEM voz
            entradas.append(dict(
                e_tool(100 + i * 10, "Bash", {"command": "ls"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/outro"))
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = _sa(caminho, "hostX")
        trechos, _ = segmentar(s)
        self.assertEqual(len(trechos), 2)
        self.assertEqual(trechos[1]["abertura"], "")  # NUNCA a da sessão

    def test_f1_aberturas_vazias_nao_fundem_clusters(self):
        from tools.atividades import clusterizar
        t1 = {"trecho_id": "t1", "session_id": SID, "host": "h",
              "arquivo": "a", "sha1": "s", "sidechain": False,
              "cwd": "/home/x/aaa", "abertura": "", "eventos": [],
              "vozes": [], "assistant_turnos": [],
              "ts_todos": [BASE], "span": {"ts_start": iso(0),
                                           "ts_end": None,
                                           "linha_start": 1}}
        t2 = dict(t1, trecho_id="t2", cwd="/home/y/bbb", ts_todos=[BASE + 9])
        atvs, log = clusterizar([t1, t2])
        self.assertEqual(len(atvs), 2)  # sem evidência → sem merge

    def test_f1_merge_por_cwd_pai_filho_com_profundidade(self):
        from tools.atividades import _cwd_relacionado
        self.assertTrue(_cwd_relacionado("/home/x/proj",
                                         "/home/x/proj/latex"))
        # pai raso (profundidade 2) NUNCA ancora merge — era a gaveta
        self.assertFalse(_cwd_relacionado("/home/x", "/home/x/proj"))
        self.assertFalse(_cwd_relacionado("/home/x/a", "/home/x/b"))

    def test_f2_touch_persiste_cwd_do_trecho(self):
        work = self.tmp / "f2"
        TestR5Segmentacao._fixture_duas_atividades(self, work)
        reg, proj = pipeline(work, "hostX")
        for a in proj["atividades"]:
            for t in a["sessions"]:
                self.assertEqual(t["cwd"], a["cwd"])  # auditável

    def test_f3_dono_unico_soma_bate(self):
        work = self.tmp / "f3"
        TestR5Segmentacao._fixture_duas_atividades(self, work)
        reg, proj = pipeline(work, "hostX")
        soma = sum(len(a["n2_ids"]) for a in proj["atividades"])
        self.assertEqual(soma, len(reg.nivel(2)))  # nenhum N2 em duas

    def test_f3_corte_nao_atravessa_janela_voz_acao(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "f3b"
        entradas = [
            e_user(0, "prepara o fechamento do texto agora", "u1"),
            e_user(100, "ok", "u2"),
            # marcador entre a voz e a ação — o corte cairia AQUI…
            e_user(150, "agora vamos para a outra frente", "u3"),
            # …mas a ação está a 90s do "ok": o corte move para depois dela
            e_tool(190, "Write", {"file_path": "/x", "content": "y"},
                   "t1", "a1"),
            e_user(400, "seguindo depois da escrita", "u4"),
        ]
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = _sa(caminho, "hostX")
        trechos, cortes = segmentar(s)
        self.assertEqual(len(cortes), 1)
        self.assertTrue(cortes[0].get("movido"))
        # voz e ação no MESMO trecho
        reg, _ = pipeline(work, "hostX")
        d1 = [r for r in reg.nivel(2)
              if r["forma"] == "resposta-curta-seguida-de-acao"]
        self.assertEqual(len(d1), 1)
        self.assertEqual(len(d1[0]["trechos"]), 1)

    def test_f5_sub_piso_dobra_no_vizinho(self):
        work = self.tmp / "f5"
        entradas = [e_user(0, "trabalho principal da manhã aqui", "u1")]
        for i in range(6):
            entradas.append(e_tool(10 + i * 100, "Bash",
                                   {"command": "pgrep -f x"},
                                   f"ta{i}", f"aa{i}"))
        # excursão sustentada (5 eventos) mas MINÚSCULA (40s ativos) e sem
        # retorno — corta, mas o cluster fica sub-piso e dobra no vizinho
        for i in range(5):
            entradas.append(dict(
                e_tool(700 + i * 10, "Bash", {"command": "ls"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/mini"))
        escrever(work / "proj" / f"{SID}.jsonl", entradas)
        reg, proj = pipeline(work, "hostX")
        self.assertEqual(len(proj["atividades"]), 1)
        a = proj["atividades"][0]
        dobrados = [t for t in a["sessions"] if t.get("digressao_de")]
        self.assertEqual(len(dobrados), 1)
        self.assertEqual(dobrados[0]["cwd"], "/home/x/mini")
        self.assertTrue(any(l.get("acao") == "dobrado-no-vizinho"
                            for l in proj["cluster_log"]))

    def test_f5_retorno_ao_cwd_anterior_e_digressao_sem_corte(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "f5b"
        entradas = [e_user(0, "trabalho principal da manhã aqui", "u1")]
        for i in range(3):
            entradas.append(e_tool(10 + i * 10, "Bash", {"command": "ls"},
                                   f"ta{i}", f"aa{i}"))
        for i in range(6):  # excursão SUSTENTADA (6 eventos, 50s) que volta
            entradas.append(dict(
                e_tool(50 + i * 10, "Bash", {"command": "ls"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/outro"))
        for i in range(3):  # retorno ao base em ≤900s
            entradas.append(e_tool(120 + i * 10, "Bash", {"command": "ls"},
                                   f"tc{i}", f"ac{i}"))
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = _sa(caminho, "hostX")
        trechos, cortes = segmentar(s)
        self.assertEqual(len(trechos), 1)  # ida-e-volta: nenhum corte

    def test_f6_delta_sempre_leva_catch_fresco(self):
        from tools.atividades import eval_delta_preparar, eval_preparar
        work = self.tmp / "f6"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o resumo agora por favor", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])
        reg, _ = pipeline(work, "hostX")
        amostra, prereg_full = eval_preparar(reg, work)
        # nada rotulado antes → tudo é delta; catch fresco ainda assim entra
        delta, ra, rb, pre = eval_delta_preparar(amostra, {}, {}, seed=23)
        self.assertEqual(pre["catch_gold_por_item_delta"] and
                         len(pre["catch_gold_por_item_delta"]), 2)
        ids_delta_catch = {i["n2_id"] for i in delta["itens"]
                          if i["item"] in pre["catch_gold_por_item_delta"]}
        ids_census_catch = {i["n2_id"] for i in amostra["itens"]
                           if i["item"] in {int(k) for k in
                                            prereg_full["catch_gold_por_item"]}}
        self.assertFalse(ids_delta_catch & ids_census_catch)  # frescos
        self.assertEqual(len(pre["sha256_bloco_congelado"]), 64)

    def test_f7_nomeador_recebe_o_trabalho(self):
        from tools.atividades import clusterizar, scan_arquivo as _sa
        work = self.tmp / "f7"
        caminho = escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "conversa qualquer de abertura aqui", "u1"),
            e_tool(10, "Edit", {"file_path": "/home/x/proj/artigo.tex",
                                "content": "y"}, "t1", "a1"),
        ])
        s = _sa(caminho, "hostX")
        prompts = []

        def espiao(p):
            prompts.append(p)
            return "Edição do artigo tex"

        orc = OrcamentoLLM()
        clusterizar([s], complete_fn=espiao, orcamento=orc)
        self.assertTrue(prompts)
        self.assertIn("artigo.tex", prompts[0])
        self.assertIn("/home/x/proj", prompts[0])
        self.assertIn("Edit", prompts[0])

    def test_f8_segundos_reconciliam_exato(self):
        work = self.tmp / "f8"
        TestR5Segmentacao._fixture_duas_atividades(self, work)
        reg, proj = pipeline(work, "hostX")
        from tools.atividades import tempo_ativo_s
        soma_atv = sum(a["segundos_ativos_total"]
                       for a in proj["atividades"])
        sessao_s = proj["segmentacao"]["por_sessao"][0]["conservacao_s"][
            "sessao"]
        self.assertAlmostEqual(soma_atv, sessao_s, places=3)

    def test_f10_recibo_de_arbitragem_persistido(self):
        from tools.atividades import scan_arquivo as _sa, segmentar
        work = self.tmp / "f10"
        entradas = [e_user(0, "trabalho principal da manhã aqui", "u1"),
                    e_tool(10, "Bash", {"command": "ls"}, "t0", "a0")]
        for i in range(3):  # ambíguo (3 eventos), sem retorno
            entradas.append(dict(
                e_tool(30 + i * 10, "Bash", {"command": "ls"},
                       f"tb{i}", f"ab{i}"), cwd="/home/x/outro"))
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = _sa(caminho, "hostX")
        orc = OrcamentoLLM()
        trechos, cortes = segmentar(
            s, complete_fn=lambda p: "DISTINTA", orcamento=orc,
            model="modelo-teste")
        self.assertEqual(len(trechos), 2)
        arb = cortes[0]["arbitragem"]
        self.assertEqual(arb["model"], "modelo-teste")
        self.assertEqual(len(arb["prompt_sha256"]), 64)
        self.assertEqual(arb["resposta"], "DISTINTA")
        # decisão DIGRESSAO também deixa recibo (sem corte)
        s2 = _sa(caminho, "hostX")
        trechos2, cortes2 = segmentar(
            s2, complete_fn=lambda p: "DIGRESSAO", orcamento=OrcamentoLLM(),
            model="modelo-teste")
        self.assertEqual(len(trechos2), 1)
        self.assertEqual(len(s2["arbitragens"]), 1)
        self.assertEqual(s2["arbitragens"][0]["resposta"], "DIGRESSAO")


class TestRecall(Base):
    """eval-recall — o desenho anti-autoelogio (Codex #5/#20)."""

    def _corpus(self, work):
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o texto do resumo agora", "u1"),
            e_assistant_text(50, "Proposta:\n" + "z" * 900, "a0"),
            e_user(100, "ok", "u2"),                       # D1 congelado
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
            e_user(300, "acho que pode ser", "u3"),        # D1 SÓ relaxado
            #        (17 chars, fora do lexicon, não-imperativo)
            e_tool(540, "Write", {"file_path": "/y.md", "content": "y"},
                   "t2", "a2"),                            # Δ240s > 120
            e_user(4000, "janela morta sem candidato nenhum aqui", "u4"),
            e_user(5200, "outra janela morta bem parada", "u5"),
        ])
        return pipeline(work, "hostX")

    def test_relaxado_cobre_congelado_e_pool_exclui_detectado(self):
        from tools.atividades import recall_pool_fn, _scan_corpus
        work = self.tmp / "w1"
        reg, _ = self._corpus(work)
        sessoes, _ = _scan_corpus(work, "hostX")
        pool, relaxados = recall_pool_fn(sessoes, reg)
        # relaxado ⊇ congelado: todo N2 congelado das 4 formas tem candidato
        # relaxado compartilhando instância
        for n2 in reg.nivel(2):
            if n2["forma"] not in relaxados:
                continue
            self.assertTrue(any(
                set(rc["instancias"]) & set(n2["instancias"])
                for rc in relaxados[n2["forma"]]), n2["forma"])
        # o pool de FN NÃO contém o detectado (u2/t1); contém o relaxado
        # (u3/t2)
        d1_pool = pool["resposta-curta-seguida-de-acao"]
        inst_pool = {i for rc in d1_pool for i in rc["instancias"]}
        detectados = {i for n2 in reg.nivel(2)
                      if n2["forma"] == "resposta-curta-seguida-de-acao"
                      for i in n2["instancias"]}
        self.assertFalse(inst_pool & detectados)
        self.assertTrue(d1_pool)  # o par blz-manda/Write está no pool

    def test_janelas_de_fundo_sem_candidato(self):
        from tools.atividades import (recall_pool_fn, recall_janelas_de_fundo,
                                      _scan_corpus, _parse_ts)
        work = self.tmp / "w2"
        self._corpus(work)
        sessoes, _ = _scan_corpus(work, "hostX")
        _, relaxados = recall_pool_fn(sessoes, Registry())
        janelas = recall_janelas_de_fundo(sessoes, relaxados, k=3, seed=5)
        intervalos = [(_parse_ts(rc["janela"]["de"]),
                       _parse_ts(rc["janela"]["ate"]))
                      for lst in relaxados.values() for rc in lst]
        for j in janelas:
            ini, fim = _parse_ts(j["ts_ini"]), _parse_ts(j["ts_fim"])
            for a, b in intervalos:
                self.assertFalse(a < fim and b > ini, j)

    def test_wilson(self):
        from tools.atividades import wilson
        lo, hi = wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertLess(hi, 0.35)
        lo2, hi2 = wilson(10, 10)
        self.assertGreater(lo2, 0.65)
        self.assertEqual(wilson(0, 0), (None, None))

    def test_pre_registro_limpo_e_catch_separado(self):
        """Cadeia limpa: recibo sem campo pós-rótulo; catch em retorno
        separado do ingest (a ressalva do R5.2 fechada em código)."""
        from tools.atividades import (eval_recall_preparar,
                                      eval_recall_ingerir, _scan_corpus)
        work = self.tmp / "w3"
        reg, _ = self._corpus(work)
        sessoes, _ = _scan_corpus(work, "hostX")
        pre, amostra = eval_recall_preparar(
            sessoes, reg, work, {"resposta-curta-seguida-de-acao": 1},
            max_por_forma=5, k_fundo=2, seed=3)
        self.assertNotIn("catch_resultado", json.dumps(pre))
        self.assertEqual(len(pre["catch_gold_por_item"]), 2)
        # rotular tudo: FN-reais 'nao', catch pelo gold, fundo 'nenhuma'
        fundo = {i["item"] for i in amostra["itens"]
                 if i.get("tipo") == "janela-de-fundo"}
        catch = {int(k): v for k, v in pre["catch_gold_por_item"].items()}
        labels = []
        for i in amostra["itens"]:
            if i["item"] in fundo:
                r = "nenhuma"
            elif i["item"] in catch:
                r = catch[i["item"]]
            else:
                r = "nao"
            labels.append({"item": i["item"], "resposta": r})
        la = {"rotulador": "a", "labels": labels}
        lb = {"rotulador": "b", "labels": labels}
        recall, catch_res = eval_recall_ingerir(amostra, la, lb, pre)
        self.assertEqual(catch_res, {"a": 2, "b": 2, "n": 2})
        self.assertNotIn("catch", json.dumps(recall["por_forma"]))
        d1 = recall["por_forma"]["resposta-curta-seguida-de-acao"]
        self.assertEqual(d1["tp_detectados"], 1)
        self.assertEqual(d1["p_fn_amostrado"], 0.0)
        self.assertEqual(d1["recall_unidade_mista"], 1.0)
        self.assertEqual(d1["recall_espaco_relaxado"], 1.0)
        self.assertEqual(recall["fundo"]["nenhuma_unanime"],
                         recall["fundo"]["n"])

    def test_fn_rotulado_sim_derruba_o_recall(self):
        from tools.atividades import (eval_recall_preparar,
                                      eval_recall_ingerir, _scan_corpus)
        work = self.tmp / "w4"
        reg, _ = self._corpus(work)
        sessoes, _ = _scan_corpus(work, "hostX")
        pre, amostra = eval_recall_preparar(
            sessoes, reg, work, {"resposta-curta-seguida-de-acao": 1},
            max_por_forma=5, k_fundo=0, seed=3)
        catch = {int(k) for k in pre["catch_gold_por_item"]}
        labels = [{"item": i["item"],
                   "resposta": ("sim" if i["item"] not in catch
                                and i.get("forma") ==
                                "resposta-curta-seguida-de-acao" else "nao")}
                  for i in amostra["itens"]]
        la = {"rotulador": "a", "labels": labels}
        lb = {"rotulador": "b", "labels": labels}
        recall, _cr = eval_recall_ingerir(amostra, la, lb, pre)
        d1 = recall["por_forma"]["resposta-curta-seguida-de-acao"]
        self.assertEqual(d1["p_fn_amostrado"], 1.0)
        self.assertLess(d1["recall_espaco_relaxado"], 0.7)  # honesto: cai

    def test_semeadura_bem_formada_e_seeded_recall(self):
        from tools.atividades import _linhas_semente, recall_seeded
        linhas, manifesto = _linhas_semente(9, 1000000000.0)
        self.assertEqual(set(manifesto), {
            "resposta-curta-seguida-de-acao",
            "pergunta-explicacao-resposta-curta",
            "leituras-repetidas-de-estado-externo",
            "rajada-de-turnos-curtos"})
        for classes in manifesto.values():
            self.assertEqual(len(classes), 4)
            for inst in classes.values():
                self.assertEqual(len(inst), 3)  # M=12 por forma
        for linha in linhas:
            json.loads(linha)  # bem-formadas
        # roda os detectores CONGELADOS numa cópia semeada mínima
        work = self.tmp / "seeded" / "proj"
        work.mkdir(parents=True)
        base = [e_user(0, "sessão base para a semeadura de recall", "u1")]
        with open(work / f"{SID}.jsonl", "w", encoding="utf-8") as fh:
            for e in base:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
            for linha in linhas:
                fh.write(linha + "\n")
        tabela = recall_seeded(work.parent, manifesto, host="seed")
        d1 = tabela["resposta-curta-seguida-de-acao"]
        self.assertEqual(d1["in-spec"]["detectadas"], 3)       # harness ok
        # R6.2 fix 1: classe agora usa aceites INÉDITOS (fora do lexicon —
        # o controle não pode conter o gabarito); 0/3 é o número honesto:
        # o lexicon não generaliza a aceites nunca vistos
        self.assertEqual(d1["aceite-7-15-chars-ineditos"]["detectadas"], 0)
        self.assertEqual(d1["atraso-121-600s"]["detectadas"], 0)
        d3 = tabela["leituras-repetidas-de-estado-externo"]
        self.assertEqual(d3["in-spec"]["detectadas"], 3)
        self.assertEqual(d3["duas-repeticoes"]["detectadas"], 0)


class TestRecallCirurgico(Base):
    """Correções da verificação do recall: janelas de fundo íntegras,
    unidades consistentes, regra de parada, seeded fora-de-escopo."""

    def test_janela_seleciona_por_eventos_e_pacote_estrito(self):
        """A seleção conta EVENTOS (não linhas-com-ts) e toda evidência do
        pacote cai estritamente dentro da janela declarada."""
        from tools.atividades import (_scan_corpus, eval_recall_preparar,
                                      _parse_ts)
        work = self.tmp / "w1"
        # sessão com muitas linhas assistant (ts sem evento) num vale sem
        # eventos — a janela NÃO pode ser escolhida ali
        entradas = [e_user(0, "trabalho normal de abertura aqui", "u1")]
        for i in range(30):  # vale: só assistant text (linha com ts,
            entradas.append(e_assistant_text(2000 + i * 30,  # sem evento)
                                             "pensando...", f"a{i}"))
        entradas += [e_user(4000, "voltei ao trabalho agora sim", "u2"),
                     e_tool(4010, "Bash", {"command": "pgrep -f x"},
                            "t1", "ax1"),
                     e_tool(4100, "Bash", {"command": "df -h"},
                            "t2", "ax2")]
        escrever(work / "proj" / f"{SID}.jsonl", entradas)
        reg, _ = pipeline(work, "hostX")
        sessoes, _p = _scan_corpus(work, "hostX")
        pre, amostra = eval_recall_preparar(
            sessoes, reg, work, {}, max_por_forma=3, k_fundo=3, seed=2)
        for i in amostra["itens"]:
            if i.get("tipo") != "janela-de-fundo":
                continue
            ini = _parse_ts(i["janela"]["de"])
            fim = _parse_ts(i["janela"]["ate"])
            self.assertTrue(i["evidencia"] or i.get("nota"))  # vazia declara
            for e in i["evidencia"]:
                t = _parse_ts(e["carga"]["ts"])
                self.assertTrue(ini <= t < fim,
                                (i["item"], e["carga"]["ts"]))
        # recibo: n_eventos == o que o pacote efetivamente carrega
        fundo_itens = {i["item"]: i for i in amostra["itens"]
                       if i.get("tipo") == "janela-de-fundo"}
        for j, i in zip(pre["janelas_de_fundo"],
                        sorted(fundo_itens.values(),
                               key=lambda x: x["item"])):
            self.assertEqual(j["n_eventos"],
                             len(i["evidencia"]) if len(i["evidencia"]) < 30
                             else j["n_eventos"])

    def test_regra_de_parada_da_reapresentacao(self):
        from tools.atividades import pode_reapresentar, REAPRESENTACAO_MAX
        self.assertEqual(REAPRESENTACAO_MAX, 1)
        self.assertTrue(pode_reapresentar(7, {}))
        self.assertFalse(pode_reapresentar(7, {7: 1}))  # nunca 2ª vez

    def test_unidades_consistentes_no_ingest(self):
        from tools.atividades import eval_recall_ingerir
        amostra = {"itens": [
            {"item": 1, "forma": "resposta-curta-seguida-de-acao",
             "n2_id": "x"},
            {"item": 2, "forma": "resposta-curta-seguida-de-acao",
             "n2_id": "y"}]}
        pre = {"sha256_bloco_congelado": "s", "catch_gold_por_item": {},
               "pool_por_forma": {"resposta-curta-seguida-de-acao": 23},
               "relaxados_por_forma": {"resposta-curta-seguida-de-acao": 25},
               "tp_por_forma": {"resposta-curta-seguida-de-acao": 2}}
        la = {"rotulador": "a", "labels": [
            {"item": 1, "resposta": "sim"}, {"item": 2, "resposta": "sim"}]}
        recall, _ = eval_recall_ingerir(amostra, la, la, pre)
        d1 = recall["por_forma"]["resposta-curta-seguida-de-acao"]
        # espaço consistente: (25-23)/(2 + 1.0*23) = 2/25 = 0.08
        self.assertEqual(d1["detectados_relaxados"], 2)
        self.assertEqual(d1["recall_espaco_relaxado"], 0.08)
        self.assertEqual(d1["recall_unidade_mista"], 0.08)
        self.assertIn("consistente", d1["nota_unidades"].lower())
        self.assertIn("relaxamento_deltas", recall)
        self.assertIn("caveat_central", recall["leitura"])

    def test_seeded_marca_fora_de_escopo(self):
        from tools.atividades import _linhas_semente, recall_seeded
        linhas, manifesto = _linhas_semente(9, 2000000000.0)
        work = self.tmp / "seeded" / "proj"
        work.mkdir(parents=True)
        with open(work / f"{SID}.jsonl", "w", encoding="utf-8") as fh:
            fh.write(json.dumps(e_user(
                0, "sessão base p/ semeadura fora-de-escopo", "u1"),
                ensure_ascii=False) + "\n")
            for linha in linhas:
                fh.write(linha + "\n")
        tabela = recall_seeded(work.parent, manifesto, host="seed")
        fl = tabela["resposta-curta-seguida-de-acao"][
            "frase-longa-de-aceite"]
        self.assertIn("fora_do_escopo_por_construcao", fl)
        self.assertNotIn(
            "fora_do_escopo_por_construcao",
            tabela["resposta-curta-seguida-de-acao"][
                "aceite-7-15-chars-ineditos"])


class TestR61Tuning(Base):
    """Front A (v2.1-proposta) — mudanças guiadas pela medição de recall."""

    def test_cd_e_wrapper_neutro(self):
        from tools.atividades import classificar_comando as cc
        self.assertEqual(cc("cd /home/x/proj && tail -2 run.log"), "leitura")
        self.assertEqual(cc("cd /home/x && py_compile a.py"), "execucao")
        self.assertEqual(cc("cd /home/x"), "execucao")  # só cd: nada a ler

    def test_heredoc_python_por_payload(self):
        from tools.atividades import classificar_comando as cc
        ler = ("python3 - <<'PY'\nimport json\n"
               "d=json.load(open('/tmp/x.json'))\nprint(d['a'])\nPY")
        escrever_ = ("python3 - <<'PY'\nimport json\n"
                     "json.dump({}, open('/tmp/x.json','w'))\nPY")
        self.assertEqual(cc(ler), "leitura")
        self.assertEqual(cc(escrever_), "escrita")

    def test_d1_lexicon_e_imperativo_e_execucao(self):
        work = self.tmp / "w1"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "prepara os disparos de hoje", "u1"),
            e_assistant_text(10, "Pronto:\n" + "x" * 900, "a0"),
            e_user(100, "blz manda", "u2"),               # lexicon (9 chars)
            e_tool(115, "Bash", {"command": "python3 run.py"}, "t1", "a1"),
            e_user(700, "dispara o 1", "u3"),             # lexicon/imperativo
            e_tool(724, "Bash", {"command": "python3 seq_driver.py 1"},
                   "t2", "a2"),
            e_user(1400, "acho que pode ser", "u4"),      # NÃO qualifica
            e_tool(1415, "Write", {"file_path": "/x", "content": "y"},
                   "t3", "a3"),
        ])
        reg, _ = pipeline(work, "hostX")
        d1 = [r for r in reg.nivel(2)
              if r["forma"] == "resposta-curta-seguida-de-acao"]
        self.assertEqual(len(d1), 2)
        gatilhos = {r["params"]["gatilho"] for r in d1}
        self.assertTrue(gatilhos <= {"lexicon", "imperativo"})
        self.assertEqual({r["params"]["classe_acao"] for r in d1},
                         {"execucao"})

    def test_d3_mesmo_alvo_nao_mesma_flag(self):
        from tools.atividades import _chave_leitura
        self.assertEqual(_chave_leitura("tail -c 100 /tmp/f.log"),
                         ("tail", "/tmp/f.log"))
        self.assertEqual(_chave_leitura("cd /x && grep -n pat art.tex"),
                         ("grep", "art.tex"))
        work = self.tmp / "w2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "monitorando o arquivo de saída", "u1"),
            e_tool(60, "Bash", {"command": "tail -c 100 /tmp/f.log"},
                   "t1", "a1"),
            e_tool(120, "Bash", {"command": "tail -n 5 /tmp/f.log"},
                   "t2", "a2"),
            e_tool(180, "Bash", {"command": "cd /tmp && tail /tmp/f.log"},
                   "t3", "a3"),
            # alvos DISTINTOS não agrupam
            e_tool(300, "Bash", {"command": "cat /tmp/a.txt"}, "t4", "a4"),
            e_tool(360, "Bash", {"command": "cat /tmp/b.txt"}, "t5", "a5"),
            e_tool(420, "Bash", {"command": "cat /tmp/c.txt"}, "t6", "a6"),
        ])
        reg, _ = pipeline(work, "hostX")
        d3 = [r for r in reg.nivel(2)
              if r["forma"] == "leituras-repetidas-de-estado-externo"]
        self.assertEqual(len(d3), 1)
        self.assertEqual(d3[0]["params"]["n_repeticoes"], 3)
        self.assertEqual(d3[0]["params"]["alvo"], "/tmp/f.log")

    def test_d2_resposta_do_lexicon(self):
        work = self.tmp / "w3"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "como fica a estrutura da seção quatro?", "u1"),
            e_assistant_text(30, "Explicação:\n" + "y" * 900, "a1"),
            e_user(90, "blz perfeito", "u2"),
        ])
        reg, _ = pipeline(work, "hostX")
        d2 = [r for r in reg.nivel(2)
              if r["forma"] == "pergunta-explicacao-resposta-curta"]
        self.assertEqual(len(d2), 0)  # "blz perfeito" NÃO está no lexicon
        work2 = self.tmp / "w3b"
        escrever(work2 / "proj" / f"{SID}.jsonl", [
            e_user(0, "como fica a estrutura da seção quatro?", "u1"),
            e_assistant_text(30, "Explicação:\n" + "y" * 900, "a1"),
            e_user(90, "blz manda", "u2"),
        ])
        reg2, _ = pipeline(work2, "hostX")
        d2b = [r for r in reg2.nivel(2)
               if r["forma"] == "pergunta-explicacao-resposta-curta"]
        self.assertEqual(len(d2b), 1)


class TestR61Positivas(Base):
    """Front B — catálogo positivo (v2.1)."""

    def test_resposta_longa_em_voz_propria(self):
        work = self.tmp / "w1"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "me explica a projeção ortogonal de novo?", "u1"),
            e_assistant_text(30, "Explicação:\n" + "e" * 900, "a1"),
            e_user(400, "então deixa eu tentar dizer com as minhas "
                        "palavras: " + "a projeção pega o vetor e joga no "
                        "subespaço mais próximo, o resto é o erro ortogonal "
                        "que não tem componente ali; " * 3, "u2"),
        ])
        reg, _ = pipeline(work, "hostX")
        p1 = [r for r in reg.nivel(2)
              if r["forma"] == "resposta-longa-nao-interrogativa-apos-explicacao"]
        self.assertEqual(len(p1), 1)
        self.assertGreaterEqual(p1[0]["params"]["chars_resposta"], 300)

    def test_pergunta_de_aprofundamento(self):
        work = self.tmp / "w2"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "resume a seção de related work pra mim", "u1"),
            e_assistant_text(30, "Resumo:\n" + "r" * 900, "a1"),
            e_user(300, "e como isso se compara com o baseline geométrico "
                        "que a gente usou no capítulo dois?", "u2"),
        ])
        reg, _ = pipeline(work, "hostX")
        p2 = [r for r in reg.nivel(2)
              if r["forma"] == "pergunta-longa-apos-explicacao"]
        self.assertEqual(len(p2), 1)

    def test_retomada_de_entrega_com_vocabulario(self):
        work = self.tmp / "w3"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha a entrega do experimento de ranking", "u1"),
            e_assistant_text(
                30, "Entrega pronta. Duas perguntas de autoteste: qual "
                    "baseline geometrico venceu no ranking parcial? como o "
                    "subespaco de calibracao muda o resultado?", "a1"),
            e_user(600, "sobre o autoteste: o baseline geometrico venceu "
                        "porque o subespaco estava mal calibrado no treino "
                        "da rodada anterior", "u2"),
        ])
        reg, _ = pipeline(work, "hostX")
        p3 = [r for r in reg.nivel(2)
              if r["forma"] ==
              "turno-com-tokens-em-comum-com-a-entrega"]
        self.assertEqual(len(p3), 1)
        self.assertGreaterEqual(p3[0]["params"]["tokens_compartilhados"], 3)

    def test_zeros_honestos_sem_material(self):
        work = self.tmp / "w4"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "sessão curta sem explicações longas", "u1"),
            e_assistant_text(10, "ok", "a1"),
        ])
        reg, proj = pipeline(work, "hostX")
        for f in ("resposta-longa-nao-interrogativa-apos-explicacao",
                  "pergunta-longa-apos-explicacao",
                  "turno-com-tokens-em-comum-com-a-entrega"):
            self.assertIn(f, proj["formas_sem_instancias"])


class TestR62(Base):
    """R6.2 — um teste por MUST."""

    def test_f1_controle_semeado_sem_gabarito(self):
        from tools.atividades import _linhas_semente, D1_ACEITE_LEX
        _linhas, manifesto = _linhas_semente(9, 3000000000.0)
        self.assertIn("aceite-7-15-chars-ineditos",
                      manifesto["resposta-curta-seguida-de-acao"])
        # invariante: nenhuma string semeada de aceite está no lexicon
        for txt in ("combinado", "ta valendo", "de acordo"):
            self.assertNotIn(txt, D1_ACEITE_LEX)

    def test_f2_recibo_versionado_nunca_sobrescrito(self):
        from tools.atividades import gravar_recibo
        state = self.tmp / "st"
        state.mkdir()
        p1 = gravar_recibo(state, "pre-registro", {"x": 1})
        p2 = gravar_recibo(state, "pre-registro", {"x": 2})
        self.assertNotEqual(p1, p2)
        self.assertTrue(p1.exists() and p2.exists())
        self.assertEqual(json.loads(p1.read_text())["x"], 1)  # imutável
        self.assertEqual(json.loads(
            (state / "pre-registro.json").read_text())["x"], 2)  # ponteiro

    def _entrega(self, work, turno, t_turno=600):
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha a entrega do experimento de ranking", "u1"),
            e_assistant_text(
                30, "Entrega pronta. Duas perguntas de autoteste: qual "
                    "baseline geometrico venceu no ranking parcial? como o "
                    "subespaco de calibracao muda o resultado?", "a1"),
            e_user(t_turno, turno, "u2"),
        ])
        reg, _ = pipeline(work, "hostX")
        return [r for r in reg.nivel(2)
                if r["forma"] == "turno-com-tokens-em-comum-com-a-entrega"]

    def test_f4_probes_do_adversarial_nao_disparam(self):
        probes = [
            # reclamação citando a entrega
            "cara, ficou muito ruim essa entrega do baseline geometrico "
            "do ranking, refaz tudo",
            # papagaio de jargão (zero tokens próprios)
            "baseline geometrico subespaco calibracao ranking",
            # descarte em português genérico
            "pode apagar isso tudo depois, nao presta",
            # o probe literal
            "apaga o corpus... lixo.",
        ]
        for k, probe in enumerate(probes):
            work = self.tmp / f"p{k}"
            self.assertEqual(self._entrega(work, probe), [], probe)

    def test_f4_retomada_genuina_ainda_dispara(self):
        work = self.tmp / "gen"
        p3 = self._entrega(
            work, "sobre o autoteste: o baseline geometrico venceu porque "
                  "o subespaco estava mal calibrado no treino da rodada "
                  "anterior")
        self.assertEqual(len(p3), 1)
        self.assertGreaterEqual(p3[0]["params"]["razao_overlap"], 0.5)
        self.assertGreaterEqual(p3[0]["params"]["tokens_proprios"], 2)

    def test_f5_taxas_de_conversao_na_projecao(self):
        work = self.tmp / "tx"
        self._entrega(work, "ok")  # gera corpus qualquer
        _, proj = pipeline(work, "hostX")
        tx = proj["taxas_de_conversao"]["por_forma"]
        self.assertIn("turno-com-tokens-em-comum-com-a-entrega", tx)
        v = tx["turno-com-tokens-em-comum-com-a-entrega"]
        self.assertEqual(v["oportunidades_do_gate"], 1)
        self.assertEqual(v["disparos"], 0)

    def test_f6_sessao_em_curso_declarada(self):
        work = self.tmp / "sc"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "sessão viva sendo analisada agora", "u1"),
            e_assistant_text(10, "ok", "a1"),
        ])
        reg, proj = pipeline(work, "hostX", sessao_em_curso=SID)
        sc = proj["cobertura"]["sessao_em_curso"]
        self.assertEqual(sc["session_id"], SID)
        self.assertIn("PARCIAIS", sc["nota"])
        html = render_report(reg, proj)
        self.assertIn("valores PARCIAIS", html)

    def test_f7_dispare_por_verbo_nao_por_argumento(self):
        from tools.atividades import (_gatilho_aceite, D1_ACEITE_LEX,
                                      THRESHOLDS)
        p = THRESHOLDS["resposta-curta-seguida-de-acao"]
        self.assertNotIn("dispara o 1", D1_ACEITE_LEX)
        self.assertEqual(_gatilho_aceite("dispare o 1", p), "imperativo")
        self.assertEqual(_gatilho_aceite("dispara o 7", p), "imperativo")

    def test_f8_recusa_nunca_e_aceite(self):
        work = self.tmp / "rec"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "prepara a limpeza do diretório", "u1"),
            e_assistant_text(30, "Proposta:\n" + "z" * 900, "a1"),
            e_user(100, "nao", "u2"),
            e_tool(110, "Write", {"file_path": "/x", "content": "y"},
                   "t1", "a2"),
        ])
        reg, _ = pipeline(work, "hostX")
        d1 = [r for r in reg.nivel(2)
              if r["forma"] == "resposta-curta-seguida-de-acao"]
        # "prepara…" (imperativo) pode disparar; "nao" NUNCA
        for r in d1:
            voz = reg.by_id[r["instancias"][0]]
            self.assertNotEqual(voz["conteudo_redigido"]["texto"], "nao")


class TestCwdModal(Base):
    def test_cwd_e_o_modal_nao_o_ultimo(self):
        """Finding R1 #18: sessão que muda de diretório fica com o cwd MODAL."""
        work = self.tmp / "work"
        entradas = [
            e_user(0, "trabalhando no projeto principal hoje", "u1"),
            e_user(60, "seguindo aqui no mesmo lugar", "u2"),
            e_user(120, "continua no principal ainda sim", "u3"),
        ]
        entradas.append(dict(e_user(180, "um pulo rápido em outro dir", "u4"),
                             cwd="/home/x/outro"))
        caminho = escrever(work / "proj" / f"{SID}.jsonl", entradas)
        s = scan_arquivo(caminho, "hostX")
        self.assertEqual(s["cwd"], "/home/x/proj")


if __name__ == "__main__":
    unittest.main()

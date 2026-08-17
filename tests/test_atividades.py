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
    derivar_agencia, eval_ingerir, fold_padroes, montar_cobertura, pipeline,
    persistir, redigir, render_report, scan_arquivo, tempo_ativo_s,
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
    def test_autorizado_por_voz_nao_interrogativa(self):
        ag = derivar_agencia(100.0, False, [(90.0, "faz o commit")])
        self.assertEqual(ag["executor"], "agente")
        self.assertEqual(ag["autorizacao"], "autorizado")

    def test_pergunta_nao_autoriza(self):
        ag = derivar_agencia(100.0, False, [(90.0, "pode commitar?")])
        self.assertEqual(ag["autorizacao"], "desconhecido")

    def test_sem_sinal_vira_desconhecido_nunca_chutado(self):
        ag = derivar_agencia(500.0, False, [(90.0, "faz o commit")])
        self.assertEqual(ag["autorizacao"], "desconhecido")
        ag2 = derivar_agencia(100.0, False, [])
        self.assertEqual(ag2["autorizacao"], "desconhecido")

    def test_sidechain_autonomo(self):
        ag = derivar_agencia(100.0, True, [(99.0, "vai")])
        self.assertEqual(ag["autorizacao"], "autonomo")


class TestRegressao17s(Base):
    """O caso 17s como fixture SINTÉTICA: a regra GENÉRICA
    resposta-curta-seguida-de-acao deve achá-lo (regressão, não validade)."""

    def test_detector_generico_acha_a_sequencia(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "publica o parágrafo com o gancho formal", "u1"),
            e_assistant_text(30, "Parágrafo pronto:\n" + "x" * 900, "a1"),
            e_user(1552, "ok", "u2"),                       # voz curta
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
            e_user(10, "não ocorreu?", "u1"),
            e_user(20, "não ocorreu?", "u2"),
            e_user(30, "não ocorreu?", "u3"),
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
        amostra = eval_preparar(reg, work)
        formas = {i["forma"] for i in amostra["itens"]}
        self.assertGreaterEqual(len(formas), 2)
        for i in amostra["itens"]:
            self.assertTrue(i["descricao_mecanica"])
            self.assertTrue(i["evidencia"])

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

    def test_com_completer_gera_n3_e_n4(self):
        work = self.tmp / "work"
        escrever(work / "proj" / f"{SID}.jsonl", [
            e_user(0, "fecha o texto do resumo agora", "u1"),
            e_user(100, "ok", "u2"),
            e_tool(110, "Write", {"file_path": "/x.md", "content": "y"},
                   "t1", "a1"),
        ])

        def fake_complete(prompt):
            if "hipóteses de mentoria" in prompt:
                return ('{"hipotese": "Você revisa antes do ok?", '
                        '"falsificacao": "um relato de revisão prévia"}')
            if "Nomeie" in prompt:
                return "Fechamento do resumo"
            return ('{"claim": "sequência compatível com aceite rápido", '
                    '"confianca": 0.6, "alternativas": ["revisão prévia em '
                    'outra superfície"]}')

        reg, proj = pipeline(work, "hostX", complete_fn=fake_complete)
        self.assertGreaterEqual(len(reg.nivel(3)), 1)
        self.assertGreaterEqual(len(reg.nivel(4)), 1)
        n3 = reg.nivel(3)[0]
        self.assertTrue(n3["alternativas"])
        html = render_report(reg, proj)
        self.assertIn("Você revisa antes do ok?", html)


if __name__ == "__main__":
    unittest.main()

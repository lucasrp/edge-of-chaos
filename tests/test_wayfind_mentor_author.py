"""O wayfind autorado por `mentor` tem que FOLDAR — escrita e leitura falam o mesmo vocabulário.

Renomeação do operador em 2026-07-13: a palavra de superfície é **mentor**, não `grill`. Ela foi
aplicada no escritor (`_wayfinder_curation`) e no leitor de tickets (`_foldable_ticket_open`), e
esquecida no leitor de mapas (`_foldable_map_open`). O efeito não era um erro: era silêncio. O mapa
era ESCRITO com sucesso, o `grill_gate` o aceitava (ele conta `map.opened` por TIPO), e a lente
nunca o via — levando junto todos os seus tickets, porque ticket não folda sem resolver o mapa pai.
O mentorado recebia um close que dizia "mapeado" e um portfólio vazio.

Sobreviveu um mês porque a suíte inteira fala o vocabulário PRÉ-renomeação: das 44 chamadas de
`open_map`/`open_ticket` nos testes, 100% usavam `grill` ou `operador`, e nenhum teste em todo o
repositório usava `author="mentor"`. Uma renomeação de vocabulário só está feita quando um teste
exercita o nome NOVO ponta a ponta.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402


class WayfindAcceptsMentorAuthor(unittest.TestCase):
    def _fold_kinds(self, log):
        entities = eventlog._lens_entities(eventlog.read(log=log))
        kinds = {}
        for entity in entities:
            kinds.setdefault(entity["kind"], []).append(entity)
        return kinds

    def test_mentor_authored_map_and_ticket_fold_end_to_end(self):
        for author in ("operador", "grill", "mentor"):
            with self.subTest(author=author), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log.jsonl"
                opened = eventlog.open_map(
                    operacao="edge", titulo="Mapa do wayfind",
                    rationale="O mentor mapeia o que entendeu", dispatch_id="d1",
                    author=author, log=log,
                )
                ref = f"edge/{opened['payload']['num']}"
                eventlog.open_ticket(
                    map=ref, titulo="Buraco declarado", question="O que ainda não sei?",
                    rationale="Vira inscrição, não silêncio", dispatch_id="d1",
                    author=author, log=log,
                )

                kinds = self._fold_kinds(log)
                self.assertEqual(len(kinds.get("map", [])), 1,
                                 f"mapa autorado por {author!r} não foldou — escrita aceita, "
                                 "leitura descarta em silêncio")
                self.assertEqual(len(kinds.get("ticket", [])), 1,
                                 f"ticket de mapa autorado por {author!r} não foldou — um ticket "
                                 "não resolve sem o mapa pai, então o mapa invisível leva os "
                                 "tickets junto")

    def test_map_state_resolves_a_mentor_authored_map(self):
        """set_map_state resolve pela lente: mapa que não folda é mapa que não se pode mover."""
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            opened = eventlog.open_map(
                operacao="edge", titulo="Mapa do wayfind", rationale="mapear",
                dispatch_id="d1", author="mentor", log=log,
            )
            event = eventlog.set_map_state(
                ref=f"edge/{opened['payload']['num']}", estado="ativado",
                rationale="ratificado na leitura de volta", dispatch_id="d1",
                author="mentor", log=log,
            )
            self.assertEqual(event["payload"]["estado"], "ativado")

    def test_write_and_fold_agree_on_the_author_vocabulary(self):
        """A regra estrutural: o escritor não pode aceitar um autor que o leitor descarta.

        Sem isto, qualquer renomeação futura repete o mesmo silêncio — grava e some.
        """
        for author in ("operador", "grill", "mentor"):
            with self.subTest(author=author):
                accepted_by_writer = True
                try:
                    eventlog._wayfinder_curation("r", "d1", author, tier="asserted")
                except ValueError:
                    accepted_by_writer = False
                payload = {
                    "ulid": "01M0000000000000000000000A", "num": "map-001", "operacao": "edge",
                    "titulo": "t", "rationale": "r", "dispatch_id": "d1",
                    "tier": "asserted", "author": author, "thread": None,
                }
                self.assertEqual(
                    accepted_by_writer, eventlog._foldable_map_open(payload),
                    f"escrita e fold discordam sobre author={author!r} — o modo de falha é "
                    "silencioso: o evento é gravado e nunca mais é visto")


if __name__ == "__main__":
    unittest.main()

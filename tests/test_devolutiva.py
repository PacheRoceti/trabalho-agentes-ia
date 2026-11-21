"""Testes OFFLINE das duas correções que a devolutiva da Parte 2 apontou (docs/mudancas.md §1).

- 5d, o detector de laço: o nó que repete um passo da trajetória (mesmo nó, mesmos argumentos, mesmo
  resultado) encerra a execução em `erro_fatal`, e nada executa depois dele (src/grafo.py, fim do arquivo);
- 4b, a memória episódica por semelhança: a tela do H1 traz os episódios de outro guia parecidos com
  o caso atual, por embedding (src/vetorial.py, fim do arquivo). Embedder de mentira: sem chave, sem rede.

    python -m unittest tests.test_devolutiva -v
"""
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CHECKPOINT_DB"] = ":memory:"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db                                    # noqa: E402
import grafo                                 # noqa: E402
import vetorial                              # noqa: E402
from agente import Termino                   # noqa: E402
from test_grafo import NAO_CAI, ROTEIROS, SIM, UPLOAD, ModeloRoteirizado, texto, triagem  # noqa: E402


def vetor_do_caso(t: str) -> list[float]:
    """O "embedding" de mentira: o eixo do guia citado na descrição do caso. Permissão (KB-102) e FTP
    (KB-114) ficam perto (cosseno 0,95); DNS (KB-106) fica longe dos dois."""
    if "Permissão negada" in t:
        return [1.0, 0.0, 0.0]
    if "Login por FTP" in t:
        return [0.95, 0.312, 0.0]
    return [0.0, 0.0, 1.0]


class TestDetectorDeLaco(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()
        self._busca, grafo.BUSCA = grafo.BUSCA, "palavra"

    def tearDown(self):
        grafo.BUSCA = self._busca
        self.con.close()

    def rodar(self, ticket, roteiro, **kw):
        return grafo.rodar_grafo(ticket, client=ModeloRoteirizado(roteiro), modelo="fake", con=self.con,
                                 verbose=False, confirmador=kw.pop("confirmador", SIM), **kw)

    def test_a_mesma_redacao_repetida_e_laco_e_termina_sem_gravar(self):
        # o texto curto é recusado; o modelo devolve o MESMO texto: repetir sem mudar nada é laço
        e = self.rodar("TKT-0004", [triagem("comercial"), texto("Upgrade.")])
        self.assertEqual(e.termino, Termino.ERRO_FATAL)
        self.assertTrue(e.motivo.startswith(grafo.MOTIVO_LACO), e.motivo)
        self.assertIn("redigir", e.motivo)
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0004"), 0)
        # pego na segunda redação, antes de a segunda ser julgada: uma recusa só
        self.assertEqual([p.ferramenta for p in e.passos].count("redigir"), 2)
        self.assertEqual(len([p for p in e.passos if p.ferramenta == "validar" and p.erro]), 1)

    def test_o_caminho_normal_nao_dispara_o_detector(self):
        for ticket in ("TKT-0001", "TKT-0002", "TKT-0004", "TKT-0007", "TKT-0999"):
            with self.subTest(ticket=ticket):
                db.recriar_banco()
                e = self.rodar(ticket, ROTEIROS[ticket])
                self.assertEqual(e.termino, Termino.RESPONDEU, e.motivo)

    def test_passo_repetido_ignora_indice_e_tempo_e_o_validar(self):
        antes = {"passos": [{"indice": 0, "ferramenta": "consultar_ticket", "argumentos": {"id_ticket": "X"},
                             "resultado": {"a": 1}, "erro": None, "ms": 5},
                            {"indice": 1, "ferramenta": "validar", "argumentos": {"desfecho": "y"},
                             "resultado": None, "erro": {"erro": "curto"}, "ms": 0}]}
        igual = {"indice": 7, "ferramenta": "consultar_ticket", "argumentos": {"id_ticket": "X"},
                 "resultado": {"a": 1}, "erro": None, "ms": 99}
        outro = {**igual, "resultado": {"a": 2}}
        mesma_recusa = {**antes["passos"][1], "indice": 8}
        self.assertIsNotNone(grafo.passo_repetido(antes, {"passos": [igual]}))
        self.assertIsNone(grafo.passo_repetido(antes, {"passos": [outro]}))
        self.assertIsNone(grafo.passo_repetido(antes, {"passos": [mesma_recusa]}))

    def test_depois_do_laco_nenhum_no_executa_alem_do_finalizar(self):
        def gravar(state, ctx):
            raise AssertionError("o gravar não pode rodar depois de um laço")
        estado = {"motivo": f"{grafo.MOTIVO_LACO}: teste", "passos": []}
        self.assertEqual(grafo._rodar_no(gravar, estado, None), {})


class TestEpisodicaPorSemelhanca(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()
        self._busca, grafo.BUSCA = grafo.BUSCA, "palavra"
        self.chamadas = []

        def embedder(textos):
            self.chamadas.append(list(textos))
            return [vetor_do_caso(t) for t in textos]
        vetorial.EMBEDDER = embedder

    def tearDown(self):
        vetorial.EMBEDDER = None
        grafo.BUSCA = self._busca
        self.con.close()

    def episodio(self, ticket, kb_id, dias=1, cliente="CLI-99", veredito="rejeitado"):
        artigo = db.buscar_artigo(self.con, kb_id)
        quando = (datetime.now().astimezone() - timedelta(days=dias)).isoformat(timespec="seconds")
        db.registrar_episodio(self.con, {
            "ticket_externo": ticket, "cliente_id": cliente, "classe": "tecnico",
            "categoria": artigo["categoria"], "kb_id": kb_id, "score": 0.7,
            "acao_proposta": "abrir_chamado_interno", "desfecho": "fila_humana", "veredito": veredito,
            "termino": "respondeu", "resumo": f"{ticket}: teste", "criado_em": quando})

    def parecidos(self, kb_id="KB-102", cliente="CLI-01"):
        return vetorial.precedentes_parecidos(self.con, "tecnico", db.buscar_artigo(self.con, kb_id),
                                              "abrir_chamado_interno", cliente)

    def test_lembra_o_caso_parecido_de_outro_guia_e_outro_cliente(self):
        self.episodio("TKT-9001", "KB-114")              # FTP: parecido com permissão
        self.episodio("TKT-9002", "KB-106")              # DNS: não parecido
        self.episodio("TKT-9003", "KB-102")              # o mesmo guia: já está na contagem exata
        achados = self.parecidos()
        self.assertEqual([p["ticket"] for p in achados], ["TKT-9001"])
        self.assertGreaterEqual(achados[0]["cosseno"], vetorial.LIMIAR_PARECIDO)
        self.assertIn("parecido", achados[0]["por"])

    def test_respeita_o_decaimento_e_guarda_o_vetor_do_episodio(self):
        self.episodio("TKT-9001", "KB-114", dias=100)    # antigo: aparece marcado
        self.episodio("TKT-9004", "KB-114", dias=400)    # passou de 365 dias: não é lido
        achados = self.parecidos()
        self.assertEqual([(p["ticket"], p["antigo"]) for p in achados], [("TKT-9001", True)])
        self.parecidos()                                 # de novo: só o caso atual vai ao embedding
        self.assertEqual(len(self.chamadas[-1]), 1)

    def test_a_tela_do_h1_traz_os_parecidos_e_o_texto_do_cliente_nao_vai_ao_embedding(self):
        self.episodio("TKT-9001", "KB-114")
        e = grafo.rodar_grafo("TKT-0007", client=ModeloRoteirizado(ROTEIROS["TKT-0007"]), modelo="fake",
                              con=self.con, verbose=False, confirmador=None)
        self.assertEqual(e.termino, Termino.HUMANO)
        self.assertEqual([p["ticket"] for p in e.pendencia["precedentes"]["parecidos"]], ["TKT-9001"])
        relato = self.con.execute("SELECT texto FROM tickets_externos WHERE id = 'TKT-0007'").fetchone()[0]
        self.assertFalse(any(relato in t for chamada in self.chamadas for t in chamada))

    def test_sem_embedding_a_tela_vai_sem_os_parecidos_e_diz_por_que(self):
        self.episodio("TKT-9001", "KB-114")

        def falha(textos):
            raise ConnectionError("fora do ar")
        for embedder, motivo in ((falha, "embedding indisponível"), (None, "busca por palavra")):
            with self.subTest(motivo=motivo):
                db.recriar_banco()
                self.episodio("TKT-9001", "KB-114")
                vetorial.EMBEDDER = embedder
                e = grafo.rodar_grafo("TKT-0007", client=ModeloRoteirizado(ROTEIROS["TKT-0007"]),
                                      modelo="fake", con=self.con, verbose=False, confirmador=None)
                self.assertEqual(e.termino, Termino.HUMANO)        # a pausa acontece mesmo assim
                memoria = e.pendencia["precedentes"]
                self.assertIsNone(memoria["parecidos"])
                self.assertIn(motivo, memoria["parecidos_motivo"])


if __name__ == "__main__":
    unittest.main()

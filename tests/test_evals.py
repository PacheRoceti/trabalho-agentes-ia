"""Testes OFFLINE da suíte de avaliação (evals/): sem chave e sem rede.

Provam o que é da suíte: o dataset confere com o gabarito e o seed e tem a composição que o
enunciado pede, cada checagem reprova o que deve reprovar, e a rodada inteira roda o sistema pelo
`main.executar` e grava o resultado. NÃO provam o número de uma rodada real: só
`python -m evals.rodar` mede.

    python -m unittest tests.test_evals -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["CHECKPOINT_DB"] = ":memory:"     # antes de importar o grafo: nada de arquivo nos testes
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))      # para importar o modelo roteirizado de test_grafo

import db                                    # noqa: E402
import grafo as grafo_mod                    # noqa: E402
from evals import checagens                  # noqa: E402
from evals.comparar import _medidas          # noqa: E402
from evals.rodar import carregar_dataset, conferir_dataset, resumir, rodar_rodada  # noqa: E402
from test_grafo import ROTEIROS, ModeloRoteirizado, triagem, texto  # noqa: E402


def passo(ferramenta, **argumentos):
    return {"ferramenta": ferramenta, "argumentos": argumentos, "resultado": {}, "erro": None}


class TestDataset(unittest.TestCase):
    def setUp(self):
        self.dataset, _ = carregar_dataset()
        self.casos = self.dataset["casos"]

    def test_confere_com_o_gabarito_e_o_seed(self):
        db.recriar_banco()
        con = db.conectar()
        try:
            self.assertEqual(conferir_dataset(self.dataset, con), [])
        finally:
            con.close()

    def test_conferencia_acusa_o_esperado_que_divergiu(self):
        db.recriar_banco()
        con = db.conectar()
        try:
            alterado = json.loads(json.dumps(self.dataset))
            alterado["casos"][0]["esperado"]["acao"] = "fila_humana"
            self.assertEqual(len(conferir_dataset(alterado, con)), 1)
        finally:
            con.close()

    def test_composicao_que_o_enunciado_pede(self):
        self.assertGreaterEqual(len(self.casos), 20)
        for c in self.casos:
            with self.subTest(caso=c["id"]):
                self.assertIn(c["origem"], {"producao", "desenvolvimento", "sintetico"})
                self.assertIn(c["classe"], self.dataset["classes"])
                self.assertTrue(c["por_que_existe"].strip())
                if c["origem"] == "sintetico":
                    self.assertTrue(c.get("revisado_por"))
        por_classe = {}
        for c in self.casos:
            por_classe[c["classe"]] = por_classe.get(c["classe"], 0) + 1
        self.assertGreaterEqual(sum(1 for n in por_classe.values() if n > 1), 3)
        # recusa: id inexistente, sem procedimento na base e fora da alçada vão à fila humana
        recusas = {c["id"] for c in self.casos if c["esperado"]["acao"] == "fila_humana"}
        self.assertTrue({"TKT-0999", "TKT-0119", "TKT-0120"} <= recusas)

    def test_os_seis_casos_da_parte_2_estao_no_dataset(self):
        demonstrados = sorted(c.get("parte2_caso") for c in self.casos if c.get("parte2_caso"))
        self.assertEqual(demonstrados, [1, 2, 3, 4, 5, 6])


class TestChecagens(unittest.TestCase):
    def nomes_que_falham(self, lista):
        return {c["propriedade"] for c in lista if not c["ok"]}

    def test_trajetoria_certa_passa(self):
        log = {"passos": [passo("consultar_ticket", id_ticket="TKT-0001"), passo("triagem"),
                          passo("buscar_base_conhecimento", termos=["ssl"]), passo("decidir"),
                          passo("redigir", desfecho="anotacao_interna"),
                          passo("registrar_encaminhamento", destino="anotacao_interna")]}
        self.assertEqual(self.nomes_que_falham(checagens.de_trajetoria(log, {"chamado_interno": False})), set())

    def test_anotar_sem_buscar_antes_reprova(self):
        log = {"passos": [passo("consultar_ticket"), passo("decidir"),
                          passo("registrar_encaminhamento", destino="anotacao_interna")]}
        self.assertIn("buscou_antes_de_agir_com_guia",
                      self.nomes_que_falham(checagens.de_trajetoria(log, {"chamado_interno": False})))

    def test_tentativa_de_abrir_chamado_indevido_reprova_mesmo_com_erro(self):
        tentativa = passo("abrir_chamado_interno", kb_id="KB-104")
        tentativa["erro"] = "recusado pelo portão"
        log = {"passos": [passo("consultar_ticket"), passo("buscar_base_conhecimento"), tentativa]}
        self.assertIn("nao_tentou_abrir_chamado_indevido",
                      self.nomes_que_falham(checagens.de_trajetoria(log, {"chamado_interno": False})))
        # quando o chamado é o esperado, a mesma trajetória não reprova por isso
        self.assertNotIn("nao_tentou_abrir_chamado_indevido",
                         self.nomes_que_falham(checagens.de_trajetoria(log, {"chamado_interno": True})))

    def test_ferramenta_repetida_reprova_e_no_de_modelo_repetido_nao(self):
        log = {"passos": [passo("consultar_ticket"), passo("triagem"), passo("triagem"),
                          passo("buscar_base_conhecimento", termos=["x"]),
                          passo("buscar_base_conhecimento", termos=["x"])]}
        falhas = self.nomes_que_falham(checagens.de_trajetoria(log, {"chamado_interno": False}))
        self.assertIn("sem_ferramenta_repetida", falhas)
        log["passos"].pop()
        self.assertNotIn("sem_ferramenta_repetida",
                         self.nomes_que_falham(checagens.de_trajetoria(log, {"chamado_interno": False})))

    def test_saida_fora_do_schema_reprova(self):
        falhas = self.nomes_que_falham(checagens.deterministicas({"saida": {"id_ticket": "x"},
                                                                   "termino": "respondeu"}))
        self.assertEqual(falhas, {"saida_valida_no_schema"})

    def test_mudanca_em_outro_chamado_e_detectada(self):
        db.recriar_banco()
        con = db.conectar()
        try:
            antes = checagens.foto_do_resto(con, "TKT-0007")
            con.execute("UPDATE chamados_internos SET prioridade = 'P1' WHERE id = 1")
            depois = checagens.foto_do_resto(con, "TKT-0007")
            log = {"termino": "respondeu", "motivo": None, "desfecho": {}}
            falhas = self.nomes_que_falham(checagens.de_resultado(log, "TKT-0004", con, antes, depois))
            self.assertIn("nada_mudou_fora_deste_chamado", falhas)
        finally:
            con.close()

    def test_resumo_conta_pass_k_e_pass_at_k(self):
        casos = [{"id": "X", "classe": "A"}, {"id": "Y", "classe": "A"}, {"id": "Z", "classe": "B"}]
        execucoes = [{"id": i, "passou": p, "checagens": []}
                     for i, p in (("X", True), ("X", True), ("Y", True), ("Y", False),
                                  ("Z", False), ("Z", False))]
        r = resumir(execucoes, casos)["por_classe"]
        self.assertEqual(r["A"], {"casos": 2, "passaram_todas": 1, "passaram_alguma": 2,
                                  "execucoes": 4, "execucoes_ok": 3})
        self.assertEqual(r["B"]["passaram_todas"], 0)
        taxas, media, geral = _medidas({"resumo": {"por_classe": r}})
        self.assertEqual(taxas, {"A": 50.0, "B": 0.0})
        self.assertEqual(media, 25.0)
        self.assertAlmostEqual(geral, 100 / 3)


class TestRodada(unittest.TestCase):
    """A rodada inteira, pelo main.executar, com o modelo roteirizado no lugar da API."""

    def setUp(self):
        self._busca, grafo_mod.BUSCA = grafo_mod.BUSCA, "palavra"
        self.pasta = tempfile.TemporaryDirectory()
        self.dataset, _ = carregar_dataset()

    def tearDown(self):
        grafo_mod.BUSCA = self._busca
        self.pasta.cleanup()

    def rodar(self, ids, roteiros, repeticoes=1):
        casos = [c for c in self.dataset["casos"] if c["id"] in ids]
        # um cliente só, como na rodada real: os roteiros em fila, na ordem dos casos e das repetições
        cliente = ModeloRoteirizado([t for _ in range(repeticoes) for c in casos for t in roteiros[c["id"]]])
        destino = Path(self.pasta.name) / "rodada"
        metadados = {"rodada": "teste", "versao": "0.0.0", "commit": None, "modelo": "fake",
                     "dataset": {"versao": self.dataset["versao"], "casos": len(casos), "origem": {},
                                 "classes": self.dataset["classes"]}, "repeticoes": repeticoes}
        return rodar_rodada(self.dataset, casos, repeticoes, destino, cliente, "fake", (0.0, 0.0),
                            metadados, avisar=lambda *_: None), destino

    def test_rodada_grava_resultado_e_logs_e_os_casos_passam(self):
        ids = ["TKT-0001", "TKT-0004"]
        r, destino = self.rodar(ids, ROTEIROS)
        self.assertTrue((destino / "resultado.json").exists())
        self.assertTrue((destino / "logs" / "rep-1" / "TKT-0001.json").exists())
        self.assertEqual([e["passou"] for e in r["execucoes"]], [True, True],
                         [c for e in r["execucoes"] for c in e["checagens"] if not c["ok"]])

    def test_desfecho_errado_reprova_no_nivel_de_resultado(self):
        # a triagem diz comercial num chamado técnico: grava fila_comercial no lugar da anotação
        r, _ = self.rodar(["TKT-0001"], {"TKT-0001": [triagem("comercial"), texto("Assunto comercial.")]})
        falhas = {c["propriedade"] for c in r["execucoes"][0]["checagens"] if not c["ok"]}
        self.assertIn("gravou_o_desfecho_do_gabarito", falhas)
        self.assertEqual(r["resumo"]["casos_que_falharam"], ["TKT-0001"])

    def test_limite_de_requisicoes_reexecuta_o_caso_e_registra(self):
        import main
        from evals import rodar as modulo_rodar
        original, esperas = main.executar, modulo_rodar.ESPERAS_429_S
        chamadas = []

        def executar_com_429_na_primeira(id_ticket, *a, **kw):
            chamadas.append(id_ticket)
            if len(chamadas) == 1:       # o que o sistema grava quando desiste do 429 (erro_fatal)
                log_dir = a[5]
                (log_dir / f"{id_ticket}.json").write_text(json.dumps(
                    {"termino": "erro_fatal", "motivo": "API indisponível após 5 tentativas: Error code: 429",
                     "passos": [], "saida": None}), encoding="utf-8")
                return None
            return original(id_ticket, *a, **kw)
        main.executar, modulo_rodar.ESPERAS_429_S = executar_com_429_na_primeira, (0,)
        try:
            r, _ = self.rodar(["TKT-0004"], ROTEIROS)
        finally:
            main.executar, modulo_rodar.ESPERAS_429_S = original, esperas
        self.assertEqual(chamadas, ["TKT-0004", "TKT-0004"])
        e = r["execucoes"][0]
        self.assertTrue(e["passou"])
        self.assertEqual((e["reexecucoes_429"], e["falha_de_infraestrutura"]), (1, False))
        self.assertEqual(r["resumo"]["reexecucoes_429"], 1)

    def test_rodada_que_ja_existe_nao_e_sobrescrita(self):
        self.rodar(["TKT-0004"], ROTEIROS)
        with self.assertRaises(FileExistsError):
            self.rodar(["TKT-0004"], ROTEIROS)


if __name__ == "__main__":
    unittest.main()

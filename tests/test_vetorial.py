"""Testes OFFLINE da busca vetorial e híbrida (src/vetorial.py): sem chave e sem rede, com um
embedder de mentira cujos vetores são escolhidos à mão.

Provam o que é do CÓDIGO: a escala do score, o índice (refeito só quando o texto muda), a curadoria
antes do ranking, a fusão por posição, a ressalva, o recuo para a busca por palavra e o grafo
usando tudo isso. NÃO provam que o `mistral-embed` põe o relato perto do guia certo: isso só
`python src/medir_rag.py` mede (docs/rag.md §4).

    python -m unittest discover -s tests -v
"""
import json
import math
import os
import sys
import unittest
from pathlib import Path

os.environ["CHECKPOINT_DB"] = ":memory:"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db                                    # noqa: E402
import grafo as grafo_mod                    # noqa: E402
import vetorial                              # noqa: E402
from grafo import rodar_grafo                # noqa: E402
from test_grafo import ROTEIROS, SIM, ModeloRoteirizado  # noqa: E402
from verificar import verificar              # noqa: E402

# Um eixo por guia; o relato é uma combinação de eixos, e o cosseno sai das contas.
EIXOS = ["KB-101", "KB-101-A", "KB-102", "KB-103", "KB-104", "KB-105", "KB-106", "KB-107", "KB-108",
         "KB-109", "KB-110", "KB-111", "KB-112", "KB-113", "KB-114", "KB-115",
         "PLANO-Start", "PLANO-Business", "PLANO-VPS"]
N_GUIAS, N_FICHAS = 16, 3


def vetor(**pesos):
    v = [pesos.get(k.replace("-", "_"), 0.0) for k in EIXOS]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class Embedder:
    """Guia -> o eixo dele (o texto do guia começa pelo título). Relato -> o vetor combinado."""

    def __init__(self, relatos, falha=None):
        self.relatos, self.falha, self.chamadas = relatos, falha, []

    def __call__(self, textos):
        self.chamadas.append(list(textos))
        if self.falha:
            raise self.falha
        return [self.relatos[t] if t in self.relatos else self._guia(t) for t in textos]

    @staticmethod
    def _guia(texto):
        titulos = {"Certificado SSL vencido": "KB_101", "Certificado SSL não renovou": "KB_101_A",
                   "Permissão negada": "KB_102", "Acesso SSH": "KB_103", "Site fora do ar": "KB_104",
                   "Backup diário": "KB_105", "Falha de resolução": "KB_106",
                   "Banco de dados recusando": "KB_107", "Disco ou cota": "KB_108",
                   "Tarefa agendada": "KB_109", "Site em laço": "KB_110", "Envio de e-mail": "KB_111",
                   "Bloqueio indevido": "KB_112", "Aplicação PHP": "KB_113", "Login por FTP": "KB_114",
                   "Servidor com CPU": "KB_115", "Hospedagem Start": "PLANO_Start",
                   "Hospedagem Business": "PLANO_Business", "VPS Pro": "PLANO_VPS"}
        eixo = next(e for t, e in titulos.items() if texto.startswith(t))
        return vetor(**{eixo: 1.0})


SSL = "O certificado SSL do meu site venceu."
SSH = "Recebo permissão negada quando tento entrar por SSH."
INTERMITENTE = "Meu site dá erro 502 de vez em quando."
RELATOS = {
    SSL: vetor(KB_101=0.62, KB_101_A=0.62, KB_104=0.1),      # as duas versões, igualmente perto
    SSH: vetor(KB_102=0.60, KB_103=0.55),                     # o guia de permissão vence no vetor
    INTERMITENTE: vetor(KB_104=0.9, KB_101_A=0.1),
    "fora do assunto": vetor(KB_102=0.3, KB_105=0.3, KB_106=0.3, KB_104=0.3),
}


class TestVetorial(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()
        self.emb = Embedder(RELATOS)
        vetorial.EMBEDDER = self.emb
        self.busca_anterior, grafo_mod.BUSCA = grafo_mod.BUSCA, "vetorial"

    def tearDown(self):
        vetorial.EMBEDDER = None
        grafo_mod.BUSCA = self.busca_anterior
        self.con.close()

    def buscar(self, relato, termos=("x",), **kw):
        return vetorial.buscar(self.con, list(termos), relato=relato, **kw)

    # ---- a escala

    def test_escala_o_limiar_do_cosseno_vale_o_limiar_do_portao(self):
        self.assertEqual(vetorial.escala(vetorial.LIMIAR_COSSENO), 0.5)
        self.assertEqual(vetorial.escala(1.0), 1.0)
        self.assertLess(vetorial.escala(0.799), 0.5)            # abaixo do limiar, mesmo que o arredondamento a levasse a 0,50
        self.assertEqual(vetorial.escala(0.6), 0.0)
        self.assertEqual(vetorial.escala(0.3), 0.0)             # não fica negativo
        self.assertLess(vetorial.escala(0.79), 0.5)             # logo abaixo do limiar, não age
        self.assertGreaterEqual(vetorial.escala(0.81), 0.5)

    # ---- o índice

    def test_indice_embeda_cada_guia_uma_vez_e_so_refaz_o_que_mudou(self):
        self.buscar("fora do assunto")
        self.assertEqual(len(self.emb.chamadas[0]), N_GUIAS + N_FICHAS)   # os guias (o revogado também) e as fichas
        self.assertEqual(self.emb.chamadas[1], ["fora do assunto"])   # e o relato
        self.buscar("fora do assunto")
        self.assertEqual(len(self.emb.chamadas), 3)              # 2a busca: só o relato
        self.con.execute("UPDATE kb_artigos SET solucao = 'nova solução' WHERE id = 'KB-105'")
        self.buscar("fora do assunto")
        self.assertEqual(len(self.emb.chamadas[3]), 1)           # só o guia que mudou

    def test_indice_guarda_na_tabela_e_sobrevive_a_outra_conexao(self):
        self.buscar("fora do assunto")
        con2 = db.conectar()
        n = con2.execute("SELECT COUNT(*) FROM kb_vetores").fetchone()[0]
        con2.close()
        self.assertEqual(n, N_GUIAS + N_FICHAS)

    # ---- a curadoria vale antes do ranking

    def test_o_vetorial_acha_as_duas_versoes_sem_curadoria(self):
        r = self.buscar(SSL, incluir_revogados=True, desempatar_por_data=False)
        ids = [x["kb_id"] for x in r]
        self.assertEqual(set(ids[:2]), {"KB-101", "KB-101-A"})
        self.assertEqual(r[0]["score"], r[1]["score"])           # nada diz qual vale

    def test_com_curadoria_so_a_versao_vigente_volta_e_o_descarte_fica_registrado(self):
        r = self.buscar(SSL, desempatar_por_data=False, incluir_revogados=False)
        self.assertNotIn("KB-101", [x["kb_id"] for x in r])      # o filtro de revogados
        self.con.execute("UPDATE kb_artigos SET revogado_por = NULL")
        # eixos ortogonais: duas versões não passam de 0,71 com o relato no meio. O limiar baixa
        # só aqui, para o descarte "também casava" valer
        antes, vetorial.LIMIAR_COSSENO = vetorial.LIMIAR_COSSENO, 0.65
        self.addCleanup(setattr, vetorial, "LIMIAR_COSSENO", antes)
        r = self.buscar(SSL)                                     # o desempate por data
        self.assertEqual(r[0]["kb_id"], "KB-101-A")
        self.assertNotIn("KB-101", [x["kb_id"] for x in r])
        self.assertEqual(r[0]["versoes_descartadas"], [{"kb_id": "KB-101", "data_publicacao": "2025-03-10"}])
        self.assertEqual(r[0]["data_publicacao"], "2026-02-02")

    # ---- a fusão

    def test_a_palavra_pode_virar_o_ranking_do_vetor(self):
        so_vetor = self.buscar(SSH, termos=["ssh", "fail2ban"], modo="vetorial")
        self.assertEqual(so_vetor[0]["kb_id"], "KB-102")         # o vetor põe permissão na frente
        hibrida = self.buscar(SSH, termos=["ssh", "fail2ban", "acesso"], modo="hibrida")
        self.assertEqual(hibrida[0]["kb_id"], "KB-103")          # a palavra empurra o guia de SSH
        self.assertEqual(hibrida[0]["busca"], "hibrida")

    def test_o_score_do_portao_e_o_do_vetor_mesmo_na_busca_hibrida(self):
        r = self.buscar(SSH, termos=["ssh", "fail2ban", "acesso"])
        self.assertAlmostEqual(r[0]["score"], vetorial.escala(r[0]["cosseno"]), delta=0.011)   # o campo cosseno tem 3 casas

    def test_modo_desconhecido_e_recusado(self):
        with self.assertRaises(ValueError):
            self.buscar(SSL, modo="outro")

    # ---- a ressalva (coluna nao_cobre) continua literal

    def test_ressalva_literal_reduz_o_score_no_vetorial_tambem(self):
        r = self.buscar(INTERMITENTE, termos=["502", "deploy"])
        kb104 = next(x for x in r if x["kb_id"] == "KB-104")
        self.assertIn("ressalva", kb104)
        self.assertLess(kb104["score"], 0.5)
        sem = self.buscar("Meu site dá erro 502 o tempo todo.", termos=["502"])    # fora do dicionário de relatos
        self.assertNotIn("ressalva", next((x for x in sem if x["kb_id"] == "KB-104"), {}))

    # ---- as fichas de plano

    def test_as_fichas_entram_no_indice_mas_nao_disputam_o_melhor_guia(self):
        r = self.buscar(SSL, incluir_revogados=True, desempatar_por_data=False, top=30)
        self.assertTrue(all(x["kb_id"].startswith("KB-") for x in r))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM kb_vetores WHERE kb_id LIKE 'PLANO:%'")
                         .fetchone()[0], N_FICHAS)

    def test_a_pergunta_sobre_um_plano_acha_a_ficha(self):
        RELATOS["o escopo do VPS"] = vetor(PLANO_VPS=0.9, PLANO_Start=0.2)
        f = vetorial.buscar_fichas(self.con, "o escopo do VPS", top=2)
        self.assertEqual([x["plano"] for x in f], ["VPS Pro", "Hospedagem Start"])

    # ---- o gasto de embedding vai para o log

    def test_os_tokens_de_embedding_vao_para_o_estado_e_para_o_log(self):
        def contando(textos):
            vetorial.TOKENS_EMBEDDING += 10 * len(textos)
            return self.emb(textos)
        vetorial.EMBEDDER = contando
        RELATOS["O certificado SSL do meu site venceu ontem e a renovação automática não rodou. "
                "O navegador mostra aviso de site não seguro para os meus clientes."] = vetor(KB_101_A=0.9)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            modelo = ModeloRoteirizado(ROTEIROS["TKT-0001"])
            rodar_grafo("TKT-0001", client=modelo, modelo="fake", con=self.con, verbose=False,
                        confirmador=SIM, log_dir=Path(d))
            gasto = json.loads((Path(d) / "TKT-0001.json").read_text(encoding="utf-8"))["tokens_embedding"]
            self.assertEqual(gasto, 10 * (N_GUIAS + N_FICHAS) + 10)    # a indexação (1ª busca) e o relato
            rodar_grafo("TKT-0004", client=ModeloRoteirizado(ROTEIROS["TKT-0004"]), modelo="fake",
                        con=self.con, verbose=False, confirmador=SIM, log_dir=Path(d))
            self.assertEqual(json.loads((Path(d) / "TKT-0004.json").read_text(encoding="utf-8"))
                             ["tokens_embedding"], 0)                  # comercial: não busca, não gasta

    # ---- o recuo

    def test_se_o_embedding_falha_a_busca_cai_para_a_de_palavras_e_diz_isso(self):
        vetorial.EMBEDDER = Embedder(RELATOS, falha=ConnectionError("sem rede"))
        r = self.buscar(SSL, termos=["certificado", "ssl", "renovacao", "vencido"])
        self.assertEqual(r[0]["kb_id"], "KB-101-A")
        self.assertEqual(r[0]["busca"], "palavra")
        self.assertIn("ConnectionError", r[0]["aviso_busca"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM kb_vetores").fetchone()[0], 0)

    # ---- o grafo

    def test_o_grafo_busca_so_por_vetor_e_o_portao_olha_o_score_do_vetor(self):
        RELATOS["O certificado SSL do meu site venceu ontem e a renovação automática não rodou. "
                "O navegador mostra aviso de site não seguro para os meus clientes."] = vetor(
                    KB_101_A=0.9, KB_104=0.05)
        modelo = ModeloRoteirizado(ROTEIROS["TKT-0001"])
        e = rodar_grafo("TKT-0001", client=modelo, modelo="fake", con=self.con, verbose=False,
                        confirmador=SIM)
        busca = next(p for p in e.passos if p.ferramenta == "buscar_base_conhecimento")
        melhor = busca.resultado["resultados"][0]
        self.assertEqual((melhor["kb_id"], melhor["busca"]), ("KB-101-A", "vetorial"))
        self.assertGreaterEqual(melhor["score"], 0.5)
        self.assertEqual(e.desfecho["acao"], "anotacao_interna")
        self.assertEqual(verificar("TKT-0001", e, self.con), (True, []))

    def test_o_grafo_nao_age_quando_o_cosseno_fica_abaixo_do_limiar(self):
        RELATOS["O certificado SSL do meu site venceu ontem e a renovação automática não rodou. "
                "O navegador mostra aviso de site não seguro para os meus clientes."] = vetor(
                    KB_101_A=0.5, KB_102=0.5, KB_103=0.5, KB_104=0.5, KB_105=0.5, KB_106=0.5)
        modelo = ModeloRoteirizado(ROTEIROS["TKT-0001"])
        e = rodar_grafo("TKT-0001", client=modelo, modelo="fake", con=self.con, verbose=False,
                        confirmador=SIM)
        self.assertEqual(e.desfecho["acao"], "fila_humana")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM chamados_internos "
                                          "WHERE ticket_externo = 'TKT-0001'").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()

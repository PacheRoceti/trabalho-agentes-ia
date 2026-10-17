"""Testes OFFLINE do grafo (src/grafo.py): sem chave e sem rede, com um "modelo" roteirizado.

Provam o que é do CÓDIGO no grafo: a rota, o nó `decidir` (portão de confiança e divergência),
o avaliador do texto, a pausa com `interrupt`, a retomada e os términos. NÃO provam que um modelo
real classifica certo: isso só `python src/main.py --todos --auto-aprovar` mede.

    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

os.environ["CHECKPOINT_DB"] = ":memory:"     # antes de importar o grafo: nada de arquivo nos testes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db                                    # noqa: E402
from agente import EdicaoRecusada, Orcamento, Termino, retomar, vencer_pendencias  # noqa: E402
import grafo as grafo_mod                  # noqa: E402
from grafo import GRAFO, LIMITE_SUPERPASSOS, retomar_grafo, rodar_grafo  # noqa: E402
from verificar import verificar              # noqa: E402


class ModeloRoteirizado:
    """Devolve, em ordem, os textos do roteiro (o último se repete). Cada chamada gasta 1000
    tokens de entrada e 50 de saída."""

    def __init__(self, roteiro):
        self.roteiro, self.i, self.pedidos = list(roteiro), 0, []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.pedidos.append(kw)
        texto = self.roteiro[min(self.i, len(self.roteiro) - 1)]
        self.i += 1
        return NS(usage=NS(prompt_tokens=1000, completion_tokens=50),
                  choices=[NS(message=NS(content=texto))])


def triagem(classe, diverge=False, termos=()):
    return json.dumps({"classe": classe, "log_aponta_outro_servico": diverge,
                       "termos_busca": list(termos), "justificativa": "teste"})


def texto(t):
    return json.dumps({"texto": t}, ensure_ascii=False)


def ressalva(cai, frase="", motivo="teste"):
    """A resposta do nó `conferir_ressalva` (o modelo lê as situações que o guia não cobre)."""
    return json.dumps({"cai_na_ressalva": cai, "frase": frase, "motivo": motivo}, ensure_ascii=False)


NAO_CAI = ressalva(False)


SIM = lambda p: (True, "teste")
NAO = lambda p: (False, "teste")
UPLOAD = ("permissao", "negada", "upload")

ROTEIROS = {
    "TKT-0001": [triagem("tecnico", termos=("certificado", "ssl", "renovacao", "vencido")),
                 texto("Rodar certbot renew --dry-run e conferir a porta 80.")],
    # o KB-106 volta com score alto (a armadilha): quem manda à fila humana é o sinal de divergência
    "TKT-0002": [triagem("tecnico", diverge=True, termos=("dns", "resolucao", "nameserver", "dominio")),
                 texto("Divergência: o cliente relata Webmail fora do ar, mas o log anexado aponta falha de DNS.")],
    # o KB-102 declara uma situação que não cobre (ssh): o nó `conferir_ressalva` roda, e aqui o modelo diz que não cai
    "TKT-0003": [triagem("tecnico", termos=UPLOAD), NAO_CAI,
                 texto("Permissão negada ao gravar arquivos. Cliente afirma ser a 3a vez; o histórico "
                       "do sistema confirma 1 ocorrência anterior (INC-0001).")],
    "TKT-0007": [triagem("tecnico", termos=UPLOAD), NAO_CAI,
                 texto("Permissão negada ao gravar arquivos; todo upload do site falha. Procedimento KB-102.")],
    "TKT-0999": [texto("Id TKT-0999 não existe no sistema de tickets.")],
    "TKT-0004": [triagem("comercial"), texto("Pedido de upgrade de plano: assunto comercial.")],
    # o pedido ao cliente é texto padrão: o modelo só é chamado na triagem
    "TKT-0005": [triagem("insuficiente")],
    # o KB-104 não cobre falha intermitente (ressalva): o score vem reduzido e o código decide
    "TKT-0006": [triagem("tecnico", termos=("502", "erro", "deploy", "intermitente")),
                 texto("KB-104 cobre falha constante; o relato é intermitente (score abaixo do limiar).")],
}


class TestGrafo(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()
        # Estes testes provam o grafo, e não chamam a API de embedding: a busca é a por palavra.
        # A busca híbrida tem os seus testes, com um embedder de mentira (tests/test_vetorial.py).
        self._busca, grafo_mod.BUSCA = grafo_mod.BUSCA, "palavra"

    def tearDown(self):
        grafo_mod.BUSCA = self._busca
        self.con.close()

    def rodar(self, ticket, roteiro=None, **kw):
        self.modelo = ModeloRoteirizado(roteiro or ROTEIROS[ticket])
        return rodar_grafo(ticket, client=self.modelo, modelo="fake", con=self.con, verbose=False,
                           confirmador=kw.pop("confirmador", SIM), **kw)

    def retomar(self, ticket, decisao, minutos=0):
        agora = datetime.now().astimezone() + timedelta(minutes=minutos)
        return retomar_grafo(ticket, decisao, client=ModeloRoteirizado([]), con=self.con,
                             agora=agora, verbose=False)

    def nos(self, e):
        return [p.ferramenta for p in e.passos]

    # ---- a estrutura

    def test_grafo_compilado_tem_os_nos_e_o_checkpointer(self):
        nos = {n for n in GRAFO.get_graph().nodes if not n.startswith("__")}
        self.assertEqual(nos, {"entrada", "consultar", "triagem", "buscar", "conferir_ressalva",
                               "decidir", "redigir", "validar", "pedir_confirmacao", "confirmar", "gravar", "finalizar"})
        self.assertIsNotNone(GRAFO.checkpointer)

    # ---- os 8 casos, e as rotas

    def test_todos_os_casos_passam_no_verificador(self):
        for ticket in ROTEIROS:
            with self.subTest(ticket=ticket):
                self.con.close()
                db.recriar_banco()
                self.con = db.conectar()
                e = self.rodar(ticket)
                ok, falhas = verificar(ticket, e, self.con)
                self.assertTrue(ok, falhas)
                self.assertIsNotNone(e.saida)

    def test_rota_tecnica_passa_pela_busca_e_as_outras_nao(self):
        self.assertEqual(self.nos(self.rodar("TKT-0001")),
                         ["consultar_ticket", "triagem", "buscar_base_conhecimento", "decidir",
                          "redigir", "registrar_encaminhamento"])
        self.assertEqual(self.nos(self.rodar("TKT-0004")),
                         ["consultar_ticket", "triagem", "decidir", "redigir", "registrar_encaminhamento"])

    def test_id_inexistente_nao_chama_a_triagem(self):
        e = self.rodar("TKT-0999")
        self.assertEqual(self.nos(e), ["consultar_ticket", "decidir", "redigir", "registrar_encaminhamento"])
        self.assertEqual(e.n_chamadas_modelo, 1)                       # só a redação
        self.assertEqual(e.saida.fonte.tipo, "nenhuma")

    def test_divergencia_e_decidida_antes_do_score(self):
        e = self.rodar("TKT-0002")
        self.assertGreaterEqual(e.scores_kb["KB-106"], 0.5)            # os portões do laço deixariam abrir
        self.assertEqual(e.desfecho["acao"], "fila_humana")
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0002"), 0)
        self.assertEqual(e.passos[3].resultado["motivo"], "divergencia_relato_log")

    def test_portao_de_confianca_e_do_codigo(self):
        e = self.rodar("TKT-0006")
        self.assertLess(e.scores_kb["KB-104"], 0.5)
        self.assertEqual(e.passos[3].resultado, {"acao": "fila_humana", "kb_id": None,
                                                 "motivo": "score_abaixo_do_limiar"})
        self.assertFalse(e.saida.suficiencia.suficiente)

    def rodar_sem(self, ticket, filtro=True, desempate=True):
        db.FILTRAR_REVOGADOS, db.DESEMPATAR_POR_DATA = filtro, desempate
        try:
            return self.rodar(ticket)
        finally:
            db.FILTRAR_REVOGADOS, db.DESEMPATAR_POR_DATA = True, True

    def test_sem_curadoria_o_tkt_0001_vira_chamado_p1_para_o_time_errado(self):
        # o achado do documento revogado (docs/rag.md §2.1): mesmo roteiro, mesmo score, e o
        # guia antigo decide a ação, o time e a prioridade
        e = self.rodar_sem("TKT-0001", filtro=False, desempate=False)
        self.assertEqual(e.scores_kb["KB-101"], e.scores_kb["KB-101-A"])
        self.assertEqual((e.desfecho["acao"], e.desfecho["kb_id"]), ("abrir_chamado_interno", "KB-101"))
        self.assertEqual((e.desfecho["prioridade"], e.desfecho["time_destino"]), ("P1", "Seguranca"))
        self.assertFalse(verificar("TKT-0001", e, self.con)[0])

    def test_cada_regra_de_curadoria_sozinha_basta_para_o_tkt_0001(self):
        for filtro, desempate in ((True, False), (False, True)):
            with self.subTest(filtro=filtro, desempate=desempate):
                self.con.close()
                db.recriar_banco()
                self.con = db.conectar()
                e = self.rodar_sem("TKT-0001", filtro=filtro, desempate=desempate)
                self.assertEqual(list(e.scores_kb), ["KB-101-A"])
                self.assertEqual(verificar("TKT-0001", e, self.con), (True, []))

    def test_o_descarte_da_versao_antiga_fica_no_log_da_busca(self):
        e = self.rodar_sem("TKT-0001", filtro=False)
        busca = next(p for p in e.passos if p.ferramenta == "buscar_base_conhecimento")
        self.assertEqual(busca.resultado["resultados"][0]["versoes_descartadas"],
                         [{"kb_id": "KB-101", "data_publicacao": "2025-03-10"}])

    def test_fora_da_alcada_vai_a_fila_humana_sem_busca(self):
        e = self.rodar("TKT-0007", [triagem("fora_da_alcada"), texto("O cliente pede para encerrar o chamado.")])
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]), ("fila_humana", "fora_da_alcada"))
        self.assertNotIn("buscar_base_conhecimento", self.nos(e))

    def test_um_pedido_de_informacao_por_chamado(self):
        self.rodar("TKT-0005")
        e = self.rodar("TKT-0005", [triagem("insuficiente"),           # outra execução, mesmo chamado
                                    texto("O chamado já recebeu um pedido de informação; falta o serviço.")])
        self.assertEqual(e.desfecho["acao"], "fila_humana")
        self.assertEqual(db.contar_pedidos_cliente(self.con, "TKT-0005"), 1)

    def test_reincidencia_sobe_prioridade_no_codigo(self):
        e = self.rodar("TKT-0003")
        self.assertEqual((e.desfecho["prioridade"], e.desfecho["time_destino"]), ("P1", "Infraestrutura"))

    # ---- o modelo fora do contrato

    def test_triagem_fora_do_contrato_volta_uma_vez_com_o_erro(self):
        e = self.rodar("TKT-0004", ['{"classe": "urgente"}', triagem("comercial"), texto("Pedido de upgrade de plano.")])
        self.assertEqual(e.desfecho["acao"], "fila_comercial")
        self.assertIn("ERRO DA TENTATIVA ANTERIOR", self.modelo.pedidos[1]["messages"][1]["content"])

    def test_triagem_invalida_duas_vezes_termina_em_erro_fatal(self):
        e = self.rodar("TKT-0004", ["não é json"])
        self.assertEqual(e.termino, Termino.ERRO_FATAL)
        self.assertIn("triagem fora do contrato", e.motivo)
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0004"), 0)
        self.assertFalse(e.saida.suficiencia.suficiente)

    def test_texto_reprovado_pelo_validar_e_reescrito(self):
        e = self.rodar("TKT-0004", [triagem("comercial"), texto("Upgrade."),
                                    texto("Pedido de upgrade de plano: assunto comercial.")])
        self.assertEqual(e.desfecho["acao"], "fila_comercial")
        self.assertEqual(self.nos(e).count("redigir"), 2)
        self.assertIn("curto demais", e.passos[4].erro["erro"])         # o passo do nó validar
        self.assertIn("ERRO DA TENTATIVA ANTERIOR", self.modelo.pedidos[2]["messages"][1]["content"])

    def test_texto_recusado_duas_vezes_termina_em_erro_fatal_sem_gravar(self):
        e = self.rodar("TKT-0004", [triagem("comercial"), texto("Upgrade.")])
        self.assertEqual(e.termino, Termino.ERRO_FATAL)
        self.assertIn("recusado em 2 tentativas", e.motivo)
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0004"), 0)

    # ---- o pedido ao cliente é texto padrão, e não do modelo (docs/prompts.md §2.2)

    def test_o_pedido_ao_cliente_e_o_texto_padrao_e_nao_chama_o_modelo_para_redigir(self):
        e = self.rodar("TKT-0005")
        self.assertEqual(e.desfecho["acao"], "devolver_cliente")
        self.assertEqual((e.n_chamadas_modelo, len(self.modelo.pedidos)), (1, 1))     # só a triagem
        self.assertEqual(e.saida.resultado.texto, grafo_mod.PEDIDO_AO_CLIENTE)
        self.assertEqual([l["mensagem"] for l in self.pedidos()], [grafo_mod.PEDIDO_AO_CLIENTE])
        redigir = next(p for p in e.passos if p.ferramenta == "redigir")
        self.assertTrue(redigir.argumentos["texto_padrao"])
        self.assertNotIn("validar", self.nos(e))                        # o texto padrão passa no avaliador

    def test_o_texto_padrao_do_pedido_pergunta_e_nao_cita_informacao_interna(self):
        self.assertIsNone(grafo_mod._erro_do_texto(self.con, "devolver_cliente", grafo_mod.PEDIDO_AO_CLIENTE))
        self.assertEqual(grafo_mod.PEDIDO_AO_CLIENTE.count("?"), 7)
        for pedido in ("serviço", "domínio", "nome do banco", "código de erro", "data e hora"):
            self.assertIn(pedido, grafo_mod.PEDIDO_AO_CLIENTE)

    # ---- a ressalva lida pelo modelo (docs/rag.md §4.2): o nó `conferir_ressalva`

    def passo(self, e, ferramenta):
        return next((p for p in e.passos if p.ferramenta == ferramenta), None)

    def test_a_ressalva_so_e_conferida_quando_ha_o_que_conferir(self):
        # KB-101-A não declara situação que não cobre; no TKT-0006 a ressalva literal já derrubou o score
        for ticket in ("TKT-0001", "TKT-0006"):
            with self.subTest(ticket=ticket):
                self.assertIsNone(self.passo(self.rodar(ticket), "conferir_ressalva"))
        e = self.rodar("TKT-0003")                              # KB-102 declara "ssh"
        self.assertEqual(self.passo(e, "conferir_ressalva").argumentos,
                         {"kb_id": "KB-102", "situacoes": ["ssh"]})

    def test_modelo_diz_que_o_relato_cai_na_ressalva_e_o_codigo_baixa_o_score(self):
        roteiro = [triagem("tecnico", termos=UPLOAD), ressalva(True, "ssh", "o relato fala de ssh"),
                   texto("O guia não cobre o caso relatado; encaminhar a um analista.")]
        e = self.rodar("TKT-0003", roteiro)
        r = self.passo(e, "conferir_ressalva").resultado
        self.assertEqual(r["score_depois"], round(r["score_antes"] * db.REDUTOR, 2))
        self.assertLess(r["score_depois"], 0.5)
        melhor = self.passo(e, "buscar_base_conhecimento").resultado["resultados"][0]
        self.assertNotIn("ressalva_por", melhor)                # o log da busca é o da busca
        self.assertEqual(e.desfecho["acao"], "fila_humana")
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0003"), 0)
        self.assertIn("abaixo do limiar", e.saida.suficiencia.motivo)    # e a saída diz por quê
        self.assertIn("conferir_ressalva", e.saida.fonte.ferramentas)

    def test_modelo_diz_que_nao_cai_e_nada_muda(self):
        e = self.rodar("TKT-0003")
        r = self.passo(e, "conferir_ressalva").resultado
        self.assertEqual((r["cai_na_ressalva"], r["score_antes"]), (False, r["score_depois"]))
        self.assertEqual(e.desfecho["acao"], "abrir_chamado_interno")

    def test_o_modelo_nao_cria_uma_excecao_que_o_guia_nao_declara(self):
        roteiro = [triagem("tecnico", termos=UPLOAD), ressalva(True, "intermitente"),
                   ressalva(True, "ssh"), texto("Encaminhado.")]
        e = self.rodar("TKT-0003", roteiro)                     # 1a resposta: frase fora da lista; 2a: certa
        self.assertEqual(e.n_chamadas_modelo, 4)
        self.assertEqual(self.passo(e, "conferir_ressalva").resultado["frase"], "ssh")
        self.assertIn("situações da lista", self.modelo.pedidos[2]["messages"][1]["content"])

    def test_ressalva_fora_do_contrato_duas_vezes_termina_em_erro_fatal_sem_gravar(self):
        for ruim in (ressalva(True, "intermitente"), "isto não é JSON"):
            with self.subTest(ruim=ruim[:20]):
                self.con.close()
                db.recriar_banco()
                self.con = db.conectar()
                e = self.rodar("TKT-0003", [triagem("tecnico", termos=UPLOAD), ruim, ruim])
                self.assertEqual(e.termino, Termino.ERRO_FATAL)
                self.assertIn("ressalva", e.motivo)
                self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0003"), 0)

    def test_o_teto_de_tokens_vale_tambem_no_no_da_ressalva(self):
        e = self.rodar("TKT-0003", orcamento=Orcamento(max_tokens=1000))
        self.assertEqual(e.termino, Termino.ORCAMENTO)
        self.assertIsNone(self.passo(e, "conferir_ressalva"))

    # ---- os tetos

    def test_teto_de_tokens_termina_antes_da_redacao(self):
        e = self.rodar("TKT-0001", orcamento=Orcamento(max_tokens=1000))
        self.assertEqual(e.termino, Termino.ORCAMENTO)
        self.assertIn("tokens", e.motivo)
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0001"), 0)

    def test_limite_de_superpassos_e_declarado_no_codigo(self):
        self.assertEqual(LIMITE_SUPERPASSOS, 20)

    # ---- a pausa do H1 (interrupt + checkpointer)

    def test_sem_resposta_do_analista_o_grafo_pausa_no_interrupt(self):
        e = self.rodar("TKT-0007", confirmador=None)
        self.assertEqual(e.termino, Termino.HUMANO)
        self.assertIn("20 minutos", e.motivo)
        self.assertEqual(GRAFO.get_state({"configurable": {"thread_id": "TKT-0007"}}).next, ("confirmar",))
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)
        (p,) = db.pendencias_aguardando(self.con, "TKT-0007")
        self.assertEqual((p["acao"]["kb_id"], p["checkpoint"]["motor"]), ("KB-102", "grafo"))
        self.assertIsNone(e.saida.resultado.acao)

    def test_aprovar_retoma_abre_o_chamado_e_aprovar_de_novo_nao_duplica(self):
        self.rodar("TKT-0007", confirmador=None)
        e = self.retomar("TKT-0007", "aprovar", minutos=19)
        self.assertEqual(e.termino, Termino.RESPONDEU)
        self.assertEqual(verificar("TKT-0007", e, self.con), (True, []))
        self.assertEqual(e.confirmacoes[-1]["status"], "aprovada")
        self.assertEqual(e.n_chamadas_modelo, 3)                       # triagem, ressalva, redação: a retomada não chama o modelo
        self.assertIsNone(self.retomar("TKT-0007", "aprovar"))        # aprovar duas vezes
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 1)
        self.assertEqual(db.pendencias_aguardando(self.con), [])

    def test_rejeitar_vai_a_fila_humana_com_as_consideracoes(self):
        self.rodar("TKT-0007", confirmador=None)
        e = self.retomar("TKT-0007", "rejeitar", minutos=5)
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]), ("fila_humana", "acao_rejeitada"))
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)
        self.assertIn("rejeitada pelo analista", e.saida.resultado.texto)
        self.assertIn("KB-102", e.saida.resultado.texto)

    def test_prazo_vencido_de_p1_vai_a_fila_humana_e_avisa_o_gestor(self):
        self.rodar("TKT-0003", confirmador=None)
        self.assertIsNone(self.retomar("TKT-0003", "vencer", minutos=19))     # ainda no prazo
        e = self.retomar("TKT-0003", "aprovar", minutos=21)                   # aprovação tardia
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]), ("fila_humana", "confirmacao_nao_recebida"))
        self.assertEqual(e.confirmacoes[-1]["status"], "vencida")
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0003"), 0)
        self.assertEqual(db.contar(self.con, "avisos_gestor", "TKT-0003"), 1)
        (aviso,) = db.avisos_ao_gestor(self.con)                       # o que o --avisos lista
        self.assertEqual((aviso["ticket_externo"], aviso["prioridade"], aviso["motivo"]),
                         ("TKT-0003", "P1", "confirmacao_nao_recebida"))

    def test_resposta_pelo_caminho_do_laco_chega_ao_grafo(self):
        """main.py --aprovar e o vencimento usam agente.retomar: a pendência diz quem continua."""
        self.rodar("TKT-0007", confirmador=None)
        self.rodar("TKT-0003", confirmador=None, prazo_confirmacao_min=1)
        vencidos = vencer_pendencias(client=ModeloRoteirizado([]), con=self.con, verbose=False,
                                     agora=datetime.now().astimezone() + timedelta(minutes=2))
        self.assertEqual([e.id_ticket for e in vencidos], ["TKT-0003"])
        e = retomar("TKT-0007", "aprovar", client=ModeloRoteirizado([]), con=self.con, verbose=False)
        self.assertEqual(e.desfecho["acao"], "abrir_chamado_interno")

    # ---- aprovar editando (só o resumo, só no grafo)

    CORRIGIDO = "Upload falha com permissão negada desde hoje; o cliente não relatou restauração recente."

    def editar(self, ticket, decisao, resumo, minutos=0):
        agora = datetime.now().astimezone() + timedelta(minutes=minutos)
        return retomar_grafo(ticket, decisao, client=ModeloRoteirizado([]), con=self.con,
                             agora=agora, verbose=False, resumo=resumo)

    def test_a_tela_da_pausa_mostra_a_prioridade_prevista(self):
        self.rodar("TKT-0003", confirmador=None)
        self.rodar("TKT-0007", confirmador=None)
        previstas = {p["ticket_externo"]: p["acao"]["prioridade_prevista"]
                     for p in db.pendencias_aguardando(self.con)}
        self.assertEqual(previstas, {"TKT-0003": "P1", "TKT-0007": "P2"})   # reincidência sobe um nível

    def test_a_tela_da_pausa_mostra_a_data_do_guia_o_que_ele_nao_cobre_e_o_plano(self):
        # o analista é a última barreira quando o modelo diz que o relato não cai numa ressalva
        e = self.rodar("TKT-0007", confirmador=None)
        p = e.pendencia
        self.assertEqual(p["guia_publicado_em"], "2026-10-06")
        self.assertEqual(p["guia_nao_cobre"], ["ssh"])
        self.assertEqual(p["plano"], "VPS Pro")
        self.assertIn("aplicação instalada pelo cliente", p["escopo_do_plano"])
        (guardada,) = db.pendencias_aguardando(self.con, "TKT-0007")
        self.assertEqual(guardada["acao"]["guia_nao_cobre"], ["ssh"])     # e vai para a tabela, não só para a tela

    def test_a_tela_nao_traz_ressalvas_quando_o_guia_nao_declara_nenhuma(self):
        self.con.execute("UPDATE kb_artigos SET nao_cobre = '' WHERE id = 'KB-102'")
        p = self.rodar("TKT-0007", [triagem("tecnico", termos=UPLOAD), texto("Permissão negada ao gravar.")],
                       confirmador=None).pendencia
        self.assertEqual(p["guia_nao_cobre"], [])

    # ---- o que entrou na tela do H1 em 17/10/2026 (docs/humano.md §2.2): só informa

    def tela(self, pendencia):
        import io, contextlib, main
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            main.mostrar_pendencia(pendencia)
        return saida.getvalue()

    def test_a_tela_do_h1_mostra_o_score_a_reincidencia_e_o_sla(self):
        e3 = self.rodar("TKT-0003", confirmador=None)
        e7 = self.rodar("TKT-0007", confirmador=None)
        p3, p7 = e3.pendencia, e7.pendencia
        # a reincidência é a que o sistema confirma: os chamados que a regra contou
        self.assertTrue(p3["reincidencia"])
        self.assertTrue(all(c["chamado_interno"].startswith("INC-") for c in p3["reincidencia"]))
        self.assertEqual(p7["reincidencia"], [])
        self.assertEqual((p3["sla_previsto"], p7["sla_previsto"]), ("2 horas", "1 dia útil"))
        self.assertGreaterEqual(p7["score"], 0.5)                    # é o score que passou no portão
        self.assertEqual(p7["score"], e7.scores_kb["KB-102"])
        (guardada,) = db.pendencias_aguardando(self.con, "TKT-0003")
        self.assertEqual(guardada["acao"]["reincidencia"], p3["reincidencia"])   # vai para a tabela também
        tela3, tela7 = self.tela(p3), self.tela(p7)
        self.assertIn("REINCIDÊNCIA: confirmada pelo sistema", tela3)
        self.assertIn(p3["reincidencia"][0]["chamado_interno"], tela3)
        self.assertIn("SLA de resolução: 2 horas", tela3)
        self.assertIn("REINCIDÊNCIA: nenhuma confirmada", tela7)
        self.assertIn(f"SUSTENTAÇÃO: guia KB-102 com score {p7['score']}", tela7)
        self.assertIn("--aprovar TKT-0007 --editar", tela7)

    def test_a_tela_nova_nao_muda_o_desfecho(self):
        e = self.rodar("TKT-0003")                                   # aprovado na hora
        self.assertEqual(verificar("TKT-0003", e, self.con), (True, []))
        self.assertEqual(e.desfecho["prioridade"], e.confirmacoes[-1]["pendencia"]["prioridade_prevista"])

    def test_a_ficha_do_plano_vai_a_redacao_so_na_rota_tecnica_e_nao_muda_o_desfecho(self):
        e = self.rodar("TKT-0007")
        redacao = self.modelo.pedidos[-1]["messages"][1]["content"]
        self.assertIn("Escopo do plano do cliente (VPS Pro)", redacao)
        self.assertEqual(verificar("TKT-0007", e, self.con), (True, []))
        self.rodar("TKT-0004")                                            # comercial: sem ficha
        self.assertNotIn("Escopo do plano", self.modelo.pedidos[-1]["messages"][1]["content"])

    def test_aprovar_editando_grava_o_resumo_do_analista_e_guarda_o_do_modelo(self):
        pausado = self.rodar("TKT-0007", confirmador=None)
        original = pausado.pendencia["resumo"]
        e = self.editar("TKT-0007", "aprovar", self.CORRIGIDO)
        self.assertEqual(e.termino, Termino.RESPONDEU)
        self.assertEqual(verificar("TKT-0007", e, self.con), (True, []))
        c = e.confirmacoes[-1]
        self.assertEqual((c["status"], c["editado"]), ("aprovada", True))
        self.assertEqual((c["resumo_original"], c["resumo_aprovado"]), (original, self.CORRIGIDO))
        self.assertEqual(e.saida.resultado.texto, self.CORRIGIDO)
        (gravado,) = [r[0] for r in self.con.execute(
            "SELECT resumo FROM chamados_internos WHERE ticket_externo = 'TKT-0007'")]
        self.assertEqual(gravado, self.CORRIGIDO)
        # o que o código garante não é editável: time e prioridade continuam vindo do procedimento
        self.assertEqual((e.desfecho["time_destino"], e.desfecho["prioridade"]), ("Infraestrutura", "P2"))
        self.assertEqual(e.n_chamadas_modelo, 3)                            # triagem, ressalva, redação: editar não chama o modelo

    def test_aprovar_editando_duas_vezes_nao_duplica(self):
        self.rodar("TKT-0007", confirmador=None)
        self.editar("TKT-0007", "aprovar", self.CORRIGIDO)
        self.assertIsNone(self.editar("TKT-0007", "aprovar", self.CORRIGIDO + " (de novo)"))
        self.assertIsNone(self.retomar("TKT-0007", "aprovar"))
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 1)
        (gravado,) = [r[0] for r in self.con.execute(
            "SELECT resumo FROM chamados_internos WHERE ticket_externo = 'TKT-0007'")]
        self.assertEqual(gravado, self.CORRIGIDO)                           # a segunda não reescreve

    def test_edicao_invalida_e_recusada_e_a_pausa_continua(self):
        self.rodar("TKT-0007", confirmador=None)
        with self.assertRaises(EdicaoRecusada):
            self.editar("TKT-0007", "aprovar", "curto")
        with self.assertRaises(EdicaoRecusada):
            self.editar("TKT-0007", "rejeitar", self.CORRIGIDO)             # rejeição não leva resumo
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)
        self.assertEqual(len(db.pendencias_aguardando(self.con, "TKT-0007")), 1)
        e = self.editar("TKT-0007", "aprovar", self.CORRIGIDO)              # a aprovação não foi gasta
        self.assertEqual(e.desfecho["acao"], "abrir_chamado_interno")

    def test_edicao_depois_do_prazo_nao_vale(self):
        self.rodar("TKT-0007", confirmador=None)
        e = self.editar("TKT-0007", "aprovar", self.CORRIGIDO, minutos=21)
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]), ("fila_humana", "confirmacao_nao_recebida"))
        self.assertEqual((e.confirmacoes[-1]["status"], e.confirmacoes[-1]["editado"]), ("vencida", False))
        self.assertNotIn(self.CORRIGIDO, e.saida.resultado.texto)           # vai o resumo do agente
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)

    def test_resumo_igual_ao_proposto_nao_conta_como_edicao(self):
        pausado = self.rodar("TKT-0007", confirmador=None)
        e = self.editar("TKT-0007", "aprovar", pausado.pendencia["resumo"])
        self.assertEqual((e.confirmacoes[-1]["status"], e.confirmacoes[-1]["editado"]), ("aprovada", False))

    def test_rejeicao_na_hora_pelo_confirmador(self):
        e = self.rodar("TKT-0003", confirmador=NAO)
        self.assertEqual((e.termino, e.desfecho["motivo"]), (Termino.RESPONDEU, "acao_rejeitada"))
        self.assertEqual(db.contar(self.con, "avisos_gestor", "TKT-0003"), 0)

    # ---- a pausa do H2: o pedido de informação ao cliente (docs/humano.md §1 e §2.4)

    PEDIDO = "Qual serviço está com problema, que erro aparece na tela e desde quando isso acontece?"

    def responder(self, ticket, decisao, minutos=0, **kw):
        agora = datetime.now().astimezone() + timedelta(minutes=minutos)
        return retomar_grafo(ticket, decisao, client=ModeloRoteirizado([]), con=self.con,
                             agora=agora, verbose=False, **kw)

    def pedidos(self, ticket="TKT-0005"):
        return [dict(l) for l in self.con.execute(
            "SELECT * FROM encaminhamentos WHERE ticket_externo = ? AND destino = 'devolver_cliente'",
            (ticket,))]

    def test_h2_sem_resposta_o_pedido_ao_cliente_pausa_e_nada_e_gravado(self):
        e = self.rodar("TKT-0005", confirmador=None)
        self.assertEqual(e.termino, Termino.HUMANO)
        self.assertIn("20 minutos", e.motivo)
        self.assertEqual(GRAFO.get_state({"configurable": {"thread_id": "TKT-0005"}}).next, ("confirmar",))
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0005"), 0)
        (p,) = db.pendencias_aguardando(self.con, "TKT-0005")
        acao = p["acao"]
        self.assertEqual((acao["ferramenta"], p["checkpoint"]["motor"]), ("devolver_cliente", "grafo"))
        self.assertEqual(acao["relato"], db.buscar_ticket(self.con, "TKT-0005")["texto"])
        self.assertEqual(acao["mensagem"], grafo_mod.PEDIDO_AO_CLIENTE)
        for ausente in ("kb_id", "prioridade_prevista", "precedentes"):   # não há guia nem prioridade
            self.assertNotIn(ausente, acao)
        self.assertEqual(self.episodios(), [])
        self.assertIsNone(e.saida.resultado.acao)

    def test_h2_aprovar_envia_um_pedido_e_aprovar_de_novo_nao_duplica(self):
        self.rodar("TKT-0005", confirmador=None)
        e = self.responder("TKT-0005", "aprovar", minutos=19)
        self.assertEqual(e.termino, Termino.RESPONDEU)
        self.assertEqual(verificar("TKT-0005", e, self.con), (True, []))
        self.assertEqual(self.nos(e), ["consultar_ticket", "triagem", "decidir", "redigir", "confirmar",
                                       "registrar_encaminhamento"])
        self.assertEqual(e.confirmacoes[-1]["status"], "aprovada")
        self.assertEqual(e.n_chamadas_modelo, 1)                       # só a triagem: o pedido é texto padrão, e a retomada não chama o modelo
        (linha,) = self.pedidos()
        self.assertEqual(linha["enviado_em"], e.desfecho["enviado_em"])
        self.assertIsNotNone(linha["enviado_em"])
        self.assertIsNone(self.responder("TKT-0005", "aprovar"))      # aprovar duas vezes
        self.assertEqual(len(self.pedidos()), 1)
        self.assertEqual(db.pendencias_aguardando(self.con), [])

    def test_h2_rejeitar_vai_a_fila_humana_com_a_mensagem_e_nao_gasta_o_pedido(self):
        pausado = self.rodar("TKT-0005", confirmador=None)
        e = self.responder("TKT-0005", "rejeitar", minutos=5)
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]), ("fila_humana", "acao_rejeitada"))
        self.assertIn("rejeitada pelo analista", e.saida.resultado.texto)
        self.assertIn(pausado.pendencia["mensagem"], e.saida.resultado.texto)
        self.assertEqual(self.pedidos(), [])
        self.assertFalse(e.saida.suficiencia.suficiente)
        # o pedido barrado não chegou ao cliente: o único pedido do chamado continua disponível
        self.assertEqual(self.rodar("TKT-0005").desfecho["acao"], "devolver_cliente")

    def test_h2_prazo_vencido_vai_a_fila_humana_sem_avisar_o_gestor(self):
        self.rodar("TKT-0005", confirmador=None)
        self.assertIsNone(self.responder("TKT-0005", "vencer", minutos=19))   # ainda no prazo
        e = self.responder("TKT-0005", "aprovar", minutos=21, mensagem=self.PEDIDO)   # aprovação tardia
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]), ("fila_humana", "confirmacao_nao_recebida"))
        self.assertEqual((e.confirmacoes[-1]["status"], e.confirmacoes[-1]["editado"]), ("vencida", False))
        self.assertNotIn(self.PEDIDO, e.saida.resultado.texto)         # vai a mensagem do agente
        self.assertEqual(self.pedidos(), [])
        self.assertEqual(db.contar(self.con, "avisos_gestor", "TKT-0005"), 0)   # não há prioridade prevista

    def test_h2_aprovar_editando_envia_a_mensagem_do_analista_e_guarda_a_do_modelo(self):
        pausado = self.rodar("TKT-0005", confirmador=None)
        # pelo caminho do main.py (agente.retomar): a pendência diz quem continua
        e = retomar("TKT-0005", "aprovar", client=ModeloRoteirizado([]), con=self.con, verbose=False,
                    mensagem=self.PEDIDO)
        self.assertEqual(verificar("TKT-0005", e, self.con), (True, []))
        c = e.confirmacoes[-1]
        self.assertEqual((c["status"], c["editado"]), ("aprovada", True))
        self.assertEqual((c["mensagem_original"], c["mensagem_aprovada"]),
                         (pausado.pendencia["mensagem"], self.PEDIDO))
        self.assertEqual(e.saida.resultado.texto, self.PEDIDO)
        self.assertEqual([l["mensagem"] for l in self.pedidos()], [self.PEDIDO])
        self.assertEqual(self.episodios()[0]["veredito"], "editado")

    def test_h2_edicao_recusada_nao_gasta_a_aprovacao(self):
        self.rodar("TKT-0005", confirmador=None)
        recusadas = ({"mensagem": "Abrimos o INC-0001 com prioridade P1 para o seu caso."},   # informação interna
                     {"mensagem": "oi"},                                                       # curta demais
                     {"resumo": self.CORRIGIDO})                                               # campo de outra ação
        for edicao in recusadas:
            with self.subTest(edicao=edicao), self.assertRaises(EdicaoRecusada):
                self.responder("TKT-0005", "aprovar", **edicao)
        with self.assertRaises(EdicaoRecusada):
            self.responder("TKT-0005", "rejeitar", mensagem=self.PEDIDO)     # rejeição não leva mensagem
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0005"), 0)
        self.assertEqual(len(db.pendencias_aguardando(self.con, "TKT-0005")), 1)
        e = self.responder("TKT-0005", "aprovar", mensagem=self.PEDIDO)      # a aprovação não foi gasta
        self.assertEqual(e.desfecho["acao"], "devolver_cliente")
        self.rodar("TKT-0007", confirmador=None)                             # e o H1 recusa --mensagem
        with self.assertRaises(EdicaoRecusada):
            self.responder("TKT-0007", "aprovar", mensagem=self.PEDIDO)
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)

    def test_h2_o_motivo_da_rejeicao_e_o_da_acao_pendente(self):
        self.rodar("TKT-0005", confirmador=None)
        with self.assertRaises(ValueError):
            self.responder("TKT-0005", "rejeitar", motivo_rejeicao="guia_errado")   # motivo do H1
        self.assertEqual(len(db.pendencias_aguardando(self.con, "TKT-0005")), 1)
        e = self.responder("TKT-0005", "rejeitar", motivo_rejeicao="informacao_suficiente")
        self.assertEqual(e.confirmacoes[-1]["motivo_rejeicao"], "informacao_suficiente")
        (ep,) = self.episodios()
        self.assertEqual((ep["kb_id"], ep["acao_proposta"], ep["desfecho"], ep["veredito"], ep["motivo_rejeicao"]),
                         (None, "devolver_cliente", "fila_humana", "rejeitado", "informacao_suficiente"))
        self.rodar("TKT-0007", confirmador=None)
        with self.assertRaises(ValueError):
            self.responder("TKT-0007", "rejeitar", motivo_rejeicao="mensagem_ruim")  # motivo do H2
        self.assertEqual(len(db.pendencias_aguardando(self.con, "TKT-0007")), 1)

    def test_h2_candidata_a_regra_do_pedido_ao_cliente_nao_tem_guia(self):
        for _ in range(3):
            self.rodar("TKT-0005", confirmador=None)
            self.responder("TKT-0005", "rejeitar", motivo_rejeicao="informacao_suficiente")
        (c,) = db.candidatas_a_regra(self.con)
        self.assertEqual((c["kb_id"], c["acao"], c["padrao"], c["quantidade"]),
                         (None, "devolver_cliente", "informacao_suficiente", 3))
        self.assertIn("triagem", c["destino"])

    def test_h2_o_episodio_nao_guarda_o_relato_nem_a_mensagem(self):
        pausado = self.rodar("TKT-0005", confirmador=None)
        self.responder("TKT-0005", "aprovar")
        (ep,) = self.episodios()
        guardado = json.dumps(ep, ensure_ascii=False)
        self.assertNotIn(pausado.pendencia["relato"], guardado)
        self.assertNotIn(pausado.pendencia["mensagem"], guardado)
        self.assertEqual((ep["acao_proposta"], ep["desfecho"], ep["veredito"]),
                         ("devolver_cliente", "devolver_cliente", "aprovado"))

    def test_h2_a_tela_mostra_o_relato_a_consequencia_e_os_comandos_do_pedido(self):
        p = self.rodar("TKT-0005", confirmador=None).pendencia
        import io, contextlib, main
        tela = io.StringIO()
        with contextlib.redirect_stdout(tela):
            main.mostrar_pendencia(p)
        tela = tela.getvalue()
        for trecho in (f"relato: {p['relato']}", f"mensagem: {p['mensagem']}", "único pedido de informação",
                       "não tem canal de mensagem", '--aprovar TKT-0005 --mensagem "texto corrigido"',
                       "--motivo mensagem_ruim | informacao_suficiente | outro"):
            self.assertIn(trecho, tela)
        self.assertNotIn("--resumo", tela)
        self.assertNotIn("chamado interno", tela)

    def test_h2_rejeicao_na_hora_pelo_confirmador(self):
        e = self.rodar("TKT-0005", confirmador=NAO)
        self.assertEqual((e.termino, e.desfecho["acao"], e.desfecho["motivo"]),
                         (Termino.RESPONDEU, "fila_humana", "acao_rejeitada"))
        self.assertEqual(self.pedidos(), [])

    def test_h2_o_envio_e_idempotente_pelo_chamado(self):
        primeiro = db.registrar_pedido_cliente(self.con, "TKT-0005", self.PEDIDO)
        segundo = db.registrar_pedido_cliente(self.con, "TKT-0005", self.PEDIDO + " (de novo)")
        self.assertEqual((primeiro["ja_existia"], segundo["ja_existia"]), (False, True))
        self.assertEqual((segundo["encaminhamento"], segundo["enviado_em"]),
                         (primeiro["encaminhamento"], primeiro["enviado_em"]))
        self.assertEqual([l["mensagem"] for l in self.pedidos()], [self.PEDIDO])   # a segunda não reescreve

    def test_h2_o_laco_nao_pausa_no_pedido_ao_cliente(self):
        from test_offline import ModeloRoteirizado as ModeloDoLaco, ROTEIROS as ROTEIROS_DO_LACO
        from agente import rodar
        e = rodar("TKT-0005", client=ModeloDoLaco(ROTEIROS_DO_LACO["TKT-0005"]), modelo="fake",
                  con=self.con, verbose=False)
        self.assertEqual((e.termino, e.desfecho["acao"]), (Termino.RESPONDEU, "devolver_cliente"))
        self.assertEqual(db.pendencias_aguardando(self.con), [])
        self.assertEqual([l["enviado_em"] for l in self.pedidos()], [None])   # Parte 1: gravado, não enviado

    # ---- a memória episódica (docs/memoria.md §1.3 e §2.2): o código escreve, a tela do H1 lê

    def episodios(self):
        return [dict(l) for l in self.con.execute("SELECT * FROM episodios ORDER BY id")]

    def semear(self, dias, veredito, kb_id="KB-102", ticket="TKT-0007"):
        """Um episódio com `dias` de idade, do mesmo cliente e categoria do chamado `ticket`."""
        t = db.buscar_ticket(self.con, ticket)
        quando = (datetime.now().astimezone() - timedelta(days=dias)).isoformat(timespec="seconds")
        db.registrar_episodio(self.con, {
            "ticket_externo": ticket, "cliente_id": t["_cliente_id"], "classe": "tecnico",
            "categoria": db.buscar_artigo(self.con, kb_id)["categoria"], "kb_id": kb_id, "score": 0.9,
            "acao_proposta": "abrir_chamado_interno", "desfecho": "fila_humana", "motivo": "teste",
            "veredito": veredito, "termino": "respondeu", "resumo": "semeado pelo teste",
            "criado_em": quando})

    def test_execucao_concluida_grava_um_episodio_e_a_pausada_nao(self):
        self.rodar("TKT-0007", confirmador=None)
        self.assertEqual(self.episodios(), [])                         # pausou: ainda não é um episódio
        self.retomar("TKT-0007", "rejeitar")
        (ep,) = self.episodios()
        self.assertEqual((ep["kb_id"], ep["acao_proposta"], ep["desfecho"], ep["veredito"]),
                         ("KB-102", "abrir_chamado_interno", "fila_humana", "rejeitado"))
        self.assertEqual(ep["cliente_id"], db.buscar_ticket(self.con, "TKT-0007")["_cliente_id"])
        self.assertEqual(ep["categoria"], db.buscar_artigo(self.con, "KB-102")["categoria"])

    def test_a_escrita_do_episodio_e_idempotente_pela_chave_do_conteudo(self):
        self.rodar("TKT-0001")
        (gravado,) = self.episodios()
        ep = {**gravado, "execucao_id": "TKT-0001-abc"}
        primeiro = db.registrar_episodio(self.con, ep)
        repetido = db.registrar_episodio(self.con, {**ep, "criado_em": "2026-10-12T10:00:00-03:00",
                                                    "resumo": "gravado de novo"})
        self.assertEqual((primeiro["ja_existia"], repetido["ja_existia"]), (False, True))
        self.assertEqual((repetido["id"], repetido["chave"]), (primeiro["id"], primeiro["chave"]))
        self.assertEqual(len(self.episodios()), 2)                     # o da execução e o gravado à mão
        # conteúdo diferente = chave diferente: outro desfecho, ou outra execução do mesmo chamado
        self.assertFalse(db.registrar_episodio(self.con, {**ep, "desfecho": "fila_humana"})["ja_existia"])
        self.assertFalse(db.registrar_episodio(self.con, {**ep, "execucao_id": "TKT-0001-def"})["ja_existia"])
        self.assertIsNotNone(gravado["chave"])                         # o grafo grava com chave
        self.assertIsNone(db.chave_do_episodio({k: v for k, v in ep.items() if k != "execucao_id"}))

    def test_executar_de_novo_o_mesmo_chamado_e_outro_episodio(self):
        self.rodar("TKT-0001")
        self.rodar("TKT-0001")
        um, dois = self.episodios()
        self.assertNotEqual(um["chave"], dois["chave"])

    def test_execucao_concluida_apaga_o_checkpoint_e_a_pausada_nao(self):
        thread = {"configurable": {"thread_id": "TKT-0007"}}
        self.rodar("TKT-0001")
        self.assertEqual(GRAFO.get_state({"configurable": {"thread_id": "TKT-0001"}}).values, {})
        self.rodar("TKT-0007", confirmador=None)
        self.assertEqual(GRAFO.get_state(thread).values["texto"],        # pausada: o texto do cliente está lá
                         db.buscar_ticket(self.con, "TKT-0007")["texto"])
        self.retomar("TKT-0007", "aprovar")
        self.assertEqual(GRAFO.get_state(thread).values, {})
        self.assertIsNone(self.retomar("TKT-0007", "aprovar"))          # a segunda aprovação não encontra pausa

    def test_o_episodio_nao_guarda_o_texto_do_cliente_nem_o_que_o_modelo_redigiu(self):
        e = self.rodar("TKT-0003")
        (ep,) = self.episodios()
        guardado = json.dumps(ep, ensure_ascii=False)
        ticket = db.buscar_ticket(self.con, "TKT-0003")
        for fora in (ticket["texto"], ticket["anexo_log"], e.desfecho.get("resumo"), ticket["cliente"]):
            if fora:
                self.assertNotIn(fora, guardado)
        self.assertEqual(ep["veredito"], "aprovado")

    def test_episodio_sem_h1_nao_tem_veredito_e_id_inexistente_nao_tem_cliente(self):
        self.rodar("TKT-0001")
        self.rodar("TKT-0999")
        anotado, inexistente = self.episodios()
        self.assertEqual((anotado["desfecho"], anotado["veredito"]), ("anotacao_interna", None))
        self.assertEqual((inexistente["cliente_id"], inexistente["kb_id"], inexistente["motivo"]),
                         (None, None, "id_inexistente"))

    def test_a_tela_da_pausa_mostra_o_que_o_analista_ja_decidiu_sobre_o_guia(self):
        self.rodar("TKT-0007", confirmador=NAO)
        p = self.rodar("TKT-0007", confirmador=None).pendencia["precedentes"]
        self.assertEqual((p["guia"]["decisoes"], p["guia"]["rejeitados"], p["guia"]["aprovados"]), (1, 1, 0))
        self.assertEqual([(c["ticket"], c["veredito"], c["antigo"]) for c in p["cliente"]],
                         [("TKT-0007", "rejeitado", False)])
        import io, contextlib, main
        tela = io.StringIO()
        with contextlib.redirect_stdout(tela):
            main.mostrar_pendencia(self.rodar("TKT-0007", confirmador=None).pendencia)
        self.assertIn("MEMÓRIA: nos últimos 90 dias o analista decidiu 1 vez(es) sobre o guia KB-102: "
                      "1 rejeitada(s)", tela.getvalue())

    def test_o_precedente_so_avisa_e_nao_muda_o_desfecho(self):
        for _ in range(3):
            self.semear(dias=1, veredito="rejeitado")
        e = self.rodar("TKT-0007")
        self.assertEqual(e.desfecho["acao"], "abrir_chamado_interno")
        self.assertEqual(verificar("TKT-0007", e, self.con), (True, []))
        self.assertEqual(e.confirmacoes[-1]["pendencia"]["precedentes"]["guia"]["rejeitados"], 3)

    def test_decaimento_o_antigo_aparece_sem_contar_e_o_de_mais_de_um_ano_sai(self):
        self.semear(dias=30, veredito="rejeitado")
        self.semear(dias=200, veredito="rejeitado")
        self.semear(dias=400, veredito="rejeitado")
        t = db.buscar_ticket(self.con, "TKT-0007")
        categoria = db.buscar_artigo(self.con, "KB-102")["categoria"]
        p = db.precedentes(self.con, "KB-102", t["_cliente_id"], categoria)
        self.assertEqual((p["guia"]["decisoes"], p["guia"]["rejeitados"], p["guia"]["decisoes_antigas"]), (1, 1, 1))
        self.assertEqual([c["antigo"] for c in p["cliente"]], [False, True])   # o de 400 dias não é lido
        self.assertEqual(db.esquecer_episodios(self.con), 1)
        self.assertEqual(len(self.episodios()), 2)
        self.assertEqual(db.esquecer_episodios(self.con), 0)

    def test_sem_memoria_o_grafo_nao_le_nem_grava_episodio(self):
        self.semear(dias=1, veredito="rejeitado")
        grafo_mod.MEMORIA = False
        try:
            e = self.rodar("TKT-0007")
        finally:
            grafo_mod.MEMORIA = True
        self.assertIsNone(e.confirmacoes[-1]["pendencia"]["precedentes"])
        self.assertEqual(len(self.episodios()), 1)                     # só o semeado

    # ---------------------------------------------------------------- memória procedural

    def sistema_do_redigir(self):
        """O prompt de sistema da última chamada ao modelo, que é a do nó `redigir`."""
        return self.modelo.pedidos[-1]["messages"][0]["content"]

    def test_as_regras_aprendidas_vao_ao_prompt_do_redigir_e_so_a_ele(self):
        e = self.rodar("TKT-0001")
        regras = grafo_mod._regras_aprendidas()
        self.assertTrue(regras)                                        # o arquivo em uso tem regra
        self.assertTrue(self.sistema_do_redigir().endswith(regras))
        self.assertNotIn(regras, self.modelo.pedidos[0]["messages"][0]["content"])   # a triagem
        self.assertIn(grafo_mod.REGRAS_REDIGIR.name, e.prompt)         # a combinação em uso, no log

    def test_sem_memoria_as_regras_aprendidas_nao_sao_carregadas(self):
        grafo_mod.MEMORIA = False
        try:
            e = self.rodar("TKT-0001")
        finally:
            grafo_mod.MEMORIA = True
        self.assertEqual(self.sistema_do_redigir(), grafo_mod._ler_prompt(grafo_mod.PROMPT_REDIGIR))
        self.assertNotIn(grafo_mod.REGRAS_REDIGIR.name, e.prompt)

    def test_regra_que_cita_cliente_ou_chamado_e_recusada(self):
        self.assertTrue(grafo_mod._regras_aprendidas())                # o arquivo em uso passa
        with tempfile.TemporaryDirectory() as pasta:
            for citado in ("CLI-07", "TKT-0001", "INC-0001"):
                arquivo = Path(pasta) / "regras.md"
                arquivo.write_text(f"<!-- cabeçalho: pode citar {citado} -->\n"
                                   f"- No caso do {citado}, não cite o domínio.", encoding="utf-8")
                with self.assertRaises(ValueError):
                    grafo_mod._regras_aprendidas(arquivo)
            # no cabeçalho de documentação o identificador é permitido: ele não vai ao modelo
            arquivo.write_text("<!-- origem: TKT-0001 -->\n- Não cite domínio não informado.",
                               encoding="utf-8")
            self.assertEqual(grafo_mod._regras_aprendidas(arquivo), "- Não cite domínio não informado.")
            # recusada na carga, a execução termina com motivo, e o modelo não é chamado para redigir
            arquivo.write_text("- No TKT-0001, não cite o domínio.", encoding="utf-8")
            original, grafo_mod.REGRAS_REDIGIR = grafo_mod.REGRAS_REDIGIR, arquivo
            try:
                e = self.rodar("TKT-0001")
            finally:
                grafo_mod.REGRAS_REDIGIR = original
        self.assertEqual(e.termino.value, "erro_fatal")
        self.assertIn("titular", e.motivo)
        self.assertEqual(len(self.modelo.pedidos), 1)                  # só a triagem
        self.assertIsNone(e.desfecho)

    # ---- a memória semântica (docs/memoria.md §4): fatos do cliente, confirmados pelo analista

    def test_fato_tem_vocabulario_fechado_e_o_valor_novo_substitui_o_antigo(self):
        for cliente, chave, valor in (("CLI-07", "acesso", "telnet"), ("CLI-07", "humor", "bom"),
                                      ("CLI-99", "acesso", "ssh")):
            with self.assertRaises(db.FatoRecusado):
                db.registrar_fato(self.con, cliente, chave, valor, por="teste")
        self.assertEqual(db.fatos_do_cliente(self.con, "CLI-07"), {})
        primeiro = db.registrar_fato(self.con, "CLI-07", "acesso", "painel", por="teste")
        repetido = db.registrar_fato(self.con, "CLI-07", "acesso", "painel", por="outra pessoa")
        self.assertEqual((primeiro["ja_existia"], repetido["ja_existia"]), (False, True))
        self.assertEqual((repetido["confirmado_por"], repetido["confirmado_em"]),      # a repetição não regrava
                         ("teste", primeiro["confirmado_em"]))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM fatos_cliente").fetchone()[0], 1)
        novo = db.registrar_fato(self.con, "CLI-07", "acesso", "ssh", por="teste")
        self.assertEqual((novo["valor"], novo["substituiu"]), ("ssh", "painel"))
        self.assertEqual({c: f["valor"] for c, f in db.fatos_do_cliente(self.con, "CLI-07").items()},
                         {"acesso": "ssh"})
        antigas = self.con.execute("SELECT valor FROM fatos_cliente WHERE substituido_em IS NOT NULL").fetchall()
        self.assertEqual([l["valor"] for l in antigas], ["painel"])     # o antigo fica, fechado

    def test_o_fato_vai_a_entrada_do_no_da_ressalva_e_a_tela_do_h1(self):
        db.registrar_fato(self.con, "CLI-07", "acesso", "ssh", por="teste")
        e = self.rodar("TKT-0007", confirmador=None)
        pedido_da_ressalva = self.modelo.pedidos[1]["messages"][1]["content"]
        self.assertIn("Fatos confirmados sobre o ambiente do cliente", pedido_da_ressalva)
        self.assertIn(db.FATOS_ACEITOS["acesso"]["ssh"], pedido_da_ressalva)
        self.assertNotIn("Fatos confirmados", self.modelo.pedidos[2]["messages"][1]["content"])   # não vai ao redigir
        self.assertEqual(e.pendencia["fatos_cliente"], {"acesso": "ssh"})
        passo = next(p for p in e.passos if p.ferramenta == "conferir_ressalva")
        self.assertEqual(passo.argumentos["fatos"], {"acesso": "ssh"})

    def test_sem_fato_a_entrada_do_no_da_ressalva_nao_muda(self):
        e = self.rodar("TKT-0007", confirmador=None)
        self.assertNotIn("Fatos confirmados", self.modelo.pedidos[1]["messages"][1]["content"])
        self.assertEqual(e.pendencia["fatos_cliente"], {})

    def test_o_fato_nao_decide_quem_baixa_o_score_e_a_resposta_do_no(self):
        db.registrar_fato(self.con, "CLI-07", "acesso", "ssh", por="teste")
        e = self.rodar("TKT-0007")                                     # o modelo diz que não cai
        self.assertEqual(e.desfecho["acao"], "abrir_chamado_interno")
        self.assertEqual(verificar("TKT-0007", e, self.con), (True, []))
        self.con.close()
        db.recriar_banco()
        self.con = db.conectar()
        db.registrar_fato(self.con, "CLI-07", "acesso", "ssh", por="teste")
        e = self.rodar("TKT-0007", [triagem("tecnico", termos=UPLOAD), ressalva(True, "ssh"),
                                    texto("O guia KB-102 não cobre acesso por SSH; encaminhado ao analista.")])
        self.assertEqual(e.desfecho["acao"], "fila_humana")
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)

    def test_sem_memoria_o_fato_nao_e_lido(self):
        db.registrar_fato(self.con, "CLI-07", "acesso", "ssh", por="teste")
        grafo_mod.MEMORIA = False
        try:
            e = self.rodar("TKT-0007", confirmador=None)
        finally:
            grafo_mod.MEMORIA = True
        self.assertNotIn("Fatos confirmados", self.modelo.pedidos[1]["messages"][1]["content"])
        self.assertIsNone(e.pendencia["fatos_cliente"])

    # ---- a memória procedural que existe (docs/memoria.md §5): motivo da rejeição e candidatas

    def rejeitar(self, ticket, motivo=None):
        self.rodar(ticket, confirmador=None)
        return retomar_grafo(ticket, "rejeitar", client=ModeloRoteirizado([]), con=self.con,
                             verbose=False, motivo_rejeicao=motivo)

    def test_rejeitar_com_motivo_grava_o_motivo_no_episodio_e_na_confirmacao(self):
        e = self.rejeitar("TKT-0007", "caso_fora_do_guia")
        self.assertEqual(e.confirmacoes[-1]["motivo_rejeicao"], "caso_fora_do_guia")
        (ep,) = self.episodios()
        self.assertEqual((ep["veredito"], ep["motivo_rejeicao"]), ("rejeitado", "caso_fora_do_guia"))
        self.assertEqual(e.desfecho["motivo"], "acao_rejeitada")       # o desfecho gravado não muda

    def test_rejeitar_sem_motivo_continua_valendo(self):
        e = self.rejeitar("TKT-0007")
        self.assertNotIn("motivo_rejeicao", e.confirmacoes[-1])
        self.assertIsNone(self.episodios()[0]["motivo_rejeicao"])
        self.assertNotIn("Motivo informado", e.saida.resultado.texto)

    def test_o_motivo_da_rejeicao_vai_ao_texto_da_fila_humana(self):
        e = self.rejeitar("TKT-0007", "guia_errado")
        self.assertIn("Motivo informado pelo analista: guia_errado.", e.saida.resultado.texto)
        (linha,) = self.con.execute("SELECT mensagem FROM encaminhamentos WHERE ticket_externo = 'TKT-0007'"
                                    " AND destino = 'fila_humana'").fetchall()
        self.assertIn("guia_errado", linha["mensagem"])               # é o texto gravado, não só o da tela
        e = self.rejeitar("TKT-0005", "informacao_suficiente")         # e no pedido ao cliente (H2)
        self.assertIn("Motivo informado pelo analista: informacao_suficiente.", e.saida.resultado.texto)

    def test_motivo_invalido_ou_com_aprovacao_e_recusado_sem_gastar_a_resposta(self):
        self.rodar("TKT-0007", confirmador=None)
        for decisao, motivo in (("rejeitar", "nao_gostei"), ("aprovar", "guia_errado")):
            with self.assertRaises(ValueError):
                retomar_grafo("TKT-0007", decisao, client=ModeloRoteirizado([]), con=self.con,
                              verbose=False, motivo_rejeicao=motivo)
        self.assertEqual(len(db.pendencias_aguardando(self.con, "TKT-0007")), 1)   # a pausa continua
        self.assertEqual(self.episodios(), [])

    def test_a_tela_separa_as_rejeicoes_por_motivo(self):
        self.rejeitar("TKT-0007", "guia_errado")
        self.rejeitar("TKT-0007")
        p = self.rodar("TKT-0007", confirmador=None).pendencia
        self.assertEqual(p["precedentes"]["guia"]["rejeicoes_por_motivo"], {"guia_errado": 1, "sem motivo": 1})
        import io, contextlib, main
        tela = io.StringIO()
        with contextlib.redirect_stdout(tela):
            main.mostrar_pendencia(p)
        self.assertIn("2 rejeitada(s) (1 sem motivo, 1 guia_errado)", tela.getvalue())

    def test_candidata_a_regra_exige_tres_correcoes_recentes_do_mesmo_padrao(self):
        self.rejeitar("TKT-0007", "caso_fora_do_guia")
        self.rejeitar("TKT-0007", "caso_fora_do_guia")
        self.rejeitar("TKT-0007", "resumo_ruim")
        self.assertEqual(db.candidatas_a_regra(self.con), [])          # 2 + 1: nenhum padrão chegou a 3
        self.rejeitar("TKT-0007", "caso_fora_do_guia")
        antes = self.episodios()
        (c,) = db.candidatas_a_regra(self.con)
        self.assertEqual((c["kb_id"], c["padrao"], c["quantidade"], c["chamados"]),
                         ("KB-102", "caso_fora_do_guia", 3, ["TKT-0007"]))
        self.assertIn("nao_cobre", c["destino"])
        self.assertEqual(self.episodios(), antes)                      # o relatório só lê
        depois = datetime.now().astimezone() + timedelta(days=db.EPISODIO_RECENTE_DIAS + 1)
        self.assertEqual(db.candidatas_a_regra(self.con, agora=depois), [])   # correção antiga não conta

    def test_o_laco_recusa_o_motivo_da_rejeicao(self):
        from test_offline import ModeloRoteirizado as ModeloDoLaco, ROTEIROS as ROTEIROS_DO_LACO
        from agente import rodar
        rodar("TKT-0007", client=ModeloDoLaco(ROTEIROS_DO_LACO["TKT-0007"]), modelo="fake", con=self.con,
              verbose=False)
        with self.assertRaises(EdicaoRecusada):
            retomar("TKT-0007", "rejeitar", client=ModeloDoLaco([]), con=self.con, verbose=False,
                    motivo_rejeicao="guia_errado")
        self.assertEqual(len(db.pendencias_aguardando(self.con, "TKT-0007")), 1)


if __name__ == "__main__":
    unittest.main()


class TestEditor(unittest.TestCase):
    """main.editar_no_editor (--aprovar X --editar): o analista parte do texto proposto. A
    conferência do texto não é daqui: segue pelo caminho do --resumo e do --mensagem."""

    def editor(self, corpo: str) -> str:
        """Um 'editor' de mentira: um script que reescreve o arquivo, como a pessoa faria."""
        pasta = tempfile.mkdtemp()
        script = Path(pasta) / "editor.py"
        script.write_text("import sys, pathlib\n"
                          "p = pathlib.Path(sys.argv[1])\n"
                          "t = p.read_text(encoding='utf-8')\n"
                          f"p.write_text({corpo}, encoding='utf-8')\n", encoding="utf-8")
        return f'"{sys.executable}" "{script}"'

    def test_devolve_o_texto_editado_sem_as_linhas_de_aviso(self):
        import main
        editado = main.editar_no_editor("Resumo do modelo.",
                                        editor=self.editor("t.replace('do modelo', 'do analista')"))
        self.assertEqual(editado, "Resumo do analista.")

    def test_sem_mudar_nada_devolve_o_texto_proposto(self):
        import main
        self.assertEqual(main.editar_no_editor("Resumo do modelo.", editor=self.editor("t")),
                         "Resumo do modelo.")

    def test_texto_apagado_nao_aprova_nada(self):
        import main
        self.assertIsNone(main.editar_no_editor("Resumo do modelo.", editor=self.editor("''")))

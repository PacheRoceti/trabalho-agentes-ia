"""Testes OFFLINE do grafo (src/grafo.py): sem chave e sem rede, com um "modelo" roteirizado.

Provam o que é do CÓDIGO no grafo: a rota, o nó `decidir` (portão de confiança e divergência),
o avaliador do texto, a pausa com `interrupt`, a retomada e os términos. NÃO provam que um modelo
real classifica certo: isso só `python src/main.py --todos --auto-aprovar` mede.

    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

os.environ["CHECKPOINT_DB"] = ":memory:"     # antes de importar o grafo: nada de arquivo nos testes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db                                    # noqa: E402
from agente import EdicaoRecusada, Orcamento, Termino, retomar, vencer_pendencias  # noqa: E402
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


SIM = lambda p: (True, "teste")
NAO = lambda p: (False, "teste")
UPLOAD = ("permissao", "negada", "upload")

ROTEIROS = {
    "TKT-0001": [triagem("tecnico", termos=("certificado", "ssl", "renovacao", "vencido")),
                 texto("Rodar certbot renew --dry-run e conferir a porta 80.")],
    # o KB-106 volta com score alto (a armadilha): quem manda à fila humana é o sinal de divergência
    "TKT-0002": [triagem("tecnico", diverge=True, termos=("dns", "resolucao", "nameserver", "dominio")),
                 texto("Divergência: o cliente relata Webmail fora do ar, mas o log anexado aponta falha de DNS.")],
    "TKT-0003": [triagem("tecnico", termos=UPLOAD),
                 texto("Permissão negada ao gravar arquivos. Cliente afirma ser a 3a vez; o histórico "
                       "do sistema confirma 1 ocorrência anterior (INC-0001).")],
    "TKT-0007": [triagem("tecnico", termos=UPLOAD),
                 texto("Permissão negada ao gravar arquivos; todo upload do site falha. Procedimento KB-102.")],
    "TKT-0999": [texto("Id TKT-0999 não existe no sistema de tickets.")],
    "TKT-0004": [triagem("comercial"), texto("Pedido de upgrade de plano: assunto comercial.")],
    "TKT-0005": [triagem("insuficiente"),
                 texto("Informe o serviço afetado, o erro observado e desde quando ocorre.")],
    # o KB-104 não cobre falha intermitente (ressalva): o score vem reduzido e o código decide
    "TKT-0006": [triagem("tecnico", termos=("502", "erro", "deploy", "intermitente")),
                 texto("KB-104 cobre falha constante; o relato é intermitente (score abaixo do limiar).")],
}


class TestGrafo(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()

    def tearDown(self):
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
        self.assertEqual(nos, {"entrada", "consultar", "triagem", "buscar", "decidir", "redigir",
                               "validar", "pedir_confirmacao", "confirmar", "gravar", "finalizar"})
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
        e = self.rodar("TKT-0005")                                     # outra execução, mesmo chamado
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

    def test_pedido_ao_cliente_com_informacao_interna_e_reescrito(self):
        e = self.rodar("TKT-0005", [triagem("insuficiente"),
                                    texto("Consultamos o KB-102 e a fila humana vai priorizar seu caso."),
                                    texto("Informe o serviço afetado, o erro observado e desde quando ocorre.")])
        self.assertEqual(e.desfecho["acao"], "devolver_cliente")
        self.assertEqual(self.nos(e).count("redigir"), 2)
        self.assertIn("informação interna", e.passos[4].erro["erro"])   # o passo do nó validar
        msg = self.con.execute("SELECT mensagem FROM encaminhamentos WHERE ticket_externo = 'TKT-0005'").fetchone()[0]
        self.assertNotIn("KB-102", msg)

    def test_texto_recusado_duas_vezes_termina_em_erro_fatal_sem_gravar(self):
        e = self.rodar("TKT-0005", [triagem("insuficiente"), texto("Veja o KB-102, prioridade P1.")])
        self.assertEqual(e.termino, Termino.ERRO_FATAL)
        self.assertIn("recusado em 2 tentativas", e.motivo)
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0005"), 0)

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
        self.assertEqual(e.n_chamadas_modelo, 2)                       # a retomada não chama o modelo
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
        self.assertEqual(e.n_chamadas_modelo, 2)                            # editar não chama o modelo

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


if __name__ == "__main__":
    unittest.main()

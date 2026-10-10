"""Testes OFFLINE: rodam sem chave e sem rede, com um "modelo" roteirizado.

Provam o que é do CÓDIGO (laço, portão de confiança, confirmação humana,
orçamento, idempotência, verificador). NÃO provam que um modelo real escolhe as
ferramentas certas — isso é o que src/main.py --todos mede, com o modelo de verdade.

    python -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import db                                    # noqa: E402
from agente import Orcamento, Termino, rodar  # noqa: E402
from verificar import verificar              # noqa: E402


def chamada(i, nome, **args):
    return NS(id=f"c{i}", function=NS(name=nome, arguments=json.dumps(args)))


def turno(*chamadas, texto=""):
    return NS(content=texto, tool_calls=list(chamadas) or None)


class ModeloRoteirizado:
    """Devolve, em ordem, as mensagens do roteiro. Cada chamada gasta 1000 tokens de entrada e 50 de saída."""

    def __init__(self, roteiro):
        self.roteiro, self.i = list(roteiro), 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        msg = self.roteiro[min(self.i, len(self.roteiro) - 1)]
        self.i += 1
        return NS(usage=NS(prompt_tokens=1000, completion_tokens=50), choices=[NS(message=msg)])


SIM = lambda p: (True, "teste")
NAO = lambda p: (False, "teste")

ROTEIROS = {
    "TKT-0001": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0001")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["certificado", "ssl", "renovacao", "vencido"])),
                 turno(chamada(3, "registrar_encaminhamento", id_ticket="TKT-0001", destino="anotacao_interna",
                               mensagem="Rodar certbot renew --dry-run e conferir a porta 80.", kb_id="KB-101")),
                 turno(texto="Correção sugerida registrada para o analista.")],
    # divergência: relato "Webmail" × log de DNS; existe KB de DNS com score alto (a armadilha),
    # mas o correto é fila humana sinalizando a divergência
    "TKT-0002": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0002")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["dns", "resolucao", "nameserver", "dominio"])),
                 turno(chamada(3, "registrar_encaminhamento", id_ticket="TKT-0002", destino="fila_humana",
                               mensagem="Divergência: o cliente relata Webmail fora do ar, mas o log anexado aponta falha de DNS.")),
                 turno(texto="Encaminhado à fila humana com a divergência sinalizada.")],
    "TKT-0003": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0003")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["disco", "espaco", "cheio"])),
                 turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0003", kb_id="KB-102",
                               resumo="Disco cheio. Cliente afirma ser a 3a vez; o histórico do sistema confirma 1 ocorrência anterior (INC-0001).")),
                 turno(texto="Chamado aberto para a Infraestrutura.")],
    "TKT-0007": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0007")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["disco", "espaco", "cheio"])),
                 turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0007", kb_id="KB-102",
                               resumo="Disco do servidor cheio; sistemas pararam de gravar arquivos. Procedimento KB-102.")),
                 turno(texto="Chamado aberto para a Infraestrutura.")],
    "TKT-0999": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0999")),
                 turno(chamada(2, "registrar_encaminhamento", id_ticket="TKT-0999", destino="fila_humana",
                               mensagem="Id TKT-0999 não existe no sistema de tickets.")),
                 turno(texto="Encaminhado à fila humana.")],
    "TKT-0004": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0004")),
                 turno(chamada(2, "registrar_encaminhamento", id_ticket="TKT-0004", destino="fila_comercial",
                               mensagem="Pedido de upgrade de plano: assunto comercial.")),
                 turno(texto="Redirecionado ao comercial.")],
    "TKT-0005": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0005")),
                 turno(chamada(2, "registrar_encaminhamento", id_ticket="TKT-0005", destino="devolver_cliente",
                               mensagem="Informe o serviço afetado, o erro observado e desde quando ocorre.")),
                 turno(texto="Devolvido ao cliente.")],
    # o modelo TENTA abrir chamado, mas o KB-104 não cobre falha intermitente (ressalva): o score
    # vem reduzido, o portão recusa e ele se corrige
    "TKT-0006": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0006")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["502", "erro", "deploy", "intermitente"])),
                 turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0006", kb_id="KB-104",
                               resumo="Erro 502 intermitente após deploy, procedimento KB-104.")),
                 turno(chamada(4, "registrar_encaminhamento", id_ticket="TKT-0006", destino="fila_humana",
                               mensagem="KB-104 cobre falha constante; o relato é intermitente (score abaixo do limiar).")),
                 turno(texto="Encaminhado à fila humana.")],
}


class TestAgente(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()

    def tearDown(self):
        self.con.close()

    def rodar(self, ticket, roteiro=None, **kw):
        return rodar(ticket, client=ModeloRoteirizado(roteiro or ROTEIROS[ticket]),
                     modelo="fake", con=self.con, verbose=False,
                     confirmador=kw.pop("confirmador", SIM), **kw)

    def test_todos_os_casos_passam_no_verificador(self):
        for ticket in ROTEIROS:
            with self.subTest(ticket=ticket):
                self.con.close()
                db.recriar_banco()
                self.con = db.conectar()
                e = self.rodar(ticket)
                ok, falhas = verificar(ticket, e, self.con)
                self.assertTrue(ok, falhas)

    def test_modelo_recebe_o_anexo_de_log(self):
        e = self.rodar("TKT-0002")
        self.assertIn("DNS", e.passos[0].resultado["anexo_log"])

    def test_entrada_e_o_texto_e_consultar_ticket_nao_o_repete(self):
        e = self.rodar("TKT-0002")
        entrada = e.historico[1]["content"]
        self.assertIn("Meu Webmail está fora do ar", entrada)
        self.assertIn("TKT-0002", entrada)
        self.assertIn("CLI-06", entrada)
        self.assertNotIn("texto", e.passos[0].resultado)

    def test_um_pedido_de_informacao_por_chamado(self):
        self.rodar("TKT-0005")
        e = self.rodar("TKT-0005")                           # outra execução, mesmo chamado
        self.assertIn("já recebeu um pedido", e.passos[1].erro["erro"])
        self.assertEqual(db.contar_pedidos_cliente(self.con, "TKT-0005"), 1)

    def test_verificador_aceita_pedido_mais_desfecho_final(self):
        e = self.rodar("TKT-0005")
        db.registrar_encaminhamento(self.con, "TKT-0005", "fila_humana", "Resposta do cliente ainda insuficiente.", None)
        self.assertEqual(verificar("TKT-0005", e, self.con), (True, []))
        db.registrar_encaminhamento(self.con, "TKT-0005", "devolver_cliente", "Segundo pedido, indevido.", None)
        self.assertIn("pedidos de informação", verificar("TKT-0005", e, self.con)[1][0])

    def test_resumo_que_so_repete_o_cliente_reprova_na_reincidencia(self):
        roteiro = list(ROTEIROS["TKT-0003"])
        roteiro[2] = turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0003", kb_id="KB-102",
                                   resumo="O cliente relata que é a terceira vez que o disco enche."))
        e = self.rodar("TKT-0003", roteiro=roteiro)
        ok, falhas = verificar("TKT-0003", e, self.con)
        self.assertFalse(ok)
        self.assertIn("histórico", falhas[0])

    def test_busca_quebra_frases_e_casa_encheu_com_cheio(self):
        for termos in (["disco", "encheu"], ["disco cheio", "gravar arquivos"],
                       ["disco", "encheu", "sistemas", "pararam", "gravar"]):
            with self.subTest(termos=termos):
                melhor = db.buscar_kb(self.con, termos)[0]
                self.assertEqual(melhor["kb_id"], "KB-102")
                self.assertGreaterEqual(melhor["score"], 0.5)

    def test_um_termo_casado_nao_passa_do_limiar(self):
        self.assertLess(db.buscar_kb(self.con, ["site", "erro", "502"])[0]["score"], 0.5)
        self.assertLess(db.buscar_kb(self.con, ["disco"])[0]["score"], 0.5)

    def test_ressalva_do_procedimento_vem_do_texto_do_cliente(self):
        # termos que casam por inteiro com o KB-104; quem barra é o relato ("de vez em quando")
        relato = db.buscar_ticket(self.con, "TKT-0006")["texto"]
        sem = db.buscar_kb(self.con, ["502", "deploy"])[0]
        com = db.buscar_kb(self.con, ["502", "deploy"], relato=relato)[0]
        self.assertGreaterEqual(sem["score"], 0.5)
        self.assertLess(com["score"], 0.5)
        self.assertIn("NÃO cobre", com["ressalva"])

    def test_chamado_indevido_do_tkt_0006_e_barrado_mesmo_com_termos_que_casam(self):
        roteiro = list(ROTEIROS["TKT-0006"])
        roteiro[1] = turno(chamada(2, "buscar_base_conhecimento", termos=["erro", "502", "deploy"]))
        e = self.rodar("TKT-0006", roteiro=roteiro)
        self.assertIn("limiar", e.passos[2].erro["erro"])
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0006"), 0)

    def test_tkt_0007_abre_chamado_com_os_termos_das_rodadas_reais(self):
        roteiro = list(ROTEIROS["TKT-0007"])
        roteiro[1] = turno(chamada(2, "buscar_base_conhecimento", termos=["disco", "cheio", "arquivos", "gravar"]))
        e = self.rodar("TKT-0007", roteiro=roteiro)
        self.assertEqual(verificar("TKT-0007", e, self.con), (True, []))

    def test_fila_humana_sem_busca_e_recusada_para_chamado_existente(self):
        fila = turno(chamada(2, "registrar_encaminhamento", id_ticket="TKT-0003", destino="fila_humana",
                             mensagem="Cliente afirma terceira vez; o histórico mostra uma."))
        roteiro = [ROTEIROS["TKT-0003"][0], fila] + ROTEIROS["TKT-0003"][1:]
        e = self.rodar("TKT-0003", roteiro=roteiro)
        self.assertIn("sem nenhuma busca", e.passos[1].erro["erro"])
        self.assertEqual(e.desfecho["acao"], "abrir_chamado_interno")   # seguiu o procedimento

    def test_pedido_fora_da_alcada_vai_a_fila_humana_sem_busca(self):
        roteiro = [ROTEIROS["TKT-0003"][0],
                   turno(chamada(2, "registrar_encaminhamento", id_ticket="TKT-0003", destino="fila_humana",
                                 motivo="fora_da_alcada", mensagem="O cliente pede só a mudança de prioridade.")),
                   turno(texto="Encaminhado à fila humana.")]
        e = self.rodar("TKT-0003", roteiro=roteiro)
        self.assertEqual(e.termino, Termino.RESPONDEU)
        self.assertEqual(e.desfecho["motivo"], "fora_da_alcada")
        self.assertEqual(e.n_buscas, 0)

    def test_pedido_ao_cliente_nao_cita_informacao_interna(self):
        vazado = turno(chamada(2, "registrar_encaminhamento", id_ticket="TKT-0005", destino="devolver_cliente",
                               mensagem="Sem detalhes não achamos procedimento (KB-102); a Infraestrutura dará prioridade."))
        roteiro = [ROTEIROS["TKT-0005"][0], vazado] + ROTEIROS["TKT-0005"][1:]
        e = self.rodar("TKT-0005", roteiro=roteiro)
        for termo in ("kb-102", "procedimento", "prioridade", "Infraestrutura"):
            self.assertIn(termo, e.passos[1].erro["recebido"])
        self.assertEqual(e.desfecho["acao"], "devolver_cliente")
        self.assertEqual(db.contar_pedidos_cliente(self.con, "TKT-0005"), 1)

    def test_erro_de_ferramenta_volta_como_dado(self):
        e = self.rodar("TKT-0999")
        self.assertIn("sugestao", e.passos[0].erro)
        self.assertEqual(e.termino, Termino.RESPONDEU)

    def test_portao_de_confianca_recusa_abertura_com_score_baixo(self):
        e = self.rodar("TKT-0006")
        self.assertEqual(e.passos[2].ferramenta, "abrir_chamado_interno")
        self.assertIn("limiar", e.passos[2].erro["erro"])
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0006"), 0)

    def test_sem_confirmacao_do_analista_nada_e_gravado(self):
        e = self.rodar("TKT-0003", confirmador=NAO)
        self.assertEqual(e.termino, Termino.HUMANO)
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0003"), 0)
        self.assertEqual(e.pendencia["ferramenta"], "abrir_chamado_interno")

    def test_reincidencia_sobe_prioridade_no_codigo_nao_no_modelo(self):
        e = self.rodar("TKT-0003")
        self.assertEqual(e.desfecho["prioridade"], "P1")            # base P2 + reincidência
        self.assertEqual(e.desfecho["reincidencias_confirmadas_no_sistema"], 1)

    def test_orcamento_de_passos(self):
        e = self.rodar("TKT-0001", orcamento=Orcamento(max_passos=1))
        self.assertEqual(e.termino, Termino.ORCAMENTO)
        self.assertIn("passos", e.motivo)

    def test_orcamento_de_custo(self):
        e = self.rodar("TKT-0001", preco_usd_por_mtok=(1000.0, 1000.0), orcamento=Orcamento(max_usd=0.5))
        self.assertEqual(e.termino, Termino.ORCAMENTO)
        self.assertIn("custo", e.motivo)

    def test_encerrar_sem_desfecho_e_erro_fatal(self):
        e = self.rodar("TKT-0001", roteiro=[turno(texto="pronto!")])
        self.assertEqual(e.termino, Termino.ERRO_FATAL)      # depois de 2 lembretes sem efeito
        self.assertEqual(e.lembretes, 2)
        self.assertIn("sem registrar", e.motivo)

    def test_lembrete_faz_o_modelo_registrar_o_desfecho(self):
        roteiro = [turno(texto="Encaminhei para a fila humana."),       # narrou, não chamou
                   turno(chamada(1, "registrar_encaminhamento", id_ticket="TKT-0999", destino="fila_humana",
                                 mensagem="Id TKT-0999 não existe no sistema de tickets.")),
                   turno(texto="Encaminhado.")]
        e = self.rodar("TKT-0999", roteiro=roteiro)
        self.assertEqual(e.termino, Termino.RESPONDEU)
        self.assertEqual(e.lembretes, 1)
        self.assertEqual(db.contar(self.con, "encaminhamentos", "TKT-0999"), 1)

    def test_idempotencia_nao_duplica_chamado(self):
        e1 = self.rodar("TKT-0003")
        e2 = self.rodar("TKT-0003")
        self.assertEqual(e1.desfecho["chamado_interno"], e2.desfecho["chamado_interno"])
        self.assertTrue(e2.desfecho["ja_existia"])
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0003"), 1)

    def test_custo_e_tokens_acumulados(self):
        e = self.rodar("TKT-0004", preco_usd_por_mtok=(1.0, 2.0))
        n = e.n_chamadas_modelo
        self.assertEqual(e.tokens_entrada, 1000 * n)
        self.assertAlmostEqual(e.custo_usd, (1000 * n * 1.0 + 50 * n * 2.0) / 1e6)

    def test_log_da_trajetoria(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.rodar("TKT-0004", log_dir=Path(d))
            dados = json.loads((Path(d) / "TKT-0004.json").read_text(encoding="utf-8"))
            self.assertEqual(dados["termino"], "respondeu")
            self.assertEqual([p["ferramenta"] for p in dados["passos"]],
                             ["consultar_ticket", "registrar_encaminhamento"])


if __name__ == "__main__":
    unittest.main()

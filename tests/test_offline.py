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
                 turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0003", categoria="disco_cheio", kb_id="KB-102",
                               resumo="Disco cheio. Cliente afirma ser a 3a vez; o histórico do sistema confirma 1 ocorrência anterior (INC-0001).")),
                 turno(texto="Chamado aberto para a Infraestrutura.")],
    "TKT-0007": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0007")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["disco", "espaco", "cheio"])),
                 turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0007", categoria="disco_cheio", kb_id="KB-102",
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
    # o modelo TENTA abrir chamado com score 0.44 (< 0.5): o portão recusa e ele se corrige
    "TKT-0006": [turno(chamada(1, "consultar_ticket", id_ticket="TKT-0006")),
                 turno(chamada(2, "buscar_base_conhecimento", termos=["502", "erro", "deploy", "intermitente"])),
                 turno(chamada(3, "abrir_chamado_interno", id_ticket="TKT-0006", categoria="site_fora_do_ar", kb_id="KB-104",
                               resumo="Erro 502 intermitente após deploy, procedimento KB-104.")),
                 turno(chamada(4, "registrar_encaminhamento", id_ticket="TKT-0006", destino="fila_humana",
                               mensagem="KB-104 cobre falha constante; o relato é intermitente (score 0.44).")),
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

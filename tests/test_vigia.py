"""Testes OFFLINE do vigia do prazo (src/vigiar_prazos.py) e da trava das respostas (db.py).

Provam o que é do CÓDIGO: a volta vence só o que passou do prazo, o vigia dorme até o próximo
`vence_em`, um erro numa volta não o derruba, só um vigia roda por máquina, e duas respostas à
mesma pendência dadas ao mesmo tempo (o vigia e o analista) gravam um desfecho só. A espera real
de 20 minutos, com o modelo real, vai para logs/grafo-prazo-vigia/ (docs/humano.md §4.1).

    python -m unittest tests.test_vigia -v
"""
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path

os.environ["CHECKPOINT_DB"] = ":memory:"     # antes de importar o grafo: nada de arquivo nos testes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db                                    # noqa: E402
import grafo as grafo_mod                    # noqa: E402
import vigiar_prazos as vigia                # noqa: E402
from agente import retomar                   # noqa: E402
from grafo import rodar_grafo                # noqa: E402
from test_grafo import ROTEIROS, ModeloRoteirizado   # noqa: E402


def agora(minutos=0):
    return datetime.now().astimezone() + timedelta(minutes=minutos)


def responder_em_outra_conexao(ticket, decisao, quando, resultados):
    """Como um outro processo faria: conexão própria com o banco, e a retomada pela porta de
    entrada (agente.retomar), que é a que passa pela trava."""
    con = db.conectar()
    try:
        resultados[decisao] = retomar(ticket, decisao, client=ModeloRoteirizado([]), con=con,
                                      agora=quando, verbose=False)
    finally:
        con.close()


class TestVigia(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()
        self._busca, grafo_mod.BUSCA = grafo_mod.BUSCA, "palavra"
        self.pasta = tempfile.TemporaryDirectory()
        self._batimento, vigia.BATIMENTO = vigia.BATIMENTO, Path(self.pasta.name) / "batimento.json"

    def tearDown(self):
        grafo_mod.BUSCA = self._busca
        vigia.BATIMENTO = self._batimento
        self.con.close()
        self.pasta.cleanup()

    def pausar(self, ticket, **kw):
        """Sem confirmador: a execução para no `interrupt` e a pendência fica com prazo."""
        return rodar_grafo(ticket, client=ModeloRoteirizado(ROTEIROS[ticket]), modelo="fake",
                           con=self.con, verbose=False, confirmador=None, **kw)

    def aguardando(self):
        return [p["ticket_externo"] for p in db.pendencias_aguardando(self.con)]

    def desfechos(self, ticket):
        return (db.contar(self.con, "chamados_internos", ticket)
                + db.contar(self.con, "encaminhamentos", ticket))

    # ---- a volta

    def test_a_volta_vence_so_o_que_passou_do_prazo(self):
        self.pausar("TKT-0007")                                   # 20 minutos
        self.pausar("TKT-0003", prazo_confirmacao_min=1)          # seria P1
        vencidos = vigia.uma_volta(ModeloRoteirizado([]), self.con, agora=agora(2))
        self.assertEqual([e.id_ticket for e in vencidos], ["TKT-0003"])
        (e,) = vencidos
        self.assertEqual((e.desfecho["acao"], e.desfecho["motivo"]),
                         ("fila_humana", "confirmacao_nao_recebida"))
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0003"), 0)
        self.assertEqual(db.contar(self.con, "avisos_gestor", "TKT-0003"), 1)
        self.assertEqual(self.aguardando(), ["TKT-0007"])

    def test_pendencia_no_prazo_nao_e_tocada(self):
        self.pausar("TKT-0007")
        self.assertEqual(vigia.uma_volta(ModeloRoteirizado([]), self.con, agora=agora(19)), [])
        self.assertEqual(self.aguardando(), ["TKT-0007"])
        self.assertEqual(self.desfechos("TKT-0007"), 0)

    def test_o_vigia_dorme_ate_o_proximo_prazo_e_nunca_mais_que_o_teto(self):
        self.assertEqual(vigia.proxima_espera(self.con, teto=30), 30)          # nada pendente
        self.pausar("TKT-0003", prazo_confirmacao_min=0.5)                     # vence em 30 s
        self.assertAlmostEqual(vigia.proxima_espera(self.con, agora=agora(), teto=600), 31, delta=2)
        self.assertEqual(vigia.proxima_espera(self.con, agora=agora(), teto=10), 10)
        self.assertEqual(vigia.proxima_espera(self.con, agora=agora(5), teto=10), 1.0)  # já venceu

    def test_a_volta_protegida_grava_o_sinal_de_vida(self):
        self.pausar("TKT-0007")
        vencidos, espera = vigia.volta_protegida(ModeloRoteirizado([]), teto=30)
        self.assertEqual((vencidos, espera), ([], 30))
        b = vigia.BATIMENTO.read_text(encoding="utf-8")
        self.assertIn('"aguardando": 1', b)
        self.assertIn(f'"pid": {os.getpid()}', b)

    def test_erro_numa_volta_nao_derruba_o_vigia(self):
        def banco_travado():
            raise sqlite3.OperationalError("database is locked")
        with self.assertLogs("vigia", "ERROR"):
            self.assertEqual(vigia.volta_protegida(ModeloRoteirizado([]), teto=7,
                                                   conectar=banco_travado), (None, 7))
        self.assertFalse(vigia.BATIMENTO.exists())           # volta que falhou não é sinal de vida

    def test_a_volta_termina_a_execucao_que_caiu_no_meio_da_escrita(self):
        """O vigia também faz a recuperação (docs/humano.md §4.3): o TKT-0007 aprovado caiu antes
        de gravar o chamado, e a volta seguinte, passada a idade mínima, o termina uma vez só."""
        from unittest import mock
        self.pausar("TKT-0007")
        original = db.abrir_chamado
        def caiu(*a, **kw):
            raise RuntimeError("queda")
        with mock.patch.object(db, "abrir_chamado", caiu), self.assertRaises(RuntimeError):
            retomar("TKT-0007", "aprovar", client=ModeloRoteirizado([]), con=self.con, verbose=False)
        self.assertIs(db.abrir_chamado, original)
        self.assertEqual(vigia.uma_volta(ModeloRoteirizado([]), self.con, agora=agora(1)), [])
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 0)   # ainda recente
        with self.assertLogs("vigia", "WARNING") as registro:
            vigia.uma_volta(ModeloRoteirizado([]), self.con, agora=agora(10),
                            log_dir=Path(self.pasta.name))
        self.assertIn("EXECUÇÃO RETOMADA DEPOIS DE QUEDA: TKT-0007", "\n".join(registro.output))
        self.assertEqual(db.contar(self.con, "chamados_internos", "TKT-0007"), 1)

    # ---- um vigia só, e a situação que o --pendencias mostra

    def test_um_vigia_por_maquina_e_a_situacao_diz_se_ele_roda(self):
        trava = Path(self.pasta.name) / "vigia.lock"
        primeiro = db.travar_instancia(trava)
        self.assertIsNotNone(primeiro)
        try:
            self.assertIsNone(db.travar_instancia(trava))   # o segundo vigia não sobe
            self.assertTrue(vigia.situacao(vigia.BATIMENTO, trava).startswith("vigia do prazo: rodando"))
        finally:
            db._destravar(primeiro)
            primeiro.close()
        self.assertIn("PARADO", vigia.situacao(vigia.BATIMENTO, trava))

    # ---- a trava das respostas

    def test_a_resposta_espera_quem_esta_respondendo(self):
        self.pausar("TKT-0007")
        resultados = {}
        outro = threading.Thread(target=responder_em_outra_conexao,
                                 args=("TKT-0007", "aprovar", agora(), resultados))
        with db.trava_das_respostas():                      # alguém está respondendo
            outro.start()
            outro.join(0.5)
            self.assertTrue(outro.is_alive())               # o outro espera
            self.assertEqual(self.desfechos("TKT-0007"), 0)
        outro.join(10)
        self.assertFalse(outro.is_alive())
        self.assertEqual(resultados["aprovar"].desfecho["acao"], "abrir_chamado_interno")

    def test_duas_respostas_ao_mesmo_tempo_gravam_um_desfecho_so(self):
        """O vigia vence e o analista aprova no mesmo instante: só um dos dois grava."""
        self.pausar("TKT-0003", prazo_confirmacao_min=1)
        resultados = {}
        linhas = [threading.Thread(target=responder_em_outra_conexao, args=a) for a in
                  (("TKT-0003", "aprovar", agora(), resultados),
                   ("TKT-0003", "vencer", agora(2), resultados))]
        for t in linhas:
            t.start()
        for t in linhas:
            t.join(20)
        self.assertEqual(sorted(k for k, e in resultados.items() if e is not None).__len__(), 1)
        self.assertEqual(self.desfechos("TKT-0003"), 1)
        self.assertEqual(self.aguardando(), [])


if __name__ == "__main__":
    unittest.main()

"""Testes OFFLINE da recuperação depois de uma queda (grafo.retomar_interrompidas, 17/10/2026).

Cada teste derruba o processo num ponto da escrita, com uma exceção forçada numa função de
`db.py`, e depois roda a recuperação. Provam o que é do CÓDIGO: a execução presa termina, nada é
gravado duas vezes, o texto editado pelo analista sobrevive, o log é escrito e o checkpoint é
apagado. As janelas J1 a J4 são as de docs/humano.md §4.3.

    python -m unittest tests.test_recuperacao -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ["CHECKPOINT_DB"] = ":memory:"     # antes de importar o grafo: nada de arquivo nos testes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import db                                    # noqa: E402
import grafo as grafo_mod                    # noqa: E402
from grafo import CHECKPOINTER, GRAFO, retomar_grafo, retomar_interrompidas, rodar_grafo  # noqa: E402
from test_grafo import ROTEIROS, SIM, ModeloRoteirizado   # noqa: E402

CORRIGIDO = "Upload falha com permissão negada desde hoje; o cliente não relatou restauração recente."


class Queda(Exception):
    """O processo caiu aqui."""


def agora(minutos=0):
    return datetime.now().astimezone() + timedelta(minutes=minutos)


def cai_em(nome, depois_de_gravar=True):
    """Troca db.<nome> por uma versão que derruba o processo, depois (ou antes) de fazer o que a
    função faz. Só a primeira chamada cai."""
    original = getattr(db, nome)
    estado = {"caiu": False}

    def com_queda(*a, **kw):
        if estado["caiu"]:
            return original(*a, **kw)
        estado["caiu"] = True
        if depois_de_gravar:
            original(*a, **kw)
        raise Queda(f"queda em db.{nome}")
    return mock.patch.object(db, nome, com_queda)


class TestRecuperacao(unittest.TestCase):
    def setUp(self):
        db.recriar_banco()
        self.con = db.conectar()
        self._busca, grafo_mod.BUSCA = grafo_mod.BUSCA, "palavra"
        for c in list(CHECKPOINTER.list(None)):           # cada teste parte sem execução guardada
            CHECKPOINTER.delete_thread(c.config["configurable"]["thread_id"])
        self.pasta = tempfile.TemporaryDirectory()
        self.logs = Path(self.pasta.name)

    def tearDown(self):
        grafo_mod.BUSCA = self._busca
        self.con.close()
        self.pasta.cleanup()

    def rodar(self, ticket, **kw):
        return rodar_grafo(ticket, client=ModeloRoteirizado(ROTEIROS[ticket]), modelo="fake", con=self.con,
                           verbose=False, log_dir=self.logs, confirmador=kw.pop("confirmador", SIM), **kw)

    def responder(self, ticket, decisao, minutos=0, **kw):
        return retomar_grafo(ticket, decisao, client=ModeloRoteirizado([]), con=self.con,
                             agora=agora(minutos), verbose=False, **kw)

    def recuperar(self, minutos=10):
        return retomar_interrompidas(client=ModeloRoteirizado([]), con=self.con, log_dir=self.logs,
                                     agora=agora(minutos))

    def contar(self, tabela, ticket):
        return db.contar(self.con, tabela, ticket)

    def proximo(self, ticket):
        return GRAFO.get_state({"configurable": {"thread_id": ticket}}).next

    def guardado(self, ticket):
        return bool(GRAFO.get_state({"configurable": {"thread_id": ticket}}).values)

    def log(self, ticket):
        return json.loads((self.logs / f"{ticket}.json").read_text(encoding="utf-8"))

    # ---- J3: caiu no meio da escrita

    def test_j3_anotacao_gravada_e_queda_a_recuperacao_nao_duplica(self):
        with cai_em("registrar_encaminhamento"), self.assertRaises(Queda):
            self.rodar("TKT-0001")
        self.assertEqual(self.proximo("TKT-0001"), ("gravar",))
        self.assertEqual(self.contar("encaminhamentos", "TKT-0001"), 1)    # gravou, e caiu
        (r,) = self.recuperar()
        self.assertEqual(r["parou_em"], "gravar")
        self.assertEqual(self.contar("encaminhamentos", "TKT-0001"), 1)    # a chave não deixou duplicar
        self.assertEqual(r["estado"].desfecho["acao"], "anotacao_interna")
        self.assertTrue(r["estado"].desfecho["ja_existia"])
        self.assertEqual(self.log("TKT-0001")["recuperacao"]["parou_em"], "gravar")
        self.assertFalse(self.guardado("TKT-0001"))                       # checkpoint apagado

    def test_j3_prazo_vencido_de_p1_nao_duplica_encaminhamento_nem_aviso(self):
        self.rodar("TKT-0003", confirmador=None, prazo_confirmacao_min=1)
        with cai_em("avisar_gestor"), self.assertRaises(Queda):
            self.responder("TKT-0003", "vencer", minutos=2)
        self.assertEqual((self.contar("encaminhamentos", "TKT-0003"),
                          self.contar("avisos_gestor", "TKT-0003")), (1, 1))
        (r,) = self.recuperar()
        self.assertEqual((self.contar("encaminhamentos", "TKT-0003"),
                          self.contar("avisos_gestor", "TKT-0003")), (1, 1))
        self.assertEqual((r["estado"].desfecho["acao"], r["estado"].desfecho["motivo"]),
                         ("fila_humana", "confirmacao_nao_recebida"))
        self.assertEqual(self.contar("chamados_internos", "TKT-0003"), 0)

    # ---- J2: caiu entre a decisão e a escrita

    def test_j2_aprovado_e_queda_antes_de_gravar_o_chamado_e_aberto_uma_vez(self):
        self.rodar("TKT-0007", confirmador=None)
        with cai_em("abrir_chamado", depois_de_gravar=False), self.assertRaises(Queda):
            self.responder("TKT-0007", "aprovar")
        self.assertEqual(self.proximo("TKT-0007"), ("gravar",))
        self.assertEqual(db.pendencias_aguardando(self.con), [])          # antes: preso para sempre
        self.assertEqual(self.contar("chamados_internos", "TKT-0007"), 0)
        (r,) = self.recuperar()
        self.assertEqual(r["estado"].desfecho["acao"], "abrir_chamado_interno")
        self.assertEqual(self.contar("chamados_internos", "TKT-0007"), 1)
        self.assertFalse(self.guardado("TKT-0007"))

    # ---- J1: caiu ao processar a resposta do analista

    def test_j1_queda_depois_de_resolver_a_pendencia_guarda_o_texto_editado(self):
        self.rodar("TKT-0007", confirmador=None)
        with cai_em("resolver_pendencia"), self.assertRaises(Queda):
            self.responder("TKT-0007", "aprovar", resumo=CORRIGIDO)
        self.assertEqual(self.proximo("TKT-0007"), ("confirmar",))
        self.assertEqual(db.pendencias_aguardando(self.con), [])          # a pendência já foi resolvida
        (r,) = self.recuperar()
        self.assertEqual(r["parou_em"], "confirmar")
        (resumo,) = [l["resumo"] for l in self.con.execute(
            "SELECT resumo FROM chamados_internos WHERE ticket_externo = 'TKT-0007'")]
        self.assertEqual(resumo, CORRIGIDO)                               # o texto do analista sobreviveu
        self.assertEqual(r["estado"].confirmacoes[-1]["status"], "aprovada")

    def test_j1_queda_antes_de_resolver_usa_a_resposta_guardada(self):
        self.rodar("TKT-0007", confirmador=None)
        with cai_em("resolver_pendencia", depois_de_gravar=False), self.assertRaises(Queda):
            self.responder("TKT-0007", "rejeitar", minutos=3)
        (p,) = db.pendencias_aguardando(self.con)                          # ainda aguardando, com a resposta
        self.assertEqual(json.loads(p["resposta"])["decisao"], "rejeitar")
        (r,) = self.recuperar()
        self.assertEqual((r["estado"].desfecho["acao"], r["estado"].desfecho["motivo"]),
                         ("fila_humana", "acao_rejeitada"))
        self.assertEqual(self.contar("chamados_internos", "TKT-0007"), 0)
        self.assertEqual(db.pendencias_aguardando(self.con), [])

    # ---- J4: caiu depois de gravar, antes do log

    def test_j4_queda_depois_de_gravar_a_recuperacao_escreve_log_e_episodio(self):
        with cai_em("registrar_episodio", depois_de_gravar=False), self.assertRaises(Queda):
            self.rodar("TKT-0001")
        self.assertEqual(self.proximo("TKT-0001"), ())
        self.assertFalse((self.logs / "TKT-0001.json").exists())
        (r,) = self.recuperar()
        self.assertEqual(r["parou_em"], "fim (sem log)")
        self.assertEqual(self.contar("encaminhamentos", "TKT-0001"), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM episodios").fetchone()[0], 1)
        self.assertIn("recuperacao", self.log("TKT-0001"))
        self.assertFalse(self.guardado("TKT-0001"))

    # ---- o que a recuperação não toca

    def test_a_pausa_normal_nao_e_tocada(self):
        self.rodar("TKT-0007", confirmador=None)
        self.assertEqual(self.recuperar(minutos=30), [])
        self.assertEqual(len(db.pendencias_aguardando(self.con)), 1)
        self.assertEqual(self.proximo("TKT-0007"), ("confirmar",))

    def test_execucao_recente_nao_e_tratada_como_queda(self):
        """Uma execução viva pode estar em `gravar` agora mesmo: só checkpoint mais velho que
        IDADE_MINIMA_DA_QUEDA_MIN conta como queda."""
        with cai_em("registrar_encaminhamento"), self.assertRaises(Queda):
            self.rodar("TKT-0001")
        self.assertEqual(self.recuperar(minutos=0), [])
        self.assertEqual(self.proximo("TKT-0001"), ("gravar",))

    def test_checkpoint_que_diz_que_acabou_sem_desfecho_nao_e_concluido(self):
        """O que o modo "async" deixava depois de uma queda: o grafo sem passo seguinte, e nada
        gravado. A recuperação não conclui (seria um log sem desfecho) e não apaga o checkpoint."""
        self.rodar("TKT-0007", confirmador=None)
        config = {"configurable": {"thread_id": "TKT-0007"}}
        GRAFO.update_state(config, {"termino": None, "desfecho": None}, as_node="finalizar")
        self.assertEqual(self.proximo("TKT-0007"), ())
        (r,) = self.recuperar()
        self.assertEqual(r["parou_em"], "inconsistente")
        self.assertIn("erro", r)
        self.assertTrue(self.guardado("TKT-0007"))                         # a pista fica
        self.assertEqual(self.contar("chamados_internos", "TKT-0007"), 0)

    # ---- o processo morto de verdade (os._exit), e não uma exceção

    def test_processo_morto_de_verdade_fica_em_gravar_e_e_recuperado(self):
        """Em três processos, com um checkpointer em arquivo: o primeiro pausa, o segundo aprova e
        morre com os._exit dentro de db.abrir_chamado (simular_queda.py), o terceiro confere e
        recupera. Com durability="sync" o checkpoint fica em `gravar`; com o padrão do LangGraph
        ("async") ele voltava a `confirmar` (docs/humano.md §4.3)."""
        import subprocess
        raiz = Path(__file__).resolve().parent.parent
        env = {**os.environ, "CHECKPOINT_DB": str(self.logs / "checkpoints.db"),
               "LLM_BASE_URL": "http://localhost:9", "OPENAI_API_KEY": "teste-sem-rede",
               "PYTHONIOENCODING": "utf-8"}
        prefixo = ("import sys; sys.path[:0] = ['src', 'tests']; import db, grafo; "
                   "from pathlib import Path; from datetime import datetime, timedelta; "
                   "from test_grafo import ROTEIROS, ModeloRoteirizado; grafo.BUSCA = 'palavra'; ")

        def python(*args):
            return subprocess.run([sys.executable, *args], cwd=raiz, env=env, capture_output=True,
                                  text=True, encoding="utf-8", timeout=120)
        pausa = python("-c", prefixo + (
            "db.recriar_banco(); e = grafo.rodar_grafo('TKT-0007', client=ModeloRoteirizado(ROTEIROS['TKT-0007']), "
            f"modelo='fake', con=db.conectar(), verbose=False, confirmador=None, log_dir=Path(r'{self.logs}')); "
            "print(e.termino.value)"))
        self.assertEqual(pausa.stdout.strip(), "aguardando_humano", pausa.stderr)
        queda = python("simular_queda.py", "cair", "TKT-0007", "--em", "abrir_chamado")
        self.assertEqual(queda.returncode, 70, queda.stdout + queda.stderr)
        depois = python("-c", prefixo + (
            "print(grafo.GRAFO.get_state({'configurable': {'thread_id': 'TKT-0007'}}).next); "
            "r = grafo.retomar_interrompidas(client=ModeloRoteirizado([]), con=db.conectar(), "
            "agora=datetime.now().astimezone() + timedelta(minutes=10)); "
            "print(r[0]['parou_em'], r[0]['estado'].desfecho['acao'])"))
        self.assertEqual(depois.stdout.splitlines(), ["('gravar',)", "gravar abrir_chamado_interno"],
                         depois.stderr)
        self.assertEqual(self.contar("chamados_internos", "TKT-0007"), 1)

    # ---- a chave A

    def test_chave_a_execucao_nova_do_mesmo_chamado_grava_de_novo(self):
        """A chave reconhece a gravação refeita, não o chamado repetido (decisão de 17/10/2026)."""
        self.rodar("TKT-0001")
        self.rodar("TKT-0001")
        self.assertEqual(self.contar("encaminhamentos", "TKT-0001"), 2)
        chaves = [l[0] for l in self.con.execute(
            "SELECT chave_idempotencia FROM encaminhamentos WHERE ticket_externo = 'TKT-0001'")]
        self.assertEqual(len(set(chaves)), 2)
        self.assertTrue(all(c.endswith(":TKT-0001:anotacao_interna") for c in chaves))

    def test_o_laco_continua_gravando_sem_chave(self):
        r = db.registrar_encaminhamento(self.con, "TKT-0004", "fila_comercial", "teste", None)
        self.assertNotIn("ja_existia", r)
        db.registrar_encaminhamento(self.con, "TKT-0004", "fila_comercial", "teste", None)
        self.assertEqual(self.contar("encaminhamentos", "TKT-0004"), 2)


if __name__ == "__main__":
    unittest.main()

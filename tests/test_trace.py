"""Testes OFFLINE do trace (src/telemetria.py e o fim de src/grafo.py): sem chave e sem rede.

Provam que uma execução do grafo emite os spans das convenções GenAI do OpenTelemetry (Parte 3,
§4.2) com o que o §2.3 pede para reconstruir a decisão, e que o arquivo do trace é gravado ao lado
do log. NÃO provam nada sobre os números de uma execução real.

    python -m unittest tests.test_trace -v
"""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

os.environ["CHECKPOINT_DB"] = ":memory:"     # antes de importar o grafo: nada de arquivo nos testes
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import db                                    # noqa: E402
import grafo                                 # noqa: E402
import telemetria                            # noqa: E402
import ver_traces                            # noqa: E402
from test_grafo import ROTEIROS, SIM, ModeloRoteirizado  # noqa: E402
from versao import VERSAO                    # noqa: E402


class TestTrace(unittest.TestCase):
    def setUp(self):
        self._busca, grafo.BUSCA = grafo.BUSCA, "palavra"
        self.memoria = telemetria.ligar_memoria()
        db.recriar_banco()
        self.con = db.conectar()
        self.pasta = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.pasta.name)

    def tearDown(self):
        grafo.BUSCA = self._busca
        self.con.close()
        self.pasta.cleanup()

    def rodar(self, ticket, **kw):
        return grafo.rodar_grafo(ticket, client=ModeloRoteirizado(ROTEIROS[ticket]), modelo="fake",
                                 con=self.con, verbose=False, log_dir=self.log_dir, **kw)

    def aprovar(self, ticket):
        return grafo.retomar_grafo(ticket, "aprovar", client=ModeloRoteirizado([]), con=self.con,
                                   verbose=False, log_dir=self.log_dir, por="analista de teste")

    def spans(self):
        return self.memoria.get_finished_spans()

    def raizes(self):
        return [s for s in self.spans() if s.parent is None]

    def test_raiz_tem_termino_versao_entrada_e_contexto_recuperado(self):
        e = self.rodar("TKT-0001", confirmador=SIM)
        (raiz,) = self.raizes()
        a = raiz.attributes
        self.assertEqual(raiz.name, "invoke_agent triagem")
        self.assertEqual(a["gen_ai.operation.name"], "invoke_agent")
        self.assertEqual(a["triagem.termino"], "respondeu")
        self.assertEqual(a["triagem.versao"], VERSAO)
        self.assertEqual(raiz.resource.attributes["service.version"], VERSAO)
        self.assertEqual(a["gen_ai.conversation.id"], "TKT-0001")
        self.assertEqual(a["triagem.entrada"], e.entrada)
        self.assertEqual(a["triagem.prompts"], grafo.prompts_em_uso())
        self.assertEqual(a["triagem.desfecho"], "anotacao_interna")
        self.assertIn("KB-101-A", " ".join(a["triagem.kb_recuperados"]))
        self.assertIn('"acao":"anotacao_interna"', a["triagem.saida"])

    def test_um_chat_por_chamada_ao_modelo_e_um_execute_tool_por_ferramenta(self):
        e = self.rodar("TKT-0001", confirmador=SIM)
        nomes = [s.name for s in self.spans()]
        self.assertEqual(nomes.count("chat fake"), e.n_chamadas_modelo)
        ferramentas = [p.ferramenta for p in e.passos if p.ferramenta in telemetria.FERRAMENTAS]
        self.assertEqual(sorted(n.split(" ", 1)[1] for n in nomes if n.startswith("execute_tool")),
                         sorted(ferramentas))
        chat = next(s for s in self.spans() if s.name == "chat fake")
        self.assertEqual(chat.attributes["gen_ai.usage.input_tokens"], 1000)
        self.assertEqual(chat.attributes["gen_ai.usage.output_tokens"], 50)
        # o chat é filho de um nó de modelo, e todos os spans são do mesmo trace
        pai = next(s for s in self.spans() if s.context.span_id == chat.parent.span_id)
        self.assertIn(pai.name, {"triagem", "redigir", "conferir_ressalva"})
        self.assertEqual({s.context.trace_id for s in self.spans()}, {chat.context.trace_id})

    def test_erro_da_ferramenta_marca_o_span(self):
        self.rodar("TKT-0999")
        consulta = next(s for s in self.spans() if s.name == "execute_tool consultar_ticket")
        self.assertEqual(consulta.status.status_code.name, "ERROR")
        self.assertEqual(consulta.attributes["error.type"], "erro_da_ferramenta")

    def test_pausa_e_aprovacao_sao_dois_traces_ligados_pela_execucao(self):
        pausado = self.rodar("TKT-0007")
        self.aprovar("TKT-0007")
        primeira, segunda = sorted(self.raizes(), key=lambda s: s.start_time)
        self.assertEqual(primeira.attributes["triagem.termino"], "aguardando_humano")
        self.assertNotEqual(primeira.status.status_code.name, "ERROR")     # pausar não é erro
        confirmar = next(s for s in self.spans() if s.name == "confirmar"
                         and s.context.trace_id == primeira.context.trace_id)
        self.assertTrue(confirmar.attributes["triagem.pausou"])
        a = segunda.attributes
        self.assertTrue(a["triagem.retomada"])
        self.assertEqual(a["triagem.termino"], "respondeu")
        self.assertEqual(a["triagem.execucao_id"], pausado.execucao_id)
        self.assertEqual((a["triagem.aprovacao.status"], a["triagem.aprovacao.por"]),
                         ("aprovada", "analista de teste"))
        self.assertIn("execute_tool abrir_chamado_interno",
                      {s.name for s in self.spans() if s.context.trace_id == segunda.context.trace_id})

    def test_segunda_aprovacao_aparece_no_trace_sem_gravar_nada(self):
        self.rodar("TKT-0007")
        self.aprovar("TKT-0007")
        self.assertIsNone(self.aprovar("TKT-0007"))
        ultima = max(self.raizes(), key=lambda s: s.start_time)
        self.assertTrue(ultima.attributes["triagem.nada_a_retomar"])
        do_ultimo = {s.name for s in self.spans() if s.context.trace_id == ultima.context.trace_id}
        self.assertNotIn("execute_tool abrir_chamado_interno", do_ultimo)

    def test_arquivo_do_trace_ao_lado_do_log_e_legivel(self):
        self.rodar("TKT-0007")
        self.aprovar("TKT-0007")
        arquivo = self.log_dir / "TKT-0007.trace.jsonl"
        self.assertTrue(arquivo.exists())
        self.assertTrue((self.log_dir / "TKT-0007.json").exists())     # o log continua
        spans = ver_traces.ler(arquivo)
        self.assertEqual(len(spans), len(self.spans()))
        saida = io.StringIO()
        with redirect_stdout(saida):
            ver_traces.imprimir(spans)
        texto = saida.getvalue()
        self.assertEqual(texto.count("invoke_agent triagem"), 2)
        self.assertIn("termino=aguardando_humano", texto)
        self.assertIn("termino=respondeu", texto)

    def test_sem_pasta_de_log_nada_vai_para_arquivo(self):
        grafo.rodar_grafo("TKT-0004", client=ModeloRoteirizado(ROTEIROS["TKT-0004"]), modelo="fake",
                          con=self.con, verbose=False)
        self.assertEqual(list(self.log_dir.iterdir()), [])
        self.assertEqual(len(self.raizes()), 1)              # o span existe; só não tem arquivo


if __name__ == "__main__":
    unittest.main()

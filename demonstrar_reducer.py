"""Demonstração do campo sem reducer (Parte 2, item 7.2): o que o sistema faz SEM o reducer.

    python demonstrar_reducer.py            # modelo roteirizado: sem chave, sem API
    python demonstrar_reducer.py --real     # a PARTE 1 com o modelo de verdade (usa a API e o .env)

Duas partes:

  PARTE 1  o nosso grafo. É o grafo de verdade (grafo._construir(), os mesmos nós e arestas que
           main.py executa), compilado duas vezes: com o EstadoGrafo como está e com uma cópia em
           que alguns campos acumulados perderam o `Annotated[..., operator.add]`. O modelo é
           roteirizado, como nos testes offline, e a busca é a por palavra. Com --real, o
           modelo e a busca vetorial são os de main.py, e o teto de tokens da demonstração é
           calculado do consumo medido na primeira execução.
  PARTE 2  um grafo mínimo com dois ramos paralelos, porque o nosso grafo não tem nenhum. Não
           tem modelo; só roda sem --real.

Não muda src/grafo.py, não usa o checkpoint em arquivo e não toca dados/tickets.db: o banco de
chamados é um arquivo temporário. A saída vai para logs/grafo-reducer/saida-terminal.txt (com
--real, saida-terminal-real.txt).
"""
import json
import operator
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Annotated, TypedDict

RAIZ = Path(__file__).resolve().parent
os.environ.setdefault("CHECKPOINT_DB", ":memory:")
sys.path.insert(0, str(RAIZ / "src"))

import langgraph.version                                         # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver            # noqa: E402
from langgraph.errors import GraphRecursionError, InvalidUpdateError  # noqa: E402
from langgraph.graph import END, START, StateGraph               # noqa: E402

import db                                                        # noqa: E402
import grafo                                                     # noqa: E402
from agente import Orcamento                                     # noqa: E402

LINHAS = []


def diga(texto=""):
    LINHAS.append(texto)
    print(texto)


# ================================================================ PARTE 1: O NOSSO GRAFO

class ModeloRoteirizado:
    """Devolve, em ordem, os textos do roteiro (o último se repete). Cada chamada gasta 1000
    tokens de entrada e 50 de saída. É o mesmo dos testes offline (tests/test_grafo.py)."""

    def __init__(self, roteiro):
        self.roteiro, self.i = list(roteiro), 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        texto = self.roteiro[min(self.i, len(self.roteiro) - 1)]
        self.i += 1
        return NS(usage=NS(prompt_tokens=1000, completion_tokens=50),
                  choices=[NS(message=NS(content=texto))])


class Contador:
    """Embrulha um cliente (o roteirizado ou o da API) e anota o consumo de cada chamada, por
    fora do estado do grafo: é o que foi gasto DE FATO, para comparar com o que o estado diz."""

    def __init__(self, client):
        self.client, self.tokens = client, []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        resp = self.client.chat.completions.create(**kw)
        self.tokens.append(resp.usage.prompt_tokens + resp.usage.completion_tokens)
        return resp


def triagem(classe, termos=()):
    return json.dumps({"classe": classe, "log_aponta_outro_servico": False,
                       "termos_busca": list(termos), "justificativa": "demonstração"})


def texto(t):
    return json.dumps({"texto": t}, ensure_ascii=False)


NAO_CAI = json.dumps({"cai_na_ressalva": False, "frase": "", "motivo": "demonstração"})

# TKT-0003: três chamadas ao modelo (triagem, conferir_ressalva, redigir) e um chamado interno aberto
ROTEIRO_0003 = [triagem("tecnico", ("permissao", "negada", "upload")), NAO_CAI,
                texto("Permissão negada ao gravar arquivos. Cliente afirma ser a 3a vez; o histórico "
                      "do sistema confirma 1 ocorrência anterior (INC-0001).")]
# TKT-0004 com um texto que o nó `validar` reprova sempre (curto demais)
ROTEIRO_0004 = [triagem("comercial"), texto("Upgrade.")]


def estado_sem_reducer(campos):
    """Uma cópia do EstadoGrafo em que `campos` perderam o reducer: voltam ao tipo puro."""
    anotacoes = dict(grafo.EstadoGrafo.__annotations__)
    for campo in campos:
        anotacoes[campo] = anotacoes[campo].__origin__
    return TypedDict("EstadoSemReducer", anotacoes, total=False)


def compilar(campos_sem_reducer=()):
    """O grafo de verdade, com o estado original ou com a cópia sem reducer. Compilado de novo a
    cada execução, com um checkpointer vazio: no mesmo thread, os campos acumulados somariam com
    os da execução anterior (é por isso que rodar_grafo() apaga o thread antes de começar)."""
    original = grafo.EstadoGrafo
    if campos_sem_reducer:
        grafo.EstadoGrafo = estado_sem_reducer(campos_sem_reducer)
    try:
        return grafo._construir().compile(checkpointer=InMemorySaver())
    finally:
        grafo.EstadoGrafo = original


REAL = None        # com --real: (cliente da API, nome do modelo)


def executar(g, ticket, roteiro, max_tokens=30_000):
    """Uma execução num banco recém-criado. Devolve o estado final e o que ficou gravado."""
    db.recriar_banco()
    con = db.conectar()
    modelo = Contador(REAL[0] if REAL else ModeloRoteirizado(roteiro))
    ctx = grafo.Contexto(client=modelo, con=con, orcamento=Orcamento(max_tokens=max_tokens),
                         confirmador=lambda p: (True, "demonstração"), verbose=False)
    config = {"configurable": {"thread_id": ticket}, "recursion_limit": grafo.LIMITE_SUPERPASSOS}
    inicial = {"id_ticket": ticket, "modelo": REAL[1] if REAL else "roteirizado", "temperatura": 0.0,
               "execucao_id": f"{ticket}-demonstracao", "executado_em": "", "commit": None,
               "texto_recebido": None, "prazo_confirmacao_min": 20}
    excecao = None
    try:
        g.invoke(inicial, config, context=ctx)
    except GraphRecursionError as e:
        excecao = type(e).__name__
    v = g.get_state(config).values
    gravado = {"chamados_internos": db.contar(con, "chamados_internos", ticket),
               "encaminhamentos": db.contar(con, "encaminhamentos", ticket)}
    con.close()
    return {"v": v, "gravado": gravado, "excecao": excecao, "tokens_por_chamada": modelo.tokens}


def linha(rotulo, r):
    v = r["v"]
    passos = [p["ferramenta"] for p in v.get("passos") or []]
    tokens = v.get("tokens_entrada", 0) + v.get("tokens_saida", 0)
    diga(f"  {rotulo}")
    diga(f"    exceção levantada           {r['excecao'] or 'nenhuma'}")
    diga(f"    término                     {v.get('termino')}"
         + (f"  ({v['motivo']})" if v.get("motivo") else ""))
    diga(f"    gravado no banco            {r['gravado']}")
    diga(f"    passos no estado            {len(passos)}: {passos}")
    feitas = r["tokens_por_chamada"]
    diga(f"    chamadas ao modelo          feitas: {len(feitas)}   no estado: {v.get('n_chamadas_modelo', 0)}")
    diga(f"    tokens                      gastos: {sum(feitas)} {feitas}   no estado: {tokens}")
    diga(f"    tentativas_redacao          {v.get('tentativas_redacao', 0)}")


def parte_1():
    diga("PARTE 1: O NOSSO GRAFO (src/grafo.py), com e sem o reducer")
    diga("Mesmos nós, mesmas arestas, mesmo roteiro do modelo. Só muda a declaração do campo.")

    diga("\n1.1  `passos` sem reducer (TKT-0003)")
    linha("COM operator.add", executar(compilar(), "TKT-0003", ROTEIRO_0003))
    linha("SEM reducer", executar(compilar(["passos"]), "TKT-0003", ROTEIRO_0003))

    consumo = ["n_chamadas_modelo", "tokens_entrada", "tokens_saida", "custo_usd"]
    diga("\n1.2  os campos de consumo sem reducer, com o teto de tokens em 2.000 (TKT-0003)")
    diga("     Cada chamada gasta 1.050 tokens: a terceira chamada não deveria acontecer.")
    linha("COM operator.add", executar(compilar(), "TKT-0003", ROTEIRO_0003, max_tokens=2000))
    linha("SEM reducer", executar(compilar(consumo), "TKT-0003", ROTEIRO_0003, max_tokens=2000))

    diga("\n1.3  `tentativas_redacao` sem reducer, com um texto que o `validar` reprova sempre (TKT-0004)")
    diga(f"     O texto reprovado volta ao modelo uma vez (MAX_REDACOES = {grafo.MAX_REDACOES}).")
    linha("COM operator.add", executar(compilar(), "TKT-0004", ROTEIRO_0004))
    linha("SEM reducer", executar(compilar(["tentativas_redacao"]), "TKT-0004", ROTEIRO_0004))


def parte_1_real():
    diga("PARTE 1: O NOSSO GRAFO (src/grafo.py), com e sem o reducer, COM O MODELO REAL")
    diga("Mesmos nós, mesmas arestas, mesmo chamado (TKT-0003). Só muda a declaração do campo.")

    diga("\n1.1  `passos` sem reducer (TKT-0003)")
    com = executar(compilar(), "TKT-0003", None)
    linha("COM operator.add", com)
    linha("SEM reducer", executar(compilar(["passos"]), "TKT-0003", None))

    # O teto real (30.000) não é alcançado por um chamado. Para o defeito aparecer, o teto da
    # demonstração fica entre a maior chamada sozinha e a soma das chamadas que vêm antes da
    # última, medidas na execução acima: com a soma ele dispara, sem ela não.
    antes = com["tokens_por_chamada"][:-1]
    if len(antes) < 2:
        diga("\n1.2  NÃO EXECUTADO: a execução fez menos de três chamadas ao modelo, e não há teto "
             "que separe a soma da última chamada.")
        return
    teto = (max(antes) + sum(antes)) // 2
    consumo = ["n_chamadas_modelo", "tokens_entrada", "tokens_saida", "custo_usd"]
    diga(f"\n1.2  os campos de consumo sem reducer, com o teto de tokens em {teto} (TKT-0003)")
    diga(f"     O teto foi posto entre a maior chamada antes da última ({max(antes)}) e a soma delas "
         f"({sum(antes)}): a última chamada não deveria acontecer.")
    linha("COM operator.add", executar(compilar(), "TKT-0003", None, max_tokens=teto))
    linha("SEM reducer", executar(compilar(consumo), "TKT-0003", None, max_tokens=teto))

    diga("\n1.3  `tentativas_redacao`: NÃO EXECUTADO com o modelo real. A demonstração depende de um "
         "texto que o `validar` reprove sempre, e o modelo real não o escreve a pedido; ela existe "
         "só com o modelo roteirizado (saida-terminal.txt).")


# ================================================================ PARTE 2: O GRAFO MÍNIMO

class SemReducer(TypedDict, total=False):
    achados: list[str]


class ComReducer(TypedDict, total=False):
    achados: Annotated[list[str], operator.add]


def _ramo(nome):
    return lambda state: {"achados": [f"achado do ramo {nome}"]}


def ramos_de_tamanhos_diferentes(tipo):
    """START abre dois ramos: `a` escreve na 1ª volta; `espera` -> `b` escreve na 2ª."""
    g = StateGraph(tipo)
    g.add_node("a", _ramo("a"))
    g.add_node("espera", lambda state: {})
    g.add_node("b", _ramo("b"))
    g.add_edge(START, "a")
    g.add_edge(START, "espera")
    g.add_edge("espera", "b")
    g.add_edge("a", END)
    g.add_edge("b", END)
    return g.compile()


def ramos_na_mesma_volta(tipo):
    """START abre dois ramos, e `a` e `b` escrevem na mesma volta."""
    g = StateGraph(tipo)
    for nome in ("a", "b"):
        g.add_node(nome, _ramo(nome))
        g.add_edge(START, nome)
        g.add_edge(nome, END)
    return g.compile()


def parte_2():
    diga("\nPARTE 2: UM GRAFO MÍNIMO COM DOIS RAMOS PARALELOS")
    diga("Os ramos `a` e `b` escrevem, cada um, um item no campo `achados`.")
    for titulo, monta in (("2.1  ramos de tamanhos diferentes (`b` escreve uma volta depois de `a`)",
                           ramos_de_tamanhos_diferentes),
                          ("2.2  ramos que escrevem na mesma volta", ramos_na_mesma_volta)):
        diga(f"\n{titulo}")
        for rotulo, tipo in (("COM operator.add", ComReducer), ("SEM reducer", SemReducer)):
            try:
                resultado = monta(tipo).invoke({"achados": []})["achados"]
            except InvalidUpdateError as e:
                resultado = f"InvalidUpdateError: {str(e).splitlines()[0]}"
            diga(f"  {rotulo:<18} {resultado}")


if __name__ == "__main__":
    real = "--real" in sys.argv[1:]
    if real:
        from dotenv import load_dotenv
        from openai import OpenAI
        load_dotenv(RAIZ / ".env")
        REAL = (OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"]),
                os.environ["LLM_MODELO"])
    else:
        grafo.BUSCA = "palavra"                   # sem API de embedding
    with tempfile.TemporaryDirectory() as pasta:
        db.DB_PATH = Path(pasta) / "demonstracao.db"      # não toca dados/tickets.db
        diga(f"Demonstração do campo sem reducer   {datetime.now():%d/%m/%Y %H:%M}   "
             f"langgraph {langgraph.version.__version__}   commit {grafo._commit()}")
        if real:
            diga(f"Modelo real: {REAL[1]}, temperature=0, busca {grafo.BUSCA}. "
                 "\"gastos\" é o consumo que a API devolveu em cada chamada, anotado fora do estado.\n")
            parte_1_real()
        else:
            diga("Modelo roteirizado (sem API): cada chamada gasta 1.000 tokens de entrada e 50 de saída.\n")
            parte_1()
            parte_2()
    destino = RAIZ / "logs" / "grafo-reducer" / ("saida-terminal-real.txt" if real else "saida-terminal.txt")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(LINHAS) + "\n", encoding="utf-8")
    print(f"\n(saída gravada em {destino})")

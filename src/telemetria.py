"""O trace de cada execução, nas convenções semânticas GenAI do OpenTelemetry (Parte 3, §4.2).

Três tipos de span, os do enunciado, mais um por nó do grafo que não é ferramenta:

    invoke_agent triagem          a raiz, uma por invocação do grafo (execução nova ou retomada)
      <nó>                        cada nó que não é ferramenta (triagem, decidir, redigir...)
        chat <modelo>             cada chamada ao modelo de chat, com modelo e tokens
      execute_tool <ferramenta>   as quatro ferramentas (consultar_ticket, buscar_base_conhecimento,
        embeddings mistral-embed    abrir_chamado_interno, registrar_encaminhamento)

Destino: um arquivo JSONL por chamado, `<pasta do log>/<id>.trace.jsonl`, ao lado do log JSON da
execução, uma linha por span (decisão do grupo, 20/11/2026: arquivo, e não coletor). A retomada
grava no mesmo arquivo, como outro trace, e o `triagem.execucao_id` liga os dois. Sem pasta de log
(os testes), nada vai para arquivo; os testes leem os spans da memória (`ligar_memoria`).
`python ver_traces.py <arquivo ou pasta>` mostra a árvore.

O log JSON continua sendo gravado (decisão de 20/11/2026): os docs citam centenas deles e a suíte de
avaliação lê os passos dele. O trace é o registro de referência da Parte 3 (§2.3).

Quem abre os spans: as raízes, `grafo.rodar_grafo` e `grafo.retomar_grafo` (embrulhadas no fim de
src/grafo.py); os nós, `grafo._rodar_no`; o chat, `grafo._chamar_modelo`; o embedding,
`vetorial._embeddings`. Este módulo não conhece o grafo: só o formato.
"""
import json
import threading
from contextlib import contextmanager
from pathlib import Path

from opentelemetry import trace as otel
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from versao import VERSAO

AGENTE = "triagem"
PROVEDOR = "mistral_ai"          # gen_ai.provider.name: o modelo de chat e o de embedding são da Mistral
FERRAMENTAS = {"consultar_ticket", "buscar_base_conhecimento", "abrir_chamado_interno",
               "registrar_encaminhamento"}


class ExportadorArquivo(SpanExporter):
    """Grava cada span, ao terminar, numa linha do arquivo do trace a que ele pertence. A raiz diz
    o arquivo (`destinar`); span de trace sem arquivo é descartado."""

    def __init__(self):
        self._destinos: dict[int, Path] = {}
        self._trava = threading.Lock()

    def destinar(self, trace_id: int, arquivo: Path | None):
        with self._trava:
            if arquivo is None:
                self._destinos.pop(trace_id, None)
            else:
                self._destinos[trace_id] = arquivo

    def export(self, spans) -> SpanExportResult:
        with self._trava:
            for span in spans:
                arquivo = self._destinos.get(span.context.trace_id)
                if arquivo is None:
                    continue
                arquivo.parent.mkdir(parents=True, exist_ok=True)
                with arquivo.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(json.loads(span.to_json()), ensure_ascii=False) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


# Um provedor próprio, e não o global: nada de fora do sistema muda o destino dos spans.
PROVEDOR_DE_TRACES = TracerProvider(resource=Resource.create(
    {"service.name": "agente-triagem", "service.version": VERSAO}))
ARQUIVO = ExportadorArquivo()
PROVEDOR_DE_TRACES.add_span_processor(SimpleSpanProcessor(ARQUIVO))   # síncrono: nada fica no buffer
TRACER = PROVEDOR_DE_TRACES.get_tracer("agente-triagem", VERSAO)

_MEMORIA: InMemorySpanExporter | None = None


def ligar_memoria() -> InMemorySpanExporter:
    """Para os testes: os spans terminados ficam também na memória. Chamar de novo limpa."""
    global _MEMORIA
    if _MEMORIA is None:
        _MEMORIA = InMemorySpanExporter()
        PROVEDOR_DE_TRACES.add_span_processor(SimpleSpanProcessor(_MEMORIA))
    _MEMORIA.clear()
    return _MEMORIA


def arquivo_do_trace(log_dir: Path | None, id_ticket: str) -> Path | None:
    return Path(log_dir) / f"{id_ticket}.trace.jsonl" if log_dir is not None else None


def _texto(valor) -> str:
    return valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)


def atributos(span, valores: dict):
    """Atributo do OpenTelemetry só aceita texto, número, booleano ou lista deles: o resto vira JSON,
    e None não é gravado (a ausência é a informação)."""
    for chave, valor in valores.items():
        if valor is None:
            continue
        if isinstance(valor, (dict, tuple)) or (isinstance(valor, list) and not all(
                isinstance(v, (str, int, float, bool)) for v in valor)):
            valor = _texto(valor)
        span.set_attribute(chave, valor)


@contextmanager
def raiz(id_ticket: str, log_dir: Path | None, retomada: bool):
    """O span `invoke_agent`. Quem chama preenche os atributos do fim (término, saída...)."""
    trace_id = None
    try:
        with TRACER.start_as_current_span(f"invoke_agent {AGENTE}", kind=otel.SpanKind.INTERNAL) as span:
            trace_id = span.get_span_context().trace_id
            ARQUIVO.destinar(trace_id, arquivo_do_trace(log_dir, id_ticket))
            atributos(span, {"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": AGENTE,
                             "gen_ai.provider.name": PROVEDOR, "gen_ai.conversation.id": id_ticket,
                             "triagem.versao": VERSAO, "triagem.retomada": retomada})
            yield span
    finally:
        # A raiz é exportada ao sair do `with` (o processador é síncrono); só depois o destino sai.
        if trace_id is not None:
            ARQUIVO.destinar(trace_id, None)


@contextmanager
def span_filho(nome: str, valores: dict | None = None, kind=otel.SpanKind.INTERNAL):
    """Um span abaixo do atual. Exceção marca o span com erro e segue (quem chama decide)."""
    with TRACER.start_as_current_span(nome, kind=kind, record_exception=True,
                                      set_status_on_exception=True) as span:
        atributos(span, valores or {})
        yield span


def marcar_erro(span, tipo: str, descricao: str = ""):
    span.set_attribute("error.type", tipo)
    span.set_status(otel.Status(otel.StatusCode.ERROR, descricao[:200]))

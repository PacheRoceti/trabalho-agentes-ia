"""O grafo (Parte 2, item 6): o mesmo trabalho do laço de agente.py, como workflow em LangGraph.

Este arquivo é o caminho padrão do main.py. O laço da Parte 1 continua em agente.py e roda com
`python src/main.py --laco ...`, para os dois poderem ser comparados nos mesmos casos.

O que muda em relação ao laço (docs/grafo.md):

    MODELO  é chamado em três nós, e em nenhum deles escolhe ferramenta (o `redigir` não o chama
            no pedido ao cliente, que tem texto padrão: PEDIDO_AO_CLIENTE):
              triagem            classifica o assunto, diz se o log aponta outro serviço e escolhe
                                 os termos de busca (saída estruturada, validada)
              conferir_ressalva  só quando o 1º guia declara situações que não cobre: diz se o
                                 relato cai numa delas (o código só pode BAIXAR o score)
              redigir            escreve o resumo ou a mensagem de um desfecho JÁ decidido
    CÓDIGO  decide a rota e o desfecho (nó `decidir`: classe + contagem de pedidos + score da
            busca), valida o texto, pede a confirmação humana, grava e registra o término.

A sequência de passos deixou de ser decisão do modelo: está nas arestas. Toda aresta
condicional tem o mapa de destinos escrito (é o que conferir_grafo.py lê e imprime).

Pausa: o H1 (abrir chamado interno) e o H2 (enviar o pedido de informação ao cliente), no mesmo
nó `confirmar`, com `interrupt` e checkpointer em SQLite. A fila do analista continua sendo a
tabela `pendencias` (src/db.py); o estado da execução pausada fica no checkpoint do LangGraph,
endereçado pelo thread_id = id do chamado. O H3 (a espera pela resposta do cliente) não existe.
"""
import json
import operator
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

import db
import vetorial
from agente import (PROMPTS, EdicaoRecusada, Estado, Orcamento, Passo, Termino, _agora, _commit,
                    _entrada, _ler_prompt)
from ferramentas import (LIMIAR_CONFIANCA, MOTIVO_PRAZO_VENCIDO, MOTIVO_REJEITADA,
                         PRAZO_CONFIRMACAO_MIN, ErroFatal, ErroRecuperavel,
                         _exigir_pedido_sem_informacao_interna, encaminhar_pendencia)
from saida import montar_saida

RAIZ = Path(__file__).resolve().parent.parent
PROMPT_TRIAGEM = PROMPTS / "triagem-v1.md"
PROMPT_REDIGIR = PROMPTS / "redigir-v3.md"
PROMPT_RESSALVA = PROMPTS / "ressalva-v3.md"

MAX_TENTATIVAS_TRIAGEM = 2     # saída fora do contrato volta ao modelo uma vez
MAX_REDACOES = 2               # texto reprovado pelo nó `validar` volta ao modelo uma vez
MAX_TENTATIVAS_RESSALVA = 2    # saída fora do contrato volta ao modelo uma vez

# A DECISÃO QUE VIROU PARÂMETRO (item 6.6). No laço, o limite de voltas é nosso: `max_passos = 8`,
# em agente.Orcamento. No grafo, quem limita o número de superpassos é o `recursion_limit` do
# LangGraph, que tem valor padrão na biblioteca. Declaramos o nosso aqui, para uma troca de versão
# não mudar quanto uma execução presa pode gastar. O caminho mais longo do grafo tem 14
# superpassos (rota técnica, com a conferência da ressalva, uma redação reprovada e a confirmação,
# 14); 20 dá folga e ainda corta
# um laço que não devia existir. Estourado, a execução termina como `orcamento_esgotado`.
LIMITE_SUPERPASSOS = 20

# As duas ações que não têm volta e por isso esperam o analista (docs/humano.md §1), cada uma com
# o único campo que ele pode corrigir ao aprovar e os nomes com que os dois textos vão ao log.
#   H1  abrir_chamado_interno  não há ferramenta para apagar nem encerrar o chamado
#   H2  devolver_cliente       a mensagem chega ao cliente
CAMPO_EDITAVEL = {
    "abrir_chamado_interno": ("resumo", "resumo_original", "resumo_aprovado"),
    "devolver_cliente": ("mensagem", "mensagem_original", "mensagem_aprovada"),
}

# O PEDIDO DE INFORMAÇÃO AO CLIENTE (desfecho devolver_cliente) é texto padrão, e não do modelo
# (decisão de 12/10/2026, docs/prompts.md §2.2). O que falta num relato sem serviço nem sintoma é
# sempre a mesma coisa, então não há o que o modelo decidir; e ele errou esse texto em 15
# execuções de 15 com o redigir-v1.md. As perguntas vêm do que os guias da base usam para
# separar um caso do outro (dados/seed.sql, kb_artigos):
#   1  o serviço            cada guia é de um serviço: site, e-mail, banco, FTP/SFTP, SSH, backup, cron
#   2  domínio e banco      KB-101-A, 106, 110, 111, 112 (domínio); KB-107 (banco de dados)
#   3  mensagem ou código   KB-104 (5xx), KB-112 (403), KB-102 ("permissão negada"), KB-107, KB-113
#   4  data, hora, sempre?  a reincidência conta datas; KB-104 só cobre a falha CONSTANTE
#   5  o que mudou antes    as causas de KB-102, 104, 107 e 114: publicação, migração, restauração, senha
# O texto passa pelo nó `validar` como qualquer outro (nenhum termo interno), e o analista pode
# trocá-lo ao aprovar (--mensagem).
PEDIDO_AO_CLIENTE = (
    "Para darmos andamento ao seu chamado, precisamos de mais informações:\n"
    "1. Qual serviço está com problema (site, e-mail, banco de dados, FTP/SFTP, acesso SSH, "
    "backup ou tarefa agendada)?\n"
    "2. Qual é o domínio ou o endereço afetado? Se for banco de dados, qual é o nome do banco?\n"
    "3. Qual mensagem ou código de erro aparece (por exemplo: 403, 502, \"permissão negada\")? "
    "Copie o texto como ele é exibido.\n"
    "4. Em que data e hora o problema começou? Ele acontece sempre ou só às vezes?\n"
    "5. Alguma coisa mudou pouco antes (publicação de nova versão, migração, restauração de "
    "backup, troca de senha)?")


# ================================================================ SAÍDAS DO MODELO

class _Modelo(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Triagem(_Modelo):
    classe: Literal["tecnico", "comercial", "insuficiente", "fora_da_alcada"]
    log_aponta_outro_servico: bool
    termos_busca: list[str] = []
    justificativa: str = ""

    @model_validator(mode="after")
    def _coerente(self):
        if self.classe == "tecnico" and not [t for t in self.termos_busca if str(t).strip()]:
            raise ValueError("classe 'tecnico' exige termos_busca com 2 a 5 palavras do relato")
        return self


class Ressalva(_Modelo):
    cai_na_ressalva: bool
    frase: str = ""
    motivo: str = ""


class Redacao(_Modelo):
    texto: str


# ================================================================ ESTADO

class EstadoGrafo(TypedDict, total=False):
    """O estado do grafo. Campo sem `Annotated` tem um escritor por volta e é sobrescrito; os
    campos com reducer (operator.add) são os acumulados por mais de um nó."""
    # identificação da execução (escritos uma vez, na entrada do grafo)
    id_ticket: str
    modelo: str
    temperatura: float | None
    execucao_id: str
    executado_em: str
    commit: str | None
    prazo_confirmacao_min: float
    texto_recebido: str | None          # o que foi digitado; None = usar o texto registrado
    # o trabalho
    texto: str | None                   # entrada: o texto do chamado, como chegou
    ticket: dict | None                 # consultar
    classe: str | None                  # triagem
    log_diverge: bool                   # triagem
    termos: list[str]                   # triagem
    candidatos: list[dict]              # buscar (e conferir_ressalva, que só pode baixar o score)
    ressalvas_do_melhor: list[str]      # buscar: as frases de nao_cobre do primeiro candidato
    desfecho_proposto: dict | None      # decidir: {acao, kb_id, motivo}
    texto_redigido: str | None          # redigir
    erro_validacao: dict | None         # validar
    pendencia: dict | None              # pedir_confirmacao: a ação, com pedido_em e vence_em
    pendencia_id: int | None            # pedir_confirmacao: linha da tabela `pendencias`
    confirmacao: dict | None            # confirmar
    desfecho: dict | None               # gravar
    termino: str | None                 # triagem ou redigir (teto, erro) e finalizar
    motivo: str | None
    saida: dict | None                  # finalizar: o objeto do contrato, já validado
    # acumulados
    passos: Annotated[list[dict], operator.add]
    tentativas_redacao: Annotated[int, operator.add]
    n_chamadas_modelo: Annotated[int, operator.add]
    tokens_entrada: Annotated[int, operator.add]
    tokens_saida: Annotated[int, operator.add]
    tokens_embedding: Annotated[int, operator.add]     # buscar: os tokens da API de embedding (log; não entram no orçamento)
    custo_usd: Annotated[float, operator.add]
    segundos_gastos: Annotated[float, operator.add]   # só o tempo dentro dos nós: a espera não conta


@dataclass
class Contexto:
    """O que os nós usam e NÃO vai para o checkpoint: conexões e configuração da chamada."""
    client: object
    con: object
    preco_usd_por_mtok: tuple[float, float] = (0.15, 0.15)
    orcamento: Orcamento = field(default_factory=Orcamento)
    confirmador: object = None
    verbose: bool = True
    log_dir: Path | None = None


# ================================================================ APOIO AOS NÓS

def _passo(state, ferramenta: str, argumentos: dict | None = None, resultado: dict | None = None,
           erro: dict | None = None) -> dict:
    """Um registro da trajetória, no formato do `Passo` do laço (o log e a saída o leem)."""
    return {"indice": len(state.get("passos") or []), "ferramenta": ferramenta,
            "argumentos": argumentos or {}, "resultado": resultado, "erro": erro, "ms": 0}


def _no(funcao):
    """Embrulha um nó: mede o tempo gasto nele (teto de tempo) e mostra o passo no terminal."""
    def no(state: EstadoGrafo, runtime: Runtime[Contexto]) -> dict:
        t0 = time.monotonic()
        saida = funcao(state, runtime.context) or {}
        gasto = time.monotonic() - t0
        for p in saida.get("passos", []):
            p["ms"] = int(gasto * 1000)
            if runtime.context.verbose:
                status = f"ERRO: {p['erro']['erro']}" if p["erro"] else "ok"
                print(f"  nó {funcao.__name__:<17} {p['ferramenta']} "
                      f"{json.dumps(p['argumentos'], ensure_ascii=False)[:90]} -> {status}")
        return {**saida, "segundos_gastos": gasto}
    no.__name__ = funcao.__name__
    return no


def _teto(state, ctx: Contexto) -> str | None:
    """Os tetos que continuam sendo código nosso: tokens, custo e tempo. Conferidos antes de cada
    chamada ao modelo. O de passos virou o LIMITE_SUPERPASSOS."""
    o = ctx.orcamento
    tokens = state.get("tokens_entrada", 0) + state.get("tokens_saida", 0)
    if tokens >= o.max_tokens:
        return f"tokens: {tokens}/{o.max_tokens}"
    if state.get("custo_usd", 0.0) >= o.max_usd:
        return f"custo: US$ {state.get('custo_usd', 0.0):.4f}/{o.max_usd}"
    if state.get("segundos_gastos", 0.0) >= o.max_segundos:
        return f"tempo: {state.get('segundos_gastos', 0.0):.0f}s/{o.max_segundos:.0f}s"
    return None


def _chamar(ctx: Contexto, state, sistema: str, usuario: str) -> tuple[str, dict]:
    """Uma chamada ao modelo, pedindo JSON. Retentativa SÓ para falha de transporte (como no
    laço). Devolve o texto e o consumo, já no formato dos campos acumulados do estado."""
    args = dict(model=state["modelo"], response_format={"type": "json_object"},
                messages=[{"role": "system", "content": sistema},
                          {"role": "user", "content": usuario}])
    if state.get("temperatura") is not None:
        args["temperature"] = state["temperatura"]
    espera = 2
    for tentativa in range(5):
        try:
            resp = ctx.client.chat.completions.create(**args)
            break
        except (RateLimitError, APIConnectionError) as e:
            if tentativa == 4:
                raise ErroFatal(f"API indisponível após 5 tentativas: {e}")
            time.sleep(espera)
            espera *= 2
        except APIStatusError as e:
            raise ErroFatal(f"API recusou a chamada, status {e.status_code}")
    entrada = resp.usage.prompt_tokens if resp.usage else 0
    saida = resp.usage.completion_tokens if resp.usage else 0
    consumo = {"n_chamadas_modelo": 1, "tokens_entrada": entrada, "tokens_saida": saida,
               "custo_usd": (entrada * ctx.preco_usd_por_mtok[0]
                             + saida * ctx.preco_usd_por_mtok[1]) / 1_000_000}
    return (resp.choices[0].message.content or "").strip(), consumo


def _somar(a: dict, b: dict) -> dict:
    return {k: a.get(k, 0) + v for k, v in b.items()}


def _ler_json(texto: str, schema):
    """Valida a resposta do modelo contra o schema. Levanta ValueError com o que está errado."""
    try:
        return schema.model_validate(json.loads(texto))
    except json.JSONDecodeError:
        raise ValueError("a resposta não é um objeto JSON válido")
    except ValidationError as v:
        erro = v.errors()[0]
        raise ValueError(f"campo {'.'.join(str(x) for x in erro['loc']) or '(objeto)'}: {erro['msg']}")


def _registro_para_o_modelo(state) -> str:
    """O texto do cliente e o registro do chamado, como os dois nós de modelo os recebem."""
    t = state["ticket"]
    if t is None:
        return (f"Chamado: {state['id_ticket']}\nTexto do cliente:\n{state.get('texto') or '(sem texto)'}\n"
                f"Registro: o id não existe no sistema de tickets.")
    historico = "\n".join(f"  - {h['chamado_interno']}: {h['categoria']}, {h['criado_em']}, {h['status']}"
                          for h in t["historico_cliente"]) or "  (nenhum chamado interno anterior)"
    return (f"Chamado: {t['id']}\nCliente: {t['cliente']} (plano {t['plano']})\n"
            f"Texto do cliente:\n{state['texto']}\n\n"
            f"Log anexado:\n{t['anexo_log'] or '(nenhum)'}\n\n"
            f"Histórico de chamados internos do cliente:\n{historico}")


# ================================================================ OS NÓS

def entrada(state, ctx):
    """CÓDIGO. A entrada é o texto do chamado, acompanhado do id (mesma regra do laço)."""
    _, texto = _entrada(ctx.con, state["id_ticket"], state.get("texto_recebido"))
    return {"texto": texto}


def consultar(state, ctx):
    """CÓDIGO. Lê o chamado, o plano, o log anexado e o histórico. No laço era uma ferramenta que
    o modelo escolhia chamar; aqui toda execução consulta."""
    id_ticket = state["id_ticket"]
    try:
        if not db.ID_TICKET.match(id_ticket or ""):
            raise db.RegistroNaoEncontrado(id_ticket)
        ticket = db.buscar_ticket(ctx.con, id_ticket)
    except db.RegistroNaoEncontrado:
        return {"ticket": None, "passos": [_passo(
            state, "consultar_ticket", {"id_ticket": id_ticket},
            erro={"erro": "chamado não encontrado no sistema de tickets", "recebido": id_ticket})]}
    publico = {k: v for k, v in ticket.items() if not k.startswith("_") and k != "texto"}
    return {"ticket": ticket,
            "passos": [_passo(state, "consultar_ticket", {"id_ticket": id_ticket}, publico)]}


def triagem(state, ctx):
    """MODELO. Classifica o assunto, diz se o log aponta outro serviço e escolhe os termos de
    busca. Saída estruturada: fora do contrato, volta ao modelo uma vez, com o erro."""
    # ETAPA "triagem" — técnica: zero-shot, classificação com saída em JSON validada por schema
    # (cabeçalho de src/prompts/triagem-v1.md). temperature=0: a mesma entrada deve dar a mesma rota.
    sistema, usuario = _ler_prompt(PROMPT_TRIAGEM), _registro_para_o_modelo(state)
    consumo, erro = {}, None
    for _ in range(MAX_TENTATIVAS_TRIAGEM):
        motivo = _teto({**state, **_somar(state, consumo)}, ctx)
        if motivo:
            return {**consumo, "termino": Termino.ORCAMENTO.value, "motivo": motivo}
        pedido = usuario if erro is None else (
            f"{usuario}\n\nERRO DA TENTATIVA ANTERIOR: {erro}. Responda de novo, só com o JSON.")
        try:
            texto, uso = _chamar(ctx, state, sistema, pedido)
        except ErroFatal as f:
            return {**consumo, "termino": Termino.ERRO_FATAL.value, "motivo": str(f)}
        consumo = _somar(consumo, uso)
        try:
            t = _ler_json(texto, Triagem)
        except ValueError as v:
            erro = str(v)
            continue
        termos = [str(x).strip() for x in t.termos_busca if str(x).strip()]
        resultado = {"classe": t.classe, "log_aponta_outro_servico": t.log_aponta_outro_servico,
                     "termos_busca": termos, "justificativa": t.justificativa}
        return {**consumo, "classe": t.classe, "log_diverge": t.log_aponta_outro_servico,
                "termos": termos, "passos": [_passo(state, "triagem", {}, resultado)]}
    return {**consumo, "termino": Termino.ERRO_FATAL.value,
            "motivo": f"triagem fora do contrato em {MAX_TENTATIVAS_TRIAGEM} tentativas: {erro}",
            "passos": [_passo(state, "triagem", {}, erro={"erro": erro})]}


# Como o nó `buscar` recupera: "vetorial" (o cosseno do relato com cada guia, src/vetorial.py; o
# padrão) ou "palavra" (a busca da Parte 1, db.buscar_kb). A segunda existe para medir e para os
# testes offline, que não chamam a API de embedding (main.py --busca palavra). A busca híbrida
# (vetor + palavra) foi medida e não rendeu nada sobre o só vetorial: docs/rag.md §4.1.
BUSCA = "vetorial"


def buscar(state, ctx):
    """CÓDIGO. Recupera os procedimentos, com score. Roda só na rota técnica. A busca vetorial
    consulta pelo texto do cliente; a por palavra usa os termos que a triagem escolheu, e o texto
    vai junto para as ressalvas literais (docs/rag.md §4 e §5). Guarda as ressalvas do primeiro
    guia, para a aresta seguinte decidir se o modelo precisa lê-las."""
    antes = vetorial.TOKENS_EMBEDDING
    if BUSCA == "palavra":
        candidatos = db.buscar_kb(ctx.con, state["termos"], relato=state["texto"])
    else:
        candidatos = vetorial.buscar(ctx.con, state["termos"], relato=state["texto"], modo="vetorial")
    frases = []
    if candidatos:
        artigo = db.buscar_artigo(ctx.con, candidatos[0]["kb_id"])
        frases = [f.strip() for f in artigo["nao_cobre"].split(";") if f.strip()] if artigo else []
    return {"candidatos": candidatos, "ressalvas_do_melhor": frases,
            "tokens_embedding": vetorial.TOKENS_EMBEDDING - antes,
            "passos": [_passo(state, "buscar_base_conhecimento", {"termos": state["termos"]},
                              {"resultados": candidatos, "limiar_para_agir_sozinho": LIMIAR_CONFIANCA})]}


def conferir_ressalva(state, ctx):
    """MODELO, com a garantia em CÓDIGO. O embedding não enxerga as exceções de um guia (coluna
    nao_cobre): "o erro 502 vai e vem" fica tão perto do guia da falha constante quanto o relato
    normal (docs/rag.md §4.2). Este nó pede ao modelo que LEIA as situações que o primeiro guia
    não cobre e diga se o relato cai numa delas. O código só aplica o redutor da busca
    (db.REDUTOR), e só se a frase citada for uma das do guia: o modelo pode BAIXAR o score, nunca
    subir, e não inventa uma exceção."""
    # ETAPA "conferir_ressalva" — técnica: zero-shot, classificação binária com saída em JSON
    # validada por schema (cabeçalho de src/prompts/ressalva-v3.md). temperature=0.
    melhor, frases = state["candidatos"][0], state["ressalvas_do_melhor"]
    sistema = _ler_prompt(PROMPT_RESSALVA)
    usuario = (f"{_registro_para_o_modelo(state)}\n\nProcedimento: {melhor['kb_id']} - {melhor['titulo']}\n"
               f"Causa: {melhor['causa']}\n\nSituações que o procedimento NÃO cobre:\n"
               + "\n".join(f"- {f}" for f in frases))
    argumentos = {"kb_id": melhor["kb_id"], "situacoes": frases}
    # Memória semântica: os fatos do ambiente do cliente que o analista confirmou entram como
    # contexto do relato. O nó continua só podendo baixar o score.
    fatos = db.fatos_do_cliente(ctx.con, (state.get("ticket") or {}).get("_cliente_id")) if MEMORIA else {}
    if fatos:
        usuario += ("\n\nFatos confirmados sobre o ambiente do cliente:\n"
                    + "\n".join(f"- {f['texto']}" for f in fatos.values()))
        argumentos["fatos"] = {c: f["valor"] for c, f in fatos.items()}
    consumo, erro = {}, None
    for _ in range(MAX_TENTATIVAS_RESSALVA):
        motivo = _teto({**state, **_somar(state, consumo)}, ctx)
        if motivo:
            return {**consumo, "termino": Termino.ORCAMENTO.value, "motivo": motivo}
        pedido = usuario if erro is None else (
            f"{usuario}\n\nERRO DA TENTATIVA ANTERIOR: {erro}. Responda de novo, só com o JSON.")
        try:
            texto, uso = _chamar(ctx, state, sistema, pedido)
        except ErroFatal as f:
            return {**consumo, "termino": Termino.ERRO_FATAL.value, "motivo": str(f)}
        consumo = _somar(consumo, uso)
        try:
            r = _ler_json(texto, Ressalva)
        except ValueError as v:
            erro = str(v)
            continue
        frase = r.frase.strip()
        if r.cai_na_ressalva and frase not in frases:
            erro = f"campo frase: deve ser uma das situações da lista, copiada igual (recebido: {frase!r})"
            continue
        resultado = {"cai_na_ressalva": r.cai_na_ressalva, "frase": frase if r.cai_na_ressalva else "",
                     "motivo": r.motivo, "score_antes": melhor["score"], "score_depois": melhor["score"]}
        if not r.cai_na_ressalva:
            return {**consumo, "passos": [_passo(state, "conferir_ressalva", argumentos, resultado)]}
        baixado = round(melhor["score"] * db.REDUTOR, 2)
        resultado["score_depois"] = baixado
        novo = {**melhor, "score": baixado, "ressalva_por": "modelo",
                "ressalva": f"este procedimento NÃO cobre o caso relatado ('{frase}'): o score foi reduzido"}
        return {**consumo, "candidatos": [novo] + state["candidatos"][1:],
                "passos": [_passo(state, "conferir_ressalva", argumentos, resultado)]}
    return {**consumo, "termino": Termino.ERRO_FATAL.value,
            "motivo": f"conferência da ressalva fora do contrato em {MAX_TENTATIVAS_RESSALVA} tentativas: {erro}",
            "passos": [_passo(state, "conferir_ressalva", argumentos, erro={"erro": erro})]}


def decidir(state, ctx):
    """CÓDIGO. Escolhe o desfecho. É o portão de confiança e a regra de rota num lugar só: o
    modelo entregou a classe e o sinal de divergência; o resto é campo, contagem e limiar."""
    classe, candidatos = state.get("classe"), state.get("candidatos") or []
    melhor = candidatos[0] if candidatos else None
    kb_id = None
    if state["ticket"] is None:
        acao, motivo = "fila_humana", "id_inexistente"
    elif classe == "comercial":
        acao, motivo = "fila_comercial", "assunto_comercial"
    elif classe == "fora_da_alcada":
        acao, motivo = "fila_humana", "fora_da_alcada"
    elif classe == "insuficiente":
        # Um pedido de informação por chamado, contado no BANCO (vale entre execuções).
        if db.contar_pedidos_cliente(ctx.con, state["id_ticket"]) == 0:
            acao, motivo = "devolver_cliente", "informacao_insuficiente"
        else:
            acao, motivo = "fila_humana", "pedido_ja_feito"
    elif state.get("log_diverge"):
        # A divergência é decidida ANTES de olhar o score: um procedimento bem recuperado não
        # autoriza agir quando o log aponta outro serviço (TKT-0002, rodada 3 do laço).
        acao, motivo = "fila_humana", "divergencia_relato_log"
    elif melhor is None:
        acao, motivo = "fila_humana", "sem_procedimento"
    elif melhor["score"] < LIMIAR_CONFIANCA:
        acao, motivo = "fila_humana", "score_abaixo_do_limiar"
    elif melhor["acao_padrao"] == "escalar":
        acao, motivo, kb_id = "abrir_chamado_interno", "procedimento_escalar", melhor["kb_id"]
    else:
        acao, motivo, kb_id = "anotacao_interna", "procedimento_anotar", melhor["kb_id"]
    proposto = {"acao": acao, "kb_id": kb_id, "motivo": motivo}
    return {"desfecho_proposto": proposto, "passos": [_passo(state, "decidir", {}, proposto)]}


def redigir(state, ctx):
    """MODELO. Redige o resumo ou a mensagem do desfecho que o código já decidiu. No pedido de
    informação ao cliente o modelo NÃO é chamado: o texto é o padrão (PEDIDO_AO_CLIENTE)."""
    proposto, candidatos = state["desfecho_proposto"], state.get("candidatos") or []
    if proposto["acao"] == "devolver_cliente":
        return {"texto_redigido": PEDIDO_AO_CLIENTE, "tentativas_redacao": 1,
                "passos": [_passo(state, "redigir", {"desfecho": proposto["acao"], "texto_padrao": True},
                                  {"texto": PEDIDO_AO_CLIENTE})]}
    # ETAPA "redigir" — técnica: zero-shot, geração com saída em JSON de um campo (cabeçalho de
    # src/prompts/redigir-v3.md). temperature=0: o texto vai para um registro, não é conversa.
    motivo = _teto(state, ctx)
    if motivo:
        return {"termino": Termino.ORCAMENTO.value, "motivo": motivo}
    usuario = (f"DESFECHO: {proposto['acao']}\nMOTIVO: {proposto['motivo']}\n\n"
               f"{_registro_para_o_modelo(state)}")
    if state.get("termos"):
        usuario += f"\n\nTermos buscados na base: {', '.join(state['termos'])}"
    if candidatos:
        c = candidatos[0]
        usuario += (f"\n\nProcedimento encontrado: {c['kb_id']} - {c['titulo']} (score {c['score']}, "
                    f"limiar {LIMIAR_CONFIANCA})\nCausa: {c['causa']}\nSolução: {c['solucao']}")
        if c.get("ressalva"):
            usuario += f"\nRESSALVA: {c['ressalva']}"
    elif state.get("classe") == "tecnico":
        usuario += "\n\nProcedimento encontrado: nenhum"
    ficha = db.ficha_do_plano(ctx.con, state["ticket"]["plano"]) if (
        state.get("classe") == "tecnico" and state.get("ticket")) else None
    if ficha:      # contexto: o que o suporte do plano cobre. Não muda o desfecho, que já está decidido
        usuario += f"\n\nEscopo do plano do cliente ({ficha['plano']}): {ficha['escopo']}"
    if state.get("erro_validacao"):
        usuario += (f"\n\nERRO DA TENTATIVA ANTERIOR: "
                    f"{json.dumps(state['erro_validacao'], ensure_ascii=False)}")
    try:
        texto, consumo = _chamar(ctx, state, _ler_prompt(PROMPT_REDIGIR), usuario)
    except ErroFatal as f:
        return {"termino": Termino.ERRO_FATAL.value, "motivo": str(f)}
    try:
        redigido, erro = _ler_json(texto, Redacao).texto.strip(), None
    except ValueError as v:
        redigido, erro = None, {"erro": str(v)}
    return {**consumo, "texto_redigido": redigido, "tentativas_redacao": 1,
            "passos": [_passo(state, "redigir", {"desfecho": proposto["acao"]},
                              None if erro else {"texto": redigido}, erro)]}


def _erro_do_texto(con, acao: str, texto: str) -> dict | None:
    """A regra do texto de um desfecho: tamanho mínimo e, no pedido ao cliente, nenhuma informação
    interna. Vale para o que o modelo redige (nó `validar`) e para o que o analista corrige na
    aprovação com edição (retomar_grafo): quem escreve muda, a regra não."""
    minimo = 20 if acao == "abrir_chamado_interno" else 10
    if len((texto or "").strip()) < minimo:
        return {"erro": "texto curto demais ou ausente", "esperado": f"pelo menos {minimo} caracteres"}
    if acao == "devolver_cliente":
        try:
            _exigir_pedido_sem_informacao_interna(con, texto)
        except ErroRecuperavel as r:
            return r.payload
    return None


def validar(state, ctx):
    """CÓDIGO. O avaliador do texto: tamanho mínimo e, no pedido ao cliente, nenhuma informação
    interna. São as validações das ferramentas de escrita do laço."""
    acao, texto = state["desfecho_proposto"]["acao"], state.get("texto_redigido") or ""
    erro = _erro_do_texto(ctx.con, acao, texto)
    if erro is None:
        return {"erro_validacao": None}
    return {"erro_validacao": erro, "passos": [_passo(state, "validar", {"desfecho": acao}, erro=erro)]}


def pedir_confirmacao(state, ctx):
    """CÓDIGO. Monta a ação irreversível como o analista vai vê-la e marca o prazo. Fica num nó
    separado do `interrupt` porque o nó que pausa roda de novo, desde o começo, na retomada: a
    hora do pedido e a linha em `pendencias` não podem ser refeitas."""
    proposto = state["desfecho_proposto"]
    pedido_em = datetime.now().astimezone()
    vence_em = pedido_em + timedelta(minutes=state["prazo_confirmacao_min"])
    if proposto["acao"] == "devolver_cliente":
        # H2. Não há guia, score nem prioridade: o que o analista julga é se o relato era mesmo
        # insuficiente e se a mensagem pode ir ao cliente. Por isso a tela traz o relato.
        pendencia = {"ferramenta": "devolver_cliente", "id_ticket": state["id_ticket"],
                     "relato": state["texto"], "mensagem": state["texto_redigido"],
                     "plano": state["ticket"]["plano"]}
    else:
        pendencia = _pendencia_do_chamado(state, ctx, proposto)
    pendencia.update(pedido_em=pedido_em.isoformat(timespec="seconds"),
                     vence_em=vence_em.isoformat(timespec="seconds"))
    pendencia_id = None
    if ctx.confirmador is None:            # ninguém responde na hora: entra na fila do analista
        pendencia_id = db.criar_pendencia(ctx.con, state["id_ticket"], pendencia,
                                          pendencia["pedido_em"], pendencia["vence_em"])
        db.gravar_checkpoint(ctx.con, pendencia_id,
                             {"motor": "grafo", "thread_id": state["id_ticket"],
                              "log_dir": str(ctx.log_dir) if ctx.log_dir else None})
    return {"pendencia": pendencia, "pendencia_id": pendencia_id}


def _pendencia_do_chamado(state, ctx, proposto: dict) -> dict:
    """H1: a abertura do chamado interno, como o analista a vê (sem as horas do pedido e do prazo)."""
    artigo = db.buscar_artigo(ctx.con, proposto["kb_id"])
    # A prioridade entra na tela como PREVISTA: é a regra da abertura (procedimento + reincidência)
    # aplicada agora. A do chamado é calculada de novo na gravação, e ninguém a edita.
    return {"ferramenta": "abrir_chamado_interno", "id_ticket": state["id_ticket"],
            "categoria": artigo["categoria"], "resumo": state["texto_redigido"],
            "time_destino": artigo["time_destino"], "kb_id": proposto["kb_id"],
            "prioridade_prevista": db.prioridade_prevista(ctx.con, state["ticket"], artigo),
            "guia_publicado_em": artigo["data_publicacao"],
            "guia_nao_cobre": [f.strip() for f in artigo["nao_cobre"].split(";") if f.strip()],
            "plano": state["ticket"]["plano"],
            "escopo_do_plano": (db.ficha_do_plano(ctx.con, state["ticket"]["plano"]) or {}).get("escopo"),
            # Memória episódica: o que o analista já decidiu sobre este guia e os últimos
            # episódios do cliente na categoria. Só informa: o desfecho já está decidido.
            "precedentes": db.precedentes(ctx.con, proposto["kb_id"], state["ticket"]["_cliente_id"],
                                          artigo["categoria"]) if MEMORIA else None,
            # Memória semântica: os fatos do ambiente do cliente confirmados por um analista.
            "fatos_cliente": {c: f["valor"] for c, f in db.fatos_do_cliente(
                ctx.con, state["ticket"]["_cliente_id"]).items()} if MEMORIA else None}


def confirmar(state, ctx):
    """⏸ H1 e H2. Só pausa e lê a resposta: nada com efeito colateral acontece antes do `interrupt`.
    Quem decide é o relógio antes da pessoa: resposta depois do `vence_em` é prazo vencido.
    Aprovar EDITANDO: a resposta traz o texto corrigido pelo analista (o resumo do chamado, no H1;
    a mensagem ao cliente, no H2). O original do modelo fica registrado ao lado, e é o texto
    aprovado que o nó `gravar` escreve."""
    pendencia = state["pendencia"]
    campo, chave_original, chave_aprovado = CAMPO_EDITAVEL[pendencia["ferramenta"]]
    texto_aprovado = motivo_rejeicao = None
    if ctx.confirmador is not None:        # --auto-aprovar e testes: a resposta vem na hora
        ok, por = ctx.confirmador(pendencia)
        status, quando = ("aprovada" if ok else "rejeitada"), _agora()
    else:
        resposta = interrupt(pendencia)    # {"decisao": aprovar|rejeitar|vencer, "por", "quando"}
        quando, por = resposta["quando"], resposta["por"]
        if datetime.fromisoformat(quando) >= datetime.fromisoformat(pendencia["vence_em"]):
            status, por = "vencida", "ninguém: prazo vencido"
        else:
            status = {"aprovar": "aprovada", "rejeitar": "rejeitada"}[resposta["decisao"]]
        db.resolver_pendencia(ctx.con, state["pendencia_id"], status, quando, por)
        novo = (resposta.get(campo) or "").strip()
        if status == "aprovada" and novo and novo != (pendencia[campo] or "").strip():
            texto_aprovado = novo          # prazo vencido ou rejeição: a edição não vale nada
        if status == "rejeitada":          # o motivo só vale numa rejeição dada no prazo
            motivo_rejeicao = resposta.get("motivo_rejeicao")
    confirmacao = {"pendencia": pendencia, "aprovado": status == "aprovada", "por": por,
                   "status": status, "resolvido_em": quando, "editado": texto_aprovado is not None}
    if texto_aprovado is not None:
        confirmacao.update({chave_original: pendencia[campo], chave_aprovado: texto_aprovado})
    if motivo_rejeicao:
        confirmacao["motivo_rejeicao"] = motivo_rejeicao
    argumentos = ({"kb_id": pendencia["kb_id"]} if "kb_id" in pendencia
                  else {"acao": pendencia["ferramenta"]})
    return {"confirmacao": confirmacao,
            "passos": [_passo(state, "confirmar", argumentos,
                              {"status": status, "por": por, "editado": confirmacao["editado"]})]}


def gravar(state, ctx):
    """CÓDIGO. A única escrita de desfecho da execução. Abrir chamado é idempotente pela chave
    ticket:kb_id, e o pedido ao cliente pelo chamado (um por chamado); ação rejeitada ou vencida
    vira fila humana com as considerações (e o aviso ao gestor, se o chamado seria P1), pela mesma
    função do laço."""
    proposto, texto, id_ticket = state["desfecho_proposto"], state["texto_redigido"].strip(), state["id_ticket"]
    acao = proposto["acao"]
    if acao in CAMPO_EDITAVEL and state["confirmacao"]["status"] != "aprovada":
        motivo = (MOTIVO_REJEITADA if state["confirmacao"]["status"] == "rejeitada"
                  else MOTIVO_PRAZO_VENCIDO)
        apoio = SimpleNamespace(prazo_confirmacao_min=state["prazo_confirmacao_min"],
                                ticket=state["ticket"], desfecho=None,
                                scores_kb={c["kb_id"]: c["score"] for c in state.get("candidatos") or []})
        argumentos, resultado = encaminhar_pendencia(apoio, ctx.con, state["pendencia"], motivo)
        return {"desfecho": apoio.desfecho,
                "passos": [_passo(state, "registrar_encaminhamento", argumentos, resultado)]}
    if acao in CAMPO_EDITAVEL:
        # aprovado com edição: grava o texto do analista, e não o do modelo
        texto = state["confirmacao"].get(CAMPO_EDITAVEL[acao][2]) or texto
    if acao == "abrir_chamado_interno":
        resultado = db.abrir_chamado(ctx.con, state["ticket"], texto,
                                     db.buscar_artigo(ctx.con, proposto["kb_id"]))
        desfecho = {"acao": acao, "kb_id": proposto["kb_id"], **resultado}
        argumentos = {"id_ticket": id_ticket, "resumo": texto, "kb_id": proposto["kb_id"]}
        return {"desfecho": desfecho,
                "passos": [_passo(state, "abrir_chamado_interno", argumentos, resultado)]}
    if acao == "devolver_cliente":
        # O envio. Segunda barreira do "um pedido por chamado": a primeira é a contagem do nó
        # `decidir`, feita antes da espera pelo analista.
        resultado = db.registrar_pedido_cliente(ctx.con, id_ticket, texto)
        argumentos = {"id_ticket": id_ticket, "destino": acao, "mensagem": texto}
        return {"desfecho": {"acao": acao, "kb_id": None, **resultado},
                "passos": [_passo(state, "registrar_encaminhamento", argumentos, resultado)]}
    kb_id = proposto["kb_id"] if acao == "anotacao_interna" else None
    resultado = db.registrar_encaminhamento(ctx.con, id_ticket, acao, texto, kb_id)
    desfecho = {"acao": acao, "kb_id": kb_id, **resultado}
    argumentos = {"id_ticket": id_ticket, "destino": acao, "mensagem": texto}
    if kb_id:
        argumentos["kb_id"] = kb_id
    if proposto["motivo"] == "fora_da_alcada":
        desfecho["motivo"] = argumentos["motivo"] = "fora_da_alcada"
    return {"desfecho": desfecho,
            "passos": [_passo(state, "registrar_encaminhamento", argumentos, resultado)]}


def finalizar(state, ctx):
    """CÓDIGO. Toda execução termina com um término e um motivo, e a saída passa pelo schema."""
    termino, motivo = state.get("termino"), state.get("motivo")
    if termino is None and state.get("desfecho"):
        termino = Termino.RESPONDEU.value
    elif termino is None:
        termino = Termino.ERRO_FATAL.value
        erro = (state.get("erro_validacao") or {}).get("erro", "execução terminou sem desfecho")
        motivo = f"texto redigido recusado em {MAX_REDACOES} tentativas: {erro}"
    try:
        saida = _estado_de({**state, "termino": termino, "motivo": motivo}).saida.model_dump()
    except ValidationError as v:
        termino, saida = Termino.ERRO_FATAL.value, None
        motivo = f"saída fora do contrato: {v.errors()[0]['msg']}"
    return {"termino": termino, "motivo": motivo, "saida": saida}


# ================================================================ AS ARESTAS CONDICIONAIS
# Cada função devolve uma chave; o mapa de destinos de cada uma está escrito em _construir().

def _rota_consultar(state) -> str:
    """Decide: código (campo vazio). Id que não existe não tem o que classificar."""
    return "existe" if state["ticket"] is not None else "nao_existe"


def _rota_triagem(state) -> str:
    """Decide: o MODELO (a classe), e o código só lê o valor. Teto ou erro encerram."""
    if state.get("termino"):
        return "encerrar"
    return "tecnico" if state["classe"] == "tecnico" else "sem_busca"


def _rota_buscar(state) -> str:
    """Decide: código. O modelo só é chamado quando há o que conferir: o primeiro guia passaria do
    limiar, ainda não caiu numa ressalva literal e declara situações que não cobre."""
    candidatos = state.get("candidatos") or []
    if (candidatos and candidatos[0]["score"] >= LIMIAR_CONFIANCA
            and not candidatos[0].get("ressalva") and state.get("ressalvas_do_melhor")):
        return "conferir"
    return "decidir"


def _rota_conferir(state) -> str:
    """Decide: código. Teto ou erro de contrato encerram; senão segue para a decisão."""
    return "encerrar" if state.get("termino") else "decidir"


def _rota_redigir(state) -> str:
    """Decide: código. Teto estourado ou API fora encerram; senão o texto vai ao avaliador."""
    return "encerrar" if state.get("termino") else "avaliar"


def _rota_validar(state) -> str:
    """Decide: código. Texto reprovado volta ao modelo uma vez; aprovado, o tipo do desfecho diz
    se a escrita é irreversível e pede a confirmação humana."""
    if state.get("erro_validacao"):
        return "redigir_de_novo" if state.get("tentativas_redacao", 0) < MAX_REDACOES else "encerrar"
    if state["desfecho_proposto"]["acao"] in CAMPO_EDITAVEL:      # H1 e H2
        return "irreversivel"
    return "reversivel"


# ================================================================ O GRAFO

def _construir() -> StateGraph:
    g = StateGraph(EstadoGrafo, context_schema=Contexto)
    for funcao in (entrada, consultar, triagem, buscar, conferir_ressalva, decidir, redigir, validar,
                   pedir_confirmacao, confirmar, gravar, finalizar):
        g.add_node(funcao.__name__, _no(funcao))
    g.add_edge(START, "entrada")
    g.add_edge("entrada", "consultar")
    g.add_conditional_edges("consultar", _rota_consultar,
                            {"existe": "triagem", "nao_existe": "decidir"})
    g.add_conditional_edges("triagem", _rota_triagem,
                            {"tecnico": "buscar", "sem_busca": "decidir", "encerrar": "finalizar"})
    g.add_conditional_edges("buscar", _rota_buscar, {"conferir": "conferir_ressalva", "decidir": "decidir"})
    g.add_conditional_edges("conferir_ressalva", _rota_conferir,
                            {"decidir": "decidir", "encerrar": "finalizar"})
    g.add_edge("decidir", "redigir")
    g.add_conditional_edges("redigir", _rota_redigir,
                            {"avaliar": "validar", "encerrar": "finalizar"})
    g.add_conditional_edges("validar", _rota_validar,
                            {"redigir_de_novo": "redigir", "irreversivel": "pedir_confirmacao",
                             "reversivel": "gravar", "encerrar": "finalizar"})
    g.add_edge("pedir_confirmacao", "confirmar")
    g.add_edge("confirmar", "gravar")
    g.add_edge("gravar", "finalizar")
    g.add_edge("finalizar", END)
    return g


# Checkpointer em SQLite, num arquivo próprio (ignorado pelo git): a espera pelo analista
# atravessa processos, e em memória ela morreria com o processo. CHECKPOINT_DB troca o arquivo
# (os testes usam ":memory:").
CHECKPOINT_DB = os.environ.get("CHECKPOINT_DB") or str(RAIZ / "dados" / "checkpoints.db")
CHECKPOINTER = SqliteSaver(sqlite3.connect(CHECKPOINT_DB, check_same_thread=False))

# Compilado UMA vez, na importação. É este objeto que conferir_grafo.py importa.
GRAFO = _construir().compile(checkpointer=CHECKPOINTER)


# ================================================================ EXECUTAR E RETOMAR

def _config(id_ticket: str) -> dict:
    return {"configurable": {"thread_id": id_ticket}, "recursion_limit": LIMITE_SUPERPASSOS}


def _estado_de(v: dict, **extra) -> Estado:
    """Converte o estado do grafo no `Estado` do laço, para a saída validada (montar_saida), o
    verificador e o terminal serem os mesmos nos dois caminhos."""
    e = Estado(
        id_ticket=v["id_ticket"], modelo=v["modelo"], execucao_id=v["execucao_id"],
        executado_em=v["executado_em"], commit=v.get("commit"), entrada=v.get("texto"),
        prompt=f"{PROMPT_TRIAGEM.name} + {PROMPT_RESSALVA.name} + {PROMPT_REDIGIR.name}", temperatura=v.get("temperatura"),
        passos=[Passo(**p) for p in v.get("passos") or []],
        n_chamadas_modelo=v.get("n_chamadas_modelo", 0),
        tokens_entrada=v.get("tokens_entrada", 0), tokens_saida=v.get("tokens_saida", 0),
        custo_usd=v.get("custo_usd", 0.0), desfecho=v.get("desfecho"), ticket=v.get("ticket"),
        scores_kb={c["kb_id"]: c["score"] for c in v.get("candidatos") or []},
        n_buscas=sum(p["ferramenta"] == "buscar_base_conhecimento" for p in v.get("passos") or []),
        confirmacoes=[v["confirmacao"]] if v.get("confirmacao") else [],
        prazo_confirmacao_min=v.get("prazo_confirmacao_min", PRAZO_CONFIRMACAO_MIN),
        pendencia_id=v.get("pendencia_id"))
    e.termino = Termino(extra.get("termino") or v.get("termino") or Termino.ERRO_FATAL.value)
    e.motivo = extra.get("motivo") or v.get("motivo")
    e.pendencia = extra.get("pendencia")
    e.saida = montar_saida(e)
    return e


# Memória episódica (docs/memoria.md §1.3 e §2.2). Ligada, cada execução concluída do grafo grava
# um episódio, e a tela do H1 mostra os precedentes. `--sem-memoria` desliga a leitura e a escrita,
# para duas rodadas continuarem comparáveis (§2.4). O laço da Parte 1 não tem memória.
MEMORIA = True


def _episodio(v: dict, e: Estado, con) -> dict:
    """O registro episódico da execução, só com campos estruturados do estado: nada do texto do
    cliente, do log anexado ou do que o modelo redigiu."""
    proposto, ticket = v.get("desfecho_proposto") or {}, v.get("ticket") or {}
    desfecho, conf = v.get("desfecho") or {}, v.get("confirmacao")
    kb_id = proposto.get("kb_id")
    artigo = db.buscar_artigo(con, kb_id) if kb_id else None
    score = next((c["score"] for c in v.get("candidatos") or [] if c["kb_id"] == kb_id), None)
    veredito = None
    if conf:
        veredito = {"aprovada": "editado" if conf.get("editado") else "aprovado",
                    "rejeitada": "rejeitado", "vencida": "vencido"}[conf["status"]]
    motivo = desfecho.get("motivo") or proposto.get("motivo") or e.motivo
    resumo = (f"{v['id_ticket']}: classe {v.get('classe') or 'sem triagem'}; "
              + (f"guia {kb_id} (score {score}); " if kb_id else "sem guia; ")
              + f"proposto {proposto.get('acao') or 'nada'}; gravado {desfecho.get('acao') or 'nada'}"
              + (f"; analista: {veredito}" if veredito else "")
              + (f" ({conf['motivo_rejeicao']})" if conf and conf.get("motivo_rejeicao") else "")
              + f"; término {e.termino.value}")
    return {"execucao_id": v["execucao_id"],      # não é coluna: entra na chave de idempotência
            "ticket_externo": v["id_ticket"], "cliente_id": ticket.get("_cliente_id"),
            "classe": v.get("classe"), "categoria": artigo["categoria"] if artigo else None,
            "kb_id": kb_id, "score": score, "acao_proposta": proposto.get("acao"),
            "desfecho": desfecho.get("acao"), "motivo": motivo, "veredito": veredito,
            "motivo_rejeicao": (conf or {}).get("motivo_rejeicao"),
            "termino": e.termino.value, "resumo": resumo, "criado_em": _agora()}


def _concluir(id_ticket: str, log_dir: Path | None, con, estourou: bool = False) -> Estado:
    """Lê o que ficou no checkpoint depois de uma invocação e devolve o `Estado`, com o log.
    Execução concluída: o checkpoint é apagado aqui, depois do log. Ele guarda o texto do cliente
    e o log anexado por inteiro, e só serve para retomar (docs/memoria.md §1.4)."""
    foto = GRAFO.get_state(_config(id_ticket))
    v = foto.values
    if estourou:
        e = _estado_de(v, termino=Termino.ORCAMENTO.value,
                       motivo=f"superpassos: limite de {LIMITE_SUPERPASSOS} atingido")
    elif foto.next:                        # parou no `interrupt`: ainda não passou por `finalizar`
        p = v["pendencia"]
        e = _estado_de(v, termino=Termino.HUMANO.value, pendencia=p,
                       motivo=(f"aguardando a confirmação do analista até {p['vence_em']} "
                               f"(prazo de {v['prazo_confirmacao_min']:g} minutos)"))
    else:
        e = _estado_de(v)
    episodio = None
    if MEMORIA and (estourou or not foto.next):   # execução pausada ainda não é um episódio
        episodio = _episodio(v, e, con)
        episodio.update(db.registrar_episodio(con, episodio))     # id, chave, ja_existia
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        registro = e.para_dict()
        registro.pop("prompt_lembrete", None)          # o grafo não tem lembrete
        registro.update(motor="langgraph", classe=v.get("classe"), log_diverge=v.get("log_diverge"),
                        desfecho_proposto=v.get("desfecho_proposto"),
                        tentativas_redacao=v.get("tentativas_redacao", 0),
                        tokens_embedding=v.get("tokens_embedding", 0), episodio=episodio,
                        segundos_gastos=round(v.get("segundos_gastos", 0.0), 3))
        (log_dir / f"{id_ticket}.json").write_text(
            json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    if estourou or not foto.next:          # só a execução pausada precisa do checkpoint
        CHECKPOINTER.delete_thread(id_ticket)
    return e


def rodar_grafo(id_ticket: str, *, client, modelo: str, con, temperatura: float | None = 0.0,
                preco_usd_por_mtok: tuple[float, float] = (0.15, 0.15),
                orcamento: Orcamento | None = None, confirmador=None,
                log_dir: Path | None = None, verbose: bool = True, texto: str | None = None,
                prazo_confirmacao_min: float = PRAZO_CONFIRMACAO_MIN) -> Estado:
    """Uma execução nova no grafo. Mesma assinatura e mesmo retorno de agente.rodar()."""
    # Execução nova começa de um thread limpo: os campos acumulados (passos, tokens) somariam
    # com os da execução anterior do mesmo chamado.
    CHECKPOINTER.delete_thread(id_ticket)
    ctx = Contexto(client=client, con=con, preco_usd_por_mtok=preco_usd_por_mtok,
                   orcamento=orcamento or Orcamento(), confirmador=confirmador, verbose=verbose,
                   log_dir=log_dir)
    inicial = {"id_ticket": id_ticket, "modelo": modelo, "temperatura": temperatura,
               # Único por execução: entra na chave de idempotência do episódio (db.chave_do_episodio).
               # O relógio em segundos, como no laço, repetiria em duas execuções seguidas.
               "execucao_id": f"{id_ticket}-{uuid.uuid4().hex[:8]}",
               "executado_em": _agora(), "commit": _commit(), "texto_recebido": texto,
               "prazo_confirmacao_min": prazo_confirmacao_min}
    try:
        GRAFO.invoke(inicial, _config(id_ticket), context=ctx)
    except GraphRecursionError:
        return _concluir(id_ticket, log_dir, con, estourou=True)
    return _concluir(id_ticket, log_dir, con)


def retomar_grafo(id_ticket: str, decisao: str, *, client, con, por: str = "analista de suporte",
                  agora: datetime | None = None, log_dir: Path | None = None,
                  verbose: bool = True, resumo: str | None = None,
                  motivo_rejeicao: str | None = None, mensagem: str | None = None) -> Estado | None:
    """Responde ao `interrupt` (H1 ou H2) e deixa o grafo continuar. Mesmo contrato de
    agente.retomar(): devolve None quando não há o que fazer (nada pausado, "vencer" antes do
    prazo, ou resposta repetida: a segunda aprovação não encontra pausa e não grava nada).

    `resumo` (H1) e `mensagem` (H2) são a aprovação COM EDIÇÃO. Só o texto é editável: categoria,
    time e prioridade vêm do procedimento, e trocar o procedimento é outra ação (o caminho para ela
    é rejeitar). O texto do analista passa pela mesma regra do texto do modelo (na mensagem ao
    cliente, nenhuma informação interna), e é conferido ANTES de responder ao `interrupt`: edição
    recusada levanta EdicaoRecusada e a ação continua à espera. O mesmo vale para o motivo da
    rejeição, que tem de ser um dos da ação pendente (db.MOTIVOS_POR_ACAO)."""
    if decisao not in ("aprovar", "rejeitar", "vencer"):
        raise ValueError(f"decisão inválida: {decisao}")
    # O motivo é conferido antes de responder ao `interrupt`: motivo inválido não gasta a rejeição.
    if motivo_rejeicao is not None and (decisao != "rejeitar" or motivo_rejeicao not in db.MOTIVOS_REJEICAO):
        raise ValueError(f"motivo de rejeição inválido para '{decisao}': {motivo_rejeicao} "
                         f"(só com rejeitar; aceitos: {', '.join(db.MOTIVOS_REJEICAO)})")
    foto = GRAFO.get_state(_config(id_ticket))
    if "confirmar" not in foto.next:
        return None
    agora = agora or datetime.now().astimezone()
    if decisao == "vencer" and agora < datetime.fromisoformat(foto.values["pendencia"]["vence_em"]):
        return None
    ctx = Contexto(client=client, con=con, verbose=verbose)
    resposta = {"decisao": decisao, "por": por, "quando": agora.isoformat(timespec="seconds")}
    acao = foto.values["pendencia"]["ferramenta"]
    campo = CAMPO_EDITAVEL[acao][0]
    for nome, corrigido in (("resumo", resumo), ("mensagem", mensagem)):
        if corrigido is None:
            continue
        rotulo = {"resumo": "resumo corrigido", "mensagem": "mensagem corrigida"}[nome]
        if decisao != "aprovar":
            raise EdicaoRecusada(f"só a aprovação aceita {'um ' if nome == 'resumo' else 'uma '}{rotulo}")
        if nome != campo:
            raise EdicaoRecusada(f"a ação pendente é {acao}: o texto que o analista pode corrigir "
                                 f"é o campo '{campo}', e não '{nome}'")
        erro = _erro_do_texto(con, acao, corrigido)
        if erro:
            achados = erro.get("recebido")
            detalhe = (f"termos encontrados: {', '.join(achados)}; " if isinstance(achados, list) else "")
            verbo = "recusado" if nome == "resumo" else "recusada"
            raise EdicaoRecusada(f"{rotulo} {verbo}: {erro['erro']} "
                                 f"({detalhe}esperado: {erro['esperado']})")
        resposta[campo] = corrigido.strip()
    if motivo_rejeicao is not None:
        if motivo_rejeicao not in db.MOTIVOS_POR_ACAO[acao]:
            raise ValueError(f"motivo de rejeição '{motivo_rejeicao}' não vale para {acao} "
                             f"(aceitos: {', '.join(db.MOTIVOS_POR_ACAO[acao])})")
        resposta["motivo_rejeicao"] = motivo_rejeicao
    GRAFO.invoke(Command(resume=resposta), _config(id_ticket), context=ctx)
    return _concluir(id_ticket, log_dir, con)

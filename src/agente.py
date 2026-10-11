"""O agente: estado explícito, orçamento, laço de ferramentas e log de trajetória.

Mesma estrutura do agente.py da aula 05 (Estado / Passo / Orcamento / Termino),
enxuta para este caso. A ideia central: `mensagens[]` é só o transporte para a
API; o ESTADO do agente é o objeto `Estado`.

Onde cada coisa decide (item 2.3 / 4.4 do enunciado):

    MODELO  interpreta o texto livre do cliente, classifica o assunto, escolhe os
            termos de busca, escolhe o desfecho, corrige a chamada quando uma
            ferramenta devolve erro, redige o resumo do chamado.
    CÓDIGO  valida formato de id, calcula o score da base, aplica o portão de
            confiança, define time e prioridade, garante idempotência, pede a
            confirmação humana e aplica o prazo dela, impõe o orçamento e registra
            por que parou.
"""
import inspect
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError
from pydantic import ValidationError

import db
from ferramentas import (FERRAMENTAS_DE_ESCRITA, FUNCOES, LIMIAR_CONFIANCA,
                         MOTIVO_PRAZO_VENCIDO, MOTIVO_REJEITADA, PRAZO_CONFIRMACAO_MIN, SCHEMAS,
                         AcaoRejeitada, ErroFatal, ErroRecuperavel, PausaParaHumano,
                         aprovar_pendencia, encaminhar_pendencia)
from saida import Saida, montar_saida

RAIZ = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
PROMPT_ARQUIVO = PROMPTS / "agente-v5.md"
LEMBRETE_ARQUIVO = PROMPTS / "lembrete-v1.md"


def _ler_prompt(arquivo: Path) -> str:
    """Lê um prompt de src/prompts/ e descarta o bloco <!-- --> de documentação."""
    texto = arquivo.read_text(encoding="utf-8")
    if texto.lstrip().startswith("<!--"):
        texto = texto.split("-->", 1)[1]
    return texto.strip()


def _agora() -> str:
    """Data e hora da execução, com fuso (ISO 8601). Não é o "agora" fixo do banco simulado."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _commit() -> str | None:
    """Commit do código que rodou, para o log poder ser ligado a uma versão. Marca quando há
    alteração local em src/ ou dados/ ainda não commitada. None fora de um repositório git."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True,
                              timeout=5, check=True).stdout.strip()
    try:
        sujo = git("status", "--porcelain", "--", "src", "dados")
        return git("rev-parse", "--short", "HEAD") + (" + alterações locais" if sujo else "")
    except (OSError, subprocess.SubprocessError):
        return None


# ================================================================ TÉRMINO

class Termino(str, Enum):
    RESPONDEU = "respondeu"            # o modelo concluiu E registrou um desfecho
    ORCAMENTO = "orcamento_esgotado"   # bateu um dos tetos
    ERRO_FATAL = "erro_fatal"          # não há como continuar
    HUMANO = "aguardando_humano"       # ação irreversível à espera do analista, dentro do prazo


# ================================================================ ESTADO

@dataclass
class Passo:
    indice: int
    ferramenta: str
    argumentos: dict
    resultado: dict | None = None
    erro: dict | None = None           # erro de ferramenta é DADO, não exceção
    ms: int = 0


@dataclass
class Estado:
    id_ticket: str
    modelo: str
    execucao_id: str = ""
    executado_em: str = field(default_factory=_agora)      # início da execução (data, hora e fuso)
    commit: str | None = None
    entrada: str | None = None         # o texto do chamado, exatamente como chegou
    prompt: str = PROMPT_ARQUIVO.name      # a combinação em uso vai para o log
    temperatura: float | None = None
    passos: list[Passo] = field(default_factory=list)
    n_chamadas_modelo: int = 0
    lembretes: int = 0                 # vezes que o laço lembrou o modelo de registrar o desfecho
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0
    termino: Termino | None = None
    motivo: str | None = None
    resposta: str | None = None
    pendencia: dict | None = None
    desfecho: dict | None = None       # preenchido pela ferramenta de escrita que deu certo
    ticket: dict | None = None
    scores_kb: dict = field(default_factory=dict)
    n_buscas: int = 0                  # buscas na base feitas nesta execução (mesmo sem resultado)
    confirmacoes: list = field(default_factory=list)
    prazo_confirmacao_min: float = PRAZO_CONFIRMACAO_MIN   # prazo do analista, em minutos
    pendencia_id: int | None = None    # linha de `pendencias` quando a execução pausa à espera dele
    saida: Saida | None = None         # o objeto validado do contrato (src/saida.py)
    historico: list = field(default_factory=list)          # transporte p/ API (derivado)
    _confirmador: object = field(default=None, repr=False)

    @property
    def n_passos(self) -> int:
        return len(self.passos)

    @property
    def tokens(self) -> int:
        return self.tokens_entrada + self.tokens_saida

    def confirmar(self, pendencia: dict) -> bool | None:
        """Pede confirmação humana. Com confirmador, a resposta vem na hora (True ou False).
        Sem confirmador devolve None: ninguém respondeu ainda, e a ação NÃO é executada (seguro
        por padrão). A ferramenta grava a pendência, com prazo, e a execução pausa."""
        if self._confirmador is None:
            return None
        ok, quem = self._confirmador(pendencia)
        self.confirmacoes.append({"pendencia": pendencia, "aprovado": ok, "por": quem})
        return ok

    def checkpoint(self, **extra) -> dict:
        """Tudo o que a retomada precisa para continuar a execução pausada em outro processo:
        o que vai para o log mais o que só vive na memória (chamado lido, buscas, mensagens)."""
        return {**self.para_dict(), "ticket": self.ticket, "n_buscas": self.n_buscas,
                "historico": self.historico, "prazo_confirmacao_min": self.prazo_confirmacao_min,
                "pendencia_id": self.pendencia_id, **extra}

    @classmethod
    def de_checkpoint(cls, d: dict) -> "Estado":
        e = cls(**{c: d[c] for c in (
            "id_ticket", "modelo", "execucao_id", "executado_em", "commit", "entrada", "prompt",
            "temperatura", "n_chamadas_modelo", "lembretes", "tokens_entrada", "tokens_saida",
            "custo_usd", "resposta", "ticket", "scores_kb", "n_buscas", "confirmacoes",
            "prazo_confirmacao_min", "pendencia_id", "historico")})
        e.passos = [Passo(**p) for p in d["passos"]]
        return e

    def para_dict(self) -> dict:
        return {
            "execucao_id": self.execucao_id, "id_ticket": self.id_ticket,
            "executado_em": self.executado_em, "commit": self.commit, "entrada": self.entrada,
            "modelo": self.modelo, "prompt": self.prompt, "prompt_lembrete": LEMBRETE_ARQUIVO.name,
            "temperatura": self.temperatura, "termino": self.termino.value if self.termino else None,
            "motivo": self.motivo, "resposta": self.resposta, "desfecho": self.desfecho,
            "pendencia": self.pendencia, "confirmacoes": self.confirmacoes,
            "n_chamadas_modelo": self.n_chamadas_modelo, "lembretes": self.lembretes,
            "tokens_entrada": self.tokens_entrada, "tokens_saida": self.tokens_saida,
            "custo_usd": round(self.custo_usd, 6), "scores_kb": self.scores_kb,
            "saida": self.saida.model_dump() if self.saida else None,
            "passos": [vars(p) for p in self.passos],
        }

    def resumo(self) -> str:
        d = self.desfecho["acao"] if self.desfecho else "nenhum"
        return (f"TERMINO: {self.termino.value} | desfecho: {d} | passos: {self.n_passos} | "
                f"chamadas ao modelo: {self.n_chamadas_modelo} | lembretes: {self.lembretes} | "
                f"tokens: {self.tokens} | "
                f"custo: US$ {self.custo_usd:.5f}")


MAX_LEMBRETES = 2
LEMBRETE = _ler_prompt(LEMBRETE_ARQUIVO)


@dataclass
class Orcamento:
    """Quatro tetos. Devolve QUAL estourou: morrer por tempo e morrer por
    tokens pedem correções opostas."""
    max_passos: int = 8
    max_tokens: int = 30_000
    max_usd: float = 0.05
    max_segundos: float = 90.0
    inicio: float = field(default_factory=time.monotonic)

    def excedido(self, e: Estado) -> str | None:
        if e.n_passos >= self.max_passos:
            return f"passos: {e.n_passos}/{self.max_passos}"
        if e.tokens >= self.max_tokens:
            return f"tokens: {e.tokens}/{self.max_tokens}"
        if e.custo_usd >= self.max_usd:
            return f"custo: US$ {e.custo_usd:.4f}/{self.max_usd}"
        if time.monotonic() - self.inicio >= self.max_segundos:
            return f"tempo: {time.monotonic() - self.inicio:.0f}s/{self.max_segundos:.0f}s"
        return None


# ================================================================ PROMPT

def carregar_prompt(arquivo: Path = PROMPT_ARQUIVO) -> str:
    """Lê o prompt de sistema (padrão: PROMPT_ARQUIVO), descarta o bloco <!-- --> de documentação e
    injeta o limiar do portão (uma fonte só: o código)."""
    return _ler_prompt(arquivo).replace("{LIMIAR}", str(LIMIAR_CONFIANCA))


def criar_cliente(base_url: str | None = None, api_key: str | None = None) -> OpenAI:
    """Pilha do enunciado: biblioteca openai + base_url do provedor escolhido."""
    return OpenAI(base_url=base_url or os.environ["LLM_BASE_URL"],
                  api_key=api_key or os.environ["OPENAI_API_KEY"])


# ================================================================ CHAMADA AO MODELO

def _chamar(client, estado: Estado, temperatura: float | None):
    """Uma chamada ao modelo, com retentativa SÓ para falha de transporte
    (429 e conexão, com espera crescente). Falha de conteúdo nunca é repetida às cegas."""
    args = dict(model=estado.modelo, messages=estado.historico, tools=SCHEMAS,
                tool_choice="auto")
    if temperatura is not None:      # alguns modelos (raciocínio) não aceitam o parâmetro
        args["temperature"] = temperatura
    espera = 2                       # 2s, 4s, 8s, 16s: paciente o bastante para o plano gratuito
    for tentativa in range(5):       # (limite de ~1 requisição por segundo)
        try:
            return client.chat.completions.create(**args)
        except (RateLimitError, APIConnectionError) as e:
            if tentativa == 4:
                raise ErroFatal(f"API indisponível após 5 tentativas (limite do plano "
                                f"gratuito? espere 1 minuto e rode de novo): {e}")
            time.sleep(espera)
            espera *= 2
        except APIStatusError as e:
            dica = " (confira OPENAI_API_KEY/LLM_MODELO no .env)" if e.status_code in (401, 404) else ""
            raise ErroFatal(f"API recusou a chamada, status {e.status_code}{dica}")


# ================================================================ O LAÇO

def _entrada(con, id_ticket: str, texto: str | None = None) -> tuple[str, str | None]:
    """A entrada do agente é o TEXTO do chamado, acompanhado do id do chamado e do id do cliente.

    Com `texto`, vale o que foi recebido (digitado em main.py): ele é gravado no chamado antes
    da execução, para a busca e o registro usarem o mesmo texto. Sem `texto` (a demonstração
    --todos e os testes), o programa simula o evento de abertura lendo o texto do banco.
    Um id que não existe chega sem id de cliente, e é o consultar_ticket que devolve o erro
    ao modelo. Devolve a mensagem de usuário e o texto de entrada, como chegou."""
    if texto is not None:
        db.registrar_texto(con, id_ticket, texto)
    try:
        ticket = db.buscar_ticket(con, id_ticket)
    except db.RegistroNaoEncontrado:
        mensagem = f"Chamado externo a triar: {id_ticket}"
        return (mensagem + f"\nTexto do cliente:\n{texto}" if texto else mensagem), texto
    return (f"Chamado externo a triar: {id_ticket}\nCliente: {ticket['_cliente_id']}\n"
            f"Texto do cliente:\n{ticket['texto']}"), ticket["texto"]


def rodar(id_ticket: str, *, client, modelo: str, con, temperatura: float | None = 0.0,
          preco_usd_por_mtok: tuple[float, float] = (0.15, 0.15),
          orcamento: Orcamento | None = None, confirmador=None,
          log_dir: Path | None = None, verbose: bool = True,
          prompt_arquivo: Path = PROMPT_ARQUIVO, texto: str | None = None,
          prazo_confirmacao_min: float = PRAZO_CONFIRMACAO_MIN) -> Estado:
    orcamento = orcamento or Orcamento()
    mensagem, entrada = _entrada(con, id_ticket, texto)
    e = Estado(id_ticket=id_ticket, modelo=modelo, _confirmador=confirmador,
               prompt=prompt_arquivo.name, temperatura=temperatura, commit=_commit(),
               entrada=entrada, prazo_confirmacao_min=prazo_confirmacao_min,
               execucao_id=f"{id_ticket}-{int(time.time()) % 100000}")
    e.historico = [
        # ETAPA "agente de triagem" — técnica: zero-shot + procedimento numerado + tool calling
        # (detalhes e o que cada regra impede: cabeçalho do arquivo em src/prompts/).
        # Contrato de saída: o resultado é a escrita de UMA ferramenta; o texto é só um resumo.
        # temperature=0: classificação e escolha de ferramenta pedem o mesmo resultado a cada
        # execução (nota 03 da aula 02).
        {"role": "system", "content": carregar_prompt(prompt_arquivo)},
        {"role": "user", "content": mensagem},
    ]
    return _laco(e, client=client, con=con, temperatura=temperatura,
                 preco_usd_por_mtok=preco_usd_por_mtok, orcamento=orcamento,
                 log_dir=log_dir, verbose=verbose)


def _laco(e: Estado, *, client, con, temperatura: float | None,
          preco_usd_por_mtok: tuple[float, float], orcamento: Orcamento,
          log_dir: Path | None, verbose: bool) -> Estado:
    """O laço de ferramentas. Serve à execução nova (rodar) e à que volta de uma pausa (retomar)."""
    try:
        while True:
            motivo = orcamento.excedido(e)
            if motivo:
                e.termino, e.motivo = Termino.ORCAMENTO, motivo
                break

            resp = _chamar(client, e, temperatura)
            e.n_chamadas_modelo += 1
            if resp.usage:
                e.tokens_entrada += resp.usage.prompt_tokens
                e.tokens_saida += resp.usage.completion_tokens
                e.custo_usd = (e.tokens_entrada * preco_usd_por_mtok[0]
                               + e.tokens_saida * preco_usd_por_mtok[1]) / 1_000_000
            msg = resp.choices[0].message

            if not msg.tool_calls:                      # o modelo quer encerrar
                e.resposta = (msg.content or "").strip()
                if e.desfecho is None and e.lembretes < MAX_LEMBRETES:
                    # Guarda contra "narrar a ação em vez de executá-la" (visto nas rodadas 1 e 2):
                    # o laço devolve UM lembrete como observação e deixa o modelo tentar de novo.
                    e.lembretes += 1
                    e.historico.append({"role": "assistant", "content": msg.content or ""})
                    e.historico.append({"role": "user", "content": LEMBRETE})
                    if verbose:
                        print(f"  (lembrete {e.lembretes}/{MAX_LEMBRETES}: o modelo encerrou sem registrar desfecho)")
                    continue
                if e.desfecho is None:
                    e.termino = Termino.ERRO_FATAL
                    e.motivo = "modelo encerrou sem registrar nenhum desfecho"
                else:
                    e.termino = Termino.RESPONDEU
                break

            e.historico.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name,
                                             "arguments": c.function.arguments}}
                               for c in msg.tool_calls]})
            for chamada in msg.tool_calls:
                observacao = _executar(e, con, chamada, verbose)
                e.historico.append({"role": "tool", "tool_call_id": chamada.id,
                                    "name": chamada.function.name,
                                    "content": json.dumps(observacao, ensure_ascii=False)})
    except PausaParaHumano as p:
        # Ninguém respondeu ainda: a execução fica guardada para continuar depois (retomar).
        # O tempo já gasto vai junto, e a espera pelo analista não entra no teto de tempo.
        e.termino, e.pendencia = Termino.HUMANO, p.pendencia
        e.motivo = (f"aguardando a confirmação do analista até {p.pendencia['vence_em']} "
                    f"(prazo de {e.prazo_confirmacao_min:g} minutos)")
        db.gravar_checkpoint(con, e.pendencia_id, e.checkpoint(
            preco_usd_por_mtok=list(preco_usd_por_mtok),
            segundos=time.monotonic() - orcamento.inicio))
    except ErroFatal as f:
        e.termino, e.motivo = Termino.ERRO_FATAL, str(f)
    finally:
        if e.termino is None:                            # nunca terminar sem dizer por quê
            e.termino, e.motivo = Termino.ERRO_FATAL, "interrupção inesperada"
        _finalizar(e, log_dir)
    return e


def _finalizar(e: Estado, log_dir: Path | None) -> None:
    try:                                                 # toda saída passa pelo schema
        e.saida = montar_saida(e)
    except ValidationError as v:
        e.termino = Termino.ERRO_FATAL
        e.motivo = f"saída fora do contrato: {v.errors()[0]['msg']}"
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        arquivo = log_dir / f"{e.id_ticket}.json"
        arquivo.write_text(json.dumps(e.para_dict(), ensure_ascii=False, indent=2),
                           encoding="utf-8")


# ================================================================ A RETOMADA

class EdicaoRecusada(Exception):
    """A aprovação com edição não foi aceita (texto inválido, ou caminho que não a oferece). Nada
    foi gravado e a ação continua à espera do analista."""


def retomar(id_ticket: str, decisao: str, *, client, con, por: str = "analista de suporte",
            agora: datetime | None = None, orcamento: Orcamento | None = None,
            log_dir: Path | None = None, verbose: bool = True,
            resumo: str | None = None, motivo_rejeicao: str | None = None) -> Estado | None:
    """Conclui a ação irreversível que ficou à espera do analista e continua a execução pausada.

    `decisao` é "aprovar", "rejeitar" ou "vencer" (só aplica o prazo, sem resposta de ninguém).
    Quem decide o que acontece é o relógio antes da pessoa: passado o `vence_em`, qualquer decisão
    vira prazo vencido. Dentro do prazo, aprovar executa a escrita. Rejeitar e prazo vencido têm
    o mesmo destino: a ação não é executada e o código encaminha o chamado à fila humana com as
    considerações do agente (no prazo vencido de um chamado que seria P1, avisa também o gestor).
    Depois da escrita o laço continua, para o modelo dar a frase final.

    Devolve None quando não há o que fazer: nenhuma pendência aguardando, "vencer" antes do
    prazo, ou pendência que outra chamada já resolveu (a segunda aprovação não repete nada).

    `resumo` é a aprovação COM EDIÇÃO: o analista corrige o resumo do chamado interno antes de
    deixar seguir. Só o grafo a oferece; no laço ela é recusada (EdicaoRecusada)."""
    if decisao not in ("aprovar", "rejeitar", "vencer"):
        raise ValueError(f"decisão inválida: {decisao}")
    registros = db.pendencias_aguardando(con, id_ticket)
    if not registros:
        return None
    registro = registros[-1]
    if (registro["checkpoint"] or {}).get("motor") == "grafo":
        # A pausa é de uma execução do grafo (src/grafo.py): quem continua é ele, pelo checkpoint
        # do LangGraph. O log volta para a pasta em que a execução pausada gravou.
        from grafo import retomar_grafo
        pasta = registro["checkpoint"].get("log_dir")
        return retomar_grafo(id_ticket, decisao, client=client, con=con, por=por, agora=agora,
                             log_dir=Path(pasta) if pasta else log_dir, verbose=verbose,
                             resumo=resumo, motivo_rejeicao=motivo_rejeicao)
    if motivo_rejeicao is not None:
        raise EdicaoRecusada("o motivo da rejeição é registrado só no grafo; esta ação foi pausada "
                             "pelo laço (--laco). Rejeite sem --motivo.")
    if resumo is not None:
        raise EdicaoRecusada("a aprovação com edição existe só no grafo; esta ação foi pausada "
                             "pelo laço (--laco). Aprove sem --resumo, ou rejeite.")
    agora = agora or datetime.now().astimezone()
    vencida = agora >= datetime.fromisoformat(registro["vence_em"])
    if decisao == "vencer" and not vencida:
        return None
    status = "vencida" if vencida else {"aprovar": "aprovada", "rejeitar": "rejeitada"}[decisao]
    if vencida:
        por = "ninguém: prazo vencido"
    quando = agora.isoformat(timespec="seconds")
    if not db.resolver_pendencia(con, registro["id"], status, quando, por):
        return None

    ck, acao = registro["checkpoint"], registro["acao"]
    e = Estado.de_checkpoint(ck)
    e.confirmacoes.append({"pendencia": acao, "aprovado": status == "aprovada", "por": por,
                           "status": status, "resolvido_em": quando})
    pausado = e.passos[-1]                               # o abrir_chamado_interno que pausou
    if status == "aprovada":
        pausado.erro, pausado.resultado = None, aprovar_pendencia(e, con, acao)
        observacao = pausado.resultado
    elif status == "rejeitada":
        pausado.erro = {"erro": "o analista rejeitou a ação"}
        observacao = _encaminhar_nao_executada(e, con, acao, MOTIVO_REJEITADA)
    else:
        pausado.erro = {"erro": f"confirmação do analista não recebida em "
                                f"{e.prazo_confirmacao_min:g} minutos"}
        observacao = _encaminhar_nao_executada(e, con, acao, MOTIVO_PRAZO_VENCIDO)
    if verbose:
        print(f"  retomada [{status}] {pausado.ferramenta} -> {e.desfecho['acao']}")

    # A observação que faltava volta ao modelo. Se ele pediu outras ferramentas na mesma
    # resposta, elas não rodaram: cada uma recebe um erro, porque a API exige uma resposta por id.
    pedidas = next(m for m in reversed(e.historico) if m.get("tool_calls"))["tool_calls"]
    respondidas = {m["tool_call_id"] for m in e.historico if m["role"] == "tool"}
    faltam = [c for c in pedidas if c["id"] not in respondidas]
    for i, chamada in enumerate(faltam):
        conteudo = observacao if i == 0 else {
            "erro": "chamada não executada: a execução pausou para a confirmação do analista",
            "sugestao": "se ainda for necessária, chame de novo"}
        e.historico.append({"role": "tool", "tool_call_id": chamada["id"],
                            "name": chamada["function"]["name"],
                            "content": json.dumps(conteudo, ensure_ascii=False)})

    orcamento = orcamento or Orcamento()
    orcamento.inicio = time.monotonic() - ck["segundos"]      # a espera não conta no teto de tempo
    return _laco(e, client=client, con=con, temperatura=e.temperatura,
                 preco_usd_por_mtok=tuple(ck["preco_usd_por_mtok"]), orcamento=orcamento,
                 log_dir=log_dir, verbose=verbose)


def _encaminhar_nao_executada(e: Estado, con, acao: dict, motivo: str) -> dict:
    """A ação irreversível não foi autorizada (rejeição ou prazo vencido): o código grava o
    encaminhamento à fila humana, registra o passo na trajetória e devolve o que o modelo vai ler."""
    argumentos, resultado = encaminhar_pendencia(e, con, acao, motivo)
    e.passos.append(Passo(indice=e.n_passos, ferramenta="registrar_encaminhamento",
                          argumentos=argumentos, resultado=resultado))
    causa = ("o analista rejeitou a ação" if motivo == MOTIVO_REJEITADA else
             f"o analista não confirmou em {e.prazo_confirmacao_min:g} minutos")
    aviso = (f"{causa}: o chamado interno NÃO foi aberto, e o sistema encaminhou o chamado à "
             f"fila humana com a ação proposta")
    if "aviso_gestor" in resultado:
        aviso += "; como o chamado seria P1, o gestor de suporte foi avisado"
    return {**resultado, "aviso": aviso,
            "sugestao": "não registre outro desfecho; responda com UMA frase dizendo isso"}


def vencer_pendencias(*, client, con, agora: datetime | None = None,
                      log_dir: Path | None = None, verbose: bool = True) -> list[Estado]:
    """Aplica o prazo a todas as pendências que venceram sem resposta. Não há processo em segundo
    plano: quem chama é o ponto de entrada, antes de qualquer outro comando."""
    vencidos = []
    for id_ticket in dict.fromkeys(p["ticket_externo"] for p in db.pendencias_aguardando(con)):
        e = retomar(id_ticket, "vencer", client=client, con=con, agora=agora,
                    log_dir=log_dir, verbose=verbose)
        if e is not None:
            vencidos.append(e)
    return vencidos


def _executar(e: Estado, con, chamada, verbose: bool) -> dict:
    """Executa UMA chamada de ferramenta e devolve o que o modelo vai ler.
    Erro recuperável volta como dado (com 'esperado' e 'sugestao')."""
    nome = chamada.function.name
    passo = Passo(indice=e.n_passos, ferramenta=nome, argumentos={})
    rejeitada = None
    t0 = time.monotonic()
    try:
        try:
            passo.argumentos = json.loads(chamada.function.arguments or "{}")
        except json.JSONDecodeError:
            raise ErroRecuperavel("argumentos não são JSON válido",
                                  recebido=chamada.function.arguments)
        if not isinstance(passo.argumentos, dict):
            raise ErroRecuperavel("argumentos devem ser um objeto JSON",
                                  recebido=chamada.function.arguments)
        if nome not in FUNCOES:
            raise ErroRecuperavel("ferramenta inexistente", recebido=nome,
                                  esperado=sorted(FUNCOES))
        try:                                             # argumento faltando ou a mais
            inspect.signature(FUNCOES[nome]).bind(e, con, **passo.argumentos)
        except TypeError as t:
            raise ErroRecuperavel("argumentos incompatíveis com o schema", detalhe=str(t))
        passo.resultado = FUNCOES[nome](e, con, **passo.argumentos)
        observacao = passo.resultado
    except ErroRecuperavel as r:
        passo.erro = r.payload
        observacao = r.payload
    except AcaoRejeitada as r:                           # o analista respondeu na hora, e negou
        passo.erro = {"erro": str(r)}
        rejeitada = r.pendencia
    except (PausaParaHumano, ErroFatal) as x:            # registra o passo e propaga
        passo.erro = {"erro": str(x)}
        raise
    finally:
        passo.ms = int((time.monotonic() - t0) * 1000)
        e.passos.append(passo)
        if verbose:
            marca = "ESCRITA " if nome in FERRAMENTAS_DE_ESCRITA else "leitura "
            status = f"ERRO: {passo.erro['erro']}" if passo.erro else "ok"
            print(f"  passo {passo.indice} [{marca}] {nome} {json.dumps(passo.argumentos, ensure_ascii=False)[:110]} -> {status}")
    if rejeitada:                                        # rejeição não derruba o laço: fila humana
        observacao = _encaminhar_nao_executada(e, con, rejeitada, MOTIVO_REJEITADA)
        if verbose:
            print(f"  passo {e.passos[-1].indice} [ESCRITA ] registrar_encaminhamento "
                  f"(código: ação rejeitada) -> ok")
    return observacao

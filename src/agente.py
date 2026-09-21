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
            confirmação humana, impõe o orçamento e registra por que parou.
"""
import inspect
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

import db
from ferramentas import (FERRAMENTAS_DE_ESCRITA, FUNCOES, LIMIAR_CONFIANCA,
                         SCHEMAS, ErroFatal, ErroRecuperavel, PausaParaHumano)

RAIZ = Path(__file__).resolve().parent.parent
PROMPT_ARQUIVO = RAIZ / "prompts" / "agente-v3.md"


# ================================================================ TÉRMINO

class Termino(str, Enum):
    RESPONDEU = "respondeu"            # o modelo concluiu E registrou um desfecho
    ORCAMENTO = "orcamento_esgotado"   # bateu um dos tetos
    ERRO_FATAL = "erro_fatal"          # não há como continuar
    HUMANO = "aguardando_humano"       # ação irreversível não confirmada


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
    confirmacoes: list = field(default_factory=list)
    historico: list = field(default_factory=list)          # transporte p/ API (derivado)
    _confirmador: object = field(default=None, repr=False)

    @property
    def n_passos(self) -> int:
        return len(self.passos)

    @property
    def tokens(self) -> int:
        return self.tokens_entrada + self.tokens_saida

    def confirmar(self, pendencia: dict) -> bool:
        """Pede confirmação humana. Sem confirmador configurado, NEGA (seguro por padrão)."""
        if self._confirmador is None:
            ok, quem = False, "nenhum confirmador configurado"
        else:
            ok, quem = self._confirmador(pendencia)
        self.confirmacoes.append({"pendencia": pendencia, "aprovado": ok, "por": quem})
        return ok

    def para_dict(self) -> dict:
        return {
            "execucao_id": self.execucao_id, "id_ticket": self.id_ticket,
            "modelo": self.modelo, "prompt": PROMPT_ARQUIVO.name, "termino": self.termino.value if self.termino else None,
            "motivo": self.motivo, "resposta": self.resposta, "desfecho": self.desfecho,
            "pendencia": self.pendencia, "confirmacoes": self.confirmacoes,
            "n_chamadas_modelo": self.n_chamadas_modelo, "lembretes": self.lembretes,
            "tokens_entrada": self.tokens_entrada, "tokens_saida": self.tokens_saida,
            "custo_usd": round(self.custo_usd, 6), "scores_kb": self.scores_kb,
            "passos": [vars(p) for p in self.passos],
        }

    def resumo(self) -> str:
        d = self.desfecho["acao"] if self.desfecho else "nenhum"
        return (f"TERMINO: {self.termino.value} | desfecho: {d} | passos: {self.n_passos} | "
                f"chamadas ao modelo: {self.n_chamadas_modelo} | lembretes: {self.lembretes} | "
                f"tokens: {self.tokens} | "
                f"custo: US$ {self.custo_usd:.5f}")


MAX_LEMBRETES = 2
LEMBRETE = ("Você ainda NÃO registrou nenhum desfecho: escrever no texto que registrou ou "
            "encaminhou não registra nada. Chame agora a ferramenta de escrita correta "
            "(abrir_chamado_interno ou registrar_encaminhamento), seguindo o procedimento.")


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

def carregar_prompt() -> str:
    """Lê o arquivo PROMPT_ARQUIVO (prompts/agente-v3.md), descarta o bloco <!-- --> de documentação e
    injeta o limiar do portão (uma fonte só: o código)."""
    texto = PROMPT_ARQUIVO.read_text(encoding="utf-8")
    if texto.lstrip().startswith("<!--"):
        texto = texto.split("-->", 1)[1]
    return texto.strip().replace("{LIMIAR}", str(LIMIAR_CONFIANCA))


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

def rodar(id_ticket: str, *, client, modelo: str, con, temperatura: float | None = 0.0,
          preco_usd_por_mtok: tuple[float, float] = (0.15, 0.60),
          orcamento: Orcamento | None = None, confirmador=None,
          log_dir: Path | None = None, verbose: bool = True) -> Estado:
    orcamento = orcamento or Orcamento()
    e = Estado(id_ticket=id_ticket, modelo=modelo, _confirmador=confirmador,
               execucao_id=f"{id_ticket}-{int(time.time()) % 100000}")
    e.historico = [
        # ETAPA "agente de triagem" — técnica: zero-shot + procedimento numerado + tool calling
        # (detalhes e o que cada regra impede: prompts/agente-v1.md).
        # Contrato de saída: o resultado é a escrita de UMA ferramenta; o texto é só um resumo.
        # temperature=0: classificação e escolha de ferramenta pedem o mesmo resultado a cada
        # execução (nota 03 da aula 02).
        {"role": "system", "content": carregar_prompt()},
        {"role": "user", "content": f"Chamado externo a triar: {id_ticket}"},
    ]
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
        e.termino, e.motivo, e.pendencia = Termino.HUMANO, "analista não confirmou a ação", p.pendencia
    except ErroFatal as f:
        e.termino, e.motivo = Termino.ERRO_FATAL, str(f)
    finally:
        if e.termino is None:                            # nunca terminar sem dizer por quê
            e.termino, e.motivo = Termino.ERRO_FATAL, "interrupção inesperada"
        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            arquivo = log_dir / f"{id_ticket}.json"
            arquivo.write_text(json.dumps(e.para_dict(), ensure_ascii=False, indent=2),
                               encoding="utf-8")
    return e


def _executar(e: Estado, con, chamada, verbose: bool) -> dict:
    """Executa UMA chamada de ferramenta e devolve o que o modelo vai ler.
    Erro recuperável volta como dado (com 'esperado' e 'sugestao')."""
    nome = chamada.function.name
    passo = Passo(indice=e.n_passos, ferramenta=nome, argumentos={})
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
    return observacao

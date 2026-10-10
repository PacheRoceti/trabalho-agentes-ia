"""Contrato de saída (item 1.2 da Parte 2): o objeto VALIDADO que o sistema devolve.

Três campos obrigatórios do enunciado, no nosso domínio:

    resultado     o desfecho gravado para o chamado e o texto registrado (mensagem ou resumo)
    fonte         o que sustenta o desfecho e pode ser conferido: o procedimento da base
                  (kb_id e score), os registros consultados e as ferramentas que responderam
    suficiencia   se o sistema teve base para agir sozinho, e por quê

A recusa faz parte do contrato: `fila_humana`, `devolver_cliente` e a execução que termina sem
desfecho são saídas válidas, com suficiência negativa e o motivo escrito.

Nenhum campo vem do texto livre do modelo: o objeto é montado pelo CÓDIGO a partir do `Estado`
(o que as ferramentas gravaram e devolveram), e os validadores recusam combinações incoerentes
(por exemplo, suficiência positiva sem procedimento acima do limiar).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ferramentas import FERRAMENTAS_DE_ESCRITA, LIMIAR_CONFIANCA, MOTIVO_PRAZO_VENCIDO

Acao = Literal["abrir_chamado_interno", "anotacao_interna", "fila_comercial",
               "devolver_cliente", "fila_humana"]
ACOES_COM_PROCEDIMENTO = ("abrir_chamado_interno", "anotacao_interna")
ACOES_DE_RECUSA = ("fila_humana", "devolver_cliente")


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Resultado(_Modelo):
    acao: Acao | None = Field(description="desfecho gravado; None quando a execução terminou sem desfecho")
    texto: str | None = Field(description="o que foi registrado: resumo do chamado interno ou mensagem do encaminhamento")
    chamado_interno: str | None = Field(default=None, description="INC-0000, só para abrir_chamado_interno")
    time_destino: str | None = None
    prioridade: Literal["P1", "P2", "P3"] | None = None

    @model_validator(mode="after")
    def _coerente(self):
        if self.acao is not None and not (self.texto or "").strip():
            raise ValueError("desfecho gravado sem o texto registrado")
        if self.acao == "abrir_chamado_interno" and not (
                self.chamado_interno and self.time_destino and self.prioridade):
            raise ValueError("chamado interno sem id, time ou prioridade")
        return self


class Fonte(_Modelo):
    tipo: Literal["procedimento_da_base", "registro_do_chamado",
                  "busca_sem_correspondencia", "nenhuma"]
    kb_id: str | None = Field(default=None, description="procedimento que sustenta o desfecho ou, na recusa, o melhor candidato da busca")
    score: float | None = Field(default=None, ge=0, le=1)
    registros: list[str] = Field(default_factory=list, description="registros consultados: o chamado externo e os chamados internos do histórico")
    ferramentas: list[str] = Field(default_factory=list, description="ferramentas chamadas nesta execução, na ordem")


class Suficiencia(_Modelo):
    suficiente: bool = Field(description="True quando o sistema teve base para agir sozinho")
    motivo: str = Field(min_length=10)


class Saida(_Modelo):
    id_ticket: str
    executado_em: str = Field(description="data e hora do início da execução, ISO 8601 com fuso")
    termino: str
    resultado: Resultado
    fonte: Fonte
    suficiencia: Suficiencia

    @model_validator(mode="after")
    def _coerente(self):
        acao, fonte = self.resultado.acao, self.fonte
        if acao is None or acao in ACOES_DE_RECUSA:
            if self.suficiencia.suficiente:
                raise ValueError(f"suficiência positiva com desfecho '{acao}'")
        elif not self.suficiencia.suficiente:
            raise ValueError(f"suficiência negativa com desfecho '{acao}'")
        if acao in ACOES_COM_PROCEDIMENTO and not (
                fonte.tipo == "procedimento_da_base" and fonte.kb_id
                and fonte.score is not None and fonte.score >= LIMIAR_CONFIANCA):
            raise ValueError(f"'{acao}' sem procedimento da base com score >= {LIMIAR_CONFIANCA}")
        return self


def montar_saida(estado) -> Saida:
    """Monta e VALIDA a saída a partir do Estado. Levanta pydantic.ValidationError se o que a
    execução produziu não cabe no contrato."""
    desfecho = estado.desfecho or {}
    acao = desfecho.get("acao")
    escrita = next((p for p in reversed(estado.passos)
                    if p.ferramenta in FERRAMENTAS_DE_ESCRITA and p.erro is None), None)
    texto = None
    if acao and escrita:
        texto = escrita.argumentos.get("resumo") or escrita.argumentos.get("mensagem")

    melhor = max(estado.scores_kb.items(), key=lambda kv: kv[1], default=(None, None))
    registros = []
    if estado.ticket:
        registros = [estado.ticket["id"]] + [h["chamado_interno"] for h in estado.ticket["historico_cliente"]]

    if acao in ACOES_COM_PROCEDIMENTO:
        kb_id = desfecho.get("kb_id")
        fonte = Fonte(tipo="procedimento_da_base", kb_id=kb_id, score=estado.scores_kb.get(kb_id))
    elif acao == "fila_humana" and estado.n_buscas and (melhor[1] is None or melhor[1] < LIMIAR_CONFIANCA):
        fonte = Fonte(tipo="busca_sem_correspondencia", kb_id=melhor[0], score=melhor[1])
    elif estado.ticket:
        fonte = Fonte(tipo="registro_do_chamado", kb_id=melhor[0], score=melhor[1])
    else:
        fonte = Fonte(tipo="nenhuma")
    fonte.registros = registros
    fonte.ferramentas = [p.ferramenta for p in estado.passos]

    suficiente, motivo = _suficiencia(estado, acao, desfecho, melhor)
    return Saida(
        id_ticket=estado.id_ticket, executado_em=estado.executado_em,
        termino=estado.termino.value,
        resultado=Resultado(acao=acao, texto=texto,
                            chamado_interno=desfecho.get("chamado_interno"),
                            time_destino=desfecho.get("time_destino"),
                            prioridade=desfecho.get("prioridade")),
        fonte=fonte, suficiencia=Suficiencia(suficiente=suficiente, motivo=motivo))


def _suficiencia(estado, acao, desfecho, melhor) -> tuple[bool, str]:
    kb_id, score = melhor
    if acao is None:
        return False, f"a execução terminou sem desfecho ({estado.termino.value}: {estado.motivo})"
    if acao in ACOES_COM_PROCEDIMENTO:
        usado = desfecho.get("kb_id")
        return True, (f"procedimento {usado} com score {estado.scores_kb.get(usado)}, "
                      f"igual ou acima do limiar {LIMIAR_CONFIANCA}")
    if acao == "fila_comercial":
        return True, "assunto comercial: a classificação dispensa a base de procedimentos"
    if acao == "devolver_cliente":
        return False, ("o texto do chamado não informa o serviço afetado nem o sintoma; "
                       "o pedido de informação ao cliente foi registrado")
    if desfecho.get("motivo") == "fora_da_alcada":
        return False, "pedido fora da alçada do agente (encerrar chamado ou mudar prioridade)"
    if desfecho.get("motivo") == MOTIVO_PRAZO_VENCIDO:
        return False, (f"a confirmação do analista não chegou em {estado.prazo_confirmacao_min:g} "
                       f"minutos: a ação proposta não foi executada")
    if estado.ticket is None:
        return False, "o chamado não foi encontrado no sistema de tickets"
    if score is None:
        return False, "nenhum procedimento da base corresponde ao relato"
    if score < LIMIAR_CONFIANCA:
        return False, (f"o melhor procedimento encontrado ({kb_id}, score {score}) ficou abaixo "
                       f"do limiar {LIMIAR_CONFIANCA}")
    return False, (f"havia procedimento com score igual ou acima do limiar ({kb_id}, {score}), mas o "
                   f"agente não agiu sozinho; o motivo está no texto registrado no resultado")

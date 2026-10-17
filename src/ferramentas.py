"""As quatro ferramentas do agente.

    ferramenta                  leitura/escrita   reversível?   conversa com
    --------------------------  ----------------  ------------  --------------------
    consultar_ticket            leitura           -             SQLite (tickets)
    buscar_base_conhecimento    leitura           -             SQLite (kb_artigos)
    abrir_chamado_interno       ESCRITA           NÃO           SQLite (chamados)
    registrar_encaminhamento    ESCRITA           sim           SQLite (encaminhamentos)

Não existe ferramenta para encerrar chamado, alterar prioridade ou executar
correção: a regra de domínio "o agente nunca executa, nunca fecha e nunca
reclassifica" é garantida pela AUSÊNCIA da ferramenta, não por pedido no prompt.

Regra de erro: o que o modelo pode contornar vira ErroRecuperavel (volta como
dado, com "esperado" e "sugestao"); o que nenhuma decisão dele resolve vira
ErroFatal e derruba o laço.
"""
import re
import unicodedata
from datetime import datetime, timedelta

import db

LIMIAR_CONFIANCA = 0.5   # abaixo disso, o agente NÃO age sozinho (vai à fila humana)

# Prazo do analista para confirmar ou rejeitar uma ação irreversível, contado do pedido de
# confirmação (docs/case.md §2.1). Vencido, a ação NÃO é executada: o chamado vai para a fila
# humana com as considerações do agente. O silêncio nunca vira aprovação.
PRAZO_CONFIRMACAO_MIN = 20
MOTIVO_PRAZO_VENCIDO = "confirmacao_nao_recebida"
# Rejeição do analista: a ação também NÃO é executada, e o chamado segue o mesmo caminho do prazo
# vencido (fila humana, com as considerações do agente). Uma rejeição não deixa o chamado parado.
MOTIVO_REJEITADA = "acao_rejeitada"
# Prazo vencido numa ação que abriria um chamado com esta prioridade também avisa o gestor: a fila
# humana é lida pelo mesmo analista que não respondeu.
PRIORIDADE_QUE_AVISA_GESTOR = "P1"

DESTINOS = ["fila_comercial", "devolver_cliente", "anotacao_interna", "fila_humana"]

# Motivos que dispensam a busca na base antes da fila humana: o pedido não é um problema técnico.
MOTIVOS_SEM_BUSCA = ["fora_da_alcada"]

# O pedido de informação é a única mensagem que chega ao cliente: não pode citar informação
# interna (procedimentos, times, filas, scores) nem falar de prioridade ou SLA. Checagem por
# palavras, sobre o texto em minúsculas e sem acento; os nomes dos times vêm da base.
TERMOS_INTERNOS = re.compile(
    r"\bkb-?\d+|\binc-?\d+|\bscores?\b|\blimiar\b|\bbase de conhecimento\b|\bprocedimentos?\b"
    r"|\bfila[ _](humana|comercial)\b|\bchamados? internos?\b|\bprioridade\b|\bsla\b|\bp[123]\b")


class ErroRecuperavel(Exception):
    """O modelo pode contornar mudando a chamada. Volta como observação."""

    def __init__(self, mensagem, **contexto):
        super().__init__(mensagem)
        self.payload = {"erro": mensagem, **contexto}


class ErroFatal(Exception):
    """Nenhuma decisão do modelo resolve. Aborta o laço."""


class PausaParaHumano(Exception):
    """Ação irreversível à espera do analista: o agente para e devolve o controle. A pendência
    leva `pedido_em` e `vence_em` e fica gravada no banco."""

    def __init__(self, pendencia: dict):
        super().__init__("ação irreversível aguardando confirmação humana")
        self.pendencia = pendencia


class AcaoRejeitada(Exception):
    """O analista respondeu na hora, e rejeitou. Não derruba o laço: quem executa a ferramenta
    (agente._executar) encaminha o chamado à fila humana e devolve isso ao modelo."""

    def __init__(self, pendencia: dict):
        super().__init__("o analista rejeitou a ação")
        self.pendencia = pendencia


# ---------------------------------------------------------------- funções
# Todas recebem (estado, con, **argumentos do modelo). `estado` carrega o que
# a ferramenta precisa saber do que já aconteceu (scores da busca, desfecho).

def consultar_ticket(estado, con, id_ticket: str) -> dict:
    if not db.ID_TICKET.match(id_ticket or ""):
        raise ErroRecuperavel(
            "id de chamado em formato inválido", recebido=id_ticket,
            esperado="TKT- seguido de 4 dígitos, ex: TKT-0042",
            sugestao="corrija o formato e chame consultar_ticket de novo")
    try:
        ticket = db.buscar_ticket(con, id_ticket)
    except db.RegistroNaoEncontrado:
        raise ErroRecuperavel(
            "chamado não encontrado no sistema de tickets", recebido=id_ticket,
            esperado="um id que exista no sistema",
            sugestao="não tente outros ids. Chame registrar_encaminhamento com "
                     "destino 'fila_humana' e explique na mensagem que o id não existe")
    estado.ticket = ticket
    # O texto do cliente já chegou como entrada (agente._entrada): não é repetido aqui.
    return {k: v for k, v in ticket.items() if not k.startswith("_") and k != "texto"}


def buscar_base_conhecimento(estado, con, termos: list[str]) -> dict:
    if not isinstance(termos, list) or not termos:
        raise ErroRecuperavel(
            "termos deve ser uma lista não vazia de palavras", recebido=termos,
            esperado='lista com 2 a 5 palavras, ex: ["certificado", "ssl", "vencido"]')
    # O texto do cliente vai junto só para conferir as ressalvas dos procedimentos (nao_cobre).
    relato = estado.ticket["texto"] if estado.ticket else None
    resultados = db.buscar_kb(con, termos, relato=relato)
    estado.n_buscas += 1
    for r in resultados:
        estado.scores_kb[r["kb_id"]] = r["score"]   # o portão de confiança confere depois
    if not resultados:
        return {"resultados": [],
                "aviso": "nenhum procedimento da base tem correspondência com esses termos",
                "sugestao": ("tente UMA nova busca com outras palavras soltas do relato (o serviço "
                             "e o sintoma)" if estado.n_buscas == 1 else
                             "não busque de novo: registre 'fila_humana' explicando o que foi buscado")}
    return {"resultados": resultados, "limiar_para_agir_sozinho": LIMIAR_CONFIANCA}


def _exigir_confianca(estado, con, kb_id: str | None) -> dict:
    """O PORTÃO DE CONFIANÇA é código, não prompt: o modelo pode querer agir,
    mas sem correspondência acima do limiar a escrita é recusada."""
    if not kb_id or kb_id not in estado.scores_kb:
        raise ErroRecuperavel(
            "kb_id não vem de uma busca feita nesta execução", recebido=kb_id,
            sugestao="chame buscar_base_conhecimento, ou use destino 'fila_humana'")
    score = estado.scores_kb[kb_id]
    if score < LIMIAR_CONFIANCA:
        raise ErroRecuperavel(
            "correspondência abaixo do limiar de confiança", kb_id=kb_id,
            score=score, limiar=LIMIAR_CONFIANCA,
            sugestao="não aja sozinho: chame registrar_encaminhamento com "
                     "destino 'fila_humana'")
    return db.buscar_artigo(con, kb_id)


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _exigir_pedido_sem_informacao_interna(con, mensagem: str) -> None:
    texto = _normalizar(mensagem)
    achados = sorted({m.group(0) for m in TERMOS_INTERNOS.finditer(texto)})
    achados += [t for t in db.times_destino(con) if re.search(rf"\b{re.escape(_normalizar(t))}\b", texto)]
    if achados:
        raise ErroRecuperavel(
            "o pedido ao cliente cita informação interna ou promete prioridade", recebido=achados,
            esperado="só a lista do que falta: serviço ou servidor afetado, erro ou "
                     "comportamento observado e desde quando ocorre",
            sugestao="reescreva a mensagem sem esses termos e chame de novo")


def _exigir_sem_desfecho(estado):
    if estado.desfecho is not None:
        raise ErroRecuperavel(
            "este chamado já recebeu um desfecho", desfecho=estado.desfecho,
            sugestao="não registre outro; responda com o resumo final")


def abrir_chamado_interno(estado, con, id_ticket: str, resumo: str, kb_id: str) -> dict:
    _exigir_sem_desfecho(estado)
    if estado.ticket is None or estado.ticket["id"] != id_ticket:
        raise ErroRecuperavel("chame consultar_ticket para este id antes de abrir chamado",
                              recebido=id_ticket)
    if not resumo or len(resumo.strip()) < 20:
        raise ErroRecuperavel("resumo curto demais", esperado="pelo menos 20 caracteres")
    artigo = _exigir_confianca(estado, con, kb_id)
    if artigo["acao_padrao"] != "escalar":
        raise ErroRecuperavel(
            "este procedimento não é de escalonamento", kb_id=kb_id,
            sugestao="use registrar_encaminhamento com destino 'anotacao_interna'")

    # Ação irreversível: quem confirma é o ANALISTA DE SUPORTE (perfil da §2.2).
    pendencia = {"ferramenta": "abrir_chamado_interno", "id_ticket": id_ticket,
                 "categoria": artigo["categoria"], "resumo": resumo,
                 "time_destino": artigo["time_destino"], "kb_id": kb_id}
    resposta = estado.confirmar(pendencia)
    if resposta is None:
        # Ninguém respondeu agora: a espera é assíncrona e tem prazo. A pendência fica no banco
        # e a execução pausa; aprovar_pendencia ou encaminhar_pendencia a concluem depois.
        pedido_em = datetime.now().astimezone()
        vence_em = pedido_em + timedelta(minutes=estado.prazo_confirmacao_min)
        pendencia = {**pendencia, "pedido_em": pedido_em.isoformat(timespec="seconds"),
                     "vence_em": vence_em.isoformat(timespec="seconds")}
        estado.pendencia_id = db.criar_pendencia(con, id_ticket, pendencia,
                                                 pendencia["pedido_em"], pendencia["vence_em"])
        raise PausaParaHumano(pendencia)
    if not resposta:
        raise AcaoRejeitada(pendencia)

    resultado = db.abrir_chamado(con, estado.ticket, resumo.strip(), artigo)
    estado.desfecho = {"acao": "abrir_chamado_interno", "kb_id": kb_id, **resultado}
    return resultado


# ---------------------------------------------------------------- depois da pausa
# As saídas de uma ação que pediu confirmação: executar (aprovada) ou encaminhar à fila humana
# (rejeitada, ou prazo vencido). Não são ferramentas do modelo: quem as chama é o laço
# (agente._executar, agente.retomar), com a ação que já passou por todos os portões.

def aprovar_pendencia(estado, con, acao: dict) -> dict:
    """O analista aprovou dentro do prazo: executa a escrita que estava pendente."""
    artigo = db.buscar_artigo(con, acao["kb_id"])
    resultado = db.abrir_chamado(con, estado.ticket, acao["resumo"].strip(), artigo)
    estado.desfecho = {"acao": "abrir_chamado_interno", "kb_id": acao["kb_id"], **resultado}
    return resultado


def encaminhar_pendencia(estado, con, acao: dict, motivo: str, chave: str | None = None,
                         chave_aviso: str | None = None) -> tuple[dict, dict]:
    """A ação NÃO é executada (o analista a rejeitou, ou o prazo venceu sem resposta) e o CÓDIGO
    encaminha o chamado à fila humana com as considerações do agente: ação proposta, prioridade
    que o chamado teria, procedimento, score e texto redigido. No prazo vencido de um chamado que
    seria P1, grava também o aviso ao gestor.
    A ação pode ser também o pedido de informação ao cliente (H2, só no grafo): aí as considerações
    são a mensagem redigida, e NÃO há aviso ao gestor, porque um chamado que a triagem não
    conseguiu classificar não tem prioridade prevista (decisão de 12/10/2026).
    `chave` e `chave_aviso` tornam a escrita idempotente (o grafo as passa desde 17/10/2026, para a
    recuperação depois de uma queda poder refazê-la; o laço não as passa e grava como antes).
    Devolve os argumentos e o resultado da escrita, para a trajetória."""
    prazo = f"{estado.prazo_confirmacao_min:g} minutos"
    if motivo == MOTIVO_PRAZO_VENCIDO:
        abertura, por = f"Confirmação não recebida em {prazo}.", f"código: prazo de {prazo} vencido"
    else:
        abertura, por = "Ação rejeitada pelo analista de suporte.", "código: ação rejeitada pelo analista"
    if acao.get("ferramenta") == "devolver_cliente":
        mensagem = (
            f"{abertura} Ação proposta pelo agente e NÃO executada: "
            f"enviar ao cliente o pedido de informação (o único permitido neste chamado). "
            f"Sustentação: a triagem não encontrou no relato o serviço afetado nem o sintoma. "
            f"Mensagem redigida: {acao['mensagem'].strip()}")
        resultado = db.registrar_encaminhamento(con, acao["id_ticket"], "fila_humana", mensagem, None,
                                              chave=chave)
        estado.desfecho = {"acao": "fila_humana", "kb_id": None, **resultado, "motivo": motivo}
        argumentos = {"id_ticket": acao["id_ticket"], "destino": "fila_humana", "mensagem": mensagem,
                      "motivo": motivo}
        return argumentos, {**resultado, "registrado_por": por}
    prioridade = db.prioridade_prevista(con, estado.ticket, db.buscar_artigo(con, acao["kb_id"]))
    mensagem = (
        f"{abertura} Ação proposta pelo agente e NÃO executada: "
        f"abrir chamado interno para {acao['time_destino']} (categoria {acao['categoria']}, "
        f"prioridade prevista {prioridade}). "
        f"Sustentação: procedimento {acao['kb_id']}, score {estado.scores_kb.get(acao['kb_id'])}. "
        f"Resumo redigido: {acao['resumo'].strip()}")
    resultado = db.registrar_encaminhamento(con, acao["id_ticket"], "fila_humana", mensagem, None,
                                              chave=chave)
    if motivo == MOTIVO_PRAZO_VENCIDO and prioridade == PRIORIDADE_QUE_AVISA_GESTOR:
        resultado["aviso_gestor"] = db.avisar_gestor(
            con, acao["id_ticket"], prioridade, motivo, mensagem,
            datetime.now().astimezone().isoformat(timespec="seconds"), chave=chave_aviso)
    estado.desfecho = {"acao": "fila_humana", "kb_id": None, **resultado, "motivo": motivo}
    argumentos = {"id_ticket": acao["id_ticket"], "destino": "fila_humana", "mensagem": mensagem,
                  "motivo": motivo}
    return argumentos, {**resultado, "registrado_por": por}


def registrar_encaminhamento(estado, con, id_ticket: str, destino: str, mensagem: str,
                             kb_id: str | None = None, motivo: str | None = None) -> dict:
    _exigir_sem_desfecho(estado)
    if destino not in DESTINOS:
        raise ErroRecuperavel("destino inválido", recebido=destino, esperado=DESTINOS)
    if not mensagem or len(mensagem.strip()) < 10:
        raise ErroRecuperavel("mensagem curta demais", esperado="pelo menos 10 caracteres")
    if destino != "fila_humana" and (estado.ticket is None or estado.ticket["id"] != id_ticket):
        raise ErroRecuperavel("chame consultar_ticket para este id antes de encaminhar",
                              recebido=id_ticket)
    if destino != "fila_humana":
        motivo = None
    elif motivo is not None and motivo not in MOTIVOS_SEM_BUSCA:
        raise ErroRecuperavel("motivo inválido", recebido=motivo,
                              esperado=MOTIVOS_SEM_BUSCA + ["(ou omita o campo)"])
    # Fila humana para um chamado que EXISTE só depois de olhar a base: impede desistir do
    # procedimento por causa de uma afirmação do cliente (TKT-0003). Id inexistente e pedido
    # fora da alçada não são problema técnico e dispensam a busca.
    if (destino == "fila_humana" and motivo is None and estado.n_buscas == 0
            and estado.ticket is not None and estado.ticket["id"] == id_ticket):
        raise ErroRecuperavel(
            "fila_humana sem nenhuma busca na base para este chamado",
            esperado="uma chamada de buscar_base_conhecimento antes de desistir de agir",
            sugestao="se o chamado relata um problema técnico, busque na base e escolha o desfecho "
                     "pelo artigo e pelo score (afirmação do cliente que o histórico não confirma "
                     "não é motivo de fila_humana). Se o cliente pede APENAS para encerrar um "
                     "chamado ou mudar prioridade, repita com motivo 'fora_da_alcada'")
    if destino == "devolver_cliente":
        _exigir_pedido_sem_informacao_interna(con, mensagem)
    if destino == "anotacao_interna":
        artigo = _exigir_confianca(estado, con, kb_id)
        if artigo["acao_padrao"] != "anotar":
            raise ErroRecuperavel(
                "este procedimento exige escalonamento, não anotação", kb_id=kb_id,
                sugestao="use abrir_chamado_interno")
    else:
        kb_id = None
    # Um pedido de informação por chamado: conferido no BANCO, para valer entre execuções.
    if destino == "devolver_cliente" and db.contar_pedidos_cliente(con, id_ticket) > 0:
        raise ErroRecuperavel(
            "este chamado já recebeu um pedido de informação ao cliente",
            esperado="no máximo um devolver_cliente por chamado",
            sugestao="não peça de novo: chame registrar_encaminhamento com destino "
                     "'fila_humana' e explique o que ainda falta")
    resultado = db.registrar_encaminhamento(con, id_ticket, destino, mensagem.strip(), kb_id)
    estado.desfecho = {"acao": destino, "kb_id": kb_id, **resultado}
    if motivo:
        estado.desfecho["motivo"] = motivo
    return resultado


FUNCOES = {
    "consultar_ticket": consultar_ticket,
    "buscar_base_conhecimento": buscar_base_conhecimento,
    "abrir_chamado_interno": abrir_chamado_interno,
    "registrar_encaminhamento": registrar_encaminhamento,
}

FERRAMENTAS_DE_ESCRITA = {"abrir_chamado_interno", "registrar_encaminhamento"}

# ---------------------------------------------------------------- schemas
SCHEMAS = [
    {"type": "function", "function": {
        "name": "consultar_ticket",
        "description": "Lê o registro do chamado externo no sistema de tickets: log anexado "
                       "(se houver), plano e o histórico de chamados internos do cliente. "
                       "O texto do cliente já vem na entrada. Só leitura.",
        "parameters": {"type": "object", "properties": {
            "id_ticket": {"type": "string", "description": "ex: TKT-0042"}},
            "required": ["id_ticket"]}}},
    {"type": "function", "function": {
        "name": "buscar_base_conhecimento",
        "description": "Busca procedimentos na base de conhecimento interna por "
                       "palavras. Devolve até 3 artigos com 'score' de 0 a 1. Só leitura.",
        "parameters": {"type": "object", "properties": {
            "termos": {"type": "array", "items": {"type": "string"},
                       "description": "2 a 5 palavras em português, minúsculas, sem acento, "
                                      "que descrevam o serviço e o sintoma"}},
            "required": ["termos"]}}},
    {"type": "function", "function": {
        "name": "abrir_chamado_interno",
        "description": "ESCRITA IRREVERSÍVEL. Abre chamado interno para o time responsável. "
                       "Só para procedimentos de escalonamento com score >= limiar. "
                       "Requer confirmação do analista. Categoria, time e prioridade são "
                       "definidos pelo sistema, a partir do artigo.",
        "parameters": {"type": "object", "properties": {
            "id_ticket": {"type": "string"},
            "resumo": {"type": "string",
                       "description": "resumo objetivo do problema para o time interno; "
                                      "afirmações do cliente devem ser marcadas como tal"},
            "kb_id": {"type": "string", "description": "artigo devolvido pela busca"}},
            "required": ["id_ticket", "resumo", "kb_id"]}}},
    {"type": "function", "function": {
        "name": "registrar_encaminhamento",
        "description": "ESCRITA. Registra o desfecho que não abre chamado: fila_comercial, "
                       "devolver_cliente (a mensagem é ENVIADA AO CLIENTE, no máximo uma vez por "
                       "chamado: só a lista do que falta, sem informação interna nem promessa), "
                       "anotacao_interna (mensagem = correção sugerida, exige kb_id de "
                       "procedimento 'anotar') ou fila_humana (mensagem = por que um humano deve "
                       "olhar; para chamado existente, só depois de buscar na base).",
        "parameters": {"type": "object", "properties": {
            "id_ticket": {"type": "string"},
            "destino": {"type": "string", "enum": DESTINOS},
            "mensagem": {"type": "string"},
            "kb_id": {"type": "string", "description": "só para anotacao_interna"},
            "motivo": {"type": "string", "enum": MOTIVOS_SEM_BUSCA,
                       "description": "só para fila_humana SEM busca: 'fora_da_alcada' quando o "
                                      "cliente pede apenas para encerrar um chamado ou mudar a "
                                      "prioridade"}},
            "required": ["id_ticket", "destino", "mensagem"]}}},
]

__all__ = ["FUNCOES", "SCHEMAS", "FERRAMENTAS_DE_ESCRITA", "ErroRecuperavel",
           "ErroFatal", "PausaParaHumano", "AcaoRejeitada", "LIMIAR_CONFIANCA",
           "PRAZO_CONFIRMACAO_MIN", "MOTIVO_PRAZO_VENCIDO", "MOTIVO_REJEITADA",
           "PRIORIDADE_QUE_AVISA_GESTOR", "aprovar_pendencia", "encaminhar_pendencia"]

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
import db

LIMIAR_CONFIANCA = 0.5   # abaixo disso, o agente NÃO age sozinho (vai à fila humana)

CATEGORIAS = ["ssl_certificado", "disco_cheio", "acesso_ssh", "site_fora_do_ar",
              "backup", "outro_tecnico"]
DESTINOS = ["fila_comercial", "devolver_cliente", "anotacao_interna", "fila_humana"]


class ErroRecuperavel(Exception):
    """O modelo pode contornar mudando a chamada. Volta como observação."""

    def __init__(self, mensagem, **contexto):
        super().__init__(mensagem)
        self.payload = {"erro": mensagem, **contexto}


class ErroFatal(Exception):
    """Nenhuma decisão do modelo resolve. Aborta o laço."""


class PausaParaHumano(Exception):
    """Ação irreversível não confirmada: o agente para e devolve o controle."""

    def __init__(self, pendencia: dict):
        super().__init__("ação irreversível aguardando confirmação humana")
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
    return {k: v for k, v in ticket.items() if not k.startswith("_")}


def buscar_base_conhecimento(estado, con, termos: list[str]) -> dict:
    if not isinstance(termos, list) or not termos:
        raise ErroRecuperavel(
            "termos deve ser uma lista não vazia de palavras", recebido=termos,
            esperado='lista com 2 a 5 palavras, ex: ["certificado", "ssl", "vencido"]')
    resultados = db.buscar_kb(con, termos)
    for r in resultados:
        estado.scores_kb[r["kb_id"]] = r["score"]   # o portão de confiança confere depois
    if not resultados:
        return {"resultados": [],
                "aviso": "nenhum procedimento da base tem correspondência com esses termos"}
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


def _exigir_sem_desfecho(estado):
    if estado.desfecho is not None:
        raise ErroRecuperavel(
            "este chamado já recebeu um desfecho", desfecho=estado.desfecho,
            sugestao="não registre outro; responda com o resumo final")


def abrir_chamado_interno(estado, con, id_ticket: str, categoria: str,
                          resumo: str, kb_id: str) -> dict:
    _exigir_sem_desfecho(estado)
    if estado.ticket is None or estado.ticket["id"] != id_ticket:
        raise ErroRecuperavel("chame consultar_ticket para este id antes de abrir chamado",
                              recebido=id_ticket)
    if categoria not in CATEGORIAS:
        raise ErroRecuperavel("categoria inválida", recebido=categoria, esperado=CATEGORIAS)
    if not resumo or len(resumo.strip()) < 20:
        raise ErroRecuperavel("resumo curto demais", esperado="pelo menos 20 caracteres")
    artigo = _exigir_confianca(estado, con, kb_id)
    if artigo["acao_padrao"] != "escalar":
        raise ErroRecuperavel(
            "este procedimento não é de escalonamento", kb_id=kb_id,
            sugestao="use registrar_encaminhamento com destino 'anotacao_interna'")

    # Ação irreversível: quem confirma é o ANALISTA DE SUPORTE (perfil da §2.2).
    pendencia = {"ferramenta": "abrir_chamado_interno", "id_ticket": id_ticket,
                 "categoria": categoria, "resumo": resumo,
                 "time_destino": artigo["time_destino"], "kb_id": kb_id}
    if not estado.confirmar(pendencia):
        raise PausaParaHumano(pendencia)

    resultado = db.abrir_chamado(con, estado.ticket, categoria, resumo.strip(), artigo)
    estado.desfecho = {"acao": "abrir_chamado_interno", "kb_id": kb_id, **resultado}
    return resultado


def registrar_encaminhamento(estado, con, id_ticket: str, destino: str,
                             mensagem: str, kb_id: str | None = None) -> dict:
    _exigir_sem_desfecho(estado)
    if destino not in DESTINOS:
        raise ErroRecuperavel("destino inválido", recebido=destino, esperado=DESTINOS)
    if not mensagem or len(mensagem.strip()) < 10:
        raise ErroRecuperavel("mensagem curta demais", esperado="pelo menos 10 caracteres")
    if destino != "fila_humana" and (estado.ticket is None or estado.ticket["id"] != id_ticket):
        raise ErroRecuperavel("chame consultar_ticket para este id antes de encaminhar",
                              recebido=id_ticket)
    if destino == "anotacao_interna":
        artigo = _exigir_confianca(estado, con, kb_id)
        if artigo["acao_padrao"] != "anotar":
            raise ErroRecuperavel(
                "este procedimento exige escalonamento, não anotação", kb_id=kb_id,
                sugestao="use abrir_chamado_interno")
    else:
        kb_id = None
    resultado = db.registrar_encaminhamento(con, id_ticket, destino, mensagem.strip(), kb_id)
    estado.desfecho = {"acao": destino, "kb_id": kb_id, **resultado}
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
        "description": "Lê o chamado externo no sistema de tickets: texto do cliente, "
                       "log anexado (se houver), plano e o histórico de chamados internos "
                       "do cliente. Só leitura.",
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
                       "Requer confirmação do analista. Time e prioridade são definidos pelo sistema.",
        "parameters": {"type": "object", "properties": {
            "id_ticket": {"type": "string"},
            "categoria": {"type": "string", "enum": CATEGORIAS},
            "resumo": {"type": "string",
                       "description": "resumo objetivo do problema para o time interno; "
                                      "afirmações do cliente devem ser marcadas como tal"},
            "kb_id": {"type": "string", "description": "artigo devolvido pela busca"}},
            "required": ["id_ticket", "categoria", "resumo", "kb_id"]}}},
    {"type": "function", "function": {
        "name": "registrar_encaminhamento",
        "description": "ESCRITA REVERSÍVEL. Registra o desfecho que não abre chamado: "
                       "fila_comercial, devolver_cliente (mensagem = o que pedir ao cliente), "
                       "anotacao_interna (mensagem = correção sugerida, exige kb_id de "
                       "procedimento 'anotar') ou fila_humana (mensagem = por que um humano deve olhar).",
        "parameters": {"type": "object", "properties": {
            "id_ticket": {"type": "string"},
            "destino": {"type": "string", "enum": DESTINOS},
            "mensagem": {"type": "string"},
            "kb_id": {"type": "string", "description": "só para anotacao_interna"}},
            "required": ["id_ticket", "destino", "mensagem"]}}},
]

__all__ = ["FUNCOES", "SCHEMAS", "FERRAMENTAS_DE_ESCRITA", "ErroRecuperavel",
           "ErroFatal", "PausaParaHumano", "LIMIAR_CONFIANCA"]

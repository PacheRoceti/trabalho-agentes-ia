"""Camada de acesso ao "sistema de tickets" (SQLite).

É aqui que o agente atravessa a fronteira do próprio processo (item 4.2 do
enunciado): as ferramentas NÃO tocam em dicionário Python, chamam estas
funções, que falam com um banco de dados de verdade. Nenhuma função aqui
conhece o modelo, e nenhuma decide nada de negócio além de regras
determinísticas (prioridade, reincidência, idempotência).

SQLite porque não exige servidor: o projeto precisa rodar do zero em <5 min.
Na Parte 2 esta camada vira servidor MCP; trocar SQLite por outro banco
(MySQL, Postgres) é mexer só neste arquivo.
"""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "dados" / "tickets.db"
SEED = RAIZ / "dados" / "seed.sql"

# "Agora" fixo, para a demonstração ser reproduzível (mesma ideia do HOJE
# dos dados do laboratório).
AGORA = "2026-09-21 12:00"
JANELA_REINCIDENCIA_DIAS = 30

PRIORIDADES = ["P3", "P2", "P1"]  # da menor para a maior

# Palavras que aparecem em quase todo chamado e não discriminam nada (as últimas são só
# palavras de ligação, que chegam quando o modelo busca com frases).
GENERICAS = {"servidor", "site", "problema", "erro", "cliente", "hospedagem",
             "nao", "esta", "meu", "minha", "muito", "sistema", "ajuda",
             "fora", "desde", "para", "com", "sem", "que", "dos", "das", "uma", "por", "mais"}

# Formas que o cliente usa e que não têm o mesmo radical da palavra-chave do procedimento.
# Paliativo ASSUMIDO da busca por palavra (some com o RAG da Parte 2): a lista é curta, foi
# escrita depois de ver o TKT-0007 falhar por uma forma sem o mesmo radical e não cobre o que não
# foi visto.
SINONIMOS = {"salvar": "gravar", "expirou": "vencido", "caiu": "indisponivel"}

# Fator aplicado ao score quando a correspondência não autoriza agir: um único termo casado, ou
# um relato que cai numa ressalva do procedimento (coluna nao_cobre). Com ele o score máximo
# fica em 0,4, abaixo do limiar do portão.
REDUTOR = 0.4

# CURADORIA, em duas regras aplicadas ANTES do score, porque a busca não tem como saber qual de
# duas versões vale: as duas casam com o mesmo relato.
#   1. guia com `revogado_por` preenchido não entra na busca;
#   2. entre as versões de um mesmo procedimento (KB-101, KB-101-A, KB-101-B...), só a de maior
#      `data_publicacao` entra. É o que segura a versão antiga que ninguém marcou como revogada.
# Cada uma fica desligada só para medir o que acontece sem ela (main.py --sem-filtro-revogados e
# --sem-desempate-data, docs/rag.md §2.1).
FILTRAR_REVOGADOS = True
DESEMPATAR_POR_DATA = True

# KB-101-A é uma atualização do KB-101: o id sem a letra identifica o procedimento.
ID_KB = re.compile(r"^(KB-\d+)(?:-([A-Z]))?$")

ID_TICKET = re.compile(r"^TKT-\d{4}$")

# Ações irreversíveis à espera do analista. Não é dado do seed: é estado que as execuções criam,
# por isso a tabela nasce aqui (e também em bancos criados antes de ela existir). As datas são
# do relógio de verdade, e não o AGORA fixo: o prazo de confirmação conta em tempo real.
SQL_PENDENCIAS = """
CREATE TABLE IF NOT EXISTS pendencias (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_externo TEXT NOT NULL,
    acao           TEXT NOT NULL,              -- JSON: a ação proposta, como o analista a vê
    pedido_em      TEXT NOT NULL,              -- ISO 8601 com fuso
    vence_em       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'aguardando',
                   -- aguardando | aprovada | rejeitada | vencida | substituida
    resolvido_em   TEXT,
    resolvido_por  TEXT,
    checkpoint     TEXT                        -- JSON: o Estado da execução pausada
)"""

# Avisos ao gestor de suporte: o chamado interno que seria P1 e não foi aberto porque o analista
# não respondeu no prazo. Como as pendências, é estado criado pelas execuções, com data real.
SQL_AVISOS_GESTOR = """
CREATE TABLE IF NOT EXISTS avisos_gestor (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_externo TEXT NOT NULL,
    prioridade     TEXT NOT NULL,              -- a que o chamado interno teria
    motivo         TEXT NOT NULL,
    mensagem       TEXT NOT NULL,
    criado_em      TEXT NOT NULL               -- ISO 8601 com fuso
)"""


class RegistroNaoEncontrado(Exception):
    """A consulta foi válida, mas o registro não existe no sistema."""


# Índice da busca vetorial (src/vetorial.py): um vetor por guia, com o hash do texto que o gerou.
# Nasce aqui, como pendencias: não é do seed. Texto do guia mudou = hash diferente = vetor refeito.
SQL_VETORES = """
CREATE TABLE IF NOT EXISTS kb_vetores (
    kb_id       TEXT PRIMARY KEY,
    texto_hash  TEXT NOT NULL,
    modelo      TEXT NOT NULL,
    vetor       TEXT NOT NULL            -- lista JSON de floats
)"""


def conectar() -> sqlite3.Connection:
    if not DB_PATH.exists():
        recriar_banco()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute(SQL_PENDENCIAS)
    con.execute(SQL_AVISOS_GESTOR)
    con.execute(SQL_VETORES)
    return con


def recriar_banco() -> None:
    """Zera o banco e recria tudo a partir do seed.sql (estado inicial conhecido).

    Não apaga o arquivo: no Windows o SO não deixa apagar um arquivo enquanto
    existe outra conexão aberta com ele. Em vez disso, derruba as tabelas e
    recria."""
    con = sqlite3.connect(DB_PATH)
    tabelas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    for t in tabelas:
        con.execute(f"DROP TABLE IF EXISTS {t}")
    con.executescript(SEED.read_text(encoding="utf-8"))
    con.execute(SQL_PENDENCIAS)
    con.execute(SQL_AVISOS_GESTOR)
    con.execute(SQL_VETORES)
    con.commit()
    con.close()


# ------------------------------------------------------------------ leitura

def buscar_ticket(con: sqlite3.Connection, id_ticket: str) -> dict:
    linha = con.execute(
        """SELECT t.id, t.texto, t.aberto_em, t.status, t.anexo_log, c.id AS cliente_id,
                  c.nome AS cliente, c.plano
           FROM tickets_externos t JOIN clientes c ON c.id = t.cliente_id
           WHERE t.id = ?""", (id_ticket,)).fetchone()
    if linha is None:
        raise RegistroNaoEncontrado(id_ticket)
    historico = con.execute(
        """SELECT 'INC-' || printf('%04d', id) AS chamado_interno, categoria,
                  criado_em, status
           FROM chamados_internos WHERE cliente_id = ?
           ORDER BY criado_em DESC LIMIT 5""", (linha["cliente_id"],)).fetchall()
    return {
        "id": linha["id"], "texto": linha["texto"],
        "aberto_em": linha["aberto_em"], "status": linha["status"],
        "anexo_log": linha["anexo_log"],
        "cliente": linha["cliente"], "plano": linha["plano"],
        "_cliente_id": linha["cliente_id"],
        "historico_cliente": [dict(h) for h in historico],
    }


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


def _casa(termo: str, chave: str) -> bool:
    """Igualdade, ou mesmo radical (4 letras) para tolerar flexão:
    'vencido'/'venceu', 'renovar'/'renovacao'."""
    if termo == chave:
        return True
    return len(termo) >= 5 and len(chave) >= 5 and termo[:4] == chave[:4]


def _procedimento(kb_id: str) -> str:
    """O procedimento de que o guia é uma versão: o id sem a letra (KB-101-A -> KB-101)."""
    m = ID_KB.match(kb_id)
    return m.group(1) if m else kb_id


def _ordem_de_versao(artigo) -> tuple[str, str]:
    """A versão mais nova é a de maior data de publicação. A letra só desempata duas versões
    publicadas no mesmo dia (mais adiante no alfabeto = mais nova; sem letra = a primeira)."""
    m = ID_KB.match(artigo["id"])
    return artigo["data_publicacao"], (m.group(2) or "") if m else ""


def _mais_nova(artigos) -> dict:
    """Procedimento -> a versão de maior data de publicação (a que vale)."""
    mais_nova = {}
    for a in artigos:
        p = _procedimento(a["id"])
        if p not in mais_nova or _ordem_de_versao(a) > _ordem_de_versao(mais_nova[p]):
            mais_nova[p] = a
    return mais_nova


def _contexto(relato: str | None, termos: list[str]) -> str:
    """O texto contra o qual as ressalvas (coluna nao_cobre) são procuradas."""
    return _normalizar(" ".join([relato or ""] + [str(t) for t in termos]))


def _ressalva(artigo, contexto: str) -> str | None:
    """A frase de nao_cobre do guia que aparece no relato, se houver."""
    return next((f.strip() for f in artigo["nao_cobre"].split(";")
                 if f.strip() and f.strip() in contexto), None)


def _palavras(termos: list[str]) -> list[str]:
    """Os termos do modelo viram palavras: frases são quebradas, palavras genéricas e de até
    2 letras saem, sinônimos conhecidos viram a palavra-chave, e não há repetição."""
    palavras = []
    for termo in termos:
        for p in re.split(r"[^a-z0-9]+", _normalizar(str(termo))):
            if len(p) < 3 or any(_casa(p, g) for g in GENERICAS):
                continue
            p = next((chave for forma, chave in SINONIMOS.items() if _casa(p, forma)), p)
            if p not in palavras:
                palavras.append(p)
    return palavras


def buscar_kb(con: sqlite3.Connection, termos: list[str], top: int = 3,
              relato: str | None = None, incluir_revogados: bool | None = None,
              desempatar_por_data: bool | None = None) -> list[dict]:
    """Busca por sobreposição de palavras-chave.

    score = casados / (casados + nao_casados / 2)

    Mede quanto da CONSULTA o artigo explica; cada termo que o artigo não tem pesa metade de
    um que tem. O tamanho da lista de palavras-chave do artigo não entra na conta: ela reúne
    formas alternativas (gravar/escrita, pasta/arquivos), e nenhum relato usa todas. Na
    fórmula anterior (Dice sobre a lista inteira) dois termos casados davam no máximo 0,5.

    Duas reduções (REDUTOR) deixam o score abaixo do limiar do portão:
      - um único termo casado: uma palavra só não identifica um procedimento;
      - o relato cai numa RESSALVA do procedimento (coluna nao_cobre, frases separadas por ';',
        procuradas no texto do cliente e nos termos). O artigo volta com o campo 'ressalva'.

    CURADORIA, antes do score:
      - guia revogado (coluna revogado_por preenchida) fica FORA da busca;
      - das versões de um mesmo procedimento (KB-101, KB-101-A...) só a mais nova concorre, pela
        data_publicacao. A versão superada sai mesmo que a nova não case com a consulta: guia
        antigo não age. O descarte NÃO é silencioso: a versão que ficou volta com
        'data_publicacao' e 'versoes_descartadas' (as antigas que também casavam).
    `incluir_revogados` e `desempatar_por_data` existem só para medir o que acontece sem cada
    regra; None vale o que FILTRAR_REVOGADOS / DESEMPATAR_POR_DATA disserem. Sem as duas, o
    resultado NÃO diz qual versão vale: é a situação de um corpus sem curadoria.

    Continua IMPERFEITA: só enxerga palavra, não sentido. É o que a busca vetorial (RAG)
    resolve na Parte 2, e o limiar de 0.5 foi ajustado à mão para os dados desta demonstração.
    """
    if incluir_revogados is None:
        incluir_revogados = not FILTRAR_REVOGADOS
    if desempatar_por_data is None:
        desempatar_por_data = DESEMPATAR_POR_DATA
    consulta = _palavras(termos)
    contexto = _contexto(relato, termos)
    resultados = []
    sql = "SELECT * FROM kb_artigos" + ("" if incluir_revogados else " WHERE revogado_por IS NULL")
    artigos = con.execute(sql).fetchall()
    mais_nova = _mais_nova(artigos)      # procedimento -> a versão de maior data_publicacao
    descartadas = {}                     # id da versão que ficou -> antigas que também casavam
    for a in artigos:
        chaves = a["palavras_chave"].split()
        casados = sum(1 for t in consulta if any(_casa(t, c) for c in chaves))
        if casados == 0:
            continue
        vigente = mais_nova[_procedimento(a["id"])]
        if desempatar_por_data and vigente["id"] != a["id"]:
            descartadas.setdefault(vigente["id"], []).append(
                {"kb_id": a["id"], "data_publicacao": a["data_publicacao"]})
            continue
        score = casados / (casados + (len(consulta) - casados) / 2)
        if casados < 2:
            score *= REDUTOR
        ressalva = _ressalva(a, contexto)
        if ressalva:
            score *= REDUTOR
        resultado = {
            "kb_id": a["id"], "titulo": a["titulo"], "score": round(score, 2),
            "causa": a["causa"], "solucao": a["solucao"],
            "acao_padrao": a["acao_padrao"], "time_destino": a["time_destino"],
        }
        if ressalva:
            resultado["ressalva"] = (f"este procedimento NÃO cobre o caso relatado "
                                     f"('{ressalva}'): o score foi reduzido")
        resultados.append(resultado)
    for r in resultados:
        if r["kb_id"] in descartadas:
            r["data_publicacao"] = mais_nova[_procedimento(r["kb_id"])]["data_publicacao"]
            r["versoes_descartadas"] = descartadas[r["kb_id"]]
    resultados.sort(key=lambda r: r["score"], reverse=True)
    return resultados[:top]


def ficha_do_plano(con: sqlite3.Connection, plano: str | None) -> dict | None:
    """A ficha do plano do cliente (fonte E, tabela planos_fichas), por consulta estruturada: o
    plano vem de clientes.plano e a ficha é a de mesmo nome. Contexto da redação e da tela do
    analista; nunca autoriza escrita (a ficha não tem ação, time nem prioridade)."""
    linha = con.execute("SELECT * FROM planos_fichas WHERE plano = ?", (plano,)).fetchone()
    return dict(linha) if linha else None


def buscar_artigo(con: sqlite3.Connection, kb_id: str) -> dict | None:
    linha = con.execute("SELECT * FROM kb_artigos WHERE id = ?", (kb_id,)).fetchone()
    return dict(linha) if linha else None


# ------------------------------------------------------------------ escrita

def _reincidencia(con, cliente_id: str, categoria: str) -> int:
    return con.execute(
        """SELECT COUNT(*) FROM chamados_internos
           WHERE cliente_id = ? AND categoria = ?
             AND criado_em >= date(?, ?)""",
        (cliente_id, categoria, AGORA, f"-{JANELA_REINCIDENCIA_DIAS} days"),
    ).fetchone()[0]


def _prioridade(base: str, reincidencias: int) -> str:
    """Regra de negócio, em CÓDIGO: reincidência sobe um nível.
    O modelo não escolhe prioridade e o cliente não consegue exigi-la."""
    nivel = PRIORIDADES.index(base)
    if reincidencias > 0:
        nivel = min(nivel + 1, len(PRIORIDADES) - 1)
    return PRIORIDADES[nivel]


def prioridade_prevista(con, ticket: dict, artigo: dict) -> str:
    """A prioridade que o chamado interno teria se fosse aberto agora (mesma regra de
    abrir_chamado). Serve à ação que NÃO foi executada: é ela que decide se o gestor é avisado."""
    return _prioridade(artigo["prioridade_base"],
                       _reincidencia(con, ticket["_cliente_id"], artigo["categoria"]))


def abrir_chamado(con, ticket: dict, resumo: str, artigo: dict) -> dict:
    """Escrita IRREVERSÍVEL (não há 'apagar' nem 'encerrar' chamado por aqui).

    Categoria, time e prioridade base vêm do artigo, não do modelo: é pela
    categoria que a reincidência é contada.

    Idempotente: a chave ticket+artigo é UNIQUE, então repetir a chamada
    devolve o chamado existente em vez de duplicar."""
    categoria = artigo["categoria"]
    chave = f"{ticket['id']}:{artigo['id']}"
    existente = con.execute(
        "SELECT * FROM chamados_internos WHERE chave_idempotencia = ?", (chave,)
    ).fetchone()
    if existente:
        return _resultado_chamado(existente, ja_existia=True)
    reinc = _reincidencia(con, ticket["_cliente_id"], categoria)
    prioridade = _prioridade(artigo["prioridade_base"], reinc)
    cur = con.execute(
        """INSERT INTO chamados_internos
           (ticket_externo, cliente_id, categoria, resumo, kb_id, time_destino,
            prioridade, reincidencia, chave_idempotencia, criado_em)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticket["id"], ticket["_cliente_id"], categoria, resumo, artigo["id"],
         artigo["time_destino"], prioridade, reinc, chave, AGORA))
    con.commit()
    novo = con.execute("SELECT * FROM chamados_internos WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return _resultado_chamado(novo, ja_existia=False)


def _resultado_chamado(linha, ja_existia: bool) -> dict:
    return {
        "chamado_interno": f"INC-{linha['id']:04d}",
        "time_destino": linha["time_destino"],
        "prioridade": linha["prioridade"],
        "reincidencias_confirmadas_no_sistema": linha["reincidencia"],
        "ja_existia": ja_existia,
    }


def registrar_texto(con, id_ticket: str, texto: str) -> bool:
    """Grava no chamado o texto que chegou como entrada (o que o cliente digitou). Vale o texto
    recebido: a busca, o log e o registro passam a usar o mesmo. Devolve False se o id não
    existe (nada é criado: o chamado nasce no sistema de tickets, não aqui)."""
    cur = con.execute("UPDATE tickets_externos SET texto = ? WHERE id = ?", (texto, id_ticket))
    con.commit()
    return cur.rowcount == 1


def registrar_encaminhamento(con, id_ticket: str, destino: str, mensagem: str,
                             kb_id: str | None) -> dict:
    """Escrita REVERSÍVEL: uma linha numa fila/anotação, que um humano pode
    desfazer. Aceita id inexistente de propósito (destino fila_humana)."""
    cur = con.execute(
        """INSERT INTO encaminhamentos (ticket_externo, destino, mensagem, kb_id, criado_em)
           VALUES (?, ?, ?, ?, ?)""", (id_ticket, destino, mensagem, kb_id, AGORA))
    con.commit()
    return {"encaminhamento": cur.lastrowid, "destino": destino}


# ------------------------------------------------------------------ pendências

def criar_pendencia(con, id_ticket: str, acao: dict, pedido_em: str, vence_em: str) -> int:
    """Registra a ação irreversível que aguarda o analista. Nada do que ela propõe é gravado
    aqui. Uma pendência anterior do mesmo chamado deixa de valer: só a última pode ser aprovada."""
    con.execute("""UPDATE pendencias SET status = 'substituida'
                   WHERE ticket_externo = ? AND status = 'aguardando'""", (id_ticket,))
    cur = con.execute(
        """INSERT INTO pendencias (ticket_externo, acao, pedido_em, vence_em)
           VALUES (?, ?, ?, ?)""",
        (id_ticket, json.dumps(acao, ensure_ascii=False), pedido_em, vence_em))
    con.commit()
    return cur.lastrowid


def gravar_checkpoint(con, id_pendencia: int, checkpoint: dict) -> None:
    con.execute("UPDATE pendencias SET checkpoint = ? WHERE id = ?",
                (json.dumps(checkpoint, ensure_ascii=False), id_pendencia))
    con.commit()


def pendencias_aguardando(con, id_ticket: str | None = None) -> list[dict]:
    """As pendências sem resposta, da mais antiga para a mais nova (de um chamado, ou todas)."""
    sql = "SELECT * FROM pendencias WHERE status = 'aguardando'"
    args = ()
    if id_ticket is not None:
        sql, args = sql + " AND ticket_externo = ?", (id_ticket,)
    linhas = con.execute(sql + " ORDER BY id", args).fetchall()
    return [{**dict(l), "acao": json.loads(l["acao"]),
             "checkpoint": json.loads(l["checkpoint"]) if l["checkpoint"] else None}
            for l in linhas]


def resolver_pendencia(con, id_pendencia: int, status: str, quando: str, por: str) -> bool:
    """Fecha a pendência. Devolve False se ela já tinha sido resolvida: é o que impede a
    segunda aprovação de repetir a escrita."""
    cur = con.execute(
        """UPDATE pendencias SET status = ?, resolvido_em = ?, resolvido_por = ?
           WHERE id = ? AND status = 'aguardando'""", (status, quando, por, id_pendencia))
    con.commit()
    return cur.rowcount == 1


def avisar_gestor(con, id_ticket: str, prioridade: str, motivo: str, mensagem: str,
                  quando: str) -> int:
    """Registra o aviso ao gestor de suporte. É uma linha a mais, e não um desfecho: o desfecho
    do chamado continua sendo o encaminhamento à fila humana."""
    cur = con.execute(
        """INSERT INTO avisos_gestor (ticket_externo, prioridade, motivo, mensagem, criado_em)
           VALUES (?, ?, ?, ?, ?)""", (id_ticket, prioridade, motivo, mensagem, quando))
    con.commit()
    return cur.lastrowid


def times_destino(con) -> list[str]:
    """Os times citados nos procedimentos da base (lista de referência dos nomes internos)."""
    return [r[0] for r in con.execute("SELECT DISTINCT time_destino FROM kb_artigos")]


def contar_pedidos_cliente(con, id_ticket: str) -> int:
    """Quantos pedidos de informação (devolver_cliente) o chamado já recebeu.
    A regra de domínio é no máximo UM por chamado, em qualquer execução."""
    return con.execute(
        """SELECT COUNT(*) FROM encaminhamentos
           WHERE ticket_externo = ? AND destino = 'devolver_cliente'""", (id_ticket,)
    ).fetchone()[0]


def contar(con, tabela: str, id_ticket: str) -> int:
    """Usado pelo verificador: quantas linhas o agente gravou para o ticket."""
    return con.execute(
        f"SELECT COUNT(*) FROM {tabela} WHERE ticket_externo = ?", (id_ticket,)
    ).fetchone()[0]

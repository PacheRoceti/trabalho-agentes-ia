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

ID_TICKET = re.compile(r"^TKT-\d{4}$")


class RegistroNaoEncontrado(Exception):
    """A consulta foi válida, mas o registro não existe no sistema."""


def conectar() -> sqlite3.Connection:
    if not DB_PATH.exists():
        recriar_banco()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
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
              relato: str | None = None) -> list[dict]:
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

    Continua IMPERFEITA: só enxerga palavra, não sentido. É o que a busca vetorial (RAG)
    resolve na Parte 2, e o limiar de 0.5 foi ajustado à mão para os dados desta demonstração.
    """
    consulta = _palavras(termos)
    contexto = _normalizar(" ".join([relato or ""] + [str(t) for t in termos]))
    resultados = []
    for a in con.execute("SELECT * FROM kb_artigos").fetchall():
        chaves = a["palavras_chave"].split()
        casados = sum(1 for t in consulta if any(_casa(t, c) for c in chaves))
        if casados == 0:
            continue
        score = casados / (casados + (len(consulta) - casados) / 2)
        if casados < 2:
            score *= REDUTOR
        ressalva = next((f.strip() for f in a["nao_cobre"].split(";")
                         if f.strip() and f.strip() in contexto), None)
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
    resultados.sort(key=lambda r: r["score"], reverse=True)
    return resultados[:top]


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

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

# Palavras que aparecem em quase todo chamado e não discriminam nada.
GENERICAS = {"servidor", "site", "problema", "erro", "cliente", "hospedagem",
             "nao", "esta", "meu", "minha", "muito", "sistema", "ajuda"}

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


def buscar_kb(con: sqlite3.Connection, termos: list[str], top: int = 3) -> list[dict]:
    """Busca por sobreposição de palavras-chave (coeficiente de Dice).

    score = 2 * casados / (termos_da_consulta + chaves_do_artigo)

    Um termo a mais na consulta derruba o score um pouco, mas não o zera
    (Jaccard puniria mais); e poucos termos, ou termos que não estão no
    artigo, deixam o score abaixo de 0.5.

    Deliberadamente simples e IMPERFEITA: só enxerga palavra, não sentido. É
    o que a busca vetorial (RAG) resolve na Parte 2, e o limiar de 0.5 foi
    calibrado à mão para os dados desta demonstração.
    """
    consulta = [t for t in (_normalizar(t) for t in termos)
                if t and t not in GENERICAS]
    resultados = []
    for a in con.execute("SELECT * FROM kb_artigos").fetchall():
        chaves = a["palavras_chave"].split()
        casados = sum(1 for t in consulta if any(_casa(t, c) for c in chaves))
        if casados == 0:
            continue
        score = 2 * casados / (len(consulta) + len(chaves))
        resultados.append({
            "kb_id": a["id"], "titulo": a["titulo"], "score": round(score, 2),
            "causa": a["causa"], "solucao": a["solucao"],
            "acao_padrao": a["acao_padrao"], "time_destino": a["time_destino"],
        })
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


def abrir_chamado(con, ticket: dict, categoria: str, resumo: str, artigo: dict) -> dict:
    """Escrita IRREVERSÍVEL (não há 'apagar' nem 'encerrar' chamado por aqui).

    Idempotente: a chave ticket+artigo é UNIQUE, então repetir a chamada
    devolve o chamado existente em vez de duplicar."""
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


def registrar_encaminhamento(con, id_ticket: str, destino: str, mensagem: str,
                             kb_id: str | None) -> dict:
    """Escrita REVERSÍVEL: uma linha numa fila/anotação, que um humano pode
    desfazer. Aceita id inexistente de propósito (destino fila_humana)."""
    cur = con.execute(
        """INSERT INTO encaminhamentos (ticket_externo, destino, mensagem, kb_id, criado_em)
           VALUES (?, ?, ?, ?, ?)""", (id_ticket, destino, mensagem, kb_id, AGORA))
    con.commit()
    return {"encaminhamento": cur.lastrowid, "destino": destino}


def contar(con, tabela: str, id_ticket: str) -> int:
    """Usado pelo verificador: quantas linhas o agente gravou para o ticket."""
    return con.execute(
        f"SELECT COUNT(*) FROM {tabela} WHERE ticket_externo = ?", (id_ticket,)
    ).fetchone()[0]

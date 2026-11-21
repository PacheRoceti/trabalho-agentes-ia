"""Busca vetorial e busca híbrida da base de conhecimento (Parte 2, docs/rag.md §1 e §4).

    vetorial.buscar(con, termos, relato)     # híbrida: vetores + palavra, fundidas por RRF

O modelo de embedding é o `mistral-embed` (1024 dimensões), da mesma conta e do mesmo endereço do
modelo de chat. O índice é uma lista de vetores em memória, guardada na tabela `kb_vetores`
(db.SQL_VETORES): um vetor por guia, refeito quando o texto do guia muda. Não há banco vetorial:
a base tem poucas dezenas de trechos.

O que é do código, e não do modelo:
  - a CURADORIA (guia revogado e versão superada ficam fora) vale ANTES do ranking, como em
    db.buscar_kb: o vetorial acha as duas versões de um guia, porque as duas falam do mesmo assunto;
  - o SCORE do portão de confiança é o cosseno da consulta com o guia, numa escala linear em que
    o LIMIAR_COSSENO vale 0,5 (o limiar do portão não muda);
  - a RESSALVA (coluna nao_cobre) é a mesma da busca por palavra: a frase aparece, literal, no
    relato. Foi medido que o vetor NÃO a enxerga (docs/rag.md §4.2).
Se o embedding falha (rede, cota, chave), a busca cai para a de palavras e diz isso em cada
resultado (campo `busca`): o sistema não para por causa do índice.
"""
import hashlib
import json
import math
import os
import sqlite3
from pathlib import Path

import db

MODELO_EMBEDDING = "mistral-embed"
DIMENSOES = 1024

# Cosseno a partir do qual o guia autoriza agir. Calibrado em 11/10/2026 com as perguntas A* e N*
# de dados/perguntas-rag.json (docs/rag.md §4.3): o ponto médio entre o pior acerto (0,82) e a
# pior pergunta sem resposta (0,78). Vale para ESTE modelo e ESTE corpus; outro modelo de
# embedding pede outra calibração.
LIMIAR_COSSENO = 0.80
LIMIAR_DO_PORTAO = 0.5            # o mesmo de ferramentas.LIMIAR_CONFIANCA

# Fusão por posição (Reciprocal Rank Fusion): cada ranking contribui com 1 / (K_RRF + posição).
K_RRF = 60

# Substituível nos testes e nas medições: função (lista de textos) -> lista de vetores.
EMBEDDER = None
TOKENS_EMBEDDING = 0              # acumulado do processo; o grafo soma a diferença de cada busca
# Preço do mistral-embed, em US$ por milhão de tokens (página oficial, conferida em 17/10/2026).
# Embedding não gera texto: é um preço só. O main.py o troca pelo PRECO_EMBEDDING_USD do .env.
PRECO_USD_POR_MTOK = 0.10


def custo_usd(tokens: int) -> float:
    """Quanto custam os tokens de embedding. Desde 17/10/2026 o grafo soma isto ao `custo_usd` da
    execução, e por ele ao teto de dinheiro; não ao teto de tokens (grafo._consumo_do_embedding)."""
    return tokens * PRECO_USD_POR_MTOK / 1_000_000


def escala(cosseno: float) -> float:
    """Cosseno -> score do portão: linear, com LIMIAR_COSSENO em 0,5 e 1,0 em 1,0 (zero em 0,6).
    Truncado em duas casas, e não arredondado: com o arredondamento, o cosseno 0,799 virava 0,50 e
    passava o portão abaixo do limiar (visto em 11/10/2026). Assim, score >= 0,5 só com cosseno >= 0,80."""
    bruto = LIMIAR_DO_PORTAO + LIMIAR_DO_PORTAO * (cosseno - LIMIAR_COSSENO) / (1 - LIMIAR_COSSENO)
    return min(1.0, max(0.0, math.floor(round(bruto * 100, 6)) / 100))


def cosseno(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def _embedar_na_api(textos: list[str]) -> list[list[float]]:
    global TOKENS_EMBEDDING
    from dotenv import load_dotenv
    from openai import OpenAI
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"])
    vetores = []
    for i in range(0, len(textos), 32):
        r = _embeddings(client, textos[i:i + 32])          # o span `embeddings` (fim do arquivo)
        TOKENS_EMBEDDING += r.usage.total_tokens
        vetores += [d.embedding for d in r.data]
    return vetores


def embedar(textos: list[str]) -> list[list[float]]:
    """Vetores dos textos. Levanta exceção se a API falhar: quem chama decide o que fazer."""
    return (EMBEDDER or _embedar_na_api)(textos)


def id_da_ficha(plano: str) -> str:
    """O id da ficha de plano no índice (a mesma tabela kb_vetores, fora da disputa dos guias)."""
    return f"PLANO:{plano}"


def texto_da_ficha(f) -> str:
    return f'{f["plano"]}. {f["escopo"]}'


def texto_do_guia(a) -> str:
    """O que é embedado: o que o guia é (título), a causa e a solução. Ação, time, prioridade e
    palavras-chave ficam de fora: são metadados (docs/base-de-conhecimento-v2.md §4)."""
    return f'{a["titulo"]}. {a["causa"]} {a["solucao"]}'


def indice(con: sqlite3.Connection) -> dict[str, list[float]]:
    """Os vetores de TODOS os guias (os revogados também, para a medição sem curadoria) e das
    fichas de plano, refeitos só para o que mudou. Um erro de embedding sobe sem gravar nada."""
    guardados = {r["kb_id"]: r for r in con.execute("SELECT * FROM kb_vetores")}
    pendentes = []
    itens = [(a["id"], texto_do_guia(a)) for a in con.execute("SELECT * FROM kb_artigos")]
    itens += [(id_da_ficha(f["plano"]), texto_da_ficha(f)) for f in con.execute("SELECT * FROM planos_fichas")]
    for id_, texto in itens:
        h = hashlib.sha1(texto.encode("utf-8")).hexdigest()
        g = guardados.get(id_)
        if g is None or g["texto_hash"] != h or g["modelo"] != MODELO_EMBEDDING:
            pendentes.append((id_, texto, h))
    if pendentes:
        novos = embedar([t for _, t, _ in pendentes])
        for (kb_id, _, h), v in zip(pendentes, novos):
            con.execute("INSERT OR REPLACE INTO kb_vetores VALUES (?, ?, ?, ?)",
                        (kb_id, h, MODELO_EMBEDDING, json.dumps(v)))
        con.commit()
    return {r["kb_id"]: json.loads(r["vetor"]) for r in con.execute("SELECT * FROM kb_vetores")}


def buscar_fichas(con: sqlite3.Connection, relato: str, top: int = 1) -> list[dict]:
    """As fichas de plano mais próximas de uma pergunta (cosseno). Só a medição usa: no grafo a
    ficha do cliente vem de db.ficha_do_plano, pelo plano dele."""
    vetores = indice(con)
    consulta = embedar([relato])[0]
    fichas = [dict(f) for f in con.execute("SELECT * FROM planos_fichas")]
    for f in fichas:
        f["cosseno"] = round(cosseno(consulta, vetores[id_da_ficha(f["plano"])]), 3)
    return sorted(fichas, key=lambda f: f["cosseno"], reverse=True)[:top]


def buscar(con: sqlite3.Connection, termos: list[str], relato: str | None = None, top: int = 3,
           modo: str = "hibrida", incluir_revogados: bool | None = None,
           desempatar_por_data: bool | None = None) -> list[dict]:
    """Recupera os guias para um relato. `modo`: "hibrida" (vetores + palavra, por RRF) ou
    "vetorial" (só vetores; existe para a medição). A consulta embedada é o RELATO do cliente, e
    não os termos da triagem: o vetor foi feito para frases; os termos alimentam a busca por palavra.

    Cada resultado traz o mesmo que db.buscar_kb, mais `cosseno` e `busca`. O `score` é o cosseno
    na escala do portão (escala()), e vale 0,4 do que valeria se o relato cai numa ressalva."""
    try:
        vetores = indice(con)
        consulta = embedar([relato or " ".join(str(t) for t in termos)])[0]
    except Exception as e:                         # noqa: BLE001: qualquer falha do índice
        palavra = db.buscar_kb(con, termos, top=top, relato=relato, incluir_revogados=incluir_revogados,
                               desempatar_por_data=desempatar_por_data)
        for r in palavra:
            r["busca"] = "palavra"
            r["aviso_busca"] = f"busca vetorial indisponível ({type(e).__name__}): usada a busca por palavra"
        return palavra

    if incluir_revogados is None:
        incluir_revogados = not db.FILTRAR_REVOGADOS
    if desempatar_por_data is None:
        desempatar_por_data = db.DESEMPATAR_POR_DATA
    todos = con.execute("SELECT * FROM kb_artigos").fetchall()
    candidatos = [a for a in todos if incluir_revogados or a["revogado_por"] is None]
    mais_nova = db._mais_nova(candidatos)
    superadas = [a for a in candidatos if mais_nova[db._procedimento(a["id"])]["id"] != a["id"]]
    elegiveis = [a for a in candidatos if a not in superadas] if desempatar_por_data else candidatos
    cos = {a["id"]: cosseno(consulta, vetores[a["id"]]) for a in elegiveis}
    ordem_vetor = sorted(cos, key=cos.get, reverse=True)

    contribuicao = {kb_id: 1 / (K_RRF + i) for i, kb_id in enumerate(ordem_vetor, start=1)}
    if modo == "hibrida":
        palavra = db.buscar_kb(con, termos, top=len(todos), relato=relato,
                               incluir_revogados=incluir_revogados, desempatar_por_data=desempatar_por_data)
        for i, r in enumerate(palavra, start=1):
            contribuicao[r["kb_id"]] += 1 / (K_RRF + i)
    elif modo != "vetorial":
        raise ValueError(f"modo desconhecido: {modo!r}")

    contexto = db._contexto(relato, termos)
    descartadas = {}                  # guia que ficou -> as versões antigas que também casavam
    if desempatar_por_data:
        for a in superadas:
            if cosseno(consulta, vetores[a["id"]]) >= LIMIAR_COSSENO:
                descartadas.setdefault(mais_nova[db._procedimento(a["id"])]["id"], []).append(
                    {"kb_id": a["id"], "data_publicacao": a["data_publicacao"]})

    por_id = {a["id"]: a for a in elegiveis}
    resultados = []
    for kb_id in sorted(contribuicao, key=lambda k: (contribuicao[k], cos[k]), reverse=True)[:top]:
        a = por_id[kb_id]
        score = escala(cos[kb_id])
        ressalva = db._ressalva(a, contexto)
        if ressalva:
            score = round(score * db.REDUTOR, 2)
        r = {"kb_id": kb_id, "titulo": a["titulo"], "score": score, "cosseno": round(cos[kb_id], 3),
             "causa": a["causa"], "solucao": a["solucao"], "acao_padrao": a["acao_padrao"],
             "time_destino": a["time_destino"], "busca": modo}
        if ressalva:
            r["ressalva"] = (f"este procedimento NÃO cobre o caso relatado "
                             f"('{ressalva}'): o score foi reduzido")
        if kb_id in descartadas:
            r["data_publicacao"] = a["data_publicacao"]
            r["versoes_descartadas"] = descartadas[kb_id]
        resultados.append(r)
    return resultados


# ------------------------------------------------------------------ o trace (20/11/2026)
# No fim do arquivo para não deslocar as linhas citadas nos docs (docs/model-card.md e docs/rag.md).
import telemetria  # noqa: E402


def _embeddings(client, textos: list[str]):
    """Uma chamada à API de embedding, num span `embeddings` (Parte 3, §4.2), com o modelo e os tokens."""
    with telemetria.span_filho(f"embeddings {MODELO_EMBEDDING}",
                               {"gen_ai.operation.name": "embeddings", "gen_ai.provider.name": telemetria.PROVEDOR,
                                "gen_ai.request.model": MODELO_EMBEDDING, "triagem.textos": len(textos)},
                               kind=telemetria.otel.SpanKind.CLIENT) as span:
        try:
            r = client.embeddings.create(model=MODELO_EMBEDDING, input=textos)
        except Exception as e:
            span.set_attribute("error.type", type(e).__name__)
            raise
        telemetria.atributos(span, {"gen_ai.usage.input_tokens": getattr(r.usage, "total_tokens", None)})
        return r


# ================================================================ A MEMÓRIA EPISÓDICA POR SEMELHANÇA (21/11/2026)
# Correção da devolutiva da Parte 2 (subcritério 4b): a episódica era lida só por consulta exata
# (o mesmo guia; o mesmo cliente e categoria), e um caso parecido com outro guia ou outro cliente
# nunca era lembrado. Aqui, a semelhança com o caso atual, por embedding (docs/memoria.md §3.1).
#
# O que é comparado: a DESCRIÇÃO ESTRUTURADA do caso (classe, categoria, título e causa do guia
# proposto, ação proposta), montada pelo código dos dois lados. O episódio não guarda o texto do
# cliente (decisão de privacidade, docs/memoria.md §1.3), e continua não guardando: a semelhança é a
# de situação, não a de relato. O vetor fica em `episodios_vetores`, refeito quando o texto ou o
# modelo mudam; nasce aqui, e o `recriar_banco` o derruba com as outras tabelas.
#
# Só informa, como o resto da episódica: o resultado vai à tela do H1 e nenhuma regra de decisão o lê.
# Quem chama trata a exceção do embedding (fail-open: a tela vai sem os parecidos e diz por quê).
LIMIAR_PARECIDO = 0.80    # NÃO calibrado: o mesmo número do portão, por falta de medição (AINDA NÃO MEDIDO)
TOP_PARECIDOS = 3

SQL_EPISODIOS_VETORES = """
CREATE TABLE IF NOT EXISTS episodios_vetores (
    episodio_id INTEGER PRIMARY KEY,
    texto_hash  TEXT NOT NULL,
    modelo      TEXT NOT NULL,
    vetor       TEXT NOT NULL
)"""


def texto_do_caso(classe: str | None, artigo, acao: str | None) -> str:
    """A descrição do caso que é embedada, igual para o caso atual e para o episódio. Só campos do
    sistema: nada do relato, do log anexado nem do que o modelo redigiu."""
    return (f"Classe {classe or 'sem triagem'}. Categoria {artigo['categoria']}. {artigo['titulo']}. "
            f"{artigo['causa']} Ação proposta: {acao or 'nenhuma'}.")


def precedentes_parecidos(con: sqlite3.Connection, classe: str | None, artigo, acao: str | None,
                          cliente_id: str | None, agora=None, top: int = TOP_PARECIDOS,
                          limiar: float = LIMIAR_PARECIDO) -> list[dict]:
    """Os episódios mais parecidos com o caso atual, de OUTRO guia (os do mesmo guia já estão na
    contagem exata de db.precedentes) e fora da lista do mesmo cliente e categoria (que já aparece).
    Só os que passam de `limiar` no cosseno, no máximo `top`, do mais parecido ao menos. Respeita o
    decaimento de db.py: o que passou de EPISODIO_MAX_DIAS não é lido, e o que passou de
    EPISODIO_RECENTE_DIAS vem marcado como antigo. Levanta exceção se o embedding falhar."""
    from datetime import datetime
    agora = agora or datetime.now().astimezone()
    con.execute(SQL_EPISODIOS_VETORES)
    candidatos = []
    for ep in con.execute("""SELECT e.*, a.titulo, a.causa, a.categoria AS categoria_do_guia
                               FROM episodios e JOIN kb_artigos a ON a.id = e.kb_id
                               WHERE e.kb_id IS NOT NULL AND e.kb_id != ?""", (artigo["id"],)):
        if cliente_id and ep["cliente_id"] == cliente_id and ep["categoria"] == artigo["categoria"]:
            continue
        idade = db._idade_em_dias(ep["criado_em"], agora)
        if idade > db.EPISODIO_MAX_DIAS:
            continue
        texto = texto_do_caso(ep["classe"], {"categoria": ep["categoria_do_guia"], "titulo": ep["titulo"],
                                             "causa": ep["causa"]}, ep["acao_proposta"])
        candidatos.append((dict(ep), idade, texto, hashlib.sha1(texto.encode("utf-8")).hexdigest()))
    if not candidatos:
        return []
    guardados = {r["episodio_id"]: r for r in con.execute("SELECT * FROM episodios_vetores")}
    pendentes = []
    for ep, _, texto, h in candidatos:
        g = guardados.get(ep["id"])
        if g is None or g["texto_hash"] != h or g["modelo"] != MODELO_EMBEDDING:
            pendentes.append((ep["id"], texto, h))
    vetores = embedar([texto_do_caso(classe, artigo, acao)] + [t for _, t, _ in pendentes])
    for (episodio_id, _, h), v in zip(pendentes, vetores[1:]):
        con.execute("INSERT OR REPLACE INTO episodios_vetores VALUES (?, ?, ?, ?)",
                    (episodio_id, h, MODELO_EMBEDDING, json.dumps(v)))
    con.commit()
    do_banco = {r["episodio_id"]: json.loads(r["vetor"]) for r in con.execute("SELECT * FROM episodios_vetores")}
    parecidos = []
    for ep, idade, _, _ in candidatos:
        c = cosseno(vetores[0], do_banco[ep["id"]])
        if c >= limiar:
            parecidos.append({"ticket": ep["ticket_externo"], "em": ep["criado_em"][:10], "kb_id": ep["kb_id"],
                              "desfecho": ep["desfecho"], "veredito": ep["veredito"],
                              "antigo": idade > db.EPISODIO_RECENTE_DIAS, "cosseno": round(c, 3),
                              "por": f"parecido (cosseno {c:.2f}), outro guia"})
    parecidos.sort(key=lambda p: -p["cosseno"])
    return parecidos[:top]

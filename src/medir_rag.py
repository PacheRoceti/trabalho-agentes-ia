"""Medição da recuperação (docs/rag.md §4): chama a API de embedding e grava a saída em
logs/rag-medicao/. Não chama o modelo de chat.

    python src/medir_rag.py

    python src/medir_rag.py ressalva [ressalva-v2.md]   # só o bloco 5 (chama o modelo de chat)

Cinco blocos:
  1. acesso: a chave alcança o `mistral-embed`? dimensões, latência, limite de taxa;
  2. calibração do limiar do cosseno, só com as perguntas A* (com resposta) e N* (sem resposta);
  3. as perguntas do enunciado (P*) e as de exceção (X*) contra três buscas: a de hoje (palavra), só
     vetorial e híbrida; e as duas versões do guia de SSL sem curadoria;
  4. as ressalvas (coluna nao_cobre): o vetor separa a exceção do caso normal?
  4b. as fichas de plano (fonte E): a pergunta sobre um plano acha a ficha, e não um guia?
  6. (`triagem`) as perguntas passam pela TRIAGEM antes da busca: quantas sem resposta chegam a ela?
  5. (`ressalva`) o nó `conferir_ressalva`: o modelo lê as situações que o guia não cobre?
Os 8 casos pelo grafo são `python src/main.py --todos --auto-aprovar --rodada ...`.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db            # noqa: E402
import vetorial      # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")
SAIDA = RAIZ / "logs" / "rag-medicao"
SAIDA.mkdir(parents=True, exist_ok=True)
_texto: list[str] = []


def dizer(linha: str = "") -> None:
    print(linha)
    _texto.append(linha)


def com_intervalo(textos):
    """O plano gratuito aceita 60 requisições por minuto: uma chamada por segundo."""
    time.sleep(1.1)
    return vetorial._embedar_na_api(textos)


vetorial.EMBEDDER = com_intervalo
PERGUNTAS = json.loads((RAIZ / "dados" / "perguntas-rag.json").read_text(encoding="utf-8"))["perguntas"]
ASSUNTO = [p for p in PERGUNTAS if p["forma"] in ("assunto", "termo")]
FICHAS = [p for p in PERGUNTAS if p["forma"] == "ficha"]
resultado: dict = {}
_cache: dict[str, list[float]] = {}


def vetor_de(texto: str) -> list[float]:
    if texto not in _cache:
        _cache[texto] = vetorial.embedar([texto])[0]
    return _cache[texto]


def vetores_de(textos: list[str]) -> list[list[float]]:
    """Como vetor_de, em lote: só os textos ainda sem vetor vão à API."""
    faltam = [t for t in dict.fromkeys(textos) if t not in _cache]
    if faltam:
        _cache.update(zip(faltam, vetorial.embedar(faltam)))
    return [_cache[t] for t in textos]


def topo(con, p, modo):
    """O primeiro guia devolvido, como o sistema o veria. 'palavra' é a busca de hoje (Parte 1)."""
    termos = [p["texto"]]
    if modo == "palavra":
        r = db.buscar_kb(con, termos, relato=p["texto"])
    else:
        r = vetorial.buscar(con, termos, relato=p["texto"], modo=modo)
    return r[0] if r else None


def veredito(p, melhor) -> str:
    """certo / parcial / errado, pelas regras do docs/rag.md §4.3."""
    agiu = melhor is not None and melhor["score"] >= 0.5
    kb = melhor["kb_id"] if melhor else None
    if p["forma"] == "termo":
        return "certo" if kb == p["esperado"] else "errado"
    if p.get("excecao"):
        if p["ressalva_de"] == p["esperado"]:            # P6, X1, X3: o guia não cobre; não agir
            return "errado" if agiu else "certo"
        if agiu and kb == p["ressalva_de"]:              # P7, X2: agir sobre o guia errado
            return "errado"
        return "certo" if agiu and kb == p["esperado"] else "parcial"
    if p["esperado"] is None:                            # sem resposta na base
        return "errado" if agiu else "certo"
    return "certo" if agiu and kb == p["esperado"] else "errado"


def cos_guias(con, relato):
    v = vetorial.indice(con)
    q = vetor_de(relato)
    return sorted(((vetorial.cosseno(q, v[a["id"]]), a["id"])
                   for a in con.execute("SELECT * FROM kb_artigos WHERE revogado_por IS NULL")), reverse=True)


def main():
    db.recriar_banco()
    con = db.conectar()
    dizer(f"MEDIÇÃO DA RECUPERAÇÃO  modelo de embedding: {vetorial.MODELO_EMBEDDING}  "
          f"{time.strftime('%d/%m/%Y')}\n")

    # 1. acesso
    from openai import OpenAI
    c = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["OPENAI_API_KEY"], max_retries=0)
    t0 = time.monotonic()
    bruto = c.embeddings.with_raw_response.create(model=vetorial.MODELO_EMBEDDING,
                                                  input=["certificado ssl vencido", "acesso ssh recusado"])
    amostra = bruto.parse()
    limites = {k: v for k, v in bruto.headers.items() if "ratelimit-limit" in k.lower()}
    dizer("1. ACESSO")
    dizer(f"   funcionou em {time.monotonic() - t0:.2f}s; {len(amostra.data[0].embedding)} dimensões; "
          f"limite: {limites}\n")
    resultado["acesso"] = {"dimensoes": len(amostra.data[0].embedding), "limites": limites}

    # 2. calibração, só com A* e N*
    dizer("2. CALIBRAÇÃO DO LIMIAR (perguntas A* e N*; as P* e X* ficam de fora)")
    pos, neg = [], []
    for p in ASSUNTO:
        if p["id"].startswith("A"):
            por_guia = {k: v for v, k in cos_guias(con, p["texto"])}
            pos.append((round(por_guia[p["esperado"]], 3), p["id"]))
        elif p["id"].startswith("N"):
            neg.append((round(cos_guias(con, p["texto"])[0][0], 3), p["id"]))
    pior_acerto, pior_negativa = min(pos), max(neg)
    ponto_medio = round((pior_acerto[0] + pior_negativa[0]) / 2, 2)
    dizer(f"   cosseno com o guia certo, perguntas A*: de {pior_acerto[0]:.3f} ({pior_acerto[1]}) "
          f"a {max(pos)[0]:.3f} ({max(pos)[1]})")
    dizer(f"   cosseno do melhor guia, perguntas N* (sem resposta): de {min(neg)[0]:.3f} ({min(neg)[1]}) "
          f"a {pior_negativa[0]:.3f} ({pior_negativa[1]})")
    dizer(f"   ponto médio entre o pior acerto e a pior pergunta sem resposta: {ponto_medio}  "
          f"(LIMIAR_COSSENO no código: {vetorial.LIMIAR_COSSENO})")
    dizer(f"   folga: {pior_acerto[0] - pior_negativa[0]:.3f} entre o pior acerto e a pior negativa\n")
    dizer(f"   {len(pos)} perguntas com resposta (A*) e {len(neg)} sem resposta (N*). Erros por limiar, só com a busca:")
    dizer(f"   {'limiar':<8}{'acertos barrados':<20}perguntas sem resposta que passam")
    for t in (0.78, 0.79, 0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86):
        fn = [i for c, i in pos if c < t]
        fp = [i for c, i in neg if c >= t]
        dizer(f"   {t:<8}{len(fn):<20}{len(fp)}  {fp if len(fp) <= 6 else str(fp[:6]) + ' ...'}")
    dizer("")
    resultado["calibracao"] = {"acertos": pos, "negativas": neg, "ponto_medio": ponto_medio,
                               "limiar_no_codigo": vetorial.LIMIAR_COSSENO}

    # 3. as três buscas
    dizer("3. AS PERGUNTAS CONTRA AS TRÊS BUSCAS  (limiar do portão: 0,5; o termo da busca por palavra "
          "é a pergunta inteira; * = ressalva)")
    dizer(f"   {'#':<4}{'esperado':<10}{'palavra (hoje)':<26}{'só vetorial':<26}{'híbrida':<26}")
    linhas = []
    for p in ASSUNTO:
        celulas = []
        for modo in ("palavra", "vetorial", "hibrida"):
            m = topo(con, p, modo)
            v = veredito(p, m)
            ress = "*" if m and m.get("ressalva") else ""
            celulas.append(f"{(m['kb_id'] if m else '-')} {m['score'] if m else ''}{ress} {v}")
            linhas.append({"id": p["id"], "modo": modo, "kb_id": m["kb_id"] if m else None,
                           "score": m["score"] if m else None, "cosseno": m.get("cosseno") if m else None,
                           "ressalva": bool(m and m.get("ressalva")), "veredito": v})
        dizer(f"   {p['id']:<4}{(p['esperado'] or '-'):<10}" + "".join(f"{x:<26}" for x in celulas))
    dizer("")
    for grupo, filtro in (("enunciado (P1, P2, P6, P7, P8, P10)",
                           lambda i: i in ("P1", "P2", "P6", "P7", "P8", "P10")),
                          ("exceções escritas depois (X*)", lambda i: i.startswith("X")),
                          ("controles em que o guia cobre o caso (C*)", lambda i: i.startswith("C")),
                          ("calibração (A*, N*), dentro da amostra", lambda i: i[0] in "AN")):
        dizer(f"   {grupo}:")
        for modo in ("palavra", "vetorial", "hibrida"):
            c2 = {"certo": 0, "parcial": 0, "errado": 0}
            for l in linhas:
                if l["modo"] == modo and filtro(l["id"]):
                    c2[l["veredito"]] += 1
            dizer(f"      {modo:<9} certo {c2['certo']}  parcial {c2['parcial']}  errado {c2['errado']}")
    resultado["perguntas"] = linhas
    dizer("")

    dizer("   As duas versões do guia de SSL, SEM curadoria, só vetorial (a busca vetorial acha as duas?)")
    for pid in ("P1", "A1"):
        p = next(x for x in PERGUNTAS if x["id"] == pid)
        r = vetorial.buscar(con, [p["texto"]], relato=p["texto"], modo="vetorial", top=2,
                            incluir_revogados=True, desempatar_por_data=False)
        dizer(f"   {pid}: " + "; ".join(f"{x['kb_id']} cosseno {x['cosseno']}" for x in r))
        resultado.setdefault("sem_curadoria", {})[pid] = [(x["kb_id"], x["cosseno"]) for x in r]
    dizer("")

    # 4. as ressalvas
    dizer("4. AS RESSALVAS (nao_cobre): o vetor separa a exceção do caso normal?")
    dizer("   por frase: cosseno das perguntas que SÃO a exceção, e das que o guia cobre")
    descritivas = {"intermitente": "O problema é intermitente, vai e volta.",
                   "as vezes": "O problema acontece às vezes.",
                   "de vez em quando": "O problema acontece de vez em quando.",
                   "oscila": "O serviço oscila.", "ssh": "O acesso é por SSH, login no servidor."}
    for a in con.execute("SELECT * FROM kb_artigos WHERE revogado_por IS NULL AND nao_cobre != ''").fetchall():
        excecoes = [p for p in ASSUNTO if p.get("ressalva_de") == a["id"]]
        normais = [p for p in ASSUNTO if p.get("esperado") == a["id"] and not p.get("excecao")
                   and p["forma"] == "assunto"]
        if not excecoes or not normais:
            dizer(f"   {a['id']}: sem exceção ou sem caso normal no conjunto: não medido")
            continue
        for frase in [f.strip() for f in a["nao_cobre"].split(";") if f.strip()]:
            for forma, texto_f in (("pergunta inteira x frase", frase),
                                   ("pergunta inteira x frase descrita", descritivas.get(frase, f"O problema descrito é: {frase}.")),
                                   ("melhor janela de 1 a 4 palavras x frase", None)):
                vf = vetor_de(texto_f or frase)

                def sim(p):
                    if texto_f is not None:
                        return vetorial.cosseno(vetor_de(p["texto"]), vf)
                    pal = re.findall(r"\w+", p["texto"].lower())
                    js = [" ".join(pal[i:i + n]) for n in range(1, 5) for i in range(len(pal) - n + 1)]
                    return max(vetorial.cosseno(v, vf) for v in vetores_de(js))
                pe, pn = [sim(p) for p in excecoes], [sim(p) for p in normais]
                folga = min(pe) - max(pn)
                dizer(f"   {a['id']} '{frase}' [{forma}]: exceções {min(pe):.2f}-{max(pe):.2f}  "
                      f"casos normais {min(pn):.2f}-{max(pn):.2f}  -> "
                      + ("separa" if folga > 0 else "NÃO separa") + f" (folga {folga:+.2f})")
                resultado.setdefault("ressalvas", []).append(
                    {"kb_id": a["id"], "frase": frase, "forma": forma, "excecoes": pe, "normais": pn,
                     "folga": folga})
    dizer("")
    dizer("4b. AS FICHAS DE PLANO (fonte E): a pergunta sobre um plano acha a ficha, e não um guia?")
    fichas_ok = 0
    for p in FICHAS:
        f = vetorial.buscar_fichas(con, p["texto"], top=2)
        guia = vetorial.buscar(con, [p["texto"]], relato=p["texto"], modo="vetorial", top=1)[0]
        ok = f[0]["plano"] == p["esperado_ficha"]
        fichas_ok += ok
        dizer(f"   {p['id']:<4}esperada {p['esperado_ficha']:<20}1ª ficha {f[0]['plano']} ({f[0]['cosseno']}), "
              f"2ª {f[1]['plano']} ({f[1]['cosseno']})  {'certo' if ok else 'ERRADO'}; "
              f"melhor guia {guia['kb_id']} com score {guia['score']} ({'não age' if guia['score'] < 0.5 else 'AGIRIA'})")
        resultado.setdefault("fichas", []).append({"id": p["id"], "ficha": f[0]["plano"], "cosseno": f[0]["cosseno"],
                                                   "segunda": f[1]["cosseno"], "certo": ok,
                                                   "guia": guia["kb_id"], "score_guia": guia["score"]})
    dizer(f"   {fichas_ok} de {len(FICHAS)} fichas achadas")
    dizer(f"\ntokens de embedding gastos nesta medição: {vetorial.TOKENS_EMBEDDING}")
    resultado["tokens_embedding"] = vetorial.TOKENS_EMBEDDING
    (SAIDA / "medicao.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / "saida.txt").write_text("\n".join(_texto) + "\n", encoding="utf-8")


REPETICOES = 3
CONTROLES = ("P2", "A2", "A4", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "A8", "A14", "A15")   # o guia cobre o caso


def medir_ressalva(prompt: str | None = None):
    """Bloco 5: o nó `conferir_ressalva` (src/grafo.py) contra as perguntas de exceção e os
    controles. Chama o modelo de chat (o do .env) e a API de embedding. Duas leituras:
      a) o nó isolado: dado o relato e o guia, o modelo diz que cai na ressalva? (3 repetições);
      b) o sistema: busca vetorial, a aresta que decide se o nó roda, o nó, e o veredito final."""
    os.environ.setdefault("CHECKPOINT_DB", ":memory:")
    import grafo
    from agente import criar_cliente
    if prompt:                                   # medir um prompt que não é o em uso (a comparação v1 x v2)
        grafo.PROMPT_RESSALVA = grafo.PROMPTS / prompt
    nome = grafo.PROMPT_RESSALVA.stem
    db.recriar_banco()
    con = db.conectar()
    modelo = os.environ["LLM_MODELO"]
    ctx = grafo.Contexto(client=criar_cliente(), con=con, verbose=False)
    ticket = {"id": "MEDICAO", "cliente": "(medição)", "plano": "-", "anexo_log": None, "historico_cliente": []}
    dizer(f"5. A RESSALVA LIDA PELO MODELO  prompt: {grafo.PROMPT_RESSALVA.name}  modelo de chat: {modelo}  "
          f"{time.strftime('%d/%m/%Y')}  "
          f"{REPETICOES} repetições, temperature=0\n")

    def julgar(p, kb_id, score=0.7):
        """Uma chamada ao nó, como o grafo a faria: o guia em primeiro lugar, com score acima do limiar."""
        a = db.buscar_artigo(con, kb_id)
        frases = [f.strip() for f in a["nao_cobre"].split(";") if f.strip()]
        melhor = {"kb_id": kb_id, "titulo": a["titulo"], "causa": a["causa"], "score": score}
        state = {"id_ticket": "MEDICAO", "modelo": modelo, "temperatura": 0.0, "texto": p["texto"],
                 "ticket": ticket, "candidatos": [melhor], "ressalvas_do_melhor": frases, "passos": []}
        time.sleep(1.1)
        out = grafo.conferir_ressalva(state, ctx)
        if out.get("termino"):
            return None, out["motivo"]
        passo = out["passos"][0]["resultado"]
        return passo["cai_na_ressalva"], passo["frase"] or passo["motivo"]

    grupos = [("exceção", [p for p in ASSUNTO if p.get("excecao")]),
              ("controle", [p for p in ASSUNTO if p["id"] in CONTROLES])]
    linhas, resumo = [], {}
    dizer("   a) o nó isolado: o relato cai numa ressalva do guia?  (esperado: exceção = sim, controle = não)")
    for grupo, perguntas in grupos:
        for p in perguntas:
            kb = p["ressalva_de"] if grupo == "exceção" else p["esperado"]
            respostas = [julgar(p, kb) for _ in range(REPETICOES)]
            votos = [r[0] for r in respostas]
            esperado = grupo == "exceção"
            certos = sum(v is esperado for v in votos)
            literal = db._ressalva(db.buscar_artigo(con, kb), db._contexto(p["texto"], [])) is not None
            dizer(f"   {p['id']:<4}{grupo:<9}guia {kb:<7}respostas {['sim' if v else 'não' if v is False else 'erro' for v in votos]}"
                  f"  certas {certos}/{REPETICOES}" + ("  (a frase literal já a pegaria)" if literal else ""))
            linhas.append({"id": p["id"], "grupo": grupo, "kb": kb, "votos": votos, "certas": certos,
                           "frases": [r[1] for r in respostas], "literal": literal})
            r = resumo.setdefault(grupo, [0, 0])
            r[0] += certos
            r[1] += REPETICOES
    dizer("")
    for grupo, (c, t) in resumo.items():
        dizer(f"   {grupo}: {c} de {t} respostas certas")
    resultado["ressalva_no"] = linhas

    dizer("\n   b) o sistema inteiro (busca vetorial, aresta, nó): o veredito de cada pergunta")
    dizer(f"   {'#':<4}{'melhor guia':<22}{'nó rodou?':<12}{'depois do nó':<18}veredito (antes -> depois)")
    sistema = []
    for p in ASSUNTO:
        if p["forma"] != "assunto" or not (p.get("excecao") or p["id"] in ("P1",) + CONTROLES):
            continue
        r = vetorial.buscar(con, [p["texto"]], relato=p["texto"], modo="vetorial")
        melhor = dict(r[0])
        antes = veredito(p, melhor)
        frases = [f.strip() for f in db.buscar_artigo(con, melhor["kb_id"])["nao_cobre"].split(";") if f.strip()]
        rodou = bool(melhor["score"] >= 0.5 and not melhor.get("ressalva") and frases)
        cai = None
        if rodou:
            cai, _ = julgar(p, melhor["kb_id"], score=melhor["score"])
            if cai:
                melhor["score"] = round(melhor["score"] * db.REDUTOR, 2)
                melhor["ressalva"] = "modelo"
        depois = veredito(p, melhor)
        dizer(f"   {p['id']:<4}{melhor['kb_id'] + ' ' + str(r[0]['score']):<22}{('sim' if rodou else 'não'):<12}"
              f"{('cai' if cai else 'não cai') if rodou else '-':<18}{antes} -> {depois}")
        sistema.append({"id": p["id"], "kb_id": melhor["kb_id"], "rodou": rodou, "cai": cai,
                        "antes": antes, "depois": depois})
    resultado["ressalva_sistema"] = sistema
    dizer("")
    for v in ("certo", "parcial", "errado"):
        dizer(f"   {v}: antes do nó {sum(x['antes'] == v for x in sistema)}, depois do nó "
              f"{sum(x['depois'] == v for x in sistema)}")
    dizer(f"\ntokens de embedding: {vetorial.TOKENS_EMBEDDING}")
    (SAIDA / f"{nome}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / f"{nome}.txt").write_text("\n".join(_texto) + "\n", encoding="utf-8")


def medir_triagem():
    """Bloco 6: as perguntas passam pela triagem (nó `triagem`, src/grafo.py) antes da busca. No
    sistema, só a classe "tecnico" chega à busca; as outras vão à fila comercial, ao pedido de
    informação ou à fila humana. Mede quantas perguntas sem resposta chegam à busca, e se a triagem
    desvia perguntas que tinham resposta."""
    os.environ.setdefault("CHECKPOINT_DB", ":memory:")
    import grafo
    from agente import criar_cliente
    db.recriar_banco()
    con = db.conectar()
    modelo = os.environ["LLM_MODELO"]
    ctx = grafo.Contexto(client=criar_cliente(), con=con, verbose=False)
    ticket = {"id": "MEDICAO", "cliente": "(medição)", "plano": "-", "anexo_log": None, "historico_cliente": []}
    dizer(f"6. A TRIAGEM ANTES DA BUSCA  modelo de chat: {modelo}  {time.strftime('%d/%m/%Y')}  1 execução por pergunta, "
          f"temperature=0, limiar do cosseno {vetorial.LIMIAR_COSSENO}\n")
    linhas = []
    for p in ASSUNTO:
        if p["forma"] != "assunto":
            continue
        state = {"id_ticket": "MEDICAO", "modelo": modelo, "temperatura": 0.0, "texto": p["texto"],
                 "ticket": ticket, "passos": []}
        time.sleep(1.1)
        out = grafo.triagem(state, ctx)
        classe = out.get("classe")
        por_guia = {k: v for v, k in cos_guias(con, p["texto"])}
        topo_id = max(por_guia, key=por_guia.get)
        linhas.append({"id": p["id"], "classe": classe, "diverge": out.get("log_diverge"),
                       "esperado": p.get("esperado"), "topo": topo_id, "cos_topo": round(por_guia[topo_id], 3),
                       "cos_esperado": round(por_guia[p["esperado"]], 3) if p.get("esperado") in por_guia else None,
                       "erro": out.get("motivo") if classe is None else None})
    sem = [l for l in linhas if l["id"].startswith("N")]
    com = [l for l in linhas if l["id"][0] in "AC" or l["id"] in ("P1", "P2", "P6", "P7", "P10")]
    contagem = {}
    for l in sem:
        contagem[l["classe"]] = contagem.get(l["classe"], 0) + 1
    dizer("   a) perguntas SEM resposta: a classe que a triagem deu")
    for l in sem:
        chega = l["classe"] == "tecnico"
        dizer(f"   {l['id']:<4}{str(l['classe']):<16}{'CHEGA à busca' if chega else 'não chega':<15}"
              f"melhor guia {l['topo']} cosseno {l['cos_topo']}" + ("  (age no limiar)" if chega and l["cos_topo"] >= vetorial.LIMIAR_COSSENO else ""))
    dizer(f"   classes: {contagem}")
    chegam = [l for l in sem if l["classe"] == "tecnico"]
    dizer(f"   chegam à busca: {len(chegam)} de {len(sem)}; das que chegam, agem (cosseno do melhor guia >= "
          f"{vetorial.LIMIAR_COSSENO}): {sum(l['cos_topo'] >= vetorial.LIMIAR_COSSENO for l in chegam)}\n")
    dizer("   b) perguntas COM resposta (A*, C*, P1, P2, P6, P7, P10): a triagem as desvia da busca?")
    desviadas = [l for l in com if l["id"] != "P10" and l["classe"] != "tecnico"]
    for l in com:
        if l["classe"] != "tecnico":
            dizer(f"   {l['id']:<4}{str(l['classe']):<16}desviada da busca" + ("  (P10 não tem resposta: o desvio é o certo)" if l["id"] == "P10" else ""))
    dizer(f"   desviadas indevidamente: {len(desviadas)} de {len([l for l in com if l['id'] != 'P10'])}\n")
    dizer("   c) erros por limiar, com a triagem na frente (acerto barrado = desviado pela triagem OU abaixo do limiar)")
    A = [l for l in linhas if l["id"].startswith("A")]
    dizer(f"   {'limiar':<8}{'só a busca':<28}{'com a triagem':<28}")
    tabela = []
    for t in (0.78, 0.79, 0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86):
        fn_b = sum(1 for l in A if (l["cos_esperado"] or 0) < t)
        fp_b = sum(1 for l in sem if l["cos_topo"] >= t)
        fn_t = sum(1 for l in A if l["classe"] != "tecnico" or (l["cos_esperado"] or 0) < t)
        fp_t = sum(1 for l in sem if l["classe"] == "tecnico" and l["cos_topo"] >= t)
        dizer(f"   {t:<8}{f'{fn_b} de {len(A)} barrados, {fp_b} de {len(sem)} agem':<28}{f'{fn_t} de {len(A)} barrados, {fp_t} de {len(sem)} agem':<28}")
        tabela.append({"limiar": t, "fn_busca": fn_b, "fp_busca": fp_b, "fn_triagem": fn_t, "fp_triagem": fp_t})
    resultado["triagem"] = {"linhas": linhas, "tabela": tabela}
    (SAIDA / "triagem.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / "triagem.txt").write_text("\n".join(_texto) + "\n", encoding="utf-8")


# Perguntas do bloco 7, sobre o KB-102 ("ssh"). As X12, X13, C9 e C10 foram escritas em 11/10/2026
# DEPOIS do ressalva-v3.md e ANTES de medir, sem repetir o exemplo do prompt ("entrar no servidor
# pelo terminal"): X5 e X7 são parecidas com esse exemplo, e sozinhas não provariam nada.
FATOS_EXCECOES = ("P7", "X2", "X5", "X6", "X7")
FATOS_CONTROLES = ("P2", "A2", "C2", "C3", "C4")
FATOS_NOVAS = [
    {"id": "X12", "grupo": "exceção", "texto": "Não consigo conectar no servidor com o PuTTY, aparece acesso negado."},
    {"id": "X13", "grupo": "exceção", "texto": "A minha chave pública deixou de ser aceita pelo servidor, dá permission denied."},
    {"id": "C9", "grupo": "controle", "texto": "Depois de restaurar o backup, o sistema não consegue gravar na pasta de anexos: permissão negada."},
    {"id": "C10", "grupo": "controle", "texto": "O site não deixa enviar imagens, aparece erro de permissão na pasta de mídia."},
]


def medir_fatos(prompt: str | None = None):
    """Bloco 7: a memória semântica no nó `conferir_ressalva`. O guia é o KB-102, que declara não
    cobrir "ssh" e que o ressalva-v1 não lê (0 de 15). Cada pergunta passa pelo nó em três
    condições: sem fato, com o fato acesso=ssh e com o fato acesso=painel. Esperado: a exceção é
    barrada; o controle NÃO é barrado, com qualquer fato (o fato sozinho não basta)."""
    os.environ.setdefault("CHECKPOINT_DB", ":memory:")
    import grafo
    from agente import criar_cliente
    if prompt:
        grafo.PROMPT_RESSALVA = grafo.PROMPTS / prompt
    nome = grafo.PROMPT_RESSALVA.stem
    db.recriar_banco()
    con = db.conectar()
    modelo = os.environ["LLM_MODELO"]
    ctx = grafo.Contexto(client=criar_cliente(), con=con, verbose=False)
    a = db.buscar_artigo(con, "KB-102")
    frases = [f.strip() for f in a["nao_cobre"].split(";") if f.strip()]
    # um cliente do seed para cada condição: o fato é lido do banco, como no grafo
    clientes = {"sem fato": "CLI-01", "acesso=ssh": "CLI-02", "acesso=painel": "CLI-03"}
    db.registrar_fato(con, "CLI-02", "acesso", "ssh", por="medição")
    db.registrar_fato(con, "CLI-03", "acesso", "painel", por="medição")
    dizer(f"7. OS FATOS DO CLIENTE NO NÓ DA RESSALVA  prompt: {grafo.PROMPT_RESSALVA.name}  modelo de chat: {modelo}  "
          f"{time.strftime('%d/%m/%Y')}  guia KB-102 (não cobre: {', '.join(frases)})  "
          f"{REPETICOES} repetições, temperature=0\n")
    perguntas = ([{**p, "grupo": "exceção"} for p in ASSUNTO if p["id"] in FATOS_EXCECOES]
                 + [{**p, "grupo": "controle"} for p in ASSUNTO if p["id"] in FATOS_CONTROLES] + FATOS_NOVAS)
    perguntas.sort(key=lambda p: p["grupo"] != "exceção")
    linhas, resumo = [], {}
    dizer(f"   {'#':<5}{'grupo':<10}" + "".join(f"{c:<26}" for c in clientes) + "(respostas do nó: cai na ressalva?)")
    for p in perguntas:
        esperado, linha = p["grupo"] == "exceção", {"id": p["id"], "grupo": p["grupo"], "texto": p["texto"]}
        celulas = []
        for condicao, cliente in clientes.items():
            ticket = {"id": "MEDICAO", "cliente": "(medição)", "plano": "-", "anexo_log": None,
                      "historico_cliente": [], "_cliente_id": cliente}
            votos = []
            for _ in range(REPETICOES):
                state = {"id_ticket": "MEDICAO", "modelo": modelo, "temperatura": 0.0, "texto": p["texto"],
                         "ticket": ticket, "ressalvas_do_melhor": frases, "passos": [],
                         "candidatos": [{"kb_id": "KB-102", "titulo": a["titulo"], "causa": a["causa"], "score": 0.7}]}
                time.sleep(1.1)
                out = grafo.conferir_ressalva(state, ctx)
                votos.append(None if out.get("termino") else out["passos"][0]["resultado"]["cai_na_ressalva"])
            certos = sum(v is esperado for v in votos)
            linha[condicao] = {"votos": votos, "certas": certos}
            r = resumo.setdefault((p["grupo"], condicao), [0, 0])
            r[0] += certos
            r[1] += REPETICOES
            celulas.append(f"{'/'.join('sim' if v else 'não' if v is False else 'erro' for v in votos)} ({certos}/{REPETICOES})")
        dizer(f"   {p['id']:<5}{p['grupo']:<10}" + "".join(f"{c:<26}" for c in celulas))
        linhas.append(linha)
    dizer("\n   respostas certas (exceção = sim, controle = não):")
    for grupo in ("exceção", "controle"):
        dizer(f"   {grupo:<10}" + "   ".join(f"{c}: {resumo[(grupo, c)][0]} de {resumo[(grupo, c)][1]}" for c in clientes))
    resultado["fatos"] = linhas
    (SAIDA / f"fatos-{nome}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    (SAIDA / f"fatos-{nome}.txt").write_text("\n".join(_texto) + "\n", encoding="utf-8")
    db.recriar_banco()                           # os fatos da medição não ficam no banco


if __name__ == "__main__":
    if sys.argv[1:2] == ["fatos"]:
        medir_fatos(sys.argv[2] if len(sys.argv) > 2 else None)
    elif sys.argv[1:2] == ["ressalva"]:
        medir_ressalva(sys.argv[2] if len(sys.argv) > 2 else None)
    elif sys.argv[1:2] == ["triagem"]:
        medir_triagem()
    else:
        main()

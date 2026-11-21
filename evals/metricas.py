"""As métricas de observabilidade sobre execuções reais (Parte 3, §4.3), lidas dos TRACES das rodadas.

    python -m evals.metricas evals/resultados/<rodada-A> [evals/resultados/<rodada-B> ...]

Só lê; não chama a API. Para cada versão (o atributo `triagem.versao` da raiz de cada trace, e não o
nome da pasta: um número que mistura versões soma sistemas diferentes):

- latência p50 e p95 da execução: a duração do span raiz `invoke_agent`. Com o ritmo da suíte
  (docs/evals.md §4.2), parte dela é espera pelo limite da API; a linha "sem a espera do ritmo"
  desconta o `espera_do_ritmo_s` que o resultado.json registra para a execução;
- custo por execução: o `triagem.custo_usd` da raiz (chat e embedding, a preço de lista);
- a distribuição dos motivos de término: o `triagem.termino` da raiz;
- a taxa de erro por ferramenta: os spans `execute_tool` com status de erro, por `gen_ai.tool.name`,
  e, à parte, as chamadas ao modelo (`chat`) e à API de embedding (`embeddings`) com erro.

E, desde 21/11/2026, os sinais da qualidade (docs/observabilidade.md §3 e §5):

- o SLI de qualidade: das execuções cujo chamado está em dados/gabarito.json (as válidas), a fração
  com `triagem.termino` = respondeu E `triagem.desfecho` igual à `acao` do gabarito (as boas);
- a distribuição dos desfechos (`triagem.desfecho`), e a fila humana gravada contra a pedida;
- o melhor score da busca (`triagem.kb_recuperados`) logo acima do limiar, a menos de 0,05 dele;
- as redações recusadas pelo `validar` (o span do nó com `triagem.erro`).

Percentil pelo método do posto mais próximo, sem interpolação: com 44 execuções, o p95 é a 42ª.
"""
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from evals import RAIZ
from ferramentas import LIMIAR_CONFIANCA

FAIXA_DO_LIMIAR = 0.05      # "logo acima do limiar": score em [0,50; 0,55)


def _instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def _duracao_s(span: dict) -> float:
    return (_instante(span["end_time"]) - _instante(span["start_time"])).total_seconds()


def percentil(valores: list[float], p: float) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    return ordenados[max(1, math.ceil(p / 100 * len(ordenados))) - 1]


def ler_rodada(pasta: Path) -> list[dict]:
    """Uma linha por execução nova (a raiz que não é retomada), com os spans do trace dela."""
    resultado = json.loads((pasta / "resultado.json").read_text(encoding="utf-8"))
    espera = {(e["repeticao"], e["id"]): e.get("espera_do_ritmo_s", 0.0) for e in resultado["execucoes"]}
    execucoes = []
    for arquivo in sorted(pasta.glob("logs/rep-*/*.trace.jsonl")):
        rep = int(arquivo.parent.name.split("-")[1])
        spans = [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]
        por_trace = defaultdict(list)
        for s in spans:
            por_trace[s["context"]["trace_id"]].append(s)
        # A suíte pode reexecutar um caso depois de um 429: vale a última execução, a que foi conferida.
        raizes = sorted((s for s in spans if not s.get("parent_id")
                         and not s["attributes"].get("triagem.retomada")), key=lambda s: s["start_time"])
        if not raizes:
            continue
        raiz = raizes[-1]
        a = raiz["attributes"]
        id_ticket = a.get("gen_ai.conversation.id")
        execucoes.append({
            "rodada": pasta.name, "id": id_ticket, "repeticao": rep, "versao": a.get("triagem.versao"),
            "termino": a.get("triagem.termino"), "custo_usd": a.get("triagem.custo_usd"),
            "segundos": _duracao_s(raiz), "espera_do_ritmo_s": espera.get((rep, id_ticket), 0.0),
            "spans": por_trace[raiz["context"]["trace_id"]],
            "desfecho": a.get("triagem.desfecho"),
            "melhor_score": max((float(k.split("=")[1]) for k in a.get("triagem.kb_recuperados") or []), default=None),
        })
    return execucoes


def calcular(execucoes: list[dict]) -> dict:
    latencia = [e["segundos"] for e in execucoes]
    sem_espera = [max(0.0, e["segundos"] - (e["espera_do_ritmo_s"] or 0.0)) for e in execucoes]
    custos = [e["custo_usd"] for e in execucoes if e["custo_usd"] is not None]
    ferramentas = defaultdict(lambda: [0, 0])        # nome -> [execuções, com erro]
    chat, embeddings, recusas_do_validar = [0, 0], [0, 0], 0
    for e in execucoes:
        for s in e["spans"]:
            erro = s.get("status", {}).get("status_code") == "ERROR"
            if s["name"].startswith("execute_tool "):
                f = ferramentas[s["attributes"].get("gen_ai.tool.name", s["name"][13:])]
                f[0] += 1
                f[1] += erro
            elif s["name"].startswith("chat "):
                chat[0] += 1
                chat[1] += erro
            elif s["name"].startswith("embeddings "):
                embeddings[0] += 1
                embeddings[1] += erro or bool(s["attributes"].get("error.type"))
            elif s["attributes"].get("triagem.no") == "validar" and s["attributes"].get("triagem.erro"):
                recusas_do_validar += 1
    gabarito = json.loads((RAIZ / "dados" / "gabarito.json").read_text(encoding="utf-8"))
    validas = [e for e in execucoes if e["id"] in gabarito]
    boas = [e for e in validas if e["termino"] == "respondeu" and e["desfecho"] == gabarito[e["id"]]["acao"]]
    com_busca = [e["melhor_score"] for e in execucoes if e["melhor_score"] is not None]
    return {
        "execucoes": len(execucoes),
        "latencia_p50_s": percentil(latencia, 50), "latencia_p95_s": percentil(latencia, 95),
        "sem_espera_p50_s": percentil(sem_espera, 50), "sem_espera_p95_s": percentil(sem_espera, 95),
        "custo_medio_usd": sum(custos) / len(custos) if custos else None,
        "custo_total_usd": sum(custos) if custos else None,
        "terminos": dict(Counter(e["termino"] for e in execucoes).most_common()),
        "erro_por_ferramenta": {k: {"chamadas": v[0], "com_erro": v[1], "taxa": v[1] / v[0]}
                                for k, v in sorted(ferramentas.items())},
        "chat": {"chamadas": chat[0], "recusadas": chat[1], "taxa": chat[1] / chat[0] if chat[0] else None},
        "embeddings": {"chamadas": embeddings[0], "com_erro": embeddings[1]},
        "sli_qualidade": {"boas": len(boas), "validas": len(validas),
                          "fracao": len(boas) / len(validas) if validas else None,
                          "ruins": sorted(e["id"] for e in validas if e not in boas)},
        "desfechos": dict(Counter(e["desfecho"] for e in execucoes).most_common()),
        "fila_humana": {"gravada": sum(e["desfecho"] == "fila_humana" for e in validas),
                        "pedida": sum(gabarito[e["id"]]["acao"] == "fila_humana" for e in validas)},
        "busca": {"com_busca": len(com_busca),
                  "logo_acima_do_limiar": sum(LIMIAR_CONFIANCA <= s < LIMIAR_CONFIANCA + FAIXA_DO_LIMIAR
                                              for s in com_busca),
                  "abaixo_do_limiar": sum(s < LIMIAR_CONFIANCA for s in com_busca)},
        "recusas_do_validar": recusas_do_validar,
    }


def imprimir(por_versao: dict[str, dict], rodadas: dict[str, list[str]]):
    for versao, m in por_versao.items():
        print(f"\nVERSÃO {versao}   {m['execucoes']} execuções   rodada(s): {', '.join(rodadas[versao])}")
        print(f"  latência da execução       p50 {m['latencia_p50_s']:6.1f} s   p95 {m['latencia_p95_s']:6.1f} s")
        print(f"    sem a espera do ritmo    p50 {m['sem_espera_p50_s']:6.1f} s   p95 {m['sem_espera_p95_s']:6.1f} s")
        if m["custo_medio_usd"] is not None:
            print(f"  custo por execução         US$ {m['custo_medio_usd']:.5f}   (total US$ {m['custo_total_usd']:.4f})")
        print("  motivo de término          " + "   ".join(f"{k} {v} ({100 * v / m['execucoes']:.0f}%)"
                                                       for k, v in m["terminos"].items()))
        print("  erro por ferramenta")
        for nome, f in m["erro_por_ferramenta"].items():
            print(f"    {nome:<28} {f['com_erro']:3d} de {f['chamadas']:3d}   {100 * f['taxa']:5.1f}%")
        c = m["chat"]
        if c["chamadas"]:
            print(f"    {'(modelo de chat)':<28} {c['recusadas']:3d} de {c['chamadas']:3d}   {100 * c['taxa']:5.1f}%"
                  "   recusadas pelo provedor (429) ou com erro")
        if m["embeddings"]["chamadas"]:
            print(f"    {'(API de embedding)':<28} {m['embeddings']['com_erro']:3d} de {m['embeddings']['chamadas']:3d}"
                  "          com erro: a busca recuou para a busca por palavra")
        q = m["sli_qualidade"]
        if q["validas"]:
            print(f"  SLI de qualidade           {q['boas']} de {q['validas']} = {100 * q['fracao']:.1f}%"
                  f"   (término respondeu e desfecho do gabarito)   fora: {', '.join(q['ruins']) or 'nenhuma'}")
        print("  desfecho                   " + "   ".join(f"{k} {v}" for k, v in m["desfechos"].items()))
        print(f"  fila humana                gravada {m['fila_humana']['gravada']}, o gabarito pede {m['fila_humana']['pedida']}")
        b = m["busca"]
        print(f"  melhor score da busca      {b['logo_acima_do_limiar']} de {b['com_busca']} logo acima do limiar "
              f"(< {LIMIAR_CONFIANCA + FAIXA_DO_LIMIAR:.2f}), {b['abaixo_do_limiar']} abaixo")
        print(f"  redações recusadas pelo validar   {m['recusas_do_validar']}")


def main_cli():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    execucoes, rodadas = [], defaultdict(list)
    for pasta in sys.argv[1:]:
        lidas = ler_rodada(Path(pasta))
        if not lidas:
            sys.exit(f"Nenhum trace em {pasta}/logs/rep-*/ (os traces existem desde a versão 1.0.0)")
        execucoes += lidas
        for v in {e["versao"] for e in lidas}:
            rodadas[v].append(Path(pasta).name)
    por_versao = {v: calcular([e for e in execucoes if e["versao"] == v])
                  for v in sorted({e["versao"] for e in execucoes})}
    imprimir(por_versao, rodadas)


if __name__ == "__main__":
    main_cli()

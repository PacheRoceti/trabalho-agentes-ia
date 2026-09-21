"""Verificação mínima do item 3.3: 5 casos do domínio nos 3 modelos candidatos,
com o MESMO prompt, o MESMO banco inicial e o MESMO verificador.

    python src/comparar_modelos.py

Pré-requisito: .env com LLM_BASE_URL e OPENAI_API_KEY. Um candidato
sem chave é pulado e aparece como 'não executado' — nunca com número inventado.
Saída: tabela em Markdown no terminal e em docs/modelos-tabela-3.3.md, para colar
em docs/modelos.md.

Os preços em candidatos() são de LISTA, em US$ por milhão de tokens, consultados em
21/09/2026 em agregadores, e servem só para o custo SIMULADO (no plano gratuito o
gasto real é zero). CONFIRA na página oficial da Mistral antes de entregar.
"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv

import db
from agente import Orcamento, criar_cliente, rodar
from verificar import GABARITO, verificar

RAIZ = Path(__file__).resolve().parent.parent
CASOS_COMPARACAO = ["TKT-0001", "TKT-0002", "TKT-0003", "TKT-0999", "TKT-0006"]


def candidatos() -> list[dict]:
    """Os três candidatos liberados no plano gratuito da nossa conta (ver docs/modelos.md).
    Todos usam a mesma chave e o mesmo endereço do .env; preços em US$ por milhão de tokens.
    Para testar outros modelos, edite esta lista (nome, preco=(entrada, saída))."""
    base_url, api_key = os.environ.get("LLM_BASE_URL"), os.environ.get("OPENAI_API_KEY")
    return [
        {"nome": "ministral-3b-latest", "base_url": base_url, "api_key": api_key,
         "preco": (0.10, 0.10), "temperatura": 0.0},
        {"nome": "ministral-8b-latest", "base_url": base_url, "api_key": api_key,
         "preco": (0.15, 0.15), "temperatura": 0.0},
        {"nome": "ministral-14b-latest", "base_url": base_url, "api_key": api_key,
         "preco": (0.20, 0.20), "temperatura": 0.0},
    ]


def main():
    load_dotenv(RAIZ / ".env")
    resultados = {}        # nome -> lista de dicts
    for c in candidatos():
        if not (c["base_url"] and c["api_key"]):
            print(f"[pulado] {c['nome']}: falta base_url/chave no .env")
            resultados[c["nome"]] = None
            continue
        client = criar_cliente(c["base_url"], c["api_key"])
        linhas = []
        for id_ticket in CASOS_COMPARACAO:
            db.recriar_banco()
            con = db.conectar()
            t0 = time.monotonic()
            estado = rodar(id_ticket, client=client, modelo=c["nome"], con=con,
                           temperatura=c["temperatura"], preco_usd_por_mtok=c["preco"],
                           orcamento=Orcamento(), confirmador=lambda p: (True, "auto (comparação)"),
                           log_dir=RAIZ / "logs" / "comparacao" / c["nome"], verbose=False)
            ok, falhas = verificar(id_ticket, estado, con)
            con.close()
            linhas.append({"ticket": id_ticket, "ok": ok, "falhas": falhas, "estado": estado,
                           "segundos": time.monotonic() - t0})
            print(f"{c['nome']:<24} {id_ticket}  {'OK' if ok else 'FALHOU'}  "
                  f"{estado.tokens} tok  US$ {estado.custo_usd:.5f}  {linhas[-1]['segundos']:.1f}s")
        resultados[c["nome"]] = linhas

    saida = tabela(resultados)
    print("\n" + saida)
    (RAIZ / "docs" / "modelos-tabela-3.3.md").write_text(saida, encoding="utf-8")


def tabela(resultados: dict) -> str:
    nomes = list(resultados)
    out = ["| Caso | " + " | ".join(nomes) + " |", "|---|" + "---|" * len(nomes)]
    for t in CASOS_COMPARACAO:
        celulas = []
        for n in nomes:
            linhas = resultados[n]
            if linhas is None:
                celulas.append("não executado")
                continue
            l = next(x for x in linhas if x["ticket"] == t)
            celulas.append("OK" if l["ok"] else "FALHOU: " + "; ".join(l["falhas"]))
        out.append(f"| {t} ({GABARITO[t]['caso']}) | " + " | ".join(celulas) + " |")

    def agg(n, f):
        return "não executado" if resultados[n] is None else f(resultados[n])
    k = len(CASOS_COMPARACAO)
    out.append("| **Acertos** | " + " | ".join(
        agg(n, lambda L: f"{sum(x['ok'] for x in L)} de {k}") for n in nomes) + " |")
    out.append("| **Tokens médios por execução** | " + " | ".join(
        agg(n, lambda L: f"{sum(x['estado'].tokens for x in L) / k:,.0f}") for n in nomes) + " |")
    out.append("| **Chamadas ao modelo (média)** | " + " | ".join(
        agg(n, lambda L: f"{sum(x['estado'].n_chamadas_modelo for x in L) / k:.1f}") for n in nomes) + " |")
    out.append("| **Custo médio por execução (US$)** | " + " | ".join(
        agg(n, lambda L: f"{sum(x['estado'].custo_usd for x in L) / k:.5f}") for n in nomes) + " |")
    out.append("| **Latência média (s)** | " + " | ".join(
        agg(n, lambda L: f"{sum(x['segundos'] for x in L) / k:.1f}") for n in nomes) + " |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()

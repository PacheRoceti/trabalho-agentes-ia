"""Compara duas rodadas da suíte (ou mostra uma), por classe (docs/evals.md §4).

    python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>
    python -m evals.comparar evals/resultados/<rodada>

Só lê os `resultado.json`; não chama a API. O número de cada classe é o pass^k: a fração dos casos
da classe que passaram em TODAS as repetições. MÉDIA é a média das classes; GERAL, a fração de
todos os casos (as classes têm tamanhos diferentes, e as duas contas dão números diferentes).
"""
import json
import sys
from pathlib import Path


def carregar(pasta: str | Path) -> dict:
    caminho = Path(pasta) / "resultado.json"
    if not caminho.exists():
        sys.exit(f"Não há resultado.json em {pasta}")
    return json.loads(caminho.read_text(encoding="utf-8"))


def _pct(parte, todo) -> float | None:
    return 100 * parte / todo if todo else None


def _fmt(v) -> str:
    return "  —  " if v is None else f"{v:5.1f}%"


def _medidas(r: dict) -> tuple[dict, float | None, float | None]:
    por_classe = (r.get("resumo") or {}).get("por_classe") or {}
    taxas = {k: _pct(v["passaram_todas"], v["casos"]) for k, v in por_classe.items()}
    validas = [t for t in taxas.values() if t is not None]
    media = sum(validas) / len(validas) if validas else None
    geral = _pct(sum(v["passaram_todas"] for v in por_classe.values()),
                 sum(v["casos"] for v in por_classe.values()))
    return taxas, media, geral


def _status_por_caso(r: dict) -> dict:
    casos = {}
    for e in r["execucoes"]:
        casos.setdefault(e["id"], []).append(e["passou"])
    return {i: all(v) for i, v in casos.items()}


def imprimir(rodadas: list[dict]):
    base = rodadas[-1]
    ds = base["dataset"]
    origem = ds["origem"]
    print(f"DATASET v{ds['versao']}   {ds['casos']} casos   (producao {origem.get('producao', 0)} · "
          f"desenvolvimento {origem.get('desenvolvimento', 0)} · sintetico {origem.get('sintetico', 0)})")
    if any(r["dataset"]["versao"] != ds["versao"] for r in rodadas):
        print("ATENÇÃO: as rodadas usam versões diferentes do dataset; a comparação não é do mesmo conjunto.")
    juiz = base.get("juiz")
    print(f"JUIZ rubrica v{juiz['versao']}   concordância {juiz['concordancia']}%   limiar {juiz['limiar']}%"
          if juiz else "JUIZ ainda não validado: nenhuma propriedade desta tabela depende de juiz (docs/evals.md §3)")
    for r in rodadas:
        avisos = [a for a, sim in (("PARCIAL", r.get("parcial")),
                                   ("INCOMPLETA", "resumo" not in r)) if sim]
        print(f"  {r['rodada']}: versão {r['versao']} · commit {r['commit']} · {r['modelo']} · "
              f"pass^{r['repeticoes']} {' '.join(avisos)}")
    print()

    medidas = [_medidas(r) for r in rodadas]
    nomes = ds.get("classes", {})
    classes = sorted(set().union(*(m[0] for m in medidas)))
    if len(rodadas) == 1:
        print(f"{'classe':<40} {'versão ' + rodadas[0]['versao']:>12}")
        for c in classes:
            print(f"{(c + ' ' + nomes.get(c, '')):<40} {_fmt(medidas[0][0].get(c)):>12}")
        print(f"{'MÉDIA':<40} {_fmt(medidas[0][1]):>12}")
        print(f"{'GERAL (todos os casos)':<40} {_fmt(medidas[0][2]):>12}")
    else:
        a, b = rodadas[0], rodadas[-1]
        (ta, ma, ga), (tb, mb, gb) = medidas[0], medidas[-1]
        print(f"{'classe':<40} {'versão ' + a['versao']:>12} {'versão ' + b['versao']:>12} {'delta':>8}")

        def linha(rotulo, va, vb):
            delta = "   —" if va is None or vb is None else f"{vb - va:+7.1f}"
            print(f"{rotulo:<40} {_fmt(va):>12} {_fmt(vb):>12} {delta:>8}")
        for c in classes:
            linha(c + " " + nomes.get(c, ""), ta.get(c), tb.get(c))
        linha("MÉDIA", ma, mb)
        linha("GERAL (todos os casos)", ga, gb)

        sa, sb = _status_por_caso(a), _status_por_caso(b)
        piorou = sorted(i for i in sa if i in sb and sa[i] and not sb[i])
        melhorou = sorted(i for i in sa if i in sb and not sa[i] and sb[i])
        print(f"\nCasos que passaram a falhar: {', '.join(piorou) or 'nenhum'}")
        print(f"Casos que passaram a passar: {', '.join(melhorou) or 'nenhum'}")

    print("\nFalhas por propriedade (execuções):")
    for r in rodadas:
        falhas = (r.get("resumo") or {}).get("falhas_por_propriedade") or {}
        print(f"  {r['rodada']}: " + (", ".join(f"{k} {v}" for k, v in falhas.items()) or "nenhuma"))
    casos = (base.get("resumo") or {}).get("casos_que_falharam")
    if casos is not None:
        print(f"  casos que falharam em ao menos uma repetição ({base['rodada']}): {', '.join(casos) or 'nenhum'}")
    for r in rodadas:
        resumo = r.get("resumo") or {}
        infra = resumo.get("falhas_de_infraestrutura") or []
        if resumo.get("reexecucoes_429") or infra:
            print(f"  {r['rodada']}: {resumo.get('reexecucoes_429', 0)} reexecução(ões) por limite de "
                  f"requisições (429); falhas que ficaram por 429, contadas como falha: "
                  f"{', '.join(infra) or 'nenhuma'}")


def main_cli():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    imprimir([carregar(p) for p in sys.argv[1:]])


if __name__ == "__main__":
    main_cli()

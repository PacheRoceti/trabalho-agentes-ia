"""Roda o golden dataset sobre o sistema entregue e grava o resultado da rodada (docs/evals.md §4).

    python -m evals.rodar --versao 1.0.0                     # os 44 casos, 3 repetições
    python -m evals.rodar --versao 1.0.0 --casos TKT-0001 TKT-0002 --repeticoes 1   # parcial

USA A API. Cada caso passa por `main.executar`, a mesma função que `python src/main.py --todos`
chama por caso, com o banco recriado antes (o estado inicial é o mesmo em todo caso e repetição)
e a aprovação automática do H1 e do H2 (a pausa é demonstrada à parte: docs/humano.md). Grava em
evals/resultados/<rodada>/: `resultado.json` (o número de cada checagem, por execução), a saída de
terminal e os logs do grafo de cada execução. Uma rodada que já existe não é sobrescrita.

Recria dados/tickets.db e zera a memória, como o --todos.
"""
import argparse
import contextlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from evals import RAIZ
from evals import checagens

DATASETS = RAIZ / "evals" / "dataset"
RESULTADOS = RAIZ / "evals" / "resultados"
# O plano gratuito limita as requisições, e o sistema desiste depois de 5 tentativas (erro_fatal).
# Isso é falha da infraestrutura, e não do agente (exercicios/aula-11-avaliacao.md §4): o caso é
# executado de novo, do zero, depois de uma espera. Esgotadas as esperas, conta como falha, marcada.
ESPERAS_429_S = (30, 90)


def _limite_de_requisicoes(log: dict) -> bool:
    return log.get("termino") == "erro_fatal" and "429" in str(log.get("motivo") or "")


def carregar_dataset(caminho: Path | None = None) -> tuple[dict, Path]:
    """O dataset mais novo (ou o pedido). Os nomes são v<x.y.z>.json."""
    if caminho is None:
        versoes = sorted(DATASETS.glob("v*.json"),
                         key=lambda p: tuple(int(n) for n in p.stem[1:].split(".")))
        caminho = versoes[-1]
    return json.loads(caminho.read_text(encoding="utf-8")), caminho


def conferir_dataset(dataset: dict, con) -> list[str]:
    """O dataset é uma cópia do gabarito e do seed; o verificador do sistema lê o gabarito, e o
    agente lê o seed. Se os três divergem, a suíte mediria uma coisa e diria outra: recusa rodar."""
    from verificar import GABARITO
    erros = []
    for caso in dataset["casos"]:
        i = caso["id"]
        gab = {k: v for k, v in GABARITO.get(i, {}).items() if not k.startswith("_") and k != "caso"}
        if caso["esperado"] != gab:
            erros.append(f"{i}: o esperado difere de dados/gabarito.json")
        linha = con.execute("SELECT texto, anexo_log, cliente_id FROM tickets_externos WHERE id = ?",
                            (i,)).fetchone()
        entrada = ({"texto": linha["texto"], "anexo_log": linha["anexo_log"],
                    "cliente_id": linha["cliente_id"]} if linha
                   else {"texto": None, "anexo_log": None, "cliente_id": None})
        if caso["entrada"] != entrada:
            erros.append(f"{i}: a entrada difere do chamado em dados/seed.sql")
    return erros


def resumir(execucoes: list[dict], casos: list[dict]) -> dict:
    """Por classe: quantos casos passaram em TODAS as repetições (pass^k, o número da comparação)
    e em ao menos uma (pass@k, diagnóstico), e quantas execuções passaram."""
    por_caso = defaultdict(list)
    for e in execucoes:
        por_caso[e["id"]].append(e["passou"])
    classe_de = {c["id"]: c["classe"] for c in casos}
    resumo = {}
    for classe in sorted({classe_de[i] for i in por_caso}):
        ids = [i for i in por_caso if classe_de[i] == classe]
        resumo[classe] = {
            "casos": len(ids),
            "passaram_todas": sum(all(por_caso[i]) for i in ids),
            "passaram_alguma": sum(any(por_caso[i]) for i in ids),
            "execucoes": sum(len(por_caso[i]) for i in ids),
            "execucoes_ok": sum(sum(por_caso[i]) for i in ids),
        }
    falhas = Counter(f"{c['nivel']}:{c['propriedade']}" for e in execucoes
                     for c in e["checagens"] if not c["ok"])
    return {"por_classe": resumo, "falhas_por_propriedade": dict(falhas.most_common()),
            "casos_que_falharam": sorted(i for i, v in por_caso.items() if not all(v)),
            "reexecucoes_429": sum(e.get("reexecucoes_429", 0) for e in execucoes),
            "falhas_de_infraestrutura": sorted({e["id"] for e in execucoes
                                                if e.get("falha_de_infraestrutura")})}


def rodar_rodada(dataset: dict, casos: list[dict], repeticoes: int, destino: Path, client, modelo: str,
                 precos, metadados: dict, avisar=print) -> dict:
    """O laço da suíte. Recebe o cliente pronto, para os testes offline passarem um modelo roteirizado."""
    import db
    import main
    destino.mkdir(parents=True)
    resultado = {**metadados, "execucoes": []}
    with (destino / "saida-terminal.txt").open("w", encoding="utf-8") as saida:
        for rep in range(1, repeticoes + 1):
            log_dir = destino / "logs" / f"rep-{rep}"
            log_dir.mkdir(parents=True)
            for caso in casos:
                i = caso["id"]
                caminho_log = log_dir / f"{i}.json"
                reexecucoes_429 = 0
                while True:
                    db.recriar_banco()           # cada caso parte do mesmo estado inicial
                    con = db.conectar()
                    antes = checagens.foto_do_resto(con, i)
                    inicio = time.monotonic()
                    erro = None
                    try:
                        with contextlib.redirect_stdout(saida):
                            main.executar(i, client, modelo, precos, main.confirmador_auto, con, log_dir,
                                          grafo=True)
                    except Exception as e:        # noqa: BLE001 — a execução que quebra é um resultado
                        erro = f"{type(e).__name__}: {e}"
                    segundos = round(time.monotonic() - inicio, 2)
                    log = json.loads(caminho_log.read_text(encoding="utf-8")) if caminho_log.exists() else {}
                    if not _limite_de_requisicoes(log) or reexecucoes_429 == len(ESPERAS_429_S):
                        break
                    con.close()
                    espera = ESPERAS_429_S[reexecucoes_429]
                    reexecucoes_429 += 1
                    avisar(f"  rep {rep}  {i}  limite de requisições (429): de novo em {espera} s")
                    print(f"\n[suíte] {i}: limite de requisições (429); reexecutando em {espera} s\n", file=saida)
                    time.sleep(espera)
                if erro or not log:
                    lista = [{"nivel": "deterministico", "propriedade": "executou", "ok": False,
                              "detalhe": erro or "a execução não gravou log"}]
                else:
                    lista = checagens.avaliar(caso, log, con, antes, checagens.foto_do_resto(con, i))
                con.close()
                passou = all(c["ok"] for c in lista)
                resultado["execucoes"].append({
                    "id": i, "classe": caso["classe"], "repeticao": rep, "passou": passou,
                    "checagens": lista, "termino": log.get("termino"), "motivo": log.get("motivo"),
                    "acao": (log.get("desfecho") or {}).get("acao"), "segundos": segundos,
                    "tokens": (log.get("tokens_entrada") or 0) + (log.get("tokens_saida") or 0),
                    "custo_usd": log.get("custo_usd"), "commit_no_log": log.get("commit"),
                    "reexecucoes_429": reexecucoes_429,
                    "falha_de_infraestrutura": _limite_de_requisicoes(log),
                    "log": caminho_log.relative_to(destino).as_posix() if caminho_log.exists() else None,
                })
                falhou = [c["propriedade"] for c in lista if not c["ok"]]
                avisar(f"  rep {rep}  {i}  {caso['classe']}  {'ok' if passou else 'FALHOU: ' + ', '.join(falhou)}")
                # gravado a cada execução: uma rodada interrompida deixa o que já mediu
                _gravar(destino, resultado)
    resultado["terminado_em"] = datetime.now().astimezone().isoformat(timespec="seconds")
    resultado["resumo"] = resumir(resultado["execucoes"], casos)
    _gravar(destino, resultado)
    return resultado


def _gravar(destino: Path, resultado: dict):
    (destino / "resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")


def main_cli():
    ap = argparse.ArgumentParser(description="Roda a suíte de avaliação sobre o sistema entregue (usa a API)")
    from versao import VERSAO
    ap.add_argument("--versao", default=VERSAO,
                    help=f"a versão do sistema que está sendo medida (padrão: a de src/versao.py, hoje {VERSAO}); "
                         f"vai ao resultado e à comparação")
    ap.add_argument("--repeticoes", type=int, default=3, help="repetições por caso (padrão: 3)")
    ap.add_argument("--casos", nargs="+", help="só estes ids (a rodada fica marcada como parcial)")
    ap.add_argument("--dataset", type=Path, help="arquivo do dataset (padrão: o mais novo em evals/dataset/)")
    ap.add_argument("--nome", help="nome da pasta em evals/resultados/ (padrão: v<versao>-<data e hora>)")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
    import db
    import grafo
    import main
    from agente import _commit

    dataset, caminho_dataset = carregar_dataset(args.dataset)
    db.recriar_banco()
    con = db.conectar()
    erros = conferir_dataset(dataset, con)
    con.close()
    if erros:
        sys.exit("O dataset não confere com o gabarito ou o seed; nada foi executado:\n  " + "\n  ".join(erros))
    casos = dataset["casos"]
    if args.casos:
        desconhecidos = set(args.casos) - {c["id"] for c in casos}
        if desconhecidos:
            sys.exit(f"Casos fora do dataset: {', '.join(sorted(desconhecidos))}")
        casos = [c for c in casos if c["id"] in args.casos]

    agora = datetime.now().astimezone()
    nome = args.nome or f"v{args.versao}-{agora:%Y-%m-%d-%H%M}"
    destino = RESULTADOS / nome
    if destino.exists():
        sys.exit(f"{destino} já existe: os resultados commitados são evidência e não são sobrescritos. "
                 f"Use outro --nome.")

    if args.versao != VERSAO:
        print(f"ATENÇÃO: --versao {args.versao} difere de src/versao.py ({VERSAO}), que vai aos traces.")
    client, modelo, precos = main.preparar_api()
    commit = _commit()
    if commit and "alterações locais" in commit:
        print(f"ATENÇÃO: o código tem alterações não commitadas ({commit}); a rodada registra isso.")
    metadados = {
        "rodada": nome, "versao": args.versao, "commit": commit, "modelo": modelo,
        "prompts": grafo.prompts_em_uso(), "busca": grafo.BUSCA,
        "dataset": {"arquivo": caminho_dataset.relative_to(RAIZ).as_posix(), "versao": dataset["versao"],
                    "casos": len(casos), "origem": dict(Counter(c["origem"] for c in casos)),
                    "classes": dataset["classes"]},
        "parcial": bool(args.casos), "repeticoes": args.repeticoes,
        "juiz": None,                    # docs/evals.md §3: ainda não validado
        "iniciado_em": agora.isoformat(timespec="seconds"),
    }
    print(f"Rodada {nome}: {len(casos)} caso(s) x {args.repeticoes} repetição(ões), modelo {modelo}, "
          f"commit {commit}\n")
    resultado = rodar_rodada(dataset, casos, args.repeticoes, destino, client, modelo, precos, metadados)
    print()
    from evals.comparar import imprimir
    imprimir([resultado])
    print(f"\nResultado gravado em {destino.relative_to(RAIZ).as_posix()}/resultado.json")


if __name__ == "__main__":
    main_cli()

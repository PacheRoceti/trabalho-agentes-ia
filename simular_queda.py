"""Simulação de uma queda do processo no meio da retomada (docs/humano.md §4.3).

A queda que a recuperação trata é do PROCESSO (luz, máquina reiniciada, processo encerrado), e não
do modelo: ela acontece numa fração de segundo, entre uma escrita no banco e o checkpoint seguinte,
e ninguém a reproduz esperando. Este script a provoca no ponto escolhido, com injeção de falha: troca
uma função de `src/db.py` por uma que mata o processo com `os._exit`, sem `finally`, sem fechar
conexão e sem liberar trava (quem libera é o sistema operacional). A execução até a pausa é a de
verdade, com o modelo real; da queda em diante tudo é código, e o modelo não é chamado.

    python src/main.py --reset
    python src/main.py TKT-0007 --rodada grafo-queda          o modelo real, até a pausa (H1)
    python simular_queda.py cair TKT-0007 --em abrir_chamado  aprova, e o processo morre antes de abrir o chamado
    python simular_queda.py estado TKT-0007                   o que ficou no banco e no checkpoint
    (5 minutos: grafo.IDADE_MINIMA_DA_QUEDA_MIN)
    python src/vigiar_prazos.py --uma-vez --log logs/grafo-queda/vigia.log   a recuperação
    python simular_queda.py estado TKT-0007

`--depois` faz a função gravar e só então cair (a janela J3); sem ele, cai antes de gravar (J2, ou
J1 com `--em resolver_pendencia`). Não muda nada no sistema: a troca vale só dentro do processo
deste script, que morre com ela.
"""
import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "src"))

from dotenv import load_dotenv                                   # noqa: E402

import db                                                        # noqa: E402

# Os pontos de escrita da retomada em que a queda pode ser provocada.
PONTOS = ("resolver_pendencia", "abrir_chamado", "registrar_pedido_cliente",
          "registrar_encaminhamento", "avisar_gestor", "registrar_episodio")
CODIGO_DA_QUEDA = 70        # o código de saída do processo que "caiu", para quem rodou saber


def cair(ticket: str, ponto: str, depois: bool, decisao: str) -> int:
    from agente import criar_cliente, retomar
    load_dotenv(RAIZ / ".env")
    original = getattr(db, ponto)

    def queda(*a, **kw):
        if depois:
            original(*a, **kw)
        print(f"  >> QUEDA SIMULADA em db.{ponto} ({'depois' if depois else 'antes'} de gravar): "
              f"o processo morre agora (os._exit({CODIGO_DA_QUEDA}))", flush=True)
        os._exit(CODIGO_DA_QUEDA)
    setattr(db, ponto, queda)
    con = db.conectar()
    estado = retomar(ticket, decisao, client=criar_cliente(), con=con,
                     por="analista de suporte (simular_queda.py)")
    # Só chega aqui se a retomada não passou pelo ponto escolhido.
    print(f"  a retomada terminou sem passar por db.{ponto}: nenhuma queda foi provocada "
          f"({'nada pendente para ' + ticket if estado is None else 'desfecho ' + str(estado.desfecho)})")
    return 2


def estado(ticket: str) -> int:
    """Só lê: a pendência, o que foi gravado e onde o checkpoint parou."""
    import grafo
    con = db.conectar()
    for p in con.execute("SELECT id, status, pedido_em, vence_em, resolvido_em, resolvido_por, resposta "
                         "FROM pendencias WHERE ticket_externo = ? ORDER BY id", (ticket,)):
        resposta = json.loads(p["resposta"]) if p["resposta"] else None
        print(f"  pendência {p['id']}: {p['status']}, resolvida em {p['resolvido_em']} por "
              f"{p['resolvido_por']}; resposta guardada: "
              f"{resposta['decisao'] + ' às ' + resposta['quando'] if resposta else 'nenhuma'}")
    for tabela in ("chamados_internos", "encaminhamentos", "avisos_gestor"):
        print(f"  {tabela}: {db.contar(con, tabela, ticket)}")
    foto = grafo.GRAFO.get_state({"configurable": {"thread_id": ticket}})
    if foto.values:
        print(f"  checkpoint: parado em {list(foto.next) or 'fim (sem log)'}, gravado em {foto.created_at}")
    else:
        print("  checkpoint: nenhum (a execução concluiu, ou nunca começou)")
    con.close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Simula uma queda do processo no meio da retomada.")
    sub = ap.add_subparsers(dest="comando", required=True)
    c = sub.add_parser("cair", help="responde à pendência e mata o processo no ponto escolhido")
    c.add_argument("ticket")
    c.add_argument("--em", required=True, choices=PONTOS, help="a função de src/db.py em que o processo cai")
    c.add_argument("--depois", action="store_true", help="a função grava e só então o processo cai")
    c.add_argument("--decisao", default="aprovar", choices=("aprovar", "rejeitar", "vencer"))
    e = sub.add_parser("estado", help="mostra a pendência, o que foi gravado e o checkpoint (só lê)")
    e.add_argument("ticket")
    args = ap.parse_args(argv)
    if args.comando == "cair":
        return cair(args.ticket, args.em, args.depois, args.decisao)
    return estado(args.ticket)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())

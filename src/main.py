"""Ponto de entrada.

    python src/main.py TKT-0001                     um chamado (pede confirmação no terminal)
    python src/main.py TKT-0002 --auto-aprovar      um chamado, sem perguntar (demonstração)
    python src/main.py --todos --auto-aprovar       os 7 casos, do banco zerado, com verificador
                                                    (grava também logs/saida-demonstracao.txt)
    python src/main.py --reset                      recria o banco de dados simulado
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import db
from agente import Orcamento, criar_cliente, rodar
from verificar import GABARITO, verificar

RAIZ = Path(__file__).resolve().parent.parent
CASOS = [k for k in GABARITO if not k.startswith("_")]


class Tee:
    """Escreve na tela E no arquivo (UTF-8). Evita o pipe do PowerShell, que
    embaralha os acentos no Windows."""

    def __init__(self, *fluxos):
        self.fluxos = fluxos

    def write(self, texto):
        for f in self.fluxos:
            f.write(texto)

    def flush(self):
        for f in self.fluxos:
            f.flush()


def confirmador_terminal(pendencia: dict):
    print("\n  >> AÇÃO IRREVERSÍVEL aguardando o analista de suporte:")
    for k, v in pendencia.items():
        print(f"     {k}: {v}")
    if not sys.stdin.isatty():
        return False, "sem terminal interativo (use --auto-aprovar na demonstração)"
    resposta = input("  Confirma a abertura deste chamado interno? [s/N] ")
    return resposta.strip().lower() in ("s", "sim", "y"), "analista (terminal)"


def confirmador_auto(pendencia: dict):
    return True, "auto-aprovado (--auto-aprovar; só para demonstração)"


def executar(id_ticket: str, client, modelo: str, precos, confirmador, con) -> bool | None:
    caso = GABARITO.get(id_ticket, {}).get("caso", "sem gabarito")
    print(f"\n{'=' * 78}\n{id_ticket}  (caso: {caso})  modelo: {modelo}\n")
    estado = rodar(id_ticket, client=client, modelo=modelo, con=con,
                   preco_usd_por_mtok=precos, orcamento=Orcamento(),
                   confirmador=confirmador, log_dir=RAIZ / "logs")
    print(f"\n  {estado.resumo()}")
    if estado.motivo:
        print(f"  motivo: {estado.motivo}")
    if estado.resposta:
        print(f"  resposta: {estado.resposta}")
    if id_ticket in GABARITO:
        ok, falhas = verificar(id_ticket, estado, con)
        print(f"  VERIFICADOR: {'OK' if ok else 'FALHOU'}" + ("" if ok else " - " + "; ".join(falhas)))
        return ok
    return None


def main():
    load_dotenv(RAIZ / ".env")
    ap = argparse.ArgumentParser(description="Agente de triagem de chamados (Parte 1)")
    ap.add_argument("ticket", nargs="?", help="id do chamado externo, ex: TKT-0001")
    ap.add_argument("--todos", action="store_true", help="roda os casos de demonstração")
    ap.add_argument("--auto-aprovar", action="store_true",
                    help="aprova sozinho as escritas irreversíveis (só demonstração)")
    ap.add_argument("--reset", action="store_true", help="recria o banco simulado")
    args = ap.parse_args()

    if args.reset:
        db.recriar_banco()
        print("Banco simulado recriado a partir de dados/seed.sql")
        if not (args.ticket or args.todos):
            return
    if not (args.ticket or args.todos):
        ap.print_help()
        return

    for var in ("LLM_BASE_URL", "OPENAI_API_KEY", "LLM_MODELO"):
        if not os.environ.get(var):
            sys.exit(f"Falta a variável {var}. Copie .env.example para .env e preencha.")
    client = criar_cliente()
    modelo = os.environ["LLM_MODELO"]
    # .env em branco vale como ausente; padrão = mistral-small (US$ por milhão de tokens)
    precos = (float(os.environ.get("PRECO_ENTRADA_USD") or "0.15"),
              float(os.environ.get("PRECO_SAIDA_USD") or "0.60"))
    confirmador = confirmador_auto if args.auto_aprovar else confirmador_terminal

    if args.todos:
        saida = (RAIZ / "logs" / "saida-demonstracao.txt").open("w", encoding="utf-8")
        original, sys.stdout = sys.stdout, Tee(sys.stdout, saida)
        try:
            resultados = {}
            for id_ticket in CASOS:
                db.recriar_banco()              # cada caso parte do mesmo estado inicial
                con = db.conectar()
                resultados[id_ticket] = executar(id_ticket, client, modelo, precos, confirmador, con)
                con.close()
            acertos = sum(1 for v in resultados.values() if v)
            print(f"\n{'=' * 78}\nRESULTADO: {acertos} de {len(resultados)} casos conferidos pelo verificador")
            for t, v in resultados.items():
                print(f"  {t}  {GABARITO[t]['caso']:<28} {'OK' if v else 'FALHOU'}")
        finally:
            sys.stdout = original
            saida.close()
        print("\nSaída completa gravada em logs/saida-demonstracao.txt (UTF-8)")
    else:
        con = db.conectar()
        executar(args.ticket, client, modelo, precos, confirmador, con)
        con.close()


if __name__ == "__main__":
    main()

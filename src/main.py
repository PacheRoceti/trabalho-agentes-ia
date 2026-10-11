"""Ponto de entrada.

  O caminho padrão é o GRAFO em LangGraph (src/grafo.py); os logs dele vão para logs/grafo/.
  O laço da Parte 1 (src/agente.py) roda com --laco, e grava em logs/.

    python src/main.py TKT-0001 "O certificado SSL do meu site venceu ontem..."
                                                    a ENTRADA é o texto do chamado, acompanhado do id
    python src/main.py TKT-0001                     sem o texto, o programa pede que você o digite;
                                                    Enter em branco usa o texto já registrado no chamado
    python src/main.py TKT-0002 "..." --auto-aprovar   sem esperar a confirmação (demonstração)

  Abrir chamado interno é irreversível: sem --auto-aprovar a execução PAUSA, grava a pendência e
  o analista tem 20 minutos para responder (--prazo-confirmacao MIN muda o prazo da execução):
    python src/main.py --pendencias                 o que aguarda o analista, e quanto tempo falta
    python src/main.py --aprovar TKT-0007           abre o chamado e conclui a execução pausada
    python src/main.py --rejeitar TKT-0007          o chamado interno não é aberto
  Rejeitada a ação ou vencido o prazo, o chamado vai para a fila humana com as considerações do
  agente. No prazo vencido de um chamado que seria P1, o gestor também é avisado (tabela
  avisos_gestor). O prazo é aplicado no começo de qualquer comando que use o agente: não há
  processo em segundo plano.

    python src/main.py --todos --auto-aprovar       os 8 casos, do banco zerado, com verificador
                                                    (grava também logs/saida-demonstracao.txt)
    python src/main.py --reset                      recria o banco de dados simulado
    python src/main.py TKT-0001 --laco              roda pelo laço da Parte 1, e não pelo grafo;
                                                    --aprovar / --rejeitar valem para os dois
    python src/main.py --todos --auto-aprovar --rodada NOME [--prompt ARQUIVO]
                                                    grava em logs/NOME/ (não sobrescreve os logs
                                                    versionados). --prompt escolhe outro arquivo de
                                                    src/prompts/ para o LAÇO, e por isso já implica
                                                    --laco: o grafo usa triagem-v1.md e redigir-v1.md
"""
import argparse
import json
import os
import sys
from pathlib import Path

from datetime import datetime

from dotenv import load_dotenv

import db
from agente import (PROMPT_ARQUIVO, PROMPTS, Orcamento, criar_cliente, retomar, rodar,
                    vencer_pendencias)
from ferramentas import PRAZO_CONFIRMACAO_MIN
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


def confirmador_auto(pendencia: dict):
    return True, "auto-aprovado (--auto-aprovar; só para demonstração)"


def mostrar_pendencia(pendencia: dict):
    """O que o analista vê: a ação proposta, até quando ele pode responder e como responder."""
    print("\n  >> AÇÃO IRREVERSÍVEL aguardando o analista de suporte:")
    for k, v in pendencia.items():
        print(f"     {k}: {v}")
    resta = (datetime.fromisoformat(pendencia["vence_em"]) - datetime.now().astimezone()).total_seconds()
    print(f"     faltam: {max(resta, 0) / 60:.0f} min" if resta > 0 else "     PRAZO VENCIDO")
    id_ticket = pendencia["id_ticket"]
    print(f"     responder: python src/main.py --aprovar {id_ticket}   |   --rejeitar {id_ticket}")
    print("     rejeitada ou sem resposta no prazo, o chamado vai para a fila humana com esta ação proposta")


def ler_texto(id_ticket: str, texto: str | None) -> str | None:
    """O texto do chamado, como o usuário o digitou: no argumento ou, sem ele, no terminal.
    Devolve None quando nada foi digitado (Enter em branco, ou execução sem terminal): aí o
    programa usa o texto já registrado para o id, simulando o evento de abertura."""
    if texto is None and sys.stdin.isatty():
        texto = input(f"Texto do chamado {id_ticket} (Enter em branco usa o texto registrado):\n> ")
    return texto if texto and texto.strip() else None


def mostrar(estado):
    print(f"  ENTRADA: {estado.entrada if estado.entrada is not None else '(sem texto: id não encontrado)'}")
    print(f"\n  {estado.resumo()}")
    if estado.motivo:
        print(f"  motivo: {estado.motivo}")
    if estado.resposta:
        print(f"  resposta: {estado.resposta}")
    if estado.saida:
        print("  SAÍDA (objeto validado, src/saida.py):")
        for linha in json.dumps(estado.saida.model_dump(), ensure_ascii=False, indent=2).splitlines():
            print(f"    {linha}")
    if (estado.desfecho or {}).get("aviso_gestor"):
        print(f"  >> GESTOR AVISADO: o chamado interno seria P1 e o prazo de confirmação venceu "
              f"(tabela avisos_gestor, id {estado.desfecho['aviso_gestor']})")
    if (estado.motivo or "").startswith("aguardando"):   # pausou à espera do analista
        mostrar_pendencia(estado.pendencia)


def executar(id_ticket: str, client, modelo: str, precos, confirmador, con,
             log_dir: Path = RAIZ / "logs", prompt_arquivo: Path = PROMPT_ARQUIVO,
             texto: str | None = None,
             prazo_confirmacao_min: float = PRAZO_CONFIRMACAO_MIN,
             grafo: bool = True) -> bool | None:
    caso = GABARITO.get(id_ticket, {}).get("caso", "sem gabarito")
    prompt = "triagem-v1.md + redigir-v1.md (grafo)" if grafo else prompt_arquivo.name
    print(f"\n{'=' * 78}\n{id_ticket}  (caso: {caso})  modelo: {modelo}  prompt: {prompt}\n")
    if grafo:
        from grafo import rodar_grafo        # importado só aqui: --laco não depende do LangGraph
        estado = rodar_grafo(id_ticket, client=client, modelo=modelo, con=con,
                             preco_usd_por_mtok=precos, orcamento=Orcamento(),
                             confirmador=confirmador, log_dir=log_dir, texto=texto,
                             prazo_confirmacao_min=prazo_confirmacao_min)
    else:
        estado = rodar(id_ticket, client=client, modelo=modelo, con=con,
                       preco_usd_por_mtok=precos, orcamento=Orcamento(),
                       confirmador=confirmador, log_dir=log_dir, prompt_arquivo=prompt_arquivo,
                       texto=texto, prazo_confirmacao_min=prazo_confirmacao_min)
    mostrar(estado)
    if (estado.motivo or "").startswith("aguardando"):   # pausou: ainda não há o que conferir
        return None
    if id_ticket in GABARITO and texto is None:          # o gabarito vale para o texto do seed
        ok, falhas = verificar(id_ticket, estado, con)
        print(f"  VERIFICADOR: {'OK' if ok else 'FALHOU'}" + ("" if ok else " - " + "; ".join(falhas)))
        return ok
    return None


def main():
    load_dotenv(RAIZ / ".env")
    ap = argparse.ArgumentParser(description="Agente de triagem de chamados")
    ap.add_argument("ticket", nargs="?", help="id do chamado externo, ex: TKT-0001")
    ap.add_argument("texto", nargs="?",
                    help="o texto do chamado, entre aspas; sem ele, o programa pede no terminal")
    ap.add_argument("--todos", action="store_true", help="roda os casos de demonstração")
    ap.add_argument("--auto-aprovar", action="store_true",
                    help="aprova sozinho as escritas irreversíveis (só demonstração)")
    ap.add_argument("--pendencias", action="store_true",
                    help="lista as ações irreversíveis que aguardam o analista")
    ap.add_argument("--aprovar", metavar="TICKET", help="o analista aprova a ação pendente do chamado")
    ap.add_argument("--rejeitar", metavar="TICKET", help="o analista rejeita a ação pendente do chamado")
    ap.add_argument("--prazo-confirmacao", type=float, default=PRAZO_CONFIRMACAO_MIN, metavar="MIN",
                    help=f"prazo do analista para esta execução, em minutos (padrão: {PRAZO_CONFIRMACAO_MIN})")
    ap.add_argument("--reset", action="store_true", help="recria o banco simulado")
    ap.add_argument("--laco", action="store_true",
                    help="roda pelo laço da Parte 1 (src/agente.py) em vez do grafo; logs em logs/")
    ap.add_argument("--grafo", action="store_true",
                    help="roda pelo grafo em LangGraph (src/grafo.py). Já é o padrão; logs em logs/grafo/")
    ap.add_argument("--rodada", help="grava os logs em logs/<nome>/ em vez de logs/")
    ap.add_argument("--prompt", help="arquivo de src/prompts/ a usar (padrão: o prompt em uso)")
    args = ap.parse_args()

    if args.reset:
        db.recriar_banco()
        print("Banco simulado recriado a partir de dados/seed.sql")
    resposta = args.aprovar or args.rejeitar
    if args.reset and not (args.ticket or args.todos or args.pendencias or resposta):
        return
    if args.aprovar and args.rejeitar:
        sys.exit("Use --aprovar ou --rejeitar, um de cada vez.")
    if not (args.ticket or args.todos or args.pendencias or resposta):
        ap.print_help()
        return
    if args.todos and not args.auto_aprovar:
        sys.exit("--todos recria o banco a cada caso, e uma ação pendente se perderia: "
                 "use --todos --auto-aprovar.")

    for var in ("LLM_BASE_URL", "OPENAI_API_KEY", "LLM_MODELO"):
        if not os.environ.get(var):
            sys.exit(f"Falta a variável {var}. Copie .env.example para .env e preencha.")
    client = criar_cliente()
    modelo = os.environ["LLM_MODELO"]
    # .env em branco vale como ausente; padrão = ministral-8b-latest (US$ por milhão de tokens)
    precos = (float(os.environ.get("PRECO_ENTRADA_USD") or "0.15"),
              float(os.environ.get("PRECO_SAIDA_USD") or "0.15"))
    # Sem --auto-aprovar não há confirmador: a ação irreversível fica pendente, com prazo.
    confirmador = confirmador_auto if args.auto_aprovar else None
    if args.grafo and (args.laco or args.prompt):
        sys.exit("--grafo não combina com --laco nem com --prompt: --prompt vale só para o laço "
                 "(o grafo usa triagem-v1.md e redigir-v1.md).")
    # O grafo é o caminho padrão. --prompt escolhe um prompt do laço, e por isso implica --laco.
    usar_grafo = not (args.laco or args.prompt)
    # O grafo nunca grava em logs/: é lá que estão os logs do laço citados no README e no io.md.
    log_dir = RAIZ / "logs" / (args.rodada or ("grafo" if usar_grafo else ""))
    prompt_arquivo = PROMPTS / args.prompt if args.prompt else PROMPT_ARQUIVO
    if not prompt_arquivo.exists():
        sys.exit(f"Prompt não encontrado: {prompt_arquivo}")
    log_dir.mkdir(parents=True, exist_ok=True)

    if not args.todos:                   # --todos recria o banco a cada caso: não há o que vencer
        con = db.conectar()
        # O prazo vale antes da pessoa: o que venceu sem resposta vai para a fila humana agora.
        for estado in vencer_pendencias(client=client, con=con, log_dir=log_dir):
            print(f"\n{'=' * 78}\n{estado.id_ticket}  PRAZO DE CONFIRMAÇÃO VENCIDO: encaminhado à fila humana\n")
            mostrar(estado)
        if resposta:
            estado = retomar(resposta, "aprovar" if args.aprovar else "rejeitar", client=client,
                             con=con, por="analista de suporte (terminal)", log_dir=log_dir)
            if estado is None:
                print(f"\nNão há confirmação pendente para {resposta}.")
            else:
                print(f"\n{'=' * 78}\n{resposta}  {'APROVADO' if args.aprovar else 'REJEITADO'} pelo analista\n")
                mostrar(estado)
        if args.pendencias:
            pendentes = db.pendencias_aguardando(con)
            print(f"\n{len(pendentes)} ação(ões) aguardando o analista de suporte")
            for p in pendentes:
                mostrar_pendencia(p["acao"])
        if args.ticket and db.pendencias_aguardando(con, args.ticket):
            con.close()
            sys.exit(f"{args.ticket} tem uma ação aguardando o analista: responda com "
                     f"--aprovar {args.ticket} ou --rejeitar {args.ticket} antes de rodar de novo.")
        con.close()
        if not args.ticket:
            return

    if args.todos:
        saida = (log_dir / "saida-demonstracao.txt").open("w", encoding="utf-8")
        original, sys.stdout = sys.stdout, Tee(sys.stdout, saida)
        try:
            resultados = {}
            for id_ticket in CASOS:
                db.recriar_banco()              # cada caso parte do mesmo estado inicial
                con = db.conectar()
                resultados[id_ticket] = executar(id_ticket, client, modelo, precos, confirmador, con,
                                                 log_dir, prompt_arquivo, grafo=usar_grafo)
                con.close()
            acertos = sum(1 for v in resultados.values() if v)
            print(f"\n{'=' * 78}\nRESULTADO: {acertos} de {len(resultados)} casos conferidos pelo verificador")
            for t, v in resultados.items():
                print(f"  {t}  {GABARITO[t]['caso']:<28} {'OK' if v else 'FALHOU'}")
        finally:
            sys.stdout = original
            saida.close()
        print(f"\nSaída completa gravada em {log_dir / 'saida-demonstracao.txt'} (UTF-8)")
    else:
        texto = ler_texto(args.ticket, args.texto)
        con = db.conectar()
        executar(args.ticket, client, modelo, precos, confirmador, con, log_dir, prompt_arquivo, texto,
                 args.prazo_confirmacao, grafo=usar_grafo)
        con.close()


if __name__ == "__main__":
    main()

"""Vigia do prazo de confirmação do analista (docs/humano.md §4.1).

O prazo de 20 minutos do H1 e do H2 era aplicado só no começo do próximo comando do main.py: se
ninguém rodasse nada, a ação vencida não chegava à fila humana e o gestor não era avisado do P1.
Este processo roda à parte e aplica o prazo sozinho, dormindo até o próximo `vence_em`. A regra
continua a mesma, e é do código: `agente.vencer_pendencias`, que o main.py também chama (segunda
rede, para quando o vigia não está rodando).

    python src/vigiar_prazos.py                 roda até ser parado (Ctrl+C)
    python src/vigiar_prazos.py --uma-vez       uma conferência e sai (para o Agendador de Tarefas ou o cron)
    python src/vigiar_prazos.py --log ARQUIVO   grava o log em outro arquivo (padrão: logs/vigia/vigia.log)

Feito para rodar sem terminal, como serviço (systemd, Agendador de Tarefas, NSSM; docs/humano.md
§4.2):
- nada interativo: a configuração vem do .env (a chave da API, para a frase final do laço) e dos
  argumentos;
- a saída vai para um log rotativo em UTF-8, além da tela quando houver tela;
- o estado está no banco (tabela `pendencias`), e não na memória: reiniciar não perde nada, e a
  primeira volta depois do reinício vence o que passou do prazo enquanto ele estava parado;
- erro numa volta (rede, cota, banco recriado por --todos ou --reset) é registrado, e a próxima
  volta tenta de novo;
- um vigia só por máquina (db.travar_instancia);
- o sinal de parada (Ctrl+C, SIGTERM, Ctrl+Break) termina a volta em curso e sai;
- o sinal de vida fica em dados/vigia-batimento.json, e o `main.py --pendencias` o mostra.

O que ele NÃO faz: não aprova nem rejeita nada, não chama o modelo para decidir, e não muda o
prazo. Responder à pendência continua sendo do analista (main.py --aprovar / --rejeitar); as duas
coisas podem acontecer ao mesmo tempo porque toda retomada passa por db.trava_das_respostas.
"""
import argparse
import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

import db
from agente import criar_cliente, vencer_pendencias

RAIZ = Path(__file__).resolve().parent.parent
LOG_PADRAO = RAIZ / "logs" / "vigia" / "vigia.log"
LOGS_DO_LACO = RAIZ / "logs" / "vigia"      # o laço, e a execução do grafo que caiu sem pendência; a pausa do grafo guarda a pasta do seu log
BATIMENTO = RAIZ / "dados" / "vigia-batimento.json"
INTERVALO_MAX_S = 30      # teto entre duas conferências; o vigia acorda antes se um prazo vence antes
MARGEM_S = 1              # acorda um segundo depois do `vence_em`, para não chegar antes dele

log = logging.getLogger("vigia")


def _agora() -> datetime:
    return datetime.now().astimezone()


def proxima_espera(con, agora: datetime | None = None, teto: float = INTERVALO_MAX_S) -> float:
    """Quantos segundos dormir: até o `vence_em` mais próximo (mais a margem), nunca mais que o
    teto (uma pendência nova pode chegar a qualquer momento) e nunca menos de 1 s."""
    agora = agora or _agora()
    prazos = [datetime.fromisoformat(p["vence_em"]) for p in db.pendencias_aguardando(con)]
    if not prazos:
        return teto
    falta = (min(prazos) - agora).total_seconds() + MARGEM_S
    return max(1.0, min(teto, falta))


def uma_volta(client, con, agora: datetime | None = None, log_dir: Path = LOGS_DO_LACO) -> list:
    """Uma conferência: o decaimento da memória episódica, a recuperação das execuções que uma
    queda deixou pela metade e o prazo das pendências, as mesmas rotinas que o main.py roda no
    começo de cada comando. Devolve os estados que venceram."""
    esquecidos = db.esquecer_episodios(con, agora)
    import grafo                            # aqui, e não no topo: os testes fixam o checkpointer antes
    for r in grafo.retomar_interrompidas(client=client, con=con, log_dir=log_dir, agora=agora):
        if "erro" in r:
            log.error("RECUPERAÇÃO FALHOU: %s (parou em %s): %s", r["id_ticket"], r["parou_em"], r["erro"])
        else:
            desfecho = r["estado"].desfecho or {}
            log.warning("EXECUÇÃO RETOMADA DEPOIS DE QUEDA: %s | parou em %s | desfecho: %s | log: %s",
                        r["id_ticket"], r["parou_em"], desfecho.get("acao"), r["log"])
    if esquecidos:
        log.info("memória episódica: %d episódio(s) com mais de %d dias removido(s)",
                 esquecidos, db.EPISODIO_MAX_DIAS)
    vencidos = vencer_pendencias(client=client, con=con, agora=agora, log_dir=log_dir, verbose=False)
    for e in vencidos:
        desfecho = e.desfecho or {}
        log.info("PRAZO VENCIDO: %s | %s | desfecho: %s | motivo: %s%s",
                 e.id_ticket, ((e.confirmacoes[-1].get("pendencia") or {}).get("ferramenta", "?")
                               if e.confirmacoes else "?"),
                 desfecho.get("acao"), desfecho.get("motivo"),
                 f" | GESTOR AVISADO (aviso {desfecho['aviso_gestor']})"
                 if desfecho.get("aviso_gestor") else "")
    return vencidos


def volta_protegida(client, teto: float = INTERVALO_MAX_S, log_dir: Path = LOGS_DO_LACO,
                    conectar=db.conectar) -> tuple[list | None, float]:
    """Uma volta que não derruba o vigia: abre a conexão, confere, fecha. Erro vira linha de log
    e a espera padrão; a próxima volta tenta de novo. Devolve (vencidos ou None, espera em s)."""
    try:
        con = conectar()
        try:
            vencidos = uma_volta(client, con, log_dir=log_dir)
            espera, aguardando = proxima_espera(con, teto=teto), len(db.pendencias_aguardando(con))
        finally:
            con.close()
    except Exception:                       # noqa: BLE001 - o serviço não pode morrer por uma volta
        log.exception("a volta falhou; tento de novo em %g s", teto)
        return None, teto
    gravar_batimento(aguardando=aguardando, vencidas_nesta_volta=len(vencidos),
                     proxima_volta=(_agora() + timedelta(seconds=espera)).isoformat(timespec="seconds"))
    return vencidos, espera


def gravar_batimento(caminho: Path | None = None, **dados) -> None:
    """O sinal de vida: quem é o vigia e quando foi a última volta. É só para leitura."""
    caminho = caminho or BATIMENTO
    try:
        caminho.write_text(json.dumps({"pid": os.getpid(),
                                       "ultima_volta": _agora().isoformat(timespec="seconds"),
                                       **dados}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.warning("não consegui gravar o sinal de vida em %s", caminho)


def situacao(caminho_batimento: Path | None = None, caminho_trava: Path | None = None) -> str:
    """Uma linha para o `main.py --pendencias`: o vigia está rodando, e quando foi a última volta."""
    instancia = db.travar_instancia(caminho_trava)
    rodando = instancia is None
    if instancia is not None:
        db._destravar(instancia)
        instancia.close()
    try:
        b = json.loads((caminho_batimento or BATIMENTO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        b = None
    if rodando:
        return ("vigia do prazo: rodando" + (f" (pid {b['pid']}), última conferência às "
                                             f"{b['ultima_volta']}" if b else ""))
    return ("vigia do prazo: PARADO; o prazo só é aplicado quando alguém roda um comando "
            "(python src/vigiar_prazos.py)" + (f". Última conferência: {b['ultima_volta']}" if b else ""))


def configurar_log(arquivo: Path) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    formato = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    em_arquivo = RotatingFileHandler(arquivo, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    em_arquivo.setFormatter(formato)
    log.addHandler(em_arquivo)
    if sys.stdout is not None:              # como serviço (pythonw, NSSM) pode não haver tela
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        na_tela = logging.StreamHandler(sys.stdout)
        na_tela.setFormatter(formato)
        log.addHandler(na_tela)
    log.setLevel(logging.INFO)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vigia do prazo de confirmação do analista.")
    ap.add_argument("--uma-vez", action="store_true",
                    help="uma conferência e sai (para rodar pelo Agendador de Tarefas ou pelo cron)")
    ap.add_argument("--intervalo", type=float, default=INTERVALO_MAX_S, metavar="S",
                    help=f"teto entre duas conferências, em segundos (padrão: {INTERVALO_MAX_S})")
    ap.add_argument("--log", type=Path, default=LOG_PADRAO, metavar="ARQUIVO",
                    help=f"arquivo do log do vigia (padrão: {LOG_PADRAO.relative_to(RAIZ)})")
    args = ap.parse_args(argv)
    configurar_log(args.log if args.log.is_absolute() else Path.cwd() / args.log)

    instancia = db.travar_instancia()
    if instancia is None:
        log.info("outro vigia já está rodando nesta máquina (%s); saindo", db.TRAVA_VIGIA.name)
        return 0
    load_dotenv(RAIZ / ".env")
    try:
        client = criar_cliente()            # o laço chama o modelo para a frase final depois do encaminhamento
    except KeyError as k:
        log.error("falta %s no .env: o vigia precisa da chave da API", k)
        return 1

    parar = threading.Event()
    def ao_receber_sinal(numero, _quadro):
        log.info("sinal %s recebido: paro depois da volta em curso", signal.Signals(numero).name)
        parar.set()
    for nome in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, nome):
            signal.signal(getattr(signal, nome), ao_receber_sinal)

    log.info("vigia iniciado (pid %d); prazo de confirmação conferido a cada %g s no máximo",
             os.getpid(), args.intervalo)
    try:
        while True:
            _, espera = volta_protegida(client, teto=args.intervalo)
            if args.uma_vez:
                break
            fim = _agora() + timedelta(seconds=espera)
            while not parar.is_set() and _agora() < fim:  # fatias de 1 s: o sinal é atendido logo
                parar.wait(min(1.0, (fim - _agora()).total_seconds()))
            if parar.is_set():
                break
    finally:
        db._destravar(instancia)
        instancia.close()
        log.info("vigia parado")
    return 0


if __name__ == "__main__":
    sys.exit(main())

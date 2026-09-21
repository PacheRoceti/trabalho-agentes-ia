"""Verificador (item 2.6): compara o que o agente FEZ com o gabarito humano.

Confere o estado no BANCO, não o texto que o modelo escreveu: o que vale é a
escrita que aconteceu. Um verificador que lê o texto final mede se o modelo
'diz' que agiu certo, não se agiu.
"""
import json
import unicodedata
from pathlib import Path

import db

GABARITO = json.loads((Path(__file__).resolve().parent.parent / "dados" / "gabarito.json")
                      .read_text(encoding="utf-8"))


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def verificar(id_ticket: str, estado, con) -> tuple[bool, list[str]]:
    esperado = GABARITO[id_ticket]
    falhas = []
    if estado.termino.value != "respondeu":
        falhas.append(f"terminou como '{estado.termino.value}' ({estado.motivo})")
    d = estado.desfecho or {}
    if d.get("acao") != esperado["acao"]:
        falhas.append(f"desfecho '{d.get('acao')}' em vez de '{esperado['acao']}'")
    for campo in ("kb_id", "time_destino", "prioridade"):
        if campo in esperado and d.get(campo) != esperado[campo]:
            falhas.append(f"{campo} '{d.get(campo)}' em vez de '{esperado[campo]}'")

    n_chamados = db.contar(con, "chamados_internos", id_ticket)
    n_encam = db.contar(con, "encaminhamentos", id_ticket)
    if n_chamados != (1 if esperado["chamado_interno"] else 0):
        falhas.append(f"{n_chamados} chamado(s) interno(s) gravado(s) para {id_ticket}")
    if n_encam > 1:
        falhas.append(f"{n_encam} encaminhamentos gravados (esperado no máximo 1)")

    if "resumo_menciona_algum" in esperado and n_chamados:
        resumo = con.execute("SELECT resumo FROM chamados_internos WHERE ticket_externo = ?",
                             (id_ticket,)).fetchone()["resumo"]
        if not any(p in _norm(resumo) for p in esperado["resumo_menciona_algum"]):
            falhas.append("resumo não registra a divergência entre o cliente e o histórico")
    if "mensagem_menciona_algum" in esperado and n_encam:
        msg = con.execute("SELECT mensagem FROM encaminhamentos WHERE ticket_externo = ?",
                          (id_ticket,)).fetchone()["mensagem"]
        if not any(p in _norm(msg) for p in esperado["mensagem_menciona_algum"]):
            falhas.append("a mensagem não sinaliza a divergência entre o relato e o log")
    if "mensagem_menciona_todos" in esperado and n_encam:
        msg = con.execute("SELECT mensagem FROM encaminhamentos WHERE ticket_externo = ?",
                          (id_ticket,)).fetchone()["mensagem"]
        faltam = [p for p in esperado["mensagem_menciona_todos"] if p not in _norm(msg)]
        if faltam:
            falhas.append(f"a mensagem não cita: {', '.join(faltam)}")
    return (not falhas), falhas

"""Mostra os traces gravados pelo sistema (src/telemetria.py), como árvore. Só lê; não chama a API.

    python ver_traces.py logs/minha-rodada/TKT-0007.trace.jsonl      # um chamado
    python ver_traces.py logs/minha-rodada                            # todos os da pasta
    python ver_traces.py logs/minha-rodada/TKT-0007.trace.jsonl --atributos   # com todos os atributos

Cada invocação do grafo é um trace (a execução nova e cada retomada); a linha da raiz traz o término,
a versão, o desfecho e os tokens. Span com erro aparece marcado com "!!".
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# O que a linha de cada span mostra, além do nome e da duração (o resto, com --atributos).
RESUMO = ("triagem.versao", "triagem.termino", "triagem.motivo", "triagem.desfecho",
          "triagem.kb_recuperados", "triagem.aprovacao.status", "triagem.aprovacao.por", "triagem.decisao",
          "triagem.nada_a_retomar", "triagem.pausou", "gen_ai.usage.input_tokens",
          "gen_ai.usage.output_tokens", "error.type")


def _instante(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def ler(caminho: Path) -> list[dict]:
    arquivos = sorted(caminho.glob("*.trace.jsonl")) if caminho.is_dir() else [caminho]
    spans = []
    for arquivo in arquivos:
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                spans.append(json.loads(linha))
    return spans


def imprimir(spans: list[dict], todos_os_atributos: bool = False):
    por_trace: dict[str, list[dict]] = {}
    for s in spans:
        por_trace.setdefault(s["context"]["trace_id"], []).append(s)
    raizes = sorted((s for s in spans if not s.get("parent_id")), key=lambda s: s["start_time"])
    for raiz in raizes:
        filhos: dict[str, list[dict]] = {}
        for s in por_trace[raiz["context"]["trace_id"]]:
            filhos.setdefault(s.get("parent_id"), []).append(s)
        atributos = raiz.get("attributes", {})
        print(f"\n{atributos.get('gen_ai.conversation.id', '?')}  trace {raiz['context']['trace_id'][2:14]}  "
              f"{raiz['start_time'][:19]}  execução {atributos.get('triagem.execucao_id', '?')}")
        _ramo(raiz, filhos, 0, todos_os_atributos)


def _ramo(span: dict, filhos: dict, nivel: int, todos: bool):
    ms = (_instante(span["end_time"]) - _instante(span["start_time"])).total_seconds() * 1000
    erro = "!! " if span.get("status", {}).get("status_code") == "ERROR" else ""
    atributos = span.get("attributes", {})
    mostrar = atributos if todos else {k: v for k, v in atributos.items() if k in RESUMO}
    extra = "  ".join(f"{k.split('.', 1)[-1]}={v}" for k, v in mostrar.items())
    print(f"{'  ' * nivel}{erro}{span['name']:<40} {ms:8.0f} ms  {extra}")
    for f in sorted(filhos.get(span["context"]["span_id"], []), key=lambda s: s["start_time"]):
        _ramo(f, filhos, nivel + 1, todos)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    caminho = Path(args[0])
    if not caminho.exists():
        sys.exit(f"Não existe: {caminho}")
    spans = ler(caminho)
    if not spans:
        sys.exit(f"Nenhum span em {caminho} (os traces são os arquivos *.trace.jsonl)")
    imprimir(spans, "--atributos" in sys.argv)


if __name__ == "__main__":
    main()

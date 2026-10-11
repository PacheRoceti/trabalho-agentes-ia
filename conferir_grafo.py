"""Conferência do grafo (Parte 2, item 6.4): imprime o que o grafo COMPILADO tem, para comparar
com o desenho de docs/grafo.md e docs/arquitetura.md.

    python conferir_grafo.py

Importa o grafo de verdade (o objeto GRAFO de src/grafo.py, o mesmo que main.py executa);
não há cópia do desenho aqui. Não chama o modelo, não precisa de chave e não toca o banco de
chamados. O checkpointer fica em memória, para a conferência não criar arquivo.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("CHECKPOINT_DB", ":memory:")
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import langgraph.version                                         # noqa: E402
from grafo import GRAFO, LIMITE_SUPERPASSOS, EstadoGrafo         # noqa: E402

desenho = GRAFO.get_graph()
nos = [n for n in desenho.nodes if not n.startswith("__")]

print(f"langgraph {langgraph.version.__version__}")
print(f"checkpointer: {type(GRAFO.checkpointer).__name__}   recursion_limit declarado: {LIMITE_SUPERPASSOS}")

print(f"\nNÓS ({len(nos)})")
for n in nos:
    print(f"  {n}")

fixas = [a for a in desenho.edges if not a.conditional]
condicionais = [a for a in desenho.edges if a.conditional]
print(f"\nARESTAS FIXAS ({len(fixas)})")
for a in fixas:
    print(f"  {a.source:<18} -> {a.target}")

print(f"\nARESTAS CONDICIONAIS ({len(condicionais)}), com a chave do mapa de destinos")
for a in condicionais:
    print(f"  {a.source:<18} -> {a.target:<18} [{a.data}]")

print("\nCAMPOS DO ESTADO, e o reducer de cada um")
for campo, tipo in EstadoGrafo.__annotations__.items():
    reducer = getattr(tipo, "__metadata__", None)
    print(f"  {campo:<22} {reducer[0].__name__ if reducer else '(sobrescreve)'}")

print("\nMERMAID (get_graph().draw_mermaid())")
print(desenho.draw_mermaid())

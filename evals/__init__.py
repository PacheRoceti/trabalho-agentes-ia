"""A suíte de avaliação da Parte 3 (docs/evals.md). Roda da raiz do repositório:

    python -m evals.rodar --versao 1.0.0
    python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# Os módulos de src/ importam uns aos outros sem pacote (`import db`): é o mesmo arranjo dos testes.
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

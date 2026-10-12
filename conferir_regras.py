"""Confere, nos logs de uma rodada do grafo, a regra aprendida R1 de src/prompts/regras-redigir-v2.md:
o texto redigido só cita domínio que veio nas informações recebidas. Não chama a API: só lê logs.

    python conferir_regras.py logs/grafo-redigir-v3-1 logs/grafo-redigir-v3-2

Para cada log, procura os domínios no texto do nó `redigir` e diz quais não aparecem no que o nó
recebeu (o texto do chamado, o registro de `consultar_ticket`, a triagem e os guias da busca).

LIMITE: é uma checagem por expressão regular, com uma lista curta de terminações. Só enxerga
domínio; IP, nome de servidor e nome de banco, que a regra também cita, não são conferidos.
"""
import json
import re
import sys
from pathlib import Path

DOMINIO = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com\.br|net\.br|org\.br|com|net|org|io|br)\b", re.I)
RECEBIDO_DE = ("consultar_ticket", "triagem", "buscar_base_conhecimento", "conferir_ressalva")


def conferir(log: dict) -> tuple[int, list[str]]:
    """Devolve (quantas redações o log tem, os domínios citados que o nó não recebeu)."""
    passos = log.get("passos") or []
    recebido = json.dumps([log.get("entrada")] + [p.get("resultado") for p in passos
                                                  if p["ferramenta"] in RECEBIDO_DE],
                          ensure_ascii=False).lower()
    textos = [(p.get("resultado") or {}).get("texto") or "" for p in passos
              if p["ferramenta"] == "redigir" and not (p.get("argumentos") or {}).get("texto_padrao")]
    inventados = sorted({d.lower() for t in textos for d in DOMINIO.findall(t)
                         if d.lower() not in recebido})
    return len(textos), inventados


def main(pastas: list[str]) -> None:
    if not pastas:
        sys.exit(__doc__)
    for pasta in pastas:
        redacoes = com_defeito = 0
        print(f"\n{pasta}")
        for arquivo in sorted(Path(pasta).glob("TKT-*.json")):
            log = json.loads(arquivo.read_text(encoding="utf-8"))
            n, inventados = conferir(log)
            redacoes += n
            com_defeito += bool(inventados)
            if inventados:
                print(f"  {arquivo.name}  prompt: {log.get('prompt')}\n"
                      f"    domínio que o nó não recebeu: {', '.join(inventados)}")
        print(f"  {redacoes} redação(ões) do modelo; {com_defeito} log(s) com domínio não recebido")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])

"""Lê um log de execução (logs/*.json) e mostra a trajetória de forma legível.

    python src/ver_log.py logs/TKT-0003.json
    python src/ver_log.py logs/comparacao/ministral-3b-latest/TKT-0001.json

Serve para explicar POR QUE um caso falhou: quais ferramentas o modelo chamou, com
quais termos, que score a base devolveu, se precisou de lembrete e como terminou.
"""
import json
import sys

if len(sys.argv) < 2:
    sys.exit("uso: python src/ver_log.py <arquivo.json>")

d = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"{d['id_ticket']} | modelo: {d['modelo']} | prompt: {d.get('prompt', '?')}")
print(f"término: {d['termino']} | motivo: {d['motivo']} | lembretes: {d.get('lembretes', 0)}")
print(f"tokens: {d['tokens_entrada'] + d['tokens_saida']} | custo simulado: US$ {d['custo_usd']}")
print(f"scores da base nesta execução: {d['scores_kb'] or 'nenhuma busca'}")
print("\nPASSOS")
for p in d["passos"]:
    args = json.dumps(p["argumentos"], ensure_ascii=False)
    print(f"  {p['indice']}. {p['ferramenta']}  {args}")
    if p["erro"]:
        print(f"       -> ERRO: {p['erro']['erro']}")
    elif p["ferramenta"] == "buscar_base_conhecimento":
        achados = [(r["kb_id"], r["score"]) for r in p["resultado"].get("resultados", [])]
        print(f"       -> artigos (kb_id, score): {achados or 'nenhum'}")
print(f"\ndesfecho: {d['desfecho']}")
print(f"resposta final do modelo: {d['resposta']}")

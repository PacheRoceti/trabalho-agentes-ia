"""O juiz de uma propriedade sem gabarito, e a validação dele contra rótulos humanos (Parte 3, §1.3).

A propriedade: a correção sugerida ao analista é fiel ao procedimento recuperado (rubrica em
evals/prompts/juiz-v1.0.0.md). Dois passos, nesta ordem, e o primeiro é de pessoa:

    python -m evals.juiz separar evals/resultados/<rodada>      # monta evals/juiz/rotulos-v1.0.0.json (só lê)
    # uma pessoa do grupo preenche, em cada item, `rotulo_humano` (SIM ou NAO) e `nota`, e, no topo do
    # arquivo, `rotulado_por` e o `limiar` de adoção ANTES de rodar o passo seguinte
    python -m evals.juiz validar evals/juiz/rotulos-v1.0.0.json  # USA A API: o juiz em cada item

O `validar` recusa rodar se faltar rótulo, nota, rotulador ou limiar: o limiar é declarado antes de
medir, e um limiar escrito depois de ver o número não é limiar. Ele grava evals/juiz/validacao-<data>.json
com a matriz de concordância juiz × humano e os desacordos, que uma pessoa lê um a um e classifica
(defeito do juiz, da rubrica ou do rótulo humano) no campo `classificacao`.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from evals import RAIZ

RUBRICA = RAIZ / "evals" / "prompts" / "juiz-v1.0.0.md"
VERSAO_RUBRICA = "1.0.0"
PASTA = RAIZ / "evals" / "juiz"


def _sem_cabecalho(texto: str) -> str:
    return re.sub(r"^<!--.*?-->\s*", "", texto, flags=re.S).strip()


def _texto_e_guias(log: dict) -> tuple[str, str, list[dict]] | None:
    """O texto que vai ao analista (resumo do chamado ou anotação) e os guias que a busca devolveu."""
    texto, acao = None, None
    for p in log.get("passos") or []:
        a = p.get("argumentos") or {}
        if p["ferramenta"] == "abrir_chamado_interno":
            texto, acao = a.get("resumo"), "abrir_chamado_interno"
        elif p["ferramenta"] == "registrar_encaminhamento" and a.get("destino") == "anotacao_interna":
            texto, acao = a.get("mensagem"), "anotacao_interna"
    if not texto:
        return None
    guias = []
    for p in log.get("passos") or []:
        if p["ferramenta"] == "buscar_base_conhecimento":
            guias = [{k: r.get(k) for k in ("kb_id", "titulo", "causa", "solucao")}
                     for r in (p.get("resultado") or {}).get("resultados", [])]
    return texto, acao, guias


def separar(pasta_rodada: Path) -> Path:
    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / f"rotulos-v{VERSAO_RUBRICA}.json"
    if destino.exists():
        sys.exit(f"{destino} já existe: os rótulos são trabalho de pessoa e não são sobrescritos.")
    itens = []
    for arquivo in sorted(pasta_rodada.glob("logs/rep-*/TKT-*.json")):
        log = json.loads(arquivo.read_text(encoding="utf-8"))
        achado = _texto_e_guias(log)
        if achado:
            texto, acao, guias = achado
            itens.append({"id": log["id_ticket"], "log": arquivo.relative_to(RAIZ).as_posix(), "acao": acao,
                          "procedimentos": guias, "texto": texto, "rotulo_humano": None, "nota": ""})
    dados = {
        "rubrica": RUBRICA.relative_to(RAIZ).as_posix(), "versao_rubrica": VERSAO_RUBRICA,
        "rodada": pasta_rodada.name,
        "_leia": ("Para cada item: rotulo_humano = SIM se todo passo do texto está na causa ou na solução "
                  "de algum procedimento, NAO se algum não está (a mesma rubrica do juiz); nota = uma frase "
                  "dizendo por quê. Preencha rotulado_por e o limiar ANTES de rodar o juiz. Não leia o "
                  "veredito do juiz antes de rotular: ele ainda não existe quando este arquivo é preenchido."),
        "rotulado_por": None,
        "limiar": {"concordancia_minima_pct": None, "max_falsos_sim": None, "declarado_em": None},
        "itens": itens,
    }
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def _faltas(dados: dict) -> list[str]:
    faltas = []
    if not dados.get("rotulado_por"):
        faltas.append("rotulado_por")
    limiar = dados.get("limiar") or {}
    for campo in ("concordancia_minima_pct", "max_falsos_sim", "declarado_em"):
        if limiar.get(campo) in (None, ""):
            faltas.append(f"limiar.{campo}")
    for item in dados["itens"]:
        if item.get("rotulo_humano") not in ("SIM", "NAO"):
            faltas.append(f"{item['id']}: rotulo_humano")
        if not (item.get("nota") or "").strip():
            faltas.append(f"{item['id']}: nota")
    return faltas


def julgar(client, modelo: str, item: dict, rubrica: str) -> dict:
    procedimentos = "\n".join(f"{g['kb_id']} - {g['titulo']}\nCausa: {g['causa']}\nSolução: {g['solucao']}"
                              for g in item["procedimentos"]) or "(nenhum)"
    resp = client.chat.completions.create(
        model=modelo, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": rubrica},
                  {"role": "user", "content": f"PROCEDIMENTO:\n{procedimentos}\n\nTEXTO:\n{item['texto']}"}])
    bruto = (resp.choices[0].message.content or "").strip()
    try:
        saida = json.loads(bruto)
        veredito = saida.get("veredito")
    except json.JSONDecodeError:
        saida, veredito = {"bruto": bruto}, None
    return {"veredito": veredito if veredito in ("SIM", "NAO") else None, "saida": saida}


def matriz(itens: list[dict]) -> dict:
    """Linhas: o juiz; colunas: o humano. Falso SIM = o juiz aprova o que o humano reprovou."""
    m = {"juiz_SIM_humano_SIM": 0, "juiz_SIM_humano_NAO": 0, "juiz_NAO_humano_SIM": 0,
         "juiz_NAO_humano_NAO": 0, "juiz_sem_veredito": 0}
    for i in itens:
        if i["juiz"]["veredito"] is None:
            m["juiz_sem_veredito"] += 1
        else:
            m[f"juiz_{i['juiz']['veredito']}_humano_{i['rotulo_humano']}"] += 1
    total = len(itens)
    acordos = m["juiz_SIM_humano_SIM"] + m["juiz_NAO_humano_NAO"]
    return {**m, "total": total, "concordancia_pct": round(100 * acordos / total, 1) if total else None,
            "falsos_sim": m["juiz_SIM_humano_NAO"]}


def validar(arquivo: Path):
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
    import main
    from evals.rodar import Ritmo, cliente_com_ritmo
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    faltas = _faltas(dados)
    if faltas:
        sys.exit("O arquivo de rótulos não está pronto; o juiz não foi rodado. Falta:\n  " + "\n  ".join(faltas))
    client, modelo, _ = main.preparar_api()
    client = cliente_com_ritmo(client, Ritmo(2))
    rubrica = _sem_cabecalho(RUBRICA.read_text(encoding="utf-8"))
    for item in dados["itens"]:
        item["juiz"] = julgar(client, modelo, item, rubrica)
        print(f"  {item['id']}  humano {item['rotulo_humano']}  juiz {item['juiz']['veredito']}")
    m = matriz(dados["itens"])
    limiar = dados["limiar"]
    adotado = (m["concordancia_pct"] is not None and m["concordancia_pct"] >= limiar["concordancia_minima_pct"]
               and m["falsos_sim"] <= limiar["max_falsos_sim"] and m["juiz_sem_veredito"] == 0)
    resultado = {
        "rubrica": dados["rubrica"], "versao_rubrica": dados["versao_rubrica"], "modelo": modelo,
        "rotulos": arquivo.relative_to(RAIZ).as_posix(), "rotulado_por": dados["rotulado_por"],
        "limiar": limiar, "matriz": m, "adotado": adotado,
        "executado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "desacordos": [{"id": i["id"], "humano": i["rotulo_humano"], "nota_humana": i["nota"],
                        "juiz": i["juiz"]["veredito"], "saida_do_juiz": i["juiz"]["saida"],
                        "classificacao": None}           # defeito do juiz | da rubrica | do rótulo humano
                       for i in dados["itens"] if i["juiz"]["veredito"] != i["rotulo_humano"]],
        "itens": dados["itens"],
    }
    destino = PASTA / f"validacao-v{dados['versao_rubrica']}-{datetime.now():%Y-%m-%d-%H%M}.json"
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nMATRIZ (linha: juiz; coluna: humano)\n"
          f"              humano SIM   humano NAO\n"
          f"  juiz SIM    {m['juiz_SIM_humano_SIM']:10d}   {m['juiz_SIM_humano_NAO']:10d}\n"
          f"  juiz NAO    {m['juiz_NAO_humano_SIM']:10d}   {m['juiz_NAO_humano_NAO']:10d}\n"
          f"  sem veredito: {m['juiz_sem_veredito']}\n"
          f"concordância {m['concordancia_pct']}% (limiar {limiar['concordancia_minima_pct']}%), "
          f"falsos SIM {m['falsos_sim']} (máximo {limiar['max_falsos_sim']}): "
          f"{'ADOTADO' if adotado else 'NÃO ADOTADO'}\n"
          f"{len(resultado['desacordos'])} desacordo(s) para ler e classificar em {destino.relative_to(RAIZ).as_posix()}")


def main_cli():
    if len(sys.argv) != 3 or sys.argv[1] not in ("separar", "validar"):
        sys.exit(__doc__)
    if sys.argv[1] == "separar":
        destino = separar(Path(sys.argv[2]).resolve())
        n = len(json.loads(destino.read_text(encoding="utf-8"))["itens"])
        print(f"{n} itens em {destino.relative_to(RAIZ).as_posix()}: falta rotular (pessoa do grupo)")
    else:
        validar(Path(sys.argv[2]).resolve())


if __name__ == "__main__":
    main_cli()

"""Diagnóstico: faz UMA chamada mínima à API e mostra o que o provedor respondeu.

    python src/testar_api.py                  # usa LLM_MODELO do .env
    python src/testar_api.py open-mistral-nemo   # testa outro modelo

Serve para separar 'o problema é o meu código' de 'o problema é a chave, o
modelo ou o limite do plano'. Não imprime a chave.
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

for var in ("LLM_BASE_URL", "OPENAI_API_KEY", "LLM_MODELO"):
    if not os.environ.get(var):
        sys.exit(f"Falta a variável {var} no .env")

modelo = sys.argv[1] if len(sys.argv) > 1 else os.environ["LLM_MODELO"]
chave = os.environ["OPENAI_API_KEY"]
print(f"endereço: {os.environ['LLM_BASE_URL']}")
print(f"modelo:   {modelo}")
print(f"chave:    {len(chave)} caracteres, começa com '{chave[:3]}...' (o restante não é mostrado)")

client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=chave, max_retries=0)


def cabecalhos_uteis(headers) -> None:
    achou = False
    for k, v in headers.items():
        if "ratelimit" in k.lower() or "retry" in k.lower() or "limit" in k.lower():
            print(f"   {k}: {v}")
            achou = True
    if not achou:
        print("   (o provedor não devolveu cabeçalhos de limite)")


t0 = time.monotonic()
try:
    bruto = client.chat.completions.with_raw_response.create(
        model=modelo, max_tokens=5,
        messages=[{"role": "user", "content": "Responda apenas: ok"}])
    resposta = bruto.parse()
    print(f"\nRESULTADO: FUNCIONOU em {time.monotonic() - t0:.1f}s")
    print(f"   resposta do modelo: {resposta.choices[0].message.content!r}")
    print(f"   tokens: {resposta.usage.prompt_tokens} entrada / {resposta.usage.completion_tokens} saída")
    cabecalhos_uteis(bruto.headers)
except APIStatusError as e:
    print(f"\nRESULTADO: A API RECUSOU, status {e.status_code}, em {time.monotonic() - t0:.1f}s")
    print(f"   mensagem: {e}")
    cabecalhos_uteis(e.response.headers)
    dicas = {401: "chave inválida, revogada ou de outra conta",
             404: "esse nome de modelo não existe para a sua chave",
             429: "limite de requisições ou de uso da chave/plano"}
    print(f"   provável causa: {dicas.get(e.status_code, 'ver a mensagem acima')}")
except APIConnectionError as e:
    print(f"\nRESULTADO: NÃO CONECTOU ({e}). Confira a internet e o LLM_BASE_URL.")

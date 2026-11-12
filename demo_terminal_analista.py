"""Janela do analista na demonstração (demonstrar_apresentacao.py, passo 4).

Roda numa janela de terminal própria, aberta pelo demonstrador, para o vídeo mostrar que a resposta
ao H1 vem de OUTRO processo. Executa `python src/main.py <argumentos>`, mostra a saída ao vivo, grava
uma cópia no arquivo pedido e fecha sozinha depois de alguns segundos.

    python demo_terminal_analista.py ARQUIVO --aprovar TKT-0003
"""
import os
import subprocess
import sys
import time

SEGUNDOS_ABERTA = 12


def main():
    arquivo, argumentos = sys.argv[1], sys.argv[2:]
    if os.name == "nt":
        os.system("title TERMINAL DO ANALISTA")
        os.system("color 1F")               # fundo azul: a outra janela é a do demonstrador
        os.system("chcp 65001 >nul")
    print("=" * 80)
    print(f"TERMINAL DO ANALISTA  ·  outro processo (PID {os.getpid()})")
    print("=" * 80)
    print("$ python src/main.py " + " ".join(argumentos))
    print()
    proc = subprocess.Popen([sys.executable, "src/main.py", *argumentos], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    with open(arquivo, "w", encoding="utf-8") as f:
        for linha in proc.stdout:
            print(linha, end="", flush=True)
            f.write(linha)
    proc.wait()
    print()
    print(f"(esta janela fecha em {SEGUNDOS_ABERTA} s)")
    time.sleep(SEGUNDOS_ABERTA)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()

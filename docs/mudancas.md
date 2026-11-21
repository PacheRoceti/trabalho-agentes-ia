# Mudanças desde a Parte 2 (Parte 3, item 0)

> **Estado deste documento: 20/11/2026.** É também o histórico de mudanças que o
> `docs/model-card.md` cobra no campo 12. A versão do sistema mora em `src/versao.py` e vai à raiz
> de cada trace; o commit vai ao log e ao trace de cada execução.

**A base.** A entrega da Parte 2 é tomada aqui como o commit `8cac30b` (17/10/2026), o último antes
do primeiro trabalho da Parte 3 (o exercício da aula 14, em 23/10/2026). **A confirmar pelo grupo.**

## 1. As correções que a Parte 2 apontou

**Nenhuma devolução da correção da Parte 2 está registrada no repositório** até 20/11/2026. Se o
professor apontou defeitos, eles entram aqui primeiro: o que estava errado, o que mudou e o commit.

## 2. As versões do sistema

| Versão | O que muda no comportamento | Commit | Medida em |
|---|---|---|---|
| **1.0.0** | nada na decisão: é o sistema da Parte 2 (`8cac30b`), com o trace OpenTelemetry por cima (o trace observa e não muda desfecho). A constante `VERSAO` nasce aqui | `ca4a8bc` | **39 de 44** (88,6%), uma repetição: `evals/resultados/v1.0.0-2026-11-20-2129/`, commitado em `3f1fd54` (`docs/evals.md` §4.3) |
| **1.1.0** | os três controles de segurança (`docs/seguranca.md` §3): o C1 recusa o texto do modelo com comando fora do guia, o que pode trocar um desfecho por `erro_fatal`; o C2 recusa o `--auto-aprovar` avulso; o C3 para de retomar a execução que falha três vezes | `fa74011` | **40 de 44** (90,9%), uma repetição: `evals/resultados/v1.1.0-2026-11-20-2244/`. A diferença para a 1.0.0 é um caso (o `TKT-0136`), decidido pela triagem do modelo e não pelos controles: os controles não pioraram nada, e o benefício deles não é medido pelo dataset (`docs/evals.md` §4.3) |

**A ordem importa para a comparação.** A rodada da 1.0.0 mediu o código **sem** os controles (a etapa 3 ficou guardada fora da pasta durante a rodada),
para a comparação com a 1.1.0 mostrar o efeito deles (`docs/evals.md` §4). As duas rodadas foram
feitas em 20/11/2026.

## 3. As mudanças, uma a uma

| Data | Commit | Autor | O que mudou | Muda o comportamento? |
|---|---|---|---|---|
| 23/10/2026 | `67f8691` | Pedro Roceti Pache | `exercicios/aula14-respostas.md`: os dez riscos no case, o rascunho do `docs/seguranca.md` | não (documento) |
| 11/11/2026 | `9854e24` | Pedro Roceti Pache | a suíte de avaliação: `evals/` (dataset v1.0.0 com 44 casos, `rodar`, `comparar`, as checagens em três níveis), `tests/test_evals.py`, `docs/evals.md`; no `src/main.py`, a preparação do cliente e dos preços saiu de `main()` para `preparar_api()`, para a suíte usar a mesma; o `demonstrar_apresentacao.py` | não: o `preparar_api` faz o que `main()` fazia |
| 11/11/2026 | `2210d97` | Pedro Roceti Pache | `CLAUDE.md` | não |
| 11/11/2026 | `adc20ca` | Pedro Roceti Pache | a gravação da demonstração para os slides (`demo_terminal_analista.py`, `gravar-demo.bat`, `logs/apresentacao-*`) | não (só a demonstração) |
| 12/11/2026 | `554268c` | Pedro Roceti Pache | a demonstração para quando o H1 não pausa (por exemplo, por um 429 do plano gratuito), e um vídeo novo | não (só a demonstração) |
| 20/11/2026 | `ca4a8bc` | Pedro | **versão 1.0.0**: o trace (`src/telemetria.py`, `src/versao.py`, `ver_traces.py`, `tests/test_trace.py`); no `src/grafo.py`, duas linhas trocadas por uma cada (`_no` e `_chamar`) e o bloco do trace no fim; no `src/vetorial.py`, uma linha trocada e o span do embedding no fim; o `evals/rodar.py` passa a usar `VERSAO` como padrão; o OpenTelemetry fixado no `requirements.txt`; o README ganha "Como ver os traces" | não na decisão; grava um arquivo `<id>.trace.jsonl` ao lado de cada log |
| 20/11/2026 | `3f1fd54` | Pedro | a rodada da versão 1.0.0 (`evals/resultados/v1.0.0-2026-11-20-2129/`, com os logs e os traces); na suíte, o ritmo das chamadas ao modelo (`evals/rodar.Ritmo`, `--chamadas-por-minuto`), por causa do limite de duas por janela de 60 s, e os testes dele; o `docs/evals.md` com os números e a decisão de uma repetição por versão | não no sistema; a suíte espera entre as chamadas |
| 20/11/2026 | `fa74011` | Pedro | **versão 1.1.0**: os controles C1, C2 e C3 (`src/grafo.py`, `src/db.py`, `src/main.py`, `src/vigiar_prazos.py`, `tests/test_seguranca.py`). O teste `test_sem_curadoria_o_tkt_0001_vira_chamado_p1_para_o_time_errado` (`tests/test_grafo.py`) ganhou um roteiro sem comando: o texto padrão dele mandava rodar o `certbot` do KB-101-A num desfecho decidido pelo KB-101 revogado, e o C1 o recusava, com razão. A asserção do teste não mudou | sim (ver §2) |
| 21/11/2026 | `1ef5558` | Pedro | os casos hostis (`TKT-0137` a `TKT-0139`, no seed e no gabarito), o dataset 1.1.0, a checagem `nao_repassou_o_conteudo_plantado`, o `validar` fora da checagem de laço, `evals/metricas.py`, o juiz (`evals/juiz.py`, a rubrica e o arquivo de rotulação) e a rodada completa da 1.1.0 | não no sistema |
| 21/11/2026 | `cbba2e2` (branch `medicao-v1.0.0`) | — | o `3f1fd54` com o `1ef5558` aplicado por cima, só para medir os casos hostis na 1.0.0 com o `src/` dela e os dados novos | não: é o `src/` da 1.0.0 |

## 4. O que ainda não tem versão

- **Os documentos da Parte 3** (`docs/seguranca.md`, este arquivo) não mudam o sistema e não têm
  versão própria; o histórico deles é o do git.
- **As linhas citadas nos docs da Parte 2** continuam valendo: as mudanças da 1.0.0 e da 1.1.0 em
  `src/grafo.py` são trocas de uma linha por outra ou blocos no fim do arquivo, e a linha 944
  (`Command(resume=...)`, citada no `docs/grafo.md` §4.1) não se moveu. No `src/main.py`, as três
  linhas do C2 dentro de `main()` deslocam as linhas seguintes da função. Nenhum doc cita, sem
  fixar o commit, linha do `main.py` depois da 327; o `docs/model-card.md` cita as linhas 340 a 342
  por um link fixado no commit `2ec98bc`, que continua apontando para o código daquele commit.

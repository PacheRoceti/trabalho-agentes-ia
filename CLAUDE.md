# CLAUDE.md

Orientações para o Claude Code trabalhar neste repositório.

## O que é

Trabalho de disciplina (Agentes de IA): um **agente de triagem de chamados de suporte** de uma empresa fictícia de hospedagem. Ele lê o texto livre do cliente, consulta o sistema de tickets e a base de conhecimento e grava **um desfecho** por chamado. Todo o projeto (código, identificadores, comentários, docs, commits) é em **português**; mantenha assim.

O caminho padrão é o **grafo em LangGraph** da Parte 2 (`src/grafo.py`, com checkpointer em SQLite e `interrupt` no H1), medido três vezes com o modelo real: 8 de 8 em `logs/grafo/`, `logs/grafo-rodada-2/` e `logs/grafo-rodada-3/` (10/10/2026), com a pausa do H1 demonstrada em `logs/grafo-pausa/` e a aprovação com edição em `logs/grafo-caso-6/`. O laço da **Parte 1** (próprio, sem framework, em `src/agente.py`) continua no repositório e roda com `main.py --laco`; `--prompt` implica `--laco`. RAG vetorial e memória existem só como desenho em `docs/`.

## Comandos

Ambiente: Windows, venv em `.venv`, Python 3.10+. Não há linter, formatador nem build.

```bash
.venv/Scripts/python.exe -m unittest discover -s tests        # testes offline: sem chave, sem rede (70 testes: 43 do laço, 27 do grafo)
.venv/Scripts/python.exe -m unittest tests.test_offline.TestAgente.test_orcamento_de_passos   # um teste só

python src/main.py TKT-0001 "texto do chamado"                # uma execução pelo grafo (usa a API); log em logs/grafo/
python src/main.py --todos --auto-aprovar                     # os 8 casos pelo grafo + verificador; SOBRESCREVE logs/grafo/
python src/main.py --todos --auto-aprovar --laco              # os 8 casos pelo laço; SOBRESCREVE logs/TKT-*.json
python src/main.py --todos --auto-aprovar --rodada NOME --prompt agente-v4.md   # laço (--prompt implica --laco); grava em logs/NOME/
python src/main.py --pendencias                               # ações à espera do analista (prazo de 20 min)
python src/main.py --aprovar TKT-0007                         # ou --rejeitar: responde à ação pendente (grafo ou laço)
python src/main.py --aprovar TKT-0007 --resumo "texto"        # aprovar EDITANDO o resumo (só no grafo; o laço recusa)
python src/main.py --reset                                    # recria dados/tickets.db a partir do seed
python conferir_grafo.py                                      # imprime o grafo compilado (sem chave); a saída está em docs/arquitetura.md §9
python src/comparar_modelos.py                                # 5 casos × 3 modelos -> docs/modelos-tabela-3.3.md
python src/ver_log.py logs/TKT-0003.json                      # trajetória legível de um log
python src/testar_api.py [modelo]                             # diagnóstico de chave/modelo/limite
```

Tudo que não é teste offline **chama a API** (Mistral, via biblioteca `openai` com `LLM_BASE_URL`) e depende do `.env` (`LLM_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODELO`, `PRECO_ENTRADA_USD`, `PRECO_SAIDA_USD`). O plano é gratuito e limitado a ~1 requisição/s. Não leia nem imprima o `.env`.

Os scripts de `src/` importam uns aos outros sem pacote (`import db`, `from agente import ...`): rode como `python src/arquivo.py`; os testes inserem `src/` no `sys.path`.

## Arquitetura

```
main.py ──▶ agente.rodar() ──▶ ferramentas.py ──▶ db.py ──▶ SQLite (dados/tickets.db)
   │              │
   │              └─▶ saida.montar_saida()   objeto pydantic validado
   └─▶ verificar.verificar()                 compara o BANCO com dados/gabarito.json
```

| Arquivo | Papel |
|---|---|
| `src/agente.py` | O laço. `Estado` (dataclass, é o estado de verdade; `historico` é só transporte para a API), `Passo`, `Orcamento` (8 passos · 30 mil tokens · US$ 0,05 · 90 s), `Termino`. Grava `logs/<id>.json` no `finally`. |
| `src/ferramentas.py` | As 4 ferramentas, seus schemas (`SCHEMAS`) e as exceções `ErroRecuperavel` / `ErroFatal` / `PausaParaHumano`. Define `LIMIAR_CONFIANCA = 0.5`. |
| `src/db.py` | Única camada que toca o SQLite. Busca por palavras-chave (`buscar_kb`), prioridade, reincidência, idempotência. Não conhece o modelo. |
| `src/saida.py` | Contrato de saída (`Saida` = `resultado` + `fonte` + `suficiencia`), montado pelo código a partir do `Estado`, nunca do texto do modelo. |
| `src/grafo.py` | O grafo (Parte 2): `EstadoGrafo`, 11 nós, 4 arestas condicionais com mapa explícito, `GRAFO` compilado uma vez, `rodar_grafo()` / `retomar_grafo()` (mesma assinatura e retorno do laço). O modelo é chamado em `triagem` e `redigir` (JSON validado); o desfecho é do nó `decidir` (código). Reaproveita `db.py`, `saida.py` e funções de `ferramentas.py`; não muda o laço. Prompts: `triagem-v1.md` e `redigir-v1.md`. `LIMITE_SUPERPASSOS` é o `recursion_limit` declarado. Ao mudar nó ou aresta, rode `conferir_grafo.py` e atualize `docs/grafo.md` §1 e `docs/arquitetura.md` §9. |
| `src/verificar.py` | Verificador: confere o que foi **gravado no banco** contra o gabarito. |
| `src/prompts/` | `agente-v5.md` e `lembrete-v1.md` são os prompts **em uso** (constantes `PROMPT_ARQUIVO` / `LEMBRETE_ARQUIVO` em `agente.py`). v1 a v4 são histórico. |
| `dados/seed.sql` | Schema + dados fictícios: `clientes`, `tickets_externos`, `kb_artigos`, `chamados_internos`, `encaminhamentos`. As tabelas `pendencias` e `avisos_gestor` não são do seed: nascem em `db.py` (`SQL_PENDENCIAS`, `SQL_AVISOS_GESTOR`). |
| `dados/gabarito.json` | Resposta esperada dos 8 casos (`TKT-0001`…`0007` e o inexistente `TKT-0999`). Chaves com `_` são notas. |

### Princípio central: o modelo decide, o código garante

- **Modelo:** classifica o assunto, escolhe termos de busca, escolhe o desfecho, redige resumo/mensagem, corrige a chamada após um erro.
- **Código:** valida id, calcula o score da busca, aplica o portão de confiança, define categoria/time/prioridade (vêm do artigo da base + reincidência), garante idempotência, pede confirmação humana, impõe o orçamento, registra o término.

Ao mexer, preserve estas invariantes (cada uma tem teste em `tests/test_offline.py`):

- **Regra de domínio por ausência de ferramenta.** O agente nunca encerra chamado, altera prioridade ou executa correção porque essas ferramentas não existem. Não as crie.
- **Erro de ferramenta é dado.** `ErroRecuperavel` volta ao modelo como observação com `esperado` e `sugestao`; só `ErroFatal` e `PausaParaHumano` (a espera pelo analista) derrubam o laço.
- **Portão de confiança em código.** `abrir_chamado_interno` e `anotacao_interna` exigem `kb_id` vindo de uma busca desta execução (`estado.scores_kb`) com score ≥ 0,5 e `acao_padrao` compatível (`escalar` / `anotar`).
- **Um desfecho por execução** (`_exigir_sem_desfecho`) e **no máximo um `devolver_cliente` por chamado**, conferido no banco.
- **Escrita irreversível pede confirmação, com prazo.** `abrir_chamado_interno` chama `estado.confirmar()`. Com confirmador (`--auto-aprovar`, testes) a resposta vem na hora. Sem confirmador, a ação vai para a tabela `pendencias` com `vence_em` (`PRAZO_CONFIRMACAO_MIN = 20`), o `Estado` é guardado como checkpoint e a execução termina em `aguardando_humano`, sem gravar nada. `agente.retomar()` conclui: aprovar no prazo abre o chamado; rejeitar (motivo `acao_rejeitada`) e prazo vencido (motivo `confirmacao_nao_recebida`) fazem o **código** gravar `fila_humana` com as considerações do agente (`encaminhar_pendencia`). No prazo vencido de um chamado que seria **P1** (`db.prioridade_prevista`), o código grava também um aviso ao gestor na tabela `avisos_gestor`. Rejeição dada na hora por um confirmador (`AcaoRejeitada`) segue o mesmo caminho e não derruba o laço. O relógio vale antes da pessoa: aprovação tardia não abre chamado. Depois da escrita o laço continua, para o modelo dar a frase final.
- **Aprovar editando muda só o resumo, e só no grafo.** `--aprovar X --resumo "..."` chega a `retomar_grafo(resumo=...)`, que confere o texto pela mesma regra do texto do modelo (`_erro_do_texto`) **antes** de responder ao `interrupt`: edição recusada levanta `EdicaoRecusada` e não gasta a aprovação. Categoria, time, prioridade e `kb_id` não são editáveis (regra do `case.md` §2.1). O log guarda `resumo_original` e `resumo_aprovado` em `confirmacoes`. A pendência do grafo traz `prioridade_prevista`, só para a tela.
- **O prazo é conferido, não cronometrado.** Não há processo em segundo plano: `vencer_pendencias()` roda no começo de cada comando do `main.py` (menos `--todos`). A espera não conta no teto de 90 s.
- **`fila_humana` para chamado existente só depois de uma busca**, salvo `motivo="fora_da_alcada"`.
- **`devolver_cliente` não pode citar informação interna** (`TERMOS_INTERNOS` + nomes de times).
- **Lembrete:** se o modelo encerra sem desfecho, o laço reenvia `lembrete-v1.md` até `MAX_LEMBRETES` (2) vezes; depois, `erro_fatal`.
- **Toda execução termina com um `Termino` e um motivo**, e a saída passa pelo schema pydantic.

### A busca (`db.buscar_kb`)

Sobreposição de palavras: `score = casados / (casados + nao_casados / 2)`, com casamento por radical de 4 letras, lista `GENERICAS` descartada e `SINONIMOS` (paliativo assumido). O score é multiplicado por `REDUTOR` (0,4) quando só um termo casa ou quando o relato cai numa ressalva do artigo (coluna `nao_cobre`). É sabidamente imperfeita; o limiar 0,5 foi ajustado à mão para estes dados. Não a "conserte" com heurísticas novas sem pedido: é a motivação do RAG da Parte 2.

`db.AGORA` é uma data fixa (`2026-09-21 12:00`) para a reincidência (janela de 30 dias) ser reproduzível.

## Testes

`tests/test_offline.py` usa um `ModeloRoteirizado` (roteiro fixo de `tool_calls`) no lugar do cliente da API. Prova o que é do **código**; não prova que um modelo real escolhe certo, o que só `main.py --todos` mede. Ao mudar ferramenta, busca, seed ou gabarito, rode os testes offline e ajuste `ROTEIROS` se o caminho esperado mudou.

## Convenções e cuidados

- **Prompts são versionados em arquivo.** Mudança de comportamento = novo `agente-vN.md` (ou revisão datada no cabeçalho), mantendo os anteriores. O bloco `<!-- -->` inicial é documentação (técnica, contrato, o que cada regra impede, resultado medido) e é descartado ao carregar; `{LIMIAR}` é substituído pelo valor do código.
- **`logs/` é evidência versionada.** `main.py` sem `--rodada` **sobrescreve** `logs/grafo/` (o padrão) ou, com `--laco`, `logs/TKT-*.json` e `logs/saida-demonstracao.txt`, que são citados em `README.md` e `docs/io.md` (com data, modelo e commit). `logs/grafo/` é citado em `docs/grafo.md` §6, `docs/rag.md` §5 e `docs/arquitetura.md` §8 e §9. Para experimentar, use `--rodada NOME`. Não edite logs à mão.
- **Não invente números.** Resultados em docs vêm de execuções reais; o que não foi medido é marcado "AINDA NÃO MEDIDO" / "não executado". O tom dos docs é de limite assumido ("limite honesto"); siga-o.
- **O gabarito não deve ser afrouxado** para um caso passar; mudanças nele levam uma `_nota` datada com o motivo.
- `dados/tickets.db` é gerado (ignorado pelo git). `recriar_banco()` derruba as tabelas em vez de apagar o arquivo, por causa do bloqueio de arquivo do Windows.
- Saída de terminal com acento: `main.py --todos` usa `Tee` para gravar em UTF-8; evite redirecionar com pipe do PowerShell.

## Diretrizes de Comportamento do Agente

### Evitar Alucinações
- **Baseie-se estritamente nas ferramentas e dados disponíveis:** Nunca invente resultados de consultas à base de conhecimento (`db.buscar_kb`), IDs de tickets, nomes de clientes ou dados do banco SQLite. Se uma ferramenta retornar vazio ou erro, trate o erro conforme a especificação ou informe a ausência de dados, sem preencher lacunas com informações fictícias.
- **Respeite os scores e limiares:** Não assuma correspondências parciais ou semânticas que não passem pelo limiar definido em código (`LIMIAR_CONFIANCA = 0.5` ou regras de pontuação da busca).
- **Separação estrita de papéis:** O modelo decide a classificação, termos de busca e redação com base nos fatos retornados pelas ferramentas; o código garante a validação e as regras de domínio. Não misture suposições do modelo com fatos do banco.

### Tomada de Decisão e Alinhamento ("Como" o Agente Funciona)
- **Pergunte quando houver ambiguidade de design ou fluxo:** Sempre que houver dúvida sobre **como** implementar um comportamento, estruturar um fluxo, alterar o laço de execução (`agente.py`), modificar contratos de saída (`saida.py`) ou introduzir qualquer lógica nova de tomada de decisão, **faça perguntas ao usuário** antes de prosseguir com implementações por conta própria.
- **Priorize o princípio central:** Lembre-se sempre de que *o modelo decide, o código garante*. Qualquer proposta de alteração que viole essa premissa deve ser validada explicitamente com o usuário.

## Documentação (`docs/`)

| Doc | Conteúdo |
|---|---|
| `case.md` | O caso de negócio: problema, usuários, workflow, verificador, riscos (§2.12 = o que o domínio ensinou). |
| `arquitetura.md` | O sistema **como está hoje** (Parte 2, item 3): o grafo. §1 a §7 = diagrama e as seis perguntas; §8 = nível de autonomia; §9 = conferência contra o código. A tabela de campos do estado está aqui (§4) e em `grafo.md` §3.1: mudam juntas. |
| `arquitetura-v2.md` | Histórico da Parte 1: do desenho no papel ao que foi construído, e o que as rodadas ensinaram. O §7 é a descrição do laço (`--laco`), com os portões ■G1 a ■G6. |
| `io.md` | Entrada, contrato de saída e cinco exemplos reais. |
| `prompts.md` | Plano de prompt engineering e o experimento da "regra da frase". |
| `modelos.md` | Escolha de modelo (3 Ministral), custo e comparação. `modelos-tabela-3.3.md` é gerado. |
| `grafo.md`, `humano.md` | O grafo e os pontos de parada da Parte 2, implementados em `src/grafo.py` (só o H1). |
| `rag.md`, `memoria.md`, `base-de-conhecimento-v2.md` | Desenho da Parte 2 ainda não implementado (busca vetorial, memória, corpus novo). |
| `fontes.md` | Casos de indústria consultados. |

`exercicios/` guarda exercícios de aula (ex.: plano de avaliação da aula 11).
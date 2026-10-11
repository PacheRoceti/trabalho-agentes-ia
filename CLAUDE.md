# CLAUDE.md

Orientações para o Claude Code trabalhar neste repositório.

## O que é

Trabalho de disciplina (Agentes de IA): um **agente de triagem de chamados de suporte** de uma empresa fictícia de hospedagem. Ele lê o texto livre do cliente, consulta o sistema de tickets e a base de conhecimento e grava **um desfecho** por chamado. Todo o projeto (código, identificadores, comentários, docs, commits) é em **português**; mantenha assim.

O caminho padrão é o **grafo em LangGraph** da Parte 2 (`src/grafo.py`, com checkpointer em SQLite e `interrupt` no H1), medido três vezes com o modelo real: 8 de 8 em `logs/grafo/`, `logs/grafo-rodada-2/` e `logs/grafo-rodada-3/` (10/10/2026), com a pausa do H1 demonstrada em `logs/grafo-pausa/` e a aprovação com edição em `logs/grafo-caso-6/`. O laço da **Parte 1** (próprio, sem framework, em `src/agente.py`) continua no repositório e roda com `main.py --laco`; `--prompt` implica `--laco`. A busca vetorial (híbrida) está em `src/vetorial.py`, medida em `docs/rag.md` §4; a memória existe só como desenho em `docs/`.

## Comandos

Ambiente: Windows, venv em `.venv`, Python 3.10+. Não há linter, formatador nem build.

```bash
.venv/Scripts/python.exe -m unittest discover -s tests        # testes offline: sem chave, sem rede (107 testes: 53 do laço, 39 do grafo, 15 da busca vetorial)
.venv/Scripts/python.exe -m unittest tests.test_offline.TestAgente.test_orcamento_de_passos   # um teste só

python src/main.py TKT-0001 "texto do chamado"                # uma execução pelo grafo (usa a API); log em logs/grafo/
python src/main.py --todos --auto-aprovar                     # os 8 casos pelo grafo + verificador; SOBRESCREVE logs/grafo/
python src/main.py --todos --auto-aprovar --laco              # os 8 casos pelo laço; SOBRESCREVE logs/TKT-*.json
python src/main.py --todos --auto-aprovar --rodada NOME --prompt agente-v4.md   # laço (--prompt implica --laco); grava em logs/NOME/
python src/main.py --pendencias                               # ações à espera do analista (prazo de 20 min)
python src/main.py --aprovar TKT-0007                         # ou --rejeitar: responde à ação pendente (grafo ou laço)
python src/main.py --aprovar TKT-0007 --resumo "texto"        # aprovar EDITANDO o resumo (só no grafo; o laço recusa)
python src/main.py --todos --auto-aprovar --sem-filtro-revogados --sem-desempate-data --rodada NOME   # EXPERIMENTO: desliga as regras de curadoria da busca, juntas ou uma só (exige --rodada)
python src/main.py --todos --auto-aprovar --busca palavra --rodada NOME   # EXPERIMENTO: o grafo busca só por palavra, como na Parte 1 (exige --rodada)
python src/medir_rag.py                                        # mede a busca vetorial (chama a API de embedding); grava logs/rag-medicao/
python src/medir_rag.py ressalva                               # mede o nó conferir_ressalva (chama o modelo de chat)
python src/medir_rag.py triagem                                # passa as perguntas pela triagem antes da busca (chama o modelo de chat)
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
| `src/grafo.py` | O grafo (Parte 2): `EstadoGrafo`, 12 nós, 6 arestas condicionais com mapa explícito, `GRAFO` compilado uma vez, `rodar_grafo()` / `retomar_grafo()` (mesma assinatura e retorno do laço). O modelo é chamado em `triagem`, `redigir` e, só quando o 1º guia declara situações que não cobre, em `conferir_ressalva` (JSON validado); o desfecho é do nó `decidir` (código). Reaproveita `db.py`, `saida.py` e funções de `ferramentas.py`; não muda o laço. Prompts: `triagem-v1.md`, `ressalva-v1.md` e `redigir-v1.md`. `LIMITE_SUPERPASSOS` é o `recursion_limit` declarado. Ao mudar nó ou aresta, rode `conferir_grafo.py` e atualize `docs/grafo.md` §1 e `docs/arquitetura.md` §9. |
| `src/vetorial.py` | A busca do grafo (`grafo.BUSCA = "vetorial"`): `mistral-embed` (1024 dimensões) sobre o relato, índice na tabela `kb_vetores`. O modo `"hibrida"` (fundida por RRF com `db.buscar_kb`) existe só para medir: não rendeu nada sobre o só vetorial (`docs/rag.md` §4.1). A curadoria vale antes do ranking; o score do portão é o cosseno numa escala com `LIMIAR_COSSENO` (0,80) = 0,5. Se o embedding falha, recua para a busca por palavra e diz isso em `busca`. O score é truncado em duas casas (não arredondado): score ≥ 0,5 só com cosseno ≥ 0,80. O gasto de embedding vai ao log (`tokens_embedding`), fora dos tetos do orçamento. As fichas de plano (`planos_fichas`) entram no índice mas não disputam o melhor guia. **Risco assumido:** nenhum limiar separa as perguntas sem resposta das com resposta (`docs/rag.md` §4.3), e 5 de 31 perguntas sem resposta agem mesmo com a triagem, quatro delas gravando uma `anotacao_interna` sem confirmação. O grupo decidiu aceitar e documentar; não pause a anotação nem mude o limiar para "consertar" isso sem pedido. A ressalva literal (`nao_cobre` escrita no relato) continua em código; a paráfrase é lida pelo modelo no nó `conferir_ressalva`, porque o vetor não a enxerga (`docs/rag.md` §4.2). Os testes offline do grafo fixam `BUSCA = "palavra"`; a busca vetorial tem os seus (`tests/test_vetorial.py`, embedder de mentira). |
| `src/verificar.py` | Verificador: confere o que foi **gravado no banco** contra o gabarito. |
| `src/prompts/` | `agente-v5.md` e `lembrete-v1.md` são os prompts **em uso** (constantes `PROMPT_ARQUIVO` / `LEMBRETE_ARQUIVO` em `agente.py`). v1 a v4 são histórico. |
| `dados/seed.sql` | Schema + dados fictícios: `clientes`, `tickets_externos`, `kb_artigos` (16 guias: 15 vigentes, KB-101-A e KB-102 a KB-115, e o KB-101 revogado), `planos_fichas` (as 3 fichas de plano, fonte E), `chamados_internos`, `encaminhamentos`. `kb_artigos` tem `data_publicacao` e `revogado_por`. O guia com letra é a atualização do guia sem letra (`KB-101` → `KB-101-A` → `KB-101-B`); o `KB-101` é a versão antiga e revogada do guia de SSL, posta de propósito, e o `KB-101-A` é a vigente (`docs/rag.md` §2.1). As tabelas `pendencias`, `avisos_gestor` e `kb_vetores` (o índice vetorial) não são do seed: nascem em `db.py` (`SQL_PENDENCIAS`, `SQL_AVISOS_GESTOR`, `SQL_VETORES`). |
| `dados/gabarito.json` | Resposta esperada dos 8 casos (`TKT-0001`…`0007` e o inexistente `TKT-0999`). Chaves com `_` são notas. |

### Princípio central: o modelo decide, o código garante

- **Modelo:** classifica o assunto, escolhe termos de busca, escolhe o desfecho, redige resumo/mensagem, corrige a chamada após um erro.
- **Código:** valida id, calcula o score da busca, aplica o portão de confiança, define categoria/time/prioridade (vêm do artigo da base + reincidência), garante idempotência, pede confirmação humana, impõe o orçamento, registra o término.

Ao mexer, preserve estas invariantes (cada uma tem teste em `tests/test_offline.py`):

- **Regra de domínio por ausência de ferramenta.** O agente nunca encerra chamado, altera prioridade ou executa correção porque essas ferramentas não existem. Não as crie.
- **Erro de ferramenta é dado.** `ErroRecuperavel` volta ao modelo como observação com `esperado` e `sugestao`; só `ErroFatal` e `PausaParaHumano` (a espera pelo analista) derrubam o laço.
- **A ressalva lida pelo modelo só baixa o score.** `conferir_ressalva` só roda quando o 1º guia passaria do limiar, não caiu numa ressalva literal e declara `nao_cobre`. O modelo diz se o relato cai numa situação da lista; o código multiplica o score por `db.REDUTOR` e só aceita uma `frase` que esteja na lista do guia. Nada no nó sobe o score nem cria uma exceção.
- **Portão de confiança em código.** `abrir_chamado_interno` e `anotacao_interna` exigem `kb_id` vindo de uma busca desta execução (`estado.scores_kb`) com score ≥ 0,5 e `acao_padrao` compatível (`escalar` / `anotar`).
- **Um desfecho por execução** (`_exigir_sem_desfecho`) e **no máximo um `devolver_cliente` por chamado**, conferido no banco.
- **Escrita irreversível pede confirmação, com prazo.** `abrir_chamado_interno` chama `estado.confirmar()`. Com confirmador (`--auto-aprovar`, testes) a resposta vem na hora. Sem confirmador, a ação vai para a tabela `pendencias` com `vence_em` (`PRAZO_CONFIRMACAO_MIN = 20`), o `Estado` é guardado como checkpoint e a execução termina em `aguardando_humano`, sem gravar nada. `agente.retomar()` conclui: aprovar no prazo abre o chamado; rejeitar (motivo `acao_rejeitada`) e prazo vencido (motivo `confirmacao_nao_recebida`) fazem o **código** gravar `fila_humana` com as considerações do agente (`encaminhar_pendencia`). No prazo vencido de um chamado que seria **P1** (`db.prioridade_prevista`), o código grava também um aviso ao gestor na tabela `avisos_gestor`. Rejeição dada na hora por um confirmador (`AcaoRejeitada`) segue o mesmo caminho e não derruba o laço. O relógio vale antes da pessoa: aprovação tardia não abre chamado. Depois da escrita o laço continua, para o modelo dar a frase final.
- **Aprovar editando muda só o resumo, e só no grafo.** `--aprovar X --resumo "..."` chega a `retomar_grafo(resumo=...)`, que confere o texto pela mesma regra do texto do modelo (`_erro_do_texto`) **antes** de responder ao `interrupt`: edição recusada levanta `EdicaoRecusada` e não gasta a aprovação. Categoria, time, prioridade e `kb_id` não são editáveis (regra do `case.md` §2.1). O log guarda `resumo_original` e `resumo_aprovado` em `confirmacoes`. A pendência do grafo traz, só para a tela, `prioridade_prevista`, `guia_publicado_em`, `guia_nao_cobre` (as situações que o guia declara não cobrir: a última barreira contra a exceção que o nó da ressalva não lê), `plano` e `escopo_do_plano` (a ficha do plano do cliente, contexto que também vai ao `redigir`; nenhuma regra de decisão usa o plano).
- **O prazo é conferido, não cronometrado.** Não há processo em segundo plano: `vencer_pendencias()` roda no começo de cada comando do `main.py` (menos `--todos`). A espera não conta no teto de 90 s.
- **Versão antiga de um guia não entra na busca.** Duas regras de curadoria em `db.buscar_kb`, antes do score: o filtro de `revogado_por` preenchido (`db.FILTRAR_REVOGADOS`) e o desempate por `data_publicacao` entre as versões de um mesmo procedimento, que é o id sem a letra (`db.DESEMPATAR_POR_DATA`; a letra só decide no mesmo dia). O descarte pelo desempate volta no resultado (`versoes_descartadas`). Como o portão só aceita `kb_id` de uma busca da execução, a versão antiga também não serve a uma escrita. `--sem-filtro-revogados` e `--sem-desempate-data` desligam as regras só para medir. Não remova o `KB-101` do seed: ele é a evidência do enunciado §4.2. Os logs anteriores a 11/10/2026 trazem `KB-101` para o guia que hoje é o `KB-101-A`.
- **`fila_humana` para chamado existente só depois de uma busca**, salvo `motivo="fora_da_alcada"`.
- **`devolver_cliente` não pode citar informação interna** (`TERMOS_INTERNOS` + nomes de times).
- **Lembrete:** se o modelo encerra sem desfecho, o laço reenvia `lembrete-v1.md` até `MAX_LEMBRETES` (2) vezes; depois, `erro_fatal`.
- **Toda execução termina com um `Termino` e um motivo**, e a saída passa pelo schema pydantic.

### A busca (`db.buscar_kb`)

Sobreposição de palavras: `score = casados / (casados + nao_casados / 2)`, com casamento por radical de 4 letras, lista `GENERICAS` descartada e `SINONIMOS` (paliativo assumido). Guias revogados e versões superadas ficam fora. O score é multiplicado por `REDUTOR` (0,4) quando só um termo casa ou quando o relato cai numa ressalva do artigo (coluna `nao_cobre`). É sabidamente imperfeita; o limiar 0,5 foi ajustado à mão para estes dados. Não a "conserte" com heurísticas novas sem pedido. É a busca do laço da Parte 1 e a metade "palavra" da busca híbrida do grafo.

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
| `rag.md` | RAG da Parte 2: formas de recuperar, corpus, as dez perguntas, a busca vetorial (§4) e as medições. Implementado. |
| `memoria.md`, `base-de-conhecimento-v2.md` | Desenho da Parte 2 ainda não implementado (memória, corpus novo). |
| `fontes.md` | Casos de indústria consultados. |

`exercicios/` guarda exercícios de aula (ex.: plano de avaliação da aula 11).
# Arquitetura v2 — o agente da Parte 1 (o que foi realmente construído)

> `v1` era o desenho no papel (`docs/arquitetura-v1.md`); esta é a versão que
> roda. A seção 5 lista o que mudou e por quê — é o histórico do raciocínio que
> o enunciado pede que fique no `git diff`.

## 1. O workflow (itens 2.3 e 4.4): 8 passos, quem decide em cada um

```
 1. ENTRADA     id do chamado externo (evento)                          [CÓDIGO]
 2. CONSULTA    consultar_ticket: texto, cliente, plano, histórico      [MODELO chama; CÓDIGO valida o id e lê o banco]
 3. TRIAGEM     técnico | comercial | insuficiente | relato × log divergente [MODELO]
 4. BUSCA       buscar_base_conhecimento(termos) -> top-3 com score     [MODELO escolhe os termos; CÓDIGO calcula o score]
 5. PORTÃO      melhor score >= 0.5 ?                                   [CÓDIGO]
 6. DESFECHO    5 saídas possíveis (ver tabela abaixo)                  [MODELO escolhe; CÓDIGO recusa o que viola regra]
 7. ESCRITA     abrir_chamado_interno    -> IRREVERSÍVEL, confirma o analista de suporte
                registrar_encaminhamento -> REVERSÍVEL, uma linha em fila/anotação
 8. TÉRMINO     registra POR QUE parou + log da trajetória              [CÓDIGO]
```

| Desfecho | Quando | Escrita | Reversível? | Quem confirma |
|---|---|---|---|---|
| `abrir_chamado_interno` | técnico, score ≥ 0.5, procedimento "escalar" | chamado no time responsável | **não** | analista de suporte (§2.2) |
| `anotacao_interna` | técnico, score ≥ 0.5, procedimento "anotar" | correção sugerida para o analista | sim | — (o analista é quem lê e executa) |
| `fila_humana` | técnico com score < 0.5 ou sem artigo; relato que contradiz o log anexado; ou id inexistente | pedido de olhar humano | sim | — |
| `fila_comercial` | assunto comercial | redireciona | sim | — |
| `devolver_cliente` | informação insuficiente | pergunta ao cliente | sim | — |

Nenhuma ferramenta encerra chamado, altera prioridade ou executa correção. A
regra de domínio ("o agente nunca executa, nunca fecha, nunca reclassifica") é
garantida pela **ausência da ferramenta**, não por um pedido no prompt.

## 2. Diagrama

```
                    id do chamado (TKT-0000)
                              │
                              ▼
   ┌─────────────────── LAÇO (src/agente.py) ───────────────────┐
   │  ORÇAMENTO: 8 passos · 30 mil tokens · US$ 0,05 · 90 s     │
   │  ESTADO: passos, tokens, custo, scores_kb, desfecho        │
   │                                                            │
   │    ┌─────────┐   tool_calls   ┌──────────────────────────┐ │
   │    │ MODELO  │ ─────────────▶ │ CÓDIGO: valida, executa  │ │
   │    │ decide  │ ◀───────────── │ e devolve resultado OU   │ │
   │    └─────────┘   observação   │ erro com "esperado" e    │ │
   │                               │ "sugestao" (como dado)   │ │
   │                               └────────────┬─────────────┘ │
   └────────────────────────────────────────────┼───────────────┘
                                                │
       ┌──────────────────┬─────────────────────┼───────────────────┐
       ▼                  ▼                     ▼                   ▼
 consultar_ticket   buscar_base_        abrir_chamado_       registrar_
   (leitura)        conhecimento        interno             encaminhamento
                    (leitura)           ESCRITA IRREVERSÍVEL  (escrita reversível)
                                          ▲     ▲
                          PORTÃO: score >= 0.5  CONFIRMAÇÃO do analista
                          (código)              (código)
       └──────────────────┴─────────────────────┴───────────────────┘
                                   │
                    SQLite  dados/tickets.db  (outra camada: src/db.py)
                    tickets · kb_artigos · chamados_internos · encaminhamentos

   TÉRMINOS (sempre registrados):
   respondeu · orcamento_esgotado · erro_fatal · aguardando_humano
```

## 3. Onde está a decisão que justifica um agente (e onde ela ainda não está)

O que exige decisão **em tempo de execução** é (a) interpretar o texto livre do
cliente, cruzá-lo com o log anexado e dizer se é técnico, comercial, insuficiente ou divergente; (b) traduzir o relato em
termos de busca; (c) decidir, diante do resultado da busca e do erro que uma
ferramenta devolve, se busca de novo, escreve ou pede um humano; e (d) redigir o
resumo do chamado marcando o que é afirmação do cliente e o que o sistema confirma
(caso de reincidência). Nenhuma dessas quatro cabe numa regra `if`.

**Honestidade sobre o nível de autonomia.** Na maioria das execuções o caminho é o
mesmo — consultar, buscar, escrever — com 3 a 5 passos. Isso é um **roteador com
laço curto**, não um agente aberto, e é o nível que escolhemos de propósito (regra
da disciplina: a menor autonomia que resolve). O que o coloca acima de um roteador
de uma chamada só é a **re-busca** (permitida uma vez quando o score fica baixo) e a
**recuperação de erro de ferramenta** (caso do id inexistente). Se o verificador
mostrar que nenhum dos casos depende dessas duas capacidades, o desenho correto é
um workflow com duas chamadas ao modelo, e diremos isso.

**Onde a decisão entra na Parte 2.** O RAG substitui a busca por palavra; o laço
ganha um teto de re-busca com reformulação da consulta; e o portão de confiança
passa a usar similaridade vetorial calibrada com perguntas sem resposta na base
(exercício 6), em vez do limiar 0.5 ajustado à mão.

## 4. Prompt engineering (item 4.3)

Um único ponto de chamada ao modelo — o laço em `src/agente.py` — com um único
prompt, `prompts/agente-v1.md`. O cabeçalho do arquivo documenta a técnica
(zero-shot com procedimento numerado e tool calling), o contrato de saída (o
resultado é a escrita da ferramenta, não o texto) e, linha por linha, o que cada
regra impede. `temperature=0`: classificação e escolha de ferramenta pedem o mesmo
resultado a cada execução. Sem few-shot nesta versão, para não contaminar o
conjunto de teste (`dados/gabarito.json`) com exemplos do prompt.

## 5. O que mudou em relação à v1, e por quê

| v1 (papel) | v2 (código) | Por quê |
|---|---|---|
| Pipeline: triagem → agregação → parecer → decisão → registro, cada etapa uma chamada | Um laço com 4 ferramentas | O enunciado da Parte 1 exige laço com estado, erro de ferramenta como dado e orçamento; "agregação" e "parecer" viraram o resumo que o modelo escreve ao gravar |
| `abrir_chamado_interno` automático e idempotente | Só depois da confirmação do analista; idempotência mantida | Regra do §2.3: escrita irreversível precisa de confirmação humana. Idempotência evita duplicata, não torna a escrita reversível |
| Confiança = número que o modelo informa (`confianca_parecer`) | Confiança = score calculado pelo **código** a partir da base | Confiança autodeclarada pelo modelo é mal calibrada; o portão precisa de um número que o modelo não controla |
| "Sem informação" → fila humana | "Sem informação" → `devolver_cliente` (como no case v2) | O case v2 define assim; a fila humana ficou para score baixo, id inexistente e ambiguidade |
| Ação "correção sugerida" sem ferramenta | `anotacao_interna` dentro de `registrar_encaminhamento` | Estava no case v2 e faltava no desenho |
| Prioridade decidida na etapa de decisão | Prioridade calculada em código (base do procedimento + reincidência) | Só o gestor reclassifica: nem o modelo nem o cliente devem definir prioridade |

## 6. O que as rodadas de teste acrescentaram (medido em `ministral-8b-latest`)

| Achado | Mudança | Onde |
|---|---|---|
| O modelo **narra** a ação ("encaminhei...") sem chamar a ferramenta e nada é gravado (`TKT-0999` nas rodadas 1 e 2; `TKT-0003` na 1) | **Lembrete no laço**: se o modelo encerra sem desfecho, recebe até 2 avisos como observação; sem efeito, término `erro_fatal` | `src/agente.py` (`LEMBRETE`, `MAX_LEMBRETES`); campo `lembretes` no log |
| Mais regras no prompt pioraram o resultado (5 → 3 de 7) | Prompt v3 = v1 + 2 frases; v2 mantida como registro do experimento | `prompts/agente-v*.md` |
| O verificador reprovou uma resposta correta por procurar palavras exatas | Regra do `TKT-0002` passou a exigir que a mensagem cite o serviço do relato e a causa do log | `dados/gabarito.json`, `src/verificar.py` |
| O modelo pequeno pula a busca no `TKT-0003` e escolhe a fila humana | **Não corrigido**: é erro de julgamento, para o lado seguro. Vira pergunta da comparação de modelos e da Parte 2 (busca obrigatória em código, ou modelo maior) | `docs/modelos.md` §3.3 |
| **Três das quatro falhas distintas nasceram da busca por palavra** (frases que diluem o score; limiar que cai no empate 0,5 e deixou um modelo abrir chamado indevido; flexão que não casa) | **Não corrigido na Parte 1**: é o motivo do RAG com limiar calibrado na Parte 2. A confirmação do analista é a rede de segurança enquanto isso | `docs/modelos.md` §3.3-B |

Consequência para a autonomia (§3): o lembrete é uma salvaguarda de código sobre o comportamento do
modelo, do mesmo tipo do portão de confiança e da confirmação do analista. O sistema continua sendo
um roteador com laço curto.

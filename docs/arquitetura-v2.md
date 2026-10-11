# Arquitetura v2 — o agente da Parte 1 (o que foi realmente construído)

> Esta é a versão que roda. A seção 5 lista o que mudou e por quê — é o histórico do raciocínio que
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
                                            (exceto devolver_cliente na Parte 2: a mensagem chega
                                            ao cliente e exige confirmação do analista)
 8. TÉRMINO     registra POR QUE parou + log da trajetória              [CÓDIGO]
```

| Desfecho | Quando | Escrita | Reversível? | Quem confirma |
|---|---|---|---|---|
| `abrir_chamado_interno` | técnico, score ≥ 0.5, procedimento "escalar" | chamado no time responsável | **não** | analista de suporte (§2.2) |
| `anotacao_interna` | técnico, score ≥ 0.5, procedimento "anotar" | correção sugerida para o analista | sim | — (o analista é quem lê e executa) |
| `fila_humana` | técnico com score < 0.5 ou sem artigo; relato que contradiz o log anexado; id inexistente; pedido fora da alçada (fechar chamado, mudar prioridade); na Parte 2, resposta do cliente ainda insuficiente ou 3 dias úteis sem resposta | pedido de olhar humano | sim | — |
| `fila_comercial` | assunto comercial | redireciona | sim | — |
| `devolver_cliente` | informação insuficiente (no máximo uma vez por chamado) | pedido de informação ao cliente | sim na Parte 1 (só grava o pedido); **não** na Parte 2 (a mensagem chega ao cliente) | analista de suporte, a partir da Parte 2 |

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
(exercício 6), em vez do limiar 0.5 ajustado à mão. A entrada do sistema passa a ser o **texto do
chamado**, entregue pelo evento de abertura e acompanhado do id do chamado (`thread_id`) e do
cliente; `consultar_ticket` fica para o histórico, o plano e o log anexado. A reincidência
continua gerando um chamado interno novo (o anterior não é reaberto), com a prioridade um nível acima
(P1 permanece P1; conta a ocorrência anterior nos últimos 30 dias).
O `devolver_cliente` passa a ser a única interação direta com o cliente: o agente envia, depois da confirmação do analista, um pedido de informação (no máximo um por
chamado), o grafo pausa com `interrupt` e a resposta do cliente retoma a mesma conversa
(`thread_id` = id do chamado) para refazer a triagem — o mesmo checkpointer da confirmação
do analista.

## 4. Prompt engineering (item 4.3)

Um único ponto de chamada ao modelo — o laço em `src/agente.py` — com um único
prompt, `src/prompts/agente-v5.md` (v1 e v2 ficam como histórico do experimento, `docs/modelos.md` §3.3-A).
O cabeçalho do arquivo documenta a técnica
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
| "Sem informação" → fila humana | "Sem informação" → `devolver_cliente` (como no case v2) | O case v2 define assim; a fila humana ficou para score baixo, id inexistente e divergência entre relato e log |
| Ação "correção sugerida" sem ferramenta | `anotacao_interna` dentro de `registrar_encaminhamento` | Estava no case v2 e faltava no desenho |
| Categoria do chamado interno escolhida pelo modelo (argumento `categoria` de `abrir_chamado_interno`; é o que aparece nos logs da Parte 1) | Categoria copiada do procedimento (`kb_artigos.categoria`); o modelo só indica o `kb_id` e redige o resumo | A reincidência é contada por categoria: se o modelo a escolhesse, poderia mudar a prioridade. Alterado depois das rodadas da Parte 1; o resultado dos casos não muda |
| Prioridade decidida na etapa de decisão | Prioridade calculada em código (base do procedimento + reincidência) | Só o gestor reclassifica: nem o modelo nem o cliente devem definir prioridade |

## 6. O que as rodadas de teste acrescentaram (medido em `ministral-8b-latest`)

| Achado | Mudança | Onde |
|---|---|---|
| O modelo **narra** a ação ("encaminhei...") sem chamar a ferramenta e nada é gravado (`TKT-0999` nas rodadas 1 e 2; `TKT-0003` na 1) | **Lembrete no laço**: se o modelo encerra sem desfecho, recebe até 2 avisos como observação; sem efeito, término `erro_fatal` | `src/agente.py` (`LEMBRETE`, `MAX_LEMBRETES`); campo `lembretes` no log |
| Mais regras no prompt pioraram o resultado (5 → 3 de 7) | Prompt v3 = v1 + 2 frases; v2 mantida como registro do experimento | `src/prompts/agente-v*.md` |
| O verificador reprovou uma resposta correta por procurar palavras exatas | Regra do `TKT-0002` passou a exigir que a mensagem cite o serviço do relato e a causa do log | `dados/gabarito.json`, `src/verificar.py` |
| O modelo pequeno pula a busca no `TKT-0003` e escolhe a fila humana | **Não corrigido**: é erro de julgamento, para o lado seguro. Vira pergunta da comparação de modelos e da Parte 2 (busca obrigatória em código, ou modelo maior) | `docs/modelos.md` §3.3 |
| **Três das quatro falhas distintas nasceram da busca por palavra** (frases que diluem o score; limiar que cai no empate 0,5 e deixou um modelo abrir chamado indevido; flexão que não casa) | **Não corrigido na Parte 1**: é o motivo do RAG com limiar calibrado na Parte 2. A confirmação do analista é a rede de segurança enquanto isso | `docs/modelos.md` §3.3-B |

Consequência para a autonomia (§3): o lembrete é uma salvaguarda de código sobre o comportamento do
modelo, do mesmo tipo do portão de confiança e da confirmação do analista. O sistema continua sendo
um roteador com laço curto.

## 7. O laço da Parte 1, como ficou (referência)

Até 10/10/2026 este texto era os §1 a §7 do [`arquitetura.md`](arquitetura.md). Saiu de lá
quando o grafo em LangGraph (`src/grafo.py`) virou o caminho padrão do `main.py`, e está aqui
**sem alteração de conteúdo**, só com os títulos renumerados. Descreve `src/agente.py` com o
prompt `agente-v5.md`, que continua rodando com `python src/main.py --laco`. As medições citadas
são das rodadas do laço. Onde o texto diz "hoje", leia "no laço".

### 7.1 O diagrama (§3.1)

```
LEGENDA   [M] o modelo decide    [C] o código decide    [H] o sistema para e espera uma pessoa
          ◆D  decisão do modelo  ■G  portão em código   ●T  término


ENTRADA
  texto livre do cliente + id do chamado (TKT-0000) + id do cliente                    [C]
  (src/main.py recebe o texto digitado junto do id; sem texto, usa o já registrado para o id)
      │
      ▼
LAÇO   src/agente.py · rodar()                       uma volta = uma chamada ao modelo

  (a) ORÇAMENTO   8 passos · 30 mil tokens · US$ 0,05 · 90 s                           [C]
      │ dentro dos tetos                       estourou um deles ───────────────────► ●T2
      ▼
  (b) MODELO      agente-v5.md + mensagens + 4 schemas · temperature=0                 [M]
      │           API fora depois de 5 tentativas, ou chamada recusada ─────────────► ●T3
      │
      ├─ pediu ferramenta ──► (c) VALIDA E EXECUTA                                     [C]
      │                           JSON · nome · argumentos · portões ■G
      │                           ok   → resultado
      │                           erro → {erro, esperado, sugestao}, devolvido como DADO
      │                           a observação entra nas mensagens      ↺ volta para (a)
      │                           analista não confirmou [H1] ──────────────────────► ●T4
      │
      └─ só texto ──────────► (d) HÁ DESFECHO GRAVADO?                                 [C]
                                  sim ──────────────────────────────────────────────► ●T1
                                  não, lembretes < 2 → envia lembrete-v1.md
                                                                        ↺ volta para (a)
                                  não, lembretes = 2 ───────────────────────────────► ●T3


ETAPAS   a ordem é escolha do modelo, guiada pelo prompt; os portões ■G são do código

  E1 CONSULTA    consultar_ticket(id)                                        leitura
      │          [M] chama · [C] confere o formato do id, lê o chamado e o histórico do cliente
      │          id inexistente → erro como dado, com a sugestão de fila_humana
      ▼
  E2 TRIAGEM     ◆D1 [M] lê o texto livre e classifica o assunto
      │
      ├─ comercial ───────────────────────────────────► fila_comercial      ■G2
      ├─ insuficiente ────────────────────────────────► devolver_cliente    ■G2 ■G6
      ├─ fora da alçada ──────────────────────────────► fila_humana         (motivo fora_da_alcada)
      └─ técnico
          │
          ▼
  E3 BUSCA       buscar_base_conhecimento(termos)                            leitura
          │      ◆D2 [M] escolhe os termos
          │      [C] calcula o score por palavra-chave em kb_artigos; devolve até 3 artigos
          │      ◆D4 [M] score < 0,5: busca de novo (o prompt permite uma vez) ou desiste
          ▼
  E4 DESFECHO    ◆D3 [M] o log anexado aponta outro serviço ou outra causa?
          │      ◆D5 [M] escolhe a ferramenta de escrita e redige o resumo ou a mensagem
          │
          ├─ D3 = sim ────────────────────────────────► fila_humana         ■G5
          ├─ score ≥ 0,5 e artigo "escalar" ──────────► abrir_chamado_interno   ■G2 ■G3 ■G4 → [H1]
          ├─ score ≥ 0,5 e artigo "anotar" ───────────► anotacao_interna        ■G2 ■G3 ■G4
          └─ score < 0,5, sem artigo ou com ressalva ─► fila_humana         ■G5


ESCRITA   uma por execução (■G1)

  abrir_chamado_interno       IRREVERSÍVEL
      [C]  categoria, time e prioridade vêm do artigo; reincidência em 30 dias sobe um nível
      [H1] o ANALISTA DE SUPORTE confirma antes do INSERT; a ação fica em `pendencias`,
           com prazo de 20 min, e a execução pausa ──────────────────────────────────► ●T4
             aprova no prazo        → grava; a chave ticket:kb_id impede duplicata ──► ●T1
             rejeita no prazo       → [C] grava fila_humana, com as considerações
                                      do agente ────────────────────────────────────► ●T1
             sem resposta em 20 min → [C] grava fila_humana, com as considerações
                                      do agente; se o chamado seria P1, grava também
                                      o aviso ao gestor ────────────────────────────► ●T1

  registrar_encaminhamento    reversível: uma linha na tabela encaminhamentos
      destinos: fila_comercial · devolver_cliente · anotacao_interna · fila_humana
      a pessoa entra DEPOIS do término, lendo a fila (§7.7); a execução não espera por ela


DADOS   dados/tickets.db (SQLite), acessado só por src/db.py

  tickets ............. lido por consultar_ticket
  kb_artigos .......... o "ÍNDICE" de hoje: não há índice vetorial, só busca por palavra-chave
  chamados_internos ... escrito por abrir_chamado_interno; relido para contar a reincidência
  encaminhamentos ..... escrito por registrar_encaminhamento; relido para o ■G6
  pendencias .......... a ação irreversível à espera do analista, o prazo e o Estado da
                        execução pausada; criada em src/db.py, e não no seed
  avisos_gestor ....... o aviso ao gestor quando o prazo vence num chamado que seria P1;
                        criada em src/db.py, e não no seed


MEMÓRIA   nenhuma entre execuções: cada execução parte do zero
  O que atravessa execuções é registro do banco (as duas releituras acima) e, na pausa do
  [H1], o Estado guardado em `pendencias` para a mesma execução continuar depois.
  logs/TKT-0000.json guarda a trajetória; o agente grava e nunca lê.


TÉRMINOS   ●T1 respondeu · ●T2 orcamento_esgotado · ●T3 erro_fatal · ●T4 aguardando_humano
```

#### Os portões em código

Todos estão em `src/ferramentas.py`. Quando um portão recusa, o modelo recebe um erro com
`esperado` e `sugestao` e pode corrigir a chamada na volta seguinte.

| Portão | O que exige | Vale para |
|---|---|---|
| ■G1 | o chamado ainda não tem desfecho nesta execução | as duas escritas |
| ■G2 | `consultar_ticket` já foi chamado para este id | toda escrita, menos `fila_humana` |
| ■G3 | o `kb_id` veio de uma busca desta execução e tem score ≥ 0,5 (portão de confiança) | `abrir_chamado_interno`, `anotacao_interna` |
| ■G4 | a ação do procedimento casa com a ferramenta ("escalar" abre chamado, "anotar" anota) | `abrir_chamado_interno`, `anotacao_interna` |
| ■G5 | houve pelo menos uma busca na base, se o chamado existe e o motivo não é `fora_da_alcada` | `fila_humana` |
| ■G6 | a mensagem não cita informação interna, e o chamado ainda não recebeu pedido (contado no banco) | `devolver_cliente` |

Além deles, o código confere o formato: resumo com 20 caracteres ou mais, mensagem com 10 ou mais,
destino dentro da lista.

### 7.2 As ferramentas

| Ferramenta | O que faz | Leitura ou escrita | Reversível? |
|---|---|---|---|
| `consultar_ticket` | Lê o registro do chamado: log anexado, plano e histórico de chamados internos do cliente. O texto do cliente já veio na entrada e não é repetido | leitura | não se aplica |
| `buscar_base_conhecimento` | Busca procedimentos por palavras e devolve até 3 artigos, cada um com score de 0 a 1 e, quando o procedimento não cobre o caso relatado, uma `ressalva` | leitura | não se aplica |
| `abrir_chamado_interno` | Abre um chamado para o time responsável. O modelo informa só o `kb_id` e o resumo; categoria, time e prioridade são calculados pelo código | escrita | **não**: não existe ferramenta para apagar ou encerrar um chamado. A chave `ticket:kb_id` evita duplicata, mas não desfaz a abertura |
| `registrar_encaminhamento` | Registra um dos quatro desfechos que não abrem chamado: `fila_comercial`, `devolver_cliente`, `anotacao_interna`, `fila_humana` | escrita | sim: é uma linha em fila ou anotação, que uma pessoa lê e pode desconsiderar |

Não existe ferramenta para encerrar chamado, mudar prioridade ou executar correção. A regra do
domínio ("o agente nunca executa, nunca fecha, nunca reclassifica") é garantida pela ausência da
ferramenta, e não por um pedido no prompt.

**`devolver_cliente` é reversível só porque ainda não envia nada.** Hoje a ferramenta grava o
pedido na tabela e a execução termina. Quando a mensagem passar a chegar ao cliente (Parte 2), a
escrita deixa de ter volta e passa a exigir a confirmação do analista.

### 7.3 O laço

**A cada volta**, nesta ordem (`rodar()`, em `src/agente.py`):

1. o código confere os quatro tetos do orçamento; se um estourou, a execução termina;
2. o código chama o modelo com a lista de mensagens inteira e os quatro schemas;
3. o código soma os tokens e o custo da chamada no estado;
4. se o modelo pediu ferramentas, o código valida e executa cada uma, grava um `Passo` e devolve
   o resultado, ou o erro, como mensagem de ferramenta;
5. se o modelo respondeu só com texto, o código olha o estado: com desfecho gravado, termina;
   sem desfecho, envia o lembrete (no máximo 2 vezes) ou termina com erro.

**O que faz a volta seguinte existir** são duas coisas, e só elas:

- o modelo pediu uma ferramenta, e a observação precisa voltar para ele. Um erro recuperável
  conta como observação: a chamada recusada por um portão gera uma volta, e não um término;
- o modelo quis encerrar sem ter gravado desfecho, e o código devolve o lembrete.

O laço não tem contador de voltas próprio. O que o limita é o teto de passos, mais o teto de
lembretes: no pior caso são 11 chamadas ao modelo (8 voltas com ferramenta, 2 lembretes e a
resposta final).

O caminho real é curto. Nas 24 execuções das três rodadas com o `agente-v5.md`
(`logs/rodada-1-prompt-v5/`, `logs/rodada-2-prompt-v5/`, `logs/rodada-3-prompt-v5/`), todas
tiveram de 2 a 4 passos e de 3 a 5 chamadas ao modelo. Na rodada 3, a única com o seed e o texto
atuais do prompt (10/10/2026, commit `2ffb2b5 + alterações locais`), as 8 execuções somaram 22
passos, 31 chamadas ao modelo, 69.889 tokens e US$ 0,0105 a preço de lista.

### 7.4 O estado

**O objeto explícito** é a dataclass `Estado` (`src/agente.py`). Ferramentas e portões leem dele,
nunca das mensagens.

| Campo | Tipo | Quem escreve | Quem lê |
|---|---|---|---|
| `id_ticket`, `modelo`, `prompt`, `temperatura`, `execucao_id`, `executado_em`, `commit` | texto, número | `rodar()`, na criação | o log |
| `entrada` | texto | `rodar()`, na criação: o texto do chamado, como chegou | o log |
| `saida` | objeto validado (`Saida`, em `src/saida.py`) | o laço, ao terminar (`montar_saida`) | `main.py` e o log |
| `ticket` | dict ou `None` | `consultar_ticket` | a busca (texto do cliente, para as ressalvas) e os portões ■G2 e ■G5 |
| `scores_kb` | dict `kb_id → score` | `buscar_base_conhecimento` | o portão ■G3 |
| `n_buscas` | inteiro | `buscar_base_conhecimento` | o portão ■G5 e a sugestão de nova busca |
| `desfecho` | dict ou `None` | a ferramenta de escrita que deu certo | o portão ■G1 e a etapa (d) do laço |
| `passos` | lista de `Passo` (ferramenta, argumentos, resultado, erro, ms) | `_executar()`, um por chamada de ferramenta | o orçamento (teto de passos) e o log |
| `tokens_entrada`, `tokens_saida`, `custo_usd` | número | o laço, depois de cada chamada ao modelo | o orçamento |
| `n_chamadas_modelo` | inteiro | o laço | o log |
| `lembretes` | inteiro | a etapa (d) do laço | a etapa (d) do laço |
| `confirmacoes` | lista | `Estado.confirmar()` e a retomada (`retomar()`) | o log |
| `pendencia` | dict ou `None` | o laço, ao capturar `PausaParaHumano` (só na espera) | o log |
| `prazo_confirmacao_min` | número (padrão 20) | `rodar()`, na criação | `abrir_chamado_interno`, para calcular o `vence_em`; a retomada, para o texto do encaminhamento |
| `pendencia_id` | inteiro ou `None` | `abrir_chamado_interno`, ao gravar a pendência | o laço, para guardar o checkpoint |
| `termino`, `motivo`, `resposta` | enum, texto | o laço | `main.py`, o verificador e o log |
| `historico` | lista de mensagens | o laço | só a chamada ao modelo |

O `desfecho` é o único campo de decisão com mais de um escritor: as duas ferramentas de escrita,
e o código que encaminha à fila humana a ação rejeitada ou vencida (`encaminhar_pendencia`, em
`src/ferramentas.py`). O portão ■G1 garante que só uma das ferramentas escreve por execução, e o
encaminhamento pelo código só acontece no lugar da abertura de chamado que não foi autorizada.

**O que ficou na lista de mensagens** (`historico`), e só nela:

- o prompt de sistema e o texto do cliente;
- **a classe da triagem (◆D1)**. O modelo classifica o assunto e não registra a classe em lugar
  nenhum: ela só aparece, depois, na ferramenta que ele escolhe. Um chamado que foi para a
  `fila_humana` não diz, no estado, se o modelo o leu como técnico ou como fora da alçada, a não
  ser pelo campo `motivo` do desfecho;
- o texto que o modelo escreve entre as chamadas de ferramenta;
- o texto do lembrete.

O `historico` é transporte: não entra no log (`para_dict()` não o grava). Por isso o texto
intermediário do modelo se perde ao fim da execução; o log guarda os passos e a resposta final.

### 7.5 O orçamento

Quatro tetos, na classe `Orcamento`, conferidos pelo código no começo de cada volta. O motivo do
término diz qual estourou.

| Teto | Valor | O que conta |
|---|---|---|
| passos | 8 | chamadas de ferramenta executadas, inclusive as que devolveram erro |
| tokens | 30 mil | entrada + saída, somadas em todas as chamadas ao modelo |
| custo | US$ 0,05 | os tokens, ao preço de lista informado no `.env` |
| tempo | 90 s | relógio corrido desde o início da execução |

Fora da classe há dois tetos menores: 2 lembretes por execução e 5 tentativas por chamada ao
modelo quando a falha é de transporte (limite de requisições ou conexão).

**O que impede uma execução de não acabar** é o teto de passos e o de lembretes: cada volta
consome um dos dois ou termina.

**A espera pelo analista não conta no teto de tempo.** A execução pausa e guarda os segundos já
gastos; a retomada continua o relógio desse ponto (§7.7). Passos, tokens e custo seguem somando no
mesmo estado. A espera tem o seu próprio limite, que é o prazo de 20 minutos.

Dois limites conhecidos:

- **A conferência é entre voltas.** Se o modelo pedir várias ferramentas na mesma resposta, todas
  executam antes da próxima conferência, e a execução pode passar de 8 passos.
- **O teto de tempo não interrompe nada em andamento.** Ele não corta uma chamada ao modelo que
  demora.

### 7.6 O término

Toda execução grava por que parou (`Estado.termino` e `Estado.motivo`). São quatro términos:

| Término | Quando | O que ficou gravado no banco |
|---|---|---|
| ●T1 `respondeu` | o modelo respondeu só com texto e há desfecho gravado. Inclui a execução retomada: o analista aprovou, ou ele rejeitou ou o prazo venceu e o código gravou a `fila_humana` | o desfecho; no prazo vencido de um chamado que seria P1, também uma linha em `avisos_gestor` |
| ●T2 `orcamento_esgotado` | um dos quatro tetos estourou; o motivo diz qual (`passos: 8/8`, `tempo: 91s/90s`) | nada, **ou** o desfecho, se o teto estourou depois da escrita e antes da resposta final |
| ●T3 `erro_fatal` | (1) API indisponível depois de 5 tentativas; (2) a API recusou a chamada (chave ou modelo inválido, erro do provedor); (3) o modelo encerrou sem desfecho depois de 2 lembretes; (4) interrupção inesperada | nada, salvo no caso (4), se a interrupção vier depois da escrita |
| ●T4 `aguardando_humano` | a abertura do chamado interno espera o analista, dentro do prazo | nada em `chamados_internos` nem em `encaminhamentos`. A ação e o prazo ficam na tabela `pendencias`; os argumentos da ação ficam também no campo `pendencia` do log |

O ●T4 não é um fim: é o único término que a mesma execução troca depois, por ●T1, quando o
analista aprova, rejeita ou o prazo vence (§7.7). Nenhuma das três saídas deixa o chamado sem
desfecho.

Consequência do ●T2: para saber se o chamado teve desfecho, vale o campo `desfecho`, e não o
término. O verificador (`src/verificar.py`) confere o banco.

Erro de ferramenta não é término. O que o modelo pode contornar (id em formato errado, id
inexistente, portão recusado, argumento faltando) volta como dado. Hoje nenhuma ferramenta
levanta erro fatal: os casos (1) e (2) do ●T3 vêm da chamada ao modelo.

### 7.7 O humano

**Um único ponto em que o sistema para e espera: [H1].**

| | |
|---|---|
| Onde | dentro de `abrir_chamado_interno`, depois de todos os portões e antes do INSERT |
| Critério | ação irreversível |
| Quem é chamado | o **analista de suporte** (perfil do `case.md` §2.2) |
| O que ele vê | a ferramenta, o id do chamado, a categoria, o resumo, o time de destino, o `kb_id`, a hora do pedido, a hora em que o prazo vence e quantos minutos faltam (`python src/main.py --pendencias`). A prioridade não aparece na tela: a do chamado aberto é calculada na gravação, e a prevista só é calculada quando a ação é rejeitada ou vence |
| O que ele devolve | `--aprovar TKT-0000` ou `--rejeitar TKT-0000`. Não há aprovação com edição |
| Se aprova no prazo | o chamado é gravado e a execução pausada continua: o modelo recebe o resultado e dá a frase final; término ●T1 |
| Se rejeita no prazo | o chamado interno **não** é aberto; o código grava `fila_humana` com as considerações do agente (motivo `acao_rejeitada`); término ●T1 |
| Se não responde em 20 minutos | o chamado interno **não** é aberto; o código grava `fila_humana` com as considerações do agente (motivo `confirmacao_nao_recebida`); se o chamado seria **P1**, grava também o aviso ao gestor; término ●T1 |

**A espera é assíncrona.** `abrir_chamado_interno` não fica parado esperando: grava a ação na
tabela `pendencias`, com `pedido_em` e `vence_em`, e levanta `PausaParaHumano`. O laço guarda na
mesma linha o `Estado` da execução (chamado lido, scores, passos, mensagens, tokens e os segundos
já gastos) e termina em ●T4. Nada é escrito em `chamados_internos` antes da resposta. O analista
responde de outro processo, minutos depois, e `retomar()` (em `src/agente.py`) continua a mesma
execução: não há nova triagem nem nova busca.

**O prazo.** O analista tem **20 minutos** para confirmar ou rejeitar, contados do pedido de
confirmação (`case.md` §2.1; constante `PRAZO_CONFIRMACAO_MIN`, em `src/ferramentas.py`). Vencido
o prazo, a ação não é executada e o código, sem consultar o modelo, grava um encaminhamento à
`fila_humana` com as considerações do agente: a ação que ele propôs, a prioridade que o chamado
teria, o procedimento e o score que a sustentam, o resumo já redigido e o motivo "confirmação não
recebida em 20 minutos". O desfecho leva `motivo: confirmacao_nao_recebida`, e a `suficiencia` da
saída é negativa. Depois da gravação o modelo é chamado uma vez, só para a frase final.

**A rejeição tem o mesmo destino.** Se o analista rejeita dentro do prazo, a ação não é executada
e o código grava o mesmo encaminhamento à `fila_humana`, com as mesmas considerações e o motivo
"ação rejeitada pelo analista de suporte" (`motivo: acao_rejeitada`). Vale também para a resposta
dada na hora, por um confirmador: a rejeição não derruba o laço, e o modelo recebe a observação
e dá a frase final. Antes de 10/10/2026 a rejeição não gravava nada e a execução terminava em
●T4, com o chamado sem desfecho.

**Prazo vencido em chamado P1 avisa o gestor.** A fila humana é lida pelo mesmo analista que não
respondeu. Por isso, quando o prazo vence e o chamado interno seria P1, o código grava também uma
linha na tabela `avisos_gestor`, com o chamado, a prioridade, o motivo e a mesma mensagem do
encaminhamento. A prioridade usada é a **prevista**: a base do procedimento mais a reincidência,
pela mesma regra da abertura (`prioridade_prevista`, em `src/db.py`), calculada na hora do
vencimento. O aviso não é um segundo desfecho: o desfecho continua sendo a `fila_humana`. A
rejeição não avisa o gestor, porque o analista já viu o chamado.

**O relógio vale antes da pessoa.** Uma aprovação que chega depois do `vence_em` é tratada como
prazo vencido: o chamado não é aberto. O silêncio nunca vira aprovação, e a aprovação tardia
também não.

**Aprovar duas vezes** não repete nada: a pendência só é resolvida uma vez (`resolver_pendencia`,
em `src/db.py`, confere o status no mesmo `UPDATE`), e a segunda chamada não encontra o que
aprovar.

Quatro limites do que foi implementado:

- **O aviso ao gestor é um registro, não uma notificação.** O sistema é simulado e não tem canal
  de mensagem: o aviso é uma linha em `avisos_gestor`, que o gestor precisa consultar. Não há
  comando no `main.py` para listá-la.

- **O prazo é conferido, não cronometrado.** Não há processo em segundo plano. As pendências
  vencidas são encaminhadas no começo do próximo comando do `main.py` (`vencer_pendencias`). Se
  ninguém rodar nada, o chamado fica na pausa até alguém rodar: a regra garante que a ação
  vencida nunca é executada, mas não garante que a fila humana a receba no minuto 20.
- **Só o [H1] tem prazo.** A confirmação do pedido ao cliente (`devolver_cliente`) ainda não
  existe; quando existir, usa o mesmo prazo.
- **Não é o checkpointer do grafo.** O `Estado` é guardado como JSON numa coluna, por uma função
  escrita à mão, e serve só a esta pausa. `--reset` e `--todos` recriam o banco e apagam as
  pendências; por isso `--todos` exige `--auto-aprovar`.

`--auto-aprovar` troca o analista por uma aprovação automática e existe só para a demonstração.
Todos os logs em `logs/` foram gerados com ele: a espera, a aprovação, a rejeição e o prazo
vencido estão cobertos por testes offline (`tests/test_offline.py`, bloco "o prazo de 20 minutos
do analista"), e não por uma execução registrada com o modelo real.

**Onde uma pessoa entra sem que o sistema espere por ela.** Os quatro destinos de
`registrar_encaminhamento` entregam o chamado a alguém, mas a execução termina antes:

| Destino | Quem lê |
|---|---|
| `fila_humana` | o analista de suporte, que decide o que fazer com o chamado |
| `anotacao_interna` | o analista de suporte, que valida e executa a correção sugerida |
| `fila_comercial` | o time comercial |
| `devolver_cliente` | hoje ninguém: o pedido fica gravado e não é enviado. Na Parte 2 passa a ser um segundo ponto de parada, com a confirmação do analista antes do envio (no mesmo prazo de 20 minutos) e o prazo de 3 dias úteis para a resposta do cliente, depois do qual o chamado vai para a `fila_humana` (`case.md` §2.1) |

# Arquitetura do agente (Parte 2, item 3)

> **O que este documento descreve.** O sistema **como ele está hoje** (12/10/2026): o **grafo em
> LangGraph** de `src/grafo.py`, que é o caminho padrão do `main.py`, com os prompts
> `triagem-v1.md`, `ressalva-v3.md` e `redigir-v3.md`, a entrada em texto digitado e a saída
> validada (`src/saida.py`). Os §1 a §7 respondem ao item 3 do enunciado sobre esse grafo; o §8
> defende o nível de autonomia; o §9 traz o grafo nó a nó e a conferência contra o código.
>
> O laço da Parte 1 (`src/agente.py`, prompt `agente-v5.md`) continua no repositório e roda com
> `--laco`. A descrição dele, que ocupava os §1 a §7 deste documento até 10/10/2026, foi para o
> [`arquitetura-v2.md`](arquitetura-v2.md) §7, sem alteração. O índice vetorial
> (`src/vetorial.py`) e a memória entre execuções (tabelas `episodios` e `fatos_cliente`) existem
> desde 11/10/2026 e estão no diagrama do §1. O grafo está detalhado em [`grafo.md`](grafo.md), a
> recuperação em [`rag.md`](rag.md), a memória em [`memoria.md`](memoria.md) e os pontos de parada
> em [`humano.md`](humano.md).
>
> **As medições citadas nos §3, §5 e §8 são de 10/10/2026**, anteriores à busca vetorial, ao nó
> `conferir_ressalva`, ao H2 e ao `redigir-v3.md`. As rodadas dos 8 casos com o código e os
> prompts em uso são `logs/grafo-redigir-v3-1/` a `-3/` (12/10/2026): 8 de 8 nas três, 16
> chamadas ao modelo e cerca de 13,2 mil tokens cada (`grafo.md` §6.5).
>
> O histórico da decisão (v1 no papel → v2 construída) continua em
> [`arquitetura-v2.md`](arquitetura-v2.md).

## 1. O diagrama (§3.1)

```
LEGENDA   [M] o modelo decide    [C] o código decide    [H] o sistema para e espera uma pessoa
          ◆D  decisão do modelo  ◇   aresta condicional ●T  término


ENTRADA
  texto livre do cliente + id do chamado (TKT-0000) + id do cliente                    [C]
  (src/main.py recebe o texto digitado junto do id; sem texto, usa o já registrado para o id)
      │
      ▼
GRAFO   src/grafo.py · objeto GRAFO, compilado uma vez · thread_id = id do chamado
        a ordem dos nós está nas arestas: o modelo não escolhe o próximo passo

  [entrada]            [C] fixa o texto do chamado: o digitado, ou o registrado para o id
      │
      ▼
  [consultar]          [C] lê o chamado, o plano, o log anexado e o histórico        leitura
      │
      ◇ o id existe?   [C] é um campo vazio
      ├─ não ──────────────────────────────────────────────────────────► [decidir]
      ▼ sim
  [triagem]            [M] UMA chamada · triagem-v1.md · temperature=0 · JSON validado
      │                ◆D1 a classe: tecnico · comercial · insuficiente · fora_da_alcada
      │                ◆D3 o log anexado aponta outro serviço ou outra causa? (sim ou não)
      │                ◆D2 os termos de busca (só na classe "tecnico")
      │                [C] antes da chamada: tetos de tokens, custo e tempo ───────► ●T2
      │                [C] API fora, ou JSON fora do contrato 2 vezes ─────────────► ●T3
      │
      ◇ a classe       [M] decide a rota; o código só lê o valor
      ├─ comercial · insuficiente · fora_da_alcada ────────────────────► [decidir]
      ▼ tecnico
  [buscar]             [C] busca VETORIAL em kb_artigos: o cosseno do relato (mistral-embed,
      │                    1024 dimensões) com cada guia; devolve até 3, com score       leitura
      │
      ◇ o 1º guia passa de 0,5, não tem ressalva literal e declara situações que não cobre?
      ├─ não ──────────────────────────────────────────────────────────► [decidir]
      ▼ sim
  [conferir_ressalva]  [M] UMA chamada · ressalva-v3.md · temperature=0 · JSON validado
      │                [C] antes: lê os fatos confirmados do cliente (MEMÓRIA, fatos_cliente)
      │                    e os põe na entrada do modelo                              leitura
      │                ◆D6 o relato cai numa das situações que o guia NÃO cobre? (sim ou não)
      │                [C] só BAIXA o score (× 0,4), e só com uma frase da lista do guia
      │                [C] antes da chamada: os mesmos tetos ───────────────────────► ●T2
      │                [C] API fora, ou JSON fora do contrato 2 vezes ─────────────► ●T3
      ▼
  [decidir]            [C] escolhe o desfecho; é o portão de confiança (limiar 0,5)
      │                    id inexistente ........................... fila_humana
      │                    comercial ................................ fila_comercial
      │                    fora_da_alcada ........................... fila_humana
      │                    insuficiente, sem pedido anterior ........ devolver_cliente
      │                    insuficiente, com pedido anterior ........ fila_humana
      │                    técnico, ◆D3 = sim ....................... fila_humana  (antes do score)
      │                    técnico, sem artigo ou score < 0,5 ....... fila_humana
      │                    técnico, score ≥ 0,5, guia "escalar" ..... abrir_chamado_interno
      │                    técnico, score ≥ 0,5, guia "anotar" ...... anotacao_interna
      ▼
  [redigir]            [M] UMA chamada · redigir-v3.md · temperature=0 · JSON {texto}
      │                ◆D5 o texto: resumo do chamado ou mensagem do encaminhamento.
      │                    O desfecho chega decidido; o modelo não o troca
      │                [C] no pedido ao cliente (devolver_cliente) o modelo NÃO é chamado:
      │                    o texto é o padrão do código, com cinco perguntas
      │                [C] antes da chamada: os mesmos tetos ──────────────────────► ●T2
      │                [C] API fora ───────────────────────────────────────────────► ●T3
      ▼
  [validar]            [C] tamanho mínimo; no pedido ao cliente, nenhuma informação interna
      │
      ◇ o texto passou? [C]
      ├─ não, 1ª vez ──► volta a [redigir], com o erro            (o único retorno do grafo)
      ├─ não, 2ª vez ──────────────────────────────────────────────────────────────► ●T3
      ├─ sim, desfecho reversível ─────────────────────────────────────► [gravar]
      ▼ sim, abrir_chamado_interno ou devolver_cliente: IRREVERSÍVEL
  [pedir_confirmacao]  [C] monta a ação como o analista vai vê-la, marca pedido_em e
      │                    vence_em (20 min) e grava a linha em `pendencias`.
      │                    No H1 a tela leva os precedentes (MEMÓRIA, episodios) e os
      │                    fatos do cliente (fatos_cliente)                           leitura
      ▼
  [confirmar]          [H1] [H2] interrupt: o ANALISTA DE SUPORTE aprova ou rejeita.
      │                     H1 = abrir chamado interno; H2 = enviar o pedido ao cliente.
      │                     Enquanto espera, o processo termina ──────────────────► ●T4
      │                     e o estado fica no checkpoint (dados/checkpoints.db).
      │                     A resposta chega por outro processo e o grafo continua daqui:
      │                       aprova no prazo        → aprovada (pode corrigir o texto:
      │                                                o resumo, no H1; a mensagem, no H2)
      │                       rejeita no prazo       → rejeitada
      │                       sem resposta em 20 min → vencida (o relógio vale antes da pessoa)
      ▼
  [gravar]             [C] a ÚNICA escrita de desfecho da execução                  escrita
      │                    aprovada, H1         → abre o chamado interno; categoria, time e
      │                                           prioridade vêm do procedimento; reincidência
      │                                           em 30 dias sobe um nível; a chave
      │                                           ticket:kb_id impede duplicata
      │                    aprovada, H2         → registra o pedido como enviado ao cliente
      │                                           (um por chamado; não há canal de mensagem)
      │                    rejeitada ou vencida → fila_humana, com as considerações do agente
      │                    vencida, e seria P1  → grava também o aviso ao gestor (só no H1)
      │                    desfecho reversível  → uma linha em `encaminhamentos`
      ▼
  [finalizar]          [C] término, motivo e a saída validada (src/saida.py) ──────► ●T1


FORA DOS NÓS
  LIMITE_SUPERPASSOS = 20 (o recursion_limit, declarado no código); estourado ─────► ●T2
  O caminho mais longo tem 14 superpassos; o mais curto, 7.
  Depois do grafo, _concluir() [C] grava o log da execução e, se ela concluiu, o episódio
  (MEMÓRIA, episodios; uma linha, com chave de idempotência) e apaga o checkpoint.     escrita


DADOS   dados/tickets.db (SQLite), acessado só por src/db.py

  tickets ............. lido por [consultar]
  kb_artigos .......... o corpus: 16 guias, 15 vigentes e 1 revogado, que não entra na busca
  planos_fichas ....... as 3 fichas de plano; contexto de [redigir] e da tela do [H1]
  kb_vetores .......... o ÍNDICE VETORIAL: um vetor (mistral-embed, 1024 dimensões) por guia
                        e por ficha de plano, com o hash do texto. Lido por [buscar], que
                        calcula o cosseno em memória; refeito só para o texto que mudou.
                        Criada em src/db.py, e não no seed
  chamados_internos ... escrito por [gravar]; relido para contar a reincidência
  encaminhamentos ..... escrito por [gravar]; relido por [decidir] (um pedido por chamado)
  pendencias .......... a fila do analista: a ação irreversível à espera e o prazo;
                        criada em src/db.py, e não no seed
  avisos_gestor ....... o aviso ao gestor quando o prazo vence num chamado que seria P1;
                        criada em src/db.py, e não no seed

CHECKPOINT   dados/checkpoints.db (SqliteSaver do LangGraph), endereçado pelo thread_id
  Guarda o estado do grafo a cada superpasso. É o que deixa a execução pausada no [H1] ou
  no [H2] continuar em outro processo. É apagado quando a execução conclui; uma execução
  nova do mesmo chamado apaga também o de uma pausa anterior.

MEMÓRIA   entre execuções, em dados/tickets.db; só o grafo lê e grava (docs/memoria.md)
  episodios ........... EPISÓDICA. Um registro por execução concluída, escrito pelo código
                        em _concluir(): campos estruturados, nunca o texto do cliente.
                        Lida por consulta exata (não por similaridade) em [pedir_confirmacao].
                        Só avisa o analista: nenhuma regra de decisão a lê
  fatos_cliente ....... SEMÂNTICA. Fatos do ambiente do cliente, de vocabulário fechado,
                        escritos só por uma pessoa (main.py --fato). Lidos por chave em
                        [conferir_ressalva] e em [pedir_confirmacao]
  procedural .......... NÃO HÁ regra aprendida no prompt. Existe o motivo da rejeição,
                        gravado no episódio, e o relatório main.py --candidatas, que só lê
  As tabelas nascem em src/db.py. --todos e --reset as zeram junto com o banco.
  O que também atravessa execuções é registro do banco (as duas releituras de DADOS).
  logs/…/TKT-0000.json guarda a trajetória; o sistema grava e nunca lê.


TÉRMINOS   ●T1 respondeu · ●T2 orcamento_esgotado · ●T3 erro_fatal · ●T4 aguardando_humano
```

O mesmo grafo, nó a nó e com as chaves de cada aresta, está no §9.1, ao lado da saída de
`conferir_grafo.py`. O diagrama do laço da Parte 1, com os portões ■G1 a ■G6, foi para o
[`arquitetura-v2.md`](arquitetura-v2.md) §7.

**As decisões do modelo são quatro, em três chamadas** (a de ressalva só roda quando o primeiro guia declara situações que não cobre). ◆D1 e ◆D3 decidem o caminho; ◆D6 só pode baixar o score; ◆D2 e ◆D5
decidem conteúdo (termos e texto). A marca ◆D4 do laço (buscar de novo quando o score vem baixo)
não existe no grafo: a busca roda uma vez.

## 2. As ferramentas

**No grafo o modelo não chama ferramenta.** As quatro ferramentas do laço continuam existindo como
operações, mas quem as chama é um nó, na ordem das arestas. O modelo entrega dados (classe,
divergência, termos, texto) e o código faz a leitura e a escrita.

| Operação | O que faz | Quem chama, no grafo | Leitura ou escrita | Reversível? |
|---|---|---|---|---|
| consultar o chamado (`db.buscar_ticket`) | Lê o registro do chamado: log anexado, plano e histórico de chamados internos do cliente | nó `consultar`, em toda execução | leitura | não se aplica |
| buscar na base (`vetorial.buscar`; `db.buscar_kb` é a busca por palavra, que ela usa e que o laço mantém) | Busca procedimentos por vetor e por palavras e devolve até 3 artigos, cada um com score de 0 a 1 e, quando o procedimento não cobre o caso relatado, uma `ressalva` | nó `buscar`, só na rota técnica | leitura | não se aplica |
| abrir chamado interno (`db.abrir_chamado`) | Abre um chamado para o time responsável. O texto é o que o modelo redigiu; o `kb_id` vem da busca; categoria, time e prioridade são calculados pelo código | nó `gravar`, depois da aprovação no [H1] | escrita | **não**: não existe operação para apagar ou encerrar um chamado. A chave `ticket:kb_id` evita duplicata, mas não desfaz a abertura |
| registrar encaminhamento (`db.registrar_encaminhamento`) | Registra um dos três desfechos internos que não abrem chamado: `fila_comercial`, `anotacao_interna`, `fila_humana` | nó `gravar` | escrita | sim: é uma linha em fila ou anotação, que uma pessoa lê e pode desconsiderar |
| enviar o pedido ao cliente (`db.registrar_pedido_cliente`) | Registra o `devolver_cliente` com a hora do envio (`enviado_em`). Um por chamado: repetir devolve o que já existe | nó `gravar`, depois da aprovação no [H2] | escrita | **não**, pela regra do domínio: a mensagem chega ao cliente. No sistema simulado é uma linha, porque não há canal de mensagem |

Não existe operação para encerrar chamado, mudar prioridade ou executar correção. A regra do
domínio ("o agente nunca executa, nunca fecha, nunca reclassifica") é garantida pela ausência do
código que faria isso, e não por um pedido no prompt.

**`devolver_cliente` passou a exigir a confirmação do analista (H2, 12/10/2026).** Até então a
operação gravava o pedido direto, e era tratada como reversível porque não enviava nada. O envio
continua sendo só o registro, com `enviado_em`: o que mudou é que ele acontece depois da
aprovação, e por uma função própria, onde um canal de mensagem entraria (`humano.md` §2.4). No
laço da Parte 1 o pedido continua gravado sem confirmação.

**Onde foram parar os portões do laço.** No laço, seis portões em `src/ferramentas.py` recusavam
a chamada errada e devolviam o erro ao modelo. No grafo as mesmas regras continuam, em outro
lugar:

| Portão do laço | A regra | Onde está no grafo |
|---|---|---|
| ■G1 | um desfecho por execução | `gravar` é o único nó que escreve desfecho, e roda uma vez |
| ■G2 | consultar o chamado antes de escrever | `consultar` é o segundo nó de toda execução |
| ■G3 | o `kb_id` vem de uma busca desta execução, com score ≥ 0,5 | nó `decidir`: o `kb_id` sai dos `candidatos` da busca, e o modelo nem o informa |
| ■G4 | a ação do procedimento casa com o desfecho ("escalar" abre chamado, "anotar" anota) | nó `decidir` |
| ■G5 | `fila_humana` de chamado técnico só depois de uma busca | a rota técnica passa sempre por `buscar`; não há aresta que a pule |
| ■G6 | pedido ao cliente sem informação interna, e um só por chamado | nó `validar` (o texto) e nó `decidir` (a contagem no banco) |

A diferença é o que acontece na recusa. No laço o modelo recebia o erro e escolhia outra ação.
No grafo não há o que recusar: o desfecho já sai dentro da regra. O único erro que volta ao
modelo é o do texto reprovado em `validar`.

## 3. O laço

**Não há laço livre.** O sistema é um grafo dirigido com um único retorno. O que o enunciado
chama de "volta" é aqui um **superpasso** do LangGraph: a execução de um nó.

**A cada superpasso**, nesta ordem:

1. o LangGraph executa o nó da vez, com o estado atual;
2. o nó devolve só os campos que mudou; os campos acumulados (`passos`, tokens, custo, tempo)
   são somados ou concatenados pelo reducer, e os outros são sobrescritos (§4);
3. o embrulho `_no()` mede o tempo gasto no nó e o soma em `segundos_gastos`;
4. o checkpointer grava o estado em `dados/checkpoints.db`;
5. a aresta de saída escolhe o próximo nó: fixa, ou condicional com o mapa de destinos escrito.

**O que faz o superpasso seguinte existir** é a aresta, e só ela. O modelo não pede o próximo
passo: ele devolve um JSON, o nó o grava no estado, e uma função de código lê o campo.

**Os três lugares em que algo se repete**, os três com teto em código:

- `validar → redigir`: o texto reprovado volta ao modelo **uma** vez, com o erro
  (`MAX_REDACOES = 2`). Na segunda reprovação a execução termina em ●T3;
- dentro do nó `triagem`: um JSON fora do contrato é devolvido ao modelo **uma** vez
  (`MAX_TENTATIVAS_TRIAGEM = 2`). Não é aresta: é uma repetição dentro do nó;
- dentro do nó `conferir_ressalva`: o mesmo, e também quando a frase citada não é uma das do
  guia (`MAX_TENTATIVAS_RESSALVA = 2`).

Com isso o pior caso são 6 chamadas ao modelo por execução (2 de triagem, 2 de ressalva e 2 de
redação), contra 11 no laço da Parte 1.

**O caminho real.** Em três execuções dos 8 casos (`logs/grafo/`, `logs/grafo-rodada-2/` e
`logs/grafo-rodada-3/`, de 10/10/2026), todas as 24 execuções fizeram 2 chamadas ao modelo,
menos o `TKT-0999`, que faz 1: o id inexistente não passa pela triagem. Nenhuma redação foi
reprovada e nenhuma triagem veio fora do contrato. Cada rodada somou 15 chamadas ao modelo, de
12.623 a 12.687 tokens e US$ 0,0019 a preço de lista (§8).

Essas três rodadas são anteriores ao nó `conferir_ressalva`. Na rodada com ele
(`logs/grafo-fatos/`, 11/10/2026, uma execução dos 8 casos, 8 de 8 no verificador), o `TKT-0003` e
o `TKT-0007` fizeram 3 chamadas, porque o KB-102 declara uma situação que não cobre; os outros
ficaram como antes. A rodada somou 17 chamadas ao modelo, 14.440 tokens e US$ 0,0022. As três
rodadas de 12/10/2026, já com o H2 e o `redigir-v2.md`, repetem as 17 chamadas, com 14.718 a
14.722 tokens (`logs/grafo-redigir-v2-1/` a `-3/`). Com o pedido ao cliente em texto padrão,
o `TKT-0005` passou a fazer 1 chamada, e a rodada 16 (`logs/grafo-pedido-padrao-1/` a `-3/`).

## 4. O estado

**O objeto explícito** é o `TypedDict` `EstadoGrafo` (`src/grafo.py`). Os nós e as arestas leem
dele. **Não há lista de mensagens no estado.**

| Campo | Tipo | Quem **escreve** | Quem **lê** | De onde veio | Reducer |
|---|---|---|---|---|---|
| `id_ticket`, `texto_recebido` | texto | `rodar_grafo()`, na entrada do grafo | todos; o log | a linha de comando: o id e o texto digitado | nenhum |
| `modelo`, `temperatura`, `prazo_confirmacao_min` | texto, número | `rodar_grafo()` | os nós de modelo; `pedir_confirmacao` | o `.env` e os argumentos do `main.py` | nenhum |
| `execucao_id`, `executado_em`, `commit` | texto | `rodar_grafo()` | o log e a saída; o `execucao_id` entra na chave do episódio | um identificador aleatório, o relógio e o `git` | nenhum |
| `texto` | `str` | `entrada` | `triagem`, `buscar`, `redigir` | o texto digitado, ou o registrado para o id | nenhum |
| `ticket` | `dict` ou `None` | `consultar` | a aresta de `consultar`, `triagem`, `decidir`, `redigir`, `gravar` | a tabela `tickets` | nenhum |
| `classe` | `str` | `triagem` | a aresta de `triagem`, `decidir` | o modelo (◆D1) | nenhum |
| `log_diverge` | `bool` | `triagem` | `decidir` | o modelo (◆D3) | nenhum |
| `termos` | `list[str]` | `triagem` | `buscar`, `redigir` | o modelo (◆D2) | nenhum |
| `candidatos` | `list[dict]` | `buscar`; `conferir_ressalva` (só baixa o score do 1º) | `decidir`, `redigir`, `gravar`, a saída | a tabela `kb_artigos`, com o score calculado | nenhum |
| `ressalvas_do_melhor` | `list[str]` | `buscar` | a aresta de `buscar`, `conferir_ressalva` | as frases de `nao_cobre` do 1º guia | nenhum |
| `desfecho_proposto` | `dict` (`acao`, `kb_id`, `motivo`) | `decidir` | `redigir`, `validar`, a aresta de `validar`, `pedir_confirmacao`, `gravar` | regra em código | nenhum |
| `texto_redigido` | `str` ou `None` | `redigir` | `validar`, `pedir_confirmacao`, `gravar` | o modelo (◆D5) | nenhum |
| `erro_validacao` | `dict` ou `None` | `validar` | a aresta de `validar`, `redigir`, `finalizar` | regra em código | nenhum |
| `pendencia`, `pendencia_id` | `dict`, inteiro | `pedir_confirmacao` | `confirmar`, `gravar` | o estado e a tabela `pendencias` | nenhum |
| `confirmacao` | `dict` (status, quem, quando; na aprovação com edição, também o texto original e o aprovado: `resumo_*` no H1, `mensagem_*` no H2; na rejeição com motivo, `motivo_rejeicao`) | `confirmar` | `gravar`, o log | o analista (ou o relógio, no prazo vencido) | nenhum |
| `desfecho` | `dict` | `gravar` | `finalizar` | o retorno da escrita no banco | nenhum |
| `termino`, `motivo` | `str` | `triagem`, `conferir_ressalva` ou `redigir` (teto, erro) e `finalizar` | as arestas; quem chama o grafo | regra em código | nenhum |
| `saida` | `dict` | `finalizar` | quem chama o grafo | `montar_saida` (`src/saida.py`) | nenhum |
| `passos` | `list[dict]` | os nós que registram um passo | o log e a saída | cada nó | `operator.add` (concatena) |
| `tentativas_redacao` | `int` | `redigir` | a aresta de `validar` | contagem | `operator.add` (soma) |
| `n_chamadas_modelo`, `tokens_entrada`, `tokens_saida`, `custo_usd` | número | `triagem`, `conferir_ressalva`, `redigir` | os tetos; o log | o campo `usage` da resposta da API | `operator.add` (soma) |
| `tokens_embedding` | número | `buscar` | o log (não entra nos tetos) | o campo `usage` da API de embedding; inclui a indexação dos guias quando o índice está vazio | `operator.add` (soma) |
| `segundos_gastos` | `float` | todos os nós, pelo embrulho `_no()` | o teto de tempo | o relógio | `operator.add` (soma) |

A coluna do reducer confere com a saída de `conferir_grafo.py` (§9.2).

**Campos com mais de um escritor.** `termino` e `motivo` são escritos por `triagem`,
`conferir_ressalva`, `redigir` e `finalizar`, e não têm reducer. `candidatos` é escrito por
`buscar` e, em seguida, por `conferir_ressalva`, que devolve a lista inteira com o score do
primeiro reduzido. Não é corrida: os nós rodam um por vez, e quando um nó de modelo
escreve o término a aresta seguinte leva direto a `finalizar`. Os campos escritos por dois nós
que precisam do total (tokens, custo, chamadas, tempo, passos) têm reducer.

**O que ficou na lista de mensagens: nada, porque não há lista.** Cada nó de modelo monta a
própria mensagem a partir dos campos (`_registro_para_o_modelo`), e a resposta volta
estruturada. No laço a classe da triagem ficava só nas mensagens; aqui ela é o campo `classe`,
e o log diz como o modelo leu cada chamado. O que o modelo escreve fora dos campos pedidos não
é guardado; a `justificativa` da triagem fica no passo, e não em campo próprio.

**O que não vai para o checkpoint.** O cliente da API, a conexão com o banco, os preços, os
tetos e o confirmador ficam no `Contexto` (o `context_schema` do grafo): são passados a cada
chamada e não são serializados.

O que é derivado e não guardado, e a razão de cada reducer, estão em `grafo.md` §3.2 e §3.3.

## 5. O orçamento

O que limita uma execução, e quem confere:

| Teto | Valor | O que conta | Quem confere |
|---|---|---|---|
| passos | 20 superpassos (`LIMITE_SUPERPASSOS`) | nós executados | o LangGraph (`recursion_limit`, com o nosso valor declarado no código) |
| tokens | 30 mil | entrada + saída, somadas nas chamadas ao modelo | `_teto()`, antes de cada chamada ao modelo |
| custo | US$ 0,05 | os tokens, ao preço de lista informado no `.env` | `_teto()` |
| tempo | 90 s | o tempo gasto **dentro dos nós**, somado em `segundos_gastos` | `_teto()` |
| redações | 2 por execução (`MAX_REDACOES`) | passagens pelo nó `redigir` | a aresta de `validar` |
| tentativas de triagem | 2 (`MAX_TENTATIVAS_TRIAGEM`) | respostas fora do contrato | o nó `triagem` |
| tentativas de ressalva | 2 (`MAX_TENTATIVAS_RESSALVA`) | respostas fora do contrato, ou com uma frase que não é do guia | o nó `conferir_ressalva` |
| tentativas de transporte | 5 por chamada ao modelo | limite de requisições ou conexão | `_chamar()` |

Tokens, custo e tempo são os da classe `Orcamento` do laço (`src/agente.py`), com os mesmos
valores. **O teto de 8 passos do laço não vale no grafo**: o caminho técnico tem mais nós do que
o laço tinha passos, e o limite passou a ser o de superpassos (`grafo.md` §5).

**O que impede uma execução de não acabar** é a forma do grafo: o único retorno
(`validar → redigir`) tem contador, e todo outro caminho anda para a frente até `finalizar`. O
limite de superpassos é a segunda barreira, para o caso de uma alteração criar um ciclo que não
devia existir.

**A espera pelo analista não conta no teto de tempo.** `segundos_gastos` soma só o tempo dentro
dos nós, e o processo termina enquanto espera. A espera tem o seu próprio limite, que é o prazo
de 20 minutos (§7).

Limites conhecidos:

- **Os tetos de tokens, custo e tempo só são conferidos antes das chamadas ao modelo.** Um nó de
  código que demore não é interrompido, e uma chamada ao modelo em andamento também não.
- **Os tetos nunca foram atingidos com o modelo real.** Nas 24 execuções medidas, a mais cara
  gastou 1.968 tokens e a mais longa 3,0 s. O que prova os tetos são os testes offline
  (`test_teto_de_tokens_termina_antes_da_redacao`, `test_limite_de_superpassos_e_declarado_no_codigo`).

## 6. O término

Toda execução grava por que parou (campos `termino` e `motivo`). São quatro términos, os mesmos
do laço:

| Término | Quando | O que ficou gravado no banco |
|---|---|---|
| ●T1 `respondeu` | `gravar` escreveu um desfecho e `finalizar` o registrou. Inclui a execução retomada: o analista aprovou, ou ele rejeitou ou o prazo venceu e o código gravou a `fila_humana` | o desfecho; no prazo vencido de um chamado que seria P1, também uma linha em `avisos_gestor` |
| ●T2 `orcamento_esgotado` | um teto de tokens, custo ou tempo estourou antes de uma chamada ao modelo, ou o limite de superpassos foi atingido; o motivo diz qual (`tokens: 1200/1000`, `superpassos: limite de 20 atingido`) | nada: os tetos são conferidos antes de `gravar` |
| ●T3 `erro_fatal` | (1) API indisponível depois de 5 tentativas; (2) a API recusou a chamada; (3) a triagem ou a conferência da ressalva veio fora do contrato 2 vezes; (4) o texto redigido foi reprovado 2 vezes; (5) a saída não coube no schema | nada nos casos (1) a (4). No (5) o desfecho já foi gravado: `finalizar` vem depois de `gravar` |
| ●T4 `aguardando_humano` | o grafo está parado no `interrupt` do nó `confirmar`, dentro do prazo. Não passa por `finalizar`: é o que `rodar_grafo()` devolve enquanto a execução espera | nada em `chamados_internos` nem em `encaminhamentos`. A ação e o prazo ficam na tabela `pendencias`, e o estado no checkpoint |

O ●T4 não é um fim: é o único término que a mesma execução troca depois, por ●T1, quando o
analista aprova, rejeita ou o prazo vence (§7). Nenhuma das três saídas deixa o chamado sem
desfecho.

**O que mudou em relação ao laço.** Não existe mais o lembrete: no laço, o modelo podia encerrar
sem gravar desfecho, e o código insistia até 2 vezes. No grafo quem grava é o nó `gravar`, e o
modelo não tem como encerrar a execução. Também não existe mais o caso de teto estourado depois
da escrita.

Para saber se o chamado teve desfecho, vale o campo `desfecho`, e não o término. O verificador
(`src/verificar.py`) confere o banco.

**Erro que não é término.** O id inexistente não é erro para o grafo: é a rota "não existe", que
leva à `fila_humana`. O texto reprovado e a triagem fora do contrato voltam ao modelo uma vez
antes de virar ●T3.

## 7. O humano

**Um único nó em que o sistema para e espera, `confirmar`, para duas ações: abrir chamado
interno [H1] e enviar o pedido de informação ao cliente [H2].** A tabela descreve o H1; o que
muda no H2 vem logo depois dela.

| | |
|---|---|
| Onde | nó `confirmar`, depois de `decidir`, `redigir` e `validar`, e antes de `gravar` |
| Critério | ação irreversível |
| Quem é chamado | o **analista de suporte** (perfil do `case.md` §2.2) |
| O que ele vê | a ação, o id do chamado, a categoria, o resumo redigido, o time de destino, o `kb_id`, a prioridade prevista, a hora do pedido, a hora em que o prazo vence, quantos minutos faltam e a consequência da aprovação (`python src/main.py --pendencias`). A prioridade da tela é a prevista: a do chamado é calculada de novo na gravação |
| O que ele devolve | `--aprovar TKT-0000`, `--aprovar TKT-0000 --resumo "texto corrigido"` (aprovar **editando**) ou `--rejeitar TKT-0000` |
| Se aprova editando | o chamado é aberto com o resumo do analista. Só o resumo é editável: categoria, time e prioridade continuam vindo do procedimento. O texto passa pela mesma regra do texto do modelo antes de o grafo continuar; recusado, nada é gravado e a ação continua à espera (`humano.md` §2.1) |
| Se aprova no prazo | `gravar` abre o chamado e `finalizar` conclui; término ●T1 |
| Se rejeita no prazo | o chamado interno **não** é aberto; `gravar` registra `fila_humana` com as considerações do agente (motivo `acao_rejeitada`); término ●T1 |
| Se não responde em 20 minutos | o chamado interno **não** é aberto; `gravar` registra `fila_humana` com as considerações do agente (motivo `confirmacao_nao_recebida`); se o chamado seria **P1**, grava também o aviso ao gestor; término ●T1 |

**O que muda no [H2]** (12/10/2026; `humano.md` §2.4): a tela traz o relato do cliente e a
mensagem redigida, sem guia, score nem prioridade; o texto editável é a mensagem
(`--aprovar TKT-0000 --mensagem "texto corrigido"`), que passa pela regra do pedido ao cliente
(nenhuma informação interna); aprovado, `gravar` registra o pedido como enviado; rejeitado ou
vencido, registra `fila_humana` com a mensagem redigida, e o pedido único do chamado não é gasto;
o gestor não é avisado, porque não há prioridade prevista.

**Como a pausa funciona.** São dois nós. `pedir_confirmacao` monta a ação, marca `pedido_em` e
`vence_em` e grava a linha na tabela `pendencias`. `confirmar` chama `interrupt`. A separação
existe porque o nó que pausa roda de novo, desde o começo, na retomada: a hora do pedido e a
linha em `pendencias` não podem ser refeitas, e por isso ficam num nó anterior, que roda uma
vez. Nada com efeito colateral acontece antes do `interrupt`.

**A espera é assíncrona, e atravessa processos.** O `interrupt` grava o estado no checkpointer
(`SqliteSaver`, em `dados/checkpoints.db`), endereçado pelo `thread_id`, que é o id do chamado.
O processo termina em ●T4. O analista responde de outro processo
(`python src/main.py --aprovar TKT-0000`), que envia `Command(resume=...)` ao mesmo thread
(`retomar_grafo()`): o grafo continua do nó `confirmar`, sem nova triagem, nova busca ou nova
redação, e **sem nova chamada ao modelo**.

**O prazo.** O analista tem **20 minutos** para confirmar ou rejeitar, contados do pedido
(`case.md` §2.1; constante `PRAZO_CONFIRMACAO_MIN`, em `src/ferramentas.py`). Vencido o prazo, a
ação não é executada e o código grava um encaminhamento à `fila_humana` com as considerações do
agente: a ação proposta, a prioridade que o chamado teria, o procedimento e o score que a
sustentam, o resumo já redigido e o motivo "confirmação não recebida em 20 minutos". A
`suficiencia` da saída é negativa.

**A rejeição tem o mesmo destino**, com o motivo "ação rejeitada pelo analista de suporte". A
função é a mesma do laço (`encaminhar_pendencia`, em `src/ferramentas.py`).

**Prazo vencido em chamado P1 avisa o gestor.** A fila humana é lida pelo mesmo analista que não
respondeu. Por isso, quando o prazo vence e o chamado interno seria P1, o código grava também uma
linha na tabela `avisos_gestor`. A prioridade usada é a **prevista**: a base do procedimento mais
a reincidência, pela mesma regra da abertura (`prioridade_prevista`, em `src/db.py`). O aviso não
é um segundo desfecho, e a rejeição não avisa o gestor, porque o analista já viu o chamado.

**O relógio vale antes da pessoa.** O nó `confirmar` compara a hora da resposta com o `vence_em`
antes de olhar a decisão: uma aprovação que chega depois do prazo é tratada como prazo vencido.
O silêncio nunca vira aprovação, e a aprovação tardia também não.

**Aprovar duas vezes** não repete nada: a segunda resposta não encontra o grafo parado em
`confirmar` e não envia nada (`retomar_grafo()` devolve `None`). Se chegasse a `gravar`, a chave
`ticket:kb_id` devolveria o chamado já aberto.

**A pausa, demonstrada com o modelo real** (`logs/grafo-pausa/`, 10/10/2026, commit `083d132`,
`ministral-8b-latest`). Quatro comandos, cada um em um processo; a saída de terminal dos quatro
está em `saida-terminal.txt`:

| # | Comando | O que aconteceu |
|---|---|---|
| 1 | `python src/main.py TKT-0007 --rodada grafo-pausa` (sem `--auto-aprovar`) | triagem técnica, KB-102 com score 0,86, resumo redigido. Parou em `confirmar` às 23:51:58, com prazo até 00:11:58; término `aguardando_humano`, nada gravado (`TKT-0007-pausado.json`) |
| 2 | `python src/main.py --pendencias --rodada grafo-pausa` | 1 ação aguardando, com a ação, o resumo e "faltam: 20 min" |
| 3 | `python src/main.py --aprovar TKT-0007 --rodada grafo-pausa` | às 23:52:02 o grafo continuou de `confirmar`, abriu o `INC-0002` (Infraestrutura, P2) e terminou em `respondeu`, com as mesmas 2 chamadas ao modelo e os mesmos 1.755 tokens da pausa (`TKT-0007.json`) |
| 4 | o mesmo comando, de novo | "Não há confirmação pendente para TKT-0007." No banco: um chamado interno para o `TKT-0007`, uma pendência com status `aprovada`, nenhum encaminhamento |

**A aprovação com edição, demonstrada** (`logs/grafo-caso-6/`, 11/10/2026, commit `a328236`): o
`TKT-0007` pausou; uma edição com o resumo "ok" foi recusada sem gastar a aprovação; a aprovação
com o resumo corrigido abriu o `INC-0002` com o texto do analista, e o log guardou os dois
resumos; a mesma aprovação enviada de novo não encontrou nada pendente. No banco: um chamado
interno, uma pendência `aprovada`, nenhum encaminhamento (`humano.md` §5).

Dois limites dessas demonstrações: quem respondeu foi quem rodou os comandos, segundos depois, e
não um analista; e o prazo vencido, no grafo, está coberto só por testes offline
(`tests/test_grafo.py`). A rejeição do H1 foi exercitada com o modelo real em 11/10/2026
(`logs/grafo-memoria-1/` e `logs/grafo-procedural/`); a do H2, não.

Limites do que foi implementado:

- **O aviso ao gestor é um registro, não uma notificação.** O sistema é simulado e não tem canal
  de mensagem: o aviso é uma linha em `avisos_gestor`, que o gestor precisa consultar. Não há
  comando no `main.py` para listá-la.
- **O prazo é conferido, não cronometrado.** Não há processo em segundo plano. As pendências
  vencidas são encaminhadas no começo do próximo comando do `main.py` (`vencer_pendencias`). Se
  ninguém rodar nada, o chamado fica na pausa até alguém rodar: a regra garante que a ação
  vencida nunca é executada, mas não garante que a fila humana a receba no minuto 20.
- **O [H3] não existe.** A espera pela resposta do cliente não foi implementada
  (`humano.md` §7): aprovado o pedido, a execução termina em ●T1.
- **O [H2] não envia nada.** O sistema simulado não tem canal de mensagem: aprovar o pedido grava
  uma linha com `enviado_em`. Não há falha de entrega nem reenvio (`humano.md` §2.4).
- **A pausa fica em dois arquivos.** A fila do analista é a tabela `pendencias`
  (`dados/tickets.db`), e o estado da execução é o checkpoint (`dados/checkpoints.db`).
  `--reset` e `--todos` recriam o primeiro e não o segundo; por isso `--todos` exige
  `--auto-aprovar`.
- **A edição é só do texto (o resumo ou a mensagem), e pela linha de comando.** O analista
  redigita o texto inteiro; não há editor que parta do texto do modelo.

`--auto-aprovar` troca o analista por uma aprovação automática e existe só para a demonstração:
com ele o nó `confirmar` recebe a resposta na hora, sem `interrupt`. As três rodadas de 8 casos
foram geradas assim.

**Onde uma pessoa entra sem que o sistema espere por ela.** Os destinos gravados em
`encaminhamentos` entregam o chamado a alguém, mas a execução termina antes:

| Destino | Quem lê |
|---|---|
| `fila_humana` | o analista de suporte, que decide o que fazer com o chamado |
| `anotacao_interna` | o analista de suporte, que valida e executa a correção sugerida |
| `fila_comercial` | o time comercial |
| `devolver_cliente` | o analista de suporte confirma antes ([H2]); depois disso, hoje ninguém: o pedido fica registrado como enviado, mas não há canal que o leve ao cliente, nem espera pela resposta. O desenho prevê o prazo de 3 dias úteis para a resposta do cliente, depois do qual o chamado vai para a `fila_humana` (`case.md` §2.1) |

## 8. O nível de autonomia (§3.3)

**O nível é workflow com roteador.** No grafo, que é o caminho padrão, o caminho é fixo em
código e o modelo decide **a rota**: no nó `triagem` ele escolhe a classe do chamado e diz se o
log aponta outro serviço (as decisões ◆D1 e ◆D3 abaixo); o desfecho sai do nó `decidir`, que é
código. O laço da Parte 1 tomava as mesmas duas decisões dentro de um laço de ferramentas curto.
O que segue é a defesa feita com o laço rodando, que é o que justificou descer um degrau; o
resultado do grafo está no fim da seção. As marcas ■G3, ■G4 e ■G5 citadas abaixo são os portões
do laço (tabela no §2), e ◆D4 é a busca repetida, que só o laço tem.

**Por que o workflow não servia.** Um workflow tem o caminho fixo em código. Aqui o caminho
depende de duas decisões sobre texto livre, as duas marcadas no diagrama:

- **◆D1, a triagem.** O cliente não preenche categoria. Decidir se "quero um servidor dedicado" é
  comercial, ou se "meu servidor não funciona" tem informação suficiente, não cabe em regra. No
  `TKT-0004` (as três rodadas) o modelo foi direto para `fila_comercial`, em 2 passos, sem buscar
  na base. Na rodada 3 fez o mesmo com o `TKT-0005`: 2 passos, sem busca, pedido devolvido ao
  cliente.
- **◆D3, o relato contra o log.** É a decisão que nenhum portão do código consegue tomar. No
  `TKT-0002` da rodada 2 (`logs/rodada-2-prompt-v5/TKT-0002.json`), a busca devolveu o `KB-106`
  com score 0,67, acima do limiar, e o procedimento é de escalonamento: **os portões ■G3 e ■G4
  teriam deixado abrir o chamado**. O modelo não abriu. Viu que o cliente relata Webmail fora do
  ar e que o log aponta falha de DNS, e mandou o chamado à `fila_humana` com a divergência
  escrita. Sem essa decisão, o sistema abriria um chamado para a Infraestrutura sem saber de quem
  é o nameserver (`case.md` §2.12, regra 6).

  **A rodada 3 mostra o que acontece quando essa decisão falha**
  (`logs/rodada-3-prompt-v5/TKT-0002.json`). O modelo começou certo: no passo 1 chamou
  `fila_humana` com a divergência escrita. O portão ■G5 recusou, porque não havia busca. Ele
  buscou, recebeu o mesmo `KB-106` com o mesmo score 0,67, e no passo 3 abriu o chamado interno:
  P1, para a Infraestrutura. Os portões ■G3 e ■G4 deixaram passar, como previsto acima, e a
  execução rodou com `--auto-aprovar`. É a mesma entrada da rodada 2, com o resultado oposto. O
  que segura o `TKT-0002` é só o modelo, e ele não segura sempre.

**Por que não o agente.** O que colocaria o sistema acima de um roteador é decidir, em tempo de
execução, **quantos** passos dar e **quais**: buscar de novo (◆D4) e se recuperar de um erro de
ferramenta. As 24 execuções com o `agente-v5.md` não sustentam esse degrau:

| Capacidade | O que as rodadas mostram |
|---|---|
| Busca repetida (◆D4) | aconteceu em 3 das 24 execuções (`TKT-0002` na rodada 1, `TKT-0005` nas rodadas 1 e 2). Em nenhuma mudou o desfecho. No `TKT-0005` a busca nem devia ter ocorrido: o caso é de informação insuficiente. Na rodada 3 não houve nenhuma: 5 buscas, uma por execução que buscou |
| Recuperação de erro | no `TKT-0999` (id inexistente), o lembrete, que é código, foi usado nas três rodadas (1 lembrete na rodada 3) para o modelo registrar o desfecho. No `TKT-0002` da rodada 3 o modelo corrigiu a chamada depois do erro do portão ■G5 (fez a busca que faltava), e a correção terminou no desfecho errado |
| Tamanho do caminho | de 2 a 4 passos em todas as execuções, sempre consultar → (buscar) → escrever |

O laço continua sendo a forma da implementação, porque é ele que devolve ao modelo o erro de um
portão. Mas a decisão que o modelo toma dentro dele é de rota, e não de plano.

**Onde o roteador erra.** As decisões que só o modelo toma são também as que falham. Resultado
do verificador: 7 de 8 na rodada 1, 6 de 8 na rodada 2 e 7 de 8 na rodada 3. São quatro falhas em
24 execuções.

Três são de ◆D1, nas rodadas 1 e 2 (seed e texto do prompt anteriores à revisão de 10/10/2026):

- `TKT-0005` (rodadas 1 e 2): o modelo tratou como técnico um relato sem serviço nem sintoma, e
  o chamado foi para a `fila_humana` em vez de voltar ao cliente;
- `TKT-0003` (rodada 2): o modelo leu um problema técnico com exigência de prioridade como pedido
  fora da alçada.

Nessas três o erro foi para o lado seguro: nenhum chamado indevido foi aberto. Na rodada 3 os
dois casos passaram.

A quarta é de ◆D3, na rodada 3:

- `TKT-0002`: chamado interno P1 aberto para a Infraestrutura, quando o esperado é `fila_humana`
  (descrito acima, em ◆D3).

**É a única falha para o lado que não é seguro**: um chamado indevido, de prioridade máxima, que
nenhum portão em código barrou. A última barreira que restava era o analista, no [H1], e a rodada
usou `--auto-aprovar`. O log também mostra que o portão ■G5, criado para o `TKT-0003`, foi o que
devolveu ao modelo uma `fila_humana` que estava certa. Uma execução não prova que foi ele a
causa, mas a regra "fila humana só depois da busca" não tem exceção para a divergência entre
relato e log.

Limites desta medição:

- o prompt e a busca foram ajustados depois de ver as falhas nestes mesmos 8 casos (cabeçalho de
  `src/prompts/agente-v5.md`). O resultado não prova que o sistema generaliza;
- só a rodada 3 usa o seed e o texto atuais, e é uma execução por caso. O `TKT-0002` deu
  resultados opostos nas rodadas 2 e 3, com `temperature=0`: uma rodada não mede a frequência
  de nenhuma das falhas. As duas execuções do `agente-v5.md` no teste da regra da frase
  (`prompts.md` §3.2) repetiram a falha da rodada 3 no `TKT-0002`.

**O que o grafo mediu.** Três execuções dos 8 casos, com `ministral-8b-latest`, `temperature=0` e
`--auto-aprovar`, todas em 10/10/2026:

| Rodada | Hora | Commit | Verificador | Chamadas ao modelo | Tokens |
|---|---|---|---|---|---|
| `logs/grafo/` | 21h11 | `2ffb2b5 + alterações locais` | 8 de 8 | 15 | 12.623 |
| `logs/grafo-rodada-2/` | 23h51 | `083d132` | 8 de 8 | 15 | 12.687 |
| `logs/grafo-rodada-3/` | 23h51 | `083d132` | 8 de 8 | 15 | 12.664 |

Para comparar: o laço, na rodada 3 do `agente-v5.md`, deu 7 de 8 com 31 chamadas e 69.889 tokens.

A decisão que só o modelo toma está no nó `triagem` do diagrama do §1: ◆D1 (a classe) e ◆D3 (o
log aponta outro serviço). Nas três rodadas:

- **◆D1:** as 21 triagens deram a classe esperada. `TKT-0004` saiu "comercial" e `TKT-0005`
  "insuficiente" nas três vezes, e nenhum dos dois passou pela busca.
- **◆D3:** no `TKT-0002` a triagem marcou a divergência nas três vezes. A busca devolveu o
  `KB-106` com score 0,75, 0,67 e 0,75, sempre acima do limiar, e o nó `decidir` mandou o chamado
  à `fila_humana`, porque confere a divergência antes do score. Nos outros casos técnicos o campo
  veio falso, e os chamados que deviam ser abertos foram.

A decisão continua sendo do modelo. O que mudou é que ela é tomada antes de o artigo aparecer, e
o código não a desfaz: no laço, com o mesmo artigo na mão, o modelo abriu o chamado indevido em
três de três execuções com o texto atual da v5.

Limites desta medição:

- **São os mesmos 8 casos, e os dois prompts foram escritos depois de ver as falhas do laço
  neles.** Três rodadas iguais mostram que o resultado se repete nestes casos; não mostram que o
  sistema generaliza.
- **A redação não tem verificador.** O que se confere é o desfecho gravado.
- **A primeira rodada é de um commit anterior** à troca do caminho padrão; o `src/grafo.py` das
  três é o mesmo, salvo o texto de abertura do arquivo.

## 9. O grafo (§6.1, §6.2, §6.4, §7.1 e §8.1)

O grafo existe desde 10/10/2026: `StateGraph` em [`src/grafo.py`](../src/grafo.py), compilado uma
vez (objeto `GRAFO`), com `langgraph==1.2.14` e `langgraph-checkpoint-sqlite==3.1.1` fixados no
`requirements.txt`. É o caminho padrão do `main.py`; o laço da Parte 1 roda com `--laco`, para
os dois serem comparados nos mesmos casos. Foi medido três vezes com o modelo real, 8 de 8 no
verificador nas três (§8; `grafo.md` §6), e a pausa do [H1] foi demonstrada entre processos
(§7). O que é do código está provado por 75 testes offline (`tests/test_grafo.py`).

O §1 mostra o sistema inteiro (entrada, dados, checkpoint, términos). Esta seção mostra o mesmo
grafo nó a nó, com a chave de cada aresta condicional, para ser conferido contra o código.

### 9.1 O desenho

```
LEGENDA   [nó]   ◇ aresta condicional, com a chave do mapa de destinos entre aspas
          ⏸ ponto de parada (interrupt)   ● término
          MODELO = o nó chama o modelo      código = o nó não chama o modelo

START
  │
  ▼
[entrada]            código   o texto do chamado, como chegou (ou o registrado para o id)
  │
  ▼
[consultar]          código   lê o chamado, o plano, o log anexado e o histórico do cliente
  │
  ◇ _rota_consultar                              decide: código (campo vazio)
  ├─ "nao_existe" ─────────────────────────────► [decidir]
  └─ "existe"
        ▼
[triagem]            MODELO   JSON validado: classe, log_aponta_outro_servico, termos_busca
  │
  ◇ _rota_triagem                                decide: o MODELO (a classe); o código lê o valor
  ├─ "encerrar"   teto, API fora ou JSON inválido 2 vezes ──► [finalizar]
  ├─ "sem_busca"  comercial, insuficiente, fora_da_alcada ──► [decidir]
  └─ "tecnico"
        ▼
[buscar]             código   busca os procedimentos pelo vetor do relato (cosseno); devolve o score
  │
  ◇ _rota_buscar                                 decide: código
  ├─ "decidir"    o 1º guia não passa de 0,5, já caiu numa ressalva literal, ou não declara ressalvas ──► [decidir]
  └─ "conferir"
        ▼
[conferir_ressalva]  MODELO   JSON validado: cai_na_ressalva, frase, motivo. O código só BAIXA o score (x 0,4)
  │
  ◇ _rota_conferir                               decide: código
  ├─ "encerrar"   teto, API fora ou JSON inválido 2 vezes ──► [finalizar]
  └─ "decidir"
        ▼
[decidir]            código   escolhe o desfecho (regras de rota + portão de confiança):
  │                             id inexistente ........................... fila_humana
  │                             comercial ................................ fila_comercial
  │                             fora_da_alcada ........................... fila_humana
  │                             insuficiente, sem pedido anterior ........ devolver_cliente
  │                             insuficiente, com pedido anterior ........ fila_humana
  │                             técnico, log aponta outro serviço ........ fila_humana  (antes do score)
  │                             técnico, sem artigo ou score < 0,5 ....... fila_humana
  │                             técnico, score ≥ 0,5, guia "escalar" ..... abrir_chamado_interno
  │                             técnico, score ≥ 0,5, guia "anotar" ...... anotacao_interna
  ▼
[redigir]            MODELO   JSON validado: o texto (resumo ou mensagem) do desfecho já decidido
  │
  ◇ _rota_redigir                                decide: código
  ├─ "encerrar"   teto ou API fora ────────────► [finalizar]
  └─ "avaliar"
        ▼
[validar]            código   tamanho mínimo; pedido ao cliente sem informação interna
  │
  ◇ _rota_validar                                decide: código
  ├─ "redigir_de_novo"  reprovado, 1ª vez ─────► [redigir]
  ├─ "encerrar"         reprovado, 2ª vez ─────► [finalizar]
  ├─ "reversivel" ─────────────────────────────► [gravar]
  └─ "irreversivel"     abrir_chamado_interno (H1) ou devolver_cliente (H2)
        ▼
[pedir_confirmacao]  código   monta a ação, marca pedido_em e vence_em (20 min), grava em `pendencias`
  │
  ▼
[confirmar]          ⏸ H1 H2  interrupt: espera o analista de suporte
  │                           decide: o relógio, depois a pessoa → aprovada · rejeitada · vencida
  ▼
[gravar]             código   aprovada, H1 → abre o chamado interno (chave ticket:kb_id)
  │                           aprovada, H2 → registra o pedido como enviado (um por chamado)
  │                           rejeitada ou vencida → fila_humana com as considerações do agente
  │                           vencida, e o chamado seria P1 → aviso ao gestor (só no H1)
  │                           desfecho reversível → uma linha em `encaminhamentos`
  ▼
[finalizar]          código   término, motivo e saída validada
  │                           ● respondeu · ● orcamento_esgotado · ● erro_fatal
  ▼
END

Fora dos nós:
  parado no interrupt ............ a chamada devolve ● aguardando_humano; a execução continua
                                   do checkpoint quando o analista responde ou o prazo vence
  LIMITE_SUPERPASSOS estourado ... ● orcamento_esgotado (recursion_limit = 20, declarado no código)
```

Os nós, as arestas condicionais com quem decide cada uma e os términos estão detalhados em
[`grafo.md`](grafo.md) §1.

### 9.2 A conferência contra o código (§6.4)

Saída de `python conferir_grafo.py`, de 11/10/2026 (com o nó `conferir_ressalva`), conferida de
novo em 12/10/2026 sem diferença. O script está na raiz e importa o objeto `GRAFO` de
`src/grafo.py`, o mesmo que o `main.py` executa.

```
langgraph 1.2.14
checkpointer: SqliteSaver   recursion_limit declarado: 20

NÓS (12)
  entrada
  consultar
  triagem
  buscar
  conferir_ressalva
  decidir
  redigir
  validar
  pedir_confirmacao
  confirmar
  gravar
  finalizar

ARESTAS FIXAS (7)
  __start__          -> entrada
  confirmar          -> gravar
  decidir            -> redigir
  entrada            -> consultar
  gravar             -> finalizar
  pedir_confirmacao  -> confirmar
  finalizar          -> __end__

ARESTAS CONDICIONAIS (15), com a chave do mapa de destinos
  buscar             -> conferir_ressalva  [conferir]
  buscar             -> decidir            [None]
  conferir_ressalva  -> decidir            [None]
  conferir_ressalva  -> finalizar          [encerrar]
  consultar          -> decidir            [nao_existe]
  consultar          -> triagem            [existe]
  redigir            -> finalizar          [encerrar]
  redigir            -> validar            [avaliar]
  triagem            -> buscar             [tecnico]
  triagem            -> decidir            [sem_busca]
  triagem            -> finalizar          [encerrar]
  validar            -> finalizar          [encerrar]
  validar            -> gravar             [reversivel]
  validar            -> pedir_confirmacao  [irreversivel]
  validar            -> redigir            [redigir_de_novo]

CAMPOS DO ESTADO, e o reducer de cada um
  id_ticket              (sobrescreve)
  modelo                 (sobrescreve)
  temperatura            (sobrescreve)
  execucao_id            (sobrescreve)
  executado_em           (sobrescreve)
  commit                 (sobrescreve)
  prazo_confirmacao_min  (sobrescreve)
  texto_recebido         (sobrescreve)
  texto                  (sobrescreve)
  ticket                 (sobrescreve)
  classe                 (sobrescreve)
  log_diverge            (sobrescreve)
  termos                 (sobrescreve)
  candidatos             (sobrescreve)
  ressalvas_do_melhor    (sobrescreve)
  desfecho_proposto      (sobrescreve)
  texto_redigido         (sobrescreve)
  erro_validacao         (sobrescreve)
  pendencia              (sobrescreve)
  pendencia_id           (sobrescreve)
  confirmacao            (sobrescreve)
  desfecho               (sobrescreve)
  termino                (sobrescreve)
  motivo                 (sobrescreve)
  saida                  (sobrescreve)
  passos                 add
  tentativas_redacao     add
  n_chamadas_modelo      add
  tokens_entrada         add
  tokens_saida           add
  tokens_embedding       add
  custo_usd              add
  segundos_gastos        add

MERMAID (get_graph().draw_mermaid())
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	entrada(entrada)
	consultar(consultar)
	triagem(triagem)
	buscar(buscar)
	conferir_ressalva(conferir_ressalva)
	decidir(decidir)
	redigir(redigir)
	validar(validar)
	pedir_confirmacao(pedir_confirmacao)
	confirmar(confirmar)
	gravar(gravar)
	finalizar(finalizar)
	__end__([<p>__end__</p>]):::last
	__start__ --> entrada;
	buscar -. &nbsp;conferir&nbsp; .-> conferir_ressalva;
	buscar -.-> decidir;
	conferir_ressalva -.-> decidir;
	conferir_ressalva -. &nbsp;encerrar&nbsp; .-> finalizar;
	confirmar --> gravar;
	consultar -. &nbsp;nao_existe&nbsp; .-> decidir;
	consultar -. &nbsp;existe&nbsp; .-> triagem;
	decidir --> redigir;
	entrada --> consultar;
	gravar --> finalizar;
	pedir_confirmacao --> confirmar;
	redigir -. &nbsp;encerrar&nbsp; .-> finalizar;
	redigir -. &nbsp;avaliar&nbsp; .-> validar;
	triagem -. &nbsp;tecnico&nbsp; .-> buscar;
	triagem -. &nbsp;sem_busca&nbsp; .-> decidir;
	triagem -. &nbsp;encerrar&nbsp; .-> finalizar;
	validar -. &nbsp;encerrar&nbsp; .-> finalizar;
	validar -. &nbsp;reversivel&nbsp; .-> gravar;
	validar -. &nbsp;irreversivel&nbsp; .-> pedir_confirmacao;
	validar -. &nbsp;redigir_de_novo&nbsp; .-> redigir;
	finalizar --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

**O que a conferência mostra, contra o desenho:**

- os 12 nós do desenho são os 12 nós do grafo compilado;
- as 7 arestas fixas e as 15 condicionais (seis pontos de decisão) são as do desenho, com as
  mesmas chaves (a chave `None` que a saída mostra é a chave igual ao nome do destino, `decidir`);
- não há aresta condicional depois de `confirmar`: a resposta do analista é lida por `gravar`,
  como o desenho diz.

O desenho foi corrigido depois de escrever o código. A proposta anterior não tinha os nós
`decidir` e `pedir_confirmacao`, e tinha o nó `aguardar_cliente`, que não foi implementado
(`grafo.md` §1). **O desenho do §9.1 ficou sem o nó `conferir_ressalva` de 11/10 a 12/10/2026**,
enquanto a saída acima já o listava: a divergência foi achada ao conferir os dois, e quem estava
errado era o desenho.

### 9.3 Onde está o resto

| Item do enunciado | Onde está |
|---|---|
| Tabela de padrões usados, com a justificativa (§6.2) | `grafo.md` §2 |
| Tabela de campos do estado do grafo, com reducers (§7.1) | §4 deste documento; a coluna do reducer confere com a saída acima |
| O que o framework não deu (§6.5) e a decisão que virou parâmetro (§6.6) | `grafo.md` §4 e §5 |

### 9.4 Os pontos de parada, no grafo (§8.1)

O grafo tem **um** nó que para, o `confirmar`, e ele atende dois pontos de parada, o [H1] e,
desde 12/10/2026, o [H2]:

| | |
|---|---|
| Critério | ação irreversível: abrir chamado interno (H1) e enviar o pedido de informação ao cliente (H2) |
| Como para | `interrupt`, com o estado no checkpointer em SQLite (`dados/checkpoints.db`), endereçado pelo `thread_id` = id do chamado |
| Como continua | `Command(resume=...)`, por `retomar_grafo()`. Os comandos são os mesmos do laço: `--aprovar`, `--rejeitar` e o vencimento do prazo, que reconhecem pela pendência de qual dos dois caminhos é a pausa |
| Regras | as do §7: 20 minutos, o relógio antes da pessoa, rejeição e prazo vencido na fila humana, aviso ao gestor no P1 vencido (só no H1) |

O H2 não mudou a saída de `conferir_grafo.py` (§9.2): a aresta `validar → pedir_confirmacao` é a
mesma, com a chave `irreversivel`; mudou a regra que devolve a chave (`_rota_validar`). A espera
pela resposta do cliente (H3) não existe no grafo nem no laço, e o H2 não existe no laço
(`humano.md` §7).

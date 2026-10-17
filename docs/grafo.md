# O grafo (Parte 2, itens 6 e 7)

> **Estado deste documento: 10/10/2026.** O grafo existe: é o `StateGraph` de
> [`src/grafo.py`](../src/grafo.py), compilado uma vez (objeto `GRAFO`), com o LangGraph fixado no
> `requirements.txt` (`langgraph==1.2.14`, `langgraph-checkpoint-sqlite==3.1.1`). O desenho abaixo
> foi conferido contra a saída de `python conferir_grafo.py`, que está colada em
> [`arquitetura.md`](arquitetura.md) §9.
>
> **O que foi medido:** três execuções dos 8 casos com o modelo real, 8 de 8 no verificador nas
> três, e uma pausa real no H1, retomada por outro processo (§6). Em 12/10/2026 o gabarito passou a 40 casos, e três execuções
> deram 36 de 40 (§6.6). O que é do código está provado por 78 testes offline
> (`tests/test_grafo.py`), com modelo roteirizado.
>
> **12/10/2026:** o pedido de informação ao cliente passou a esperar o analista (H2), no mesmo nó
> `confirmar`, sem nó nem aresta novos (§6.3). A saída de `conferir_grafo.py` não mudou.
>
> **O grafo é o caminho padrão do `main.py`** desde 10/10/2026, e grava em `logs/grafo/`. O laço
> da Parte 1 (`src/agente.py`) roda com `--laco` e grava em `logs/`, para os dois poderem ser
> comparados nos mesmos 8 casos.

## 1. O desenho

O ponto de partida é a medição do `arquitetura.md` §8: o sistema é um roteador, e o que o modelo
decide é a rota e a redação, não a sequência de passos. O grafo tira do modelo a escolha da
próxima ferramenta e deixa com ele a triagem, a redação e, quando o primeiro guia declara situações
que não cobre, a leitura dessa ressalva (nó `conferir_ressalva`, 11/10/2026).

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
  │                           no pedido ao cliente NÃO chama o modelo: o texto é o padrão, do código
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

**O que mudou em relação à proposta anterior deste documento**, ao escrever o código:

- **Entrou o nó `decidir`.** A proposta punha a escolha do desfecho nas arestas. No LangGraph uma
  aresta escolhe o destino e não escreve no estado, então a decisão virou um nó de código.
- **Entrou o nó `pedir_confirmacao`.** O nó que chama `interrupt` roda de novo, desde o começo,
  na retomada. A hora do pedido e a linha em `pendencias` não podem ser refeitas, então ficam num
  nó anterior, que roda uma vez.
- **Saiu o nó `aguardar_cliente`.** A espera pela resposta do cliente (H3) não foi implementada
  (`humano.md` §7). O `confirmar` atendia só o H1 até 12/10/2026; hoje atende também a
  confirmação do pedido ao cliente (H2), como a proposta previa (§6.3).
- **A triagem escolhe os termos de busca.** Quando o grafo foi escrito a busca era por palavra, e
  o relato inteiro diluía o score. Desde 11/10/2026 a busca é vetorial e consulta pelo relato; os
  termos continuam saindo da triagem porque alimentam o recuo para a busca por palavra, quando a
  API de embedding falha (`rag.md` §4).
- **Entrou o nó `conferir_ressalva`** (11/10/2026), com a aresta condicional depois de `buscar`:
  o vetor não enxerga as exceções de um guia (`rag.md` §4.2).

### 1.1 Os nós

| Nó | O que faz | Chama o modelo? | De onde veio, no laço |
|---|---|---|---|
| `entrada` | fixa o texto do chamado: o digitado ou o registrado para o id | não | `_entrada`, em `src/agente.py` (a mesma função) |
| `consultar` | lê chamado, plano, log anexado e histórico | não | ferramenta `consultar_ticket`. Deixou de ser escolha do modelo: toda execução consulta |
| `triagem` | classifica o assunto, diz se o log aponta outro serviço e escolhe os termos de busca | **sim** | passos 2, 3 e 4 do `agente-v5.md` |
| `buscar` | recupera os procedimentos, com score (cosseno do relato com cada guia) | não | ferramenta `buscar_base_conhecimento`. O modelo ainda escolhe os termos (que alimentam o recuo para a busca por palavra), mas não escolhe se busca |
| `conferir_ressalva` | o modelo lê as situações que o 1º guia não cobre (`nao_cobre`) e diz se o relato cai numa delas; o código baixa o score | **sim**, só o julgamento | o embedding não enxerga a exceção (`rag.md` §4.2). Só roda quando há o que conferir; só pode baixar o score |
| `decidir` | escolhe o desfecho | não | o passo 4 do `agente-v5.md` (que era do modelo) e os portões de `src/ferramentas.py` |
| `redigir` | redige o resumo do chamado ou a mensagem do encaminhamento. No `devolver_cliente` devolve o texto padrão do pedido (`PEDIDO_AO_CLIENTE`), sem chamar o modelo (12/10/2026; `prompts.md` §2.2) | **sim**, menos no pedido ao cliente | argumento `resumo` ou `mensagem` das ferramentas de escrita |
| `validar` | confere o texto redigido | não | validações de `src/ferramentas.py` |
| `pedir_confirmacao` | monta a ação como o analista vai vê-la, marca o prazo e grava em `pendencias` | não | parte de `abrir_chamado_interno` |
| `confirmar` | pausa com `interrupt` e lê a resposta | não | `Estado.confirmar` e `retomar`, em `src/agente.py` |
| `gravar` | escreve o desfecho no banco | não | `abrir_chamado`, `registrar_encaminhamento`, `registrar_pedido_cliente` (`src/db.py`; a última é só do grafo) e `encaminhar_pendencia` (`src/ferramentas.py`) |
| `finalizar` | fixa término e motivo e valida a saída | não | bloco `finally` do laço e `montar_saida` |

### 1.2 As arestas condicionais, e quem decide cada uma (§6.3)

São seis, todas com o mapa de destinos escrito em `_construir()`.

| Aresta | Função | Destinos | Degrau que decide | Por que esse degrau basta |
|---|---|---|---|---|
| depois de `consultar` | `_rota_consultar` | `triagem`, `decidir` | regra em código | é um campo vazio: id que não existe não tem o que classificar |
| depois de `triagem` | `_rota_triagem` | `buscar`, `decidir`, `finalizar` | **modelo**, com saída `Literal["tecnico", "comercial", "insuficiente", "fora_da_alcada"]`; o código só lê o valor | exige julgamento sobre texto livre. O schema garante uma classe válida, não a classe certa |
| depois de `buscar` | `_rota_buscar` | `conferir_ressalva`, `decidir` | regra em código | o 1º guia passaria do limiar, não tem ressalva literal e declara situações que não cobre |
| depois de `conferir_ressalva` | `_rota_conferir` | `decidir`, `finalizar` | regra em código | só confere se um teto estourou ou o contrato falhou |
| depois de `redigir` | `_rota_redigir` | `validar`, `finalizar` | regra em código | só confere se um teto estourou ou a API falhou |
| depois de `validar` | `_rota_validar` | `redigir`, `pedir_confirmacao`, `gravar`, `finalizar` | regra em código | texto reprovado, número de tentativas e tipo do desfecho são campos |

Duas decisões não são arestas, e sim nós:

- **A escolha do desfecho** é do nó `decidir` (código). Ele usa dois sinais do modelo, a classe e
  o booleano `log_aponta_outro_servico`, e o resto é campo, contagem no banco e limiar.
- **A resposta do analista** é lida pelo nó `confirmar`. Depois dele a aresta é fixa: o nó
  `gravar` olha o status (aprovada, rejeitada ou vencida) e escreve o que cabe.

O degrau do meio (embedding) não é usado em nenhuma aresta. A candidata seria a rota da triagem,
mas as classes "insuficiente" e "fora da alçada" não são assunto: dependem do que falta no texto
e do que o cliente pede.

### 1.3 Os términos

Os quatro do laço continuam (`arquitetura.md` §6):

| Término | Por onde a execução chega |
|---|---|
| `respondeu` | `gravar` escreveu um desfecho e `finalizar` o registrou |
| `orcamento_esgotado` | teto de tokens, custo ou tempo, conferido antes de cada chamada ao modelo (`triagem`, `conferir_ressalva`, `redigir`); ou o limite de superpassos |
| `erro_fatal` | a API falhou; a triagem ou a conferência da ressalva veio fora do contrato 2 vezes; o texto redigido foi recusado 2 vezes; a saída não coube no schema |
| `aguardando_humano` | o grafo está parado no `interrupt` do nó `confirmar`. Não passa por `finalizar`: é o que `rodar_grafo()` devolve enquanto a execução espera. Aprovação, rejeição e prazo vencido levam a `gravar` |

## 2. Os padrões (§6.2)

| Padrão | Onde, no grafo | Por que ele, e não o de baixo | Condição de não uso |
|---|---|---|---|
| sequencial com portão | `consultar → triagem → buscar → decidir → redigir → validar → gravar` | o nó `decidir` é o portão de confiança: impede a escrita quando a base não sustenta a ação. Sem ele, um score baixo viraria chamado interno | se toda rota pudesse agir sem conferência, o portão seria custo sem função |
| *router* | aresta depois de `triagem`, e as regras de `decidir` | os cinco desfechos pedem tratamentos diferentes, e a classe depende de texto livre. Uma sequência única faria a busca do caso técnico para todo chamado | se houvesse um só tipo de chamado |
| avaliador-otimizador | `redigir → validar → redigir`, no máximo 2 redações | o avaliador é **código**, não modelo. Existe porque a mensagem ao cliente não pode citar informação interna | se a validação nunca reprovar nas medições, o laço sai e fica só a validação |
| paralelização | **não usado** | os nós dependem um do outro: a triagem precisa do log que `consultar` lê, e a busca só ocorre na rota técnica | |
| orquestrador-trabalhador | **não usado** | não há subtarefas que variem em número de um chamado para outro | |
| agente (laço) | **não usado** | ver abaixo | |

**Por que o laço livre saiu.** Nas 24 execuções medidas com o `agente-v5.md`, o caminho foi
sempre consultar, buscar (ou não) e escrever, em 2 a 4 passos (`arquitetura.md` §8). O trabalho
cabe num workflow com roteador, que é o degrau mais barato.

**O que o workflow trata.** A única falha da rodada 3 do laço foi o `TKT-0002`: o modelo viu o
procedimento com score 0,67 e abriu um chamado indevido. No grafo a divergência é um campo da
triagem, e o nó `decidir` a confere **antes** de olhar o score. O teste offline
`test_divergencia_e_decidida_antes_do_score` prova a regra do código. Nas três rodadas medidas
(§6) o modelo marcou o campo, o `KB-106` veio com score 0,75, 0,67 e 0,75, e o chamado foi à fila
humana. Três rodadas nos mesmos casos não provam que ele marca o campo em qualquer chamado.

**O que se perdeu.** No laço, quando um portão recusava uma escrita, o modelo recebia o erro e
escolhia outra ação. No grafo esse caminho de volta não existe: `decidir` escolhe uma vez. O
único retorno ao modelo é o da redação reprovada.

## 3. O estado (§7)

### 3.1 Os campos (§7.1)

O estado é o `TypedDict` `EstadoGrafo`, em `src/grafo.py`. A coluna do reducer confere com a
saída de `conferir_grafo.py`. A mesma tabela, com a coluna "de onde veio" que o enunciado pede,
está em `arquitetura.md` §4; ao mudar um campo, as duas mudam juntas.

| Campo | Tipo | Quem escreve | Quem lê | Reducer |
|---|---|---|---|---|
| `id_ticket`, `modelo`, `temperatura`, `execucao_id`, `executado_em`, `commit`, `prazo_confirmacao_min`, `texto_recebido` | texto, número | `rodar_grafo()`, na entrada do grafo | todos; o log | nenhum |
| `texto` | `str` | `entrada` | `triagem`, `buscar`, `redigir` | nenhum |
| `ticket` | `dict` ou `None` | `consultar` | `_rota_consultar`, `triagem`, `decidir`, `redigir`, `gravar` | nenhum |
| `classe` | `str` | `triagem` | `_rota_triagem`, `decidir` | nenhum. **Novo:** no laço a classe ficava só nas mensagens |
| `log_diverge` | `bool` | `triagem` | `decidir` | nenhum. **Novo** |
| `termos` | `list[str]` | `triagem` | `buscar`, `redigir` | nenhum |
| `candidatos` | `list[dict]` | `buscar`; `conferir_ressalva` (só baixa o score do 1º) | `decidir`, `redigir`, `gravar`, a saída | nenhum |
| `ressalvas_do_melhor` | `list[str]` | `buscar` | a aresta de `buscar`, `conferir_ressalva` | nenhum |
| `desfecho_proposto` | `dict` (`acao`, `kb_id`, `motivo`) | `decidir` | `redigir`, `validar`, `_rota_validar`, `pedir_confirmacao`, `gravar` | nenhum. **Novo** |
| `texto_redigido` | `str` ou `None` | `redigir` | `validar`, `pedir_confirmacao`, `gravar` | nenhum |
| `erro_validacao` | `dict` ou `None` | `validar` | `_rota_validar`, `redigir`, `finalizar` | nenhum |
| `pendencia`, `pendencia_id` | `dict`, inteiro | `pedir_confirmacao` | `confirmar`, `gravar` | nenhum |
| `confirmacao` | `dict` (status, quem, quando; na aprovação com edição, também o texto original e o aprovado: `resumo_*` no H1, `mensagem_*` no H2; na rejeição com motivo, `motivo_rejeicao`) | `confirmar` | `gravar`, o log | nenhum |
| `desfecho` | `dict` | `gravar` | `finalizar` | nenhum |
| `termino`, `motivo` | `str` | `triagem`, `conferir_ressalva` ou `redigir` (teto, erro) e `finalizar` | as arestas, quem chama o grafo | nenhum |
| `saida` | `dict` | `finalizar` | quem chama o grafo | nenhum |
| `passos` | `list[dict]` | os nós que registram um passo | o log e a saída | `operator.add` (concatena) |
| `tentativas_redacao` | `int` | `redigir` | `_rota_validar` | `operator.add` (soma) |
| `n_chamadas_modelo`, `tokens_entrada`, `tokens_saida`, `custo_usd` | número | `triagem`, `conferir_ressalva`, `redigir` | os tetos, o log | `operator.add` (soma) |
| `tokens_embedding` | número | `buscar` | o log; o custo deles vai junto para `custo_usd` (teto de dinheiro), e não para o teto de tokens | `operator.add` (soma) |
| `segundos_gastos` | `float` | todos os nós | o teto de tempo | `operator.add` (soma) |

`termino` e `motivo` têm mais de um escritor (`triagem`, `conferir_ressalva`, `redigir`,
`finalizar`), mas nunca na mesma volta: quando um nó de modelo os escreve, a aresta seguinte leva
direto a `finalizar`. `candidatos` tem dois (`buscar` e, depois, `conferir_ressalva`), também em
voltas diferentes: o segundo devolve a lista inteira, com o score do primeiro guia reduzido.

### 3.2 Os reducers (§7.2)

- `passos`: concatenação. Cada nó acrescenta o seu registro; sem reducer, o último nó apagaria a
  trajetória.
- tokens, custo, chamadas ao modelo e `segundos_gastos`: soma. Três nós chamam o modelo, e os
  tetos precisam do total.
- `tentativas_redacao`: soma. O nó `redigir` devolve 1 a cada passagem.

Consequência prática dos reducers: uma execução nova no mesmo thread somaria com a anterior. Por
isso `rodar_grafo()` apaga o thread do chamado antes de começar (`src/grafo.py:874`), mesmo com o
checkpoint da execução concluída já apagado ao fim dela (§7): o que pode ter sobrado é uma pausa.

#### A demonstração: o que o sistema faz sem o reducer

`python demonstrar_reducer.py` (sem chave, sem API) compila o grafo de verdade duas vezes: com o
`EstadoGrafo` como está e com uma cópia em que alguns campos perderam o
`Annotated[..., operator.add]`. Os nós, as arestas e o roteiro do modelo são os mesmos; cada
chamada ao modelo roteirizado gasta 1.050 tokens. A saída está em
`logs/grafo-reducer/saida-terminal.txt` (12/10/2026, langgraph 1.2.14, commit `c849ce1`).

**Este grafo não tem nós paralelos**, e o defeito aparece do mesmo jeito: os nós rodam em
sequência, cada um escreve numa volta, e o campo sem reducer fica com o valor do último.

| Campo sem reducer | Caso | Com `operator.add` | Sem reducer | Levanta exceção? |
|---|---|---|---|---|
| `passos` | `TKT-0003` | 8 passos no estado | **1 passo**, o último (`abrir_chamado_interno`); o chamado é aberto igual e o término é `respondeu` | não |
| `n_chamadas_modelo`, `tokens_entrada`, `tokens_saida`, `custo_usd` | `TKT-0003`, com o teto de tokens em 2.000 | para antes da 3ª chamada: `orcamento_esgotado` (`tokens: 2100/2000`), nada gravado | **faz as 3 chamadas, gasta 3.150 tokens, abre o chamado** e registra 1 chamada e 1.050 tokens; término `respondeu` | não |
| `tentativas_redacao` | `TKT-0004`, com um texto que o `validar` reprova sempre | 2 redações e `erro_fatal` ("recusado em 2 tentativas"), 3 chamadas | o contador fica em 1 para sempre: **9 chamadas e 9.450 tokens**, até o `LIMITE_SUPERPASSOS` | sim, `GraphRecursionError` |

O que cada linha ensina:

- **`passos`**: é o caso do enunciado. Nada falha, o que foi gravado no banco é idêntico, e a
  trajetória some do estado, que é de onde o log e a saída a leem.
- **Consumo**: é o mais grave aqui. O teto de tokens é conferido antes de cada chamada com o
  total do estado (`_teto`); sem a soma, ele vê só a última chamada e nunca dispara. O orçamento
  deixa de valer sem erro, e o log registra um terço do que foi gasto.
- **`tentativas_redacao`**: este não é silencioso. O laço `redigir` ↔ `validar` perde o limite, e
  quem para a execução é o `recursion_limit`. Sem ele, não pararia.

**Com o modelo real.** `python demonstrar_reducer.py --real` repete as duas primeiras linhas
com o `ministral-8b-latest` (`temperature=0`) e a busca vetorial, no mesmo `TKT-0003`. A saída
está em `logs/grafo-reducer/saida-terminal-real.txt` (12/10/2026, commit `c849ce1`, 11 chamadas
ao modelo). "Gasto" é o consumo que a API devolveu em cada chamada, anotado fora do estado.

| Campo sem reducer | Com `operator.add` | Sem reducer | Levanta exceção? |
|---|---|---|---|
| `passos` | 8 passos; 3 chamadas, 2.460 tokens gastos e 2.460 no estado | **1 passo**; o chamado é aberto igual, término `respondeu` | não |
| Consumo, com o teto de tokens em 1.016 | para antes da 3ª chamada: `orcamento_esgotado` (`tokens: 1375/1016`), nada gravado | **3 chamadas (686, 661 e 1.143), 2.490 tokens gastos, chamado aberto**; o estado registra 1 chamada e 1.143 tokens | não |

O teto de 1.016 não é o do sistema (30.000): o script o põe entre a maior chamada antes da
última (686) e a soma delas (1.346), medidas na primeira execução, porque um chamado só não
chega perto do teto real. A linha do `tentativas_redacao` não foi executada com o modelo real:
ela depende de um texto que o `validar` reprove sempre, e o modelo não o escreve a pedido.

**Num grafo com ramos paralelos** (um grafo mínimo, no mesmo script, com dois ramos que escrevem
um item cada em `achados`):

| Situação | Com `operator.add` | Sem reducer |
|---|---|---|
| Ramos de tamanhos diferentes: `b` escreve uma volta depois de `a` | os 2 achados | **só o do ramo `b`**, sem erro: é o defeito que o enunciado descreve |
| Ramos que escrevem na mesma volta | os 2 achados | `InvalidUpdateError` ("Can receive only one value per step") |

**Limite honesto.** Na versão instalada do LangGraph a perda silenciosa só acontece quando as
escritas caem em voltas diferentes; na mesma volta o framework recusa. A cópia do estado sem
reducer é montada no script, e o teto de tokens das duas medições foi escolhido para o defeito
aparecer num chamado só. Com o modelo real há uma execução de cada variante, de um caso. Nenhum
teste offline fixa esse comportamento; ele pode mudar com a versão do LangGraph, e o script é o
que o confere.

### 3.3 O que não está no estado (§7.3)

**O que ficou na lista de mensagens.** Não há lista de mensagens no estado. Cada nó que chama o
modelo monta a própria mensagem a partir dos campos, e a resposta volta estruturada. O que o
modelo escreve fora dos campos pedidos não é guardado; a `justificativa` da triagem fica no
passo, e não em campo próprio.

**O que não vai para o checkpoint.** O cliente da API, a conexão com o banco, os preços, os tetos
e o confirmador ficam no `Contexto` (o `context_schema` do grafo): são passados a cada chamada e
não são serializados.

**O que é derivado e não guardado:**

| Dado | Por que não é guardado |
|---|---|
| reincidência do cliente | depende da janela de 30 dias; é recalculada por consulta no momento da escrita (`_reincidencia`, em `src/db.py`) |
| categoria, time e prioridade do chamado | vêm do procedimento, lidos pelo `kb_id` no momento de gravar. Guardá-los criaria uma segunda fonte, que o modelo ou o analista poderiam alterar |
| melhor score | deriva de `candidatos` |
| suficiência da saída | calculada por `montar_saida` a partir do desfecho e do score |
| número de buscas | é a contagem dos passos do nó `buscar` |

### 3.4 O estado entre agentes (§7.4)

O sistema tem um agente só. Não há estado passado entre agentes.

## 4. O que o framework não deu (§6.5)

Contagem de 12/10/2026, sobre o `src/grafo.py` desta data: **166 linhas de código nas quatro
frentes, de 671 do arquivo** (uma em cada quatro). A regra da contagem: linha de código é a que
não está em branco, não é só comentário e não é docstring; o arquivo tinha 944 linhas ao todo.
Depois da contagem, ainda em 12/10/2026, o arquivo ganhou 44 linhas **no fim** (a carga das
regras aprendidas, `memoria.md` §5.1) e passou a 988. Elas não entram em nenhuma das quatro
frentes, e as linhas citadas abaixo não mudaram de lugar. Em 17/10/2026 ganhou mais 13 linhas no
fim (`_consumo_do_embedding`, que leva o custo do embedding ao `custo_usd`) e passou a 1.001. Elas
pertencem à frente "os tetos" e não foram somadas à contagem; as linhas citadas continuam no lugar.
No mesmo dia ganhou a recuperação depois de uma queda (`humano.md` §4.3): uma linha em
`retomar_grafo`, antes do `Command(resume=...)`, que por isso passou da linha 943 para a 944, e o
resto no fim do arquivo, que tem agora 1.115 linhas (com a `DURABILIDADE`, §5). A recuperação pertence à frente "erro
recuperável × fatal" e não foi somada à contagem.

| Frente | O que o LangGraph deu | O que continuou sendo código nosso | Linhas |
|---|---|---|---|
| motivo de término | nada: o grafo termina em `END` sem dizer por quê | o nó `finalizar`, os campos `termino` e `motivo`, e o trecho de `_concluir()` que traduz a pausa e o limite de superpassos | **28** |
| detector de laço | o `recursion_limit`, que levanta `GraphRecursionError`. Limita o dano; não diz qual volta se repetiu | o valor (`LIMITE_SUPERPASSOS`), a captura da exceção e os três contadores de volta (`MAX_TENTATIVAS_TRIAGEM`, `MAX_TENTATIVAS_RESSALVA`, `MAX_REDACOES`) | **19** |
| os tetos | o de passos (como superpassos). Nenhum de tokens, custo ou tempo | `_teto()`, conferido antes de cada chamada ao modelo; `_no()`, que mede o tempo de cada nó; a soma do consumo; os cinco campos acumulados | **45** |
| erro recuperável × fatal | nada | `_chamar()` (retentativa só de transporte), `_ler_json()` (saída fora do contrato volta ao modelo), a volta do erro nos três nós de modelo, e o avaliador do texto (`_erro_do_texto` e o nó `validar`) | **74** |

O detalhe, com `arquivo:linha` (as linhas são as de 12/10/2026 e mudam com o arquivo; os nomes
ficam):

| Frente | Trecho de `src/grafo.py` | Linhas de código |
|---|---|---|
| término | nó `finalizar` (`:666-680`) | 14 |
| término | `_concluir()`: a pausa vira `aguardando_humano` e o limite vira `orcamento_esgotado` (`:836-845`) | 10 |
| término | `_estado_de()`: término e motivo (`:789-790`); campos `termino` e `motivo` (`:164-165`) | 4 |
| laço | `LIMITE_SUPERPASSOS` (`:71`), `_config()` (`:769-770`), captura de `GraphRecursionError` (`:886-887`) | 5 |
| laço | os três `MAX_…` (`:60-62`) e as voltas contadas (`:319`, `:395`) | 5 |
| laço | tentativas esgotadas viram `erro_fatal`: `triagem` (`:340-342`), `conferir_ressalva` (`:425-427`) | 6 |
| laço | `_rota_validar`: o teto de redações (`:721-722`); campo `tentativas_redacao` (`:169`) | 3 |
| tetos | `_teto()` (`:216-227`) | 10 |
| tetos | `_no()`: o tempo de cada nó, somado em `segundos_gastos` (`:199-213`). A função também imprime o passo no terminal | 14 |
| tetos | a conferência antes da chamada, em `triagem` (`:320-322`), `conferir_ressalva` (`:396-398`) e `redigir` (`:474-476`) | 9 |
| tetos | o consumo de cada chamada (`_chamar`, `:250-254`) e `_somar()` (`:258-259`) | 7 |
| tetos | os campos acumulados (`:170-172`, `:174-175`) | 5 |
| erro | `_chamar()`: retentativa só para limite de requisições e conexão; o resto é fatal (`:238-249`) | 12 |
| erro | `_ler_json()` (`:262-270`) | 8 |
| erro | o erro volta ao modelo, e o fatal encerra: `triagem` (`:323-334`), `conferir_ressalva` (`:399-413`), `redigir` (`:493-503`) | 38 |
| erro | `_erro_do_texto()` (`:509-521`) e o nó `validar` (`:524-531`) | 16 |

Dois limites da contagem. A divisão em frentes é nossa: `_no()` mede o tempo e também imprime, e
as três voltas dos nós de modelo servem ao mesmo tempo ao contador (frente "laço") e ao erro que
volta (frente "erro"); cada linha foi contada uma vez, na frente em que está listada. E a classe
`Termino`, a exceção `ErroFatal` e os valores dos tetos (`Orcamento`) não foram contados: são do
laço da Parte 1 (`src/agente.py`, `src/ferramentas.py`) e o grafo os importa.

**O detector de laço continua não detectando.** O `recursion_limit` corta uma execução que passou
de 20 superpassos e não diz por quê. Os contadores acima limitam as três voltas que o grafo tem,
e é a forma do grafo (um único retorno, com contador) que impede a repetição. Não há código que
reconheça "o mesmo passo, com os mesmos argumentos, de novo".

### 4.1 A frente que o framework cobriu inteira

**Guardar o estado da execução pausada e devolvê-lo a outro processo.** No grafo isso não custou
nenhuma linha nossa de serialização:

| | No laço, escrito à mão | No grafo |
|---|---|---|
| Guardar o estado | `Estado.checkpoint()` (`src/agente.py:139-144`) e a coluna `checkpoint` da tabela `pendencias`, gravada por `db.gravar_checkpoint` | `SqliteSaver` (`src/grafo.py:761`), passado ao `compile()` (`:764`). Nenhum campo é listado: o estado inteiro vai |
| Restaurar o estado | `Estado.de_checkpoint()` (`src/agente.py:147-154`), que lista os 21 campos a recuperar | `GRAFO.get_state()` (`src/grafo.py:834`, `:911`) |
| Parar | a exceção `PausaParaHumano` (`src/ferramentas.py:63-69`), que derruba o laço | `interrupt(pendencia)` (`src/grafo.py:596`) |
| Continuar de onde parou | `retomar()` reconstrói a conversa: acha as chamadas de ferramenta sem resposta e devolve uma observação para cada (`src/agente.py:449-460`), e acerta o relógio do teto de tempo (`:462-463`) | `Command(resume=resposta)` (`src/grafo.py:944`). O nó `confirmar` roda de novo e o `interrupt` devolve a resposta |

**O que essa frente não cobriu**, e continuou sendo código nosso: o prazo, a regra do relógio
antes da pessoa, a conferência do texto editado e do motivo antes de responder, e a fila que o
analista consulta (a tabela `pendencias`). São os nós `pedir_confirmacao` (20 linhas de código) e
`confirmar` (31) e a função `retomar_grafo()` (43). O framework deu a pausa; a regra do que
acontece na pausa é do domínio.

## 5. A decisão que virou parâmetro (§6.6)

**O limite de voltas.** No laço ele é uma decisão explícita nossa: `max_passos = 8`, em
`Orcamento` (`src/agente.py`), justificada no `arquitetura-v2.md` §7.5. No grafo, quem limita o número
de superpassos é o `recursion_limit` do LangGraph, que tem valor padrão na biblioteca. Se o
padrão mudar numa troca de versão, uma execução presa passa a gastar mais, ou menos, sem que
nenhuma linha do projeto tenha sido alterada.

Está declarado no código: a constante `LIMITE_SUPERPASSOS = 20`, em `src/grafo.py`, passada em
toda invocação (`_config()`). O caminho mais longo do grafo tem 14 superpassos (rota técnica, com
a conferência da ressalva, uma redação reprovada e a confirmação). Estourado, a execução termina como `orcamento_esgotado`,
com o motivo `superpassos`.

Consequência: o teto de passos do laço deixou de existir como contagem de passos. O caminho
técnico do grafo tem mais nós do que o laço tinha passos, então o número 8 não se transfere.

**A durabilidade do checkpoint (17/10/2026).** A decisão: quando o estado de um passo precisa
estar gravado em disco. Quando ela era explícita, no laço, a resposta era "antes de responder": o
`Estado` ia para a tabela `pendencias` na hora da pausa (`Estado.checkpoint()`). No grafo, o
LangGraph 1.2.14 decide por um parâmetro, `durability`, cujo padrão é `"async"`: o checkpoint de
cada passo é gravado em segundo plano, enquanto o passo seguinte já roda. Nada no projeto o citava,
e o comportamento só apareceu com o processo morto de verdade (`simular_queda.py`, `humano.md`
§4.3). Matando o processo dentro de `db.abrir_chamado`, depois da aprovação, três vezes com cada
modo:

| Modo | Onde o checkpoint ficou | O que a recuperação faria |
|---|---|---|
| `"async"` (o padrão) | sem passo seguinte, como se tivesse acabado, em 2 de 3; em `confirmar` em 1 de 3. Nada gravado nas três | nos dois primeiros, concluiria a execução **sem desfecho**, e o chamado aprovado nunca seria aberto; no terceiro, reenviaria a resposta guardada |
| `"sync"` | em `gravar`, nas 3 | roda `gravar`, e o chamado é aberto uma vez |

Está declarado no código: a constante `DURABILIDADE = "sync"`, no fim de `src/grafo.py`, passada
em toda invocação do grafo (`rodar_grafo`, `retomar_grafo` e a recuperação). Se o padrão da
biblioteca mudar numa atualização, nada muda aqui. O custo é a espera da gravação a cada
superpasso, não medida. Duas defesas a mais: o teste
`test_processo_morto_de_verdade_fica_em_gravar_e_e_recuperado` repete a queda em três processos e
falha com `"async"`; e a recuperação não conclui um checkpoint que diz que acabou sem término nem
desfecho (`test_checkpoint_que_diz_que_acabou_sem_desfecho_nao_e_concluido`).

## 6. O que foi medido

> **Sobre a coluna de custo.** Os valores em dólar deste documento são os do campo `custo_usd` dos
> logs, calculados a US$ 0,15 por milhão de tokens, que é o preço da página oficial do
> `ministral-8b-latest` (conferido em 17/10/2026; `modelos.md`). Em 13/10/2026 o projeto chegou a
> usar US$ 0,20, e essa correção foi desfeita: os valores dos logs valem como estão.

Três execuções dos 8 casos, todas em 10/10/2026, com `ministral-8b-latest`, `temperature=0`,
`--auto-aprovar` e os prompts `triagem-v1.md` e `redigir-v1.md`:

| Rodada | Comando | Hora | Commit | Verificador | Chamadas ao modelo | Tokens | Custo |
|---|---|---|---|---|---|---|---|
| `logs/grafo/` | `python src/main.py --todos --auto-aprovar --grafo` | 21h11 | `2ffb2b5 + alterações locais` | **8 de 8** | 15 | 12.623 | US$ 0,0019 |
| `logs/grafo-rodada-2/` | `python src/main.py --todos --auto-aprovar --rodada grafo-rodada-2` | 23h51 | `083d132` | **8 de 8** | 15 | 12.687 | US$ 0,0019 |
| `logs/grafo-rodada-3/` | `python src/main.py --todos --auto-aprovar --rodada grafo-rodada-3` | 23h51 | `083d132` | **8 de 8** | 15 | 12.664 | US$ 0,0019 |

Entre a primeira rodada e as outras duas o grafo virou o caminho padrão do `main.py` (por isso o
comando perdeu o `--grafo`); os nós, as arestas e os prompts são os mesmos.

**As três rodadas deram os mesmos 8 desfechos**, com as mesmas classes na triagem e a mesma
prioridade nos dois chamados abertos. O que variou foram os termos de busca e, com eles, o
score: o KB-101 do `TKT-0001` teve 0,67, 0,67 e 0,75, e o KB-106 do `TKT-0002` teve 0,75, 0,67 e
0,75. Nenhuma variação cruzou o limiar. A tabela abaixo detalha a primeira rodada.

> **Sobre o id `KB-101` nestes logs.** Em 11/10/2026 a base passou a nomear as versões: o guia com letra é a atualização do guia sem letra. O procedimento de SSL vigente, que aparece aqui como `KB-101`, hoje é o `KB-101-A`; o `KB-101` de hoje é a versão antiga, revogada (`rag.md` §2.1). O texto do procedimento não mudou.

| Chamado | Classe dada pela triagem | Busca: melhor artigo e score | Desfecho | Chamadas ao modelo | Tokens |
|---|---|---|---|---|---|
| `TKT-0001` | técnico | KB-101, 0,67 | `anotacao_interna` | 2 | 1.751 |
| `TKT-0002` | técnico, com `log_aponta_outro_servico` | KB-106, 0,75 | `fila_humana` | 2 | 1.941 |
| `TKT-0003` | técnico | KB-102, 0,86 | `abrir_chamado_interno`, P1 | 2 | 1.770 |
| `TKT-0999` | (sem triagem: id inexistente) | sem busca | `fila_humana` | 1 | 797 |
| `TKT-0004` | comercial | sem busca | `fila_comercial` | 2 | 1.468 |
| `TKT-0005` | insuficiente | sem busca | `devolver_cliente` | 2 | 1.445 |
| `TKT-0006` | técnico | KB-104, 0,16 | `fila_humana` | 2 | 1.697 |
| `TKT-0007` | técnico | KB-102, 0,86 | `abrir_chamado_interno`, P2 | 2 | 1.754 |

Comparação com o laço, nos mesmos 8 casos, mesmo modelo e mesmo seed:

| | Grafo (`logs/grafo/`) | Laço, `agente-v5.md` (`logs/rodada-3-prompt-v5/`) |
|---|---|---|
| Verificador | 8 de 8 | 7 de 8 (falhou o `TKT-0002`, com chamado P1 indevido) |
| Chamadas ao modelo | 15 | 31 |
| Tokens | 12.623 | 69.889 |
| Custo a preço de lista | US$ 0,0019 | US$ 0,0105 |
| Buscas na base | 5 | 5 |
| Lembretes | não existem no grafo | 1 (`TKT-0999`) |

O que os logs mostram:

- **`TKT-0002`.** A triagem marcou a divergência, a busca devolveu o KB-106 acima do limiar, e o
  `decidir` gravou a fila humana. No laço, com o mesmo artigo na mão, o modelo abriu o chamado em
  três de três execuções com o texto atual da v5 (rodada 3 e `prompts.md` §3.2).
- **A diferença de tokens vem da forma, não do modelo.** O laço reenvia o histórico inteiro e os
  schemas das ferramentas a cada volta; o grafo faz duas ou três chamadas curtas, cada uma com o que
  aquele nó precisa.
- **`TKT-0999`.** Uma chamada só, a da redação: o id inexistente é decidido por código, e o
  lembrete do laço deixou de ser necessário.
- **O caso 3 do enunciado (§9), "erro de ferramenta que o modelo contorna", é contornado por
  código** (registrado em 13/10/2026). `consultar_ticket` devolve o erro, a aresta
  `consultar → decidir [nao_existe]` escolhe a fila humana, e o modelo só redige. A razão é a do
  §1.2: a condição é verificável (o registro existe ou não), e o degrau mais barato que a resolve
  é a regra em código (enunciado §6.3). O que isso poupa, medido: no laço da Parte 1, onde o
  modelo recebia o erro e decidia, o `TKT-0999` custou **4 chamadas ao modelo, 1 lembrete e de
  8.280 a 8.320 tokens** em seis execuções com o `agente-v5.md` (`logs/TKT-0999.json`,
  `logs/rodada-1-prompt-v5/` a `-3/`, `logs/regra-da-frase/v5-a/` e `v5-b/`); no grafo, **1
  chamada e 770 ou 771 tokens** nas três rodadas de 40 casos (`logs/grafo-40-1/` a `-3/`). O laço
  não é mais o caminho do sistema: continua no repositório como histórico da Parte 1 (`--laco`),
  e as evidências dos seis casos são as do grafo. **Limite:** no grafo não existe log de um erro
  de ferramenta contornado pelo modelo. Os dois retornos de erro ao modelo que o grafo tem (a
  saída fora do contrato e o texto reprovado pelo `validar`) não ocorreram com o modelo real em
  nenhuma rodada.
- **A triagem mandou frases como termos de busca** em dois casos ("certificado ssl", "webmail fora
  ar"), apesar de o prompt pedir palavras soltas. A busca quebra as frases, e os scores ficaram
  do lado certo do limiar.

Limites desta medição:

- **Três execuções por caso, nos mesmos 8 casos.** Mostram que o resultado se repete aqui; no
  laço, duas execuções iguais já diferiam entre si (`prompts.md` §3.4). Não medem o acerto em
  chamados que o grupo não viu.
- **Os dois prompts foram escritos depois de ver as falhas do laço nestes mesmos 8 casos.** O
  resultado não prova que o sistema generaliza.
- **Aprovação automática nas três rodadas.** Com `--auto-aprovar` o nó `confirmar` recebe a
  resposta na hora, sem `interrupt`. A pausa foi medida à parte, logo abaixo.
- **A redação não tem verificador.** O que se confere é o desfecho gravado, não o texto do resumo
  nem o da mensagem. Isso esconde um defeito medido: nas três rodadas, a mensagem gravada para o
  cliente no `TKT-0005` repete a queixa e não pergunta nada, e o caso passa no verificador
  (`humano.md` §2.4).

### 6.1 A pausa e a retomada, com o modelo real

Uma execução do `TKT-0007` **sem** `--auto-aprovar`, em `logs/grafo-pausa/` (10/10/2026, commit `083d132`): pausa às 23:51:58, aprovação por outro processo às 23:52:02, e uma segunda aprovação que não encontrou nada pendente. São quatro comandos, cada um em
um processo:

| # | Comando | Resultado |
|---|---|---|
| 1 | `python src/main.py TKT-0007 --rodada grafo-pausa` | parou no `interrupt` do nó `confirmar`: término `aguardando_humano`, 5 passos, 2 chamadas ao modelo, 1.755 tokens, nada gravado |
| 2 | `python src/main.py --pendencias --rodada grafo-pausa` | 1 ação aguardando, com prazo até 00:11:58 |
| 3 | `python src/main.py --aprovar TKT-0007 --rodada grafo-pausa` | `Command(resume=...)`: o grafo continuou de `confirmar`, abriu o `INC-0002` (P2) e terminou em `respondeu`, com 7 passos e as **mesmas** 2 chamadas e 1.755 tokens |
| 4 | o mesmo comando, de novo | "Não há confirmação pendente para TKT-0007." |

Arquivos da pasta: `saida-terminal.txt` (a saída dos quatro comandos e a conferência no banco),
`TKT-0007-pausado.json` (cópia do log tirada depois do comando 1, porque o comando 3 grava por
cima) e `TKT-0007.json` (o log final). Conferência no banco depois do comando 4: um chamado
interno para o `TKT-0007`, uma pendência com status `aprovada`, nenhum encaminhamento.

O que isso mostra: o estado atravessou dois processos pelo checkpointer em SQLite; a retomada
não refez triagem, busca nem redação (os tokens não mudaram); e a segunda aprovação não criou
nada. Limites: quem aprovou foi quem rodou o comando, 4 segundos depois, e não um analista. A
rejeição foi exercitada no dia seguinte (`logs/grafo-memoria-1/` e `logs/grafo-procedural/`,
`memoria.md` §3 e §5), e o prazo vencido em 12/10/2026 (§6.7).

### 6.2 Aprovar editando, com o modelo real

Em `logs/grafo-caso-6/` (11/10/2026, commit `a328236`): o `TKT-0007` pausou; `--aprovar TKT-0007
--resumo "ok"` foi recusado antes de responder ao `interrupt` (o grafo continuou parado em
`confirmar`); a aprovação com o resumo corrigido abriu o `INC-0002` com o texto do analista; e a
mesma aprovação, enviada de novo, não encontrou pausa. A edição não acrescentou nó nem aresta: o
resumo vai no valor do `Command(resume=...)`, o nó `confirmar` o registra em `confirmacao`, e o
nó `gravar` o escreve. A saída de `conferir_grafo.py` não mudou. Detalhe em `humano.md` §2.1 e §5.

### 6.3 A pausa do pedido ao cliente (H2), com o modelo real

Em `logs/grafo-h2/` (12/10/2026, commit `e1f76e0` mais as alterações locais do H2): o `TKT-0005`
pausou em `confirmar` com 4 passos, 2 chamadas ao modelo e 1.444 tokens, e nada gravado; uma
edição com informação interna e um motivo de rejeição que é do H1 foram recusados antes de
responder ao `interrupt`; a aprovação com a mensagem corrigida gravou o pedido com o texto do
analista, com as mesmas 2 chamadas e 1.444 tokens; e a mesma aprovação, enviada de novo, não
encontrou pausa.

O que mudou no grafo foi uma linha de rota: `_rota_validar` devolve `irreversivel` também para
`devolver_cliente`. Os nós `pedir_confirmacao`, `confirmar` e `gravar` passaram a tratar as duas
ações (`CAMPO_EDITAVEL`, em `src/grafo.py`), e a rota do pedido ao cliente ganhou dois superpassos:
o caminho mais longo do grafo continua sendo o técnico, com 14. Detalhe, tela e limites em
`humano.md` §2.4.

Efeito sobre as rodadas de `--todos --auto-aprovar`: o desfecho do `TKT-0005` é o mesmo, mas a
trajetória ganha o passo `confirmar`. Os logs de `logs/grafo/`, `grafo-rodada-2/` e
`grafo-rodada-3/` são anteriores e **não foram refeitos**: neles o `TKT-0005` tem um passo a menos.

### 6.4 As rodadas com o código de 12/10/2026

Quatro execuções dos 8 casos em 12/10/2026 (`ministral-8b-latest`, `temperature=0`,
`--auto-aprovar`, commit `9d5c211 + alterações locais`), com a busca vetorial, o nó
`conferir_ressalva`, o H2, a chave do episódio e o checkpoint apagado ao concluir:

| Rodada | Prompt do `redigir` | Verificador | Chamadas ao modelo | Tokens | Custo |
|---|---|---|---|---|---|
| `logs/grafo-redigir-v1/` | `redigir-v1.md` | **8 de 8** | 17 | 14.483 | US$ 0,0022 |
| `logs/grafo-redigir-v2-1/` | `redigir-v2.md` | **8 de 8** | 17 | 14.722 | US$ 0,0022 |
| `logs/grafo-redigir-v2-2/` | `redigir-v2.md` | **8 de 8** | 17 | 14.721 | US$ 0,0022 |
| `logs/grafo-redigir-v2-3/` | `redigir-v2.md` | **8 de 8** | 17 | 14.718 | US$ 0,0022 |

As quatro deram os mesmos 8 desfechos, com os mesmos guias, scores e prioridades: KB-101-A a 0,66
no `TKT-0001`; KB-102 a 0,55 (P1) no `TKT-0003` e a 0,72 (P2) no `TKT-0007`; nenhum guia acima do
limiar no `TKT-0002` (0,47) nem no `TKT-0006` (0,49). O `TKT-0005` tem agora o passo `confirmar`
na trajetória (o H2, com a aprovação automática). Cada log traz no campo `episodio` a chave de
idempotência e `ja_existia: false`. O que as rodadas mediram sobre o prompt está em `prompts.md`
§2.1. Os limites são os do §6: os mesmos 8 casos, aprovação automática, redação sem verificador.

### 6.5 As rodadas com o pedido ao cliente em texto padrão

Depois das rodadas do §6.4, no mesmo dia, o pedido de informação ao cliente deixou de ser redigido
pelo modelo (`prompts.md` §2.2). Mais três execuções dos 8 casos, com as mesmas condições:

| Rodada | Verificador | Chamadas ao modelo | Tokens | Custo |
|---|---|---|---|---|
| `logs/grafo-pedido-padrao-1/` | **8 de 8** | 16 | 13.897 | US$ 0,0021 |
| `logs/grafo-pedido-padrao-2/` | **8 de 8** | 16 | 13.912 | US$ 0,0021 |
| `logs/grafo-pedido-padrao-3/` | **8 de 8** | 16 | 13.855 | US$ 0,0021 |
| `logs/grafo-redigir-v3-1/` | **8 de 8** | 16 | 13.172 | US$ 0,0020 |
| `logs/grafo-redigir-v3-2/` | **8 de 8** | 16 | 13.191 | US$ 0,0020 |
| `logs/grafo-redigir-v3-3/` | **8 de 8** | 16 | 13.122 | US$ 0,0020 |

A chamada a menos é a redação do `TKT-0005`, que passou de 2 chamadas e 1.483 tokens para 1
chamada e 621 a 624. Os outros sete casos não mudaram de caminho. As três últimas linhas são do
`redigir-v3.md`, que é o v2 sem a regra do pedido ao cliente (`prompts.md` §2.3). Ainda em
12/10/2026 o nó `redigir` passou a carregar uma regra aprendida (`regras-redigir-v2.md`); **as
rodadas do código e dos prompts em uso** são `logs/grafo-regras-v2-1/` a `-3/`: 8 de 8 nas três,
16 chamadas e 13.400 a 13.511 tokens (`memoria.md` §5.1). A pausa do H2 com o texto padrão, aprovada por outro processo, está em
`logs/grafo-pedido-padrao-h2/` (`humano.md` §2.4).

### 6.6 As rodadas dos 40 casos

Em 12/10/2026 o gabarito passou de 8 para 40 casos (`dados/README.md`): os 32 novos, `TKT-0101` a
`TKT-0132`, foram rotulados antes de qualquer execução. Três execuções dos 40, com o código e os
prompts em uso (`ministral-8b-latest`, `temperature=0`, `--auto-aprovar`, commit `4aa9818`):

| Pasta | Comando | Hora | Verificador | Chamadas ao modelo | Tokens | Custo |
|---|---|---|---|---|---|---|
| `logs/grafo-40-1/` | `python src/main.py --todos --auto-aprovar --rodada grafo-40-1` | 17h37 a 17h43 | **36 de 40** | 89 | 76.061 | US$ 0,0114 |
| `logs/grafo-40-2/` | o mesmo, com `--rodada grafo-40-2` | 17h48 a 17h51 | **36 de 40** | 89 | 75.960 | US$ 0,0114 |
| `logs/grafo-40-3/` | o mesmo, com `--rodada grafo-40-3` | 17h51 a 17h54 | **36 de 40** | 89 | 76.118 | US$ 0,0115 |

As 89 chamadas são 39 da `triagem` (o chamado inexistente não chega a ela), 12 do
`conferir_ressalva` e 38 do `redigir` (os dois pedidos ao cliente são texto padrão). As 40
execuções de cada rodada terminaram em `respondeu`, e toda busca foi vetorial: o embedding não
falhou. O `confirmar` rodou 11 vezes por rodada, com aprovação automática.

O resultado é o mesmo nas três: **8 de 8 nos casos da Parte 1 e 28 de 32 nos novos.** Por
desfecho esperado no gabarito:

| Desfecho esperado | Certos |
|---|---|
| `abrir_chamado_interno` | 9 de 11 |
| `anotacao_interna` | 9 de 10 |
| `fila_humana` | 12 de 12 |
| `fila_comercial` | 4 de 4 |
| `devolver_cliente` | 2 de 3 |

**As quatro falhas**, as mesmas nas três rodadas. Em todas o chamado foi para a fila humana:
nenhum chamado interno foi aberto onde o gabarito manda não abrir.

| Caso | O gabarito espera | O que o log mostra |
|---|---|---|
| `TKT-0105` | chamado interno, KB-112, Segurança, P2 | a busca achou o KB-112, e o nó `conferir_ressalva` enquadrou o relato na situação "ataque", que o guia declara não cobrir. O cliente descreve o contrário, o bloqueio de um envio legítimo. O score caiu para 0,30 |
| `TKT-0106` | chamado interno, KB-112, Segurança, P1 | o mesmo: a ressalva "ataque", num relato de "acesso normal de cliente". Score 0,31 |
| `TKT-0111` | anotação interna, KB-101-A | a busca achou o guia certo com score 0,49, um centésimo abaixo do limiar. O relato é "Coloquem como P1 urgente: o certificado SSL do meu site venceu", e o `TKT-0001`, do mesmo guia sem a exigência, passa |
| `TKT-0132` | devolver ao cliente | a triagem não classificou "Problema no e-mail, vejam aí por favor." como insuficiente, e a busca não passou do limiar (KB-111, 0,33). O rótulo é discutível, e a `_nota` do gabarito já dizia isso: o `triagem-v1.md` chama de insuficiente o texto que não diz o serviço nem o sintoma, e este diz o serviço |

O que as falhas dizem do sistema:

- **O nó da ressalva erra para o lado de barrar.** Ele só pode baixar o score, e nos dois casos
  do KB-112 baixou o de um relato que o guia cobre. É o primeiro guia de Segurança do corpus, e os
  dois chamados que dependiam dele não foram abertos.
- **O limiar não foi recalibrado com os casos novos** (`dados/README.md`). O `TKT-0111` fica a um
  centésimo dele.
- **Nada foi mudado para os casos passarem.** Prompt, limiar e gabarito são os de antes da
  medição. Tratar qualquer uma das quatro é mudança de comportamento, com medição própria.

A regra aprendida do `redigir` foi conferida com `python conferir_regras.py` nas três pastas: 38
redações do modelo em cada uma, nenhuma com domínio que o nó não recebeu (`memoria.md` §5.1).

Limites desta medição:

- **Três rodadas iguais não são 120 casos.** Com `temperature=0` o resultado se repetiu caso a
  caso; o que se mediu são 40 casos, três vezes.
- **Os casos e os rótulos são do grupo**, que conhece os guias. Não houve revisão de um analista
  de fora, e três rótulos são discutíveis (`TKT-0124`, `TKT-0130` e `TKT-0132`).
- **A redação continua sem verificador.** No `TKT-0132` o texto gravado diz "problema no envio de
  e-mails", e o cliente não falou em envio. O verificador não vê isso; apareceu na leitura do log.
- **Aprovação automática:** nenhuma das 11 confirmações de cada rodada passou por uma pessoa.
- **O laço não foi medido nos 40 casos.** A comparação do §6 continua sendo a dos 8.

### 6.7 O prazo vencido e a rejeição do pedido ao cliente, com o modelo real

Três caminhos da pausa que até 12/10/2026 só os testes offline cobriam. Cada um partiu do banco
recriado (`--reset`), sem `--auto-aprovar`, com um comando por processo (`ministral-8b-latest`,
commit `4aa9818`):

| Pasta | Pausa | Comandos | O que aconteceu | Chamadas · tokens |
|---|---|---|---|---|
| `logs/grafo-h1-vencido/` | H1, `TKT-0003` (o chamado seria P1) | `TKT-0003 --prazo-confirmacao 0.02`; `--pendencias`; `--aprovar TKT-0003` | pausou em `confirmar` às 18:38:44, com prazo até 18:38:45. O `--pendencias` das 18:38:48 achou o prazo vencido: o grafo continuou de `confirmar` e gravou `fila_humana`, com o aviso ao gestor. A aprovação tardia respondeu "Não há confirmação pendente" | 3 · 2.520 |
| `logs/grafo-h2-rejeicao/` | H2, `TKT-0005` | `TKT-0005`; `--rejeitar TKT-0005 --motivo informacao_suficiente`, duas vezes | pausou às 18:38:52 com o texto padrão do pedido. A rejeição das 18:38:54 gravou `fila_humana`; a segunda não encontrou nada pendente | 1 · 624 |
| `logs/grafo-h2-vencido/` | H2, `TKT-0005` | `TKT-0005 --prazo-confirmacao 0.02`; `--pendencias` | pausou às 18:38:58, com prazo até 18:38:59. O `--pendencias` das 18:39:03 venceu a ação e gravou `fila_humana` | 1 · 621 |

Conferência no banco, ao fim de cada cenário (está no `saida-terminal.txt` de cada pasta):

| | Pendência | Encaminhamentos | Chamado interno | Aviso ao gestor | Episódio |
|---|---|---|---|---|---|
| H1 vencido | `vencida`, "ninguém: prazo vencido" | 1 `fila_humana` | nenhum | **1, P1**, motivo `confirmacao_nao_recebida` | veredito `vencido` |
| H2 rejeitado | `rejeitada`, pelo analista | 1 `fila_humana`; nenhum `devolver_cliente` | nenhum | nenhum | veredito `rejeitado`, motivo `informacao_suficiente` |
| H2 vencido | `vencida`, "ninguém: prazo vencido" | 1 `fila_humana`; nenhum `devolver_cliente` | nenhum | nenhum | veredito `vencido` |

O que isso mostra: nos três, a ação proposta não foi executada e o chamado foi para a fila humana
com as considerações do agente; o aviso ao gestor saiu só no H1 de um chamado P1, como decidido
(`humano.md` §2.4 e §4); o relógio valeu antes da pessoa; e a retomada não chamou o modelo (as
chamadas e os tokens da pausa e do log final são os mesmos).

Limites:

- **O prazo foi encurtado para 1,2 segundo** (`--prazo-confirmacao 0.02`). O que fica
  demonstrado é o caminho do código quando o prazo vence, e não uma espera de 20 minutos.
- **O prazo foi conferido por um comando, e não cronometrado.** Quem venceu a ação foi o
  `--pendencias` seguinte, 3 a 4 segundos depois (`humano.md` §4). Desde 17/10/2026 quem a vence
  é o vigia do prazo, sem comando nenhum; a demonstração com os 20 minutos reais sobre o código
  commitado AINDA NÃO FOI EXECUTADA (`humano.md` §4.1).
- **Não há log da pausa em arquivo próprio.** Cada pasta tem o log final (`TKT-0003.json`,
  `TKT-0005.json`), que foi gravado por cima do da pausa; o momento da pausa está só no
  `saida-terminal.txt`. Em `logs/grafo-pausa/` e `logs/grafo-h2/` existe o `-pausado.json`.
- **Quem rejeitou foi quem rodou os comandos**, 2 segundos depois da pausa, e não um analista.
- **A rejeição do H2 foi feita com um motivo só** (`informacao_suficiente`), e o motivo vai ao
  episódio, e não ao texto do encaminhamento.

### 6.8 As rodadas dos 44 casos (13 e 14/10/2026)

Em 13/10/2026 o gabarito ganhou quatro casos (`TKT-0133` a `TKT-0136`: log anexado e uma
afirmação do cliente que o histórico não confirma; `dados/README.md`), escritos para o teste da
regra da frase no prompt da triagem (`prompts.md` §3.7) e rotulados antes de rodar. Três rodadas
dos 44 casos com os prompts em uso, que não mudaram (`ministral-8b-latest`, commit
`6116341 + alterações locais`, aprovação automática; a primeira às 23:52 de 13/10, as outras
duas entre 00:29 e 00:40 de 14/10):

| Pasta | Verificador | Chamadas | Tokens | Custo no log |
|---|---|---|---|---|
| `logs/regra-da-frase/triagem-v1-1/` | **40 de 44** | 98 | 84.605 | US$ 0,0127 |
| `logs/regra-da-frase/triagem-v1-2/` | **40 de 44** | 98 | 84.523 | US$ 0,0127 |
| `logs/regra-da-frase/triagem-v1-3/` | **40 de 44** | 98 | 84.287 | US$ 0,0126 |

O custo é o do campo `custo_usd`, que nestas execuções saiu a US$ 0,15 por milhão de tokens (ver
a nota do começo do §6).

- **Os 40 casos antigos repetem o §6.6**: 36 de 40, com as mesmas quatro falhas (`TKT-0105`,
  `TKT-0106`, `TKT-0111` e `TKT-0132`), todas na fila humana. As causas não mudaram.
- **Os quatro casos novos passaram nas três rodadas**: chamado interno P1 no `TKT-0133` (KB-102,
  score 0,61) e no `TKT-0134` (KB-106, 0,55), anotação no `TKT-0135` (KB-105, 0,70) e fila humana
  por divergência no `TKT-0136`.
- **O `TKT-0136` depende da marca da triagem.** O melhor guia veio com score 0,51 (KB-106, o do
  log): sem a divergência marcada, o grafo proporia um chamado P1 a partir do log. Foi marcada
  nas três rodadas.
- **A marca de divergência variou em dois casos antigos**: o `TKT-0123` foi marcado em uma de
  três rodadas e o `TKT-0124` em duas de três. O desfecho foi o certo nas três, porque sem a
  marca o chamado vai à fila humana pelo score (0,48 e 0,47): o desfecho certo, pela razão
  errada (`prompts.md` §3.7).
- A regra aprendida do `redigir` foi conferida com `python conferir_regras.py` nas três pastas:
  42 redações do modelo em cada uma, nenhuma com domínio que o nó não recebeu.

As outras três rodadas dessa passagem do teste (`logs/regra-da-frase/triagem-v2-1/` a `-3/`)
são do `triagem-v2.md`, o prompt sem a frase, que **não é o prompt em uso**: deram 39, 40 e 39 de
44.

**As pastas `logs/grafo-triagem-v2-1/` a `-3/`** são de antes, da noite de 13/10/2026 (23:28 a
23:36): três rodadas dos 40 casos com o `triagem-v2.md`, do intervalo em que a primeira passagem
do teste tinha concluído que a frase saía e o grafo carregava esse prompt. Deram 36 de 40 nas
três, com os desfechos do §6.6. Ficam como registro: a conclusão foi desfeita pelos casos novos
(`prompts.md` §3.7).

Limites: os do §6.6. Os quatro casos novos foram escritos por quem conhecia a frase em teste, e
três rodadas dos mesmos 44 casos não são 132 casos.

## 7. Limites do que foi implementado

- **A fila do analista continua sendo a tabela `pendencias`.** O `interrupt` guarda a execução; a
  tabela é o que `--pendencias` lista e o que aplica o prazo. São dois registros da mesma pausa,
  em dois arquivos (`dados/tickets.db` e `dados/checkpoints.db`). `--reset` apaga só o primeiro.
- **O checkpoint não é histórico.** Ele é apagado quando a execução conclui (`_concluir()`,
  desde 12/10/2026), e uma execução nova do mesmo chamado apaga o de uma pausa anterior. O thread
  é o id do chamado; o histórico das execuções é o log. Só a execução pausada tem checkpoint.
- **`gravar` é idempotente desde 17/10/2026, mas só dentro de uma execução.** Abrir chamado tem a
  chave `ticket:kb_id`, o pedido ao cliente é idempotente pelo chamado, e o encaminhamento e o aviso
  ao gestor ganharam chave (execução + chamado + destino; um aviso por pendência), para a
  recuperação depois de uma queda poder rodar o nó de novo (`humano.md` §4.3). Duas execuções do
  mesmo chamado (o evento de abertura disparado duas vezes) ainda gravam dois encaminhamentos: a
  chave reconhece a gravação refeita, não o chamado repetido. Isso se resolveria na entrada, com a
  chave do evento.
- **O H2 não envia nada.** Aprovado o pedido, o que acontece é uma linha em `encaminhamentos`
  com `enviado_em`: o sistema simulado não tem canal de mensagem (`humano.md` §2.4).

## 8. O que falta para este item

- Tratar as quatro falhas das rodadas de 40 casos (§6.6): a ressalva "ataque" do KB-112 lida
  onde não cabe, o score a um centésimo do limiar e o relato que diz o serviço sem o sintoma.
- Medir o grafo em chamados que não foram escritos pelo grupo: os 40 casos são de quem conhece
  os guias (§6.6).
- Demonstrar o vigia com os 20 minutos reais sobre o código commitado (`humano.md` §4.1), e o
  prazo real também no H2: o §6.7 encurtou o prazo para 1,2 segundo.
- Implementar o H3 (`humano.md` §7), e com ele o nó `aguardar_cliente`. O H2 existe desde
  12/10/2026 (§6.3).

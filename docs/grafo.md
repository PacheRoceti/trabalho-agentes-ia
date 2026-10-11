# O grafo (Parte 2, itens 6 e 7)

> **Estado deste documento: 10/10/2026.** O grafo existe: é o `StateGraph` de
> [`src/grafo.py`](../src/grafo.py), compilado uma vez (objeto `GRAFO`), com o LangGraph fixado no
> `requirements.txt` (`langgraph==1.2.14`, `langgraph-checkpoint-sqlite==3.1.1`). O desenho abaixo
> foi conferido contra a saída de `python conferir_grafo.py`, que está colada em
> [`arquitetura.md`](arquitetura.md) §9.
>
> **O que foi medido:** três execuções dos 8 casos com o modelo real, 8 de 8 no verificador nas
> três, e uma pausa real no H1, retomada por outro processo (§6). O que é do código está provado por 21 testes offline
> (`tests/test_grafo.py`), com modelo roteirizado.
>
> **O grafo é o caminho padrão do `main.py`** desde 10/10/2026, e grava em `logs/grafo/`. O laço
> da Parte 1 (`src/agente.py`) roda com `--laco` e grava em `logs/`, para os dois poderem ser
> comparados nos mesmos 8 casos.

## 1. O desenho

O ponto de partida é a medição do `arquitetura.md` §8: o sistema é um roteador, e o que o modelo
decide é a rota e a redação, não a sequência de passos. O grafo tira do modelo a escolha da
próxima ferramenta e deixa com ele duas chamadas: a triagem e a redação.

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
[buscar]             código   busca os procedimentos com os termos da triagem; devolve o score
  │
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
  └─ "irreversivel"     abrir_chamado_interno
        ▼
[pedir_confirmacao]  código   monta a ação, marca pedido_em e vence_em (20 min), grava em `pendencias`
  │
  ▼
[confirmar]          ⏸ H1     interrupt: espera o analista de suporte
  │                           decide: o relógio, depois a pessoa → aprovada · rejeitada · vencida
  ▼
[gravar]             código   aprovada → abre o chamado interno (chave ticket:kb_id)
  │                           rejeitada ou vencida → fila_humana com as considerações do agente
  │                           vencida, e o chamado seria P1 → aviso ao gestor
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
- **Saiu o nó `aguardar_cliente`, e o `confirmar` atende só o H1.** A confirmação do pedido ao
  cliente (H2) e a espera pela resposta dele (H3) não foram implementadas (`humano.md` §7).
- **A triagem escolhe os termos de busca.** A busca é por palavra, e o relato inteiro dilui o
  score. Era uma das perguntas em aberto.

### 1.1 Os nós

| Nó | O que faz | Chama o modelo? | De onde veio, no laço |
|---|---|---|---|
| `entrada` | fixa o texto do chamado: o digitado ou o registrado para o id | não | `_entrada`, em `src/agente.py` (a mesma função) |
| `consultar` | lê chamado, plano, log anexado e histórico | não | ferramenta `consultar_ticket`. Deixou de ser escolha do modelo: toda execução consulta |
| `triagem` | classifica o assunto, diz se o log aponta outro serviço e escolhe os termos de busca | **sim** | passos 2, 3 e 4 do `agente-v5.md` |
| `buscar` | recupera os procedimentos, com score | não | ferramenta `buscar_base_conhecimento`. O modelo ainda escolhe os termos, mas não escolhe se busca |
| `decidir` | escolhe o desfecho | não | o passo 4 do `agente-v5.md` (que era do modelo) e os portões de `src/ferramentas.py` |
| `redigir` | redige o resumo do chamado ou a mensagem do encaminhamento | **sim** | argumento `resumo` ou `mensagem` das ferramentas de escrita |
| `validar` | confere o texto redigido | não | validações de `src/ferramentas.py` |
| `pedir_confirmacao` | monta a ação como o analista vai vê-la, marca o prazo e grava em `pendencias` | não | parte de `abrir_chamado_interno` |
| `confirmar` | pausa com `interrupt` e lê a resposta | não | `Estado.confirmar` e `retomar`, em `src/agente.py` |
| `gravar` | escreve o desfecho no banco | não | `abrir_chamado`, `registrar_encaminhamento` (`src/db.py`) e `encaminhar_pendencia` (`src/ferramentas.py`) |
| `finalizar` | fixa término e motivo e valida a saída | não | bloco `finally` do laço e `montar_saida` |

### 1.2 As arestas condicionais, e quem decide cada uma (§6.3)

São quatro, todas com o mapa de destinos escrito em `_construir()`.

| Aresta | Função | Destinos | Degrau que decide | Por que esse degrau basta |
|---|---|---|---|---|
| depois de `consultar` | `_rota_consultar` | `triagem`, `decidir` | regra em código | é um campo vazio: id que não existe não tem o que classificar |
| depois de `triagem` | `_rota_triagem` | `buscar`, `decidir`, `finalizar` | **modelo**, com saída `Literal["tecnico", "comercial", "insuficiente", "fora_da_alcada"]`; o código só lê o valor | exige julgamento sobre texto livre. O schema garante uma classe válida, não a classe certa |
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
| `orcamento_esgotado` | teto de tokens, custo ou tempo, conferido antes de cada chamada ao modelo (`triagem`, `redigir`); ou o limite de superpassos |
| `erro_fatal` | a API falhou; a triagem veio fora do contrato 2 vezes; o texto redigido foi recusado 2 vezes; a saída não coube no schema |
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
| `candidatos` | `list[dict]` | `buscar` | `decidir`, `redigir`, `gravar`, a saída | nenhum |
| `desfecho_proposto` | `dict` (`acao`, `kb_id`, `motivo`) | `decidir` | `redigir`, `validar`, `_rota_validar`, `pedir_confirmacao`, `gravar` | nenhum. **Novo** |
| `texto_redigido` | `str` ou `None` | `redigir` | `validar`, `pedir_confirmacao`, `gravar` | nenhum |
| `erro_validacao` | `dict` ou `None` | `validar` | `_rota_validar`, `redigir`, `finalizar` | nenhum |
| `pendencia`, `pendencia_id` | `dict`, inteiro | `pedir_confirmacao` | `confirmar`, `gravar` | nenhum |
| `confirmacao` | `dict` | `confirmar` | `gravar`, o log | nenhum |
| `desfecho` | `dict` | `gravar` | `finalizar` | nenhum |
| `termino`, `motivo` | `str` | `triagem` ou `redigir` (teto, erro) e `finalizar` | as arestas, quem chama o grafo | nenhum |
| `saida` | `dict` | `finalizar` | quem chama o grafo | nenhum |
| `passos` | `list[dict]` | os nós que registram um passo | o log e a saída | `operator.add` (concatena) |
| `tentativas_redacao` | `int` | `redigir` | `_rota_validar` | `operator.add` (soma) |
| `n_chamadas_modelo`, `tokens_entrada`, `tokens_saida`, `custo_usd` | número | `triagem`, `redigir` | os tetos, o log | `operator.add` (soma) |
| `segundos_gastos` | `float` | todos os nós | o teto de tempo | `operator.add` (soma) |

`termino` e `motivo` têm mais de um escritor (`triagem`, `redigir`, `finalizar`), mas nunca na
mesma volta: quando um nó de modelo os escreve, a aresta seguinte leva direto a `finalizar`.

### 3.2 Os reducers (§7.2)

- `passos`: concatenação. Cada nó acrescenta o seu registro; sem reducer, o último nó apagaria a
  trajetória.
- tokens, custo, chamadas ao modelo e `segundos_gastos`: soma. Dois nós chamam o modelo, e os
  tetos precisam do total.
- `tentativas_redacao`: soma. O nó `redigir` devolve 1 a cada passagem.

Consequência prática dos reducers: uma execução nova no mesmo thread somaria com a anterior. Por
isso `rodar_grafo()` apaga o thread do chamado antes de começar.

**A demonstração do que acontece sem reducer está por fazer**, e depende de uma decisão: o
enunciado pede a demonstração num grafo com nós paralelos, e este grafo não tem nenhum.

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

Levantamento feito ao escrever `src/grafo.py`. **A contagem de linhas ainda não foi feita.**

| Frente | O que o LangGraph deu | O que continuou sendo código nosso, em `src/grafo.py` |
|---|---|---|
| motivo de término | nada: o grafo termina em `END` sem dizer por quê | o nó `finalizar`, os campos `termino` e `motivo`, e `_concluir()`, que traduz a pausa e o limite de superpassos |
| detector de laço | o `recursion_limit`, que levanta `GraphRecursionError` | o valor (`LIMITE_SUPERPASSOS`), a captura da exceção e os dois contadores de volta (`MAX_TENTATIVAS_TRIAGEM`, `MAX_REDACOES`) |
| os tetos | nenhum de tokens, custo ou tempo | `_teto()`, conferido antes de cada chamada ao modelo, e o campo `segundos_gastos`, somado nó a nó por `_no()` |
| erro recuperável × fatal | nada | `_chamar()` (retentativa só de transporte), `_ler_json()` (saída fora do contrato volta ao modelo) e o tratamento de `ErroFatal` nos dois nós de modelo |

O que o framework deu e o laço tinha à mão: a pausa (`interrupt`), o estado guardado entre
processos (checkpointer em SQLite) e a retomada (`Command(resume=...)`). No laço eram a exceção
`PausaParaHumano`, uma coluna de JSON na tabela `pendencias` e a função `retomar()`.

## 5. A decisão que virou parâmetro (§6.6)

**O limite de voltas.** No laço ele é uma decisão explícita nossa: `max_passos = 8`, em
`Orcamento` (`src/agente.py`), justificada no `arquitetura-v2.md` §7.5. No grafo, quem limita o número
de superpassos é o `recursion_limit` do LangGraph, que tem valor padrão na biblioteca. Se o
padrão mudar numa troca de versão, uma execução presa passa a gastar mais, ou menos, sem que
nenhuma linha do projeto tenha sido alterada.

Está declarado no código: a constante `LIMITE_SUPERPASSOS = 20`, em `src/grafo.py`, passada em
toda invocação (`_config()`). O caminho mais longo do grafo tem 13 superpassos (rota técnica, com
uma redação reprovada e a confirmação). Estourado, a execução termina como `orcamento_esgotado`,
com o motivo `superpassos`.

Consequência: o teto de passos do laço deixou de existir como contagem de passos. O caminho
técnico do grafo tem mais nós do que o laço tinha passos, então o número 8 não se transfere.

## 6. O que foi medido

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
  schemas das ferramentas a cada volta; o grafo faz duas chamadas curtas, cada uma com o que
  aquele nó precisa.
- **`TKT-0999`.** Uma chamada só, a da redação: o id inexistente é decidido por código, e o
  lembrete do laço deixou de ser necessário.
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
  nem o da mensagem.

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
nada. Limites: quem aprovou foi quem rodou o comando, 4 segundos depois, e não um analista; a
rejeição e o prazo vencido não foram exercitados com o modelo real.

## 7. Limites do que foi implementado

- **A fila do analista continua sendo a tabela `pendencias`.** O `interrupt` guarda a execução; a
  tabela é o que `--pendencias` lista e o que aplica o prazo. São dois registros da mesma pausa,
  em dois arquivos (`dados/tickets.db` e `dados/checkpoints.db`). `--reset` apaga só o primeiro.
- **Uma execução nova apaga o checkpoint anterior do mesmo chamado.** O thread é o id do chamado,
  e não há histórico de execuções no checkpointer; o histórico é o log.
- **`gravar` não é idempotente para os encaminhamentos.** Abrir chamado tem a chave
  `ticket:kb_id`. Um encaminhamento gravado duas vezes criaria duas linhas; o que impede isso
  hoje é o nó rodar uma vez, e não uma chave.

## 8. O que falta para este item

- Medir o grafo em chamados fora dos 8 casos: as três rodadas são dos mesmos casos (§6).
- Exercitar a rejeição e o prazo vencido com o modelo real, e com log (§6.1).
- Contar as linhas das quatro frentes do §4.
- Fazer a demonstração do campo sem reducer (§3.2).
- Implementar H2 e H3 (`humano.md` §7), e com eles o nó `aguardar_cliente`.

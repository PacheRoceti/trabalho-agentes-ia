# Arquitetura do agente (Parte 2, item 3)

> **O que este documento descreve.** O sistema **como ele está hoje**, no commit `861a948`
> (10/10/2026): o laço da Parte 1, com o prompt `agente-v5.md`, a entrada em texto digitado e a
> saída validada (`src/saida.py`). O grafo
> em LangGraph, o índice vetorial, a memória e o checkpointer **ainda não existem no código**
> (a pausa pela confirmação do analista tem uma retomada própria, sobre o SQLite: §7); onde
> o enunciado pede um deles, o documento diz o que há no lugar. O que falta entrar aqui está
> listado no §9. O desenho proposto para o grafo está em [`grafo.md`](grafo.md), a recuperação em
> [`rag.md`](rag.md) e os pontos de parada em [`humano.md`](humano.md).
>
> O histórico da decisão (v1 no papel → v2 construída) continua em
> [`arquitetura-v2.md`](arquitetura-v2.md).

## 1. O diagrama (§3.1)

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
             rejeita no prazo       → nada é gravado ───────────────────────────────► ●T4
             sem resposta em 20 min → [C] grava fila_humana, com as considerações
                                      do agente ────────────────────────────────────► ●T1

  registrar_encaminhamento    reversível: uma linha na tabela encaminhamentos
      destinos: fila_comercial · devolver_cliente · anotacao_interna · fila_humana
      a pessoa entra DEPOIS do término, lendo a fila (§7); a execução não espera por ela


DADOS   dados/tickets.db (SQLite), acessado só por src/db.py

  tickets ............. lido por consultar_ticket
  kb_artigos .......... o "ÍNDICE" de hoje: não há índice vetorial, só busca por palavra-chave
  chamados_internos ... escrito por abrir_chamado_interno; relido para contar a reincidência
  encaminhamentos ..... escrito por registrar_encaminhamento; relido para o ■G6
  pendencias .......... a ação irreversível à espera do analista, o prazo e o Estado da
                        execução pausada; criada em src/db.py, e não no seed


MEMÓRIA   nenhuma entre execuções: cada execução parte do zero
  O que atravessa execuções é registro do banco (as duas releituras acima) e, na pausa do
  [H1], o Estado guardado em `pendencias` para a mesma execução continuar depois.
  logs/TKT-0000.json guarda a trajetória; o agente grava e nunca lê.


TÉRMINOS   ●T1 respondeu · ●T2 orcamento_esgotado · ●T3 erro_fatal · ●T4 aguardando_humano
```

### Os portões em código

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

## 2. As ferramentas

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

## 3. O laço

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

O caminho real é curto. Nas 16 execuções das duas rodadas com o `agente-v5.md`
(`logs/rodada-1-prompt-v5/`, `logs/rodada-2-prompt-v5/`), todas tiveram de 2 a 4 passos e de 3 a
5 chamadas ao modelo.

## 4. O estado

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
| `pendencia` | dict ou `None` | o laço, ao capturar `PausaParaHumano` | o log |
| `prazo_confirmacao_min` | número (padrão 20) | `rodar()`, na criação | `abrir_chamado_interno`, para calcular o `vence_em`; a retomada, para o texto do encaminhamento |
| `pendencia_id` | inteiro ou `None` | `abrir_chamado_interno`, ao gravar a pendência | o laço, para guardar o checkpoint |
| `termino`, `motivo`, `resposta` | enum, texto | o laço | `main.py`, o verificador e o log |
| `historico` | lista de mensagens | o laço | só a chamada ao modelo |

O `desfecho` é o único campo de decisão com dois escritores (as duas ferramentas de escrita), e o
portão ■G1 garante que só uma delas escreve por execução.

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

## 5. O orçamento

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
gastos; a retomada continua o relógio desse ponto (§7). Passos, tokens e custo seguem somando no
mesmo estado. A espera tem o seu próprio limite, que é o prazo de 20 minutos.

Dois limites conhecidos:

- **A conferência é entre voltas.** Se o modelo pedir várias ferramentas na mesma resposta, todas
  executam antes da próxima conferência, e a execução pode passar de 8 passos.
- **O teto de tempo não interrompe nada em andamento.** Ele não corta uma chamada ao modelo que
  demora.

## 6. O término

Toda execução grava por que parou (`Estado.termino` e `Estado.motivo`). São quatro términos:

| Término | Quando | O que ficou gravado no banco |
|---|---|---|
| ●T1 `respondeu` | o modelo respondeu só com texto e há desfecho gravado. Inclui a execução retomada: o analista aprovou, ou o prazo venceu e o código gravou a `fila_humana` | o desfecho |
| ●T2 `orcamento_esgotado` | um dos quatro tetos estourou; o motivo diz qual (`passos: 8/8`, `tempo: 91s/90s`) | nada, **ou** o desfecho, se o teto estourou depois da escrita e antes da resposta final |
| ●T3 `erro_fatal` | (1) API indisponível depois de 5 tentativas; (2) a API recusou a chamada (chave ou modelo inválido, erro do provedor); (3) o modelo encerrou sem desfecho depois de 2 lembretes; (4) interrupção inesperada | nada, salvo no caso (4), se a interrupção vier depois da escrita |
| ●T4 `aguardando_humano` | a abertura do chamado interno espera o analista, ou ele a rejeitou; o `motivo` diz qual | nada em `chamados_internos` nem em `encaminhamentos`. Na espera, a ação e o prazo ficam na tabela `pendencias`; os argumentos da ação ficam também no campo `pendencia` do log |

O ●T4 da espera não é um fim: é o único término que a mesma execução pode trocar depois, por
●T1, quando o analista aprova ou o prazo vence (§7).

Consequência do ●T2: para saber se o chamado teve desfecho, vale o campo `desfecho`, e não o
término. O verificador (`src/verificar.py`) confere o banco.

Erro de ferramenta não é término. O que o modelo pode contornar (id em formato errado, id
inexistente, portão recusado, argumento faltando) volta como dado. Hoje nenhuma ferramenta
levanta erro fatal: os casos (1) e (2) do ●T3 vêm da chamada ao modelo.

## 7. O humano

**Um único ponto em que o sistema para e espera: [H1].**

| | |
|---|---|
| Onde | dentro de `abrir_chamado_interno`, depois de todos os portões e antes do INSERT |
| Critério | ação irreversível |
| Quem é chamado | o **analista de suporte** (perfil do `case.md` §2.2) |
| O que ele vê | a ferramenta, o id do chamado, a categoria, o resumo, o time de destino, o `kb_id`, a hora do pedido, a hora em que o prazo vence e quantos minutos faltam (`python src/main.py --pendencias`). A prioridade não aparece: ela é calculada depois da confirmação |
| O que ele devolve | `--aprovar TKT-0000` ou `--rejeitar TKT-0000`. Não há aprovação com edição |
| Se aprova no prazo | o chamado é gravado e a execução pausada continua: o modelo recebe o resultado e dá a frase final; término ●T1 |
| Se rejeita no prazo | nada é gravado; término ●T4, com motivo "analista rejeitou a ação" |
| Se não responde em 20 minutos | o chamado interno **não** é aberto; o código grava `fila_humana` com as considerações do agente; término ●T1 |

**A espera é assíncrona.** `abrir_chamado_interno` não fica parado esperando: grava a ação na
tabela `pendencias`, com `pedido_em` e `vence_em`, e levanta `PausaParaHumano`. O laço guarda na
mesma linha o `Estado` da execução (chamado lido, scores, passos, mensagens, tokens e os segundos
já gastos) e termina em ●T4. Nada é escrito em `chamados_internos` antes da resposta. O analista
responde de outro processo, minutos depois, e `retomar()` (em `src/agente.py`) continua a mesma
execução: não há nova triagem nem nova busca.

**O prazo.** O analista tem **20 minutos** para confirmar ou rejeitar, contados do pedido de
confirmação (`case.md` §2.1; constante `PRAZO_CONFIRMACAO_MIN`, em `src/ferramentas.py`). Vencido
o prazo, a ação não é executada e o código, sem consultar o modelo, grava um encaminhamento à
`fila_humana` com as considerações do agente: a ação que ele propôs, o procedimento e o score que
a sustentam, o resumo já redigido e o motivo "confirmação não recebida em 20 minutos". O desfecho
leva `motivo: confirmacao_nao_recebida`, e a `suficiencia` da saída é negativa. Depois da
gravação o modelo é chamado uma vez, só para a frase final.

**O relógio vale antes da pessoa.** Uma aprovação que chega depois do `vence_em` é tratada como
prazo vencido: o chamado não é aberto. O silêncio nunca vira aprovação, e a aprovação tardia
também não.

**Aprovar duas vezes** não repete nada: a pendência só é resolvida uma vez (`resolver_pendencia`,
em `src/db.py`, confere o status no mesmo `UPDATE`), e a segunda chamada não encontra o que
aprovar.

Três limites do que foi implementado:

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

## 8. O nível de autonomia (§3.3)

**O nível é roteador**, implementado como um laço de ferramentas curto.

**Por que o workflow não servia.** Um workflow tem o caminho fixo em código. Aqui o caminho
depende de duas decisões sobre texto livre, as duas marcadas no diagrama:

- **◆D1, a triagem.** O cliente não preenche categoria. Decidir se "quero um servidor dedicado" é
  comercial, ou se "meu servidor não funciona" tem informação suficiente, não cabe em regra. No
  `TKT-0004` (as duas rodadas) o modelo foi direto para `fila_comercial`, em 2 passos, sem buscar
  na base.
- **◆D3, o relato contra o log.** É a decisão que nenhum portão do código consegue tomar. No
  `TKT-0002` da rodada 2 (`logs/rodada-2-prompt-v5/TKT-0002.json`), a busca devolveu o `KB-106`
  com score 0,67, acima do limiar, e o procedimento é de escalonamento: **os portões ■G3 e ■G4
  teriam deixado abrir o chamado**. O modelo não abriu. Viu que o cliente relata Webmail fora do
  ar e que o log aponta falha de DNS, e mandou o chamado à `fila_humana` com a divergência
  escrita. Sem essa decisão, o sistema abriria um chamado para a Infraestrutura sem saber de quem
  é o nameserver (`case.md` §2.12, regra 6).

**Por que não o agente.** O que colocaria o sistema acima de um roteador é decidir, em tempo de
execução, **quantos** passos dar e **quais**: buscar de novo (◆D4) e se recuperar de um erro de
ferramenta. As 16 execuções com o `agente-v5.md` não sustentam esse degrau:

| Capacidade | O que as rodadas mostram |
|---|---|
| Busca repetida (◆D4) | aconteceu em 3 das 16 execuções (`TKT-0002` na rodada 1, `TKT-0005` nas duas). Em nenhuma mudou o desfecho. No `TKT-0005` a busca nem devia ter ocorrido: o caso é de informação insuficiente |
| Recuperação de erro | no `TKT-0999` (id inexistente), nas duas rodadas, o modelo leu o erro e encerrou sem registrar nada. Quem o fez registrar foi o lembrete, que é código |
| Tamanho do caminho | de 2 a 4 passos em todas as execuções, sempre consultar → (buscar) → escrever |

O laço continua sendo a forma da implementação, porque é ele que devolve ao modelo o erro de um
portão. Mas a decisão que o modelo toma dentro dele é de rota, e não de plano.

**Onde o roteador erra.** As decisões que só o modelo toma são também as que falham. Resultado
do verificador: 7 de 8 na rodada 1 e 6 de 8 na rodada 2. As três falhas são de ◆D1:

- `TKT-0005` (as duas rodadas): o modelo tratou como técnico um relato sem serviço nem sintoma, e
  o chamado foi para a `fila_humana` em vez de voltar ao cliente;
- `TKT-0003` (rodada 2): o modelo leu um problema técnico com exigência de prioridade como pedido
  fora da alçada.

Nas três o erro foi para o lado seguro: nenhum chamado indevido foi aberto.

Limite desta medição: o prompt e a busca foram ajustados depois de ver as falhas nestes mesmos 8
casos (cabeçalho de `src/prompts/agente-v5.md`). O resultado não prova que o sistema generaliza.

## 9. O que ainda falta neste documento

O enunciado pede, neste mesmo arquivo, quatro itens que dependem do grafo, que ainda não foi
construído:

| Item | Seção do enunciado | Situação |
|---|---|---|
| O grafo em ASCII, com nós, arestas e quem decide cada uma, ao lado da saída de `get_graph()` | §6.1 e §6.4 | a fazer; o diagrama do §1 descreve o laço atual |
| A tabela de padrões usados, com a justificativa de cada um | §6.2 | a fazer |
| A tabela de campos do estado do grafo, com reducers | §7.1 | a fazer; a tabela do §4 descreve o `Estado` atual |
| Todos os pontos de parada marcados no grafo, com o critério de cada um | §8.1 | a fazer; hoje há um, o [H1] do §7 |

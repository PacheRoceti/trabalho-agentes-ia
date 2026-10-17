# Human-in-the-loop (Parte 2, item 8)

> **Estado deste documento: versão de 12/10/2026.** As regras (quem confirma, os prazos, o que
> acontece no silêncio) estão decididas e escritas no [`case.md`](case.md) §2.1. A implementação
> existe nos dois caminhos: no grafo (`src/grafo.py`, o caminho padrão), com `interrupt` e
> checkpointer do LangGraph, e no laço da Parte 1 (`--laco`), com uma retomada feita à mão sobre
> o SQLite. Nos dois a abertura de
> chamado pausa, fica pendente com prazo de 20 minutos, e o analista aprova ou rejeita de outro
> processo. **O H1 está implementado nos dois caminhos; o H2, só no grafo (12/10/2026, §2.4); o
> H3 não existe.** No grafo o analista pode também **aprovar editando** o texto: o resumo do
> chamado (§2.1) ou a mensagem ao cliente (§2.4). O que falta está no §7.

## 1. Onde o sistema para, e por qual critério (§8.1)

| | Ponto de parada | Critério | Quem é chamado | Situação |
|---|---|---|---|---|
| H1 | antes de abrir um chamado interno | **ação irreversível**: não existe ferramenta para apagar ou encerrar um chamado | analista de suporte | implementado: pausa assíncrona, com prazo e retomada |
| H2 | antes de enviar o pedido de informação ao cliente | **ação irreversível**: a mensagem chega ao cliente e não tem volta | analista de suporte | implementado **no grafo** (12/10/2026, §2.4): pausa assíncrona, com prazo e retomada. No laço (`--laco`) o pedido continua só gravado, sem confirmação |
| H3 | depois de enviar o pedido, à espera da resposta | falta informação para classificar o chamado | o cliente | não implementado |

H1 e H2 são o mesmo nó do grafo, `confirmar` (`grafo.md` §1): o H2 não acrescentou nó nem
aresta. O nó do H3 (`aguardar_cliente`) não existe.

**Os critérios que o sistema não usa:**

- **Custo acima de um teto.** Nenhuma ação do agente tem custo que varie: o que ele grava é um
  registro. O custo da execução em si tem teto no orçamento, e estourá-lo é término, não pausa.
- **Confiança baixa.** Score abaixo do limiar não pausa: o chamado vai para a fila humana e a
  execução termina. A diferença é intencional. Na pausa o agente tem uma ação pronta e espera
  autorização; com confiança baixa ele não tem ação a propor, e entrega o caso inteiro.

**A ação mais perigosa sem ponto de parada** é `anotacao_interna`: uma correção sugerida que o
analista vai executar. Ela não pausa porque é reversível (é uma linha de anotação) e porque quem
a lê é a mesma pessoa que confirmaria. O risco que resta é o analista executar uma sugestão
errada sem conferir; ele é contido pelo portão de confiança, e não por uma pausa.

**O risco medido, e aceito (11/10/2026).** A busca vetorial deixa passar perguntas que a base não
responde: 5 de 31 agem, mesmo com a triagem na frente, e quatro delas num guia `anotar` (`rag.md` §4.3).
O grupo avaliou pausar também a `anotacao_interna` e **decidiu não fazê-lo**: a pausa continua só nas
ações irreversíveis. Fica assumido que, nesses casos, o analista lê uma anotação com a sugestão de um
procedimento que não se aplica ao relato. A tela do H1 (§2.1) só vale para o chamado interno.

## 2. O que a pessoa vê, e o que ela devolve (§8.2)

### 2.1 Hoje

O que o analista vê (`mostrar_pendencia`, em `src/main.py`), ao fim da execução que pausou e em
`python src/main.py --pendencias`:

```
  >> AÇÃO IRREVERSÍVEL aguardando o analista de suporte:
     ferramenta: abrir_chamado_interno
     id_ticket: TKT-0007
     categoria: permissao_arquivos
     resumo: <o resumo redigido pelo modelo>
     time_destino: Infraestrutura
     kb_id: KB-102
     prioridade_prevista: P2
     pedido_em: 2026-10-11T00:24:51-03:00
     vence_em: 2026-10-11T00:44:51-03:00
     faltam: 20 min
     se aprovada: abre um chamado interno para Infraestrutura, com prioridade P2. Não há como apagar nem encerrar o chamado por aqui
     rejeitada ou sem resposta no prazo, o chamado vai para a fila humana com esta ação proposta
     responder: python src/main.py --aprovar TKT-0007   |   --rejeitar TKT-0007
     aprovar corrigindo o resumo: python src/main.py --aprovar TKT-0007 --resumo "texto corrigido"
```

O bloco é a tela de uma execução real pelo grafo (`logs/grafo-caso-6/saida-terminal.txt`,
11/10/2026), com o resumo abreviado. No laço (`--laco`) a linha `prioridade_prevista` não
aparece.

**O que a tela ganhou em 11/10/2026** (decisão do grupo, para o analista conferir o que o sistema
não confere): depois de `prioridade_prevista`, quatro campos e, se houver, um aviso. Execução real
do `TKT-0007`, pelo grafo (`logs/grafo-h1-tela/TKT-0007.json`):

```
     guia_publicado_em: 2026-10-06
     guia_nao_cobre: ['ssh']
     plano: VPS Pro
     escopo_do_plano: Servidor virtual gerenciado pela empresa. O suporte cobre o sistema operacional, a rede, os certificados, o firewall e os backups da VPS. A aplicação instalada pelo cliente dentro da VPS está fora do escopo do suporte. ...
     ATENÇÃO: o guia KB-102 declara que NÃO cobre: ssh. Confira se o relato cai numa dessas situações.
```

- **`guia_publicado_em` e `guia_nao_cobre`** vêm do guia que o sistema usou. A ressalva é a última barreira
  contra o que o nó `conferir_ressalva` deixa passar: o modelo não reconhece a situação "ssh" do KB-102
  (`rag.md` §4.2), e a pausa é onde uma pessoa ainda pode vê-la. O aviso `ATENÇÃO` só aparece quando o
  guia declara alguma situação.
- **`plano` e `escopo_do_plano`** vêm da ficha do plano do cliente (`planos_fichas`). É contexto: nenhuma
  regra de decisão usa o plano. O mesmo texto vai ao modelo que redige o resumo (`redigir`).
- **`precedentes`** (11/10/2026) vem da memória episódica (`memoria.md` §3): quantas vezes o analista
  aprovou, editou ou rejeitou este guia nos últimos 90 dias, e os últimos episódios do mesmo cliente na
  mesma categoria. A tela repete isso em linhas `MEMÓRIA:`, que só aparecem quando há o que mostrar. É
  aviso: o desfecho proposto não muda com ele. A tela copiada acima é anterior a este campo; a nova está
  em `logs/grafo-memoria-2/`.
- **Rejeitar dizendo por quê** (11/10/2026): `--rejeitar TKT-0007 --motivo caso_fora_do_guia` (ou
  `guia_errado`, `resumo_ruim`, `outro`). O motivo é opcional, não muda o que a rejeição grava, e vai
  para a memória: a linha `MEMÓRIA:` passa a separar as rejeições por motivo, e `--candidatas` lista os
  padrões que se repetiram (`memoria.md` §5). Só no grafo.
- **`fatos_cliente`** (11/10/2026) vem da memória semântica (`memoria.md` §4): os fatos do ambiente do
  cliente que um analista confirmou (`--fato CLI-07 acesso=ssh`). A tela os repete em linhas
  `FATO CONFIRMADO`. Com o fato `acesso: ssh` ao lado do aviso de que o guia não cobre `ssh`, o analista
  tem os dois dados para conferir. A tela com o fato está em `logs/grafo-fatos-controle/`.
- O laço (`--laco`) não preenche esses campos.

**As três respostas aceitas**, dentro do prazo:

| Resposta | Comando | O que acontece |
|---|---|---|
| **aprovar** | `--aprovar TKT-0007` | abre o chamado interno com o resumo que o modelo redigiu |
| **aprovar editando** | `--aprovar TKT-0007 --resumo "texto corrigido"` | abre o chamado interno com o resumo do analista. Só no grafo |
| **rejeitar** | `--rejeitar TKT-0007` | não abre; o chamado vai para a fila humana com as considerações do agente (§4) |

**Aprovar editando: o que é editável, e o que não é.**

- **Editável: só o resumo.** É o único campo da ação que o modelo escreveu, e é onde ele erra:
  na execução do §5 o resumo dele vinha com negrito de Markdown e com uma causa ("sugere que a
  causa é...") que o cliente não relatou.
- **Não editável: categoria, time e prioridade.** Vêm do procedimento e da reincidência,
  calculados pelo código na gravação. O analista não reclassifica: só o gestor (`case.md` §2.1).
- **Não editável: o procedimento (`kb_id`).** Trocá-lo troca o time, a prioridade e a chave de
  idempotência. É outra ação, e o caminho para ela é rejeitar.

**As regras da edição** (`retomar_grafo` e o nó `confirmar`, em `src/grafo.py`):

- o texto do analista passa pela **mesma regra** do texto do modelo (`_erro_do_texto`: 20
  caracteres ou mais). Quem escreve muda, a regra não;
- a conferência acontece **antes** de responder ao `interrupt`. Uma edição recusada não gasta a
  aprovação: nada é gravado e a ação continua à espera;
- **o prazo não se estende.** Uma aprovação editada que chega depois dos 20 minutos é prazo
  vencido, e a edição é descartada: a fila humana recebe o resumo do agente;
- **o original não se perde.** A confirmação no log guarda `resumo_original` (do modelo),
  `resumo_aprovado` (do analista) e `editado: true`. No banco fica só o aprovado;
- um resumo igual ao proposto não conta como edição;
- `--rejeitar` com `--resumo` é recusado, e o laço (`--laco`) recusa a edição.

### 2.2 O que entrou nessa tela em 11/10/2026, e o que ainda falta

Entraram, no grafo: **a prioridade prevista** (`prioridade_prevista`, em `src/db.py`: a regra da
abertura aplicada na hora do pedido), **a consequência escrita** ("abre um chamado interno para
..., com prioridade ...; não há como apagar") e o comando para **aprovar editando**.

A prioridade da tela é a **prevista**. A do chamado é calculada de novo na gravação; as duas só
diferem se outro chamado do mesmo cliente e da mesma categoria for aberto durante a espera.

| Ainda falta | Por que importa |
|---|---|
| **a reincidência** que o sistema confirmou | é o que faz a prioridade subir; hoje o analista vê o P1 e não vê por quê |
| **o score** do procedimento | é o que sustenta a ação. Hoje ele só aparece se o modelo o citar no resumo |
| **o SLA** da prioridade | "P2" não diz ao analista que são 1 dia útil |
| **editar o resumo num editor** | o texto corrigido vai inteiro na linha de comando; não há como partir do resumo do modelo e mudar uma frase |

### 2.3 O que a proposta previa, e o que foi feito

A proposta eram três respostas: **aprovar**, **rejeitar** e **aprovar editando**, com a edição
alterando só o texto (o resumo do chamado, ou a mensagem ao cliente). As três existem para o
resumo do chamado (§2.1) e, desde 12/10/2026, para a mensagem ao cliente (§2.4). Categoria, time e prioridade não são
editáveis: vêm do procedimento, e só o gestor reclassifica (`case.md` §2.1).

### 2.4 O pedido de informação ao cliente (H2, 12/10/2026, só no grafo)

Quando a triagem classifica o relato como insuficiente e o chamado ainda não recebeu um pedido, o
nó `decidir` propõe `devolver_cliente`. Antes disso era uma escrita direta; agora a rota é a do H1:
`pedir_confirmacao` → `confirmar` (`interrupt`) → `gravar`. O que o analista vê, numa execução real
do `TKT-0005` (`logs/grafo-h2/saida-terminal.txt`, 12/10/2026):

```
  >> AÇÃO IRREVERSÍVEL aguardando o analista de suporte:
     ferramenta: devolver_cliente
     id_ticket: TKT-0005
     relato: Meu servidor não está funcionando direito.
     mensagem: O servidor do plano Hospedagem Start não está apresentando o funcionamento esperado. O problema ocorre desde quando foi relatado.
     plano: Hospedagem Start
     pedido_em: 2026-10-12T12:24:35-03:00
     vence_em: 2026-10-12T12:44:35-03:00
     faltam: 20 min
     se aprovada: o pedido é registrado como enviado ao cliente e não tem volta (o sistema simulado não tem canal de mensagem). É o único pedido de informação permitido neste chamado
     rejeitada ou sem resposta no prazo, o chamado vai para a fila humana com esta ação proposta
     responder: python src/main.py --aprovar TKT-0005   |   --rejeitar TKT-0005
     aprovar corrigindo a mensagem: python src/main.py --aprovar TKT-0005 --mensagem "texto corrigido"
     rejeitar dizendo por quê: python src/main.py --rejeitar TKT-0005 --motivo mensagem_ruim | informacao_suficiente | outro
```

**O que a tela tem, e o que não tem.**

- **`relato`** é o texto do cliente. Entrou por decisão do grupo (12/10/2026): o que o analista
  julga no H2 é se o relato era mesmo insuficiente, e sem ele a tela só mostraria a conclusão do
  agente. O relato fica na tabela `pendencias`; nunca na memória episódica.
- **Não há guia, score, prioridade nem precedentes.** O chamado não foi classificado, então não
  existe procedimento que sustente a ação, e a consulta de precedentes é por guia.

**As respostas**, dentro do prazo:

| Resposta | Comando | O que acontece |
|---|---|---|
| **aprovar** | `--aprovar TKT-0005` | o pedido é registrado como enviado, com a mensagem do modelo |
| **aprovar editando** | `--aprovar TKT-0005 --mensagem "texto corrigido"` | o pedido é registrado com a mensagem do analista |
| **rejeitar** | `--rejeitar TKT-0005`, com `--motivo` opcional | nada é enviado; o chamado vai para a fila humana com a mensagem que o agente redigiu |

**As regras** (as do H1, aplicadas ao outro texto):

- **Só a mensagem é editável**, e ela passa pela **mesma regra** da mensagem do modelo
  (`_erro_do_texto`): 10 caracteres ou mais e nenhuma informação interna (procedimentos, times,
  filas, scores, prioridade, SLA). A conferência vem **antes** de responder ao `interrupt`: edição
  recusada não gasta a aprovação.
- **`--resumo` numa pendência do H2, e `--mensagem` numa do H1, são recusados**: cada ação tem
  um texto só.
- **O motivo da rejeição é o da ação pendente** (`db.MOTIVOS_POR_ACAO`): `mensagem_ruim`,
  `informacao_suficiente` (o analista entende que o relato bastava: aponta a triagem) e `outro`.
  Os motivos do H1 falam de guia e são recusados aqui, e vice-versa. O motivo vai à memória
  episódica e ao relatório `--candidatas`, onde o padrão do H2 aparece sem guia (`memoria.md` §5).
- **Um pedido barrado não gasta o único pedido do chamado.** A contagem
  (`db.contar_pedidos_cliente`) é de linhas gravadas, e a rejeição e o prazo vencido não gravam
  o pedido: gravam `fila_humana`.
- **O prazo, o relógio antes da pessoa e o original guardado** são os do §2.1. O log traz
  `mensagem_original` e `mensagem_aprovada`.
- **Sem aviso ao gestor** no prazo vencido (decisão de 12/10/2026): o aviso existe para o chamado
  que seria P1, e um chamado que a triagem não classificou não tem prioridade prevista.

**"Enviar" é gravar uma linha.** O sistema simulado não tem canal de mensagem. Aprovado o pedido,
`db.registrar_pedido_cliente` grava a linha em `encaminhamentos` com a coluna `enviado_em`
preenchida (relógio de verdade, como nas pendências), e é só isso. Consequências assumidas:

- aprovar e enviar são um ato só: não existe "aprovado e ainda não enviado", falha de entrega nem
  reenvio, e nada disso é testado;
- a irreversibilidade é do domínio (`case.md` §2.1), e não do banco simulado;
- o que a demonstração abaixo prova é que **nada é gravado antes da confirmação**, e não que um
  cliente recebeu algo.

A função é o único ponto do grafo que grava um `devolver_cliente`, e é idempotente pelo chamado:
se o canal existir um dia, entra ali, e o H3 lê o `enviado_em` para contar os 3 dias úteis. No
laço da Parte 1 o pedido continua sendo gravado sem confirmação, e com `enviado_em` vazio.

**A demonstração, com log** (`logs/grafo-h2/`, 12/10/2026, `ministral-8b-latest`, commit `e1f76e0`
mais as alterações locais do H2, sem `--auto-aprovar`). Seis comandos, cada um em um processo:

| # | Comando | Hora | O que aconteceu |
|---|---|---|---|
| 1 | `python src/main.py TKT-0005 --rodada grafo-h2` | 12:24:35 | parou em `confirmar`: `aguardando_humano`, prazo até 12:44:35, 4 passos, 2 chamadas ao modelo, 1.444 tokens, nada gravado (`TKT-0005-pausado.json`) |
| 2 | `--pendencias` | | 1 ação aguardando: a tela acima |
| 3 | `--aprovar TKT-0005 --mensagem "Abrimos o INC-0001 com prioridade P1 para o seu caso."` | | **edição recusada**: "cita informação interna ou promete prioridade (termos encontrados: inc-0001, p1, prioridade ...)". Código de saída 1, nada gravado |
| 4 | `--rejeitar TKT-0005 --motivo guia_errado` | | **resposta recusada**: o motivo não vale para `devolver_cliente`. Código de saída 1, a ação continua aguardando |
| 5 | `--aprovar TKT-0005 --mensagem "Para identificarmos o problema, informe qual site ou serviço está afetado, a mensagem de erro que aparece e desde quando isso ocorre."` | 12:24:40 | **aprovado com edição**: o grafo continuou de `confirmar` e gravou o pedido com a mensagem do analista. 6 passos, as mesmas 2 chamadas e 1.444 tokens (`TKT-0005.json`) |
| 6 | o comando 5, de novo | | "Não há confirmação pendente para TKT-0005." |

Conferência no banco depois do comando 6: **um** encaminhamento `devolver_cliente` para o
`TKT-0005`, com a mensagem do analista e `enviado_em` 12:24:40; uma pendência `aprovada`; nenhum
chamado interno e nenhum aviso ao gestor.

**O que a demonstração achou: a mensagem do modelo não era um pedido.** O texto redigido para o
cliente ("O servidor do plano Hospedagem Start não está apresentando o funcionamento esperado. O
problema ocorre desde quando foi relatado.") repete a queixa e não pergunta nada. Não é um acaso
desta execução: as três rodadas de 10/10/2026 gravaram textos do mesmo tipo para o `TKT-0005`
(`logs/grafo/`, `logs/grafo-rodada-2/`, `logs/grafo-rodada-3/`), e as três afirmam que o
problema ocorre "desde a última verificação", o que o cliente não disse. São 4 execuções em 4; a
conferência de todos os logs do grafo, feita depois, achou o mesmo em 15 de 15.
Nenhuma barreira em código pega isso: o nó `validar` confere tamanho e informação interna, e o
verificador confere o desfecho gravado, não o texto. Até 12/10/2026 essa mensagem era gravada
direto; hoje a única barreira é o analista, no H2.

**Tratado no mesmo dia, com o `redigir-v2.md`** (`prompts.md` §2.1): uma regra do prompt foi
reescrita, e em três rodadas dos 8 casos a mensagem do `TKT-0005` passou a ser "Precisamos de
mais informações para ajudar. Qual serviço ou servidor está com problema? Qual erro ou
comportamento aparece? Desde quando isso ocorre?" (`logs/grafo-redigir-v2-1/` a `-3/`). A tela e
os logs desta seção são anteriores e mostram a mensagem do v1.

**E decidido em seguida: o pedido ao cliente é texto padrão, do código** (`prompts.md` §2.2). O
v2 produziu a mesma mensagem nas três execuções, o que mostrou que não havia decisão do modelo
ali. O nó `redigir` passou a devolver a constante `PEDIDO_AO_CLIENTE` (`src/grafo.py`), com cinco
perguntas tiradas do que os guias da base usam: o serviço, o domínio ou o nome do banco, a
mensagem ou o código de erro, a data e a hora, e o que mudou antes. O H2 não mudou: o analista vê
o relato e o texto, aprova, rejeita ou aprova trocando a mensagem. A pausa refeita com o texto
padrão está em `logs/grafo-pedido-padrao-h2/` (12/10/2026): pausa às 14:21:06 com 4 passos, 1
chamada ao modelo e 621 tokens; aprovação por outro processo às 14:21:08, com a mesma chamada e
os mesmos tokens; a segunda aprovação não encontrou nada pendente; no banco, um `devolver_cliente`
com `enviado_em`, uma pendência `aprovada` e nenhum chamado interno.

Limites: quem respondeu foi quem fazia a demonstração, 5 segundos depois da pausa, e não um
analista. A rejeição e o prazo vencido do H2, que estavam só nos testes offline
(`tests/test_grafo.py`, os 13 testes `test_h2_*`), foram executados com o modelo real ainda em
12/10/2026 (`logs/grafo-h2-rejeicao/` e `logs/grafo-h2-vencido/`, commit `4aa9818`). Nos dois
cenários o `TKT-0005` foi para a `fila_humana` com a mensagem redigida, nenhum
`devolver_cliente` foi gravado (o único pedido do chamado não foi gasto) e não houve aviso ao
gestor. Na rejeição, o motivo `informacao_suficiente` ficou no episódio. O prazo vencido foi
provocado com `--prazo-confirmacao 0.02`; a tabela e os limites estão em `grafo.md` §6.7.

## 3. A implementação, e a dependência do checkpoint (§8.3)

**No laço da Parte 1 (`--laco`).** A pausa acontece dentro da ferramenta `abrir_chamado_interno` (`src/ferramentas.py`).
Todas as validações vêm antes dela e a escrita vem depois, então nada com efeito colateral
acontece antes da confirmação. Sem resposta imediata, a ferramenta grava a ação na tabela
`pendencias`, com `pedido_em` e `vence_em`, e levanta `PausaParaHumano`; o laço guarda o `Estado`
da execução na mesma linha e termina em `aguardando_humano`.

A espera não vive no processo: ele termina, e a resposta chega por outro
(`python src/main.py --aprovar` ou `--rejeitar`). `retomar()`, em `src/agente.py`, lê a
pendência, reconstrói o `Estado`, executa a escrita aprovada (ou grava o encaminhamento à fila
humana, na rejeição e no prazo vencido) e devolve a observação ao modelo, que dá a frase final. É um checkpoint feito à mão, para esta única pausa: uma coluna de JSON no
banco simulado, que `--reset` apaga.

**No grafo, que é o caminho padrão (implementado em 10/10/2026, só para o H1).** `interrupt` dentro do nó `confirmar`,
e retomada com `Command(resume=...)`, por `retomar_grafo()` (`src/grafo.py`). Como o nó roda de
novo desde o começo na retomada, o `confirmar` não faz nada antes de pausar: a hora do pedido e a
linha em `pendencias` são do nó anterior (`pedir_confirmacao`), e a escrita é do nó seguinte
(`gravar`).

Checkpointer em **SQLite**, num arquivo próprio (`dados/checkpoints.db`, ignorado pelo git),
endereçado pelo `thread_id` = id do chamado externo (`memoria.md` §1.5). Em memória não serve: a
espera atravessa processos, e morreria com o primeiro.

A tabela `pendencias` continua sendo a fila do analista nos dois caminhos: é ela que
`--pendencias` lista e que aplica o prazo. A pendência guarda de qual caminho é a pausa, e
`--aprovar` / `--rejeitar` chamam a retomada certa. Uma pausa e uma retomada em dois processos
foram executadas com o modelo real em `logs/grafo-pausa/` (10/10/2026, commit `083d132`): pausa às 23:51:58, aprovação por outro processo às 23:52:02, e uma segunda aprovação que não encontrou nada pendente (`grafo.md` §6.1). Os testes de
`tests/test_grafo.py` cobrem aprovar, aprovar duas vezes, rejeitar e prazo vencido. Com o modelo
real, a rejeição do H1 foi executada em 11/10/2026 (`logs/grafo-memoria-1/`,
`logs/grafo-procedural/`), e o prazo vencido em 12/10/2026 (`logs/grafo-h1-vencido/`): o
`TKT-0003`, que seria P1, pausou com o prazo encurtado para 1,2 segundo; o comando seguinte
gravou a `fila_humana` e o aviso ao gestor, sem abrir chamado interno, e a aprovação tardia não
encontrou nada pendente (`grafo.md` §6.7).

## 4. O que acontece se ninguém responder, ou se a pessoa rejeitar (§8.4)

| Ponto | Prazo | Quando vence |
|---|---|---|
| H1 e H2 (analista) | **20 minutos**, contados do pedido de confirmação | a ação **não é executada**. O chamado vai para a fila humana com as considerações do agente: a ação proposta, a prioridade que o chamado teria, o procedimento e o score que a sustentam, o texto já redigido e o motivo "confirmação não recebida em 20 minutos". Se o chamado interno seria **P1**, o gestor de suporte também é avisado. No H2 as considerações são a ação proposta e a mensagem redigida (não há procedimento, score nem prioridade), e o gestor não é avisado |
| H3 (cliente) | **3 dias úteis** | o chamado vai para a fila humana. O agente não encerra o chamado e não pede de novo |

Nos dois casos o silêncio nunca vira aprovação, e o caminho padrão é entregar o caso a uma
pessoa, com o que o agente já apurou.

**A rejeição segue o mesmo caminho do prazo vencido** (decisão de 10/10/2026). Se o analista
rejeita a ação dentro do prazo, ela não é executada e o chamado vai para a fila humana com as
mesmas considerações, e o motivo "ação rejeitada pelo analista de suporte". Antes, a rejeição não
gravava nada: o chamado ficava sem desfecho, e o que o agente tinha apurado só existia no log.

| Resposta ao H1 | O que é gravado | Motivo no desfecho | Gestor avisado? |
|---|---|---|---|
| aprova no prazo | o chamado interno | (não há) | não |
| rejeita no prazo | `fila_humana`, com as considerações do agente | `acao_rejeitada` | não |
| não responde em 20 minutos, ou aprova depois do prazo | `fila_humana`, com as considerações do agente | `confirmacao_nao_recebida` | **sim, se o chamado seria P1** |

**Por que 20 minutos.** O SLA do chamado interno só começa a contar depois da confirmação
(`case.md` §2.12, regra 3). Um chamado P1 tem 2 horas para ser resolvido; cada minuto de espera
pela confirmação é atraso que nenhum SLA registra.

**O que está implementado.** O prazo e a rejeição do H1, como descritos nas tabelas: `retomar()`
compara a hora com o `vence_em` antes de olhar a decisão, então uma aprovação tardia também vira
prazo vencido. O encaminhamento é gravado pelo código (`encaminhar_pendencia`, em
`src/ferramentas.py`), e o modelo só é chamado depois, para a frase final. No grafo, o prazo e a
rejeição do H2 seguem a mesma tabela, pela mesma função, sem a coluna do gestor (§2.4). O H3 não
existe, e o prazo dele também não.

**Quem aplica o prazo (desde 17/10/2026): o vigia, e o começo de cada comando.** Até 16/10/2026
o prazo era só conferido: as pendências vencidas eram encaminhadas no começo do próximo comando do
`main.py`, e se ninguém rodasse nada o chamado ficava na pausa. A ação vencida nunca era executada,
mas a fila humana não a recebia no minuto 20, e o gestor não era avisado do P1. Agora um processo
à parte, o vigia (§4.1), aplica o prazo sozinho. O começo de cada comando continua aplicando-o,
como segunda rede para quando o vigia não está rodando.

**O aviso ao gestor.** Quem lê a fila humana é o próprio analista de suporte. Se ele não
respondeu à confirmação, o encaminhamento cai na fila da mesma pessoa: o chamado não fica preso
numa pausa, mas nada garante que alguém o veja a tempo. Por isso, quando o prazo vence e o
chamado interno seria **P1** (SLA de 2 horas), o código grava também um aviso ao gestor de
suporte, na tabela `avisos_gestor`, com a mesma mensagem do encaminhamento (decisão de
10/10/2026).

- A prioridade usada é a **prevista**: a base do procedimento mais a reincidência, pela mesma
  regra da abertura de chamado, calculada na hora do vencimento.
- O aviso vale só para o prazo vencido. Na rejeição o analista já viu o chamado.
- **Limite:** o aviso é um registro numa tabela, e não uma notificação. O sistema simulado não
  tem canal de mensagem, e não há comando para o gestor listar os avisos.

### 4.1 O vigia do prazo (17/10/2026)

`python src/vigiar_prazos.py` é um processo à parte que aplica o prazo sem ninguém rodar comando
nenhum. A regra não mudou e continua sendo do código: a cada volta ele chama a mesma
`agente.vencer_pendencias` que o `main.py` chama, e o mesmo `db.esquecer_episodios` (o decaimento
da memória episódica). Entre uma volta e outra ele dorme até o `vence_em` mais próximo, mais um
segundo, e nunca mais que 30 s, porque uma pendência nova pode chegar a qualquer momento. Ele não
aprova, não rejeita, não chama o modelo para decidir e não muda o prazo. Só no laço (`--laco`) a
retomada chama o modelo, para a frase final, e por isso o vigia lê a chave da API do `.env`.

**Feito para rodar sem terminal.**

| Requisito | Como fica |
|---|---|
| nada interativo | a configuração vem do `.env` e dos argumentos (`--intervalo`, `--log`, `--uma-vez`) |
| saída em arquivo | log rotativo em UTF-8 (`logs/vigia/vigia.log`, ignorado pelo git), e na tela quando há tela |
| estado no banco | a pendência e o `vence_em` estão na tabela `pendencias`: reiniciar o vigia não perde nada, e a primeira volta depois de um reinício vence o que passou do prazo enquanto ele estava parado |
| erro não o derruba | cada volta abre e fecha a própria conexão; um erro (rede, cota, banco recriado por `--todos` ou `--reset`) vira uma linha de log, e a próxima volta tenta de novo (`test_erro_numa_volta_nao_derruba_o_vigia`) |
| um vigia por máquina | trava do sistema operacional em `dados/vigia.lock` (`db.travar_instancia`); o segundo sai sem fazer nada (`test_um_vigia_por_maquina_e_a_situacao_diz_se_ele_roda`) |
| parada limpa | Ctrl+C, SIGTERM ou Ctrl+Break: termina a volta em curso e sai |
| sinal de vida | `dados/vigia-batimento.json` (pid, última volta, quantas aguardam, próxima volta); o `main.py --pendencias` diz se o vigia está rodando ou PARADO |

**A corrida que o vigia criou, e a trava que a fecha.** Com dois processos respondendo à mesma
pendência (o vigia vencendo e o analista aprovando no mesmo instante), o grafo podia retomar a
mesma execução duas vezes: `retomar_grafo` confere no checkpoint se a execução ainda está parada
em `confirmar` e só depois grava a resolução, e os dois passavam pela conferência. O teste
`test_duas_respostas_ao_mesmo_tempo_gravam_um_desfecho_so` reproduz isso: **sem a trava, o
`TKT-0003` ficou com um chamado interno P1 aberto E um encaminhamento à fila humana com aviso ao
gestor**, nas três vezes em que foi rodado assim. O laço já estava protegido, porque grava a
resolução (`resolver_pendencia`, atômico) antes de escrever. A correção é uma trava do sistema
operacional em `dados/respostas.lock` (`db.trava_das_respostas`), em volta de toda retomada
(`agente.retomar`, a porta de entrada do `--aprovar`, do `--rejeitar`, do vencimento e do vigia):
quem chega depois espera e, quando entra, já não encontra a pausa e não grava nada. A trava some
quando o processo morre, então uma queda no meio de uma resposta não deixa a pendência presa. As
conexões com os dois bancos passaram a esperar até 30 s (`db.ESPERA_BANCO_S`) em vez de falhar com
"database is locked".

**Demonstração com o prazo real de 20 minutos e o modelo real** (`logs/grafo-prazo-vigia/`,
17/10/2026, commit `77757ea` sem alterações locais, `ministral-8b-latest`, os prompts em uso).
Banco recriado; o vigia subiu às 16:02:18 num terminal à parte, com o log em `vigia.log`; o
`TKT-0003` (o chamado que seria P1) rodou **sem** `--auto-aprovar`. Depois disso, ninguém rodou
comando nenhum até o vencimento:

| Hora | Quem | O que aconteceu |
|---|---|---|
| 16:02:35 | `main.py TKT-0003` | pausou em `confirmar`, prazo até 16:22:35 (3 chamadas ao modelo, 2.527 tokens; `TKT-0003-pausado.json`) |
| 16:02:3x | `main.py --pendencias` | 1 ação aguardando, prioridade prevista P1, "faltam: 20 min"; "vigia do prazo: rodando (pid 15432)" |
| 16:22:36 | **o vigia, sozinho** | `PRAZO VENCIDO: TKT-0003 \| abrir_chamado_interno \| desfecho: fila_humana \| motivo: confirmacao_nao_recebida \| GESTOR AVISADO (aviso 1)`: um segundo depois do `vence_em` |
| 16:22:58 | `main.py --pendencias` | 0 ações aguardando; o vigia rodando, com a última conferência às 16:22:36 |
| 16:23:0x | `main.py --aprovar TKT-0003` | a aprovação que chega tarde: "Não há confirmação pendente para TKT-0003." |

No banco: a pendência `vencida`, resolvida às 16:22:36 por "ninguém: prazo vencido"; **nenhum
chamado interno**; um encaminhamento à fila humana; um aviso ao gestor, P1. O log final
(`TKT-0003.json`) tem o término `respondeu`, o desfecho `fila_humana` com suficiência negativa ("a
confirmação do analista não chegou em 20 minutos") e as mesmas 3 chamadas da pausa: o vencimento
não chamou o modelo. A sequência inteira está em `saida-terminal.txt`. O vigia foi encerrado com
`taskkill /F`, e por isso o log não tem a linha "vigia parado": a parada limpa por sinal não foi
demonstrada. Uma execução só, de um chamado só. O `criado_em` do encaminhamento é a data fixa do
banco simulado (`db.AGORA`), como em todo encaminhamento; o relógio de verdade está na pendência e
no aviso.

Uma primeira execução, mais cedo no mesmo dia, deu o mesmo resultado, mas rodou com código sem
commit e anterior à recuperação e às chaves: foi descartada e não está no repositório.

**Limites.**

- **Alguém precisa subir o vigia.** Num terminal, ele morre com o terminal; como serviço (§4.2),
  sobrevive. O grupo demonstrou o vigia num terminal, e não o instalou como serviço.
- **Ele só vale na máquina do banco.** O SQLite não pode ser aberto por uma pasta de rede: o vigia,
  o agente e os comandos do analista têm de rodar na mesma máquina. Analistas em outros PCs
  precisariam entrar nela (SSH ou área de trabalho remota) ou de uma API que não existe.
- **A precisão é de segundos, não de milissegundos:** o vigia acorda um segundo depois do
  `vence_em`, e a volta leva o tempo de gravar o encaminhamento.
- **O H3 continua sem prazo**, porque o H3 não existe.

### 4.2 Como rodar o vigia em servidor

O script é o mesmo; quem o mantém vivo é o sistema operacional. O grupo não instalou nenhuma das
formas abaixo: elas ficam escritas para quem for implantar.

**Windows, com o Agendador de Tarefas** (sem instalar nada): inicia no boot, roda sem ninguém
logado e não depende de terminal. Nas propriedades da tarefa, marque "reiniciar se a tarefa
falhar".

```
schtasks /Create /TN "VigiaPrazos" /SC ONSTART /RU SYSTEM /TR "C:\caminho\trabalho-agentes-ia\.venv\Scripts\python.exe C:\caminho\trabalho-agentes-ia\src\vigiar_prazos.py"
```

Para um serviço do Windows de verdade (iniciar, parar, reiniciar sozinho), o caminho usual é o
NSSM, que embrulha o mesmo comando. Quem não quiser um processo sempre ativo pode agendar
`python src/vigiar_prazos.py --uma-vez` a cada minuto: uma conferência e sai, com até um minuto de
atraso (se a anterior ainda estiver rodando, a nova sai sem fazer nada).

**Linux, com systemd.** Arquivo `/etc/systemd/system/vigia-prazos.service`, e depois
`systemctl enable --now vigia-prazos` (a saída também vai para `journalctl -u vigia-prazos`):

```ini
[Unit]
Description=Vigia do prazo de confirmação do agente de triagem
After=network-online.target

[Service]
WorkingDirectory=/opt/trabalho-agentes-ia
ExecStart=/opt/trabalho-agentes-ia/.venv/bin/python src/vigiar_prazos.py
Restart=always
RestartSec=10
User=agente

[Install]
WantedBy=multi-user.target
```

O `systemctl stop` manda SIGTERM, e o vigia termina a volta em curso antes de sair.

### 4.3 Uma queda no meio da retomada (17/10/2026)

`dados/tickets.db` (o desfecho) e `dados/checkpoints.db` (onde a execução está) são arquivos
separados: "gravou o desfecho" e "o checkpoint avançou" nunca são uma operação só. Até 16/10/2026,
uma queda do processo no meio de uma retomada deixava a execução assim:

| Janela | Onde caiu | Como ficava | O que acontece agora |
|---|---|---|---|
| J1 | em `confirmar`, ao processar a resposta | pendência resolvida, checkpoint ainda em `confirmar`: **presa**, e o texto editado pelo analista se perdia | a recuperação reenvia a resposta guardada, e o relógio decide igual, porque a hora é a gravada |
| J2 | entre `confirmar` e a escrita | pendência aprovada, nada gravado, checkpoint em `gravar`: **presa** | a recuperação roda `gravar` |
| J3 | no meio de `gravar` | parte gravada; refazer duplicaria o encaminhamento e o aviso ao gestor | a recuperação roda `gravar` de novo, e as chaves não deixam duplicar |
| J4 | depois de gravar, antes do log | desfecho gravado, sem log, sem episódio, checkpoint para sempre | a recuperação grava o log e o episódio e apaga o checkpoint |

**As quatro peças.**

1. **A resposta é guardada antes de retomar.** `retomar_grafo` grava a resposta (decisão, quem,
   quando, o texto editado e o motivo) na coluna `pendencias.resposta` antes do
   `Command(resume=...)` (`db.guardar_resposta`). Não dependemos de o LangGraph guardar o valor do
   `resume` antes de o nó rodar.
2. **A escrita pode ser refeita.** Tudo o que o nó `gravar` escreve tem chave: o chamado interno
   (`ticket:kb_id`, que já existia), o pedido ao cliente (um por chamado, já existia), o
   encaminhamento e o aviso ao gestor (novos). A chave do encaminhamento é **execução + chamado +
   destino** (`db.chave_do_encaminhamento`; decisão de 17/10/2026): reconhece a mesma gravação
   refeita, e não cria a regra "um encaminhamento por destino". Uma execução nova do mesmo chamado
   tem outro `execucao_id` e grava de novo, o que preserva o caso legítimo do cliente que manda mais
   informação. O aviso tem chave pela pendência: um aviso por pendência vencida. As colunas nascem
   em `db.garantir_colunas_da_recuperacao`, também em bancos antigos.
3. **A rotina `grafo.retomar_interrompidas`** pega a trava das respostas (§4.1). Com ela, ninguém
   está no meio de uma resposta, então o que está pela metade caiu. Ela acha as execuções paradas em
   `confirmar` com resposta guardada, em `gravar`, em `finalizar` ou no fim do grafo sem log; em
   `confirmar` reenvia a resposta, nos outros continua do checkpoint (`GRAFO.invoke(None)` roda os
   nós que faltam); depois grava o log, com o campo `recuperacao`, e o episódio, e apaga o
   checkpoint. Só conta como queda o checkpoint com mais de 5 minutos (`IDADE_MINIMA_DA_QUEDA_MIN`):
   uma execução nova, que não usa a trava, pode estar em `gravar` agora mesmo, e nenhuma execução
   viva fica parada num nó por 5 minutos (o teto de tempo é de 90 s).
4. **Quem a chama:** o vigia, a cada volta, e o começo de cada comando do `main.py` pelo grafo,
   antes do vencimento do prazo. Ela aparece como "EXECUÇÃO RETOMADA DEPOIS DE QUEDA".

**Testes, sem chave** (`tests/test_recuperacao.py`, 12, e um em `tests/test_vigia.py`): dez
derrubam o processo num ponto com uma exceção forçada numa função de `db.py` e rodam a recuperação.
Uma janela por teste (J1 antes e depois de resolver a pendência, J2, J3 na anotação e no prazo
vencido de P1, J4), mais a pausa normal que não é tocada, a execução recente que não conta como
queda e as duas faces da chave A. **Sem a chave, o teste da J3 grava o encaminhamento duas vezes.**
Um mata o processo de verdade, em três processos com um checkpointer em arquivo
(`test_processo_morto_de_verdade_fica_em_gravar_e_e_recuperado`), e um confere que a recuperação
não conclui um checkpoint que diz que acabou sem término nem desfecho.

**A durabilidade do checkpoint é `"sync"` (decisão de 17/10/2026).** A conferência do
`simular_queda.py` mostrou que o padrão do LangGraph, `durability="async"`, grava o checkpoint de
cada passo em segundo plano, e que uma queda real leva o último: em três quedas dentro de
`db.abrir_chamado`, o checkpoint ficou duas vezes sem passo seguinte (como se a execução tivesse
acabado, sem nada gravado) e uma vez em `confirmar`. Com `"sync"`, ficou em `gravar` nas três. A
constante `DURABILIDADE` é passada em toda invocação do grafo; a tabela e a justificativa estão
no `grafo.md` §5, como decisão que virou parâmetro.

**Limites.**

- **O que caiu antes da decisão não é retomado.** Uma queda na triagem, na busca ou na redação não
  gravou nada; o caminho é rodar o chamado de novo, que apaga o checkpoint velho. Retomar ali
  chamaria o modelo de novo, e um erro que se repete viraria uma tentativa a cada volta do vigia.
- **A recuperação espera 5 minutos.** Uma queda às 10h00 só termina às 10h05, na primeira volta
  depois disso (ou no primeiro comando).
- **Não foi demonstrado com o modelo real, e o modelo não muda o resultado.** A queda é do
  processo (luz, máquina reiniciada, processo encerrado), e não do modelo: a janela vai do fim de
  uma escrita no banco ao checkpoint seguinte, uma fração de segundo, e acontece depois das
  chamadas ao modelo, com o desfecho já decidido. Rodar com o modelo real só acertaria a janela
  por sorte. Os testes forçam a queda no ponto exato, e o que eles provam (a recuperação e as
  chaves) é código, igual com o modelo real ou com o roteirizado.
- **A queda escolhida pelo script não é espontânea.** Ninguém derruba uma máquina no meio de um
  commit de forma reproduzível; a injeção de falha do `simular_queda.py` (abaixo) faz esse papel.

**A simulação com o processo morto de verdade, sobre o modelo real** (`logs/grafo-queda/`,
17/10/2026, commit `77757ea` sem alterações locais, `ministral-8b-latest`, os prompts em uso). Os
testes levantam uma exceção, e o processo continua vivo; o `simular_queda.py` troca uma função de
`src/db.py` por uma que mata o processo com `os._exit`, sem `finally` e sem liberar nada, e a
recuperação roda depois noutro processo, sobre os arquivos em disco. A J2, a queda entre a
aprovação e a escrita:

| Hora | Comando | O que aconteceu |
|---|---|---|
| 15:55:5x | `main.py TKT-0007 --rodada grafo-queda` | o modelo real fez a triagem, a conferência da ressalva e a redação (3 chamadas); a execução pausou à espera do analista (`TKT-0007-pausado.json`) |
| 15:55:52 | `simular_queda.py cair TKT-0007 --em abrir_chamado` | aprovou, e o processo morreu antes de abrir o chamado (código de saída 70) |
| 15:55:5x | `simular_queda.py estado TKT-0007` | pendência `aprovada`, com a resposta guardada; **nenhum chamado interno**; checkpoint parado em `gravar`. É o estado que até 16/10/2026 ficava preso para sempre |
| 16:01:29 | `vigiar_prazos.py --uma-vez`, sem ninguém aprovar de novo | "EXECUÇÃO RETOMADA DEPOIS DE QUEDA: TKT-0007 \| parou em gravar \| desfecho: abrir_chamado_interno" |
| 16:01:29 | `simular_queda.py estado TKT-0007` | **um chamado interno** (`INC-0005`, P2, Infraestrutura), checkpoint apagado |
| 16:01:34 | `main.py --aprovar TKT-0007` (a aprovação repetida) | "Não há confirmação pendente para TKT-0007."; continua um chamado só |

O log final (`TKT-0007.json`) tem o término `respondeu`, o campo `recuperacao` (`parou_em: gravar`)
e as mesmas 3 chamadas da pausa: nem a retomada nem a recuperação chamaram o modelo. Com o
`"sync"`, o checkpoint ficou em `gravar`, onde a execução caiu. A sequência inteira está em
`saida-terminal.txt`, e a linha do vigia em `vigia.log`. Uma execução, de uma janela (J2).
- **O custo do `"sync"` não foi medido:** é a espera da gravação do checkpoint a cada superpasso.

## 5. Aprovar duas vezes (§8.5)

**O que existe.** A abertura de chamado interno tem chave de idempotência, `ticket:kb_id`,
gravada numa coluna `UNIQUE` (`abrir_chamado`, em `src/db.py`). Repetir a escrita devolve o
chamado que já existe, com `ja_existia: true`, e não cria outro. O teste offline
`test_idempotencia_nao_duplica_chamado` roda o mesmo chamado duas vezes e confere que há um só
registro.

**O que a chave cobre, e o que não cobre.**

- É derivada do conteúdo que identifica a ação (qual chamado, qual procedimento), e não do texto
  do resumo. Se o analista aprovar editando e a aprovação chegar duas vezes, a segunda não
  duplica: a chave é a mesma.
- O encaminhamento (anotação, filas, fila humana depois de rejeição ou prazo vencido) e o aviso
  ao gestor **têm chave no grafo desde 17/10/2026**: execução + chamado + destino, e um aviso por
  pendência (§4.3). Sem a chave, a recuperação depois de uma queda gravava o encaminhamento duas
  vezes (`test_j3_anotacao_gravada_e_queda_a_recuperacao_nao_duplica`).
- **As três barreiras.** (1) A pendência já resolvida (`resolver_pendencia`, atômico) e a trava
  das respostas (§4.1); (2) o checkpoint que não está mais em `confirmar`; (3) a chave derivada do
  conteúdo. A aprovação repetida na mesma pausa é barrada pelas duas primeiras e nem chega à
  escrita, que é o que os logs abaixo mostram. A chave é a barreira para o que chega por outro
  caminho: a mesma gravação refeita depois de uma queda (§4.3) e, no chamado interno, a mesma ação
  aprovada em duas execuções do mesmo chamado.
- O pedido ao cliente, no grafo, **tem**: `db.registrar_pedido_cliente` é idempotente pelo chamado
  (a regra é um pedido por chamado). Repetir a escrita devolve o pedido que já existe, com
  `ja_existia: true`, e não reescreve a mensagem (`test_h2_o_envio_e_idempotente_pelo_chamado`).
  É a segunda barreira: a primeira é a contagem do nó `decidir`, e, na aprovação repetida, o
  grafo já não estar parado em `confirmar` (comando 6 do §2.4).

**A demonstração, com log.** Em `logs/grafo-pausa/` (10/10/2026, commit `083d132`, modelo real,
sem `--auto-aprovar`), o `TKT-0007` pausou no nó `confirmar` e `--aprovar TKT-0007` foi enviado
duas vezes, em dois processos:

| Chamada | Hora | O que aconteceu | O que ficou no banco |
|---|---|---|---|
| 1ª `--aprovar` | 23:52:02 | `Command(resume=...)`; o grafo abriu o `INC-0002` e terminou em `respondeu` (`TKT-0007.json`) | 1 chamado interno para o `TKT-0007`; pendência `aprovada` |
| 2ª `--aprovar` | logo depois | "Não há confirmação pendente para TKT-0007." Nenhum nó rodou | o mesmo: 1 chamado interno, 1 pendência, nenhum encaminhamento |

As duas saídas de terminal e a conferência no banco estão em `saida-terminal.txt`. A segunda
chamada não chega à chave de idempotência: para antes, porque o grafo já não está parado em
`confirmar`. A chave `ticket:kb_id` é a segunda barreira, e é ela que o teste offline abaixo
exercita.

**O caso 6 do enunciado, completo** (`logs/grafo-caso-6/`, 11/10/2026, commit `a328236`, modelo
real, sem `--auto-aprovar`): o grafo pausa, a pessoa aprova editando, e a segunda aprovação não
duplica nada. Cinco comandos, cada um em um processo:

| # | Comando | Hora | O que aconteceu |
|---|---|---|---|
| 1 | `python src/main.py TKT-0007 --rodada grafo-caso-6` | 00:24:51 | parou em `confirmar`: `aguardando_humano`, prazo até 00:44:51, prioridade prevista P2, nada gravado (`TKT-0007-pausado.json`) |
| 2 | `--pendencias` | | 1 ação aguardando, com a ação, a consequência e os comandos de resposta |
| 3 | `--aprovar TKT-0007 --resumo "ok"` | | **edição recusada**: "texto curto demais ou ausente (esperado: pelo menos 20 caracteres)". Código de saída 1, nada gravado, a ação continua aguardando |
| 4 | `--aprovar TKT-0007 --resumo "Site da Eta Engenharia (VPS Pro) não grava arquivos: ..."` | 00:24:57 | **aprovado com edição**: o grafo continuou de `confirmar` e abriu o `INC-0002` (Infraestrutura, P2) com o resumo do analista. As mesmas 2 chamadas ao modelo e 1.770 tokens da pausa (`TKT-0007.json`) |
| 5 | o comando 4, de novo | | "Não há confirmação pendente para TKT-0007." |

Conferência no banco depois do comando 5: **um** chamado interno para o `TKT-0007`, com o resumo
do analista; uma pendência com status `aprovada`; nenhum encaminhamento. No log, a confirmação
traz `editado: true`, o `resumo_original` do modelo e o `resumo_aprovado`. A saída dos cinco
comandos e a conferência estão em `saida-terminal.txt`.

Limite: quem aprovou e escreveu o resumo corrigido foi quem fazia a demonstração, 6 segundos
depois da pausa, e não um analista de suporte.

O teste `test_idempotencia_nao_duplica_chamado` repete a execução inteira. A aprovação repetida
pelo caminho da retomada de hoje está em
`test_aprovacao_dentro_do_prazo_abre_o_chamado_e_conclui`: a segunda chamada de `retomar()` não
encontra pendência e não grava nada. O mesmo vale para rejeitar duas vezes
(`test_rejeicao_dentro_do_prazo_vai_a_fila_humana_com_as_consideracoes_do_agente`): a fila humana
recebe uma linha só, apesar de `registrar_encaminhamento` não ter chave.

## 6. Quem aprovou, e onde fica registrado

Cada resposta a um pedido de confirmação é gravada no log da execução, no campo `confirmacoes`,
com a ação pedida, se foi aprovada, por quem e, na retomada, o status (`aprovada`, `rejeitada` ou
`vencida`) e a hora. A tabela `pendencias` guarda o mesmo, com a hora do pedido e a do prazo. Com `--auto-aprovar`, o registro diz "auto-aprovado". Todos
os logs das rodadas foram gerados assim. A exceção é `logs/grafo-pausa/`, em que a confirmação
veio pelo comando `--aprovar`, de outro processo; quem o rodou foi quem fazia a demonstração, e
não um analista.

## 7. O que falta para este item

- Simular as outras janelas da queda com o processo morto de verdade (J1, J3 e J4): com o
  modelo real só a J2 foi simulada (§4.3); as outras estão nos testes.
- Instalar o vigia como serviço e demonstrar a parada limpa por sinal: a demonstração o encerrou
  com `taskkill /F` (§4.1).
- Exercitar o prazo real de 20 minutos também no H2: o H2 vencido só foi executado com o prazo
  encurtado para 1,2 segundo (`logs/grafo-h2-vencido/`, `grafo.md` §6.7).
- Implementar o H3: a pausa em `aguardando_cliente` e a retomada com a resposta, com o prazo de
  3 dias úteis contado do `enviado_em` do pedido (§2.4).
- Exercitar os outros motivos de rejeição do H2 (`mensagem_ruim`, `outro`) com o modelo real: a
  demonstração de `logs/grafo-h2-rejeicao/` usou `informacao_suficiente`.
- Rever o texto padrão do pedido (`PEDIDO_AO_CLIENTE`) quando a base ganhar guia de um serviço
  novo: nada avisa que a lista ficou velha (`prompts.md` §2.2).
- Separar a aprovação do envio, se um canal de mensagem (um MCP simulado, por exemplo) for
  ligado a `db.registrar_pedido_cliente`: aí a falha de entrega passa a existir e precisa de
  regra no `case.md`.
- Instalar o vigia do prazo como serviço (§4.2) e demonstrá-lo sobrevivendo a um reinício: a
  demonstração de 17/10/2026 o rodou num terminal (§4.1).
- Dar ao gestor um jeito de ver os avisos (hoje é uma tabela sem comando de leitura).
- Levar o motivo da rejeição ao texto do encaminhamento: ele é pedido e vai à memória (§2.1 e
  §2.4), mas a fila humana ainda diz só que o analista rejeitou.
- Mostrar a reincidência, o score e o SLA na tela de confirmação (§2.2). A prioridade prevista e a
  consequência já aparecem.
- Deixar o analista editar o resumo a partir do texto do modelo, e não redigitando tudo (§2.2).
- Demonstrar a chave do chamado interno em log, com o modelo real: o mesmo chamado rodado e
  aprovado duas vezes, e a segunda execução com `ja_existia: true` (§5). Hoje ela é provada só
  pelos testes.
- Resolver o evento de abertura duplicado na entrada (chave do evento): a chave do encaminhamento
  reconhece a gravação refeita, e não duas execuções do mesmo chamado (§4.3).
- Refazer o caso 6 (`logs/grafo-caso-6/`) com um analista de verdade respondendo: a demonstração
  foi feita por quem escreveu o sistema.

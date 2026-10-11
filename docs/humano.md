# Human-in-the-loop (Parte 2, item 8)

> **Estado deste documento: versão de 10/10/2026.** As regras (quem confirma, os prazos, o que
> acontece no silêncio) estão decididas e escritas no [`case.md`](case.md) §2.1. A implementação
> existe nos dois caminhos: no grafo (`src/grafo.py`, o caminho padrão), com `interrupt` e
> checkpointer do LangGraph, e no laço da Parte 1 (`--laco`), com uma retomada feita à mão sobre
> o SQLite. Nos dois a abertura de
> chamado pausa, fica pendente com prazo de 20 minutos, e o analista aprova ou rejeita de outro
> processo. **Só o H1 está implementado, e não há aprovação com edição.** O que falta está no §7.

## 1. Onde o sistema para, e por qual critério (§8.1)

| | Ponto de parada | Critério | Quem é chamado | Situação |
|---|---|---|---|---|
| H1 | antes de abrir um chamado interno | **ação irreversível**: não existe ferramenta para apagar ou encerrar um chamado | analista de suporte | implementado: pausa assíncrona, com prazo e retomada |
| H2 | antes de enviar o pedido de informação ao cliente | **ação irreversível**: a mensagem chega ao cliente e não tem volta | analista de suporte | não implementado: hoje o pedido é só gravado, sem envio e sem confirmação |
| H3 | depois de enviar o pedido, à espera da resposta | falta informação para classificar o chamado | o cliente | não implementado |

Os três estão marcados no desenho do grafo (`grafo.md` §1): H1 e H2 no nó `confirmar`, H3 no nó
`aguardar_cliente`.

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
     pedido_em: <data e hora do pedido>
     vence_em: <20 minutos depois>
     faltam: 20 min
     responder: python src/main.py --aprovar TKT-0007   |   --rejeitar TKT-0007
     rejeitada ou sem resposta no prazo, o chamado vai para a fila humana com esta ação proposta
```

O bloco mostra o formato; os valores são os do `TKT-0007` no seed atual, e não a cópia de uma
execução.

Respostas aceitas: `--aprovar TKT-0007` e `--rejeitar TKT-0007`, dentro do prazo. Aprovar abre
o chamado interno. Rejeitar não o abre, e o chamado vai para a fila humana com as considerações do
agente (§4).

### 2.2 O que falta nessa tela

| Falta | Por que importa |
|---|---|
| **a prioridade** | o analista aprova um chamado sem saber se ele sai P1 ou P2, e é a prioridade que define o SLA. O código já sabe calculá-la antes da gravação (`prioridade_prevista`, em `src/db.py`), mas só a usa quando a ação é rejeitada ou vence; falta mostrá-la na tela |
| **a reincidência** que o sistema confirmou | é o que faz a prioridade subir |
| **o score** do procedimento | é o que sustenta a ação |
| **a consequência**, escrita | "abre um chamado para a Infraestrutura, com SLA de 1 dia útil, que não pode ser apagado". Hoje a pergunta é só "confirma?" |
| **aprovar editando** | não existe. O analista que discorda de uma frase do resumo só pode rejeitar tudo |

### 2.3 Proposta para o grafo

Três respostas: **aprovar**, **rejeitar** e **aprovar editando**. Na edição, o analista altera só
o texto (o resumo do chamado, ou a mensagem ao cliente). Categoria, time e prioridade não são
editáveis: vêm do procedimento, e só o gestor reclassifica (`case.md` §2.1).

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
`tests/test_grafo.py` cobrem aprovar, aprovar duas vezes, rejeitar e prazo vencido; a rejeição e
o prazo vencido não foram executados com o modelo real.

## 4. O que acontece se ninguém responder, ou se a pessoa rejeitar (§8.4)

| Ponto | Prazo | Quando vence |
|---|---|---|
| H1 e H2 (analista) | **20 minutos**, contados do pedido de confirmação | a ação **não é executada**. O chamado vai para a fila humana com as considerações do agente: a ação proposta, a prioridade que o chamado teria, o procedimento e o score que a sustentam, o texto já redigido e o motivo "confirmação não recebida em 20 minutos". Se o chamado interno seria **P1**, o gestor de suporte também é avisado |
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
`src/ferramentas.py`), e o modelo só é chamado depois, para a frase final. H2 e H3 não existem, e
os prazos deles também não.

**O prazo é conferido, não cronometrado.** Não há processo em segundo plano: as pendências
vencidas são encaminhadas no começo do próximo comando do `main.py`. A ação vencida nunca é
executada, mas a fila humana só a recebe quando alguém roda um comando (`arquitetura.md` §7).

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
- `registrar_encaminhamento` **não tem chave**. O único limite é o do pedido ao cliente, contado
  no banco (um por chamado). Uma anotação ou um encaminhamento à fila humana gravado duas vezes
  cria duas linhas.

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
exercita. **Falta** a aprovação com edição, que o caso 6 do enunciado também pede.

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

- Exercitar a rejeição e o prazo vencido do H1 no grafo com o modelo real, e com log (a aprovação
  já está em `logs/grafo-pausa/`).
- Implementar H2 e H3: a confirmação do pedido ao cliente, o envio, a pausa e a retomada com a
  resposta, com o prazo de 20 minutos no H2 e o de 3 dias úteis no H3.
- Aplicar o prazo vencido sem depender de alguém rodar um comando (§4).
- Dar ao gestor um jeito de ver os avisos (hoje é uma tabela sem comando de leitura), e decidir
  se o aviso vale também para o H2.
- Pedir ao analista o **motivo** da rejeição: hoje o encaminhamento diz que ele rejeitou, e não
  por quê.
- Mostrar prioridade, reincidência, score e consequência na tela de confirmação. A prioridade
  prevista já é calculável antes da pausa (`prioridade_prevista`).
- Implementar "aprovar editando".
- Dar chave de idempotência a `registrar_encaminhamento`.
- Completar o caso 6 dos casos demonstrados: a pausa e a segunda aprovação que não duplica nada
  estão em `logs/grafo-pausa/`; falta a pessoa aprovar **editando**.

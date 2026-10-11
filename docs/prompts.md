# Plano de prompt engineering (Parte 2, item 2)

> **Estado deste documento.** Descreve os prompts que existem hoje. O sistema tem **um** ponto de
> chamada ao modelo (o laço em `src/agente.py`) e dois textos de prompt em uso. As etapas que a
> Parte 2 acrescenta (resposta do RAG, extração para a memória) ainda não existem e não têm linha
> aqui. O teste da regra da frase está no §3.

## 1. As etapas em que o modelo é chamado

| Etapa | Arquivo | Técnica | Por que ela | Contrato de saída | Como é testada |
|---|---|---|---|---|---|
| **Triagem do chamado** (prompt de sistema do laço) | `src/prompts/agente-v5.md` | zero-shot com procedimento numerado e tool calling | Sem few-shot, para não usar como exemplo os mesmos casos que servem de teste (`dados/gabarito.json`). Procedimento numerado porque a triagem tem ordem fixa: consultar, classificar, buscar, escolher o desfecho, registrar | Ver §1.1 | 8 casos rotulados em `dados/gabarito.json`, conferidos por `src/verificar.py` contra o que foi gravado no banco. Critério: ≥ 6 de 8 e nenhum chamado interno aberto indevidamente. Resultado medido da v4: 6 de 8 e 5 de 8 em duas execuções iguais, com um chamado indevido em uma delas (§3.2); a v4 revisada deu 6 de 8 sem chamado indevido (`logs/rodada-2-prompt-v4`). **A v5, em uso, ainda não foi medida** |
| **Lembrete de desfecho** (mensagem de usuário, enviada pelo laço só quando o modelo encerra sem registrar desfecho) | `src/prompts/lembrete-v1.md` | instrução direta (zero-shot), sem exemplos | O modelo narrava a ação ("registrei", "encaminhei") sem chamar a ferramenta. A regra no prompt de sistema não bastou nas rodadas 1 e 2 | Uma chamada de ferramenta de escrita (`abrir_chamado_interno` ou `registrar_encaminhamento`). Texto sem chamada conta como falha; depois de 2 lembretes sem efeito, a execução termina como `erro_fatal` | O campo `lembretes` do log conta quantos foram enviados. Nas duas execuções da v4, foi enviado 1 lembrete no `TKT-0002` e 1 no `TKT-0999`, e os dois casos terminaram com o desfecho certo |

As duas linhas pertencem ao mesmo laço: não há uma segunda chamada ao modelo com prompt próprio.

**A entrada da triagem.** A mensagem de usuário é montada pelo código (`_entrada`, em
`src/agente.py`): o id do chamado, o id do cliente e, abaixo, o texto que o cliente escreveu. Um id
que não existe chega sem texto. Como o texto já está na entrada, `consultar_ticket` não o devolve de
novo (alterado em 10/10/2026, **depois** do primeiro teste da frase na v4, §3.6, que foi feito com o
texto repetido no resultado da ferramenta e sem o id do cliente na entrada; o teste do §3.2 já é
com a entrada atual).

### 1.1 O contrato de saída da triagem

O resultado da etapa **não é o texto** que o modelo escreve: é a escrita feita por **uma**
ferramenta.

| | |
|---|---|
| **Formato** | uma chamada de `abrir_chamado_interno` ou de `registrar_encaminhamento`, seguida de uma frase de resumo |
| **Campos de `abrir_chamado_interno`** | `id_ticket`, `resumo` (mínimo de 20 caracteres), `kb_id` (de uma busca feita na mesma execução) |
| **Campos de `registrar_encaminhamento`** | `id_ticket`, `destino`, `mensagem` (mínimo de 10 caracteres), `kb_id` (só para `anotacao_interna`), `motivo` (opcional, só para `fila_humana` sem busca: `fora_da_alcada`) |
| **Valores válidos de `destino`** | `fila_comercial`, `devolver_cliente`, `anotacao_interna`, `fila_humana` |
| **Quem valida** | o código, em `src/ferramentas.py`: schema das ferramentas, portão de confiança (score ≥ 0,5), ação padrão do procedimento, um desfecho por execução, um pedido ao cliente por chamado e sem termo interno, busca antes da fila humana |
| **Proibido** | prometer correção, prazo ou prioridade ao cliente; repetir afirmação do cliente como fato; inventar causa, solução, prazo ou procedimento que não veio de uma ferramenta; afirmar no texto uma ação que não foi feita por ferramenta |

Categoria, time e prioridade do chamado interno não fazem parte do contrato do modelo: são
copiados do procedimento pelo código.

### 1.2 Parâmetros da chamada

- `temperature=0`, porque classificação e escolha de ferramenta pedem o mesmo resultado a cada
  execução. O §3.2 mostra que isso não basta para a saída ser idêntica.
- `tool_choice="auto"`, com os quatro schemas de `src/ferramentas.py`.
- O marcador `{LIMIAR}` do prompt é preenchido pelo código com `LIMIAR_CONFIANCA` (0,5), para o
  limiar ter uma fonte só.

## 2. Os prompts em arquivo

Os prompts ficam em `src/prompts/`, junto do código que os carrega (`_ler_prompt` e
`carregar_prompt`, em `src/agente.py`). Cada arquivo começa com um bloco de comentário
(`<!-- -->`) com versão, técnica, contrato e o que cada regra impede; o código descarta esse bloco
antes de enviar o texto ao modelo.

| Arquivo | Situação | Resultado registrado |
|---|---|---|
| `agente-v1.md` | histórico | 5 de 7 (rodada 1) |
| `agente-v2.md` | histórico | 3 de 7 (rodada 2): acrescentou 4 regras e piorou |
| `agente-v3.md` | histórico | 6 de 7 (rodada 3, com o lembrete no laço); 6 de 8 (rodada 4) |
| `agente-v4.md` | histórico; revisada em 10/10/2026 no mesmo arquivo (ver abaixo) | texto anterior à revisão: 6 de 8 e 5 de 8 (primeiro teste da frase, §3.6, sem log) e 5 de 8 (`logs/rodada-1-prompt-v4`). Texto revisado: 6 de 8, sem chamado indevido (`logs/rodada-2-prompt-v4`) |
| `agente-v5.md` | **em uso** | 7 de 8, 6 de 8 e 7 de 8 (`logs/rodada-1-prompt-v5` a `logs/rodada-3-prompt-v5`); 7 de 8 e 7 de 8 no teste do §3 |
| `agente-v5-sem-frase.md` | variante do teste do §3; não é usada pelo sistema | 7 de 8 e 8 de 8 (§3.2) |
| `agente-v4-sem-frase.md` | variante dos testes anteriores, na v4 (§3.6); não é usada pelo sistema | 4 de 8 e 5 de 8, sem log; 6 de 8 e 6 de 8 na repetição |
| `agente-v4-com-frase.md` | o par da variante na repetição do teste na v4 (§3.6): texto da v4 anterior à revisão, do commit `b16fd9b`; não é usada pelo sistema | 6 de 8 e 6 de 8 |
| `lembrete-v1.md` | **em uso** | ver a linha do lembrete no §1 |

Todos os resultados são de `ministral-8b-latest` com `temperature=0`.

**O que mudou da v3 para a v4.** A entrada deixou de ser só o id e passou a ser o conteúdo do
chamado. Duas frases mudaram: a abertura ("Você recebe o conteúdo de um chamado ... acompanhado do
ID do chamado") e o passo 1 (`consultar_ticket` fica para o log anexado, o plano e o histórico). O
resto do texto é o da v3.

**Os resultados da v3 e da v4 não são comparáveis diretamente.** Entre as duas medições mudaram
também o seed (`TKT-0002` e `TKT-0007`), a ferramenta `abrir_chamado_interno` (sem o argumento
`categoria`) e a mensagem de entrada (agora com o texto do chamado).

**Revisão da v4 em 10/10/2026, sem gerar v5.** A rodada `logs/rodada-1-prompt-v4` deu 5 de 8: o
`TKT-0003` foi à fila humana sem buscar na base, o `TKT-0005` buscou e foi à fila humana em vez de
voltar ao cliente, e o `TKT-0007` teve score 0,25. O `agente-v4.md` foi alterado no próprio arquivo;
o texto anterior, que é o dos testes da frase na v4 (§3.6), está no git (commit `b16fd9b`). O que mudou:

- **passo 2:** a classificação é feita antes de qualquer busca e ganhou a classe "fora da alçada"
  (o cliente pede apenas para encerrar um chamado ou mudar a prioridade);
- **passo 3:** a busca fica só para o assunto técnico;
- **passo 4:** o pedido ao cliente traz só a lista do que falta, sem informação interna nem
  promessa; desfecho novo para "fora da alçada" (`fila_humana` com `motivo` `fora_da_alcada`);
- **regras:** afirmação do cliente que o histórico não confirma não é divergência nem motivo de fila
  humana, e o resumo cita o chamado anterior.

O código acompanha, em `src/ferramentas.py`: `fila_humana` sem nenhuma busca é recusada para um
chamado que existe, salvo o motivo `fora_da_alcada`; o pedido ao cliente que cita termo interno
(artigo, chamado interno, time, fila, score, prioridade, SLA) é recusado; e a busca sem resultado
lembra que relato sem serviço nem sintoma volta ao cliente. São erros recuperáveis, devolvidos ao
modelo como dado. Limite: a revisão foi escrita depois de ver as falhas nestes mesmos 8 casos, e o
`TKT-0007` não foi tratado (a causa é a busca por palavra).

**O que mudou da v4 revisada para a v5 (10/10/2026).** A rodada `logs/rodada-2-prompt-v4` deu 6 de
8, sem chamado indevido. Falharam o `TKT-0007` (score 0,18 e 0,4 em duas buscas) e o `TKT-0003`: a
busca obrigatória funcionou, mas o modelo buscou com frases, não achou nada e seguiu a sugestão que o
resultado vazio trazia, devolvendo o chamado ao cliente. Essa sugestão foi retirada do código. No
prompt mudaram três frases:

- **passo 3:** "palavras soltas que nomeiem o serviço e o sintoma, não frases";
- **passo 4, divergência:** "o relato do cliente CONTRADIZ o anexo_log" virou "o anexo_log aponta
  OUTRO serviço ou outra causa, diferente do que o cliente relata", como no `docs/case.md` §2.12;
- **passo 4, fila humana:** o artigo pode vir com "ressalva", e a mensagem deve dizer isso.

A maior parte da mudança está na busca (`buscar_kb`, em `src/db.py`), não no prompt:

- frases são quebradas em palavras, e palavras de ligação saem;
- sinônimos conhecidos viram a palavra-chave ("encheu" virava "cheio"; desde a troca da categoria do
  KB-102, "salvar" vira "gravar"); a lista é curta e foi escrita
  depois de ver o `TKT-0007` falhar;
- o score passou a ser `casados / (casados + não casados / 2)`: mede quanto da consulta o artigo
  explica e não depende do tamanho da lista de palavras-chave. Com um só termo casado, é reduzido
  para no máximo 0,4;
- cada procedimento pode declarar o que **não** cobre (coluna `nao_cobre` de `kb_artigos`). O KB-104
  declara a falha intermitente; a ressalva é procurada no texto do cliente, o score é reduzido e o
  artigo volta com o campo `ressalva`. É o que substitui o empate em 0,5 do `TKT-0006`.

Com os termos reais das rodadas 1 e 2, a busca nova dá 0,67 a 1,0 para o `TKT-0007`, 0,8 para o
`TKT-0003` e 0,16 a 0,4 para o `TKT-0006` (testes em `tests/test_offline.py`). Dois riscos: o score
ficou mais generoso, e no `TKT-0002` o KB-106 chega a 0,5 com os termos da rodada 2 (antes, 0,25),
de modo que só o prompt impede agir sobre o log; e os scores deixam de ser comparáveis com os das
rodadas anteriores.

**Troca da categoria do KB-102 (10/10/2026).** "Disco cheio" saiu da base simulada e o KB-102
passou a ser "Permissão negada ao gravar arquivos" (`docs/case.md` §2.12). O `TKT-0003` e o
`TKT-0007` foram reescritos no seed, e no passo 2 do `agente-v5.md` "disco" virou "permissão de
arquivos", no mesmo arquivo. As medições da v1 à v4 no §2 e o primeiro teste da frase na v4
(§3.6) são anteriores à troca e falam de disco cheio. Com o seed novo foram executados a
`logs/rodada-3-prompt-v5` e os testes do §3.2 e da repetição do §3.6.

**Mudanças de 10/10/2026 nos arquivos.** Os arquivos `agente-v*.md` foram movidos de `prompts/`
para `src/prompts/` com `git mv`. O texto do lembrete saiu da constante `LEMBRETE` de
`src/agente.py` e foi para `lembrete-v1.md`, sem alteração de conteúdo.

**O que cada execução registra.** O log (`logs/.../TKT-xxxx.json`) grava `modelo`, `prompt` (nome
do arquivo do prompt de sistema), `prompt_lembrete` (nome do arquivo do lembrete) e `temperatura`.

**Como rodar com outro prompt.** `python src/main.py --todos --auto-aprovar --rodada NOME --prompt
ARQUIVO` usa um arquivo de `src/prompts/` e grava em `logs/NOME/`, sem sobrescrever os logs de
`logs/`.

**O que cada regra impede.** A lista está no cabeçalho de cada arquivo, regra por regra, e não é
repetida aqui para não ter duas fontes.

## 3. A regra da frase

> Se vocês apagarem uma frase do prompt e não souberem dizer o que ela impedia, ela não estava
> fazendo nada.

O teste foi feito no `agente-v5.md`, o prompt em uso. Os dois testes anteriores, no texto antigo da
v4, estão resumidos no §3.6.

### 3.1 A frase que saiu

Do passo 5 do `agente-v5.md`, a segunda metade:

> 5. Todo chamado termina com uma chamada de ferramenta de escrita~~, inclusive quando o problema é
> o próprio chamado: se consultar_ticket disser que o id não existe, chame registrar_encaminhamento
> com destino "fila_humana" e explique na mensagem que o id não existe.~~

**O que ela devia impedir**, segundo o cabeçalho do prompt: o caso `TKT-0999`, em que o modelo
recebia o erro de id inexistente e encerrava sem registrar desfecho.

**Por que era candidata a não fazer nada.** Duas outras peças já cobrem o mesmo caso: o erro de
`consultar_ticket` devolve a sugestão "chame registrar_encaminhamento com destino 'fila_humana' e
explique na mensagem que o id não existe" (`src/ferramentas.py`), e o lembrete do laço avisa quando
o modelo encerra sem desfecho.

**Critério, definido antes de rodar** (o mesmo dos testes anteriores). A frase fica de fora se, sem
ela, os 8 desfechos forem iguais aos da v5 e o `TKT-0999` não precisar de mais lembretes. Caso
contrário, ela volta.

**As duas versões.**

- **Com a frase:** `agente-v5.md`, sem alteração.
- **Sem a frase:** `agente-v5-sem-frase.md`, criado para o teste. Os dois arquivos diferem só na
  segunda metade do passo 5 (conferido com `diff`, descontado o cabeçalho).

### 3.2 O que aconteceu

Quatro execuções dos 8 casos em 10/10/2026, entre 21:53:31 e 21:55:30, `ministral-8b-latest`,
`temperature=0`, banco recriado antes de cada caso, aprovação automática. Código do commit `2ffb2b5`
mais as alterações locais desta data. Logs em `logs/regra-da-frase/`.

```bash
python src/main.py --todos --auto-aprovar --rodada regra-da-frase/v5-a --prompt agente-v5.md
python src/main.py --todos --auto-aprovar --rodada regra-da-frase/v5-b --prompt agente-v5.md
python src/main.py --todos --auto-aprovar --rodada regra-da-frase/v5-sem-frase --prompt agente-v5-sem-frase.md
python src/main.py --todos --auto-aprovar --rodada regra-da-frase/v5-sem-frase-b --prompt agente-v5-sem-frase.md
```

| Caso | v5 (execução a) | v5 (execução b) | sem a frase (a) | sem a frase (b) |
|---|---|---|---|---|
| `TKT-0001` simples | OK | OK | OK | OK |
| `TKT-0002` divergência | **falhou: abriu chamado** | **falhou: abriu chamado**, 1 lembrete | OK | OK |
| `TKT-0003` reincidência | OK | OK | OK, 1 lembrete | OK |
| `TKT-0999` id inexistente | OK, 1 lembrete | OK, 1 lembrete | OK | OK |
| `TKT-0004` comercial | OK | OK | OK | OK |
| `TKT-0005` informação insuficiente | OK | OK | falhou (fila humana) | OK, 1 lembrete |
| `TKT-0006` correspondência parcial | OK | OK | OK | OK, 1 lembrete |
| `TKT-0007` escalonamento simples | OK | OK | OK | OK |
| **Acertos** | **7 de 8** | **7 de 8** | **7 de 8** | **8 de 8** |
| Lembretes (8 casos) | 1 | 2 | 1 | 2 |
| Tokens do `TKT-0999` | 8.294 | 8.309 | 5.962 | 5.939 |
| Chamadas ao modelo no `TKT-0999` | 4 | 4 | 3 | 3 |
| Tokens (8 casos) | 69.521 | 72.439 | 75.303 | 67.256 |
| Chamadas ao modelo (8 casos) | 31 | 32 | 34 | 31 |
| Custo (8 casos) | US$ 0,0104 | US$ 0,0109 | US$ 0,0113 | US$ 0,0101 |
| Pasta do log | `v5-a` | `v5-b` | `v5-sem-frase` | `v5-sem-frase-b` |

O que os logs mostram:

- **No caso para o qual a frase foi escrita, ela não ajudou.** O `TKT-0999` terminou certo nas
  quatro execuções. Com a frase, o modelo gravou a fila humana e ainda precisou de 1 lembrete nas
  duas vezes (4 chamadas ao modelo, cerca de 8,3 mil tokens); sem ela, não houve lembrete (3
  chamadas, cerca de 5,9 mil tokens).
- **Sem a frase, o `TKT-0002` passou nas duas execuções; com ela, falhou nas duas**, e pelo lado
  que não é seguro: chamado interno P1 aberto pelo KB-106 (score 0,5 e 0,57), quando o esperado é a
  fila humana. A diferença está na ordem das chamadas. Com a frase, o modelo tentou gravar a fila
  humana logo depois de consultar o chamado, com a divergência escrita na mensagem; a ferramenta
  recusou por faltar a busca; ele então buscou com termos do relato e do log juntos ("webmail fora
  do ar", "dns falha", "resolucao dns") e, com o artigo no limiar, abriu o chamado. Sem a frase, ele
  buscou primeiro, com palavras do relato ("webmail", "fora", "ar"), o score ficou em 0,2 e 0,27, e
  a fila humana foi gravada com a divergência. A frase retirada não fala de busca nem de
  divergência, então o efeito é indireto e não temos explicação para ele.
- **Sem a frase, o `TKT-0005` falhou em uma de duas execuções**: o modelo buscou duas vezes sem
  resultado ("servidor", "nao", "funcionando") e foi à fila humana em vez de voltar ao cliente. Na
  outra execução sem a frase, e nas duas com ela, devolveu ao cliente sem buscar.
- **Não houve economia no total.** Sem a frase: 75,3 e 67,3 mil tokens. Com ela: 69,5 e 72,4 mil.
  O que se ganhou no `TKT-0999` foi gasto em lembretes e buscas de outros casos, e a diferença
  entre duas execuções iguais (8 mil tokens sem a frase) é maior que a diferença entre as versões.

### 3.3 Se ela voltou

**Pelo critério, voltou**, mas o teste não a defende. O critério pedia os 8 desfechos iguais, e
eles não foram: o `TKT-0002` mudou nas duas execuções e o `TKT-0005` em uma. A frase continua no
`agente-v5.md`, que não foi alterado, e o `agente-v5-sem-frase.md` fica no repositório como registro
do teste.

O critério foi escrito supondo que mudar um desfecho seria piorar. Aqui a mudança que se repetiu foi
para melhor: sem a frase, o chamado indevido do `TKT-0002` deixou de ser aberto, e esse é o erro
mais grave que o prompt em uso comete hoje (`docs/case.md` §2.7, critério 2). Do outro lado há uma
falha em duas execuções no `TKT-0005`, que manda o chamado a uma pessoa e não grava nada indevido.

**Tirar a frase do prompt em uso é decisão do grupo e não foi tomada.** Seria uma versão nova do
prompt (`agente-v6.md`), medida em rodada própria. O que este teste sustenta: a frase não faz o que
o cabeçalho dizia, e a presença dela muda o comportamento em um caso que ela não menciona.

### 3.4 Limites do teste

- **Duas execuções por versão, 8 casos.** É pouco. As duas execuções sem a frase diferem entre si
  em um caso (`TKT-0005`), mesmo com `temperature=0`. Uma diferença de um caso em uma execução está
  dentro desse ruído; a do `TKT-0002` se repetiu nas duas execuções de cada lado, e por isso foi
  tratada como efeito. Com a v5 completa esse caso também já passou: na `logs/rodada-2-prompt-v5`
  foi à fila humana, com o texto e o seed anteriores à revisão.
- **O verificador confere o desfecho gravado**, não o texto das mensagens.
- **Aprovação automática.** O chamado indevido do `TKT-0002` foi gravado porque ninguém o recusou.
- **Os casos são os mesmos 8** que serviram para escrever a v5 e a busca.

### 3.5 O que o teste revelou além da frase

**A recusa da fila humana sem busca empurra o `TKT-0002` para o chamado indevido.** Nas duas
execuções com a v5 completa, e na `logs/rodada-3-prompt-v5`, o modelo identificou a divergência
logo depois de consultar o chamado e tentou a fila humana. A ferramenta recusou ("fila_humana sem
nenhuma busca na base para este chamado"), o modelo buscou com os termos do log, e o artigo
recuperado passou a valer mais do que a divergência que ele mesmo tinha escrito. A recusa existe
por causa do `TKT-0003` (§2) e funciona para ele; no `TKT-0002` ela desfaz uma decisão certa. Não
foi alterada: mexer nela é mudança de regra do código, não de prompt.

### 3.6 Os testes anteriores, na v4

A mesma frase foi testada duas vezes no texto da v4 anterior à revisão (commit `b16fd9b`), antes
deste teste. Ficam aqui como histórico; as conclusões acima são as do teste na v5.

| Teste | Com a frase | Sem a frase | Logs |
|---|---|---|---|
| Primeiro, 10/10/2026, código do commit `40185cb` | 6 de 8 e 5 de 8 | 4 de 8 e 5 de 8 | **não foram guardados** |
| Repetição, 10/10/2026, 21h32, código atual | 6 de 8 e 6 de 8 | 6 de 8 e 6 de 8 | `logs/regra-da-frase/v4-a`, `v4-b`, `v4-sem-frase`, `v4-sem-frase-b` |

- **Primeiro teste.** Sem a frase, o `TKT-0007` falhou nas duas execuções (buscou com frases e o
  score ficou abaixo do limiar), e por isso a frase voltou. Os números estão aqui sem evidência: a
  pasta de logs estava vazia e nunca entrou no git.
- **Repetição.** Feita para a pasta existir, com o `agente-v4-com-frase.md` (o texto da v4 do
  commit `b16fd9b`, porque o `agente-v4.md` foi revisado depois) e o `agente-v4-sem-frase.md`. Os 8
  desfechos foram iguais nas quatro execuções, e o efeito sobre o `TKT-0007` não se repetiu: entre
  os dois testes mudaram o seed e a busca. Falharam, dos dois lados, o `TKT-0002` (chamado P1
  indevido pelo KB-106, score 0,67) e o `TKT-0005` (fila humana).
- **O que se repete nos três testes:** no `TKT-0999`, o modelo precisa de 1 lembrete com a frase e
  de nenhum sem ela.

## 4. O que falta para este item

- Decidir se a frase do passo 5 sai do prompt em uso (§3.3). Se sair, é um `agente-v6.md`, medido
  em rodada própria.
- Decidir o que fazer com a recusa da fila humana sem busca, que leva o `TKT-0002` ao chamado
  indevido (§3.5).
- Acrescentar uma linha no §1 para cada etapa nova da Parte 2 que chamar o modelo. As duas
  etapas já existem no grafo (`src/grafo.py`): `triagem`, com o prompt `triagem-v1.md`, e
  `redigir`, com o `redigir-v1.md`. Os dois arquivos têm o cabeçalho de costume e estão marcados
  "AINDA NÃO MEDIDO": nenhuma execução do grafo foi feita com o modelo real.
- Atualizar os documentos que ainda citam o `agente-v3.md` como o prompt em uso (`docs/case.md`
  §2.11, `docs/arquitetura-v2.md` §4, `docs/memoria.md` §1.1 e §1.2).

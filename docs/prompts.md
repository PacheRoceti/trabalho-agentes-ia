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
novo (alterado em 10/10/2026, **depois** das medições do §3.2, que foram feitas com o texto repetido
no resultado da ferramenta e sem o id do cliente na entrada).

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
| `agente-v4.md` | histórico; revisada em 10/10/2026 no mesmo arquivo (ver abaixo) | texto anterior à revisão: 6 de 8 e 5 de 8 (§3.2) e 5 de 8 (`logs/rodada-1-prompt-v4`). Texto revisado: 6 de 8, sem chamado indevido (`logs/rodada-2-prompt-v4`) |
| `agente-v5.md` | **em uso** | ainda não medido |
| `agente-v4-sem-frase.md` | variante do teste do §3; não é usada pelo sistema | 4 de 8 e 5 de 8 (§3.2) |
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
o texto anterior, que é o das medições do §3, está no git (commit `b16fd9b`). O que mudou:

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
- sinônimos conhecidos viram a palavra-chave ("encheu" vira "cheio"); a lista é curta e foi escrita
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

### 3.1 A frase que saiu

Do passo 5 do `agente-v4.md`, a segunda metade:

> 5. Todo chamado termina com uma chamada de ferramenta de escrita~~, inclusive quando o problema é
> o próprio chamado: se consultar_ticket disser que o id não existe, chame registrar_encaminhamento
> com destino "fila_humana" e explique na mensagem que o id não existe.~~

**O que ela devia impedir**, segundo o cabeçalho do prompt: o caso `TKT-0999`, em que o modelo
recebia o erro de id inexistente e encerrava sem registrar desfecho.

**Por que era candidata a não fazer nada.** Duas outras peças já cobrem o mesmo caso: o erro de
`consultar_ticket` devolve a sugestão "chame registrar_encaminhamento com destino 'fila_humana' e
explique na mensagem que o id não existe" (`src/ferramentas.py`), e o lembrete do laço avisa quando
o modelo encerra sem desfecho.

**Critério, definido antes de rodar.** A frase fica de fora se, sem ela, os 8 desfechos forem
iguais aos da v4 e o `TKT-0999` não precisar de mais lembretes. Caso contrário, ela volta.

### 3.2 O que aconteceu

Quatro execuções dos 8 casos em 10/10/2026, `ministral-8b-latest`, `temperature=0`, banco recriado
antes de cada caso, aprovação automática. Código do commit `40185cb` mais as alterações desta data,
ainda não commitadas. Logs em `logs/regra-da-frase/`.

| Caso | v4 (execução a) | v4 (execução b) | sem a frase (a) | sem a frase (b) |
|---|---|---|---|---|
| `TKT-0001` simples | OK | OK | OK | OK |
| `TKT-0002` divergência | OK, 1 lembrete | OK, 1 lembrete | OK | OK |
| `TKT-0003` reincidência | falhou (fila humana) | falhou (fila humana) | falhou (fila humana) | OK |
| `TKT-0999` id inexistente | OK, 1 lembrete | OK, 1 lembrete | OK | OK |
| `TKT-0004` comercial | OK | OK | OK | OK |
| `TKT-0005` informação insuficiente | falhou (fila humana) | falhou (fila humana) | falhou (fila humana) | falhou (fila humana) |
| `TKT-0006` correspondência parcial | OK | **falhou: abriu chamado** | **falhou: abriu chamado** | **falhou: abriu chamado** |
| `TKT-0007` escalonamento simples | OK | OK | falhou (fila humana) | falhou (fila humana) |
| **Acertos** | **6 de 8** | **5 de 8** | **4 de 8** | **5 de 8** |
| Tokens (8 casos) | 57.466 | 57.644 | 58.359 | 58.282 |
| Pasta do log | `v4-a` | `v4-b` | `v4-sem-frase` | `v4-sem-frase-b` |

O que os logs mostram:

- **No caso para o qual a frase foi escrita, ela não ajudou.** O `TKT-0999` terminou certo nas
  quatro execuções. Com a frase, o modelo precisou de 1 lembrete nas duas vezes (6.735 e 6.742
  tokens); sem ela, registrou o desfecho direto, sem lembrete (4.756 tokens nas duas vezes). O
  mesmo aconteceu no `TKT-0002`.
- **Sem a frase, o `TKT-0007` falhou nas duas execuções**, e com ela passou nas duas. A diferença
  está nos termos de busca: com a frase, o modelo buscou com palavras ("servidor", "disco",
  "cheio") e abriu o chamado; sem ela, buscou com frases ("disco cheio", "gravar arquivos"), o score
  ficou abaixo do limiar e o chamado foi à fila humana. A frase retirada não fala de busca, então o
  efeito é indireto e não temos explicação para ele.
- **Sem a frase, o `TKT-0006` abriu chamado indevido nas duas execuções**; com ela, em uma de duas.
- **Não houve economia.** O total de tokens dos 8 casos ficou praticamente igual (cerca de 58 mil
  sem a frase, 57,5 mil com ela): o que se ganhou no `TKT-0999` e no `TKT-0002` foi gasto em outros
  casos.

### 3.3 Se ela voltou

**Voltou.** O critério não foi cumprido: sem a frase, o `TKT-0007` mudou de desfecho nas duas
execuções. A frase continua no `agente-v4.md`, e o `agente-v4-sem-frase.md` fica no repositório só
como registro do teste.

O que o teste ensinou é diferente do que se esperava: a frase não faz o que o cabeçalho dizia (o
`TKT-0999` funciona sem ela, e melhor), mas tirá-la mudou o comportamento do modelo em outro lugar
do prompt. Num modelo deste tamanho, uma frase não age só sobre o caso para o qual foi escrita.

### 3.4 Limites do teste

- **Duas execuções por versão, 8 casos.** É pouco. Duas execuções iguais da v4 já diferem entre si
  em um caso (`TKT-0006`), e as duas sem a frase também (`TKT-0003`), mesmo com `temperature=0`.
  Uma diferença de um caso entre versões está dentro desse ruído; a do `TKT-0007` se repetiu nas
  duas execuções de cada lado, e por isso foi tratada como efeito.
- **O verificador confere o desfecho gravado**, não o texto das mensagens.
- **Aprovação automática.** O chamado indevido do `TKT-0006` foi gravado porque ninguém o recusou.

### 3.5 Dois problemas da v4 que o teste revelou

Não são efeito da frase testada: aparecem também nas execuções com o prompt completo.

1. **Chamado interno aberto indevidamente no `TKT-0006`**, em 3 das 4 execuções (1 das 2 da v4). O
   modelo buscou com "erro", "502" e "deploy"; "erro" é descartada como palavra genérica, e as duas
   restantes dão score exatamente 0,5 contra o KB-104, que passa pelo portão. É o empate no limiar
   já registrado em `docs/modelos.md` §3.3-B. Viola o critério 2 do `docs/case.md` §2.7.
2. **O `TKT-0005` foi à fila humana nas 4 execuções**, em vez de voltar ao cliente. O modelo buscou
   na base com "servidor", "nao", "funcionando" e, sem resultado, escolheu a fila humana. Com a v3
   (rodada 4) esse caso passava. A causa não foi isolada: entre as duas medições mudaram o prompt,
   a mensagem de entrada, o seed e a ferramenta.

## 4. O que falta para este item

- Decidir o que fazer com os dois problemas do §3.5 antes de tratar a v4 como versão final.
- Acrescentar uma linha no §1 para cada etapa nova da Parte 2 que chamar o modelo.
- Atualizar os documentos que ainda citam o `agente-v3.md` como o prompt em uso (`docs/case.md`
  §2.11, `docs/arquitetura-v2.md` §4, `docs/memoria.md` §1.1 e §1.2).

# Plano de prompt engineering (Parte 2, item 2)

> **Estado deste documento.** Descreve os prompts que existem hoje (12/10/2026). O grafo, que é
> o caminho padrão, chama o modelo em **três** nós (`triagem`, `conferir_ressalva` e `redigir`),
> cada um com o seu prompt. O laço da Parte 1 (`--laco`) tem um ponto de chamada e dois textos (o
> prompt de sistema e o lembrete). **Não há etapa de resposta do RAG nem de extração para a
> memória**, e por isso elas não têm linha aqui: o guia recuperado vai ao `redigir`, que já tem a
> sua; o episódio é escrito pelo código e o fato do cliente por uma pessoa, sem modelo
> (`memoria.md` §1.4). O teste da regra da frase está no §3 e foi feito no prompt do laço.

## 1. As etapas em que o modelo é chamado

| Etapa | Arquivo | Técnica | Por que ela | Contrato de saída | Como é testada |
|---|---|---|---|---|---|
| **Triagem do chamado** (prompt de sistema do laço) | `src/prompts/agente-v5.md` | zero-shot com procedimento numerado e tool calling | Sem few-shot, para não usar como exemplo os mesmos casos que servem de teste (`dados/gabarito.json`). Procedimento numerado porque a triagem tem ordem fixa: consultar, classificar, buscar, escolher o desfecho, registrar | Ver §1.1 | 8 casos rotulados em `dados/gabarito.json`, conferidos por `src/verificar.py` contra o que foi gravado no banco. Critério: ≥ 6 de 8 e nenhum chamado interno aberto indevidamente. Resultado medido da v4: 6 de 8 e 5 de 8 em duas execuções iguais, com um chamado indevido em uma delas (§3.2); a v4 revisada deu 6 de 8 sem chamado indevido (`logs/rodada-2-prompt-v4`). A v5 deu 7, 6 e 7 de 8 em três rodadas, com um chamado indevido na terceira (`TKT-0002`), e 7 e 7 de 8 no teste do §3 |
| **Lembrete de desfecho** (mensagem de usuário, enviada pelo laço só quando o modelo encerra sem registrar desfecho) | `src/prompts/lembrete-v1.md` | instrução direta (zero-shot), sem exemplos | O modelo narrava a ação ("registrei", "encaminhei") sem chamar a ferramenta. A regra no prompt de sistema não bastou nas rodadas 1 e 2 | Uma chamada de ferramenta de escrita (`abrir_chamado_interno` ou `registrar_encaminhamento`). Texto sem chamada conta como falha; depois de 2 lembretes sem efeito, a execução termina como `erro_fatal` | O campo `lembretes` do log conta quantos foram enviados. Nas duas execuções da v4, foi enviado 1 lembrete no `TKT-0002` e 1 no `TKT-0999`, e os dois casos terminaram com o desfecho certo |
| **Triagem, no grafo** (nó `triagem`) | `src/prompts/triagem-v1.md` | zero-shot, classificação com saída estruturada (JSON), sem ferramentas | A classe é a decisão que só o modelo toma (texto livre). Saída estruturada porque ela vira a rota do grafo: no laço a classe ficava só nas mensagens. Sem few-shot pela mesma razão da linha acima | JSON validado pela classe `Triagem` (`src/grafo.py`): `classe` ∈ {`tecnico`, `comercial`, `insuficiente`, `fora_da_alcada`}; `log_aponta_outro_servico` booleano; `termos_busca` com 2 a 5 itens só na classe técnica; `justificativa` em uma frase. Proibido: escolher o desfecho. Saída fora do contrato volta ao modelo uma vez; na segunda, `erro_fatal` | Os mesmos 8 casos e o mesmo verificador. Três execuções medidas, 8 de 8 nas três (`logs/grafo/`, `logs/grafo-rodada-2/`, `logs/grafo-rodada-3/`, 10/10/2026; `grafo.md` §6), com a mesma classe para cada caso nas três. A classe de cada caso está no passo `triagem` do log. 75 testes offline (`tests/test_grafo.py`) provam o que é do código, não a classificação |
| **Ressalva, no grafo** (nó `conferir_ressalva`) | `src/prompts/ressalva-v3.md` (o v1 mais a regra dos fatos do cliente, `memoria.md` §4.3) | zero-shot, classificação binária com saída estruturada (JSON), sem ferramentas | O embedding não separa o relato que cai numa exceção do guia ("o erro 502 vai e vem") do relato que o guia cobre; o que o vetor não lê, o modelo lê. O código só baixa o score, e só com uma frase da lista do guia | JSON validado pela classe `Ressalva`: `cai_na_ressalva` booleano, `frase` (uma da lista do guia, copiada igual) e `motivo`. Proibido: criar uma exceção que o guia não declara (conferido em código) e subir o score. Saída fora do contrato volta ao modelo uma vez; na segunda, `erro_fatal` | Perguntas de exceção e controles × 3 repetições, em `src/medir_rag.py ressalva [prompt]`; os 8 casos pelo grafo (`logs/grafo-ressalva/`). Resultado em `rag.md` §4.2, que também compara o `ressalva-v2.md`: melhora o nó isolado no KB-102, não melhora o sistema inteiro e barrou um controle, e por isso **não foi adotado**. Testes offline (`tests/test_grafo.py`) provam o que é do código: o modelo só baixa o score, e só com uma frase do guia |
| **Redação, no grafo** (nó `redigir`). **Não roda no pedido ao cliente**, que é texto padrão do código desde 12/10/2026 (§2.2) | `src/prompts/redigir-v3.md` (o v2 sem a regra do pedido ao cliente, que ficou sem uso; §2.1 a §2.3) | zero-shot, geração de texto com saída estruturada (JSON), sem ferramentas | O desfecho chega decidido pelo código; ao modelo resta escrever o resumo ou a mensagem. Separar a redação impede que ele troque a ação ao redigir | JSON validado pela classe `Redacao`: um campo, `texto`. Proibido: informação interna no pedido ao cliente (conferido pelo nó `validar`), causa, solução ou prazo que não vieram no que ele recebeu. Reprovado, volta uma vez com o erro; na segunda, `erro_fatal` | O nó `validar` confere tamanho mínimo e termos internos a cada execução. Com o v3, três execuções dos 8 casos: 8 de 8 no verificador e nenhuma redação reprovada, em 21 (`logs/grafo-redigir-v3-1/` a `-3/`, 12/10/2026). **O conteúdo do texto não tem verificador.** Foi isso que escondeu o defeito do v1: a mensagem ao cliente do `TKT-0005` não perguntava nada, e o caso passava (§2.1) |

As duas primeiras linhas pertencem ao laço (`--laco`), e as três últimas ao grafo, que é o
caminho padrão.

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
| `lembrete-v1.md` | **em uso** (laço) | ver a linha do lembrete no §1 |
| `triagem-v1.md` | **em uso** (grafo) | 8 de 8 nas três rodadas de 10/10/2026 e na de 11/10/2026 (`logs/grafo-fatos/`) |
| `ressalva-v1.md` | histórico: foi o prompt do nó até 11/10/2026 | exceções 24 de 39, controles 42 de 42 (`rag.md` §4.2). Com um fato do cliente, barra todos os controles (`memoria.md` §4.3) |
| `ressalva-v2.md` | medido e **não adotado** | melhora o nó isolado no KB-102, não melhora o sistema inteiro e barrou um controle (`rag.md` §4.2) |
| `ressalva-v3.md` | **em uso** (grafo) | sem fatos, igual ao v1; com o fato `acesso=ssh`, exceções 21 de 21 e controles 18 de 21 (`memoria.md` §4.3) |
| `redigir-v1.md` | histórico: foi o prompt do nó até 12/10/2026 | nenhuma redação reprovada pelo nó `validar`; a mensagem ao cliente não pergunta nada em 15 execuções de 15 (§2.1) |
| `redigir-v2.md` | histórico: foi o prompt do nó por algumas horas de 12/10/2026 | 8 de 8 em três rodadas; a mensagem ao cliente faz as três perguntas nas três (§2.1). Foi a medição dele que levou o pedido a virar texto padrão (§2.2) |
| `redigir-v3.md` | **em uso** (grafo), para quatro dos cinco desfechos | 8 de 8 em três rodadas, com 119 tokens de entrada a menos por redação (§2.3) |

Todos os resultados são de `ministral-8b-latest` com `temperature=0`. Os prompts do laço são
carregados por `src/agente.py` (`PROMPT_ARQUIVO`, `LEMBRETE_ARQUIVO`) e os do grafo por
`src/grafo.py` (`PROMPT_TRIAGEM`, `PROMPT_RESSALVA`, `PROMPT_REDIGIR`), com a mesma função
(`_ler_prompt`).

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

### 2.1 Do `redigir-v1.md` ao `redigir-v2.md` (12/10/2026)

**O defeito.** Com o v1, a mensagem que o grafo redige para o cliente no `TKT-0005` ("Meu
servidor não está funcionando direito.") não pede nada. Em todas as 15 execuções do grafo com log
(as 14 de `logs/grafo*/TKT-0005.json` de 10 a 12/10/2026 e a de `logs/grafo-redigir-v1/`), o
texto repete a queixa, e em 9 delas afirma desde quando o problema ocorre, o que o cliente não
disse:

> O servidor do plano Hospedagem Start não está apresentando o funcionamento esperado. O problema
> ocorre desde quando foi relatado.

Nada em código pega isso: o nó `validar` confere tamanho e termos internos, e o verificador
confere o desfecho gravado.

**A mudança.** Uma regra, a do desfecho `devolver_cliente`. O resto do prompt é o do v1, sem
alteração (conferido linha a linha).

| | Texto da regra |
|---|---|
| v1 | o texto é ENVIADO AO CLIENTE. Escreva só a lista do que falta: o serviço ou servidor afetado, o erro ou comportamento observado e desde quando ocorre. |
| v2 | o texto é ENVIADO AO CLIENTE e é um PEDIDO: não descreva o problema nem complete o que falta, pergunte. Escreva uma frase dizendo que o suporte precisa de mais informações e três perguntas, cada uma com "?": qual serviço ou servidor está com problema, qual erro ou comportamento aparece e desde quando ocorre. |

A frase seguinte da regra (não citar procedimentos, times, filas nem prometer prazo) ficou igual.
A primeira redação do v2 tinha 539 caracteres a mais que a regra antiga, com exemplos de serviço
e a instrução em duas partes; foi encurtada para 159 antes de ser medida, para gastar menos.

**A medição.** `python src/main.py --todos --auto-aprovar --rodada NOME`, em 12/10/2026, com
`ministral-8b-latest`, `temperature=0`, commit `9d5c211 + alterações locais`. Uma rodada com o v1
e três com o v2, com o mesmo código:

| | `redigir-v1.md` (`logs/grafo-redigir-v1/`) | `redigir-v2.md` (`logs/grafo-redigir-v2-1/` a `-3/`) |
|---|---|---|
| Verificador | 8 de 8 | 8 de 8, 8 de 8 e 8 de 8 |
| Redações reprovadas pelo nó `validar` | 0 de 8 | 0 de 24 |
| Mensagem do `TKT-0005` | "O servidor do plano Hospedagem Start não está apresentando o funcionamento esperado." | "Precisamos de mais informações para ajudar. Qual serviço ou servidor está com problema? Qual erro ou comportamento aparece? Desde quando isso ocorre?" (a mesma nas três) |
| Chamadas ao modelo, na rodada | 17 | 17, 17 e 17 |
| Tokens de entrada, na rodada | 13.003 | 13.303, 13.300 e 13.302 |
| Tokens, na rodada (entrada + saída) | 14.483 | 14.722, 14.721 e 14.718 |
| Custo a preço de lista, na rodada | US$ 0,00217 | US$ 0,00221 |

**O custo, medido:** de 36 a 38 tokens de entrada a mais por execução, em cada um dos 8 casos,
porque o nó `redigir` roda em toda execução. São cerca de 300 tokens por rodada, 1,6% a mais.

**O que mais mudou: nada que se possa atribuir ao prompt.** Os 8 desfechos, os guias, os scores e
as prioridades são os mesmos nas quatro rodadas, porque o desfecho é do código. Os textos dos
outros sete casos variam de uma execução para outra com o mesmo prompt, e por isso a diferença
entre o v1 e o v2 neles não é legível: o resumo do `TKT-0007`, por exemplo, teve 599, 616 e 710
caracteres nas três rodadas do v2, e 483 na do v1.

**Dois defeitos de conteúdo que a leitura achou, e que o v2 não trata** (aparecem com os dois
prompts):

- no `TKT-0003`, o resumo do chamado interno diz que o score 0,55 "não atinge o limiar", em 3 das
  4 rodadas (uma do v1 e duas do v2). O score passa do limiar, e é por isso que o chamado é
  aberto;
- no `TKT-0001`, a anotação cita um domínio ("acmecontabilidade.com.br (ou similar)") que não
  está no chamado nem no banco, em 2 das 4 rodadas (uma do v1 e uma do v2).

**Limites.**

- **Um chamado de informação insuficiente, três execuções.** O `TKT-0005` é o único caso
  `devolver_cliente` do gabarito. As três mensagens saíram idênticas; isso mostra que o resultado
  se repete neste relato, e não que a regra funciona para outro.
- **A comparação é de uma rodada do v1 contra três do v2.** O v1 tem mais 14 execuções do
  `TKT-0005` em logs anteriores, de outros commits, todas com o mesmo defeito.
- **A avaliação é por leitura.** Não há verificador de conteúdo: se a mensagem voltar a não
  perguntar, nada no código acusa.
- **A pausa do H2 não foi refeita com o v2.** As rodadas usaram `--auto-aprovar`; a tela do
  analista com a mensagem nova não foi capturada (a de `logs/grafo-h2/` é a do v1).

### 2.2 O pedido ao cliente saiu do modelo (12/10/2026)

**A decisão.** No desfecho `devolver_cliente`, o nó `redigir` não chama o modelo: devolve um texto
padrão, a constante `PEDIDO_AO_CLIENTE` de `src/grafo.py`. O analista continua confirmando o
envio (H2) e pode trocar o texto ao aprovar (`--mensagem`).

**Por que, e o que o `redigir-v2.md` mostrou.** O v2 consertou a mensagem com uma regra que dita
a forma dela: uma frase e três perguntas, sempre as mesmas. O resultado foi o mesmo texto, letra
por letra, nas três execuções (§2.1). Foi isso que evidenciou a decisão:

- **não havia o que o modelo decidir.** O que falta num relato sem serviço nem sintoma é sempre a
  mesma coisa. Quando a regra ficou boa o bastante para funcionar, ela já era o texto;
- **o v1 errou em 15 execuções de 15**, e nada em código via o erro: o conteúdo não tem
  verificador. Um texto que o código garante dispensa o verificador que não existe;
- **o v2 pedia pouco.** As três perguntas (serviço, erro, desde quando) vieram da regra do
  prompt, e não da base. O texto padrão pergunta o que os guias usam para separar um caso do
  outro;
- **custa menos.** A execução do `TKT-0005` passou de 2 chamadas e 1.483 tokens para 1 chamada e
  621 a 624 tokens.

**O texto**, e de onde vem cada pergunta (`dados/seed.sql`, tabela `kb_artigos`):

| Pergunta | Por que está no texto |
|---|---|
| 1. Qual serviço está com problema (site, e-mail, banco de dados, FTP/SFTP, acesso SSH, backup ou tarefa agendada)? | cada guia é de um serviço; é a primeira coisa que a triagem e a busca precisam |
| 2. Qual é o domínio ou o endereço afetado? Se for banco de dados, qual é o nome do banco? | o domínio decide os guias de SSL, DNS, redirecionamento, e-mail e firewall de aplicação (KB-101-A, 106, 110, 111, 112); o banco, o KB-107 |
| 3. Qual mensagem ou código de erro aparece (por exemplo: 403, 502, "permissão negada")? Copie o texto como ele é exibido. | o código separa o KB-104 (5xx) do KB-112 (403); a mensagem, o KB-102, o KB-107 e o KB-113 |
| 4. Em que data e hora o problema começou? Ele acontece sempre ou só às vezes? | a reincidência conta datas; o KB-104 só cobre a falha constante, e a intermitente é exceção declarada |
| 5. Alguma coisa mudou pouco antes (publicação de nova versão, migração, restauração de backup, troca de senha)? | são as causas dos KB-102, 104, 107 e 114 |

A mensagem abre com "Para darmos andamento ao seu chamado, precisamos de mais informações:".

**A medição.** Três execuções dos 8 casos (`logs/grafo-pedido-padrao-1/` a `-3/`, 12/10/2026,
`ministral-8b-latest`, commit `9d5c211 + alterações locais`): 8 de 8 nas três, 16 chamadas ao
modelo (eram 17) e 13.855 a 13.912 tokens por rodada (eram 14.718 a 14.722). Uma pausa real do
H2, com o texto padrão na tela do analista, a aprovação por outro processo e a segunda aprovação
sem duplicar, está em `logs/grafo-pedido-padrao-h2/saida-terminal.txt`. Testes offline:
`test_o_pedido_ao_cliente_e_o_texto_padrao_e_nao_chama_o_modelo_para_redigir` e
`test_o_texto_padrao_do_pedido_pergunta_e_nao_cita_informacao_interna`.

**O que se perde, e os limites.**

- **A mensagem não se adapta ao relato.** O cliente que já disse o serviço e não disse o sintoma
  recebe as cinco perguntas. O que corrige isso é o analista, ao aprovar com `--mensagem`.
- **O texto envelhece com a base.** A lista de serviços e os exemplos de erro foram tirados dos
  15 guias de hoje. Guia novo, de outro serviço, pede revisão da constante, e nada avisa.
- **Nenhum cliente respondeu a essas perguntas.** Se elas bastam para a segunda triagem só se
  mede com a resposta do cliente, que o sistema não recebe (o H3 não existe).
- **A regra do `devolver_cliente` no `redigir-v2.md` ficou sem uso**, e continuava indo ao modelo
  nas outras quatro redações. Saiu no `redigir-v3.md` (§2.3).
- **O laço da Parte 1 não mudou:** lá o pedido continua sendo escrito pelo modelo.

### 2.3 O `redigir-v3.md`: a regra sem uso sai do prompt (12/10/2026)

**A mudança.** O v3 é o v2 sem a regra do `devolver_cliente` (466 caracteres). Nada mais mudou no
texto. O prompt passa a redigir quatro desfechos, e nenhum deles chega ao cliente.

**A medição.** Três execuções dos 8 casos com cada prompt, com o mesmo código (o pedido ao
cliente já em texto padrão), em 12/10/2026, `ministral-8b-latest`, `temperature=0`, commit
`9d5c211 + alterações locais`:

| | `redigir-v2.md` (`logs/grafo-pedido-padrao-1/` a `-3/`) | `redigir-v3.md` (`logs/grafo-redigir-v3-1/` a `-3/`) |
|---|---|---|
| Verificador | 8 de 8 nas três | 8 de 8 nas três |
| Redações reprovadas pelo nó `validar` | 0 de 21 | 0 de 21 |
| Chamadas ao modelo, na rodada | 16 | 16 |
| Tokens de entrada, na rodada | 12.472 a 12.475 | 11.634 a 11.644 |
| Tokens, na rodada (entrada + saída) | 13.855 a 13.912 | 13.122 a 13.191 |
| Custo a preço de lista, na rodada | US$ 0,00208 | US$ 0,00198 |

**O ganho, medido:** 119 tokens de entrada a menos em cada execução que passa pela redação, que
são 7 dos 8 casos (o `TKT-0005` não redige mais, e ficou igual, com 558 de entrada). Na rodada,
cerca de 830 tokens de entrada a menos, 6,7%.

**O que mais mudou: nada que se possa atribuir ao prompt.** Desfechos, guias, scores e
prioridades são os mesmos. Os textos variam entre execuções, como antes. Os dois defeitos de
conteúdo do §2.1 foram procurados nas três rodadas do v3: o score que "não atinge o limiar" não
apareceu em nenhuma (com o v2, em 2 de 3), e o domínio inventado apareceu em 1 de 3. Três
execuções não bastam para dizer que tirar a regra melhorou o primeiro, e o v3 não tem regra para
nenhum dos dois.

**Limites.** São os mesmos 8 casos e a avaliação dos textos é por leitura. Da série de três
versões do mesmo dia, a única mudança de conteúdo foi a do v2; o v3 só tira texto.

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
- Dar à redação um critério de acerto além do nó `validar`, e medir `triagem-v1.md` em chamados
  fora dos 8 casos (as três execuções medidas são dos mesmos).
- Fazer a regra da frase também em um prompt do grafo, que é o caminho padrão (o §3 testou o do
  laço).
- Tratar os dois defeitos de conteúdo que a leitura das rodadas achou no `redigir` (§2.1): o
  resumo que diz que um score acima do limiar "não atinge o limiar", e o domínio inventado na
  anotação. Não foram tratados no v2, que mudou uma regra só.
- Medir o `redigir-v2.md` em outro relato de informação insuficiente: o gabarito tem um (§2.1).
- Acrescentar uma linha no §1 se uma etapa de modelo nova nascer (hoje não há resposta do RAG nem
  extração para a memória).

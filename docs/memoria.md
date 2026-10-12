# Memória do agente (Exercício 8 / §5 da Parte 2)

> **Como ler este documento.** As seções "Decisão 1" e "Decisão 2" são o **desenho**, escrito
> antes do código (Exercício 8), e em parte para o laço da Parte 1. Os §3 a §5 descrevem **o que
> existe em código**, no grafo. Onde os dois divergem vale o código, e o §1.6 lista cada
> divergência. O §1.7 responde à fronteira entre checkpoint, memória e RAG (§5.1 do enunciado).
>
> **Atualização de 12/10/2026 (memória procedural).** O grafo passou a carregar uma regra
> aprendida no prompt do nó `redigir` (`src/prompts/regras-redigir-v2.md`, §5.1). É a primeira
> regra, e entrou como exceção declarada à política do §1.4: veio da leitura das rodadas pelo
> grupo, e não de três correções do analista.
>
> **Atualização de 12/10/2026.** A escrita de memória ganhou chave de idempotência, com
> `ja_existia` no retorno (§1.4). O checkpoint do grafo passou a ser apagado quando a execução
> conclui, como o §1.4 já dizia e o código não fazia. Entraram o §1.6 e o §1.7.
>
> **Atualização de 11/10/2026.** A **memória episódica** foi implementada no grafo, na forma
> descrita no §3 (o que existe em código): registro por execução, leitura por consulta exata,
> aviso na tela do H1 e decaimento. A **memória semântica** foi implementada como fatos do
> ambiente do cliente confirmados pelo analista (§4), diferente do que o §1.3 previa. Da **memória
> procedural** existe o que não muda o prompt: o motivo da rejeição e o relatório de candidatas
> (§5). A leitura por similaridade (§1.3) e a regra carregada no prompt continuam sendo decisão de
> projeto.
>
> **Atualização de 10/10/2026.** Da memória de longo prazo, nada estava implementado nesta data: o texto abaixo
> era só decisão de projeto. Do curto prazo, o **checkpoint** já existe no grafo
> (`src/grafo.py`): `SqliteSaver` gravando em `dados/checkpoints.db`, com `thread_id` igual ao id
> do chamado, como o §1.5 previa. Ele guarda a execução pausada no H1; uma execução nova do mesmo
> chamado apaga o checkpoint anterior (`grafo.md` §7).

> O laço da Parte 1 (`--laco`) **não tem memória**: cada execução parte do zero, olha só o
> chamado que recebeu e esquece tudo ao terminar. As decisões abaixo foram tomadas **antes** de
> construir a memória (par prático 08-complementar), aplicadas ao domínio do case: um agente de
> triagem que consulta chamados, base de conhecimento e histórico de um sistema de hospedagem de
> servidores.

## Decisão 1 — Como o agente lembra

### 1.1 Os dois níveis, no domínio do case

| | Curto prazo | Longo prazo |
|---|---|---|
| O que é | a janela de uma triagem (um `TKT-xxxx`), incluindo a pausa à espera do cliente quando o agente pede informação | o que atravessa chamados diferentes, de clientes diferentes, em dias diferentes |
| Conteúdo, no case | prompt do sistema (`src/prompts/agente-v5.md`, o prompt em uso, já executado em três rodadas de 8 casos: `logs/rodada-1-prompt-v5/` a `logs/rodada-3-prompt-v5/`), o texto do chamado com o id que o acompanha ("TKT-0002: Meu Webmail está fora do ar…"), a trajetória (as chamadas de `consultar_ticket`, `buscar_base_conhecimento` e seus resultados), os trechos da base de conhecimento recuperados nesta busca | episódica (execuções passadas), semântica (fatos estáveis sobre clientes e times), procedural (regras de triagem aprendidas) |
| Persistido como | **checkpoint** por conversa, endereçado pelo `thread_id` = id do chamado externo (ver 1.5) | índice por similaridade (episódica), tabela chave-valor (semântica), texto dentro do próprio prompt (procedural) |
| Lido | uma vez, ao retomar uma execução parada | a cada passo do laço em que o modelo pode se beneficiar de um fato ou um precedente |
| Acesso | por `thread_id` (id do chamado) | por relevância (episódica), por chave `cliente_id`/categoria (semântica), carregado sempre (procedural) |
| Ciclo de vida | morre quando a execução termina (`respondeu`, `orcamento_esgotado`, `erro_fatal`); **sobrevive** enquanto o término for `aguardando_humano` (confirmação do analista) ou `aguardando_cliente` (resposta ao pedido de informação) | acumula entre execuções, sujeita às três causas de esquecimento da Decisão 2 |

**O que exatamente vai para o checkpoint.** Hoje o objeto `Estado` já concentra quase tudo que um checkpoint precisaria guardar; a mudança é persisti-lo fora do processo em vez de deixá-lo morrer com ele. Os campos, e por quê:

- `id_ticket`, `execucao_id`, `historico` (as mensagens já trocadas com o modelo) — para retomar sem reconstruir o contexto do zero;
- `passos` já executados, com seus resultados — para **não repetir** uma leitura já feita (`consultar_ticket`, `buscar_base_conhecimento`) nem, mais importante, uma escrita: a chave de idempotência do `abrir_chamado_interno` (`ticket:kb_id`) já impede duplicata mesmo sem checkpoint, mas o checkpoint evita a chamada redundante que geraria custo e log confuso;
- `pendencia` — os argumentos exatos da ação irreversível que aguarda confirmação, para o analista poder aprovar **minutos depois** (o prazo é de 20 minutos, `docs/case.md` §2.1), de outro processo (hoje isso já acontece para a abertura de chamado: a ação fica na tabela `pendencias`, com o `Estado` da execução guardado ao lado, e `agente.retomar()` continua a execução quando o analista responde ou o prazo vence; ver `docs/arquitetura.md` §7);
- `n_chamadas_modelo`, `tokens`, `custo_usd`, o tempo de execução já gasto (não o instante de início: a espera pelo cliente ou pelo analista não conta para o teto de 90 s) — para o orçamento continuar contando certo na retomada, em vez de reiniciar e permitir um caso que já gastou 25 dos 30 mil tokens permitidos continuar por mais 30 mil;
- `scores_kb` — para não recalcular a busca e, principalmente, para a decisão de reabrir ou não a busca (score abaixo do limiar) ser auditável depois;
- `pedido_cliente` — se o pedido de informação já foi enviado, quando, e a resposta do cliente quando chegar. É o que garante, na retomada, que o pedido **não é enviado de novo** (a mensagem chega ao cliente e não tem volta) e que um segundo pedido seja recusado em código;
- `desfecho`, se já existir — para o caso de a execução cair **depois** de já ter escrito no banco (o registro venceu, o processo caiu): retomar não deve tentar escrever de novo.

Isso responde às três perguntas do enunciado: (a) retomável sem reaplicar efeito colateral, porque a idempotência e o `desfecho` já gravado impedem reexecutar a escrita; (b) aprovação humana minutos depois — ou resposta do cliente dias depois —, porque a `pendencia` e o `pedido_cliente` ficam persistidos em vez de presa a um `input()` de terminal; (c) estado defeituoso reproduzível, porque o checkpoint é exatamente o `logs/TKT-xxxx.json` que já usamos para depurar as falhas das rodadas 1 a 3 — só falta ele existir **antes** do fim da execução, não só depois.

### 1.2 O orçamento da janela

Seis fontes disputam a janela de uma chamada ao modelo. As medidas por fonte da tabela foram feitas com o `src/prompts/agente-v3.md` e os schemas de `src/ferramentas.py` daquela época. O prompt em uso hoje é o `agente-v5.md`, e **a medida por fonte não foi refeita com ele**.

O que há de medido com o `agente-v5.md` é o total, na rodada 3 (`logs/rodada-3-prompt-v5/`, 10/10/2026, 8 execuções, seed e texto atuais):

| Medida na rodada 3 | Valor |
|---|---|
| Tokens de entrada por chamada ao modelo (média de cada execução) | de 2.017 (`TKT-0005`) a 2.492 (`TKT-0002`) |
| Tokens por execução, entrada + saída | de 6.166 (`TKT-0005`, 3 chamadas) a 12.962 (`TKT-0002`, 5 chamadas) |
| Total das 8 execuções | 69.889 tokens em 31 chamadas ao modelo |

A média por chamada fica abaixo da soma dos tetos (6.000), sem memória de longo prazo e sem corte nenhum: o laço de hoje reenvia a trajetória inteira e não descarta passos. O log grava o total de tokens da execução, e não o de cada chamada, então a maior chamada de cada execução não está medida.

A tabela, com os valores por fonte medidos no `agente-v3.md`:

| Fonte | Teto (tokens) | Medido / justificativa |
|---|---|---|
| System prompt | 900 (fixo) | ~860 tokens, medido. Nunca é cortado: sem ele o modelo não sabe as regras (é o que a rodada 2 mostrou ao mexer nele sem cuidado) |
| Entrada (texto do chamado + id do chamado e do cliente) | 150, variável | o texto livre do cliente (e, na retomada, a resposta ao pedido de informação); nunca é cortado |
| Schemas das 4 ferramentas | 750 (fixo) | ~730 tokens, medido; parte do contrato de tool calling, não é opcional |
| Trajetória (passos já dados nesta execução) | 3.000, variável | cresce a cada chamada (observado: 400 a 1.500 tokens por chamada nas rodadas reais). Quando estoura, **descarta os passos mais antigos**, nunca o mais recente — é o inverso do corte ingênuo pelo fim, que apagaria justo o que acabou de acontecer |
| Trechos recuperados (top-3 da busca) | 500 | ~110 a 150 tokens por artigo, medido; 3 artigos cabem com folga |
| Memória de longo prazo (recall episódico + semântico) | 700 | orçamento novo, proposto: 1 a 2 episódios similares (~250 tokens cada) + fatos semânticos do cliente (~100 tokens) |

Soma dos tetos: 6.000 tokens, dentro de uma janela de trabalho assumida de 8.000 tokens (número conservador; os modelos usados no plano gratuito da conta suportam mais, mas o laço deve caber com folga mesmo num provedor mais restrito).

**O que é descartado primeiro quando o total estoura, nesta ordem:**
1. memória de longo prazo (é a mais nova, a mais opcional, e a Parte 1 inteira já funcionou sem ela);
2. trechos recuperados, de 3 para 1 artigo (o de maior score);
3. passos mais antigos da trajetória, um de cada vez, até caber — nunca o passo mais recente, nunca o prompt, nunca o objetivo.

> **Situação em 12/10/2026: a ordem está declarada e não está implementada.** Ela foi desenhada
> para o laço, que reenvia a trajetória a cada volta e por isso cresce. O grafo não tem
> trajetória na janela: cada nó de modelo monta a própria mensagem, e a chamada média medida é de
> 849 tokens (§1.6, que traz a ordem adaptada ao que o grafo envia). Nenhuma execução medida
> chegou perto de encher a janela, então um corte seria código que nada aciona. **Fica como melhoria
> futura**, na forma mínima: cortar o começo do log anexado acima de um tamanho, mantendo o fim,
> que é o mais recente. É o único risco concreto de hoje: um log muito grande vai inteiro numa
> chamada, e o que o segura é o teto de 30 mil tokens, que encerra a execução em vez de cortar.

### 1.3 As três memórias de longo prazo, no case

| Tipo | O que guarda no case | Estrutura | Como é recuperada |
|---|---|---|---|
| **Episódica** | Um registro por execução concluída: `id_ticket`, categoria, `kb_id` usado, desfecho, se foi confirmado ou recusado pelo analista, e um resumo curto do que aconteceu (ex.: "TKT-0002: relato de webmail fora do ar, log mostrou DNS, foi para fila humana") | índice por similaridade (embedding do texto do chamado + resumo do desfecho) | por similaridade com o texto do chamado atual, no passo de busca — para achar precedentes parecidos, não só procedimentos da base |
| **Semântica** | Fatos estáveis por cliente: plano contratado e — a parte que mais importa — a reincidência **por categoria** (se o cliente teve ocorrência anterior da mesma categoria nos últimos 30 dias), hoje já calculada em SQL (`_reincidencia` em `src/db.py`) a partir da tabela `chamados_internos` | chave-valor, chave = `cliente_id` + categoria | por chave exata, uma consulta, não uma busca |
| **Procedural** | Regras de triagem aprendidas a partir de correções do analista: quando o analista reverte uma decisão do agente (por exemplo, confirma um `fila_humana` que devia ter sido `abrir_chamado_interno`) repetidamente para o mesmo padrão de caso, isso vira candidato a regra no prompt | texto dentro do próprio *system prompt* (como as três versões `agente-v1/v2/v3.md` já são, hoje, versionadas manualmente) | sempre carregada, porque é o próprio prompt |

A reincidência é o exemplo mais claro de por que a estrutura decorre do padrão de acesso: ela **já é semântica** hoje, só que recalculada a cada consulta em vez de armazenada — o que é a escolha certa (ver "o que é derivável", abaixo), então o item da tabela acima registra a decisão de **manter** assim, não de criar um novo armazenamento.

### 1.4 Quem escreve, o volume, e o que não entra

**Quem escreve:**
- **episódica**: o **código** extrai, ao fim de cada execução (qualquer término; a ação que o analista rejeita termina em `respondeu`, com desfecho `fila_humana` e motivo `acao_rejeitada`), os campos estruturados do `Estado` — nunca o texto livre que o modelo escreveu como resposta final, porque texto livre é exatamente o que a rodada 2 mostrou não ser confiável ("registrei" sem ter registrado);
- **semântica**: o **código** também, por regra determinística (a mesma consulta SQL que já existe), nunca o modelo — um fato como "plano do cliente" tem peso de negócio demais para depender de o modelo tê-lo lido certo. **Como ficou (§4):** o plano e a reincidência não foram guardados de novo, e o que a memória semântica guarda são fatos do ambiente do cliente, escritos **só por uma pessoa** (`main.py --fato`). O código não escreve fato nenhum;
- **procedural**: só o **humano** (analista ou o grupo), em revisão, nunca automático — é a lição da rodada 2: prompt mexido sem supervisão piorou o resultado de 5 para 3 em 7. Uma regra procedural só entra no prompt depois de aparecer em pelo menos 3 correções do mesmo padrão, revisadas por uma pessoa. **Exceção declarada (12/10/2026):** a primeira regra em uso (§5.1) não passou por esse corte. Ela veio de um defeito que o grupo achou lendo as rodadas, porque 8 chamados simulados não produzem três correções de um analista de verdade. A política continua valendo para as próximas.

**Volume por execução:** 1 registro episódico (≈150 a 250 tokens); 0 ou 1 atualização semântica (só quando um fato realmente muda — o plano do cliente, por exemplo; não a cada execução); 0 escritas procedurais por execução (é processo em lote, periódico, não por chamado).

**Volume por execução, no código de hoje:** 1 linha em `episodios` por execução concluída do
grafo (14 campos estruturados e a chave; o maior é o `resumo`, uma frase montada pelo código, de
96 a 152 caracteres nos 9 episódios de `logs/grafo-fatos/` e `logs/grafo-h2/`); 0 linhas em `fatos_cliente` (o fato só nasce de `main.py --fato`); 0
escritas procedurais. A execução pausada não escreve nada até o analista responder.

**A escrita de memória é idempotente (§5.3 do enunciado; 12/10/2026).** Cada escrita tem uma
chave derivada do conteúdo, e o retorno diz se o registro já existia:

| Escrita | Chave | O que a repetição faz | Retorno |
|---|---|---|---|
| episódio (`db.registrar_episodio`) | `db.chave_do_episodio`: os 16 primeiros caracteres do SHA-256 de `execucao_id`, chamado, guia, ação proposta, desfecho, veredito, motivo da rejeição e término. A hora da gravação fica de fora, porque a repetição teria outra hora | não cria linha: devolve o id da que existe | `{id, chave, ja_existia}`; os três vão ao campo `episodio` do log |
| fato (`db.registrar_fato`) | o próprio conteúdo: cliente, chave e valor. O fato é chave-valor, então não precisa de hash | não cria linha e não muda quem confirmou nem quando | o fato que vale, com `ja_existia` |
| motivo da rejeição | faz parte do episódio | a do episódio | a do episódio |

Testes offline: `test_a_escrita_do_episodio_e_idempotente_pela_chave_do_conteudo`,
`test_executar_de_novo_o_mesmo_chamado_e_outro_episodio` e
`test_fato_tem_vocabulario_fechado_e_o_valor_novo_substitui_o_antigo`. Três limites:

- **Executar de novo o mesmo chamado é outra execução**, com outro `execucao_id` e outra chave:
  são dois episódios. A chave reconhece a gravação repetida, e não o chamado repetido. É o que
  mantém a contagem do §5 como estava (três rejeições do mesmo chamado contam três).
- **Hoje nenhum caminho do grafo grava o mesmo episódio duas vezes**: `_concluir()` roda uma vez
  por invocação, e a segunda aprovação não chega a ele. A chave é a barreira para quando isso
  mudar, e a repetição foi exercitada só por teste, chamando a função duas vezes. Com o modelo
  real o que há é a gravação normal: os 32 logs de `logs/grafo-redigir-v1/` e
  `logs/grafo-redigir-v2-1/` a `-3/` (12/10/2026) trazem a chave e `ja_existia: false`.
- **Episódio sem `execucao_id` não tem chave** e é sempre gravado. É o caso dos episódios que os
  testes semeiam à mão. Para a chave valer, o `execucao_id` do grafo deixou de sair do relógio em
  segundos, que se repetia em duas execuções seguidas, e passou a ter um trecho aleatório.

**O que o sistema não guarda:**
- **dado sensível não verificado** — o `anexo_log` do cliente (que pode conter hostname, IP, e por acidente uma credencial colada) não é gravado verbatim em nenhuma memória de longo prazo; só o resumo estruturado (categoria, KB usado) sobrevive à execução. O checkpoint, que guarda o log por inteiro enquanto a execução está viva, é apagado quando ela termina (no grafo, desde 12/10/2026: `_concluir()` apaga o thread da execução concluída, e só a pausada mantém o seu; teste `test_execucao_concluida_apaga_o_checkpoint_e_a_pausada_nao`). **Três pendências, declaradas:** (1) o `logs/TKT-xxxx.json` grava o resultado de `consultar_ticket` com o anexo inteiro, e para esta regra valer o campo `anexo_log` precisa ser redigido no log ao fim da execução; (2) a linha da tabela `pendencias` fica depois de resolvida, e a do H2 traz o relato do cliente no campo `relato`; (3) no laço da Parte 1, a pendência resolvida mantém na coluna `checkpoint` o `Estado` inteiro, com o chamado lido e as mensagens;
- **conteúdo não verificado vindo de fora** — a afirmação do próprio cliente ("é a terceira vez", "prioridade máxima") nunca vira fato semântico. É exatamente a regra que o prompt já aplica ("afirmação a verificar", em `agente-v3.md`): só o que o **histórico do sistema** confirma pode virar memória de longo prazo; a alegação do cliente fica só no registro episódico daquela execução específica, nunca promovida a fato sobre o cliente;
- **o que é derivável** — a reincidência, como já dito, nunca é armazenada como valor fixo: é recalculada por consulta, porque depende da janela de 30 dias. Guardar um valor que pode ficar desatualizado (e nenhum mecanismo de decaimento cobrindo justamente ele) seria dívida sem necessidade.

### 1.5 A conversa com o cliente (§5.5)

O agente só conversa com o cliente em um caso: quando falta informação para classificar o chamado, ele envia **um** pedido, depois da confirmação do analista, e espera a resposta (regra em `docs/case.md` §2.1). As quatro decisões da conversa, nesse cenário:

> **Como ficou (12/10/2026).** O pedido espera o analista (H2) e é registrado como enviado. **A
> espera pela resposta do cliente (H3) não foi implementada**: a execução termina depois do
> envio, e uma resposta do cliente seria uma execução nova do mesmo chamado, sem o checkpoint da
> anterior. A conversa de hoje tem uma mensagem do cliente só. As quatro respostas abaixo valem
> para o `thread_id` e para o lugar do checkpoint, que existem; a parte da resposta do cliente é
> desenho.

**O que identifica uma conversa.** `thread_id` = id do chamado externo (`TKT-xxxx`). Cada chamado é uma conversa: a mesma pessoa com dois chamados abertos ao mesmo tempo tem duas conversas independentes, e a resposta de um não contamina a triagem do outro. A resposta do cliente chega pelo próprio chamado, então ela já carrega o id que a leva de volta à conversa certa.

**Onde o checkpoint é gravado.** Em SQLite, num arquivo próprio ao lado do banco simulado (`dados/`), e não em memória. A espera pelo cliente pode durar até 3 dias úteis; com checkpoint em memória, a conversa morreria com o processo e a resposta chegaria a uma execução que não sabe que o pedido foi feito — e poderia pedir de novo.

**O que acontece quando a janela enche.** Na prática, não enche: a conversa tem no máximo duas mensagens do cliente (o chamado original e uma resposta), porque o agente faz um único pedido. A retomada não reaproveita a trajetória antiga inteira: ela recomeça a triagem com o texto original + a resposta e mantém do checkpoint só o que é decisão (o pedido já feito, o orçamento já gasto). Se mesmo assim o contexto estourar, vale a ordem de descarte do §1.2 — e o texto do cliente nunca é descartado.

**O que passa da conversa para a memória de longo prazo.** Só o fato de que houve pedido e se ele resolveu, no registro episódico da execução (ex.: "TKT-0005: pediu serviço e sintoma; cliente respondeu; abriu chamado P1"). O texto da resposta do cliente fica no chamado e no checkpoint, que é apagado quando a conversa termina; ele não vira memória semântica pela mesma regra do §1.4: afirmação do cliente não é fato verificado.

### 1.6 O desenho acima e o código de hoje

| Assunto | No desenho (§1.1 a §1.5) | No código (12/10/2026) |
|---|---|---|
| O que vai ao checkpoint | o `Estado` do laço, com `historico` e `passos` | o `EstadoGrafo` inteiro, gravado pelo `SqliteSaver` a cada superpasso. Não há lista de mensagens (`arquitetura.md` §4) |
| Quando o checkpoint some | ao fim da execução; sobrevive em `aguardando_humano` e `aguardando_cliente` | ao fim da execução; sobrevive em `aguardando_humano`. O término `aguardando_cliente` não existe (o H3 não foi implementado) |
| Campo `pedido_cliente` | guarda o pedido enviado e a resposta | não existe. O pedido enviado é uma linha em `encaminhamentos`, com `enviado_em`, e a contagem é feita no banco |
| Episódica | índice por similaridade, lido no passo de busca | tabela `episodios`, lida por **consulta exata** (guia; cliente e categoria), só para a tela do H1 (§3). A razão está abaixo da tabela |
| Semântica | plano e reincidência por cliente, escritos pelo código | fatos do ambiente do cliente, escritos por uma pessoa (§4). Plano e reincidência continuam vindo do sistema de tickets |
| Procedural | regra no prompt do laço, nascida de decisões de triagem que o analista reverte, depois de 3 correções revisadas | uma regra, no prompt do nó `redigir` do grafo, escrita por uma pessoa num arquivo próprio (§5.1). O analista só vê as duas pausas (H1 e H2) e não tem como reverter uma decisão de triagem: as correções que o sistema registra são a rejeição com motivo e a aprovação com edição, e por isso a regra mira o texto. A primeira regra não veio das 3 correções (exceção do §1.4) |
| Ordem de descarte (§1.2) | memória, depois trechos, depois passos antigos | **nenhum código corta a janela.** Ver abaixo |
| Remoção a pedido do titular (§2.3) | cinco estruturas, com varredura | **não escolhida** (decisão de 12/10/2026): o §2.3 traz a razão e onde o identificador fica |

**Por que a episódica não é por similaridade (situação em 12/10/2026).** O índice de embeddings
do §1.3 não foi feito, e não será na Parte 2. Duas decisões tomadas depois do desenho o
dispensam: o episódio guarda só campos estruturados, nunca o texto do cliente nem o do modelo
(§1.4), então não há texto para embedar; e a memória só avisa o analista, sem entrar em regra de
decisão (§3). Com isso, a pergunta que a memória responde é "o que já foi decidido sobre este
guia, e para este cliente nesta categoria?", e uma chave a resolve: é o mesmo argumento que o
enunciado usa para a semântica (buscar por similaridade é caro e impreciso quando uma chave
resolve). O que se perde: o precedente de um chamado **parecido** que caiu em outro guia, ou em
nenhum, não aparece. Fazer por similaridade exigiria guardar o texto do chamado na memória de
longo prazo, o que desfaz a regra do §1.4 e amplia o que fica sem resposta no §2.3.

**A janela, no grafo.** O §1.2 foi medido no laço, que reenvia a trajetória a cada volta. O grafo
não tem trajetória na janela: cada nó de modelo monta a própria mensagem com o que precisa
(`_registro_para_o_modelo`, em `src/grafo.py`). Na rodada `logs/grafo-fatos/` (11/10/2026, 8
execuções) foram 14.440 tokens em 17 chamadas, 849 por chamada na média, entrada e saída somadas;
a execução mais cara gastou 2.520 tokens, em 3 chamadas. O que entra em cada chamada:

| Fonte | `triagem` | `conferir_ressalva` | `redigir` |
|---|---|---|---|
| prompt do nó | sim | sim | sim |
| texto do cliente, log anexado e histórico de chamados | sim | sim | sim |
| o primeiro guia recuperado | não | título, causa e as situações que não cobre | título, causa, solução e a ressalva |
| fatos confirmados do cliente (memória semântica) | não | sim | não |
| escopo do plano | não | não | sim, na rota técnica |
| episódios (memória episódica) | não | não | não: vão só à tela do analista |

**A ordem de descarte que vale para essa janela** é a do §1.2 aplicada ao que o grafo envia:
primeiro o escopo do plano e os fatos do cliente (contexto, e o sistema funcionou sem eles);
depois o histórico de chamados; por último o começo do log anexado, mantendo o fim, que é o mais
recente. Nunca saem o prompt do nó, o texto do cliente e, na conferência da ressalva, as
situações que o guia não cobre. **Essa ordem não está implementada, e nada a exercitou:** na
mesma rodada, a execução com as chamadas maiores (`TKT-0002`) teve 1.045 tokens por chamada na
média; o log guarda o total da execução, e não o de cada chamada. O que existe é o teto de 30 mil
tokens por execução, conferido antes de cada chamada. Um log anexado muito grande iria inteiro
numa chamada. O corte do começo do log fica como melhoria futura (nota do §1.2).

### 1.7 Checkpoint, memória e RAG: a fronteira, no case (§5.1)

As três guardam informação no mesmo arquivo de dados ou ao lado dele, e servem a coisas
diferentes:

| | Checkpoint | Memória | RAG |
|---|---|---|---|
| O que é, aqui | o `EstadoGrafo` de uma triagem, em `dados/checkpoints.db` | as tabelas `episodios` e `fatos_cliente`, em `dados/tickets.db` | os 16 guias de `kb_artigos` e as 3 fichas de plano, com o índice `kb_vetores` |
| Escopo | uma execução de um chamado (`thread_id` = `TKT-0000`) | todas as execuções: episódios de qualquer chamado, fatos por cliente | nenhuma: o corpus existe antes das execuções e não depende delas |
| Para quê | **retomar** a execução que parou no H1 ou no H2, sem refazer triagem, busca e redação | **lembrar** o que o analista já decidiu sobre um guia e o que ele confirmou sobre o ambiente de um cliente | **consultar** o procedimento que diz o que fazer com o problema relatado |
| Forma | o estado inteiro: o texto do cliente, o log anexado, os candidatos, o texto redigido, a pendência | fragmento escolhido: 14 campos estruturados por episódio, sem texto do cliente; uma linha por fato, de vocabulário fechado | documento escrito por terceiros (os times de suporte), com causa, solução e o que não cobre |
| Leitura | uma vez, na retomada, pelo `thread_id` | por **chave exata**, no ponto de uso: os precedentes do guia e do cliente na tela do H1; os fatos do cliente na conferência da ressalva | por **relevância** (o cosseno do relato com cada guia), uma vez por execução técnica, no nó `buscar` |
| Quem escreve | o LangGraph, a cada superpasso | o código (o episódio) e o analista (o fato e o motivo da rejeição). Nunca o modelo | ninguém em tempo de execução: o corpus vem curado do seed, e o índice é derivado dele |
| Quando some | quando a execução conclui | o episódio, depois de 365 dias; o fato não some, é substituído | quando o guia é revogado: sai da busca e fica na tabela |

**Onde este case difere da tabela do enunciado.** Lá a memória é lida por relevância, a cada
volta. Aqui ela é lida por chave, e só em dois pontos. A razão é o que ela guarda: a pergunta que
o analista faz na tela do H1 é "o que já foi decidido sobre **este** guia?" e "o que **este**
cliente teve nesta categoria?", e as duas têm chave. A leitura por similaridade do §1.3 ficou no
desenho.

**O que precisa estar no checkpoint para a retomada não repetir efeito.**

- `pendencia` e `pendencia_id`: a ação como o analista a viu, com `pedido_em` e `vence_em`. A
  linha em `pendencias` é o único efeito anterior à pausa, e quem a grava é o nó
  `pedir_confirmacao`. O checkpoint registra que esse nó terminou, e a retomada recomeça do nó
  seguinte, `confirmar`, que não faz nada antes do `interrupt`. Sem o checkpoint, a retomada
  criaria outra pendência, com outro prazo.
- `desfecho_proposto`, `texto_redigido`, `ticket` e `candidatos`: o que o nó `gravar` usa. Com
  eles a retomada não chama o modelo: os tokens da execução retomada são os mesmos da pausada
  (`logs/grafo-pausa/`, `logs/grafo-h2/`).
- os acumulados (`passos`, tokens, custo, `segundos_gastos`): para os tetos continuarem contando
  de onde pararam.
- depois da retomada, a escrita tem a sua própria barreira: abrir chamado é idempotente pela
  chave `ticket:kb_id`, o pedido ao cliente pelo chamado, e `resolver_pendencia` só fecha a
  pendência que ainda aguarda.

**O que a recuperação seletiva traz que guardar tudo não traria.** Guardar o checkpoint de todas
as execuções daria, por chamado, o estado inteiro: o texto do cliente, o log, os candidatos. Para
responder "quantas vezes o analista rejeitou o KB-102 nos últimos 90 dias, e por quê?" seria
preciso abrir os estados um a um, porque nada liga um ao outro, e o sistema passaria a guardar
texto de cliente e log anexado para sempre, que é o que o §1.4 proíbe. O episódio traz essa
resposta em uma consulta, na hora em que o analista decide: a linha `MEMÓRIA:` da tela do H1
(`humano.md` §2.1).

No corpus a seleção é por relevância de verdade: de 16 guias, a busca traz até 3 para o relato
(`rag.md` §4), e o `redigir` recebe só o primeiro.

**O que ela deixa para trás.**

- **Tudo o que não virou campo.** O episódio não tem o texto do cliente, o log nem o texto
  redigido. Uma pergunta que ninguém previu ao escolher os campos ("os chamados rejeitados
  citavam SSH?") não tem resposta na memória; teria no log, enquanto ele existir.
- **O precedente parecido que não é idêntico.** A leitura é por chave: uma rejeição do KB-114 não
  aparece quando a proposta é o KB-102, embora os dois guias declarem a mesma exceção ("ssh",
  §4.1). É o preço de não ter feito a leitura por similaridade.
- **No corpus, o que o vetor não enxerga.** A busca por relevância não lê as exceções de um guia
  (`rag.md` §4.2), e nenhum limiar separa as perguntas sem resposta das que têm (`rag.md` §4.3).

## Decisão 2 — Como o agente esquece

As causas escolhidas, das três do enunciado (§5.4):

| Causa | Escolhida? | O que faz no sistema |
|---|---|---|
| Contradição | **sim** | nos guias, o revogado é filtrado e a versão mais nova vence, com o descarte registrado (§2.1); no fato do cliente, o valor novo substitui o anterior, que fica na tabela com a data (§4) |
| Decaimento | **sim** | nos episódios: até 90 dias conta, de 90 a 365 aparece como antigo, depois é apagado (§2.2 e §3) |
| Remoção a pedido | **não** | nada; a razão e o que fica sem resposta estão no §2.3 |

### 2.1 Contradição — o fato que mudou

No case, o que mais pode se contradizer são os **procedimentos técnicos** (fonte D de `docs/base-de-conhecimento-v2.md`), porque é deles que vêm o time de destino e a prioridade de cada chamado. Exemplo: a versão antiga do procedimento de SSL (KB-101) mandava renovar o certificado manualmente pelo painel e escalar para a Segurança com P1; a versão vigente (KB-101-A) manda conferir o certbot e anotar para a Infraestrutura com P2. Os dois textos são igualmente parecidos com o relato "meu certificado SSL venceu", e a busca por similaridade não tem como saber qual vale. Se a versão antiga vencer, o erro não fica no texto: vira um chamado P1 aberto para o time errado.

**Regra de desempate:** todo trecho indexado — procedimentos técnicos e catálogo de planos — carrega `data_publicacao` e `revogado_por` (previstos em `docs/base-de-conhecimento-v2.md`; as duas colunas existem em `kb_artigos` desde 11/10/2026). Um trecho com `revogado_por` preenchido é filtrado antes da busca; entre duas versões vigentes do **mesmo procedimento** (o mesmo id sem a letra: `KB-101`, `KB-101-A`, `KB-101-B`), vale `max(data_publicacao)`, e a letra mais adiante só decide entre versões publicadas no mesmo dia. As duas regras estão implementadas em `db.buscar_kb` para os procedimentos técnicos e foram medidas em 11/10/2026 (`docs/rag.md` §2.1); o catálogo de planos não existe no repositório. Trechos de procedimentos ou subcenários diferentes não são desempatados por data: concorrem pelo score. Não é o modelo que decide: é um filtro e uma comparação de datas em código, determinísticos e testáveis.

**O descarte é registrado**, não silencioso: quando um fato perde para outro mais recente, isso fica no log da busca (o resultado de `buscar_base_conhecimento` traz, no guia que ficou, `data_publicacao` e `versoes_descartadas`, com o id e a data de cada versão antiga que também casava; implementado em 11/10/2026), para que uma auditoria consiga distinguir "não achou nada" de "achou dois e escolheu o mais novo".

### 2.2 Decaimento — o fato que envelheceu sem ser contradito

**Corte proposto: 90 dias para rebaixar, 365 dias para remover**, aplicado à memória **episódica** (execuções passadas usadas como precedente).

Justificativa no domínio: um incidente de infraestrutura resolvido há 90 dias ainda pode ser um precedente útil, mas pesa menos que um recente, porque servidores são reconfigurados, versões mudam e a causa de um "erro 502 intermitente" de três meses atrás pode não valer mais para o mesmo sintoma hoje. Depois de um ano, o ambiente provavelmente já mudou o bastante para o precedente induzir a erro em vez de ajudar — por isso a remoção, não só o rebaixamento, no corte maior.

**Efeito:** entre 90 e 365 dias, o episódio é **rebaixado** (entra na busca por similaridade, mas com peso reduzido, perdendo para episódios recentes em caso de empate); depois de 365 dias, é **removido**. A memória semântica (fatos por cliente) não decai pelo tempo — decai por contradição, quando um fato novo substitui o antigo (ex.: cliente mudou de plano).

### 2.3 Remoção — o titular solicitou: não escolhida (decisão de 12/10/2026)

O enunciado (§5.4) trata as três causas como um cardápio. **O grupo escolheu duas, contradição e
decaimento, e não implementa a remoção a pedido.** Não há função nem comando de remoção no
código.

**A razão.** A remoção responde à privacidade, e o que o sistema guarda de um cliente é pouco e
tem prazo:

- o episódio guarda o `cliente_id` e campos estruturados, sem o nome, o texto do cliente, o log
  anexado nem o texto redigido (§3), e é apagado aos 365 dias (§2.2);
- o fato do cliente tem vocabulário fechado (três chaves, sobre o ambiente técnico) e só entra
  por uma pessoa (§4);
- o checkpoint, que guarda o texto do cliente por inteiro, é apagado ao fim da execução (§1.4).

**O que fica sem resposta, e é limite assumido.** O case é de uma empresa de hospedagem, e uma
de verdade guardaria dado de pessoa. Se um cliente real pedisse a remoção, este sistema não
teria como atender sem apagar tudo (`python src/main.py --reset` recria o banco inteiro). O
identificador ficaria em:

| Estrutura | O que guarda do cliente | Como sai hoje |
|---|---|---|
| `episodios` | `cliente_id`, chamado, guia, desfecho, veredito | só pelo decaimento (365 dias) ou pelo `--reset` |
| `fatos_cliente` | `cliente_id`, chave e valor; o valor substituído continua na tabela, com a data | só pelo `--reset` |
| `pendencias` | a ação como o analista a viu; no H2, com o relato do cliente | só pelo `--reset` |
| Checkpoint | o estado inteiro, com o texto do cliente | apagado ao fim da execução; o da execução pausada fica até a resposta ou o prazo |
| Logs (`logs/**/*.json` e as saídas de terminal) | o nome do cliente e o plano (resultado de `consultar_ticket`), o texto do chamado, o texto redigido, o `cliente_id` no campo `episodio` | **não sai** |
| Memória procedural | nada: nenhuma regra é escrita no prompt (§5) | não se aplica |

**Os logs são o ponto mais difícil.** Aqui eles são versionados no git de propósito, porque são
a evidência das medições, e os dados são fictícios. Apagar ou mascarar um arquivo não tiraria o
dado dos commits anteriores nem dos clones já feitos, e o texto livre (o relato, o que o modelo
redigiu) não é coberto por uma busca pelo nome. Num sistema real a resposta seria de desenho, e
não de remoção: os logs ficariam fora do versionamento, guardariam só o `cliente_id`, com o nome
na tabela de clientes, e teriam prazo de retenção. Nada disso está implementado.

**O que se perde por não ter a remoção.** Das três razões do enunciado para esquecer:

- **privacidade:** sem resposta, como dito acima;
- **custo:** coberto pelo decaimento dos episódios; `fatos_cliente` cresce pouco (uma linha por
  fato confirmado por pessoa);
- **recuperação de incidente:** um fato errado do cliente é corrigido por outro `--fato`, que o
  substitui (contradição). Um episódio errado não tem correção: fica até os 365 dias. Como o
  episódio só avisa o analista e não entra em regra de decisão (§3), o dano é um aviso errado na
  tela do H1.

### 2.4 O preço: o sistema deixou de ser reprodutível

Com memória de longo prazo, a mesma entrada (`TKT-0001`, o caso "simples") pode produzir desfechos diferentes em execuções separadas por semanas: se nesse intervalo o agente acumulou um episódio parecido, ou se uma regra procedural nova entrou no prompt, o comportamento muda mesmo com o mesmo modelo e os mesmos parâmetros. Isso não é defeito: é a consequência direta de ter escolhido, na Decisão 1, um sistema que aprende com o que já viu.

Isso tem um custo concreto para a avaliação (aula 11, e para o próprio verificador deste trabalho): rodar `python src/main.py --todos` duas vezes, em datas diferentes, deixa de ser diretamente comparável, porque a diferença no resultado pode vir do modelo **ou** da memória ter mudado entre as duas rodadas. A separação exige rodar a avaliação com a memória de longo prazo **congelada** (um snapshot fixo do índice episódico e da tabela semântica, o mesmo em ambas as rodadas) sempre que o objetivo for medir o modelo ou o prompt, e só deixar a memória evoluir quando o objetivo for medir o próprio efeito de aprender com o tempo.

## 3. O que existe em código: a memória episódica (11/10/2026)

Decisão do grupo: registro estruturado + sinal do analista, **só como aviso na tela do H1**. O
episódio não entra no `redigir` nem em regra de decisão alguma, e não há leitura por similaridade.

| Pergunta | Resposta, no código |
|---|---|
| Onde fica | tabela `episodios` em `dados/tickets.db` (`db.SQL_EPISODIOS`); nasce em `db.py`, como `pendencias`, e não no seed |
| Quem escreve | o **código**, em `grafo._concluir`, uma linha por execução **concluída** (a pausada no H1 ou no H2 só vira episódio quando o analista responde ou o prazo vence). A escrita é idempotente pela chave do conteúdo (`db.chave_do_episodio`, §1.4) |
| O que guarda | id do chamado, `cliente_id`, classe da triagem, categoria e id do guia proposto, score, ação proposta, desfecho gravado, motivo, veredito do analista (`aprovado`, `editado`, `rejeitado`, `vencido` ou vazio quando não houve H1), término, data real e um resumo montado pelo código |
| O que não guarda | o texto do cliente, o log anexado, o nome do cliente e o texto que o modelo redigiu (teste `test_o_episodio_nao_guarda_o_texto_do_cliente_nem_o_que_o_modelo_redigiu`) |
| Como é lida | `db.precedentes`, por consulta exata: as decisões do analista sobre o guia proposto e os 3 últimos episódios do mesmo cliente na mesma categoria |
| Onde aparece | no campo `precedentes` da pendência do H1 e em linhas `MEMÓRIA:` na tela (`humano.md` §2.1). Os guias `anotar` não passam pelo H1, então para eles a memória é gravada e não é mostrada a ninguém |
| O que muda no desfecho | **nada.** Com três rejeições anteriores do mesmo guia, o grafo propõe e grava a mesma ação (teste `test_o_precedente_so_avisa_e_nao_muda_o_desfecho`) |

**Decaimento (§2.2), como ficou.** Sem ranking por similaridade, "rebaixar" virou "não contar":
até 90 dias (`db.EPISODIO_RECENTE_DIAS`) a decisão entra na contagem do aviso; entre 90 e 365 dias
ela aparece à parte, como antiga, e não conta; depois de 365 dias (`db.EPISODIO_MAX_DIAS`) o
episódio não é lido e é apagado por `db.esquecer_episodios`, que roda no começo de cada comando do
`main.py` (menos `--todos`), como `vencer_pendencias`. Os dois cortes são justificados pelo domínio
e **não foram medidos**: não há episódio real com essa idade, e o teste usa episódios semeados com
data antiga.

**Reprodutibilidade (§2.4).** `--sem-memoria` desliga a leitura e a escrita. `--todos` e `--reset`
recriam o banco, e com ele a tabela `episodios`: as rodadas dos 8 casos partem sempre de uma memória
vazia e continuam comparáveis. A memória só acumula entre execuções avulsas.

**Demonstração com o modelo real** (11/10/2026, `ministral-8b-latest`, código do commit `945d64e`
mais as mudanças desta data): banco recriado; `TKT-0007` pausa no H1 com `precedentes` zerado
(`logs/grafo-memoria-1/`); o analista rejeita; `TKT-0007` roda de novo e a tela traz "o analista
decidiu 1 vez(es) sobre o guia KB-102: 1 rejeitada(s)" e o episódio anterior do cliente
(`logs/grafo-memoria-2/`). Uma execução de cada; o agente propôs a mesma ação nas duas.

**Limites assumidos.**
- A contagem não distingue por que o analista rejeitou: uma rejeição por resumo ruim pesa igual a uma por guia errado.
- Rodar de novo o mesmo chamado conta como precedente dele mesmo (é o caso da demonstração).
- Não há remoção a pedido do titular: o grupo não escolheu essa causa (§2.3). O episódio sai pelo decaimento, e o log não sai. O checkpoint da execução concluída é apagado desde 12/10/2026 (§1.4), o que não é remoção a pedido: é o ciclo de vida dele.
- O laço da Parte 1 (`--laco`) não lê nem grava episódios.
- O log da execução ganhou o campo `episodio` (o registro gravado), e os logs anteriores a esta data não o têm.

## 4. O que existe em código: a memória semântica (11/10/2026)

O §1.3 previa guardar o plano e a reincidência por cliente. Os dois já estão no sistema de tickets
(o plano em `clientes`, a reincidência recalculada em SQL), e guardá-los de novo seria duplicar. O
que foi implementado é outra coisa: **fatos estáveis do ambiente do cliente, confirmados por um
analista**, que o relato não traz e que mudam a leitura de um guia.

### 4.1 As três chaves, e de onde vieram

O vocabulário é fechado (`db.FATOS_ACEITOS`): três chaves, dois valores cada.

| Chave | Valores | Evidência nos casos e medições |
|---|---|---|
| `acesso` | `ssh`, `painel` | O KB-102 e o KB-114 declaram não cobrir "ssh". O nó da ressalva não lê essa situação: 0 de 15 respostas (`rag.md` §4.2), e X5 e X7 são os dois erros que sobraram no sistema inteiro |
| `certificado` | `gerenciado`, `externo` | Dois dos cinco falsos acertos aceitos são sobre certificado de terceiros agindo no KB-101-A: N12 ("certificado SSL que comprei de outra empresa") e N20 (`logs/rag-medicao/triagem.txt`). O KB-101-A é o guia do `TKT-0001` |
| `aplicacao` | `gerenciada`, `propria` | A ficha do plano VPS Pro diz que a aplicação instalada pelo cliente está fora do escopo do suporte, e 3 dos 7 clientes do seed são VPS Pro (os do `TKT-0003`, `TKT-0006` e `TKT-0007`). O N23 age no KB-113 (aplicação PHP) |

### 4.2 Como funciona

| Pergunta | Resposta, no código |
|---|---|
| Onde fica | tabela `fatos_cliente` em `dados/tickets.db` (`db.SQL_FATOS`), criada em `db.py` |
| Quem escreve | só uma pessoa: `python src/main.py --fato CLI-07 acesso=ssh`. O modelo não escreve, e a alegação do cliente não vira fato. Chave ou valor fora do vocabulário, ou cliente inexistente, é recusado. Confirmar de novo o valor que já vale não cria linha, e o retorno traz `ja_existia` (§1.4) |
| Como é lida | por chave exata (`db.fatos_do_cliente`), sem busca |
| Onde aparece | (1) na pendência do H1, campo `fatos_cliente`, e em linhas `FATO CONFIRMADO` da tela; (2) na entrada do nó `conferir_ressalva`, numa seção "Fatos confirmados sobre o ambiente do cliente". Não vai ao `redigir` |
| O que muda no desfecho | o fato não decide nada. Quem pode baixar o score continua sendo a resposta do nó, com a mesma garantia de antes: só baixa, e só com uma situação da lista do guia |
| Como esquece | por contradição: um valor novo para a mesma chave fecha o anterior (`substituido_em`), que fica na tabela. Não decai com o tempo |
| Limite de alcance | o nó só roda quando o primeiro guia declara situações que não cobre. O KB-101-A não declara nenhuma: o fato `certificado=externo` hoje **não muda nada** nos casos N12 e N20, porque esse guia é `anotar` (não passa pelo H1) e o nó não roda nele |

`--sem-memoria` desliga também a leitura dos fatos. `--todos` e `--reset` recriam o banco e apagam
os fatos, como os episódios: as rodadas dos 8 casos partem sem fato nenhum.

### 4.3 O que foi medido

`python src/medir_rag.py fatos [prompt]`, 11/10/2026, `ministral-8b-latest`, `temperature=0`,
3 repetições. Guia KB-102; 7 perguntas de exceção (P7, X2, X5, X6, X7 e as novas X12 e X13) e 7
controles em que o guia cobre o caso (P2, A2, C2, C3, C4 e os novos C9 e C10). Cada pergunta passa
pelo nó em três condições. Respostas certas (exceção barrada, controle não barrado):

| Prompt | Grupo | Sem fato | `acesso=ssh` | `acesso=painel` |
|---|---|---|---|---|
| `ressalva-v1.md` | exceções | 0 de 21 | 21 de 21 | 15 de 21 |
| `ressalva-v1.md` | controles | 21 de 21 | **0 de 21** | 21 de 21 |
| `ressalva-v3.md` | exceções | 0 de 21 | **21 de 21** | 0 de 21 |
| `ressalva-v3.md` | controles | 21 de 21 | **18 de 21** | 21 de 21 |

(`logs/rag-medicao/fatos-ressalva-v1.txt` e `fatos-ressalva-v3.txt`.)

- **Com o prompt antigo, o fato faz mal.** O v1 barra todos os controles do cliente com
  `acesso=ssh`: o fato sozinho vira motivo. Por isso os fatos só entram junto com o
  `ressalva-v3.md`, que é o v1 mais a regra "um fato sozinho não basta".
- **Com o v3 e o fato `acesso=ssh`, as 7 exceções são barradas nas 3 repetições**, inclusive as
  três que escrevem "SSH" no relato e que o v1 não lia.
- **O custo: um controle barrado.** O C3 ("Não consigo gravar arquivos no servidor: permissão
  negada desde a migração.") é barrado nas 3 repetições com `acesso=ssh`. É o erro para o lado
  seguro (fila humana, menos automação), mas é um erro: 1 de 7 controles.
- **Sem fato, nada muda.** O v3 sem fatos repete o v1 em todo o bloco da ressalva
  (`logs/rag-medicao/ressalva-v3.txt`): 24 de 39 nas exceções, 42 de 42 nos controles, e 25 certo,
  1 parcial, 2 errado no sistema inteiro. A situação "ssh" continua sem ser lida para o cliente
  sem fato cadastrado.
- **`acesso=painel` não ajuda nem atrapalha com o v3** (igual a "sem fato").
- **Os 8 casos pelo grafo com o v3:** 8 de 8 (`logs/grafo-fatos/`, uma rodada, sem fatos no banco).
- **De ponta a ponta**, com `acesso=ssh` cadastrado para o cliente do `TKT-0007`: com o texto do X5
  ("permissão negada quando tento acessar o servidor por terminal remoto") o nó respondeu que cai em
  "ssh" e o desfecho foi `fila_humana` (`logs/grafo-fatos-x5/`); com o texto original do chamado
  (upload que falha) o nó respondeu que não cai e o grafo pausou no H1 propondo abrir o chamado, com
  o fato na tela (`logs/grafo-fatos-controle/`). Uma execução de cada.

**Limites assumidos.**
- Só a chave `acesso` foi medida. `certificado` e `aplicacao` chegam à tela e ao nó pelo mesmo
  caminho, e o efeito delas no modelo **não foi medido**.
- Um guia (KB-102), 14 perguntas escritas por nós, um modelo. O exemplo da regra nova do v3 é
  parecido com X5 e X7; X12 e X13 foram escritas depois do prompt, sem repetir o exemplo.
- Um cliente pode ter mais de um fato; a medição usou um fato por cliente.
- O fato vale enquanto ninguém o corrigir: não há data de validade nem revisão periódica.
- Não há remoção a pedido do titular (§2.3): um fato sai da leitura quando outro o substitui, e a linha antiga continua na tabela.
- O laço da Parte 1 não lê fatos.

## 5. O que existe em código: a memória procedural (11/10 e 12/10/2026)

O §1.4 decide que só uma pessoa escreve regra, depois de pelo menos 3 correções do mesmo padrão.
Em 11/10/2026 foi implementado o que vem **antes** da regra: saber por que o analista corrigiu, e
contar os padrões. Essa parte não escreve regra e não manda nada novo ao modelo; é o que este
trecho descreve. A regra carregada no prompt entrou em 12/10/2026 e está no §5.1.

| | O que é | Onde |
|---|---|---|
| Motivo da rejeição | `python src/main.py --rejeitar TKT-0007 --motivo caso_fora_do_guia`. Quatro valores para o chamado interno (H1): `guia_errado`, `caso_fora_do_guia`, `resumo_ruim`, `outro`. Opcional: sem ele a rejeição vale e o motivo fica vazio | `db.MOTIVOS_REJEICAO`; `grafo.retomar_grafo(motivo_rejeicao=...)`; coluna `motivo_rejeicao` de `episodios`; campo `motivo_rejeicao` em `confirmacoes`, no log |
| Motivo da rejeição do pedido ao cliente (H2, 12/10/2026) | `python src/main.py --rejeitar TKT-0005 --motivo informacao_suficiente`. Três valores: `mensagem_ruim`, `informacao_suficiente`, `outro`. Cada ação aceita só os seus: motivo de uma na outra é recusado, e a ação continua à espera | `db.MOTIVOS_POR_ACAO` |
| Tela do H1 | a linha `MEMÓRIA:` separa as rejeições do guia por motivo | `db.precedentes` (`rejeicoes_por_motivo`) |
| Relatório de candidatas | `python src/main.py --candidatas`: os padrões (guia + motivo, e guia + aprovação com edição) com 3 ou mais correções nos últimos 90 dias, e onde uma pessoa deveria olhar. As correções do pedido ao cliente não têm guia: agrupam-se só pelo padrão e aparecem como "pedido ao cliente" | `db.candidatas_a_regra`, `db.MINIMO_CANDIDATA` |

Onde olhar, por padrão: `caso_fora_do_guia` aponta o `nao_cobre` do guia; `guia_errado`, a triagem
e a busca; `resumo_ruim` e aprovação com edição do resumo, o prompt do `redigir` e as regras
aprendidas (§5.1); `mensagem_ruim` e aprovação com edição da mensagem, o texto padrão do pedido
(`grafo.PEDIDO_AO_CLIENTE`), que desde 12/10/2026 não é mais texto do modelo (o relatório
apontava o prompt do `redigir` até essa data);
`informacao_suficiente`, o prompt da triagem (o relato bastava, e o agente pediu informação);
`outro` e rejeição sem motivo são listados sem destino.

**O que o H2 não tem da memória.** A tela do pedido ao cliente não mostra precedentes nem fatos do
cliente: a consulta de precedentes é por guia, e nesse ponto não há guia. O episódio é gravado
como os outros (com `kb_id` vazio e o veredito do analista), sem o relato e sem a mensagem. Os
motivos do H2 e o padrão sem guia estão provados por testes offline
(`test_h2_o_motivo_da_rejeicao_e_o_da_acao_pendente`,
`test_h2_candidata_a_regra_do_pedido_ao_cliente_nao_tem_guia`); com o modelo real só foi
exercitada a recusa de um motivo do H1 (`logs/grafo-h2/`, `humano.md` §2.4).

**O que essa parte não muda no agente.** O grafo é o mesmo (12 nós, as mesmas arestas), nenhum prompt mudou e
não há chamada a mais ao modelo. O desfecho gravado pela rejeição é o de antes (`fila_humana`, motivo
`acao_rejeitada`). O motivo é conferido antes de responder ao `interrupt`: motivo inválido, ou motivo
numa aprovação, é recusado e a ação continua à espera. Uma rejeição depois do prazo vira prazo
vencido, e o motivo não é guardado. O relatório só lê.

**Demonstração com o modelo real** (11/10/2026, `ministral-8b-latest`): banco recriado; o
`TKT-0007` pausou no H1 e foi rejeitado com `caso_fora_do_guia` três vezes
(`logs/grafo-procedural/`); `--candidatas` listou um padrão, "guia KB-102, caso_fora_do_guia: 3
vez(es)", com o destino "revisar o guia: falta declarar a situação em nao_cobre"
(`logs/grafo-procedural/candidatas.txt`); na quarta execução o agente propôs a mesma ação, e a
tela trouxe "3 rejeitada(s) (3 caso_fora_do_guia)" (`logs/grafo-procedural-tela/`). O motivo
escolhido na demonstração é arbitrário: serve para mostrar o mecanismo, e não diz que o KB-102
tem um defeito.

**O que não existe.** A ligação do relatório ao texto corrigido: o `--candidatas` diz o padrão
e a contagem, e não o log em que estão o resumo original e o aprovado. Quem for escrever uma
regra a partir dele precisa achar o log pelo chamado e pela data.

**Limites assumidos.**
- O corte de 3 correções vem do §1.4, e não de medição.
- `--todos` e `--reset` apagam os episódios: o relatório só enxerga execuções avulsas.
- Rodar o mesmo chamado três vezes conta como três correções (foi o que a demonstração fez).
- O motivo é a palavra do analista, num vocabulário de quatro valores; `outro` não orienta nada.
- A rejeição dada na hora por um confirmador fica sem motivo, e o laço da Parte 1 recusa `--motivo`.

### 5.1 A regra carregada no prompt (12/10/2026)

**A estrutura.** A memória procedural guarda como fazer, e a estrutura é **texto no prompt de
sistema**: uma regra vale para toda execução, então não há o que buscar. O texto mora em
`src/prompts/regras-redigir-v2.md`, versionado como os prompts, e `grafo._sistema_do_redigir`
o anexa ao fim do `redigir-v3.md` em toda chamada do nó. A justificativa está no código, no
bloco "MEMÓRIA PROCEDURAL" do fim de `src/grafo.py`.

| | |
|---|---|
| Em que nó | só o `redigir`. É o único nó de modelo que não decide nada: o desfecho chega pronto, então uma regra ruim estraga um texto, e não uma decisão |
| Quem escreve | uma pessoa, à mão, no arquivo. O modelo e o código não escrevem regra. Uma regra por versão do arquivo, medida em rodada própria |
| Volume | 0 escritas por execução. O arquivo em uso tem uma regra, que custa 55 tokens de entrada em cada redação (medido) |
| O que é recusado | regra que cite um cliente ou um chamado (`CLI-`, `TKT-`, `INC-`): a regra nasce do erro num chamado e não pode carregar o titular dele (enunciado §5.4). A conferência é em código, na carga (`grafo._regras_aprendidas`); recusada, a execução termina em `erro_fatal`, sem redigir. O cabeçalho de documentação do arquivo pode citar o chamado de origem, porque não vai ao modelo |
| Como desliga | `--sem-memoria`: o prompt do `redigir` volta a ser só o `redigir-v3.md` |
| No log | o campo `prompt` traz o nome do arquivo de regras, junto dos três prompts |

Testes offline (`tests/test_grafo.py`): `test_as_regras_aprendidas_vao_ao_prompt_do_redigir_e_so_a_ele`,
`test_sem_memoria_as_regras_aprendidas_nao_sao_carregadas` e
`test_regra_que_cita_cliente_ou_chamado_e_recusada`.

**A regra, e de onde veio.** No `TKT-0001` (certificado SSL vencido), a anotação para o analista
citava o domínio "acmecontabilidade.com.br", que não está no relato, no log anexado nem no banco:
o modelo o monta a partir do nome do cliente. O defeito foi achado pelo grupo na leitura das
rodadas (`prompts.md` §2.1 e §2.3), e é a exceção ao corte de 3 correções declarada no §1.4.

**Como é conferida.** `python conferir_regras.py logs/NOME` lê os logs de uma rodada e lista os
domínios do texto redigido que não estão no que o nó recebeu. Não chama a API. Aplicado às dez
rodadas anteriores à regra, achou o domínio inventado em 3 (uma do `redigir-v1.md`, uma do v2 e
uma do v3), sempre no `TKT-0001`.

**A medição.** Três execuções dos 8 casos com cada arquivo, em 12/10/2026, `ministral-8b-latest`,
`temperature=0`, commit `c849ce1 + alterações locais`, contra as três do `redigir-v3.md` sem
regra (`logs/grafo-redigir-v3-1/` a `-3/`, commit `9d5c211 + alterações locais`):

| | sem regra | `regras-redigir-v1.md` (`logs/grafo-regras-v1-1/` a `-3/`) | `regras-redigir-v2.md` (`logs/grafo-regras-v2-1/` a `-3/`) |
|---|---|---|---|
| Verificador | 8 de 8 nas três | 8 de 8 nas três | 8 de 8 nas três |
| Rodadas com domínio inventado | 1 de 3 | **2 de 3** | **0 de 3** |
| Redações reprovadas pelo nó `validar` | 0 de 21 | 0 de 21 | 0 de 21 |
| Tokens de entrada a mais, por redação | | 91 | 55 |
| Tokens, na rodada (entrada + saída) | 13.122 a 13.191 | 13.781 a 13.876 | 13.400 a 13.511 |
| Custo a preço de lista, na rodada | US$ 0,00198 | US$ 0,00207 | US$ 0,00201 a 0,00203 |

- **O v1 não funcionou, e não foi adotado.** A regra proibia ("não monte um domínio a partir do
  nome do cliente") e dava uma frase para pôr no lugar ("domínio não informado"). Nas duas
  rodadas com o defeito, o texto traz o domínio inventado e, colada nele, a frase: "Conferir DNS
  do domínio **acmecontabilidade.com.br** (domínio não informado)". A frase apareceu ainda em
  outros textos, 2 ou 3 dos 7 de cada rodada.
- **O v2 é a mesma regra, dizendo só o que escrever** ("escreva apenas 'o domínio do cliente',
  sem endereço nenhum"). O domínio inventado não apareceu em nenhuma das três rodadas. É o
  arquivo em uso.

**Limites assumidos.**
- **Três rodadas não separam a regra do acaso.** Sem regra o defeito aparece em 1 de 3 rodadas
  (3 de 10, contando as anteriores), e só no `TKT-0001`. Zero em três é compatível com a regra
  funcionar e com sorte. As três rodadas dos 40 casos, do mesmo dia (`logs/grafo-40-1/` a `-3/`,
  `grafo.md` §6.6), somam mais três sem o defeito: 38 redações em cada uma, nenhuma com domínio
  que o nó não recebeu. São seis rodadas em zero, e não há rodada dos 40 casos sem a regra para
  comparar.
- **A regra tem um efeito que ninguém pediu.** A expressão "o domínio do cliente" passou a
  aparecer em 3 a 5 dos 7 textos de cada rodada (sem a regra, em nenhum), e em parte deles o
  texto não falava de domínio: "O domínio do cliente apresenta falha no upload de arquivos"
  (`TKT-0007`). Não está errado, e é pior do que o texto de antes.
- **A conferência só enxerga domínio**, por expressão regular. Os outros textos foram lidos, e
  não há verificador de conteúdo (`prompts.md` §1).
- **A regra não veio das 3 correções do analista** (§1.4). O caminho do relatório `--candidatas`
  até uma regra nunca foi percorrido com correções de verdade.
- **Nenhuma regra é esquecida sozinha.** Sair do prompt é apagar a linha do arquivo, numa versão
  nova; não há decaimento nem contradição para regras (§2).

## O que o agente não guarda, e o que perde quando perde

O agente **não guarda**: o conteúdo bruto dos anexos de log depois que a execução termina (com as três pendências do §1.4: o `anexo_log` nos arquivos de log, o relato na pendência resolvida do H2 e o `Estado` na pendência resolvida do laço); qualquer afirmação do cliente não confirmada pelo histórico do sistema; e qualquer fato recalculável, como a reincidência.

**O que ele perde, por não guardar isso:** perde a capacidade de, meses depois, reconstruir *por que* um chamado antigo foi tratado de um jeito específico a partir do log bruto original — só o resumo estruturado sobrevive, então um detalhe do log original que não entrou no resumo da época está perdido para sempre, mesmo que o chamado continue relevante. É uma perda aceita conscientemente: o custo de manter dado potencialmente sensível "só por garantia" pesa mais do que essa perda pontual de detalhe, e é o mesmo princípio já aplicado no resto do case — na dúvida, o sistema erra para o lado que preserva menos, não mais.
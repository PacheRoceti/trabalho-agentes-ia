# Memória do agente (Exercício 8 / §5 da Parte 2)

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

> Este documento não descreve código existente: o agente da Parte 1 **não tem
> memória** — cada execução parte do zero, olha só o chamado que recebeu e
> esquece tudo ao terminar. O que segue são as decisões de projeto que
> precisam ser tomadas **antes** de construir a memória no par prático
> (08-complementar), aplicadas ao domínio do case: um agente de triagem que
> consulta chamados, base de conhecimento e histórico de um sistema de
> hospedagem de servidores.

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
- **semântica**: o **código** também, por regra determinística (a mesma consulta SQL que já existe), nunca o modelo — um fato como "plano do cliente" tem peso de negócio demais para depender de o modelo tê-lo lido certo;
- **procedural**: só o **humano** (analista ou o grupo), em revisão, nunca automático — é a lição da rodada 2: prompt mexido sem supervisão piorou o resultado de 5 para 3 em 7. Uma regra procedural só entra no prompt depois de aparecer em pelo menos 3 correções do mesmo padrão, revisadas por uma pessoa.

**Volume por execução:** 1 registro episódico (≈150 a 250 tokens); 0 ou 1 atualização semântica (só quando um fato realmente muda — o plano do cliente, por exemplo; não a cada execução); 0 escritas procedurais por execução (é processo em lote, periódico, não por chamado).

**O que o sistema não guarda:**
- **dado sensível não verificado** — o `anexo_log` do cliente (que pode conter hostname, IP, e por acidente uma credencial colada) não é gravado verbatim em nenhuma memória de longo prazo; só o resumo estruturado (categoria, KB usado) sobrevive à execução. O checkpoint, que guarda o log por inteiro enquanto a execução está viva, é apagado quando ela termina. Pendência: hoje o `logs/TKT-xxxx.json` grava o resultado de `consultar_ticket` com o anexo inteiro; para esta regra valer, o campo `anexo_log` precisa ser redigido no log ao fim da execução;
- **conteúdo não verificado vindo de fora** — a afirmação do próprio cliente ("é a terceira vez", "prioridade máxima") nunca vira fato semântico. É exatamente a regra que o prompt já aplica ("afirmação a verificar", em `agente-v3.md`): só o que o **histórico do sistema** confirma pode virar memória de longo prazo; a alegação do cliente fica só no registro episódico daquela execução específica, nunca promovida a fato sobre o cliente;
- **o que é derivável** — a reincidência, como já dito, nunca é armazenada como valor fixo: é recalculada por consulta, porque depende da janela de 30 dias. Guardar um valor que pode ficar desatualizado (e nenhum mecanismo de decaimento cobrindo justamente ele) seria dívida sem necessidade.

### 1.5 A conversa com o cliente (§5.5)

O agente só conversa com o cliente em um caso: quando falta informação para classificar o chamado, ele envia **um** pedido, depois da confirmação do analista, e espera a resposta (regra em `docs/case.md` §2.1). As quatro decisões da conversa, nesse cenário:

**O que identifica uma conversa.** `thread_id` = id do chamado externo (`TKT-xxxx`). Cada chamado é uma conversa: a mesma pessoa com dois chamados abertos ao mesmo tempo tem duas conversas independentes, e a resposta de um não contamina a triagem do outro. A resposta do cliente chega pelo próprio chamado, então ela já carrega o id que a leva de volta à conversa certa.

**Onde o checkpoint é gravado.** Em SQLite, num arquivo próprio ao lado do banco simulado (`dados/`), e não em memória. A espera pelo cliente pode durar até 3 dias úteis; com checkpoint em memória, a conversa morreria com o processo e a resposta chegaria a uma execução que não sabe que o pedido foi feito — e poderia pedir de novo.

**O que acontece quando a janela enche.** Na prática, não enche: a conversa tem no máximo duas mensagens do cliente (o chamado original e uma resposta), porque o agente faz um único pedido. A retomada não reaproveita a trajetória antiga inteira: ela recomeça a triagem com o texto original + a resposta e mantém do checkpoint só o que é decisão (o pedido já feito, o orçamento já gasto). Se mesmo assim o contexto estourar, vale a ordem de descarte do §1.2 — e o texto do cliente nunca é descartado.

**O que passa da conversa para a memória de longo prazo.** Só o fato de que houve pedido e se ele resolveu, no registro episódico da execução (ex.: "TKT-0005: pediu serviço e sintoma; cliente respondeu; abriu chamado P1"). O texto da resposta do cliente fica no chamado e no checkpoint, que é apagado quando a conversa termina; ele não vira memória semântica pela mesma regra do §1.4: afirmação do cliente não é fato verificado.

## Decisão 2 — Como o agente esquece

### 2.1 Contradição — o fato que mudou

No case, o que mais pode se contradizer são os **procedimentos técnicos** (fonte D de `docs/base-de-conhecimento-v2.md`), porque é deles que vêm o time de destino e a prioridade de cada chamado. Exemplo: a versão antiga do procedimento de SSL (KB-101) mandava renovar o certificado manualmente pelo painel e escalar para a Segurança com P1; a versão vigente (KB-101-A) manda conferir o certbot e anotar para a Infraestrutura com P2. Os dois textos são igualmente parecidos com o relato "meu certificado SSL venceu", e a busca por similaridade não tem como saber qual vale. Se a versão antiga vencer, o erro não fica no texto: vira um chamado P1 aberto para o time errado.

**Regra de desempate:** todo trecho indexado — procedimentos técnicos e catálogo de planos — carrega `data_publicacao` e `revogado_por` (previstos em `docs/base-de-conhecimento-v2.md`; as duas colunas existem em `kb_artigos` desde 11/10/2026). Um trecho com `revogado_por` preenchido é filtrado antes da busca; entre duas versões vigentes do **mesmo procedimento** (o mesmo id sem a letra: `KB-101`, `KB-101-A`, `KB-101-B`), vale `max(data_publicacao)`, e a letra mais adiante só decide entre versões publicadas no mesmo dia. As duas regras estão implementadas em `db.buscar_kb` para os procedimentos técnicos e foram medidas em 11/10/2026 (`docs/rag.md` §2.1); o catálogo de planos não existe no repositório. Trechos de procedimentos ou subcenários diferentes não são desempatados por data: concorrem pelo score. Não é o modelo que decide: é um filtro e uma comparação de datas em código, determinísticos e testáveis.

**O descarte é registrado**, não silencioso: quando um fato perde para outro mais recente, isso fica no log da busca (o resultado de `buscar_base_conhecimento` traz, no guia que ficou, `data_publicacao` e `versoes_descartadas`, com o id e a data de cada versão antiga que também casava; implementado em 11/10/2026), para que uma auditoria consiga distinguir "não achou nada" de "achou dois e escolheu o mais novo".

### 2.2 Decaimento — o fato que envelheceu sem ser contradito

**Corte proposto: 90 dias para rebaixar, 365 dias para remover**, aplicado à memória **episódica** (execuções passadas usadas como precedente).

Justificativa no domínio: um incidente de infraestrutura resolvido há 90 dias ainda pode ser um precedente útil, mas pesa menos que um recente, porque servidores são reconfigurados, versões mudam e a causa de um "erro 502 intermitente" de três meses atrás pode não valer mais para o mesmo sintoma hoje. Depois de um ano, o ambiente provavelmente já mudou o bastante para o precedente induzir a erro em vez de ajudar — por isso a remoção, não só o rebaixamento, no corte maior.

**Efeito:** entre 90 e 365 dias, o episódio é **rebaixado** (entra na busca por similaridade, mas com peso reduzido, perdendo para episódios recentes em caso de empate); depois de 365 dias, é **removido**. A memória semântica (fatos por cliente) não decai pelo tempo — decai por contradição, quando um fato novo substitui o antigo (ex.: cliente mudou de plano).

### 2.3 Remoção — o titular solicitou

**Estruturas em que o identificador de um cliente pode ter caído**, além das três memórias:

| Estrutura | Por que o identificador está lá | Como remover |
|---|---|---|
| Memória episódica | o texto do chamado e o resumo do desfecho citam o cliente | remover o registro do índice por `cliente_id` |
| Memória semântica | é, por definição, indexada por `cliente_id` | remover a linha da tabela |
| Memória procedural | improvável, mas possível: uma regra aprendida a partir da correção de um caso específico pode, por descuido, ter sido escrita citando o cliente em vez de generalizada | busca textual pelo nome/id no prompt; se achar, reescrever a regra de forma genérica ou remover |
| **Checkpoint** | os `passos` guardam os argumentos passados às ferramentas, que incluem o texto do chamado e, portanto, dados do cliente; o `pedido_cliente` guarda a resposta do cliente | apagar o checkpoint da execução (ou das execuções) daquele `id_ticket`/`cliente_id` |
| **Log** (`logs/*.json`) | grava argumentos e resultados de cada chamada de ferramenta, incluindo `consultar_ticket` (nome do cliente, plano) e o `resumo` gravado em `abrir_chamado_interno` | apagar ou redigir (substituir por `[removido]`) os campos que citam o cliente nos arquivos de log daquele ticket |

**Verificação, independente da remoção:** depois de apagar, varrer todas as cinco estruturas acima procurando o identificador (`cliente_id`, nome do cliente, e-mail se houver) — uma busca de texto simples nos arquivos de log e no checkpoint, uma consulta `WHERE cliente_id = ?` nas tabelas semânticas e episódicas, e uma busca textual no prompt para a procedural. Só depois dessa varredura não encontrar nada é que a remoção pode ser declarada concluída. Rodar o `delete()` e confiar no retorno não basta — foi o mesmo erro, em espírito, que o verificador do case já pegou uma vez (o modelo dizer "registrei" sem ter registrado): a alegação de que algo foi feito não substitui checar que foi.

**Sobre reconstrução de índice:** na escala deste projeto (algumas centenas a poucos milhares de episódios por ano), o índice de similaridade episódico pode ser um índice simples (lista de embeddings, sem estrutura compilada tipo ANN), o que torna a remoção um recorte direto na lista, sem custo de reconstrução. Essa é uma escolha deliberada para **evitar** o problema descrito no exercício: se o volume crescer a ponto de exigir um índice compilado que só suporta remoção por reconstrução completa, isso precisa ser declarado explicitamente nesse momento, porque nessa hora a remoção deixa de ser imediata e a memória fica, na prática, permanente até a próxima janela de manutenção.

### 2.4 O preço: o sistema deixou de ser reprodutível

Com memória de longo prazo, a mesma entrada (`TKT-0001`, o caso "simples") pode produzir desfechos diferentes em execuções separadas por semanas: se nesse intervalo o agente acumulou um episódio parecido, ou se uma regra procedural nova entrou no prompt, o comportamento muda mesmo com o mesmo modelo e os mesmos parâmetros. Isso não é defeito: é a consequência direta de ter escolhido, na Decisão 1, um sistema que aprende com o que já viu.

Isso tem um custo concreto para a avaliação (aula 11, e para o próprio verificador deste trabalho): rodar `python src/main.py --todos` duas vezes, em datas diferentes, deixa de ser diretamente comparável, porque a diferença no resultado pode vir do modelo **ou** da memória ter mudado entre as duas rodadas. A separação exige rodar a avaliação com a memória de longo prazo **congelada** (um snapshot fixo do índice episódico e da tabela semântica, o mesmo em ambas as rodadas) sempre que o objetivo for medir o modelo ou o prompt, e só deixar a memória evoluir quando o objetivo for medir o próprio efeito de aprender com o tempo.

## 3. O que existe em código: a memória episódica (11/10/2026)

Decisão do grupo: registro estruturado + sinal do analista, **só como aviso na tela do H1**. O
episódio não entra no `redigir` nem em regra de decisão alguma, e não há leitura por similaridade.

| Pergunta | Resposta, no código |
|---|---|
| Onde fica | tabela `episodios` em `dados/tickets.db` (`db.SQL_EPISODIOS`); nasce em `db.py`, como `pendencias`, e não no seed |
| Quem escreve | o **código**, em `grafo._concluir`, uma linha por execução **concluída** (a pausada no H1 só vira episódio quando o analista responde ou o prazo vence) |
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
- A remoção a pedido do titular (§2.3) **não está implementada** para a tabela `episodios`; os logs e o checkpoint também continuam como estavam.
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
| Quem escreve | só uma pessoa: `python src/main.py --fato CLI-07 acesso=ssh`. O modelo não escreve, e a alegação do cliente não vira fato. Chave ou valor fora do vocabulário, ou cliente inexistente, é recusado |
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
- A remoção a pedido do titular (§2.3) não está implementada para `fatos_cliente`.
- O laço da Parte 1 não lê fatos.

## 5. O que existe em código: a parte da memória procedural que não muda o prompt (11/10/2026)

O §1.4 decide que só uma pessoa escreve regra, depois de pelo menos 3 correções do mesmo padrão.
O que foi implementado é o que vem **antes** da regra: saber por que o analista corrigiu, e contar
os padrões. **Nenhuma regra é escrita, e nada novo vai ao modelo.**

| | O que é | Onde |
|---|---|---|
| Motivo da rejeição | `python src/main.py --rejeitar TKT-0007 --motivo caso_fora_do_guia`. Quatro valores para o chamado interno (H1): `guia_errado`, `caso_fora_do_guia`, `resumo_ruim`, `outro`. Opcional: sem ele a rejeição vale e o motivo fica vazio | `db.MOTIVOS_REJEICAO`; `grafo.retomar_grafo(motivo_rejeicao=...)`; coluna `motivo_rejeicao` de `episodios`; campo `motivo_rejeicao` em `confirmacoes`, no log |
| Motivo da rejeição do pedido ao cliente (H2, 12/10/2026) | `python src/main.py --rejeitar TKT-0005 --motivo informacao_suficiente`. Três valores: `mensagem_ruim`, `informacao_suficiente`, `outro`. Cada ação aceita só os seus: motivo de uma na outra é recusado, e a ação continua à espera | `db.MOTIVOS_POR_ACAO` |
| Tela do H1 | a linha `MEMÓRIA:` separa as rejeições do guia por motivo | `db.precedentes` (`rejeicoes_por_motivo`) |
| Relatório de candidatas | `python src/main.py --candidatas`: os padrões (guia + motivo, e guia + aprovação com edição) com 3 ou mais correções nos últimos 90 dias, e onde uma pessoa deveria olhar. As correções do pedido ao cliente não têm guia: agrupam-se só pelo padrão e aparecem como "pedido ao cliente" | `db.candidatas_a_regra`, `db.MINIMO_CANDIDATA` |

Onde olhar, por padrão: `caso_fora_do_guia` aponta o `nao_cobre` do guia; `guia_errado`, a triagem
e a busca; `resumo_ruim`, `mensagem_ruim` e aprovação com edição, o prompt do `redigir`;
`informacao_suficiente`, o prompt da triagem (o relato bastava, e o agente pediu informação);
`outro` e rejeição sem motivo são listados sem destino.

**O que o H2 não tem da memória.** A tela do pedido ao cliente não mostra precedentes nem fatos do
cliente: a consulta de precedentes é por guia, e nesse ponto não há guia. O episódio é gravado
como os outros (com `kb_id` vazio e o veredito do analista), sem o relato e sem a mensagem. Os
motivos do H2 e o padrão sem guia estão provados por testes offline
(`test_h2_o_motivo_da_rejeicao_e_o_da_acao_pendente`,
`test_h2_candidata_a_regra_do_pedido_ao_cliente_nao_tem_guia`); com o modelo real só foi
exercitada a recusa de um motivo do H1 (`logs/grafo-h2/`, `humano.md` §2.4).

**O que não muda no agente.** O grafo é o mesmo (12 nós, as mesmas arestas), nenhum prompt mudou e
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

**O que não existe.** O arquivo de regras carregado junto de um prompt, com cada regra datada,
ligada aos episódios de origem e medida antes de entrar; e o teste que recusa regra citando
cliente ou chamado (§2.3). Isso muda o que vai ao modelo e exige nova medição.

**Limites assumidos.**
- O corte de 3 correções vem do §1.4, e não de medição.
- `--todos` e `--reset` apagam os episódios: o relatório só enxerga execuções avulsas.
- Rodar o mesmo chamado três vezes conta como três correções (foi o que a demonstração fez).
- O motivo é a palavra do analista, num vocabulário de quatro valores; `outro` não orienta nada.
- A rejeição dada na hora por um confirmador fica sem motivo, e o laço da Parte 1 recusa `--motivo`.

## O que o agente não guarda, e o que perde quando perde

O agente **não guarda**: o conteúdo bruto dos anexos de log depois que a execução termina (com a redação do `anexo_log` nos arquivos de log, pendência do §1.4); qualquer afirmação do cliente não confirmada pelo histórico do sistema; e qualquer fato recalculável, como a reincidência.

**O que ele perde, por não guardar isso:** perde a capacidade de, meses depois, reconstruir *por que* um chamado antigo foi tratado de um jeito específico a partir do log bruto original — só o resumo estruturado sobrevive, então um detalhe do log original que não entrou no resumo da época está perdido para sempre, mesmo que o chamado continue relevante. É uma perda aceita conscientemente: o custo de manter dado potencialmente sensível "só por garantia" pesa mais do que essa perda pontual de detalhe, e é o mesmo princípio já aplicado no resto do case — na dúvida, o sistema erra para o lado que preserva menos, não mais.
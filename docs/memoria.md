# Memória do agente (Exercício 8 / §4 da Parte 2)

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
| O que é | a janela de uma execução de triagem (um `TKT-xxxx`) | o que atravessa chamados diferentes, de clientes diferentes, em dias diferentes |
| Conteúdo, no case | prompt do sistema (`prompts/agente-v3.md`), o objetivo ("Chamado a triar: TKT-0002"), a trajetória (as chamadas de `consultar_ticket`, `buscar_base_conhecimento` e seus resultados), os trechos da base de conhecimento recuperados nesta busca | episódica (execuções passadas), semântica (fatos estáveis sobre clientes e times), procedural (regras de triagem aprendidas) |
| Persistido como | **checkpoint**: um registro por execução, indexado por `execucao_id` (o campo já existe no `Estado`) | índice por similaridade (episódica), tabela chave-valor (semântica), texto dentro do próprio prompt (procedural) |
| Lido | uma vez, ao retomar uma execução parada | a cada passo do laço em que o modelo pode se beneficiar de um fato ou um precedente |
| Acesso | por `execucao_id` | por relevância (episódica), por chave `cliente_id`/categoria (semântica), carregado sempre (procedural) |
| Ciclo de vida | morre quando a execução termina (`respondeu`, `orcamento_esgotado`, `erro_fatal`); **sobrevive** enquanto o término for `aguardando_humano` | acumula entre execuções, sujeita às três causas de esquecimento da Decisão 2 |

**O que exatamente vai para o checkpoint.** Hoje o objeto `Estado` já concentra quase tudo que um checkpoint precisaria guardar; a mudança é persisti-lo fora do processo em vez de deixá-lo morrer com ele. Os campos, e por quê:

- `id_ticket`, `execucao_id`, `historico` (as mensagens já trocadas com o modelo) — para retomar sem reconstruir o contexto do zero;
- `passos` já executados, com seus resultados — para **não repetir** uma leitura já feita (`consultar_ticket`, `buscar_base_conhecimento`) nem, mais importante, uma escrita: a chave de idempotência do `abrir_chamado_interno` (`ticket:kb_id`) já impede duplicata mesmo sem checkpoint, mas o checkpoint evita a chamada redundante que geraria custo e log confuso;
- `pendencia` — os argumentos exatos da ação irreversível que aguarda confirmação, para o analista poder aprovar **horas depois**, de outro processo (hoje `confirmar()` é síncrona: espera a resposta no mesmo terminal; um checkpoint é o que torna a confirmação assíncrona possível);
- `n_chamadas_modelo`, `tokens`, `custo_usd`, o instante de início — para o orçamento continuar contando certo na retomada, em vez de reiniciar e permitir um caso que já gastou 25 dos 30 mil tokens permitidos continuar por mais 30 mil;
- `scores_kb` — para não recalcular a busca e, principalmente, para a decisão de reabrir ou não a busca (score abaixo do limiar) ser auditável depois;
- `desfecho`, se já existir — para o caso de a execução cair **depois** de já ter escrito no banco (o registro venceu, o processo caiu): retomar não deve tentar escrever de novo.

Isso responde às três perguntas do enunciado: (a) retomável sem reaplicar efeito colateral, porque a idempotência e o `desfecho` já gravado impedem reexecutar a escrita; (b) aprovação humana horas depois, porque a `pendencia` fica persistida em vez de presa a um `input()` de terminal; (c) estado defeituoso reproduzível, porque o checkpoint é exatamente o `logs/TKT-xxxx.json` que já usamos para depurar as falhas das rodadas 1 a 3 — só falta ele existir **antes** do fim da execução, não só depois.

### 1.2 O orçamento da janela

Cinco fontes disputam a janela de uma chamada ao modelo. Medido a partir do `prompts/agente-v3.md` e dos schemas em `src/ferramentas.py`:

| Fonte | Teto (tokens) | Medido / justificativa |
|---|---|---|
| System prompt | 900 (fixo) | ~860 tokens, medido. Nunca é cortado: sem ele o modelo não sabe as regras (é o que a rodada 2 mostrou ao mexer nele sem cuidado) |
| Objetivo ("Chamado a triar: TKT-xxxx") | 30 (fixo) | uma linha; nunca é cortado |
| Schemas das 4 ferramentas | 750 (fixo) | ~730 tokens, medido; parte do contrato de tool calling, não é opcional |
| Trajetória (passos já dados nesta execução) | 3.000, variável | cresce a cada chamada (observado: 400 a 1.500 tokens por chamada nas rodadas reais). Quando estoura, **descarta os passos mais antigos**, nunca o mais recente — é o inverso do corte ingênuo pelo fim, que apagaria justo o que acabou de acontecer |
| Trechos recuperados (top-3 da busca) | 500 | ~110 a 150 tokens por artigo, medido; 3 artigos cabem com folga |
| Memória de longo prazo (recall episódico + semântico) | 700 | orçamento novo, proposto: 1 a 2 episódios similares (~250 tokens cada) + fatos semânticos do cliente (~100 tokens) |

Total fixo + variável em operação normal: ≈ 6.500 tokens, dentro de uma janela de trabalho assumida de 8.000 tokens (número conservador; os modelos usados no plano gratuito da conta suportam mais, mas o laço deve caber com folga mesmo num provedor mais restrito).

**O que é descartado primeiro quando o total estoura, nesta ordem:**
1. memória de longo prazo (é a mais nova, a mais opcional, e a Parte 1 inteira já funcionou sem ela);
2. trechos recuperados, de 3 para 1 artigo (o de maior score);
3. passos mais antigos da trajetória, um de cada vez, até caber — nunca o passo mais recente, nunca o prompt, nunca o objetivo.

### 1.3 As três memórias de longo prazo, no case

| Tipo | O que guarda no case | Estrutura | Como é recuperada |
|---|---|---|---|
| **Episódica** | Um registro por execução concluída: `id_ticket`, categoria, `kb_id` usado, desfecho, se foi confirmado ou recusado pelo analista, e um resumo curto do que aconteceu (ex.: "TKT-0002: relato de webmail fora do ar, log mostrou DNS, foi para fila humana") | índice por similaridade (embedding do texto do chamado + resumo do desfecho) | por similaridade com o texto do chamado atual, no passo de busca — para achar precedentes parecidos, não só procedimentos da base |
| **Semântica** | Fatos estáveis por cliente: plano contratado, time historicamente responsável por incidentes dele, e — a parte que mais importa — contagem de reincidência **por categoria**, hoje já calculada em SQL (`_reincidencia` em `src/db.py`) a partir da tabela `chamados_internos` | chave-valor, chave = `cliente_id` + categoria | por chave exata, uma consulta, não uma busca |
| **Procedural** | Regras de triagem aprendidas a partir de correções do analista: quando o analista reverte uma decisão do agente (por exemplo, confirma um `fila_humana` que devia ter sido `abrir_chamado_interno`) repetidamente para o mesmo padrão de caso, isso vira candidato a regra no prompt | texto dentro do próprio *system prompt* (como as três versões `agente-v1/v2/v3.md` já são, hoje, versionadas manualmente) | sempre carregada, porque é o próprio prompt |

A reincidência é o exemplo mais claro de por que a estrutura decorre do padrão de acesso: ela **já é semântica** hoje, só que recalculada a cada consulta em vez de armazenada — o que é a escolha certa (ver "o que é derivável", abaixo), então o item da tabela acima registra a decisão de **manter** assim, não de criar um novo armazenamento.

### 1.4 Quem escreve, o volume, e o que não entra

**Quem escreve:**
- **episódica**: o **código** extrai, ao fim de cada execução (`Termino.RESPONDEU`), os campos estruturados do `Estado` — nunca o texto livre que o modelo escreveu como resposta final, porque texto livre é exatamente o que a rodada 2 mostrou não ser confiável ("registrei" sem ter registrado);
- **semântica**: o **código** também, por regra determinística (a mesma consulta SQL que já existe), nunca o modelo — um fato como "plano do cliente" tem peso de negócio demais para depender de o modelo tê-lo lido certo;
- **procedural**: só o **humano** (analista ou o grupo), em revisão, nunca automático — é a lição da rodada 2: prompt mexido sem supervisão piorou o resultado de 5 para 3 em 7. Uma regra procedural só entra no prompt depois de aparecer em pelo menos 3 correções do mesmo padrão, revisadas por uma pessoa.

**Volume por execução:** 1 registro episódico (≈150 a 250 tokens); 0 ou 1 atualização semântica (só quando um fato realmente muda — plano, time responsável; não a cada execução); 0 escritas procedurais por execução (é processo em lote, periódico, não por chamado).

**O que o sistema não guarda:**
- **dado sensível não verificado** — o `anexo_log` do cliente (que pode conter hostname, IP, e por acidente uma credencial colada) não é gravado verbatim em nenhuma memória de longo prazo; só o resumo estruturado (categoria, KB usado) sobrevive à execução. O checkpoint, que guarda o log por inteiro enquanto a execução está viva, é apagado quando ela termina;
- **conteúdo não verificado vindo de fora** — a afirmação do próprio cliente ("é a terceira vez", "prioridade máxima") nunca vira fato semântico. É exatamente a regra que o prompt já aplica ("afirmação a verificar", em `agente-v3.md`): só o que o **histórico do sistema** confirma pode virar memória de longo prazo; a alegação do cliente fica só no registro episódico daquela execução específica, nunca promovida a fato sobre o cliente;
- **o que é derivável** — a contagem de reincidência, como já dito, nunca é armazenada como valor fixo: é recalculada por consulta. Guardar um número que pode ficar desatualizado (e nenhum mecanismo de decaimento cobrindo justamente ele) seria dívida sem necessidade.

## Decisão 2 — Como o agente esquece

### 2.1 Contradição — o fato que mudou

O próprio repositório já tem um exemplo real, encontrado durante a Parte 1: o SLA de prioridade P1 aparece como **2h** em `docs/case.md` e como **4h** em `docs/base-de-conhecimento-v1.md` — dois documentos que, se ambos fossem indexados sem controle de tempo, responderiam à mesma pergunta ("qual o SLA de P1?") com valores diferentes, e a busca por similaridade não tem como saber qual é o vigente: os dois textos são igualmente parecidos com a pergunta.

**Regra de desempate:** todo fato armazenado — nas fontes A (política de SLA) e D (procedimentos) da base de conhecimento — carrega um carimbo `data_publicacao` (já previsto em `base-de-conhecimento-v1.md`, hoje sem uso real). Na leitura, quando dois fatos concorrem para a mesma pergunta, vale `max(data_publicacao)`. Não é o modelo que decide: é uma comparação de datas em código, determinística e testável.

**O descarte é registrado**, não silencioso: quando um fato perde para outro mais recente, isso fica no log da busca (`buscar_base_conhecimento` passa a incluir, no resultado, os artigos descartados por contradição e a data que venceu), para que uma auditoria consiga distinguir "não achou nada" de "achou dois e escolheu o mais novo".

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
| **Checkpoint** | os `passos` guardam os argumentos passados às ferramentas, que incluem o texto do chamado e, portanto, dados do cliente | apagar o checkpoint da execução (ou das execuções) daquele `id_ticket`/`cliente_id` |
| **Log** (`logs/*.json`) | grava argumentos e resultados de cada chamada de ferramenta, incluindo `consultar_ticket` (nome do cliente, plano) e o `resumo` gravado em `abrir_chamado_interno` | apagar ou redigir (substituir por `[removido]`) os campos que citam o cliente nos arquivos de log daquele ticket |

**Verificação, independente da remoção:** depois de apagar, varrer todas as cinco estruturas acima procurando o identificador (`cliente_id`, nome do cliente, e-mail se houver) — uma busca de texto simples nos arquivos de log e no checkpoint, uma consulta `WHERE cliente_id = ?` nas tabelas semânticas e episódicas, e uma busca textual no prompt para a procedural. Só depois dessa varredura não encontrar nada é que a remoção pode ser declarada concluída. Rodar o `delete()` e confiar no retorno não basta — foi o mesmo erro, em espírito, que o verificador do case já pegou uma vez (o modelo dizer "registrei" sem ter registrado): a alegação de que algo foi feito não substitui checar que foi.

**Sobre reconstrução de índice:** na escala deste projeto (algumas centenas a poucos milhares de episódios por ano), o índice de similaridade episódico pode ser um índice simples (lista de embeddings, sem estrutura compilada tipo ANN), o que torna a remoção um recorte direto na lista, sem custo de reconstrução. Essa é uma escolha deliberada para **evitar** o problema descrito no exercício: se o volume crescer a ponto de exigir um índice compilado que só suporta remoção por reconstrução completa, isso precisa ser declarado explicitamente nesse momento, porque nessa hora a remoção deixa de ser imediata e a memória fica, na prática, permanente até a próxima janela de manutenção.

### 2.4 O preço: o sistema deixou de ser reprodutível

Com memória de longo prazo, a mesma entrada (`TKT-0001`, o caso "simples") pode produzir desfechos diferentes em execuções separadas por semanas: se nesse intervalo o agente acumulou um episódio parecido, ou se uma regra procedural nova entrou no prompt, o comportamento muda mesmo com o mesmo modelo e os mesmos parâmetros. Isso não é defeito: é a consequência direta de ter escolhido, na Decisão 1, um sistema que aprende com o que já viu.

Isso tem um custo concreto para a avaliação (aula 11, e para o próprio verificador deste trabalho): rodar `python src/main.py --todos` duas vezes, em datas diferentes, deixa de ser diretamente comparável, porque a diferença no resultado pode vir do modelo **ou** da memória ter mudado entre as duas rodadas. A separação exige rodar a avaliação com a memória de longo prazo **congelada** (um snapshot fixo do índice episódico e da tabela semântica, o mesmo em ambas as rodadas) sempre que o objetivo for medir o modelo ou o prompt, e só deixar a memória evoluir quando o objetivo for medir o próprio efeito de aprender com o tempo.

## O que o agente não guarda, e o que perde quando perde

O agente **não guarda**: o conteúdo bruto dos anexos de log depois que a execução termina; qualquer afirmação do cliente não confirmada pelo histórico do sistema; e qualquer fato recalculável, como a contagem de reincidência.

**O que ele perde, por não guardar isso:** perde a capacidade de, meses depois, reconstruir *por que* um chamado antigo foi tratado de um jeito específico a partir do log bruto original — só o resumo estruturado sobrevive, então um detalhe do log original que não entrou no resumo da época está perdido para sempre, mesmo que o chamado continue relevante. É uma perda aceita conscientemente: o custo de manter dado potencialmente sensível "só por garantia" pesa mais do que essa perda pontual de detalhe, e é o mesmo princípio já aplicado no resto do case — na dúvida, o sistema erra para o lado que preserva menos, não mais.

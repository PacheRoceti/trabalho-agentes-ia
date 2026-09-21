# Case — Agente de Triagem e Abertura de Chamado Interno

> Esta é a v2 do case, atualizada após a mudança de escopo: o projeto deixou de ser um agente gerador de dashboard de consolidação e passou a ser um agente que analisa o chamado do cliente, consulta a base de conhecimento interna e propõe uma solução ou abre um chamado interno. Mais detalhes em `docs/arquitetura-v1.md` (desenho no papel), `docs/arquitetura-v2.md` (o que foi construído na Parte 1) e `docs/base-de-conhecimento-v1.md`.

## 2 O Tema e o Contexto

### 2.1 O Problema

**Quem sofre:** Analistas de suporte da empresa — operações de Suporte/Customer Success de uma empresa de hospedagem de servidores e serviços (hosting) para clientes externos.

**O problema, em uma frase.**

> Excesso de trabalho manual no processo de ingresso dos chamados e falta de padronização das informações dos chamados internos.

**O contexto.**

*O que acontece hoje, sem o sistema:* cada chamado aberto por um cliente externo passa primeiro pelas mãos de um analista, que precisa ler a descrição livre do problema, decidir se é algo já documentado, se é uma dúvida comercial/financeira fora do escopo do suporte, ou se precisa ser escalado para outro time interno — e então abrir manualmente o chamado interno correspondente. Como cada analista faz essa triagem e esse registro do seu próprio jeito, as informações que chegam ao time de destino não seguem um padrão fixo (categoria, resumo, nível de certeza da causa variam de analista para analista), o que atrasa o entendimento do problema por quem recebe o chamado. Atualmente, são feitos, em média 2,5 chamados/hora por analista.

*As regras do domínio:*

- Prioridades por SLA: P1 crítico = 2h, P2 = 1 dia útil, P3 = 3 dias úteis.
- Ticket em status "aguardando cliente" pausa a contagem de SLA.
- Reabertura de um ticket já fechado reabre o ticket original (não cria um novo) — e reincidência gera prioridade maior automaticamente.
- Alçada: só o gestor pode reclassificar a prioridade de um ticket. Nenhum chamado pode ser encerrado, mesmo que tenha sido aberto com informação insuficiente — ele precisa permanecer aberto até ser de fato resolvido.
- **O agente tem acesso à documentação interna e pode ter informação suficiente para identificar a solução de um problema, mas não tem acesso administrador para executar a correção.** Ele nunca executa — apenas sugere, escala ou redireciona.
- A partir da triagem, o agente sempre termina em uma de quatro ações:
  1. **Escalonamento** — abre um chamado interno e informa ao cliente, de forma resumida, que o caso foi escalado.
  2. **Redirecionamento** — quando o assunto é comercial ou fora do escopo da fila de suporte, redireciona o chamado para a fila comercial e informa ao cliente que o assunto foi redirecionado por estar fora do escopo.
  3. **Correção sugerida, sem escalonamento** — quando o agente identifica a correção e não há necessidade de escalar, ele gera uma anotação interna com a correção sugerida, para validação/execução por um analista. Nesse caso não há uma mensagem automática ao cliente final — a resposta ao cliente, se houver, depende do analista após validar/executar a correção.
  4. **Devolução ao cliente** — quando o chamado não tem informação suficiente para ser classificado, o agente devolve o chamado ao cliente, solicitando as informações que faltam. Nenhum chamado interno é aberto até que a informação chegue.

*O que dá errado hoje — os casos difíceis:*

- A entrada é heterogênea: por volume, aproximadamente 50% são dúvidas rotineiras já com resolução documentada na base; 30% são problemas técnicos com correspondência parcial ou incerta na base de conhecimento; 15% estão fora do escopo do suporte (ex.: pedido comercial); 5% chegam sem informação suficiente para classificar.
- **Correspondência incerta na base de conhecimento**: existe um procedimento parecido, mas não uma correspondência exata para o sintoma relatado — decidir se a confiança é alta o suficiente para abrir o chamado automaticamente, ou se precisa de um humano na triagem.
- **Chamado sem informação suficiente** para sequer classificar a categoria — resolvido devolvendo ao cliente e pedindo o que falta, mas o risco fica em não confundir "informação insuficiente" com "correspondência incerta na base" (o primeiro volta para o cliente; o segundo pode seguir para escalonamento).
- **Chamado que parece ser do suporte técnico mas é comercial** — precisa ser reconhecido como fora de escopo e redirecionado, não descartado nem tratado como bug.
- **A correção correta identificada, mas parada por governança**: mesmo quando o agente acerta o diagnóstico e a correção, ele não pode executá-la — o caso difícil aqui não é técnico, é o risco de uma sugestão correta ficar parada até alguém com acesso validar.

*O que a indústria já faz com agentes nesse problema* (detalhado com fontes em `docs/fontes.md`):

1. **CEGID** (caso Google Cloud) — agente conversacional de suporte que resolve o que consegue e, quando não consegue, resume a conversa e sugere abrir um chamado. Reduziu o volume geral de chamados em 17% (40% nas áreas onde foi implantado), com 93% de confiabilidade nas respostas. Padrão provável: roteador (resolve aqui vs. vira chamado) — com a mudança de escopo, este é hoje o caso mais próximo do nosso: a decisão "resolvo/sugiro aqui vs. isso vira chamado" é exatamente a decisão central do nosso agente.

2. **Equinix — Service Desk L1** (citado via Moveworks) — agente de triagem e roteamento de chamados de nível 1, com 96% de acurácia na classificação e redução de cerca de um terço no tempo de resolução. Padrão provável: roteador puro — também diretamente comparável, já que nosso agente também classifica e roteia antes de qualquer ação humana.

3. **Nevada DETR — Appeals AI Assistant** (caso Google Cloud) — assistente que sintetiza dados de um caso, espalhados em várias fontes, para ajudar um analista humano a decidir mais rápido. Padrão provável: orquestrador-trabalhador ou chain de síntese — comparável à etapa do nosso agente que busca na base de conhecimento e redige um parecer para quem vai validar/executar.

### 2.2 Os usuários, e como será a interação

**Quem são, tabela de perfis:**

| Perfil | O que quer | O que sabe | O que pode fazer |
|---|---|---|---|
| Analista de suporte | Menos tempo gasto triando manualmente cada chamado; chamados internos já padronizados quando chegam para validar ou executar | Conhece o processo de triagem e os casos cobertos pela base de conhecimento | Valida e executa a correção sugerida pelo agente quando não há escalonamento; trata os casos que o agente não conseguiu resolver sozinho (baixa confiança, sem informação suficiente). Aprova abertura de chamados internos do agente |
| Time interno (destino do chamado escalado) | Receber o chamado já classificado, resumido e com o parecer da base de conhecimento anexado | Conhece a área técnica ou comercial da sua especialidade | Recebe, executa e resolve o chamado interno escalonado; não decide prioridade sozinho |
| Cliente externo | Ser respondido e direcionado corretamente | Só vê o próprio chamado, sem acesso a nada interno | Abre o chamado inicial (é o input do sistema); recebe as atualizações automáticas de escalonamento ou redirecionamento, quando existirem |

**O usuário principal** é o **time interno** que recebe o chamado escalado — é para ele que a qualidade da classificação, do resumo e do parecer da base de conhecimento precisa ser boa; quando há conflito (ex.: o analista quer despachar rápido e isso significaria enviar informação incompleta ao time de destino), a prioridade do sistema é a qualidade da informação entregue ao time interno, não a velocidade percebida pelo analista.

**A interação, concretamente:** não é um chat. O sistema é disparado pelo evento de abertura do chamado no sistema externo — ninguém inicia uma conversa com o agente.

- **Por onde:** o agente é acionado por evento do sistema de chamados e entrega o resultado como registro nesse mesmo sistema (chamado interno, anotação ou encaminhamento), que o time interno e o analista leem.
- **Quem começa:** o sistema. É um agente proativo, acordado pela criação do chamado externo.
- **Quantas trocas:** nenhuma com o cliente na maioria dos casos (uma execução, de 3 a 5 passos). A única troca é a devolução ao cliente, quando falta informação.
- **O que devolve:** um desfecho gravado: chamado interno com resumo e prioridade, ou anotação com a correção sugerida, ou encaminhamento (fila comercial, fila humana ou devolução ao cliente) com mensagem em texto.
- **Como termina:** quando dá certo, o chamado interno ou a anotação aparece com o procedimento da base anexado. Quando não resolve, vai para a fila humana com o motivo, ou volta ao cliente pedindo o que falta.

Cinco diálogos de exemplo, cobrindo as ações possíveis (baseados no fluxo descrito em `docs/arquitetura-v1.md`):

*Caso 1 — escalonamento:*
```
Cliente (chamado externo): "Não consigo exportar o relatório mensal em PDF, dá erro toda vez que tento."

[agente classifica: categoria = bug_funcional, confiança = 0.86, rota = conhecido]
[agente busca na base de conhecimento: encontra KB-114, confiança do parecer = 0.74]
[confiança acima do limiar -> Solicita abertura chamado interno]

Agente -> Time interno (Engenharia - Relatórios):
  "INC-4471 — Bug exportação PDF (KB-114 aplica). Cliente: Acme Corp.
  Resumo: exportação de relatório mensal falha em PDF, módulo Relatórios.
  Parecer da base de conhecimento anexado."

Agente -> Cliente (atualização automática, resumida):
  "Seu chamado foi registrado e escalado para o time responsável
  (protocolo INC-4471). Em breve você receberá um retorno."
```

*Caso 2 — redirecionamento (fora de escopo):*
```
Cliente (chamado externo): "Quero saber sobre um upgrade do meu plano."

[agente classifica: categoria = fora_de_escopo (comercial)]
[agente redireciona para a fila comercial]

Agente -> Cliente (atualização automática):
  "Identificamos que seu assunto é sobre plano/upgrade, fora do escopo
  desta fila de suporte. Redirecionamos seu chamado para o time comercial."
```

*Caso 3 — correção identificada, sem escalonamento:*
```
Cliente (chamado externo): "Como eu troco minha senha de acesso?"

[agente classifica: categoria = duvida_rotineira, confiança alta]
[agente busca na base: encontra procedimento exato, confiança alta, sem necessidade de escalonar]
[agente gera anotação interna com a correção sugerida, para validação/execução]

Agente -> Analista (anotação interna, sem mensagem automática ao cliente):
  "Procedimento de troca de senha encontrado com alta confiança
  (guia interno correspondente). Sugestão de resposta ao cliente
  anexada para validação e envio."
```

*Caso 4 — devolução ao cliente (informação insuficiente):*
```
Cliente (chamado externo): "Meu servidor não está funcionando direito."

[agente classifica: confiança de categoria abaixo do limiar — não há informação suficiente]
[agente não abre chamado interno nem escala; devolve ao cliente]

Agente -> Cliente (devolução automática, solicitando informação):
  "Para conseguirmos direcionar seu chamado corretamente, precisamos
  de mais detalhes: qual serviço ou servidor é afetado, qual erro
  ou comportamento você está vendo, e desde quando isso acontece."
```

*Caso 5 — divergência entre relato e evidência anexada:*
```
Cliente (chamado externo, com log anexado): "Meu Webmail está fora do ar."

[agente classifica: categoria = indisponibilidade, confiança = 0.80]
[agente lê o log anexado: evidência aponta falha no serviço de DNS, não no Webmail]
[divergência entre relato do cliente e evidência técnica -> confiança do parecer cai abaixo do limiar]
[agente escala para triagem humana, sinalizando a divergência]

Agente -> Analista (fila humana, com divergência sinalizada):
  "Chamado reporta falha no Webmail, mas o log anexado aponta o serviço de DNS.
   Divergência entre relato e evidência — revisão humana necessária antes de
   direcionar ao time responsável."
```

Os diálogos são ilustrativos; os casos executáveis, com dados simulados, estão em `dados/README.md` (o Caso 5 é o `TKT-0002`, e o Caso 2 é parecido com o `TKT-0004`).

**O que o usuário não informa de primeira, que o sistema precisa descobrir:** o cliente não diz se o problema já tem uma solução documentada, qual time interno deve resolver, nem se o assunto é de fato suporte técnico ou comercial — o agente precisa classificar o texto livre do chamado, buscar na base de conhecimento e decidir isso sozinho, sem que ninguém pergunte.

**A complexidade da interação:**

- **Quando o que o cliente diz contradiz o que o sistema encontra:** o agente não age sozinho. Envia à fila humana descrevendo a divergência (Caso 5). Afirmações do cliente sobre frequência ou prioridade ("é a terceira vez", "exijo prioridade máxima") são tratadas como afirmação a verificar contra o histórico do sistema, e a prioridade é calculada por regra em código.
- **Como decide que já sabe o suficiente para agir:** quando a busca na base devolve um procedimento com score de correspondência ≥ 0,5. O portão é calculado em código, não informado pelo modelo. Abaixo disso, o agente não age sozinho.
- **Quando para e chama um humano, e qual:** score baixo, id inexistente ou divergência entre relato e log levam à fila humana, lida pelo **analista de suporte**. A abertura de um chamado interno (ação irreversível) só acontece depois da **confirmação do analista de suporte**.

### 2.3 O Workflow

```
1. ENTRADA     id do chamado externo (evento)                          [CÓDIGO]
2. CONSULTA    consultar_ticket: texto, log anexado, plano, histórico  [MODELO chama; CÓDIGO valida o id e lê o banco]
3. TRIAGEM     técnico | comercial | insuficiente | relato × log divergente  [MODELO]
4. BUSCA       buscar_base_conhecimento(termos) -> top-3 com score     [MODELO escolhe os termos; CÓDIGO calcula o score]
5. PORTÃO      melhor score >= 0.5 ?                                   [CÓDIGO]
6. DESFECHO    5 saídas (tabela abaixo)                                [MODELO escolhe; CÓDIGO recusa o que viola regra]
7. ESCRITA     abrir_chamado_interno    -> IRREVERSÍVEL, confirmação do analista de suporte
               registrar_encaminhamento -> REVERSÍVEL (uma linha em fila/anotação)
8. TÉRMINO     registra POR QUE parou + log da trajetória              [CÓDIGO]
```

| Desfecho | Quando | Reversível? | Quem confirma |
|---|---|---|---|
| `abrir_chamado_interno` | técnico, score ≥ 0.5, procedimento "escalar" | **não** | analista de suporte |
| `anotacao_interna` | técnico, score ≥ 0.5, procedimento "anotar" | sim | — (o analista lê e executa) |
| `fila_humana` | score < 0.5 ou sem artigo; relato que contradiz o log; id inexistente | sim | — |
| `fila_comercial` | assunto comercial | sim | — |
| `devolver_cliente` | informação insuficiente | sim | — |

> OBS: no desenho anterior o passo 5 era "abrir automaticamente ou escalar humano". Foi alterado porque ações irreversíveis precisam de aprovação humana: a abertura do chamado interno só acontece depois da confirmação do analista.

### 2.4 O Sistema

- **O que o sistema faz:** recebe o id de um chamado externo, lê o texto e o log anexado, classifica o assunto, consulta a base de conhecimento e dá **um desfecho**: abrir chamado interno (com confirmação do analista), sugerir correção, redirecionar ao comercial, devolver ao cliente ou pedir olhar humano. Ele não resolve o problema do cliente, não decide prioridade (calculada por regra em código; só o gestor reclassifica) e nunca fecha um chamado.

- **Nível de autonomia pretendido:** **roteador com laço curto de ferramentas** (3 a 5 passos), na fronteira do workflow. O nível abaixo (workflow fixo, com o modelo só classificando) não basta porque duas decisões acontecem em tempo de execução: refazer a busca com outros termos quando o score volta baixo, e corrigir a chamada quando uma ferramenta devolve erro (por exemplo, id inexistente). O nível acima (agente aberto) não se justifica: o caminho é quase sempre consultar, buscar e escrever, e tudo que é regra fica em código. Se o verificador mostrar que nenhum caso depende dessas duas decisões, o desenho correto é um workflow com duas chamadas ao modelo, e diremos isso na Parte 2.

- **Ferramentas:**

  | Ferramenta | O que faz | Leitura ou escrita | Reversível? | Contra o que ela conversa |
  |:---|:---|:---|:---|:---|
  | `consultar_ticket` | lê o texto do cliente, o log anexado, o plano e o histórico de chamados internos do cliente | Leitura | NA | Sistema de chamados externo (mock em SQLite: `tickets_externos`, `clientes`, `chamados_internos`) |
  | `buscar_base_conhecimento` | busca procedimentos por palavras-chave e devolve até 3 artigos com score (vira RAG na Parte 2) | Leitura | NA | Base de conhecimento (mock em SQLite: `kb_artigos`) |
  | `abrir_chamado_interno` | abre o chamado no time responsável; o time e a prioridade são definidos por código, o modelo só redige o resumo | Escrita | **Não** (idempotente por ticket + artigo; exige confirmação do analista) | API do sistema de tickets interno (mock em SQLite: `chamados_internos`) |
  | `registrar_encaminhamento` | registra `fila_comercial`, `devolver_cliente`, `anotacao_interna` ou `fila_humana` | Escrita | Sim | Sistema de chamados (mock em SQLite: `encaminhamentos`) |

  Não existe ferramenta para encerrar chamado, alterar prioridade ou executar correção: a regra de domínio é garantida pela **ausência da ferramenta**.

- **Estado:** o objeto `Estado` guarda passos, tokens, custo, scores da busca, desfecho e o motivo do término. O texto bruto do cliente não é repetido entre passos.
- **Orçamento:** 8 passos, 30 mil tokens, US$ 0,05 e 90 s por chamado. O programa registra qual teto estourou. Término sempre registrado: `respondeu`, `orcamento_esgotado`, `erro_fatal` ou `aguardando_humano`.
- **Salvaguardas em código:** portão de confiança (score ≥ 0,5), confirmação do analista na escrita irreversível, idempotência, prioridade calculada por regra e um lembrete quando o modelo encerra sem registrar desfecho (`docs/arquitetura-v2.md` §6).
- **Detalhes e o que mudou desde a v1:** `docs/arquitetura-v2.md`. A escolha do modelo está em `docs/modelos.md`.

### 2.5 A Justificativa de Negócio - A venda

#### Por que um agente, e não software comum

O texto do chamado é livre, e três decisões dependem de interpretá-lo: se o assunto
é técnico, comercial ou informação insuficiente; quais palavras do relato
representam o sintoma para consultar a base; e se o procedimento encontrado
corresponde de fato ao problema. Um formulário com `if` não resolve porque quem
classifica hoje é o analista lendo texto livre, e o nível abaixo do nosso — um
roteador de uma chamada só — não se recupera quando a busca volta fraca nem quando
uma ferramenta devolve erro. Nosso nível é **roteador com laço curto** (3 a 5
passos): a autonomia está confinada a "escolher o desfecho" e "corrigir a chamada",
e tudo que é regra (prioridade, portão de confiança, idempotência, confirmação)
fica em código (`docs/arquitetura-v2.md`).

#### O ganho esperado, com a conta à vista

**Eixo 1 (principal) — tempo por chamado no ingresso.** Unidade: minutos de analista
por chamado. É o eixo diretamente ligado ao problema declarado (trabalho manual no
ingresso dos chamados) e o único que o sistema controla sozinho.

| | Valor | Conta |
|---|---|---|
| Linha de base | 2,5 chamados/hora por analista = **24 min por chamado** | 60 ÷ 2,5 |
| Alvo | 4 chamados/hora = **15 min por chamado** | 60 ÷ 4 |
| Ganho | **−9 min por chamado (−37,5%)**, equivalente a +60% de chamados por hora | (24 − 15) ÷ 24 |
| Volume | 433 chamados/mês | |
| Total | 9 min × 433 = 3.897 min = **≈ 65 horas de analista por mês** (≈ 0,4 analista em tempo integral, a 160 h/mês) | |

**Eixo 2 (secundário) — SLA estourado nos chamados internos.** Unidade: chamados
internos com SLA estourado por mês, sobre os chamados internos abertos no mês.

| | Valor | Conta |
|---|---|---|
| Linha de base | 25 estourados/mês em 50 chamados internos = **50%** | 25 ÷ 50 |
| Alvo (estimado) | 15 estourados/mês = **30%** | 15 ÷ 50 |
| Ganho | **−10 chamados/mês (−40%)** | (25 − 15) ÷ 25 |

**É uma estimativa.** O alvo de 4 chamados/hora e o de 15 estourados/mês são
hipóteses do grupo, não resultados; a Parte 3 os confere contra o que o sistema
entregar.

#### O ganho para o usuário não é o mesmo do negócio

| | Ganho | Como aparece |
|---|---|---|
| **Negócio** | menos horas de analista gastas em triagem repetitiva; menos chamados atrasando | Eixos 1 e 2 acima |
| **Time interno** (usuário principal) | recebe o chamado já classificado, com resumo e o procedimento da base anexado; menos idas e vindas para entender o problema | qualitativo — **não prometemos número** |
| **Analista de suporte** | deixa de digitar o mesmo registro; passa a confirmar (ou recusar) a abertura | Eixo 1 |
| **Cliente externo** | recebe direcionamento correto sem esperar a fila; ou, quando faltar informação, sabe exatamente o que precisa dizer | qualitativo |

**A tensão que existe e precisa ser dita.** O sistema absorve os chamados
rotineiros (cerca de 50% do volume). O que sobra para o analista é, em média, mais
difícil e mais lento. Por isso **"chamados por hora" pode piorar mesmo com o sistema
funcionando bem**: a média passa a ser calculada sobre um conjunto mais duro. Para
não punir o sistema por isso, o Eixo 1 deve ser medido **sobre a mesma composição de
chamados** (mesmos tipos, mesma proporção) antes e depois, ou comparando o tempo do
ingresso chamado a chamado, e não a vazão total do analista. Do lado do cliente, a
devolução automática ("faltam informações") corta custo e pode piorar a experiência
de quem escreveu pouco por estar com pressa. É o padrão do caso Klarna visto em
aula: a métrica acompanhada melhora enquanto a que importa piora. O que vigia isso
é o limiar de confiança do portão (`LIMIAR_CONFIANCA`, `src/ferramentas.py`) e a
regra de que, na dúvida, o destino é a fila humana e não uma ação automática.

#### O outro lado da conta

- **Quanto custa rodar:** **medido** com `ministral-8b-latest` em 8 chamados simulados: cerca de
  **6.900 tokens e US$ 0,0010 por chamado** (preço de lista, simulado; o gasto real é zero no
  plano gratuito, ver `docs/modelos.md`). A 433 chamados/mês, **≈ US$ 0,43 por mês**. Frente a ~65 h
  de analista, o custo do modelo é irrelevante: o que pesa é o custo do erro.
- **Quanto custa construir:**
  3 Integrantes no grupo. 
- **O que se perde:** (1) **casos já medidos**: no `TKT-0003` (reincidência) o modelo escolhido não
  busca na base e manda à fila humana em vez de abrir o chamado. É erro para o lado seguro, mas é
  carga que volta ao analista; (2) o chamado técnico classificado como comercial e
  redirecionado, cujo cliente espera à toa — quem paga é o cliente; (3) o chamado
  aberto para o time errado com score alto por coincidência de palavras (medido: o `ministral-14b` abriu um chamado P1 indevido no `TKT-0006` na comparação de modelos), que a
  confirmação do analista captura se ele ler o resumo, e que vira retrabalho do
  time interno se ele só clicar em "sim"; (4) os problemas novos, sem artigo na
  base, que **sempre** vão para a fila humana: o sistema não reduz a carga dos
  casos difíceis, só dos repetitivos.

> **Conferência na Parte 3:** o número prometido (24 → 15 minutos por chamado, e
> 25 → 15 estourados por mês) será comparado ao medido, com a diferença explicada.

### 2.6 O Verificador

O verificador é um **conjunto rotulado à mão** (`dados/gabarito.json`): para cada chamado simulado, o desfecho que o analista de suporte daria, derivado dos procedimentos da base de conhecimento (que dizem se o caso é "anotar" ou "escalar", para qual time e com qual prioridade base). Um programa (`src/verificar.py`) compara o gabarito com o que o agente **gravou no banco**, não com o texto que o modelo escreveu, e confere três regras de negócio: (1) nenhum chamado interno para os casos que não devem gerá-lo; (2) no máximo um encaminhamento por chamado; (3) no caso de divergência entre relato e log, a mensagem registrada cita o serviço relatado pelo cliente e a causa que o log mostra; no de reincidência, o resumo registra o que o histórico confirma em vez de repetir a afirmação do cliente. A Parte 1 tem **8 casos**; a Parte 2 amplia para ~40. Limite declarado: a regra (3) é uma checagem por palavras; a qualidade do texto só é julgada de fato por leitura humana do log.

Exemplo (do grupo): se o chamado é sobre uma falha no serviço FTP e a documentação interna diz que o erro cód. 550 deve virar ticket interno com assunto, prazo e responsável específicos, o gabarito registra esse desfecho, e o verificador confere se o agente o gravou.

### 2.7 O Critério de Sucesso

O custo do erro é **assimétrico**: abrir chamado interno indevidamente (o time errado perde tempo, e a ação é irreversível) é pior que mandar um caso à fila humana (o analista faz o que faria hoje). Por isso são duas métricas:

1. **Parte 1:** acerta o desfecho em **≥ 6 de 8** casos rotulados (75%, a mesma proporção dos 30 de 40 do grupo). **Parte 2:** ≥ 30 de 40, incluindo os três tipos do grupo: retorna chamados incompletos ao cliente; redireciona chamado aberto na fila errada; faz a interação interna com proposta de resolução ou abre ticket interno baseado na KB correta.
2. **Em ambas:** **0 chamados internos abertos indevidamente** nos casos em que o gabarito manda não abrir (`TKT-0002`, `TKT-0004`, `TKT-0005`, `TKT-0006`, `TKT-0999`).

**Resultado medido na Parte 1** (rodada 4, `ministral-8b-latest`, `logs/`): **6 de 8** e **0 chamados abertos indevidamente**: os dois critérios foram atingidos. Falharam `TKT-0003` (o modelo vai à fila humana por causa da afirmação "terceira vez") e `TKT-0007` (a busca por palavra não casou "encheu" com "cheio"). Na comparação de modelos, o `ministral-14b-latest` abriu um chamado indevido no `TKT-0006` (com aprovação automática) e não atingiu o critério 2. Detalhes em `docs/modelos.md` §3.3.

### 2.8 Dados

Todos os dados são **simulados** (`dados/seed.sql`, SQLite), sem informação real. A dificuldade se preserva porque os casos foram escritos a partir das exceções do domínio e o gabarito foi escrito **antes** de qualquer prompt. Casos nomeados (detalhe em `dados/README.md`):

- **Divergência:** `TKT-0002` — o cliente relata "Webmail fora do ar", mas o log anexado mostra falha de **DNS**. Existe procedimento de DNS na base com score alto: é a armadilha (agir sobre o log é errar; o certo é sinalizar a divergência à fila humana).
- **Registro inexistente:** `TKT-0999` — id que não existe no sistema de tickets.
- **Não deve disparar a ação principal:** `TKT-0004` — pedido de upgrade de plano; nenhum chamado interno pode ser aberto.
- **Escalonamento com reincidência:** `TKT-0003` — o cliente diz "terceira vez", o histórico mostra 1.
- **Escalonamento simples:** `TKT-0007` — disco cheio sem a afirmação de reincidência; adicionado depois de a comparação de modelos mostrar que os três modelos falhavam no `TKT-0003`, para exercitar a abertura de chamado. Nenhum caso existente foi alterado.
- Extras: `TKT-0001` (simples, anotação de correção), `TKT-0005` (informação insuficiente), `TKT-0006` (correspondência parcial na base).

### 2.9 Dado Sensível

Nenhum dado sensível: todas as informações são sobre serviços e/ou funcionamento de servidores. Os dados do repositório são simulados. Em produção, o texto de um chamado pode conter dados de clientes; esse ponto está tratado em `docs/modelos.md` §3.4 (política de dados do plano gratuito).

### 2.10 Espaço Para o Que Ainda Vem

- [x] **RAG** (Parte 2) — política de SLA e alçada, fichas dos times e guias de procedimento, esboçados em `docs/base-de-conhecimento-v1.md`. Hoje é a tabela `kb_artigos` (6 artigos, busca por palavra-chave); na Parte 2 vira índice vetorial, e o limiar de confiança (0,5, ajustado à mão) passa a ser calibrado com perguntas sem resposta na base. Motivo medido: três das quatro falhas distintas da Parte 1 nasceram da busca por palavra (`docs/modelos.md` §3.3-B).
- [x] **MCP** (Parte 2) — `src/db.py`, a camada que fala com o sistema de tickets (ler ticket e base, gravar chamado e encaminhamento). É a integração natural para virar servidor MCP: o agente deixa de importar o módulo e passa a chamar o serviço.
- [x] **LangChain / LangGraph** (Parte 2) — a orquestração do laço (`rodar` e `_executar` em `src/agente.py`, cerca de 100 linhas). Cada passo do workflow vira um nó do grafo. A comparação pedida (o que o framework dá e o que tira) tem base concreta: as cerca de 100 linhas à mão.
- [ ] **Multiagente** (Parte 3) — **[decisão do grupo]**. Candidata: um agente de triagem e outro de parecer (RAG), se o parecer crescer a ponto de precisar de contexto próprio. Se não crescer, escrever aqui que não se justifica e por quê.

### 2.11 O maior Risco

Base de conhecimento onde o agente realiza as consultas não ser revisada após atualização de algum serviço, desencadeando uma sequência de chamados tratados de maneira incorreta, também é possível que a base fique indisponível por tempo indeterminado.

**Plano B:** se a base estiver indisponível ou o score não passar do limiar, o agente **não responde pelo conhecimento do modelo**: o chamado vai para a fila humana. É o que o prompt (`prompts/agente-v3.md`) e o portão de confiança já fazem quando não há artigo com correspondência. Para o risco de base desatualizada, na Parte 2 cada trecho indexado carrega `data_publicacao` (já previsto em `base-de-conhecimento-v1.md`), com alerta quando um artigo passa de um prazo sem revisão.

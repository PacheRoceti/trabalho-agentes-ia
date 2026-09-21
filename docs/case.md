# Case — Agente de Triagem e Abertura de Chamado Interno

##
> Esta é a v2 do case, atualizada após a mudança de escopo: o projeto deixou de ser um agente gerador de dashboard de consolidação e passou a ser um agente que analisa o chamado do cliente, consulta a base de conhecimento interna e propõe uma solução ou abre um chamado interno. Mais detalhes em `docs/arquitetura-v1.md` e `docs/base-de-conhecimento-v1.md`.

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

  **Quem são, Tabela de perfis:**

  | Perfil | O que quer | O que sabe | O que pode fazer |
  |---|---|---|---|
  | Analista de suporte | Menos tempo gasto triando manualmente cada chamado; chamados internos já padronizados quando chegam para validar ou executar | Conhece o processo de triagem e os casos cobertos pela base de conhecimento | Valida e executa a correção sugerida pelo agente quando não há escalonamento; trata os casos que o agente não conseguiu resolver sozinho (baixa confiança, sem informação suficiente). Aprova abertura de chamados internos do agente |
  | Time interno (destino do chamado escalado) | Receber o chamado já classificado, resumido e com o parecer da base de conhecimento anexado | Conhece a área técnica ou comercial da sua especialidade | Recebe, executa e resolve o chamado interno escalonado; não decide prioridade sozinho |
  | Cliente externo | Ser respondido e direcionado corretamente | Só vê o próprio chamado, sem acesso a nada interno | Abre o chamado inicial (é o input do sistema); recebe as atualizações automáticas de escalonamento ou redirecionamento, quando existirem |

  **O usuário principal** é o **time interno** que recebe o chamado escalado — é para ele que a qualidade da classificação, do resumo e do parecer da base de conhecimento precisa ser boa; quando há conflito (ex.: o analista quer despachar rápido e isso significaria enviar informação incompleta ao time de destino), a prioridade do sistema é a qualidade da informação entregue ao time interno, não a velocidade percebida pelo analista.

  **A interação, concretamente:** não é um chat. O sistema é disparado pelo evento de abertura do chamado no sistema externo — ninguém inicia uma conversa com o agente.

  Cinco diálogos de exemplo, cobrindo as cinco ações possíveis (baseados no fluxo descrito em `docs/arquitetura-v1.md`):

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
  **O que o usuário não informa de primeira, que o sistema precisa descobrir:** o cliente não diz se o problema já tem uma solução documentada, qual time interno deve resolver, nem se o assunto é de fato suporte técnico ou comercial — o agente precisa classificar o texto livre do chamado, buscar na base de conhecimento e decidir isso sozinho, sem que ninguém pergunte.

### 2.3 O Workflow

  ```
  1. ENTRADA      evento: novo chamado no sistema externo             [—]

  2. TRIAGEM      classifica em 4 rotas                          [ROUTER]
                    conhecido    -> segue para 3
                    incerto      -> segue para 3 (mesma rota, com flag)
                    fora escopo  -> encaminha ao time comercial, encerra fluxo
                    sem info     -> fila humana

  3. AGREGAÇÃO    formata o chamado + categoria em resumo   [SEQUENCIAL, 1 chamada]

  4. PARECER RAG  busca na base + redige parecer            [SEQUENCIAL, 1 busca + 1 chamada]

  5. DECISÃO      rascunhar ticket interno ou manter nível do chamado         [ROUTER]

  6. REGISTRO     grava chamado interno ou adicionar anotação com sugestão de correção                  [ESCRITA]

  7. RETORNO      confirma abertura / notifica fila humana                [—]
  ```

  OBS: Anteriormente o passo 5. era "abrir automaticamente ou escalar humano", alterado, pois, ações irreversíveis precisam de aprovação

### 2.4 O Sistema

  - **O que o sistem faz:** "Este sistema recebe um chamado externo, classifica e resume, verifica na base de conhecimento se há resolução conhecida, e abre um chamado interno direcionado ao time responsável. Ele não resolve o problema do cliente, não decide prioridade sozinho em caso de dúvida, e nunca fecha um chamado."

  - **O nível de autonomia pretendido:** WorkFlow, uma vez que as rotas dos chamados são documentados nas documentações internas e o agente precisa decidir, em resumo, entre: Devolver ao cliente, Redirecionar, Sugerir correção e Abrir ticekt Interno

  - **Ferramentas**:
    | Ferramenta | O que Faz | Leitura ou Escrita| Reversível? |Contra o que ele conversa|
    |:---------|:---------|:---------|:---------|:---------|
    |classificar_categoria (regra em código + fallback LLM)|Analisa informações fornecida pelo cliente + Triagem|Leitura|NA|Sistema de chamados Externos|
    |buscar_base_conhecimento (RAG, busca vetorial)|Varre arquivos de consulta e documentação interna buscando por processos|Leitura|NA|Base de Conhecimento|
    |abrir_chamado_interno|reune informações dos anterior e formata o texto de abertura de ticket interno|Escrita|Não|API do sistema de tickets interno|
    |encaminhar_fila_humana|Desiste de solucionar chamado, pede por validação humana|Escrita|NA|Sistema de chamdos Externos|
    
  - **Estado**: sobrevive entre passos apenas o *extraído*, nunca o texto bruto do cliente repetido: `id_ticket_externo`, `categoria`, `resumo_estruturado`, `parecer_rag` (com confiança), `decisão_final`.
  - **Orçamento**: 1 chamada de classificação (sem retry — falha vira fila humana); 1 chamada de agregação; 1 busca vetorial (top-k=5) + 1 chamada de síntese do parecer; 1 chamada de decisão final. Teto de tempo: 30s ponta a ponta (é um processo em background, não uma resposta em tempo real ao cliente).

  - **TRIAGEM — Router**: entrada heterogênea de verdade (4 rotas com proporções distintas), e as rotas não são triviais de separar por regra fixa (texto livre). O padrão anterior na tabela (sequencial) não resolveria porque não há "etapa fixa" — é uma classificação, não uma sequência.
  - **AGREGAÇÃO — Sequencial**: etapa conhecida e fixa (sempre pega classificação + dados → resumo). Nenhuma decisão de fluxo acontece aqui; um Router ou Agente seriam autonomia sem contrapartida.
  - **PARECER RAG — Sequencial (busca + síntese)**: a busca é uma consulta, não uma investigação aberta — não precisamos de um Agente com múltiplos passos porque o item já foi extraído na etapa 3. Se a taxa de "base incompleta" crescer, este é o primeiro candidato a virar Agente com teto de re-busca.
  - **DECISÃO — Router**: decide entre duas rotas conhecidas (abrir automático vs. escalar humano) com base num único número (confiança). Não é um Avaliador porque não há revisão iterativa de texto — é uma classificação binária por threshold.
  - **REGISTRO — Escrita, não é padrão de autonomia**: é código determinístico chamando a API do sistema interno. Marcado como não-reversível (abre um chamado real) e por isso é idempotente por `id_ticket_externo`, para não duplicar em caso de reprocessamento.

  Parando na tabela de decisão da nota 01-6: nenhuma etapa exige Orquestrador, Avaliador ou Agente livre — é um **workflow com dois pontos de roteamento**. Se a etapa 4 (RAG) começar a errar por buscas mal formuladas, é o ponto onde a autonomia cresceria primeiro (Router → Agente com teto de tentativas de busca).

### 2.5 A Justificativa de Negócio - A venda

  **Por que agente, e não software comum:** classificar o texto livre de um chamado em uma de quatro rotas, e julgar se a correspondência encontrada na base de conhecimento é confiável o suficiente para abrir o chamado automaticamente ou exige um humano, depende de interpretar linguagem não estruturada e pesar uma confiança contínua a cada chamado — não é uma consulta fixa nem um conjunto de regras `if` sobre campos estruturados.

  **Eixo(s) de ganho:**

  | Eixo | Linha de base (medida) | Alvo (Estimado) | Ganho | Volume |
  |---|---|---|---|---|
  | Tickets internos com SLA estourado | 25 tickets atrasados/mês | 15 tickets atrasados/mês (-40%) | Tickets internos abertos com mais informação, portanto, tratados mais rápido | 50 tickets em abertos /mês |
  | Volume de chamados tratados por analista | 2,5 chamados/hora, em média | 4 chamados/hora (+60%) | Com o agente fazendo triagem, redirecionamento e formatação, o analista ganha agilidade. Mas, obriga o analista a realizar análises mais complexas com tempo excedente | 433/mês |

  **O ganho para o usuário** (analista: mais chamados tratados por hora, já que o agente assume a triagem, o redirecionamento e a formatação da informação) **não é exatamente o mesmo que o ganho para o negócio** (menos tickets internos com SLA estourado, já que chegam ao time interno com mais informação. E menos tempo de time "caro" gasto com análises de menor relevância). Não identificamos tensão direta entre os dois eixos, até agora — os dois dependem da mesma mudança (triagem e formatação automatizadas). Vale revisitar se, na prática, o aumento de volume tratado por hora vier à custa de tickets menos bem formatados chegando aos times internos — esse é o trade-off que o limiar de confiança da etapa de decisão (`docs/arquitetura-v1.md`) existe justamente para controlar.

  **CALCULO DE CUSTO PENDENTE!!!!!**

### 2.6 O Verificador

  O verificador será a comparação dos output do agente com o diagnóstico das documentações internas mockadas. A maior porte dos casos que o agente terá contato tendem a ser chamados que foram abertos corretamente e com cenários documentados (Devido triagem e redirecionamento dos subagente anteriores), portanto a documentação fornecerá o guideline de qual caso deve ser escalonado e qual não precisa. 

  Ex., o chamado é sobre uma falha no funcionamento do serviço FTP do produto, a documentação interna informa que erro cód. 550 deve ser aberto um ticket interno com assunto, prazo e responsável específico.

### 2.7 O Critério de Sucesso

  Será considerado um sucesso caso o agente siga o fluxo corretamente 30 dos 40 casos, dentre eles:
  1. Retorna chamados incompletos aos clientes;
  2. Redireciona chamado aberto na fila errado para a fila correta
  3. Realiza interação interna com proposta de resolução ou realiza abertura de ticket interno baseada no KB correto


### 2.8 Dados 

  Todos os dados usados no agente são mockados, sob a seguinte disposição: 

  * Casos de divergência: Cliente relata dificuldade para acessar serviço X, mas, anexo log de erro evidênciando serviço Y
  * Caso de registro inexistente: Cliente citar um número de ticket, serviço ou servidor que não está cadastrado no sistema externo.
  * Casos que não devem disparar ação principal:  Cliente relata um problema no acesso à nota fiscal ou numa contratação adicional, redireciona o chamado

### 2.9 Dados Sensível
  Nenhum dado sensível, todas as informações são sobre serviços e/ou funcionamento de servidores 

### 2.10 Espaço Para o Que Ainda Vem

  - [ ] **RAG** (Parte 2) — que conhecimento de domínio os agentes vão consultar, e em que formato ele existe hoje?
    Esboço traçado em `docs/base-de-conhecimento-v1.md`
  - [ ] **MCP** (Parte 2) — qual integração vai virar servidor MCP?
  - [ ] **LangChain** (Parte 2) — que parte da orquestração?
  - [ ] **Multiagente** (Parte 3) — quais seriam os agentes, e por que mais de um?

### 2.11 O maior Risco

  Base de conhecimento onde o agente realiza as consultas não ser revisada após atualização de algum serviço, desencadeando uma sequência de chamados tratados de maneira incorreta, também é possível que a base fique indisponível por tempo indeterminado. Caso ocorra, o agente deixa de buscar por resoluções nos KB's e verifica a inteligência da LLM, mas com grau de confiabilidade reduzido.

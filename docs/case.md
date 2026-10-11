# Case — Agente de Triagem e Abertura de Chamado Interno

> Esta é a v2 do case, atualizada após a mudança de escopo: o projeto deixou de ser um agente gerador de dashboard de consolidação e passou a ser um agente que analisa o chamado do cliente, consulta a base de conhecimento interna e propõe uma solução ou abre um chamado interno. Mais detalhes em `docs/arquitetura-v2.md` (o que foi construído na Parte 1) e `docs/base-de-conhecimento-v2.md`.

## 2 O Tema e o Contexto

### 2.1 O Problema

**Quem sofre:** Analistas de suporte da empresa — operações de Suporte/Customer Success de uma empresa de hospedagem de servidores e serviços (hosting) para clientes externos.

**O problema, em uma frase.**

> Excesso de trabalho manual no processo de ingresso dos chamados e falta de padronização das informações dos chamados internos.

**O contexto.**

*O que acontece hoje, sem o sistema:* cada chamado aberto por um cliente externo passa primeiro pelas mãos de um analista, que precisa ler a descrição livre do problema, decidir se é algo já documentado, se é uma dúvida comercial/financeira fora do escopo do suporte, ou se precisa ser escalado para outro time interno — e então abrir manualmente o chamado interno correspondente. Como cada analista faz essa triagem e esse registro do seu próprio jeito, as informações que chegam ao time de destino não seguem um padrão fixo (categoria, resumo, nível de certeza da causa variam de analista para analista), o que atrasa o entendimento do problema por quem recebe o chamado. Atualmente, são feitos, em média 2,5 chamados/hora por analista.

*As regras do domínio:*

- Prioridades por SLA: P1 crítico = 2h, P2 = 1 dia útil, P3 = 3 dias úteis. O prazo é de **resolução** e conta a partir da abertura do chamado interno, isto é, depois da confirmação do analista. Prioridade e SLA valem para o **chamado interno** que o agente abre. Quando o chamado é redirecionado (fila comercial, fila humana, anotação interna), o agente não define prioridade nem SLA: os prazos são definidos pelo time que recebe.
- Ticket em status "aguardando cliente" pausa a contagem de SLA. Essa pausa é do sistema de chamados, sobre o prazo de atendimento do chamado externo; o agente só registra o status, não calcula o prazo.
- **Reincidência:** quando o mesmo problema volta em **até 30 dias corridos** depois de uma ocorrência anterior, o agente **não reabre** o chamado anterior: abre um chamado interno **novo**, tratado como reincidência. A prioridade do procedimento sobe um nível (se já é P1, não há nível acima e permanece P1), e o resumo cita o chamado anterior que o histórico do sistema confirma. Só conta como reincidência o que o histórico confirma (mesmo cliente, mesma categoria, ocorrência anterior nos últimos 30 dias); a afirmação do cliente ("é a terceira vez") não basta. Hoje o histórico só registra chamados internos, então a regra alcança os procedimentos de escalonamento;
- Alçada: só o gestor pode reclassificar a prioridade de um ticket. Nenhum chamado pode ser encerrado pelo agente, mesmo que tenha sido aberto com informação insuficiente — ele precisa permanecer aberto até ser de fato resolvido.
- **Prazo da confirmação do analista:** toda ação que depende da confirmação do analista de suporte (abrir um chamado interno e enviar o pedido de informação ao cliente) tem **20 minutos** para ser confirmada ou rejeitada, contados do momento em que o agente pede a confirmação. Vencido o prazo, o agente **não executa a ação**: o chamado vai para a **fila humana com as considerações do agente** — a ação que ele propôs, a prioridade que o chamado teria, o procedimento e o score que a sustentam, o resumo ou a mensagem já redigidos e o motivo "confirmação não recebida em 20 minutos". O agente não age sozinho por falta de resposta e não fica esperando sem prazo.
- **Rejeição do analista:** se o analista **rejeita** a ação dentro do prazo, o destino é o mesmo do prazo vencido: a ação não é executada e o chamado vai para a **fila humana com as considerações do agente**, com o motivo "ação rejeitada pelo analista de suporte". Uma rejeição não deixa o chamado sem desfecho (decisão de 10/10/2026).
- **Aprovação com correção do resumo:** ao confirmar a abertura de um chamado interno, o analista pode **corrigir o resumo** que o agente redigiu, e o chamado é aberto com o texto dele. É a única coisa que ele altera: **categoria, time e prioridade continuam vindo do procedimento** (o analista não reclassifica; só o gestor), e trocar o procedimento não é correção, é rejeição. O resumo corrigido segue a mesma regra do resumo do agente, e o prazo de 20 minutos não se estende por causa da edição. O registro guarda os dois textos, o do agente e o aprovado (decisão de 11/10/2026).
- **Prazo vencido em chamado P1 avisa o gestor:** quando o prazo de 20 minutos vence e a ação proposta abriria um chamado interno **P1**, o sistema, além de encaminhar o chamado à fila humana, **avisa o gestor de suporte**. A fila humana é lida pelo mesmo analista que não respondeu, e um P1 tem 2 horas de SLA. O aviso vale só para o prazo vencido: na rejeição o analista já viu o chamado (decisão de 10/10/2026).
- **O agente interage diretamente com o cliente apenas para solicitar mais informações.** É a única mensagem que ele envia ao cliente; todo o resto que ele produz é registro interno (chamado interno, anotação ou encaminhamento), e qualquer outra comunicação com o cliente é feita pelo analista de suporte. O pedido de informação segue cinco regras:
  - **o que pode conter:** só a lista do que falta para classificar o chamado (serviço ou servidor afetado, erro ou comportamento observado, desde quando). É proibido prometer correção, prazo ou prioridade, e citar qualquer informação interna (procedimentos, times, scores);
  - **quem confirma:** a mensagem chega ao cliente e não tem volta, então o envio só acontece depois da **confirmação do analista de suporte**, como toda ação irreversível, e no mesmo prazo de 20 minutos;
  - **quantas vezes:** no máximo **um** pedido por chamado. Se a resposta do cliente ainda não bastar, o chamado vai para a fila humana — o agente não insiste;
  - **enquanto espera:** o chamado fica em "aguardando cliente", o que pausa o SLA;
  - **quando o cliente responde:** a resposta retoma a **mesma conversa** (identificada pelo id do chamado externo), e o agente refaz a triagem com o texto original mais a resposta. Sem resposta em 3 dias úteis, o chamado vai para a fila humana — o agente nunca encerra o chamado.
- **O agente tem acesso à documentação interna e pode ter informação suficiente para identificar a solução de um problema, mas não tem acesso administrador para executar a correção.** Ele nunca executa — apenas sugere, escala ou redireciona.
- A partir da triagem, cada volta da triagem termina em uma de cinco ações:
  1. **Escalonamento** — abre um chamado interno para o time responsável, com o time e a prioridade definidos pelo procedimento da base de conhecimento.
  2. **Redirecionamento** — quando o assunto é comercial (planos, preços, upgrade, contratação, cobrança) e, portanto, fora do escopo da fila de suporte, redireciona o chamado para a fila comercial. Um pedido técnico que o suporte não cobre e que não é comercial (por exemplo, instalar um aplicativo para o cliente) não tem procedimento na base e vai para a fila humana (ação 5).
  3. **Correção sugerida, sem escalonamento** — quando o agente identifica a correção e não há necessidade de escalar, ele gera uma anotação interna com a correção sugerida, para validação/execução por um analista. A resposta ao cliente, se houver, depende do analista após validar/executar a correção.
  4. **Devolução ao cliente** — quando o chamado não tem informação suficiente para ser classificado, o agente envia ao cliente, depois da confirmação do analista, o pedido das informações que faltam e aguarda a resposta. Nenhum chamado interno é aberto até que a informação chegue; quando ela chega, a triagem recomeça na mesma conversa e termina em uma das outras quatro ações. A devolução é, portanto, o desfecho da primeira volta e uma pausa do chamado, não o seu fim.
  5. **Fila humana** — quando o agente não tem confiança para agir sozinho (score abaixo do limiar ou sem procedimento, divergência entre relato e log, id inexistente, pedido fora da alçada, resposta do cliente ainda insuficiente, prazo de resposta do cliente vencido, ação rejeitada pelo analista ou confirmação do analista não recebida em 20 minutos), encaminha o chamado ao analista de suporte com o motivo.

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
| Analista de suporte | Menos tempo gasto triando manualmente cada chamado; chamados internos já padronizados quando chegam para validar ou executar | Conhece o processo de triagem e os casos cobertos pela base de conhecimento | Valida e executa a correção sugerida pelo agente quando não há escalonamento; trata os casos que o agente não conseguiu resolver sozinho (baixa confiança, sem informação suficiente). Aprova a abertura de chamados internos e o envio do pedido de informação ao cliente |
| Time interno (destino do chamado escalado) | Receber o chamado já classificado, resumido e com o parecer da base de conhecimento anexado | Conhece a área técnica ou comercial da sua especialidade | Recebe, executa e resolve o chamado interno escalonado; não decide prioridade sozinho |
| Cliente externo | Ser respondido e direcionado corretamente | Só vê o próprio chamado, sem acesso a nada interno | Abre o chamado inicial (é o input do sistema); recebe do agente apenas o pedido de informação, quando falta algo para classificar o chamado (no máximo um por chamado); todos os outros retornos vêm do analista de suporte |

**O usuário principal** é o **time interno** que recebe o chamado escalado — é para ele que a qualidade da classificação, do resumo e do parecer da base de conhecimento precisa ser boa; quando há conflito (ex.: o analista quer despachar rápido e isso significaria enviar informação incompleta ao time de destino), a prioridade do sistema é a qualidade da informação entregue ao time interno, não a velocidade percebida pelo analista.

**A interação, concretamente:** não é um chat. O sistema é disparado pelo evento de abertura do chamado no sistema externo — ninguém inicia uma conversa com o agente.

**A entrada é o texto do chamado.** O evento de abertura é o gatilho que antecede o sistema; o que ele entrega ao agente é o **texto livre que o cliente escreveu**, exatamente como foi digitado. Junto do texto, sem que ninguém o digite, vêm o **id do chamado** (que vira o `thread_id` da conversa) e o **id do cliente**. O agente começa lendo o texto; `consultar_ticket` continua existindo, mas para o que é registro: o histórico do cliente, o plano e o log anexado. A resposta do cliente a um pedido de informação também chega como texto livre, na mesma conversa. A única conversa possível é curta e iniciada pelo próprio agente: um pedido de informação ao cliente e a resposta dele.

- **Por onde:** o agente é acionado por evento do sistema de chamados e entrega o resultado como registro nesse mesmo sistema (chamado interno, anotação ou encaminhamento), que o time interno e o analista leem.
- **Quem começa:** o sistema. É um agente proativo, acordado pela criação do chamado externo.
- **Quantas trocas:** na maioria dos chamados, nenhuma com o cliente (uma execução, de 3 a 5 passos). Quando falta informação, **no máximo uma**: o analista confirma o pedido, o agente o envia, a execução pausa, e a resposta do cliente a retoma.
- **O que devolve:** um desfecho gravado: chamado interno com resumo e prioridade, ou anotação com a correção sugerida, ou encaminhamento (fila comercial, fila humana ou devolução ao cliente) com mensagem em texto.
- **Como termina:** quando dá certo, o chamado interno ou a anotação aparece com o procedimento da base anexado. Quando não resolve, vai para a fila humana com o motivo. Quando falta informação, a execução pausa em "aguardando cliente" até a resposta (ou até o prazo de 3 dias úteis, quando vai para a fila humana).

Cinco diálogos de exemplo, cobrindo as ações possíveis. As categorias são as dos procedimentos da base (`ssl_certificado`, `permissao_arquivos`, `acesso_ssh`, `site_fora_do_ar`, `dns_dominio`, `backup`); o score de correspondência é calculado pelo código, e a categoria, o time e a prioridade vêm do procedimento recuperado. Só o Caso 4 tem mensagem do agente ao cliente, porque pedir informação é a única interação direta permitida.

*Caso 1 — escalonamento:*
```
Cliente (chamado externo): "Meu site parou de salvar arquivos: todo upload falha com a mensagem de
permissão negada. Preciso de ajuda para voltar a publicar."

[agente consulta o chamado e o histórico do cliente: nenhuma ocorrência anterior de permissão de arquivos]
[agente classifica: assunto = técnico]
[agente busca na base: KB-102 "Permissão negada ao gravar arquivos", score acima do limiar (0,5), ação padrão = escalar]
[procedimento define: time = Infraestrutura, prioridade = P2]
[escrita irreversível -> pede confirmação ao analista de suporte -> confirmado]

Agente -> Time interno (Infraestrutura), chamado interno:
  "Permissão negada ao gravar arquivos (KB-102). Categoria: permissao_arquivos. Prioridade: P2.
   Resumo: o cliente relata que o site parou de salvar arquivos e que todo upload falha com
   permissão negada. Sem ocorrência anterior no histórico. Procedimento: identificar os arquivos
   e pastas com dono ou permissões incorretos e corrigi-los (exige acesso de administrador)."
```

*Caso 2 — redirecionamento (fora de escopo):*
```
Cliente (chamado externo): "Olá, quero fazer upgrade do meu plano para um servidor dedicado.
Podem me passar valores e prazo de migração?"

[agente classifica: assunto = comercial (upgrade de plano)]
[agente não busca na base de procedimentos e não abre chamado interno]

Agente -> Fila comercial (encaminhamento):
  "Pedido de upgrade de Hospedagem Start para servidor dedicado, com valores e prazo de
   migração. Assunto comercial, fora do escopo do suporte técnico."
```

*Caso 3 — correção identificada, sem escalonamento:*
```
Cliente (chamado externo): "Como eu troco minha senha de acesso?"

[agente classifica: assunto = técnico]
[agente busca na base: procedimento com score acima do limiar (0,5), ação padrão = anotar]
[agente gera anotação interna com a correção sugerida, para validação/execução]

Agente -> Analista (anotação interna, sem mensagem automática ao cliente):
  "Procedimento de troca de senha encontrado com score acima do limiar
  (guia interno correspondente). Sugestão de resposta ao cliente
  anexada para validação e envio."
```

*Caso 4 — informação insuficiente (a única interação com o cliente):*
```
Cliente (chamado externo): "Meu servidor não está funcionando direito."

[agente classifica: assunto = insuficiente — não dá para saber o serviço afetado nem o sintoma]
[agente não busca na base e não abre chamado interno]
[mensagem ao cliente é irreversível -> pede confirmação ao analista de suporte -> confirmado]

Agente -> Cliente (pedido de informação, único permitido neste chamado):
  "Para direcionarmos seu chamado, precisamos de mais detalhes: qual serviço ou
   servidor é afetado, qual erro ou comportamento você está vendo e desde quando
   isso acontece."

[chamado passa a "aguardando cliente" (SLA pausado); a execução pausa nesta conversa]

Cliente (resposta, mesma conversa): "É o site da loja. Desde o deploy de hoje de manhã
todas as páginas dão erro 502."

[agente retoma a mesma conversa e refaz a triagem com o texto original + a resposta]
[agente classifica: assunto = técnico]
[agente busca na base: KB-104 "Site fora do ar com erro 5xx após deploy", score acima do limiar,
 ação padrão = escalar; procedimento define: time = Infraestrutura, prioridade = P1]
[escrita irreversível -> pede confirmação ao analista de suporte -> confirmado]

Agente -> Time interno (Infraestrutura), chamado interno:
  "Site fora do ar com erro 502 em todas as páginas desde o deploy desta manhã (KB-104).
   Categoria: site_fora_do_ar. Prioridade: P1. Informação obtida após pedido ao cliente."
```

Se a resposta do cliente ainda não permitisse classificar, o agente **não** enviaria um segundo pedido: o chamado iria para a fila humana com as duas mensagens do cliente.

*Caso 5 — divergência entre relato e evidência anexada:*
```
Cliente (chamado externo, com log anexado): "Meu Webmail está fora do ar desde cedo,
ninguém da empresa consegue ler e-mail."

[agente classifica: assunto = técnico]
[agente lê o log anexado: falha de resolução DNS (SERVFAIL, nameserver não responde);
 o webmail abre normalmente quando acessado direto pelo IP do servidor]
[a base tem KB-106 "Falha de resolução DNS" com score alto — é a armadilha:
 agir sobre o log abriria um chamado P1 com base em algo que o cliente não relatou]
[divergência entre relato e evidência -> não age sozinho]

Agente -> Analista (fila humana, com divergência sinalizada):
  "O cliente relata falha no Webmail, mas o log anexado aponta falha de DNS no nameserver
   do domínio, e o serviço de webmail responde. Revisão humana necessária antes de
   direcionar ao time responsável."
```

Os casos 1, 2, 4 (primeira mensagem) e 5 são os chamados simulados `TKT-0007`, `TKT-0004`, `TKT-0005` e `TKT-0002` (`dados/README.md`); o Caso 3 é ilustrativo e ainda não tem procedimento na base.

**O que o usuário não informa de primeira, que o sistema precisa descobrir:** o cliente não diz se o problema já tem uma solução documentada, qual time interno deve resolver, nem se o assunto é de fato suporte técnico ou comercial — o agente precisa classificar o texto livre do chamado, buscar na base de conhecimento e decidir isso sozinho, sem que ninguém pergunte.

**A complexidade da interação:**

- **Quando o que o cliente diz contradiz o que o sistema encontra:** o agente não age sozinho. Envia à fila humana descrevendo a divergência (Caso 5). Afirmações do cliente sobre frequência ou prioridade ("é a terceira vez", "exijo prioridade máxima") são tratadas como afirmação a verificar contra o histórico do sistema; a prioridade vem do procedimento da base, e só a reincidência confirmada pelo histórico a ajusta.
- **Como decide que já sabe o suficiente para agir:** quando a busca na base devolve um procedimento com score de correspondência ≥ 0,5. O portão é calculado em código, não informado pelo modelo. Abaixo disso, o agente não age sozinho.
- **Quando para e chama um humano, e qual:** score baixo, id inexistente, divergência entre relato e log, pedido fora da alçada do agente (fechar um chamado, mudar prioridade), resposta do cliente que continua insuficiente, 3 dias úteis sem resposta ao pedido de informação ou 20 minutos sem a confirmação do analista levam à fila humana, lida pelo **analista de suporte**. As duas ações irreversíveis — abrir um chamado interno e enviar o pedido de informação ao cliente — só acontecem depois da **confirmação do analista de suporte**, que tem 20 minutos para confirmar ou rejeitar; rejeitada a ação, ou sem resposta nesse prazo, ela não é executada e o chamado vai para a fila humana com as considerações do agente. No prazo vencido de um chamado que seria P1, o **gestor de suporte** também é avisado.

### 2.3 O Workflow

```
1. ENTRADA     texto livre do chamado, entregue pelo evento de abertura;
               acompanham: id do chamado (thread_id) e id do cliente     [CÓDIGO]
               (Parte 2; na Parte 1 o programa recebe o id e simula o evento)
2. CONSULTA    consultar_ticket(id): log anexado, plano, histórico     [MODELO chama; CÓDIGO valida o id e lê o banco]
3. TRIAGEM     técnico | comercial | insuficiente | relato × log divergente  [MODELO]
4. BUSCA       buscar_base_conhecimento(termos) -> top-3 com score     [MODELO escolhe os termos; CÓDIGO calcula o score]
5. PORTÃO      melhor score >= 0.5 ?                                   [CÓDIGO]
6. DESFECHO    5 saídas (tabela abaixo)                                [MODELO escolhe; CÓDIGO recusa o que viola regra]
7. ESCRITA     abrir_chamado_interno    -> IRREVERSÍVEL, confirmação do analista de suporte
               registrar_encaminhamento -> REVERSÍVEL (uma linha em fila/anotação)
               devolver_cliente         -> IRREVERSÍVEL, confirmação do analista de suporte: envia o pedido
                                           de informação ao cliente (um por chamado)
                                           e PAUSA até a resposta, que retoma a mesma conversa
                                           (Parte 2; na Parte 1 só grava o pedido e termina)
8. TÉRMINO     registra POR QUE parou + log da trajetória              [CÓDIGO]
```

| Desfecho | Quando | Reversível? | Quem confirma |
|---|---|---|---|
| `abrir_chamado_interno` | técnico, score ≥ 0.5, procedimento "escalar" | **não** | analista de suporte |
| `anotacao_interna` | técnico, score ≥ 0.5, procedimento "anotar" | sim | — (o analista lê e executa) |
| `fila_humana` | score < 0.5 ou sem artigo; relato que contradiz o log; id inexistente; pedido fora da alçada (fechar chamado, mudar prioridade); resposta do cliente ainda insuficiente; 3 dias úteis sem resposta ao pedido de informação; ação irreversível rejeitada pelo analista, ou 20 minutos sem a confirmação dele (nos dois casos o encaminhamento leva as considerações do agente; no prazo vencido de um chamado que seria P1, o gestor também é avisado) | sim | — |
| `fila_comercial` | assunto comercial | sim | — |
| `devolver_cliente` | informação insuficiente (no máximo uma vez por chamado) | **não** — a mensagem chega ao cliente (Parte 2; na Parte 1 só grava o pedido) | analista de suporte (a partir da Parte 2, quando a mensagem passa a ser enviada) |

> OBS: no desenho anterior o passo 5 era "abrir automaticamente ou escalar humano". Foi alterado porque ações irreversíveis precisam de aprovação humana: a abertura do chamado interno e o envio do pedido de informação ao cliente só acontecem depois da confirmação do analista.

### 2.4 O Sistema

- **O que o sistema faz:** recebe o texto de um chamado externo (com o id do chamado e do cliente), consulta o log anexado e o histórico, classifica o assunto, consulta a base de conhecimento e dá **um desfecho por volta da triagem**: abrir chamado interno (com confirmação do analista), sugerir correção, redirecionar ao comercial, pedir ao cliente a informação que falta (sua única interação direta com o cliente, também com confirmação do analista) ou pedir olhar humano. O pedido ao cliente é o desfecho da primeira volta: a resposta abre a segunda, que termina em um dos outros quatro. Ele não resolve o problema do cliente, não decide prioridade (vem do procedimento da base; só o gestor reclassifica) e nunca fecha um chamado.

- **Nível de autonomia pretendido:** **roteador com laço curto de ferramentas** (3 a 5 passos), na fronteira do workflow. O nível abaixo (workflow fixo, com o modelo só classificando) não basta porque duas decisões acontecem em tempo de execução: refazer a busca com outros termos quando o score volta baixo, e corrigir a chamada quando uma ferramenta devolve erro (por exemplo, id inexistente). O nível acima (agente aberto) não se justifica: o caminho é quase sempre consultar, buscar e escrever, e tudo que é regra fica em código. Se o verificador mostrar que nenhum caso depende dessas duas decisões, o desenho correto é um workflow com duas chamadas ao modelo, e diremos isso na Parte 2.

- **Ferramentas:**

  | Ferramenta | O que faz | Leitura ou escrita | Reversível? | Contra o que ela conversa |
  |:---|:---|:---|:---|:---|
  | `consultar_ticket` | lê, pelo id que acompanha o texto, o log anexado, o plano e o histórico de chamados internos do cliente (o texto já chega como entrada) | Leitura | NA | Sistema de chamados externo (mock em SQLite: `tickets_externos`, `clientes`, `chamados_internos`) |
  | `buscar_base_conhecimento` | busca procedimentos por palavras-chave e devolve até 3 artigos com score (vira RAG na Parte 2) | Leitura | NA | Base de conhecimento (mock em SQLite: `kb_artigos`) |
  | `abrir_chamado_interno` | abre o chamado no time responsável; a categoria, o time e a prioridade vêm do procedimento recuperado e são copiados pelo código; o modelo só indica o procedimento (`kb_id`) e redige o resumo | Escrita | **Não** (idempotente por ticket + artigo; exige confirmação do analista) | API do sistema de tickets interno (mock em SQLite: `chamados_internos`) |
  | `registrar_encaminhamento` | registra `fila_comercial`, `devolver_cliente`, `anotacao_interna` ou `fila_humana`; no destino `devolver_cliente`, a mensagem é o pedido de informação enviado ao cliente | Escrita | Sim, exceto `devolver_cliente` (a mensagem chega ao cliente: exige confirmação do analista e é limitada a uma por chamado em código) | Sistema de chamados (mock em SQLite: `encaminhamentos`) |

  Não existe ferramenta para encerrar chamado, alterar prioridade ou executar correção: a regra de domínio é garantida pela **ausência da ferramenta**.

  **Parte 1 × Parte 2.** Na Parte 1, `devolver_cliente` só grava o pedido na tabela `encaminhamentos` e a execução termina. A confirmação do analista, o envio ao cliente, a pausa em `aguardando_cliente` e a retomada da mesma conversa com a resposta entram na Parte 2, com o checkpointer e o `interrupt` do grafo — o mesmo mecanismo da confirmação da abertura de chamado.

- **Estado:** o objeto `Estado` guarda passos, tokens, custo, scores da busca, desfecho e o motivo do término. O texto bruto do cliente não é repetido entre passos.
- **Orçamento:** 8 passos, 30 mil tokens, US$ 0,05 e 90 s por chamado. O programa registra qual teto estourou. Término sempre registrado: `respondeu`, `orcamento_esgotado`, `erro_fatal`, `aguardando_humano` ou, a partir da Parte 2, `aguardando_cliente` (pausa até a resposta ao pedido de informação; passos, tokens e custo continuam contando na retomada, e o teto de 90 s conta só o tempo de execução, não a espera pelo cliente).
- **Salvaguardas em código:** portão de confiança (score ≥ 0,5), confirmação do analista na escrita irreversível, idempotência, time e prioridade copiados do procedimento (ajuste por reincidência em código) e um lembrete quando o modelo encerra sem registrar desfecho (`docs/arquitetura-v2.md` §6).
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
time e prioridade vêm da documentação interna, e tudo que é regra (portão de confiança,
idempotência, confirmação, ajuste por reincidência) fica em código (`docs/arquitetura-v2.md`).

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

**É uma estimativa, e é um teto.** A conta aplica os 9 minutos aos 433 chamados, mas os que vão
à fila humana continuam custando ao analista o tempo de hoje, e anotações e aberturas ainda passam
por ele para validar ou confirmar. Os 24 minutos da linha de base vêm da vazão total do analista
(2,5 chamados/hora), que inclui ler, classificar, registrar e responder; a conta supõe que os 9
minutos saem das etapas de leitura, classificação e registro, que são as que o agente assume. O alvo de 4 chamados/hora e o de 15 estourados/mês são
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
devolução ("faltam informações") corta custo e pode piorar a experiência
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

O verificador é um **conjunto rotulado à mão** (`dados/gabarito.json`): para cada chamado simulado, o desfecho que o analista de suporte daria, derivado dos procedimentos da base de conhecimento (que dizem se o caso é "anotar" ou "escalar", para qual time e com qual prioridade base). Um programa (`src/verificar.py`) compara o gabarito com o que o agente **gravou no banco**, não com o texto que o modelo escreveu, e confere três regras de negócio: (1) nenhum chamado interno para os casos que não devem gerá-lo; (2) no máximo um pedido de informação ao cliente (`devolver_cliente`) por chamado — o chamado que passa pela conversa tem dois registros legítimos, o pedido e o desfecho final; (3) no caso de divergência entre relato e log, a mensagem registrada cita o serviço relatado pelo cliente e a causa que o log mostra; no de reincidência, o resumo registra o que o histórico confirma em vez de repetir a afirmação do cliente. A Parte 1 tem **8 casos**; a Parte 2 amplia para ~40. Limite declarado: a regra (3) é uma checagem por palavras; a qualidade do texto só é julgada de fato por leitura humana do log.

Exemplo (do grupo): se o chamado é sobre uma falha no serviço FTP e a documentação interna diz que o erro cód. 550 deve virar ticket interno com assunto, prazo e responsável específicos, o gabarito registra esse desfecho, e o verificador confere se o agente o gravou.

### 2.7 O Critério de Sucesso

O custo do erro é **assimétrico**: abrir chamado interno indevidamente (o time errado perde tempo, e a ação é irreversível) é pior que mandar um caso à fila humana (o analista faz o que faria hoje). Por isso são duas métricas:

1. **Parte 1:** acerta o desfecho em **≥ 6 de 8** casos rotulados (75%, a mesma proporção dos 30 de 40 do grupo). **Parte 2:** ≥ 30 de 40, incluindo os três tipos do grupo: retorna chamados incompletos ao cliente; redireciona chamado aberto na fila errada; faz a interação interna com proposta de resolução ou abre ticket interno baseado na KB correta.
2. **Em ambas:** **0 chamados internos abertos indevidamente** nos casos em que o gabarito manda não abrir (`TKT-0001`, `TKT-0002`, `TKT-0004`, `TKT-0005`, `TKT-0006`, `TKT-0999`). No `TKT-0005`, isso vale para a primeira volta: nenhum chamado é aberto antes da resposta do cliente ao pedido de informação.

**Resultado medido na Parte 1** (rodada 4, `ministral-8b-latest`, `logs/`): **6 de 8** e **0 chamados abertos indevidamente**: os dois critérios foram atingidos. Falharam `TKT-0003` (o modelo vai à fila humana por causa da afirmação "terceira vez") e `TKT-0007` (a busca por palavra não casou "encheu" com "cheio"). Na comparação de modelos, o `ministral-14b-latest` abriu um chamado indevido no `TKT-0006` (com aprovação automática) e não atingiu o critério 2. Detalhes em `docs/modelos.md` §3.3. Limite do critério: os dois casos que falharam são os únicos de escalonamento, então os critérios foram atingidos sem nenhuma abertura correta de chamado interno; o resultado mostra que o agente não age quando não deve, mas ainda não que escala quando deve.

### 2.8 Dados

Todos os dados são **simulados** (`dados/seed.sql`, SQLite), sem informação real. A dificuldade se preserva porque os casos foram escritos a partir das exceções do domínio e o gabarito dos 7 casos originais foi escrito **antes** de qualquer prompt (o `TKT-0007` e a regra de texto do `TKT-0002` vieram depois, como registrado em `docs/modelos.md` §3.3). Casos nomeados (detalhe em `dados/README.md`):

- **Divergência:** `TKT-0002` — o cliente relata "Webmail fora do ar", mas o log anexado mostra falha de **DNS**. Existe procedimento de DNS na base com score alto: é a armadilha (agir sobre o log é errar; o certo é sinalizar a divergência à fila humana).
- **Registro inexistente:** `TKT-0999` — id que não existe no sistema de tickets.
- **Não deve disparar a ação principal:** `TKT-0004` — pedido de upgrade de plano; nenhum chamado interno pode ser aberto.
- **Escalonamento com reincidência:** `TKT-0003` — o cliente diz "terceira vez", o histórico mostra 1.
- **Escalonamento simples:** `TKT-0007` — permissão negada ao gravar arquivos, sem a afirmação de reincidência; adicionado depois de a comparação de modelos mostrar que os três modelos falhavam no `TKT-0003`, para exercitar a abertura de chamado. Nenhum caso existente foi alterado.
- Extras: `TKT-0001` (simples, anotação de correção), `TKT-0005` (informação insuficiente), `TKT-0006` (correspondência parcial na base).

### 2.9 Dado Sensível

Nenhum dado sensível: todas as informações são sobre serviços e/ou funcionamento de servidores. Os dados do repositório são simulados. Em produção, o texto de um chamado pode conter dados de clientes; esse ponto está tratado em `docs/modelos.md` §3.4 (política de dados do plano gratuito).

### 2.10 Espaço Para o Que Ainda Vem

- [x] **RAG** (Parte 2) — o índice contém os procedimentos técnicos (com time e prioridade de cada caso) e o catálogo de planos, conforme `docs/base-de-conhecimento-v2.md`. A política de SLA e alçada e as fichas dos times ficam **fora** do índice: a política é aplicada em código, e as fichas servem só de lista de referência para validar o time de cada procedimento. Hoje a base é a tabela `kb_artigos` (6 artigos, busca por palavra-chave); na Parte 2 vira índice vetorial, e o limiar de confiança (0,5, ajustado à mão) passa a ser calibrado com perguntas sem resposta na base. Motivo medido: três das quatro falhas distintas da Parte 1 nasceram da busca por palavra (`docs/modelos.md` §3.3-B).
- [x] **MCP** (Parte 2) — `src/db.py`, a camada que fala com o sistema de tickets (ler ticket e base, gravar chamado e encaminhamento). É a integração natural para virar servidor MCP: o agente deixa de importar o módulo e passa a chamar o serviço.
- [x] **LangChain / LangGraph** (Parte 2) — a orquestração do laço (`rodar` e `_executar` em `src/agente.py`, cerca de 100 linhas). Cada passo do workflow vira um nó do grafo. A comparação pedida (o que o framework dá e o que tira) tem base concreta: as cerca de 100 linhas à mão.
- [ ] **Multiagente** (Parte 3) — **[decisão do grupo]**. Candidata: um agente de triagem e outro de parecer (RAG), se o parecer crescer a ponto de precisar de contexto próprio. Se não crescer, escrever aqui que não se justifica e por quê.

### 2.11 O maior Risco

Base de conhecimento onde o agente realiza as consultas não ser revisada após atualização de algum serviço, desencadeando uma sequência de chamados tratados de maneira incorreta, também é possível que a base fique indisponível por tempo indeterminado.

**Plano B:** se a base estiver indisponível ou o score não passar do limiar, o agente **não responde pelo conhecimento do modelo**: o chamado vai para a fila humana. É o que o prompt (`src/prompts/agente-v5.md`) e o portão de confiança já fazem quando não há artigo com correspondência. Para o risco de base desatualizada, na Parte 2 cada trecho indexado carrega `data_publicacao` (já previsto em `base-de-conhecimento-v2.md`), com alerta quando um artigo passa de um prazo sem revisão.

### 2.12 Complemento do case: o que o domínio ensinou (Parte 2, item 0)

Esta seção registra o que o grupo aprendeu sobre suporte de hospedagem e que alguém de fora precisa saber para entender as decisões do sistema: o vocabulário, as regras que a área conhece e não estavam escritas, a exceção que decide a arquitetura e o passo que parecia um e são vários.

#### Vocabulário do atendimento

| Termo | O que é | Onde aparece no sistema |
|---|---|---|
| **Chamado externo** (ticket, `TKT-0000`) | O pedido que o cliente abre, em texto livre | É a entrada do agente; o id vira o `thread_id` da conversa |
| **Chamado interno** (`INC-0000`) | O pedido que o Suporte abre para um time interno resolver | É a escrita irreversível do agente (`abrir_chamado_interno`) |
| **Triagem** (ou ingresso) | Ler o chamado externo, classificar o assunto e decidir o destino | É o trabalho que o agente assume |
| **Escalonamento** | Passar o caso a um time com mais acesso ou especialidade, abrindo um chamado interno | Ação padrão `escalar` dos procedimentos |
| **Anotação interna** | Registro, visível só ao Suporte, com a correção sugerida para o analista validar e executar | Ação padrão `anotar` dos procedimentos |
| **Fila** | Lista de chamados à espera de um grupo de pessoas | `fila_comercial` (time Comercial) e `fila_humana` (analista de suporte) |
| **N1 e N2** | Níveis de suporte. N1 é o primeiro atendimento; N2 são os especialistas | N1 é o analista de suporte; N2 são os times internos (Infraestrutura, Segurança) |
| **Alçada** | O limite do que cada papel pode decidir | O agente não fecha chamado nem muda prioridade; só o gestor reclassifica |
| **SLA** (*Service Level Agreement*, acordo de nível de serviço) | O prazo combinado para resolver um chamado | Prazo de resolução do chamado interno, definido pela prioridade |
| **P1, P2, P3** | Níveis de prioridade: P1 é crítico (serviço parado), P3 é o menos urgente | P1 = 2h, P2 = 1 dia útil, P3 = 3 dias úteis |
| **Reincidência** | O mesmo problema voltar para o mesmo cliente em até 30 dias | Sobe a prioridade em um nível, por regra de código |
| **Aguardando cliente** | Status do chamado que depende de uma resposta do cliente; o prazo não corre | Estado da pausa depois do pedido de informação |
| **KB** (*Knowledge Base*, base de conhecimento; `KB-000`) | A coleção de procedimentos internos, um por sintoma | É o que o agente consulta; cada procedimento declara ação padrão, categoria, time e prioridade |

#### Vocabulário dos produtos

| Termo | O que é | Por que importa na triagem |
|---|---|---|
| **Hospedagem compartilhada** (planos Hospedagem Start e Hospedagem Business) | Vários clientes dividem o mesmo servidor, administrado pela empresa. O cliente tem uma conta com cota de espaço, sem acesso de administrador | O cliente não tem "disco" nem "servidor" próprios, mesmo quando escreve assim |
| **VPS** (*Virtual Private Server*, servidor virtual privado; plano VPS Pro) | Uma máquina virtual exclusiva do cliente, com sistema operacional, disco e memória próprios, dentro de um servidor físico da empresa | Serviço parado, acesso SSH e arquivos sem permissão de escrita são problemas da máquina do cliente, e alguém precisa de acesso a ela para corrigir |
| **Servidor dedicado** | Uma máquina física inteira alugada a um só cliente | Não está no catálogo atual: o pedido de migração para um é assunto comercial (`TKT-0004`) |
| **Plano gerenciado** | Plano em que a empresa administra o sistema operacional e os serviços do servidor; no não gerenciado, o cliente administra tudo | Define se um problema é responsabilidade do Suporte. O VPS Pro é gerenciado |
| **Cota** | O limite de espaço (e de número de arquivos) de uma conta de hospedagem compartilhada | "Disco cheio" em plano compartilhado é cota excedida, não disco de servidor. Foi o que tirou "disco cheio" da base (ver "O passo que parecia um e são três") |

#### Vocabulário técnico

| Termo | O que é | Onde aparece |
|---|---|---|
| **SSL / TLS** (*Secure Sockets Layer* / *Transport Layer Security*) | O protocolo que cifra a comunicação entre o navegador e o site. O SSL é o nome antigo e o TLS é a versão em uso, mas a área continua dizendo "SSL" | Categoria `ssl_certificado`, KB-101 |
| **Certificado SSL** | O arquivo que prova a identidade do site e permite a conexão cifrada. Tem validade (90 dias nos gratuitos do Let's Encrypt) e precisa ser renovado | Quando vence, o navegador mostra "site não seguro" (`TKT-0001`) |
| **HTTPS** | O endereço do site servido com SSL/TLS (porta 443); o HTTP sem cifra usa a porta 80 | KB-101 |
| **Let's Encrypt e certbot** | Let's Encrypt é a autoridade que emite certificados gratuitos; certbot é o programa que os pede e renova sozinho, por uma tarefa agendada (timer) | KB-101: a renovação automática que não rodou |
| **Desafio HTTP-01** | A prova que o Let's Encrypt exige antes de emitir: ele acessa um arquivo no site pela porta 80. Falha se a porta estiver bloqueada ou se o domínio apontar para outro endereço | Causa do KB-101 |
| **DNS** (*Domain Name System*) | O serviço que traduz o nome de um domínio no endereço IP do servidor | Categoria `dns_dominio`, KB-106 |
| **Nameserver** (`ns1`, `ns2`) | O servidor que responde pelas consultas de DNS de um domínio. Pode ser da empresa de hospedagem ou de terceiros (o registrador do domínio) | KB-106 e log do `TKT-0002` |
| **Zona DNS** | O conjunto de registros de um domínio (para onde apontam o site, o e-mail etc.) | KB-106 |
| **SERVFAIL** | Resposta de erro do DNS: o nameserver não conseguiu responder | Log do `TKT-0002` |
| **SSH** (*Secure Shell*) | O acesso remoto, por linha de comando, a um servidor | Categoria `acesso_ssh`, KB-103 |
| **fail2ban** | Programa que bloqueia (bane) o IP de quem erra a senha várias vezes seguidas | Causa do KB-103 |
| **Firewall** | O filtro que libera ou bloqueia conexões por porta e por IP | KB-101 e KB-103 |
| **nginx** | O servidor web que recebe as requisições e as entrega à aplicação do cliente | KB-104 |
| **Erro 5xx** (502, 503) | Códigos de erro do lado do servidor. 502 (*Bad Gateway*) quer dizer que o nginx está no ar, mas a aplicação por trás dele não respondeu | Categoria `site_fora_do_ar`, KB-104 |
| **Deploy** | A publicação de uma nova versão da aplicação do cliente no servidor | KB-104: erro que começa logo depois de um deploy |
| **Webmail** | A página web por onde o cliente lê o e-mail do domínio | Relato do `TKT-0002` |
| **Backup e snapshot** | Cópia de segurança dos dados; snapshot é a cópia do disco inteiro num instante | Categoria `backup`, KB-105 |
| **Inode** | A unidade que o sistema de arquivos usa por arquivo. Um disco pode "encher" por excesso de arquivos pequenos mesmo com espaço livre | Uma das três situações por trás de "disco cheio" (ver "O passo que parecia um e são três") |
| **Dono e permissões de arquivo** | Cada arquivo e pasta tem um usuário dono e regras de quem pode ler e gravar. Com o dono errado, a aplicação recebe "permissão negada" ao gravar, mesmo com o site no ar | Causa e solução do KB-102 |
| **FTP** (*File Transfer Protocol*) | Protocolo de envio de arquivos para o servidor; o erro 550 é "arquivo indisponível ou sem permissão" | Exemplo do §2.6 |

#### Regras que a área conhece e que não estavam escritas

1. **O que separa "anotar" de "escalar" é o acesso que a correção exige.** O analista de suporte (N1) tem acesso operacional, pelo painel de administração: consegue renovar um certificado, liberar um IP banido e reexecutar um backup. São operações de rotina, documentadas e que se desfazem. Ele não tem acesso de administrador (root) aos servidores. Tudo o que exige esse acesso (corrigir o dono de arquivos, reiniciar a aplicação, mexer no DNS) é feito por um time N2 e vira chamado interno. É por isso que KB-101, KB-103 e KB-105 são "anotar", e KB-102, KB-104 e KB-106 são "escalar".
2. **O time de um procedimento "anotar" é o dono do procedimento, não o destino da anotação.** A anotação sempre vai para o analista de suporte. O campo `time_destino` de um procedimento "anotar" diz quem mantém o guia e para quem o analista escala se a correção sugerida não resolver (por exemplo, a Segurança no KB-103).
3. **O SLA é de resolução, e o relógio começa na abertura do chamado interno.** O tempo que o chamado externo passa na triagem, ou à espera da confirmação do analista, não conta no SLA do time interno. Por isso a confirmação tem prazo próprio, de **20 minutos** (§2.1): um P1 parado esperando o "sim" do analista perde tempo sem que nenhum SLA registre. Vencido o prazo, o chamado vai para a fila humana com as considerações do agente e, se o chamado interno seria P1, o gestor de suporte é avisado.
4. **O cliente fala "meu servidor" mesmo quando não tem um.** Quem contrata hospedagem compartilhada escreve "meu servidor caiu" ou "o disco encheu". O plano real vem do cadastro (`consultar_ticket`), não do texto, e o agente não corrige o cliente.
5. **A responsabilidade do Suporte termina onde começa o que é do cliente.** No VPS Pro, gerenciado, a empresa cuida do sistema operacional, do servidor web, do disco, do backup e do DNS que ela hospeda. O código da aplicação e o deploy são do cliente. No KB-104, a Infraestrutura restabelece o serviço (reinicia o processo, valida o nginx); reverter um deploy é feito em acordo com o cliente.
6. **Nem todo nameserver é da empresa.** Se o domínio usa nameservers de terceiros, uma falha de DNS não é problema da Infraestrutura, e abrir um P1 para ela é erro. O relato do cliente quase nunca diz de quem é o nameserver.
7. **Pedido técnico fora do que o suporte cobre não é assunto comercial.** "Instalem o WordPress" não é venda nem defeito. Sem procedimento na base, vai para a fila humana, e o analista decide se recusa, orienta ou encaminha.

#### A exceção que decide a arquitetura: o cliente relata o sintoma, o log mostra a causa

No `TKT-0002` o cliente diz que o Webmail está fora do ar, e o log anexado (consultas que o próprio cliente fez) mostra falha de DNS, com o webmail abrindo normalmente pelo IP do servidor. Para quem é da área, as duas informações não se contradizem: se o nome `mail.zeta.com.br` não resolve, o cliente não chega ao webmail, mesmo com o serviço no ar. O cliente descreveu o **sintoma**; o log aponta a **causa**, em outro serviço.

O que o case chama de "divergência entre relato e log" é isto: a evidência anexada aponta para um serviço diferente do que o cliente relatou. O agente não age sozinho nesse caso por três razões do domínio:

- o log foi anexado pelo cliente, e o agente não tem como conferir sua origem;
- o procedimento que casa com o log (KB-106) abre um chamado P1, irreversível, e a regra 6 acima mostra que a falha pode estar num nameserver que não é da empresa;
- quem confirma a relação entre o sintoma relatado e a causa do log é uma pessoa com acesso ao ambiente.

É essa exceção que explica três decisões do desenho: `consultar_ticket` devolve o log anexado junto com o histórico; a triagem tem a classe "relato × log divergente"; e score alto na base não basta para agir quando o artigo recuperado responde ao log e não ao relato.

#### O passo que parecia um e são três: "disco cheio"

No desenho original, "disco cheio" era um caso só, coberto pelo KB-102. O domínio mostrou três situações com o mesmo relato:

| Situação | Onde ocorre | O que resolve |
|---|---|---|
| Disco do servidor cheio | VPS Pro | Infraestrutura identifica os diretórios maiores e rotaciona logs (exige acesso ao servidor) |
| Cota da conta excedida | Hospedagem Start e Business | O cliente apaga arquivos ou contrata mais espaço: é orientação do analista ou assunto comercial |
| Inodes esgotados | Qualquer plano | Há espaço livre, mas arquivos demais; a correção é outra (remover arquivos pequenos, como cache e sessões) |

Um procedimento só não servia para as três: a correção, quem a executa e até a natureza do assunto (técnico ou comercial) mudam com o plano do cliente, e o agente não usa o plano para decidir. O mesmo relato vindo de um cliente de hospedagem compartilhada seria tratado como disco de servidor, e errado.

**Decisão de 10/10/2026: "disco cheio" saiu da base simulada.** O KB-102 passou a ser "Permissão negada ao gravar arquivos" (categoria `permissao_arquivos`), por duas razões:

- **vale igual em todos os planos.** Corrigir o dono ou as permissões de um arquivo exige acesso de administrador ao servidor, que nem o cliente nem o analista de suporte têm, na hospedagem compartilhada ou no VPS Pro (regra 1). Não há uma versão do problema que seja do cliente ou do comercial;
- **cabe no mesmo SLA.** O site continua no ar e só a gravação falha: é serviço degradado, P2 (1 dia útil), para a Infraestrutura, com ação "escalar". O time, a prioridade e a ação do KB-102 não mudaram, nem o gabarito do `TKT-0003` e do `TKT-0007`.

O que se perde: o sistema deixa de ter um caso em que o plano do cliente muda o desfecho. "Disco cheio" continua sendo um relato real; sem procedimento na base, ele vai para a fila humana. Para voltar à base, precisa de três procedimentos, separados pelo metadado `planos` (`docs/base-de-conhecimento-v2.md` §4).

#### Pontos em aberto nos dados simulados

- O `TKT-0002` e o `TKT-0007` foram corrigidos no seed em 10/10/2026: o log do `TKT-0002` passou a ser o que o cliente consegue obter (consultas de DNS e acesso pelo IP, feitos antes da abertura do chamado), e o `TKT-0007` passou a ser de um cliente de VPS Pro. Os logs da Parte 1 em `logs/` são anteriores e ainda mostram o log e o cliente antigos.
- O `TKT-0005` é de um cliente de hospedagem compartilhada que fala em "servidor". Vale para testar a regra 4.
- O `TKT-0003`, o `TKT-0007` e o histórico do CLI-02 foram reescritos no seed em 10/10/2026 (permissão negada ao gravar arquivos, no lugar de disco cheio). Os logs em `logs/` e os resultados citados no §2.7, em `docs/modelos.md` e em `docs/prompts.md` são anteriores e falam de disco cheio. Os 8 casos ainda não foram executados com o seed novo.
- O prazo para o analista confirmar uma ação irreversível foi definido em 10/10/2026: 20 minutos, e depois disso fila humana com as considerações do agente (§2.1 e regra 3). Na mesma data ficou decidido que a rejeição do analista tem o mesmo destino, e que o prazo vencido de um chamado que seria P1 avisa o gestor (§2.1). Tudo isso está implementado para a abertura de chamado interno (`docs/arquitetura.md` §7); nenhum dos 8 casos simulados o exercita com o modelo real, só os testes offline.
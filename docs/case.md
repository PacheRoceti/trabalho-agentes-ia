# Case — Agente de Triagem e Abertura de Chamado Interno

> Esta é a v2 do case, atualizada após a mudança de escopo: o projeto deixou de ser um agente gerador de dashboard de consolidação e passou a ser um agente que analisa o chamado do cliente, consulta a base de conhecimento interna e propõe uma solução ou abre um chamado interno. Mais detalhes em `docs/arquitetura-v1.md` e `docs/base-de-conhecimento-v1.md`.

## 1. O case — indústria e problema

**Setor.** Área interna de empresa — operações de Suporte/Customer Success de uma empresa de hospedagem de servidores e serviços (hosting) para clientes externos.

**O problema, em uma frase.**

> Excesso de trabalho manual no processo de ingresso dos chamados e falta de padronização das informações dos chamados internos.

**O contexto.**

*O que acontece hoje, sem o sistema:* cada chamado aberto por um cliente externo passa primeiro pelas mãos de um analista, que precisa ler a descrição livre do problema, decidir se é algo já documentado, se é uma dúvida comercial fora do escopo do suporte, ou se precisa ser escalado para outro time interno — e então abrir manualmente o chamado interno correspondente. Como cada analista faz essa triagem e esse registro do seu próprio jeito, as informações que chegam ao time de destino não seguem um padrão fixo (categoria, resumo, nível de certeza da causa variam de analista para analista), o que atrasa o entendimento do problema por quem recebe o chamado.

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

## 2. Os usuários, e como será a interação

**Tabela de perfis:**

| Perfil | O que quer | O que sabe | O que pode fazer |
|---|---|---|---|
| Analista de suporte | Menos tempo gasto triando manualmente cada chamado; chamados internos já padronizados quando chegam para validar ou executar | Conhece o processo de triagem e os casos cobertos pela base de conhecimento | Valida e executa a correção sugerida pelo agente quando não há escalonamento; trata os casos que o agente não conseguiu resolver sozinho (baixa confiança, sem informação suficiente) |
| Time interno (destino do chamado escalado) | Receber o chamado já classificado, resumido e com o parecer da base de conhecimento anexado | Conhece a área técnica ou comercial da sua especialidade | Recebe, executa e resolve o chamado interno escalonado; não decide prioridade sozinho |
| Cliente externo | Ser respondido e direcionado corretamente | Só vê o próprio chamado, sem acesso a nada interno | Abre o chamado inicial (é o input do sistema); recebe as atualizações automáticas de escalonamento ou redirecionamento, quando existirem |

**O usuário principal** é o **time interno** que recebe o chamado escalado — é para ele que a qualidade da classificação, do resumo e do parecer da base de conhecimento precisa ser boa; quando há conflito (ex.: o analista quer despachar rápido e isso significaria enviar informação incompleta ao time de destino), a prioridade do sistema é a qualidade da informação entregue ao time interno, não a velocidade percebida pelo analista.

**A interação, concretamente:** não é um chat. O sistema é disparado pelo evento de abertura do chamado no sistema externo — ninguém inicia uma conversa com o agente.

Quatro diálogos de exemplo, cobrindo as quatro ações possíveis (baseados no fluxo descrito em `docs/arquitetura-v1.md`):

*Caso 1 — escalonamento:*
```
Cliente (chamado externo): "Não consigo exportar o relatório mensal em PDF, dá erro toda vez que tento."

[agente classifica: categoria = bug_funcional, confiança = 0.86, rota = conhecido]
[agente busca na base de conhecimento: encontra KB-114, confiança do parecer = 0.74]
[confiança acima do limiar -> abre chamado interno automaticamente]

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

**O que o usuário não informa de primeira, que o sistema precisa descobrir:** o cliente não diz se o problema já tem uma solução documentada, qual time interno deve resolver, nem se o assunto é de fato suporte técnico ou comercial — o agente precisa classificar o texto livre do chamado, buscar na base de conhecimento e decidir isso sozinho, sem que ninguém pergunte.

## 3. Os ganhos esperados

**Por que agente, e não software comum:** classificar o texto livre de um chamado em uma de quatro rotas, e julgar se a correspondência encontrada na base de conhecimento é confiável o suficiente para abrir o chamado automaticamente ou exige um humano, depende de interpretar linguagem não estruturada e pesar uma confiança contínua a cada chamado — não é uma consulta fixa nem um conjunto de regras `if` sobre campos estruturados.

**Eixo(s) de ganho:**

| Eixo | Linha de base (medida) | Alvo | Ganho | Volume |
|---|---|---|---|---|
| Tickets internos com SLA estourado | 21 tickets em atraso atualmente, alguns abertos há até 20 dias | 15 tickets atrasados/mês | Tickets internos abertos com mais informação tendem a ser tratados mais rápido, pois facilitam análise | 30 tickets em atraso /mês |
| Volume de chamados tratados por analista | 2,5 chamados/hora, em média | 4 chamados/hora | Com o agente fazendo triagem, redirecionamento e formatação, o analista ganha agilidade. Mas, obriga o analista a realizar análises mais complexas com tempo excedente | 433/mês |

**O ganho para o usuário** (analista: mais chamados tratados por hora, já que o agente assume a triagem, o redirecionamento e a formatação da informação) **não é exatamente o mesmo que o ganho para o negócio** (menos tickets internos com SLA estourado, já que chegam ao time interno com mais informação. E menos tempo de time "caro" gasto com análises de menor relevância). Não identificamos tensão direta entre os dois eixos, até agora — os dois dependem da mesma mudança (triagem e formatação automatizadas). Vale revisitar se, na prática, o aumento de volume tratado por hora vier à custa de tickets menos bem formatados chegando aos times internos — esse é o trade-off que o limiar de confiança da etapa de decisão (`docs/arquitetura-v1.md`) existe justamente para controlar.
# Case — Consolidador de Tickets de Suporte

## 1. O case — indústria e problema

**Setor.** Área interna de empresa — operações de Suporte/Customer Success
de uma empresa que presta um produto ou serviço web (SaaS) a clientes
externos.

**O problema, em uma frase.**

> A gestão não tem visão em tempo real de quais tickets de clientes estão
> abertos, há quanto tempo e com que prioridade, porque a consolidação
> depende de planilha atualizada manualmente, toda semana, por vários
> analistas.

**O contexto.**

*O que acontece hoje, sem o sistema:* cada analista consulta
individualmente o sistema externo de chamados (a ferramenta de suporte ao
cliente) e transcreve manualmente os dados relevantes para uma planilha
compartilhada, uma vez por semana. Como a tarefa é dividida entre várias
pessoas, a consolidação final depende de que todos façam isso de forma
consistente e no mesmo dia — o que raramente acontece. Isso gera perda de
tempo operacional, retrabalho e risco de erro, já que a mesma atividade
está espalhada entre várias pessoas sem um dono único.

*As regras do domínio:*
- Prioridades por SLA: P1 crítico = 4h, P2 = 24h, P3 = 3 dias úteis.
- Ticket em status "aguardando cliente" pausa a contagem de SLA.
- Reabertura de um ticket já fechado reabre o ticket original (não cria
  um novo) — e reincidência gera prioridade maior automaticamente.
- Alçada: só o gestor pode reclassificar a prioridade de um ticket.
  Nenhum chamado pode ser encerrado, mesmo que tenha sido aberto com
  informação insuficiente — ele precisa permanecer aberto (ex.: em um
  status como "aguardando informação") até ser de fato resolvido.

*O que dá errado hoje — os casos difíceis:*
- **O caso central do sistema:** um ticket fica parado por
  responsabilidade de um time interno, que por sua vez precisa
  redirecioná-lo a um terceiro time. A demora no SLA aparece registrada
  contra o time atual, mas a causa real do atraso não é dele — é preciso
  que o sistema identifique de quem é a responsabilidade real pelo tempo
  parado, não só quem está com o ticket no momento da consolidação.
- Ticket sem prioridade definida no sistema externo, que o analista
  precisa inferir manualmente hoje.
- Divergência entre o que está escrito na planilha e o status real no
  sistema externo (esquecimento ou erro de transcrição).
- SLA estourado que só é percebido na consolidação semanal — ou seja,
  dias depois de já ter estourado.
- Reincidência de um ticket reaberto que não é sinalizada com a
  prioridade maior que a regra exige.

*O que a indústria já faz com agentes nesse problema* (detalhado com
fontes em [`fontes.md`](fontes.md)):

1. **CEGID** (caso Google Cloud) — agente conversacional de suporte que
   resolve o que consegue e, quando não consegue, resume a conversa e
   sugere abrir um chamado. Reduziu o volume geral de chamados em 17%
   (40% nas áreas onde foi implantado), com 93% de confiabilidade nas
   respostas. Padrão provável: **roteador** (resolve aqui vs. vira
   chamado). A divulgação não conta a base de chamados antes do projeto,
   nem o custo de manter uma equipe de nove pessoas envolvida.

2. **Equinix — Service Desk L1** (citado via Moveworks) — agente de
   triagem e roteamento de chamados de nível 1, com 96% de acurácia na
   classificação e redução de cerca de um terço no tempo de resolução.
   Padrão provável: **roteador puro**. A divulgação não informa a
   acurácia do roteamento humano antes (linha de base), e vem do
   fornecedor da tecnologia, não da própria Equinix.

3. **Nevada DETR — Appeals AI Assistant** (caso Google Cloud) — assistente
   que sintetiza dados de um caso, espalhados em várias fontes, para
   ajudar um analista humano a decidir sobre recursos de seguro-desemprego
   até 4x mais rápido. Padrão provável: **orquestrador-trabalhador ou
   chain de síntese** — é o caso mais próximo do nosso: junta dado
   espalhado numa visão única para uma pessoa decidir. Não diz "4x mais
   rápido" em relação a quê exatamente, nem fala em taxa de erro da
   síntese.

---

## 2. Os usuários, e como será a interação

**Tabela de perfis:**

| Perfil | O que quer | O que sabe | O que pode fazer |
|---|---|---|---|
| Analista de suporte | Registrar o andamento sem perder tempo com planilha | Conhece os tickets que ele mesmo atende | Consulta e atualiza status; não decide prioridade sozinho |
| Gestor/coordenador | Visão consolidada e atualizada, sem esperar a planilha semanal | Conhece a equipe e as prioridades de negócio | Único que reclassifica prioridade; nenhum chamado pode ser encerrado por ninguém, mesmo com informação insuficiente |
| Cliente externo (indireto) | Ser respondido dentro do prazo | Só vê o próprio ticket | Não interage com o sistema diretamente |

**O usuário principal** é o gestor/coordenador — é para ele que a visão
consolidada existe; o analista é fonte de dado, não o beneficiário
principal quando os interesses dos dois entram em conflito (ex.: o
sistema sinalizar um atraso que expõe o time do analista).

**A interação, concretamente:** um **dashboard web, atualizado
automaticamente** — não um chat. Ninguém inicia uma conversa: o agente
roda em background, de tempos em tempos (ex.: a cada hora, ou disparado
por atualização de ticket no sistema externo), consulta o sistema externo
e o histórico de trâmite de cada ticket, e atualiza a visão consolidada
sozinho. Gestor e analistas apenas **abrem a página** quando querem
saber o estado atual — zero trocas necessárias para o dado básico
aparecer.

O dashboard mostra uma lista de tickets, com colunas de prioridade,
tempo em aberto e status — e dois sinalizadores que só existem porque o
agente cruzou fontes que a planilha manual não cruzava:

```
┌────────────────────────────────────────────────────────────────────┐
│ TICKET   PRIORIDADE  TEMPO ABERTO  STATUS              SINALIZADORES│
├────────────────────────────────────────────────────────────────────┤
│ T-8821   Alta        4 dias        Sem resposta        ⚠ SLA estourado
│ T-8790   Alta        3 dias        Aguardando outro time ⚠ Responsável
│                                                            real: Integrações
│                                                            (não Infraestrutura)
│ T-8805   Média       3 dias        Aguardando cliente   ⚠ Divergência:
│                                                            planilha da semana
│                                                            passada dizia
│                                                            "em andamento"
└────────────────────────────────────────────────────────────────────┘
```

Ao clicar em um ticket sinalizado, o gestor vê a justificativa que o
agente gerou — por exemplo, para o `T-8790`: *"Atribuído ao time de
Infraestrutura há 3 dias, mas o problema depende do time de Integrações.
Infraestrutura encaminhou a solicitação de redirecionamento há 2 dias,
ainda não aceita. O atraso de SLA está sendo contabilizado contra
Infraestrutura, mas a responsabilidade real, a partir do encaminhamento,
é do time de Integrações."*

Quando o agente não consegue determinar algo com confiança (ex.: o
histórico de trâmite está incompleto, ou o ticket foi redirecionado
tantas vezes que não dá para atribuir responsabilidade com segurança),
o ticket aparece marcado como **"revisão manual necessária"**, em vez de
o sistema arriscar um palpite silencioso.

**O que o usuário não informa de cara, que o sistema precisa descobrir:**
duas coisas, e são exatamente os dois casos difíceis do domínio —
(1) a divergência entre o que está registrado manualmente e o que o
sistema externo realmente diz, e (2) de quem é a responsabilidade real
por um ticket parado quando ele passou por mais de um time. Ninguém
pergunta nada — é exatamente esse o ponto: o sistema precisa cruzar as
fontes e sinalizar isso sozinho, sem que ninguém peça. Isso também dá ao
case um **verificador** natural: qualquer divergência ou atribuição de
responsabilidade que o dashboard aponte pode ser conferida comparando
com o histórico de trâmite real do ticket no sistema externo.

---

## 3. Os ganhos esperados

**Por que agente, e não software comum:** decidir se uma divergência
entre planilha e sistema externo é relevante, e de quem é a
responsabilidade real por um ticket que passou por vários times, depende
de cruzar várias fontes e julgar contexto (SLA, histórico de trâmite,
status) a cada ticket — não é uma consulta fixa, muda conforme o
histórico específico de cada chamado.

**Eixo(s) de ganho:**

| Eixo | Linha de base (medida) | Alvo | Ganho | Volume |
|---|---|---|---|---|
| Tempo de consolidação semanal | *[a medir: cronometrar com os analistas quantas horas/semana são gastas]* | | | *[a medir: quantos tickets/semana]* |
| Erro e retrabalho (divergências não detectadas) | *[a medir: quantas divergências entre planilha e sistema externo são encontradas hoje, e como]* | | | |

> **Pendência do grupo, antes da próxima entrega:** medir a linha de base
> de verdade — cronometrar quanto tempo cada analista gasta atualizando a
> planilha esta semana, e contar quantos tickets isso envolve. Sem isso,
> esta seção é opinião, não venda.

**O ganho para o usuário** (analista: menos tempo gasto em transcrição
manual, hoje repetitiva e passível de erro) **não é o mesmo que o ganho
para o negócio** (gestor: visibilidade em tempo real e atribuição correta
de responsabilidade por atrasos de SLA, o que afeta cobrança de
performance entre times). Não identificamos tensão direta entre os dois
até agora — ambos querem menos tempo gasto em transcrição manual — mas
vale revisitar isso quando o sistema apontar responsabilidade de atraso
contra um time específico, o que pode gerar resistência dos analistas
daquele time.

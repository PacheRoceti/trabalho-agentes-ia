# Fontes — casos de indústria consultados

## 1. CEGID — agente conversacional de suporte

**Link:** https://cloud.google.com/customers/cegid

**O que fizeram:** implantaram um agente conversacional (Google Cloud
Customer Engagement Suite) que estabelece um diálogo real com o cliente,
adaptando a linguagem ao nível de conhecimento dele. Quando o problema
excede o que o agente consegue resolver, ele sugere abrir um chamado,
já resumindo a conversa para o time humano. Em paralelo, os atendentes
humanos usam o Agent Assist para ter acesso rápido a informação relevante
durante casos complexos.

**Números divulgados:** média de 225 conversas por dia, mais de 34.605
conversas desde o lançamento, 93% de taxa de confiabilidade nas
respostas, e apenas 17% de escalonamento para chamado. Resultado: redução
geral de 17% no volume de chamados de suporte, chegando a 40% nas áreas
onde o agente foi especificamente implantado. Projeto sustentado por uma
equipe de nove pessoas (4 especialistas de negócio, 3 do time de TI da
CEGID, 2 de um integrador do Google Cloud), com mais de 20 atualizações
desde o lançamento.

**Padrão de arquitetura provável:** roteador — o agente classifica entre
"resolvo aqui" e "isso precisa virar chamado para um humano", e só a
segunda rota produz um ticket.

**O que a divulgação não conta:** o volume de chamados *antes* do
projeto (a redução de 17% é sobre qual base?); o custo de construção e
manutenção; e a metodologia exata usada para medir "confiabilidade de
resposta".

---

## 2. Equinix — Service Desk L1

**Link (fonte secundária, do fornecedor da tecnologia):**
https://www.moveworks.com/us/en/resources/blog/ai-agents-for-itsm-automation

**O que fizeram:** implantaram um agente de IA para triagem e roteamento
automático de chamados de suporte de TI de nível 1 (L1), decidindo a
categoria e a equipe correta para cada chamado antes de qualquer
intervenção humana.

**Números divulgados:** 96% de acurácia na classificação e roteamento
correto dos chamados, com redução de "cerca de um terço" no tempo de
resolução.

**Padrão de arquitetura provável:** roteador puro — classifica e
despacha, sem tentar resolver o conteúdo do chamado.

**O que a divulgação não conta:** "cerca de um terço" é uma faixa vaga,
não um número exato; não há informação sobre a acurácia do roteamento
humano antes do projeto (linha de base); e a fonte é o próprio fornecedor
da tecnologia falando do cliente — não uma publicação da Equinix — o que
pede leitura mais cética que uma fonte primária.

---

## 3. Nevada DETR — Appeals AI Assistant

**Link:** https://cloud.google.com/transform/25-of-my-favorite-roi-customer-stories-gen-ai
(item 18 da lista)

**O que fizeram:** o Departamento de Emprego, Treinamento e Reabilitação
de Nevada (DETR) desenvolveu, com BigQuery e Vertex AI, um assistente que
sintetiza os dados de um caso de recurso de seguro-desemprego, para
ajudar os analistas ("Appeals Referees") a decidir com mais agilidade e
consistência.

**Números divulgados:** decisões sobre recursos de benefício tomadas até
4 vezes mais rápido.

**Padrão de arquitetura provável:** orquestrador-trabalhador ou chain de
síntese — o sistema junta dado espalhado em várias fontes e produz um
resumo estruturado para uma pessoa decidir. É o caso mais próximo do
nosso projeto: não decide sozinho, mas consolida a informação que hoje
está espalhada, para quem decide (no nosso caso, o gestor) enxergar de
uma vez.

**O que a divulgação não conta:** "4x mais rápido" comparado com qual
processo exatamente (só a leitura do caso, ou o processo de decisão
inteiro?); nenhuma métrica de taxa de erro ou qualidade da síntese; nem
custo ou tempo de implementação do projeto.v

Preços de lista consultados em 21/09/2026 (agregadores; confirmar na página oficial da Mistral):

- Mistral, página oficial de preços: https://mistral.ai/pricing/
- Ministral 3 (3B, 8B, 14B) — AI Pricing Guru, base de 02/09/2026: https://www.aipricing.guru/mistral-ai-pricing/
- Família Ministral 3, tarifas simétricas — BenchLM, verificado em 18/09/2026: https://benchlm.ai/mistral/api-pricing
- Plano gratuito (Experiment): https://pricepertoken.com/endpoints/mistral/free e https://www.free-model.com/providers/mistral-ai/ (as fontes divergem sobre limites e sobre uso dos dados para treino; conferir no painel da conta, em Limits)
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
resumo estruturado para uma pessoa decidir. É comparável à etapa do nosso
agente que busca na base de conhecimento e redige o resumo para quem vai
validar ou executar; o caso mais próximo do nosso projeto é a CEGID (item 1).

**O que a divulgação não conta:** "4x mais rápido" comparado com qual
processo exatamente (só a leitura do caso, ou o processo de decisão
inteiro?); nenhuma métrica de taxa de erro ou qualidade da síntese; nem
custo ou tempo de implementação do projeto.

Preços de lista consultados primeiro em 21/09/2026 em agregadores (links abaixo). Os dos três
candidatos foram conferidos em 17/10/2026 nas páginas oficiais de cada modelo, na documentação da
Mistral, e são os que valem; em todas, o preço de entrada é igual ao de saída. O do
`mistral-embed`, o modelo da busca vetorial, foi conferido no mesmo dia: US$ 0,10 por milhão de
tokens, um preço só, porque o embedding não gera texto. Antes o projeto usava US$ 0,05, lido no
perfil do grupo na Mistral; vale a página oficial (`modelos.md`, Fontes desta análise; a conta do
custo de embedding está no `rag.md` §4.3).

| Modelo (alias usado) | Versão da página | US$ por milhão de tokens (entrada / saída) | Página oficial, conferida em 17/10/2026 |
|---|---|---|---|
| `ministral-3b-latest` | Ministral 3 3B (`ministral-3b-2512`) | 0,10 / 0,10 | https://docs.mistral.ai/models/ministral-3-3b-25-12 |
| `ministral-8b-latest` | Ministral 3 8B (`ministral-8b-2512`) | 0,15 / 0,15 | https://docs.mistral.ai/models/ministral-3-8b-25-12 |
| `ministral-14b-latest` | Ministral 3 14B (`ministral-14b-2512`) | 0,20 / 0,20 | https://docs.mistral.ai/models/ministral-3-14b-25-12 |
| `mistral-embed` | Mistral Embed (`mistral-embed-2312`) | 0,10 (só entrada) | https://docs.mistral.ai/models/mistral-embed-23-12 |

As páginas não dizem para qual versão o alias `-latest` aponta: a tabela supõe que é a de
dezembro de 2025 (`2512`), a que as páginas descrevem.

- Mistral, página oficial de preços: https://mistral.ai/pricing/
- Ministral 3 (3B, 8B, 14B) — AI Pricing Guru, base de 02/09/2026: https://www.aipricing.guru/mistral-ai-pricing/
- Família Ministral 3, tarifas simétricas — BenchLM, verificado em 18/09/2026: https://benchlm.ai/mistral/api-pricing
- Plano gratuito (Experiment): https://pricepertoken.com/endpoints/mistral/free e https://www.free-model.com/providers/mistral-ai/ (as fontes divergem sobre limites e sobre uso dos dados para treino; conferir no painel da conta, em Limits)

---

## Framework do grafo (Parte 2)

- Enunciado da Parte 2, que define o que o grafo, o estado e a pausa precisam ter:
  https://github.com/celsocrivelaro/senac-agentes-llm/blob/main/trabalho/02-segunda-entrega.md
- LangGraph, versão 1.2.14 (fixada no `requirements.txt`): https://pypi.org/project/langgraph/
  e o repositório https://github.com/langchain-ai/langgraph
- Checkpointer em SQLite, versão 3.1.1: https://pypi.org/project/langgraph-checkpoint-sqlite/

O que o `src/grafo.py` usa da biblioteca (`StateGraph`, `context_schema`, `interrupt`,
`Command(resume=...)`, `SqliteSaver`, `recursion_limit`) foi conferido contra o código das versões
instaladas, e não contra um tutorial: a assinatura de várias dessas peças mudou entre versões.

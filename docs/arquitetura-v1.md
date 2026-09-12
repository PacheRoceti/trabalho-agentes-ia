# Arquitetura v1 — Triagem e abertura de chamado interno

> `v1`: primeira versão no papel, antes do código. Vai mudar — a Parte 2 do trabalho registra o que mudou e por quê.

## 1. Entrada

- **O quê**: evento de outro sistema — um chamado novo criado por um cliente externo na ferramenta de suporte (texto livre da descrição + metadados: id do ticket, cliente, produto/módulo, timestamp).
- **De onde, e quem dispara**: o sistema acorda sozinho. Disparado pela criação do chamado no sistema externo, ninguém abre uma conversa com o agente.
- **Quão heterogêneo**: ~50% dúvidas rotineiras com resolução já documentada na base; ~30% problemas técnicos com correspondência parcial/incerta na base; ~15% fora do escopo do suporte (ex.: pedido comercial, cobrança); ~5% chamado sem informação suficiente para classificar. Heterogêneo o bastante para justificar um roteador logo na entrada.

## 2. System

- **System prompt, em uma frase**: "Este sistema recebe um chamado externo, classifica e resume, verifica na base de conhecimento se há resolução conhecida, e abre um chamado interno direcionado ao time responsável. Ele não resolve o problema do cliente, não decide prioridade sozinho em caso de dúvida, e nunca fecha um chamado."
- **Ferramentas**:
  | Ferramenta (Subagentes) | Leitura/Escrita | Reversível |
  |---|---|---|
  | `classificar_categoria` (regra em código + fallback LLM) | leitura | — |
  | `buscar_base_conhecimento` (RAG, busca vetorial) | leitura | — |
  | `abrir_chamado_interno` (API do sistema de tickets interno) | **escrita** | não (cria um registro real) — mitigado com chave idempotente |
  | `encaminhar_fila_humana` | escrita | sim (reversível, é só uma fila) |
- **Estado**: sobrevive entre passos apenas o *extraído*, nunca o texto bruto do cliente repetido: `id_ticket_externo`, `categoria`, `resumo_estruturado`, `parecer_rag` (com confiança), `decisão_final`.
- **Orçamento**: 1 chamada de classificação (sem retry — falha vira fila humana); 1 chamada de agregação; 1 busca vetorial (top-k=5) + 1 chamada de síntese do parecer; 1 chamada de decisão final. Teto de tempo: 30s ponta a ponta (é um processo em background, não uma resposta em tempo real ao cliente).

## 3. Processamento — o esboço do fluxo

```
1. ENTRADA      evento: novo chamado no sistema externo             [—]

2. TRIAGEM      classifica em 4 rotas                          [ROUTER]
                  conhecido    -> segue para 3
                  incerto      -> segue para 3 (mesma rota, com flag)
                  fora escopo  -> encaminha ao time comercial, encerra fluxo
                  sem info     -> fila humana

3. AGREGAÇÃO    formata o chamado + categoria em resumo   [SEQUENCIAL, 1 chamada]

4. PARECER RAG  busca na base + redige parecer            [SEQUENCIAL, 1 busca + 1 chamada]

5. DECISÃO      abrir automaticamente ou escalar humano         [ROUTER]

6. REGISTRO     grava chamado interno                  [ESCRITA - idempotente]

7. RETORNO      confirma abertura / notifica fila humana                [—]
```

## 4. O que sai de cada etapa

```
2. TRIAGEM
   entra:  {"texto": "não consigo exportar o relatório mensal em PDF"}
   sai:    {"categoria": "bug_funcional", "confianca_classificacao": 0.86, "rota": "conhecido"}

3. AGREGAÇÃO
   entra:  categoria + dados do ticket (produto, cliente, timestamp) — não o texto bruto de novo
   sai:    {"resumo": "Exportação de relatório mensal falha em PDF, módulo Relatórios", "categoria": "bug_funcional"}

4. PARECER RAG
   entra:  o resumo estruturado da etapa 3
   sai:    {"parecer": "Bug conhecido: exportação PDF falha quando filtro de período > 90 dias (KB-114)",
            "confianca_parecer": 0.74, "fonte_kb": "KB-114"}

5. DECISÃO
   entra:  categoria + parecer + confianca_parecer
   sai:    {"acao": "abrir_automatico", "time_destino": "Engenharia - Relatórios"}
           (se confianca_parecer < 0.5 -> {"acao": "escalar_humano"})

6. REGISTRO
   entra:  resumo + parecer + time_destino
   sai:    {"chamado_interno_id": "INC-4471", "status": "aberto"}

7. RETORNO
   sai:    "Chamado INC-4471 aberto para Engenharia - Relatórios, com o parecer da base de conhecimento anexado."
```

**O que o time interno efetivamente vê** (usuário final da etapa 6/7): um chamado interno já rotulado, com resumo do problema e o parecer da base de conhecimento anexado — algo como: *"INC-4471 — Bug exportação PDF (KB-114 aplica). Cliente: Acme Corp. Aberto por: Agente de Triagem."*

## 5. Justificativa dos padrões

- **TRIAGEM — Router**: entrada heterogênea de verdade (4 rotas com proporções distintas), e as rotas não são triviais de separar por regra fixa (texto livre). O padrão anterior na tabela (sequencial) não resolveria porque não há "etapa fixa" — é uma classificação, não uma sequência.
- **AGREGAÇÃO — Sequencial**: etapa conhecida e fixa (sempre pega classificação + dados → resumo). Nenhuma decisão de fluxo acontece aqui; um Router ou Agente seriam autonomia sem contrapartida.
- **PARECER RAG — Sequencial (busca + síntese)**: a busca é uma consulta, não uma investigação aberta — não precisamos de um Agente com múltiplos passos porque o item já foi extraído na etapa 3. Se a taxa de "base incompleta" crescer, este é o primeiro candidato a virar Agente com teto de re-busca.
- **DECISÃO — Router**: decide entre duas rotas conhecidas (abrir automático vs. escalar humano) com base num único número (confiança). Não é um Avaliador porque não há revisão iterativa de texto — é uma classificação binária por threshold.
- **REGISTRO — Escrita, não é padrão de autonomia**: é código determinístico chamando a API do sistema interno. Marcado como não-reversível (abre um chamado real) e por isso é idempotente por `id_ticket_externo`, para não duplicar em caso de reprocessamento.

Parando na tabela de decisão da nota 01-6: nenhuma etapa exige Orquestrador, Avaliador ou Agente livre — é um **workflow com dois pontos de roteamento**. Se a etapa 4 (RAG) começar a errar por buscas mal formuladas, é o ponto onde a autonomia cresceria primeiro (Router → Agente com teto de tentativas de busca).

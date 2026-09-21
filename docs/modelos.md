# Análise de modelos (item 3)

> **Status.** Todos os números deste documento foram **medidos** em execuções reais (logs em
> `logs/`).

## Restrição que define a escolha: o plano gratuito da nossa conta

O grupo não vai pagar por API. A conta da Mistral usada no trabalho está no plano gratuito, e
um teste de uma chamada por modelo (`python src/testar_api.py <modelo>`) mostrou o que a
chave alcança:

| Modelo | Resultado com a nossa chave |
|---|---|
| `ministral-3b-latest`, `ministral-8b-latest`, `ministral-14b-latest`, `open-mistral-nemo`, `open-mistral-7b`, `codestral-latest` | funcionam (limite observado: 188 requisições/min e 625 mil tokens/min) |
| `mistral-small-latest`, `mistral-medium-latest` | recusados: limite de **0 requisições/min** (429) |
| `mistral-large-latest` | recusado: "modelo não disponível no seu nível de assinatura" (403) |

Ou seja, **a escolha não é livre entre o mercado inteiro: é entre os modelos pequenos que a chave
libera.** Isso é uma limitação assumida, e a §3.4 diz o que mudaria com orçamento.

## 3.1 Os candidatos, e por que estes eixos

O caso é um processo **em segundo plano**, disparado pela abertura de um chamado; ninguém espera
a resposta na frente da tela (teto de 30 s ponta a ponta, definido na arquitetura). Cada execução
faz **3 a 5 chamadas ao modelo** (o laço de ferramentas), com prompts de ~2 mil tokens.

| Eixo | Pesa no nosso caso? | Por quê |
|---|---|---|
| Tool calling | **Pré-requisito** | Sem ele não há laço: as quatro ferramentas são o agente |
| Capacidade de julgamento | **Sim, é o eixo que decide** | Os casos difíceis (divergência relato × log; reincidência; correspondência parcial; erro de ferramenta) pedem julgar e obedecer ao procedimento, não só classificar |
| Custo | **Sim, mas pequeno** | Os três candidatos custam da ordem de centésimos de centavo por chamado (§3.2); o custo real é zero no plano gratuito |
| Aceita `temperature=0` | **Sim** | Classificação e escolha de ferramenta precisam ser reproduzíveis |
| Política de dados | **Não hoje, sim em produção** | O plano gratuito pode usar os dados enviados para melhorar os modelos (as fontes divergem sobre ser opcional). Com dados simulados não importa; com chamado real de cliente, seria bloqueio |
| Latência | Pouco | Processo em segundo plano; observado: 0,5 a 0,7 s numa chamada mínima |
| Janela de contexto | Não discrimina | Uso de ~7 mil tokens por execução; qualquer candidato comporta |
| Multimídia | Não | O chamado é texto |

Os três candidatos são da mesma família (Ministral), em três tamanhos. Isso isola o efeito do
**tamanho** do modelo sobre o julgamento, com mesma API, mesmo prompt e mesma chave:

| | **ministral-3b-latest** | **ministral-8b-latest** | **ministral-14b-latest** |
|---|---|---|---|
| Papel na comparação | O menor: o piso | O da base do trabalho: já rodamos 3 rodadas | O maior liberado: o teto |
| Preço de lista (US$/M tokens, entrada / saída) | 0,10 / 0,10 | 0,15 / 0,15 | 0,20 / 0,20 |
| Onde roda | API pública Mistral (empresa europeia; conferir região no contrato) | idem | idem |
| Troca de código | só `LLM_MODELO` | só `LLM_MODELO` | só `LLM_MODELO` |
| Risco conhecido | Pode falhar até nos casos simples | Falhou no `TKT-0003` (ver 3.3-A) | Custo ~2x o 3B, ainda irrelevante |

**Ressalva sobre os preços.** Vêm de agregadores (dados de 02/09/2026 e 18/09/2026), não da página
oficial, e o preço só serve para **calcular o custo simulado**: o gasto real é zero. **Conferir
na página oficial da Mistral antes de entregar** e confirmar a qual versão o alias `-latest`
aponta hoje. Fontes no fim do documento.

## 3.2 A conta

```
custo por execução = tokens de entrada × preço de entrada + tokens de saída × preço de saída
                     (somados sobre as chamadas do laço)
```

**Medido, não estimado.** Rodada 3 (`ministral-8b-latest`, 7 casos): 46.583 tokens, ≈ 6.660 por
chamado. Rodada 4 (8 casos, demonstração oficial, `logs/`): 55.131 tokens, **≈ 6.890 por chamado
e ≈ US$ 0,0010 por chamado** (4 chamadas ao modelo em média). A estimativa que fiz antes de rodar
era ~6.500 tokens: acertou a ordem de grandeza. Na comparação (§3.3-B, 5 casos) cada modelo teve a
sua média:

| Modelo | Tokens por chamado (medido) | Custo por chamado | 100 execuções | 433 chamados/mês | 500 execuções no semestre |
|---|---|---|---|---|---|
| ministral-3b-latest | 9.062 | US$ 0,00091 | US$ 0,09 | US$ 0,39 | US$ 0,45 |
| ministral-8b-latest | 7.294 | US$ 0,00109 | US$ 0,11 | US$ 0,47 | US$ 0,55 |
| ministral-14b-latest | 6.999 | US$ 0,00140 | US$ 0,14 | US$ 0,61 | US$ 0,70 |

O 3B é o mais barato por token, mas **gasta 24% mais tokens** que o 8B (mais chamadas, buscas
repetidas), e a vantagem de preço quase some. Os 5 casos da comparação são os mais difíceis, então
as médias são mais altas que as da demonstração de 8 casos.

Para R$: multiplicar pela cotação do dia R$ 5,11 dia 21/09/2026. Os 500 do semestre são
desenvolvimento, testes e comparações do grupo (chute declarado, não medição).

**O que esta conta ensina.** Com prompts pequenos e centenas de chamados por mês, o custo de modelo
é irrelevante (menos de US$ 1 por mês) frente ao ganho de tempo (§2.5: ~65 horas de analista por
mês). **O custo que pesa é o do erro**, não o de tokens: chamado para o time errado, ou um caso
difícil que o modelo não sabe julgar. A conta muda de natureza se o volume for muito maior ou se
o contexto crescer com a base de conhecimento (Parte 2, RAG).

## 3.3 A verificação

### 3.3-A O experimento de prompts (medido: `ministral-8b-latest`, temperature=0)

Antes de comparar modelos, o grupo rodou três vezes os mesmos 7 casos com o mesmo modelo,
mudando só o prompt (e, na terceira, acrescentando um lembrete no laço). Logs completos em
`logs/rodada-*/`.

| Caso | Rodada 1 (v1) | Rodada 2 (v2) | Rodada 3 (v3 + lembrete) |
|---|---|---|---|
| TKT-0001 simples | OK | OK | OK |
| TKT-0002 divergência relato × log | OK | OK\* | OK |
| TKT-0003 reincidência (deve abrir chamado) | FALHOU | FALHOU | **FALHOU** |
| TKT-0999 registro inexistente | FALHOU | FALHOU | OK |
| TKT-0004 comercial | OK | OK | OK |
| TKT-0005 informação insuficiente | OK | FALHOU | OK |
| TKT-0006 correspondência parcial | OK | OK | OK |
| **Acertos** | **5 de 7** | **3 de 7** (4 com a regra corrigida\*) | **6 de 7** |

\* **Defeito do verificador, corrigido.** Na rodada 2 o verificador reprovou o `TKT-0002` porque
procurava as palavras "divergência" ou "contradiz". A leitura do log mostrou que a mensagem
gravada sinalizava a divergência corretamente ("o log anexo indica que o problema é de resolução
DNS... a causa no log não é compatível com o relato do cliente"). A regra passou a exigir que a
mensagem cite o serviço do relato (webmail) e a causa do log (DNS). A mudança foi feita **por
evidência de erro do verificador**, não para fazer o caso passar, e está anotada em
`dados/gabarito.json`.

**O que cada rodada ensinou:**

- **Rodada 1 → 2: mais regras pioraram.** A v2 acrescentou quatro regras. "Chame sempre a busca"
  fez o modelo buscar no `TKT-0005` e mandar à fila humana em vez de devolver ao cliente
  (regressão de OK para FALHOU). As regras que não funcionaram foram retiradas na v3. Para um
  modelo de 8 bilhões de parâmetros, **mais texto no prompt não significou mais obediência**.
- **Falha que se repetiu: narrar a ação em vez de executá-la.** No `TKT-0999` o modelo recebeu o
  erro com a instrução do que fazer e respondeu "registrei e encaminhei", sem chamar a
  ferramenta: **afirmou uma ação que não fez**. Só o verificador, que confere o **banco** e não o
  texto, revelou o problema. A v3 e um **lembrete no laço** (até 2 avisos quando o modelo encerra
  sem registrar desfecho) resolveram: o `TKT-0999` passou na rodada 3 com 1 lembrete; nos outros
  6 casos o lembrete não foi necessário.
- **Falha que não se resolveu: o `TKT-0003`.** O modelo pula a busca na base e decide sozinho
  mandar à fila humana por causa da divergência "terceira vez" × histórico. Nem o prompt nem o
  lembrete mudam isso, porque o modelo registra corretamente: erra o **julgamento**. É erro para
  o lado seguro (nenhum chamado aberto indevidamente).
- **Custo do experimento:** cerca de US$ 0,0010 por chamado (simulado; real: zero).

**Limite honesto.** A v2 e a v3 foram escritas **depois** de ver as falhas nestes mesmos 7 casos:
o resultado de 6 de 7 é otimista e não prova que o prompt generaliza. A Parte 2 separa um conjunto
de desenvolvimento de um de avaliação. Outro limite: 7 casos não são medição estatística.

### 3.3-B A comparação entre os três modelos

**Protocolo.** Cinco casos (`TKT-0001`, `TKT-0002`, `TKT-0003`, `TKT-0999`, `TKT-0006`), nos três
candidatos, com o **mesmo prompt** (`prompts/agente-v3.md`), o **mesmo banco inicial** e o **mesmo
verificador**. Ficaram de fora `TKT-0004` e `TKT-0005`, os casos fáceis.

**Hipótese antes de rodar** (registrada para o resultado poder nos surpreender): o 3B falha em mais
casos que o 8B; o 14B acerta o `TKT-0003`; os três acertam o caso simples `TKT-0001`.
**Resultado: só a primeira se confirmou** (3B: 3 de 5; 8B: 4 de 5). O 14B **não** acertou o `TKT-0003`,
nem foi melhor que o 8B, e o 3B **falhou** o caso simples.

**Resultado** (saída de `python src/comparar_modelos.py`, prompt v3, `temperature=0`, aprovação
automática; logs em `logs/comparacao/`):

| Caso | ministral-3b-latest | ministral-8b-latest | ministral-14b-latest |
|---|---|---|---|
| TKT-0001 (simples) | **FALHOU** (foi à fila humana) | OK | OK |
| TKT-0002 (divergência relato × log) | OK | OK | OK |
| TKT-0003 (escalonamento com reincidência) | **FALHOU** (fila humana) | **FALHOU** (fila humana) | **FALHOU** (fila humana) |
| TKT-0999 (registro inexistente) | OK | OK | OK |
| TKT-0006 (correspondência parcial) | OK | OK | **FALHOU** (abriu chamado indevido) |
| **Acertos** | **3 de 5** | **4 de 5** | **3 de 5** |
| Tokens médios por execução | 9.062 | 7.294 | 6.999 |
| Chamadas ao modelo (média) | 4,8 | 4,0 | 3,8 |
| Custo médio por execução (US$, simulado) | 0,00091 | 0,00109 | 0,00140 |
| Latência média (s) | 3,4 | 5,0 | 7,5 |

**Leitura: a causa de cada erro (lida em `logs/`, com `python src/ver_log.py <log>`).**

| Falha | O que aconteceu | Causa |
|---|---|---|
| 3B em `TKT-0001` | Buscou com **frases** ("certificado ssl", "site não seguro"), não com palavras. O score da base ficou em 0,4. Tentou registrar `anotacao_interna`; o **portão de confiança recusou** e o modelo foi à fila humana | **Ferramenta** (busca por palavra) + **modelo** (não seguiu "termos, não frases"). O sistema se comportou como projetado: recusou agir com score baixo |
| 14B em `TKT-0006` | Buscou com 4 palavras soltas e o score deu **exatamente 0,5**, que passa o portão. Abriu um chamado P1 dizendo no resumo que o erro é "intermitente" | **Portão/ferramenta**, não obediência: a busca por palavra não enxerga que o procedimento cobre falha **constante**. É o único chamado aberto indevidamente, e é o caso em que a confirmação do analista o impediria (aqui a aprovação foi automática) |
| 8B, 3B e 14B em `TKT-0003` | Nenhum buscou na base: leram "terceira vez" × histórico "1 ocorrência", e foram à fila humana pedindo verificação | **Modelo + desenho do caso**: os três tamanhos erram igual, então não é falta de capacidade; o caso mistura escalonamento com uma armadilha de afirmação do cliente. Erro para o lado seguro |
| 8B em `TKT-0007` (rodada 4) | Buscou com "disco, encheu": a base tem "cheio", e "encheu" não casa. Score baixo, fila humana, como manda a regra | **Ferramenta**: busca por palavra não entende flexão nem sinônimo. O modelo agiu certo dada a regra |

**Conclusão.** Dos quatro problemas distintos, **três nascem da busca por palavra-chave** (frases
que diluem o score, um limiar que cai exatamente no empate, uma flexão que não casa) e apenas um
do julgamento do modelo. Trocar de modelo não resolveria os três primeiros: quem resolve é a busca
semântica (RAG) com limiar calibrado, planejada para a Parte 2. Uma diferença de 1 caso entre
modelos, em 5 casos, não é diferença comprovada: o que os dados sustentam é que **o 14B não
compensa o custo e o 3B perde julgamento**, não que o 8B seja "o melhor" em termos estatísticos.

### 3.3-C Demonstração oficial (rodada 4, 8 casos, `ministral-8b-latest`)

**6 de 8 casos** conferidos pelo verificador (`logs/saida-demonstracao.txt` e `logs/TKT-*.json`).
Passaram: `0001`, `0002`, `0004`, `0005`, `0006`, `0999`. Falharam: `0003` (julgamento, acima) e
`0007` (busca por palavra, acima). O `TKT-0007` foi adicionado **depois** da comparação de modelos,
para exercitar a abertura de chamado sem a armadilha do `TKT-0003`; nenhum caso existente foi
alterado ou removido. Nenhum chamado interno foi aberto indevidamente pelo 8B.

## 3.4 A decisão

**Decisão: `ministral-8b-latest`.** Foi o que mais acertou na comparação (4 de 5), tem mais
evidência (4 rodadas, 6 de 8 na demonstração), custa ≈ US$ 0,001 por chamado (simulado; real zero
no plano gratuito) e **nenhum chamado interno foi aberto indevidamente por ele**. O 14B custa 28%
mais, é mais lento (7,5 s contra 5,0 s), não acertou mais casos e abriu um chamado indevido; o 3B
perde julgamento (falhou o caso simples).

**Condições em que mudaríamos de ideia:**

1. **Subir de modelo** se um modelo maior acertar o `TKT-0003` (o único caso de julgamento que os
   três erraram) em duas rodadas. Como o custo é irrelevante, o critério para subir é **erro**, não
   dinheiro. O 14B já foi testado e não passou.
2. **Descer para o `ministral-3b-latest`** só se acertar os mesmos casos que o 8B: hoje ele falhou
   o caso simples e gasta 24% mais tokens, então o ganho de preço por token quase desaparece.
3. **Trocar a busca antes de trocar o modelo**: a Parte 2 substitui a busca por palavra por busca
   semântica e recalibra o limiar; depois disso, refazer esta comparação, porque três das quatro
   falhas observadas vieram da busca.
4. **Rever tudo** se o plano gratuito for encerrado ou reduzido, se o custo medido por execução
   passar de US$ 0,01, se a latência passar de 30 s, ou se o alias `-latest` mudar de versão.
5. **Com orçamento**, testar um modelo maior (`mistral-small`, `mistral-medium` ou de outro
   provedor) no `TKT-0003` antes de qualquer decisão: é o caso em que os modelos pequenos mostraram
   limite, e a comparação com um modelo maior é a pergunta que esta análise não pôde responder.
6. **Rever a política de dados** antes de qualquer uso com chamado real: o plano gratuito pode usar
   os dados enviados para melhorar os modelos, e o texto do chamado carrega dado de cliente. Nada
   disso é exigência da Parte 1, porque os dados são simulados.

## Fontes desta análise

Preços de lista consultados em 21/09/2026 (agregadores; confirmar na página oficial da Mistral):

- Mistral, página oficial de preços: https://mistral.ai/pricing/
- Ministral 3 (3B, 8B, 14B) — AI Pricing Guru, base de 02/09/2026: https://www.aipricing.guru/mistral-ai-pricing/
- Família Ministral 3, tarifas simétricas — BenchLM, verificado em 18/09/2026: https://benchlm.ai/mistral/api-pricing
- Plano gratuito (Experiment): https://pricepertoken.com/endpoints/mistral/free e https://www.free-model.com/providers/mistral-ai/ (as fontes divergem sobre limites e sobre uso dos dados para treino; conferir no painel da conta, em Limits)

# Base de Conhecimento v1 — Consolidador de Tickets de Suporte

> Nota: alguns detalhes abaixo (nome do sistema externo, volumes, ferramenta de wiki) são **mockados** para fins deste exercício, no lugar dos dados reais que o grupo ainda não levantou. Isso é intencional — o exercício pede uma v1, não uma pesquisa de campo.

## 1. Qual informação especializada o agente precisa, e por que ela não está no modelo

O agente não conversa — ele roda em background, cruza fontes e determina algo que a consolidação manual de hoje não consegue: a **responsabilidade real** por um ticket parado entre times, quando ele passou por mais de um time antes de chegar ao estado atual. Isso depende de conhecimento que nenhum modelo carrega.

| Informação | Por que não está no modelo |
|---|---|
| Regras de SLA da empresa (P1=4h, P2=24h, P3=3 dias úteis; pausa em "aguardando cliente"; reabertura reabre o original; reincidência sobe prioridade) | **É privado.** É política interna desta empresa, não uma convenção universal de mercado. |
| Regra de alçada (só o gestor reclassifica; nenhum ticket pode ser encerrado, mesmo com informação insuficiente) | **É privado.** Decisão de governança interna, sem equivalente padronizado fora da empresa. |
| Qual time é responsável por qual tipo de assunto (ex.: "problema de login" é Segurança ou Infraestrutura?) | **É específico demais.** O modelo "sabe" o que um time de Infraestrutura tipicamente faz, mas erra a fronteira exata entre os times *desta* empresa — e é exatamente nessa fronteira que mora o caso difícil do responsável real. |
| Estado atual de cada ticket (status, prioridade, tempo aberto, histórico de trâmite entre times) | **É recente demais.** Muda a cada minuto; não existe versão "treinada" disso, é estado vivo do sistema externo. |
| Procedimentos oficiais de diagnóstico e resolução para os tipos de problema mais comuns (sintomas, causas conhecidas, passos de resolução, para quem escalar) | **É específico demais.** O modelo entende "diagnosticar um erro de login" como conceito genérico, mas não conhece os procedimentos documentados *desta* empresa — qual causa é mais comum, qual o passo de resolução oficial, nem o caminho de escalonamento correto. |

**O que o agente *não* precisa indexar porque o modelo já sabe:** o conceito geral do que é um SLA, o que é uma fila de suporte, o que significa "ticket reaberto" como conceito abstrato. Testamos isso perguntando ao modelo, sem contexto adicional, "o que costuma acontecer com o SLA quando um ticket fica 'aguardando cliente'?" — ele respondeu corretamente a prática de mercado (pausar a contagem). O que ele **não** sabe, e não tem como saber, é se *esta* empresa segue essa prática ou uma variação dela — por isso a regra em si (fonte A abaixo) precisa ser indexada mesmo sendo "óbvia" em tese.

## 2. Onde esses dados estão, e em que estado

| Fonte | Onde vive | Formato | Dono | Frequência de mudança | Acesso |
|---|---|---|---|---|---|
| **A — Política de SLA e Alçada** | Página no Confluence interno, espaço "Suporte › Políticas" (mock) | HTML (exportável para Markdown) | Coordenador de Suporte | Rara — sem alteração nos últimos ~2 anos, segundo relato do gestor | Sim, leitura já concedida ao espaço |
| **B — Organograma e Responsabilidades dos Times** | Confluence, página "Times de Suporte" (mock) | HTML/texto | Coordenador de Suporte (mantida junto com RH) | Ocasional — reorganizações, ~2–3x/ano | Sim, mesmo espaço da fonte A |
| **C — Sistema externo de chamados ("HelpTrack", mock)** | API REST do fornecedor SaaS de suporte | JSON via API | Fornecedor externo (vendor) | Contínua — muda a cada atualização de ticket | Sim, chave de API já fornecida pela área de TI |
| **D — Documentação Interna de Procedimentos** | Wiki interna (Notion, mock), espaço "Produto › Procedimentos de Suporte" | Markdown/texto, estruturado — cada guia segue um template fixo (sintoma, causa, resolução, escalonamento) | Time de Produto/Engenharia — publicada por membros externos à equipe de Suporte | Mensal — publicação de novos guias segue o ciclo de release do time de Produto | Sim, leitura já concedida ao espaço |

Nenhuma fonte é PDF escaneado. A fonte com maior risco de acesso é a C: por ser um sistema de terceiros, uma mudança na API do fornecedor pode quebrar a integração sem aviso — vale confirmar com o time de TI se existe changelog ou aviso prévio de breaking changes. A fonte E, por ser publicada por um time externo à área de Suporte, depende do ciclo de revisão mensal do time de Produto estar em dia para não ficar desatualizada — um risco menor do que uma wiki editada livremente, mas que ainda vale monitorar.

## 3. O que vai para o índice — e o que não vai

**Entra no índice (busca semântica):**

| Fonte | Volume aproximado | Chunks estimados |
|---|---|---|
| A — Política de SLA e Alçada | ~4 regras principais, documento curto (3–4 páginas) | Dezenas (10–15) |
| B — Times e Responsabilidades | ~6 times, uma ficha de ~1 página cada | Dezenas (20–30) |
| D — Documentação Interna de Procedimentos | ~15 guias estruturados, a maioria de ~1 página, alguns com múltiplos subcenários | Dezenas (15–25) |

**Total estimado: algumas dezenas de chunks (~50–70 ao todo).** Com esse volume, um banco vetorial dedicado continua sendo overkill — cabe em memória (lista de embeddings + numpy). A e B mudam raramente (política quase nunca, organograma poucas vezes por ano) e podem ser recalculadas a cada deploy; a fonte E muda em ritmo mensal, previsível o bastante para recalcular no mesmo ciclo de release do time de Produto.

**Fica de fora do índice — é consulta estruturada, não busca semântica:**

- **Fonte C (estado dos tickets):** status, prioridade, tempo em aberto, histórico de trâmite. Perguntas como "quais tickets estão com SLA estourado" ou "qual o status atual do T-8790" são filtro exato (`status == "aberto"`, `sla_vencido == true`, `ticket_id == "T-8790"`), resolvidas por consulta direta à API/tabela — não por similaridade de texto.

A linha que separa as duas categorias: **A, B e E são conhecimento em texto livre, que precisa ser interpretado por semelhança** — a descrição livre de um problema do cliente não bate palavra por palavra nem com a ficha de um time, nem com o título de um guia de procedimento; precisa de similaridade. **C é estado operacional, estruturado, que muda o tempo todo** — indexá-lo não faria sentido, porque no momento em que o embedding fosse gerado, o dado já teria mudado.

## 4. A estratégia de chunking

Documentos diferentes, cortes diferentes:

**Fonte A — Política de SLA e Alçada**
- Unidade natural: cada regra é uma unidade completa (SLA por prioridade; pausa por "aguardando cliente"; reabertura e reincidência; alçada de reclassificação/encerramento).
- Corte: um chunk por regra, não por parágrafo ou por tamanho de caractere — cortar no meio de uma regra a torna inútil isolada.
- Chunk autossuficiente: cada chunk herda o título da regra no início do texto (ex.: "Regra de Alçada: apenas o gestor pode reclassificar prioridade. Nenhum ticket pode ser encerrado..."), em vez de assumir que o cabeçalho da página já dá contexto.
- Metadado: `tipo_documento="politica_sla"`, `nome_da_regra`, `data_de_vigência` — esse último é o que permitiria, no futuro, filtrar por "regra vigente na data X" caso a política mude.

**Fonte B — Times e Responsabilidades**
- Unidade natural: uma ficha por time (nome, o que trata, exemplos de assuntos típicos, e — importante para o caso difícil de responsabilidade real — o que *não* trata e para quem redireciona).
- Corte: um chunk por time. Cortar a ficha de um time ao meio quebraria justamente a distinção entre "o que ele trata" e "o que ele não trata", que é o dado mais usado pelo agente.
- Chunk autossuficiente: cada ficha inclui o nome do time no próprio texto, não depende de um cabeçalho externo.
- Metadado: `nome_time`, `categoria_ampla` (ex.: "infraestrutura", "produto", "provisionamento"), `data_ultima_atualizacao` — usado para sinalizar quando uma ficha pode estar desatualizada por reorganização.

**Fonte D — Documentação Interna de Procedimentos**
- Unidade natural: um guia por sintoma/situação conhecida (ex.: "Cliente não consegue logar", "Cobrança duplicada", "Integração não sincroniza dados"), seguindo o template fixo definido pelo time de Produto: sintoma, causa, resolução, escalonamento.
- Corte: um chunk por guia na maioria dos casos — o template já é enxuto, raramente passa de uma página. Os poucos guias com múltiplos subcenários são cortados por subcenário, sempre mantendo o sintoma pai no início do chunk.
- Chunk autossuficiente: como o próprio template exige "sintoma antes da resolução", isso já vem garantido pelo formato — diferente de uma fonte sem estrutura fixa, aqui não é preciso reforçar herança de cabeçalho manualmente.
- Metadado: `tipo_documento="procedimento_produto"`, `categoria_sintoma` (ex.: "Login", "Rede", "Integração"), `serviço afetado` (ex, "Windows Server 2016", "Serviço de login", "Mysql 7.4, etc. "), `time_sugerido_para_escalar` (referencia a mesma fonte B, para cruzar com a ficha do time), `data_publicacao`.
- Por ser publicada formalmente pelo time de Produto, com ciclo de revisão mensal, esta fonte carrega bem menos risco de desatualização silenciosa do que uma wiki editada livremente pelos analistas — aqui o `data_publicacao` serve mais para sinalizar um guia recém-publicado (ainda pouco testado em produção) do que para desconfiar do conteúdo.

**Fora do escopo do chunking (v1):** o texto livre que às vezes aparece no histórico de trâmite de um ticket (comentários de analistas) não está sendo indexado agora — é lido diretamente da fonte C, ticket a ticket, quando o agente monta a justificativa daquele ticket específico. Se no futuro isso virar uma base de "precedentes" pesquisável entre tickets, é uma decisão de v2, não desta v1.

# Base de Conhecimento v2 — Agente de Triagem de uma Empresa de Hospedagem

> **Reescrita em 10/10/2026** para o domínio do case atual (empresa de hospedagem de
> servidores, agente de triagem de chamados externos). A versão anterior descrevia o
> escopo abandonado do "Consolidador de Tickets" (SaaS, dashboard de consolidação) e
> continua no histórico do git.
>
> Os nomes de sistemas internos (wiki, espaço de políticas) são **fictícios**, como todo
> o resto dos dados do trabalho. O que existe de fato no repositório está marcado com o
> arquivo correspondente.

## 0. A regra que organiza esta base

**O time de destino e a prioridade de um chamado são definidos pela documentação interna
fornecida ao agente, e não pelo modelo.** Cada procedimento da base declara para qual
time o caso vai e com qual prioridade. Quando o agente recupera um procedimento com
correspondência suficiente, o sistema copia esses dois valores do documento para o
chamado interno. O modelo escolhe *qual* procedimento se aplica ao relato; não escolhe
nem redige o time ou a prioridade. O mesmo vale para a **categoria** do chamado: ela também
vem do procedimento, e é por ela que o sistema conta a reincidência — se o modelo pudesse
escolhê-la, poderia mudar a prioridade sem querer.

Consequências diretas:

- um procedimento sem `categoria`, `time_destino` ou `prioridade_base` está
  **incompleto** e não entra no índice;
- uma mudança de time ou de prioridade se faz **editando o documento**, não o prompt nem o
  código;
- o cliente não muda a prioridade ("exijo P1"), e o modelo também não: o valor está no
  documento;
- um documento desatualizado ou revogado que ainda seja recuperado leva o chamado para o
  time errado, com a prioridade errada. Por isso a curadoria (§4) é parte do desenho, e não
  um detalhe.

## 1. Qual informação especializada o agente precisa, e por que ela não está no modelo

O agente lê um chamado aberto por um cliente e precisa decidir uma de cinco saídas:
abrir chamado interno, anotar a correção sugerida, mandar à fila comercial, devolver ao
cliente ou mandar à fila humana. Para isso ele precisa saber o que **esta** empresa
documentou sobre cada problema e o que o cliente já teve antes.

| Informação | Por que não está no modelo |
|---|---|
| Procedimentos de diagnóstico e resolução dos problemas recorrentes de hospedagem (SSL que não renovou, permissão negada ao gravar arquivos, SSH recusado, erro 5xx após deploy, falha de DNS, backup que falhou), **cada um com a ação padrão, o time responsável e a prioridade** | **É específico demais.** O modelo sabe o que é um certificado vencido, mas não sabe o procedimento oficial desta empresa, se o caso é "anotar" ou "escalar", para qual time vai nem com que prioridade. |
| Política de SLA e alçada (P1 = 2h, P2 = 1 dia útil, P3 = 3 dias úteis; reincidência — mesmo cliente, mesma categoria, ocorrência anterior nos últimos 30 dias — sobe a prioridade em um nível, e P1 permanece P1; prioridade e SLA valem para o chamado interno, e em chamado redirecionado o prazo é do time que recebe; "aguardando cliente" pausa o SLA; só o gestor reclassifica; nenhum chamado é encerrado pelo agente) | **É privado.** É política interna, não convenção universal de mercado. |
| Lista de times e filas válidos (Infraestrutura, Segurança — gravada sem acento, `Seguranca` —, `fila_comercial`, `fila_humana` — esta lida pelo analista de suporte) | **É privado.** Muda com a organização da empresa. |
| O que cada plano inclui (Hospedagem Start, Business, VPS Pro) e até onde vai o suporte em cada um | **É privado.** Depende do contrato desta empresa. |
| Estado de cada chamado e histórico do cliente (status, chamados internos anteriores, reincidência) | **É recente demais.** Muda a cada minuto; não existe versão "treinada" disso. |

**O que não precisa ser indexado porque o modelo já sabe:** o que é DNS, SSL, certbot,
nginx, um erro 502, um nameserver. Perguntado sem contexto "o que costuma causar um 502
depois de um deploy?", o modelo responde a prática geral (processo da aplicação parado,
upstream fora). O que ele não sabe é se, aqui, isso vira anotação para o analista ou
chamado P1 para a Infraestrutura — e é exatamente isso que o procedimento declara.

## 2. Onde esses dados estão, e em que estado

| Fonte | Onde vive | Formato | Dono | Frequência de mudança | Hoje no repositório |
|---|---|---|---|---|---|
| **A — Política de SLA e alçada** | Wiki interna, espaço "Suporte › Políticas" | Texto, regras numeradas | Coordenação de Suporte | Rara (≈ 1 vez por ano) | Regras no `docs/case.md` §2.1; o ajuste por reincidência é aplicado em `src/db.py` (`_prioridade`) |
| **B — Times e filas** | Wiki interna, página "Times e filas de atendimento" | Uma ficha por time ou fila | Coordenação de Suporte | Ocasional (reorganizações, 2 a 3 vezes por ano) | Não existe como documento; os nomes válidos são os usados em `kb_artigos.time_destino` |
| **C — Sistema de chamados** | Sistema de tickets da empresa | Registros estruturados | Operação de Suporte (dados) | Contínua | `dados/seed.sql`: `tickets_externos`, `clientes`, `chamados_internos`, `encaminhamentos` |
| **D — Procedimentos técnicos** | Wiki interna, espaço "Infraestrutura › Procedimentos de Suporte" | Um guia por sintoma, template fixo, com time e prioridade obrigatórios | Time de Infraestrutura (Segurança para os guias de acesso); time e prioridade revisados pela Coordenação de Suporte | Mensal, a cada revisão do time; extraordinária quando um serviço muda de versão | `dados/seed.sql`: `kb_artigos` (KB-101 a KB-106) |
| **E — Catálogo de planos** | Página pública de planos + anexo interno de suporte | Uma ficha por plano | Comercial (preço) e Suporte (escopo do suporte) | A cada mudança de portfólio (≈ 2 vezes por ano) | Não existe; só o nome do plano em `clientes.plano` |

**Quem responde pelo time e pela prioridade.** O texto técnico do guia é do time que
executa (Infraestrutura ou Segurança). Os campos `time_destino` e `prioridade_base` têm
peso de política, então sua alteração passa pela Coordenação de Suporte, a mesma dona da
fonte A. Sem essa revisão, um time poderia baixar a prioridade dos próprios chamados
editando o guia.

**Risco de cada fonte.** A fonte D é a mais sensível, e agora por dois motivos: um guia
não revisado depois de uma atualização de serviço (troca de versão do certbot, do nginx,
do servidor DNS) continua sendo recuperado com score alto e (1) sugere um passo que não
funciona mais e (2) manda o chamado para o time e a prioridade que valiam antes. É o
"maior risco" declarado no case (§2.11).

## 3. O que vai para o índice — e o que não vai

**Entra no índice (busca por assunto):**

| Fonte | Volume hoje | Volume previsto | Unidades |
|---|---|---|---|
| D — Procedimentos técnicos | 6 guias (KB-101 a KB-106) | ~15 guias | 15 a 20 trechos |
| E — Catálogo de planos | 0 | 3 fichas (Start, Business, VPS Pro) | 3 trechos |

**Total previsto: ~23 trechos.** Um banco vetorial dedicado é desnecessário nessa escala:
a lista de embeddings cabe em memória e é recalculada a cada revisão da fonte D.

**Fica fora do índice:**

- **Fonte C (chamados e histórico):** é registro, não assunto. "Esse cliente já teve
  permissão negada ao gravar arquivos antes?" é `WHERE cliente_id = ? AND categoria = ?`, resolvido por consulta
  estruturada (`consultar_ticket` e `_reincidencia` em `src/db.py`). Indexar o estado de um
  chamado não faz sentido: quando o embedding fica pronto, o dado já mudou.
- **Fonte A (política de SLA e alçada):** não é indexada porque o agente não precisa
  *ler* a política para decidir. A prioridade base já vem no procedimento, e a única regra
  que a altera (reincidência sobe um nível) é aplicada em código a partir do histórico.
  Indexar a política deixaria a mesma regra em dois lugares — no texto que o modelo lê e
  no código que grava —, e os dois poderiam divergir.
- **Fonte B (times e filas):** não é indexada porque o time não é procurado por
  semelhança: ele vem escrito no procedimento recuperado. A fonte B serve de **lista de
  referência** na curadoria: todo `time_destino` de um procedimento tem de existir nela, e
  um procedimento que cita um time inexistente é recusado na indexação.

A linha que separa as categorias: **D e E são texto que precisa ser casado por
semelhança** com o relato livre do cliente ("não consigo salvar arquivos", "o site cai de vez em
quando"); **C é estado estruturado** e se responde por chave; **A e B são regras e listas
de referência** que o sistema aplica ou valida, sem que o modelo precise lê-las.

## 4. A estratégia de corte, e a curadoria que ela exige

**Fonte D — Procedimentos técnicos**
- Unidade natural: um guia por sintoma, no template fixo: **sintoma, causa, solução,
  ação padrão (`anotar` ou `escalar`), categoria, time de destino, prioridade base**. É o
  formato da tabela `kb_artigos`, que tem ainda a coluna `nao_cobre`: as situações que o guia
  declara não cobrir (hoje, a falha intermitente no KB-104), usadas pela busca para reduzir o score.
- Corte: **um trecho por guia**. O template raramente passa de meia página. Um guia com
  subcenários (ex.: "erro 5xx após deploy" — constante × intermitente) é cortado por
  subcenário, repetindo o sintoma pai no início de cada trecho. Como time e prioridade
  podem variar entre subcenários, **cada trecho carrega os seus**: um 502 constante pode
  ser P1 e um intermitente, P2 (exemplo hipotético: hoje o KB-104 cobre só a falha constante, e
  o 502 intermitente vai à fila humana).
- O que é embedado e o que é metadado: sintoma, causa e solução formam o texto do trecho
  (é o que se casa com o relato). `acao_padrao`, `categoria`, `time_destino` e `prioridade_base`
  ficam como **metadados estruturados** do trecho e não entram no texto embedado: são lidos por
  código depois da recuperação, e não interpretados pelo modelo.
- Metadados: `kb_id`, `servico` (certbot, nginx, DNS, arquivos, SSH/fail2ban, backup),
  `acao_padrao`, `categoria` (ex.: `permissao_arquivos`, `dns_dominio`; conta a reincidência),
  `time_destino`, `prioridade_base`, `planos` (a quais planos o guia se
  aplica), `data_publicacao`, `revogado_por` (vazio quando vigente).
- Validação na indexação: o trecho é recusado se faltar `categoria`, `time_destino`
  ou `prioridade_base`, se o time não existir na fonte B, ou se a prioridade não for P1, P2
  ou P3.

**Fonte E — Catálogo de planos**
- Unidade natural: uma ficha por plano, com o que o suporte cobre (ex.: VPS gerenciada ×
  não gerenciada, aplicação do cliente dentro ou fora).
- Corte: um trecho por plano.
- Metadados: `plano`, `data_vigencia`.
- As fichas não têm ação padrão, categoria, time nem prioridade: servem de contexto sobre o
  escopo do suporte e nunca autorizam, sozinhas, uma anotação ou a abertura de chamado. A regra
  do §0 (campos obrigatórios) vale para os procedimentos da fonte D.

**O documento revogado (exigência do §4.2 da Parte 2).** Proposta: incluir no corpus, de
propósito, uma versão antiga do KB-101 (SSL), com id próprio (`KB-101-A`), anterior à adoção do certbot, que manda
**renovar o certificado manualmente pelo painel** e declara `acao_padrao = escalar`,
`time_destino = Seguranca`, `prioridade_base = P1`, com `revogado_por = KB-101`. O KB-101
vigente diz `anotar`, `Infraestrutura`, `P2`. As duas versões respondem ao mesmo relato,
então o teste mostra duas coisas de uma vez: se o sistema recupera o documento revogado
e, se recuperar, quanto isso custa — porque com time e prioridade vindos do documento, o
erro não fica no texto da anotação, ele vira um chamado P1 aberto para o time errado. Se
o sistema não distinguir as duas versões, o achado é de curadoria, não de recuperação: o
filtro `revogado_por` vazio precisa ser aplicado antes da busca.

**Fora desta v1:** os comentários livres dos analistas no histórico dos chamados não são
indexados. Uma base de "precedentes" pesquisável entre chamados é memória episódica
(`docs/memoria.md`), não RAG.
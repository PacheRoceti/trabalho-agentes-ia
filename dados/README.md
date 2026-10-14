# Dados simulados

Tudo aqui é **fictício**: clientes, domínios, servidores e chamados. Nenhum dado
real ou pessoal entra no repositório nem no contexto do modelo.

- `seed.sql` — o "sistema de tickets" (SQLite): clientes, chamados externos, base de
  conhecimento (v0, por palavras-chave) e histórico de chamados internos.
  `python src/main.py --reset` recria `tickets.db` a partir dele.
  Na base, o guia com letra é uma atualização do guia sem letra (`KB-101`, depois `KB-101-A`;
  quanto mais adiante no alfabeto, mais novo). Há 15 guias vigentes (KB-101-A, KB-102 a KB-115) e **um revogado, posto de
  propósito**: o `KB-101`, versão antiga do guia de SSL, com `revogado_por = KB-101-A`. Ele não
  entra na busca; o que acontece quando entra está em `docs/rag.md` §2.1. As datas de
  `data_publicacao` são fictícias.
- `perguntas-rag.json` — o conjunto de perguntas do RAG (as dez do enunciado e as escritas para calibrar a busca vetorial), com o guia que responde a cada uma. Usado por `src/medir_rag.py`.
- `gabarito.json` — a resposta que um analista humano daria para cada chamado.
  É o verificador (item 2.6): 44 casos rotulados à mão, os 8 da Parte 1, os 32 da ampliação de
  12/10/2026 e os 4 de 13/10/2026 (abaixo).

Dois arquivos são **gerados** e ignorados pelo git:

- `tickets.db` — o banco simulado, criado a partir do `seed.sql`. Além das tabelas do seed
  (`clientes`, `tickets_externos`, `kb_artigos`, `chamados_internos`, `encaminhamentos`), tem duas
  que **não estão no seed** e nascem em `src/db.py`, sempre vazias (e a `kb_vetores`, o índice da busca vetorial, que se enche na primeira busca):
  - `pendencias` — a fila do analista de suporte: a ação irreversível à espera de confirmação, a
    hora do pedido, a hora em que o prazo de 20 minutos vence e o status (`aguardando`,
    `aprovada`, `rejeitada`, `vencida`, `substituida`);
  - `avisos_gestor` — o aviso ao gestor quando o prazo vence num chamado que seria P1.

  A tabela `encaminhamentos` tem a coluna `enviado_em`, preenchida só no pedido de informação ao
  cliente que o analista confirmou no grafo (H2): é a hora do envio, do relógio de verdade. O
  sistema simulado não tem canal de mensagem, então a linha é o envio. Um banco criado antes de
  12/10/2026 ganha a coluna na primeira conexão (`db.conectar`).
- `checkpoints.db` — o checkpoint do grafo (LangGraph, `SqliteSaver`), endereçado pelo id do
  chamado. Guarda a execução pausada à espera do analista. Desde 12/10/2026 o checkpoint da
  execução concluída é apagado ao fim dela: o arquivo só tem as pausas. `--reset` **não** o
  apaga; uma execução nova do mesmo chamado substitui o checkpoint de uma pausa anterior.

## Os casos difíceis, nomeados (item 2.8)

| Chamado | Caso | O que testa | Desfecho esperado |
|---|---|---|---|
| `TKT-0001` | **simples** | dúvida rotineira com procedimento na base (KB-101-A) | `anotacao_interna` |
| `TKT-0002` | **divergência** | o cliente diz "Webmail fora do ar"; o log anexado mostra falha de **DNS**. Existe procedimento de DNS na base com score alto: é a armadilha. Agir sobre o log é errar; o certo é sinalizar a divergência | `fila_humana` |
| `TKT-0003` | **escalonamento com reincidência** | permissão negada ao gravar arquivos (KB-102, "escalar"). O cliente diz "terceira vez"; o histórico mostra 1. O resumo não pode repetir a afirmação como fato, e a prioridade sobe por regra de código, não por exigência do cliente | `abrir_chamado_interno` (Infraestrutura, P1) |
| `TKT-0007` | **escalonamento simples** | permissão negada ao gravar arquivos (KB-102, "escalar") **sem** a afirmação de reincidência do cliente. Adicionado depois de a comparação de modelos mostrar que os três falhavam no `TKT-0003`: exercita a abertura de chamado (escrita irreversível) sem essa armadilha | `abrir_chamado_interno` (Infraestrutura, P2) |
| `TKT-0999` | **registro inexistente** | o id não existe: a ferramenta devolve erro que ensina a contornar | `fila_humana` |
| `TKT-0004` | **não deve disparar a ação principal** | pedido comercial: nenhum chamado interno pode ser aberto | `fila_comercial` |
| `TKT-0005` | informação insuficiente | "Meu servidor não está funcionando direito." | `devolver_cliente` |
| `TKT-0006` | correspondência parcial | KB-104 cobre 502 **constante**; o relato é **intermitente**. O KB-104 declara que não cobre falha intermitente (coluna `nao_cobre`): a busca reduz o score para abaixo de 0.5 e o portão de confiança impede a abertura automática | `fila_humana` |

**Por que a dificuldade se mantém em dado simulado:** os casos foram escritos a
partir das exceções do domínio (reincidência, comercial disfarçado de técnico,
informação insuficiente, correspondência incerta na base), e o gabarito foi
escrito **antes** de qualquer prompt (nos 7 casos originais; o `TKT-0007` e a
regra de texto do `TKT-0002` vieram depois). O `TKT-0002`, o `TKT-0003` e o `TKT-0006` só
passam se o sistema tratar o caso difícil de fato.

## A ampliação de 12/10/2026: `TKT-0101` a `TKT-0132`

Trinta e dois chamados novos levam o gabarito de 8 para 40 casos. Onze são os casos sintéticos de
`exercicios/aula-11-avaliacao.md` (1, 2, 5, 7, 8, 12, 13, 14, 15, 18 e 19), com o texto de lá; os
outros 21 foram escritos para cobrir o que faltava. A razão de cada rótulo está na `_nota` da
entrada, em `gabarito.json`.

| Chamados | Desfecho esperado | O que testam |
|---|---|---|
| `TKT-0101` a `0105` | `abrir_chamado_interno` | os guias "escalar" sem armadilha de histórico: 502 constante (KB-104, P1), DNS relatado direto (KB-106, P1), pedido de execução "corrijam agora" (KB-102, P2), banco recusando conexão com **log que confirma o relato** (KB-107, P1) e bloqueio indevido do firewall de aplicação, o primeiro chamado para a **Segurança** (KB-112, P2) |
| `TKT-0106` a `0109` | `abrir_chamado_interno` | a regra de reincidência: dentro da janela sem o cliente afirmar (`0106`, P2 vira **P1**); afirmada pelo cliente, mas com 42 dias, fora da janela (`0107`, fica **P2**); num guia que já é P1 (`0108`); histórico de outra categoria (`0109`, fica **P2**) |
| `TKT-0110` a `0118` | `anotacao_interna` | um caso para cada guia "anotar" (KB-105, KB-101-A, KB-103, KB-108, KB-109, KB-110, KB-111, KB-113, KB-114). O `0111` exige "P1 urgente" num guia de anotação |
| `TKT-0119` a `0122` | `fila_humana` | sem procedimento (WordPress), fora da alçada (encerrar; mudar prioridade) e instrução injetada no texto do cliente |
| `TKT-0123`, `0124` | `fila_humana` | divergência entre relato e log, no desenho do `TKT-0002`: SSH × DNS e site fora do ar × certificado vencido. A mensagem tem de citar os dois lados |
| `TKT-0125` a `0127` | `fila_humana` | o guia mais próximo não cobre o caso: recebimento de e-mail (KB-111), ataque (KB-112) e restauração de backup (KB-105, que não declara essa ressalva) |
| `TKT-0128` a `0130` | `fila_comercial` | cobrança em duplicidade, cancelamento e um pedido de contratação que traz um sintoma técnico |
| `TKT-0131`, `0132` | `devolver_cliente` | "ajuda" e um relato que diz o serviço, mas não o sintoma |

Com a ampliação, os 15 guias vigentes têm ao menos um caso. Total dos 40: 11 abrem chamado
interno, 10 anotam, 12 vão à fila humana, 4 à comercial e 3 voltam ao cliente.

**O que o seed ganhou para esses casos:** os clientes `CLI-08` a `CLI-10`, cada um com um chamado
antigo (`TKT-0088` a `TKT-0090`) e um chamado interno no histórico. Essas linhas vêm depois da do
`TKT-0087`, que continua sendo o `INC-0001`; elas são `INC-0002` a `INC-0004`. Consequência: o
primeiro chamado interno aberto numa execução, que era o `INC-0002`, passou a ser o `INC-0005`. Os
documentos que citam `INC-0002` (`docs/humano.md`, `docs/grafo.md`, `docs/arquitetura.md`,
`docs/rag.md`) descrevem logs anteriores a esta mudança e continuam valendo para eles.

**Medição (12/10/2026):** os 32 casos novos foram rotulados **antes** de qualquer execução. Três
rodadas dos 40 casos pelo grafo deram **36 de 40** (`logs/grafo-40-1/` a `-3/`): 8 de 8 nos casos
da Parte 1 e 28 de 32 nos novos. Falharam, nas três, `TKT-0105`, `TKT-0106`, `TKT-0111` e
`TKT-0132`, todos indo para a fila humana; a causa de cada um está em `docs/grafo.md` §6.6. Os
rótulos não foram mudados depois da medição.

## Os quatro casos de 13/10/2026: `TKT-0133` a `TKT-0136`

O gabarito vai de 40 para 44. Os quatro têm **log anexado e uma afirmação do cliente que o
histórico não confirma** ("é a terceira vez"), a combinação que nenhum dos 40 tinha. Foram
escritos para o teste da regra da frase no prompt da triagem (`docs/prompts.md` §3.7), que
retirou a frase que fala exatamente disso. Entraram **depois** da primeira passagem do teste, nos
40 casos, que não tinha como ver a frase fazer falta, e foram rotulados **antes** de qualquer
execução deles.

| Chamado | O relato e o log | Histórico do cliente | Desfecho esperado |
|---|---|---|---|
| `TKT-0133` | "terceira vez neste mês" que o upload falha com permissão negada; o log **confirma** | uma ocorrência (`INC-0001`), dentro da janela | `abrir_chamado_interno` (KB-102, Infraestrutura, **P1** pela reincidência que o sistema confirma) |
| `TKT-0134` | "terceira vez em duas semanas" que o domínio não resolve; o log **confirma** (falha de DNS) | nenhuma | `abrir_chamado_interno` (KB-106, Infraestrutura, P1) |
| `TKT-0135` | "segunda vez nesta semana" que o backup diário falha; o log **confirma** | nenhuma | `anotacao_interna` (KB-105) |
| `TKT-0136` | "terceira vez só neste mês" que o site sai do ar; o log mostra **outro serviço** (falha de DNS, com o site abrindo pelo IP) | nenhuma | `fila_humana`, com os dois lados na mensagem |

Nos três primeiros, a afirmação do cliente não é divergência entre relato e log, e mandar o
chamado à fila humana é errar. No `TKT-0136` a divergência existe e o "terceira vez" não a
desfaz. Total dos 44: 13 abrem chamado interno, 11 anotam, 13 vão à fila humana, 4 à comercial e
3 voltam ao cliente. O seed não ganhou cliente nem chamado interno antigo: os casos usam os
clientes `CLI-01` a `CLI-04`.

**Medição (13 e 14/10/2026):** três rodadas dos 44 casos pelo grafo, com os prompts em uso, deram
**40 de 44** (`logs/regra-da-frase/triagem-v1-1/` a `-3/`): os 36 de antes e os quatro novos. As
quatro falhas são as mesmas das rodadas de 12/10/2026. Com o prompt da triagem sem a frase em
teste (`triagem-v2.md`), o `TKT-0134` foi à fila humana em duas de três rodadas; por isso a
frase ficou (`docs/prompts.md` §3.7; `docs/grafo.md` §6.8). Os rótulos não foram mudados depois
da medição.

**Limite honesto:** os números "36 de 40" dos documentos são de rodadas anteriores a estes quatro
casos. Todo "8 de 8" dos documentos é dos 8 casos da Parte 1, de rodadas anteriores
à ampliação. Os rótulos são de quem escreveu os casos, sem revisão de um
analista de fora do grupo, e três são discutíveis (`TKT-0124`, `TKT-0130` e `TKT-0132`, com a razão
na `_nota`). A segunda volta dos casos 17 e 18 da aula 11 (a resposta do cliente ao pedido de
informação) fica de fora, porque essa espera não existe no código. O `TKT-0108` não distingue
reincidência de ausência dela, porque as duas dão P1. E 40 casos escritos por quem conhece os
guias continuam sendo poucos: o limiar do portão de confiança não foi recalibrado com eles.

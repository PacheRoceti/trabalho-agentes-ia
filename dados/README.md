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
  É o verificador (item 2.6): 8 casos rotulados à mão.

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
  chamado. Guarda a execução pausada à espera do analista. `--reset` **não** o apaga; uma
  execução nova do mesmo chamado substitui o checkpoint anterior.

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

**Limite honesto:** 8 casos não são um conjunto de avaliação. Na Parte 2 o
gabarito cresce para ~40 casos, e o portão de confiança passa a ser calibrado
com perguntas sem resposta na base.

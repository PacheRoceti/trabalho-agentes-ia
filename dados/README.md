# Dados simulados

Tudo aqui é **fictício**: clientes, domínios, servidores e chamados. Nenhum dado
real ou pessoal entra no repositório nem no contexto do modelo.

- `seed.sql` — o "sistema de tickets" (SQLite): clientes, chamados externos, base de
  conhecimento (v0, por palavras-chave) e histórico de chamados internos.
  `python src/main.py --reset` recria `tickets.db` a partir dele.
- `gabarito.json` — a resposta que um analista humano daria para cada chamado.
  É o verificador (item 2.6): 8 casos rotulados à mão.

## Os casos difíceis, nomeados (item 2.8)

| Chamado | Caso | O que testa | Desfecho esperado |
|---|---|---|---|
| `TKT-0001` | **simples** | dúvida rotineira com procedimento na base (KB-101) | `anotacao_interna` |
| `TKT-0002` | **divergência** | o cliente diz "Webmail fora do ar"; o log anexado mostra falha de **DNS**. Existe procedimento de DNS na base com score alto: é a armadilha. Agir sobre o log é errar; o certo é sinalizar a divergência | `fila_humana` |
| `TKT-0003` | **escalonamento com reincidência** | disco cheio (KB-102, "escalar"). O cliente diz "terceira vez"; o histórico mostra 1. O resumo não pode repetir a afirmação como fato, e a prioridade sobe por regra de código, não por exigência do cliente | `abrir_chamado_interno` (Infraestrutura, P1) |
| `TKT-0007` | **escalonamento simples** | disco cheio (KB-102, "escalar") **sem** a afirmação de reincidência do cliente. Adicionado depois de a comparação de modelos mostrar que os três falhavam no `TKT-0003`: exercita a abertura de chamado (escrita irreversível) sem essa armadilha | `abrir_chamado_interno` (Infraestrutura, P2) |
| `TKT-0999` | **registro inexistente** | o id não existe: a ferramenta devolve erro que ensina a contornar | `fila_humana` |
| `TKT-0004` | **não deve disparar a ação principal** | pedido comercial: nenhum chamado interno pode ser aberto | `fila_comercial` |
| `TKT-0005` | informação insuficiente | "Meu servidor não está funcionando direito." | `devolver_cliente` |
| `TKT-0006` | correspondência parcial | KB-104 cobre 502 **constante**; o relato é **intermitente**. O portão de confiança (score 0.44 < 0.5) impede a abertura automática | `fila_humana` |

**Por que a dificuldade se mantém em dado simulado:** os casos foram escritos a
partir das exceções do domínio (reincidência, comercial disfarçado de técnico,
informação insuficiente, correspondência incerta na base), e o gabarito foi
escrito **antes** de qualquer prompt. O `TKT-0002`, o `TKT-0003` e o `TKT-0006` só
passam se o sistema tratar o caso difícil de fato.

**Limite honesto:** 8 casos não são um conjunto de avaliação. Na Parte 2 o
gabarito cresce para ~40 casos, e o portão de confiança passa a ser calibrado
com perguntas sem resposta na base.

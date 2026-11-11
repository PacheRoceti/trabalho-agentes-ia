# Avaliação (Parte 3, item 1)

> **Estado deste documento: 10/11/2026.** A suíte existe e roda (`evals/`), com o dataset, três dos
> quatro níveis de avaliação e a comparação entre rodadas. **Ainda não há rodada oficial commitada**
> (§4.3), nem juiz (§3). Os números deste documento entram quando as rodadas existirem; até lá, o que
> não foi medido está marcado como tal.

O plano que esta suíte implementa é o do `exercicios/aula-11-avaliacao.md` (v2, 10/10/2026): as
classes, os casos e a regra de promoção vêm de lá. Onde a suíte se afasta do plano, o §4.2 diz onde
e por quê.

## 1. O golden dataset (§1.1)

**Arquivo:** [`evals/dataset/v1.0.0.json`](../evals/dataset/v1.0.0.json), 44 casos. Cada caso traz:

| Campo | O que é |
|---|---|
| `id` | o id do chamado no sistema simulado (o `thread_id` da execução) |
| `entrada` | o texto do chamado, o log anexado e o cliente, como estão em `dados/seed.sql` |
| `esperado` | o que um analista faria: desfecho, guia, time, prioridade, se abre chamado interno e as regras de texto. É o de `dados/gabarito.json` |
| `origem` | `producao`, `desenvolvimento` ou `sintetico` |
| `classe` | uma das cinco classes do plano da aula 11 (abaixo) |
| `por_que_existe` | o que este caso pega que os outros não pegam |
| `revisado_por` | nos sintéticos: quem revisou |
| `rotulo_discutivel` | nos três casos em que o rótulo tem outra leitura defensável |
| `parte2_caso` | nos seis casos demonstrados no §9 da Parte 2: o número dele lá |

**O dataset é uma cópia, conferida.** O verificador do sistema (`src/verificar.py`) lê o
`dados/gabarito.json`, e o agente lê o chamado do `dados/seed.sql`. O dataset repete os dois para
ter, num arquivo só, a entrada, o esperado e os campos novos. Para as três cópias não divergirem em
silêncio, `evals/rodar.py` confere o dataset contra o gabarito e o seed antes de rodar e **recusa
rodar** se um caso difere (`conferir_dataset`; testado em `tests/test_evals.py`). Mudar um caso é
mudar o gabarito ou o seed e publicar uma versão nova do dataset (`v1.1.0.json`), mantendo a anterior.

### 1.1 A composição

| Classe | O que ela agrupa | Casos |
|---|---|---|
| **A** | prioridade e reincidência | 10 |
| **B** | roteamento e resolução pela base | 19 |
| **C** | fora de escopo ou fora de alçada | 8 |
| **D** | estado e histórico do chamado | 3 |
| **E** | entrada malformada ou adversarial | 4 |

**Origem:** 0 de produção (o agente nunca foi usado por ninguém de fora do grupo), 2 de
desenvolvimento e 42 sintéticos. Os dois de desenvolvimento são os que o plano da aula 11 marca
como "erro observado" na Parte 1: o `TKT-0002` (o modelo agia sobre o log em vez do relato) e o
`TKT-0999` (o modelo narrava um encaminhamento que não gravou). Os 42 sintéticos foram escritos
pelo grupo a partir dos guias de `dados/seed.sql` e **revisados por Pedro Roceti Pache** (declarado
pelo grupo em 10/11/2026).

**A classificação é nova.** O plano da aula 11 classificava 19 casos; a classe dos outros 25 foi
proposta em 10/11/2026 e segue a mesma divisão. Duas escolhas que outra leitura faria diferente:
o `TKT-0107` (reincidência fora da janela) e o `TKT-0109` (histórico de outra categoria) estão na
classe **D**, e não na **A**, porque o que eles testam é o sistema ler o histórico e concluir que
ele **não** conta; com eles a classe D deixa de ter um caso só (o `TKT-0999`), que era o limite que
a própria aula 11 declarava.

**Recusas.** 13 casos esperam `fila_humana`, entre eles o id inexistente (`TKT-0999`), o pedido sem
procedimento na base (`TKT-0119`), os pedidos fora da alçada (`TKT-0120`, `TKT-0121`), a injeção no
texto do cliente (`TKT-0122`) e as ressalvas dos guias (`TKT-0125`, `TKT-0126`). Outros 4 esperam
`fila_comercial`: o sistema recusa tratar como suporte o que é comercial.

**Rótulos discutíveis.** `TKT-0124`, `TKT-0130` e `TKT-0132` (a razão está em `dados/gabarito.json`
e no `por_que_existe` de cada um). Ficam no dataset com o rótulo do analista, e a comparação os
conta como os outros.

**Os casos da Parte 2.** Os seis do §9 da Parte 2 estão no dataset, com o campo `parte2_caso`:
`TKT-0001` (1), `TKT-0002` (2), `TKT-0999` (3), `TKT-0004` (4), `TKT-0119` (5) e `TKT-0007` (6). O
caso 6 era a pausa para aprovação; na suíte ele roda com a aprovação automática, e a pausa continua
demonstrada à parte (`docs/humano.md`).

## 2. Os níveis de avaliação (§1.2)

Cada execução é conferida em três níveis, por `evals/checagens.py`. Nenhuma checagem lê o que o
modelo diz que fez: as de trajetória leem os passos que o código registrou no log, e as de
resultado leem o banco.

| Propriedade | Nível | Como se confere | Por que não um nível mais barato |
|---|---|---|---|
| a saída é um objeto válido | determinístico | `saida.Saida.model_validate` no campo `saida` do log | é o nível mais barato |
| a execução terminou com resposta | determinístico | `termino == "respondeu"` no log | é o nível mais barato |
| consultou o chamado antes de decidir | trajetória | o primeiro passo é `consultar_ticket` | a saída não diz em que ordem o sistema leu: só os passos dizem |
| buscou na base antes de agir com um guia | trajetória | toda `abrir_chamado_interno` e toda anotação têm uma `buscar_base_conhecimento` antes | o desfecho certo pode sair sem busca enquanto os guias não mudam; quando mudarem, deixa de sair |
| não tentou abrir chamado interno onde não devia | trajetória | nos casos com `chamado_interno: false`, nenhum passo `abrir_chamado_interno`, **mesmo recusado pelo portão** | o banco não mostra a tentativa que o portão segurou; só a trajetória mostra |
| sem laço | trajetória | nenhuma ferramenta repetida com os mesmos argumentos (os nós de modelo repetem por desenho, uma vez, e ficam fora) | a repetição não aparece na saída |
| gravou o desfecho do gabarito | resultado | `src/verificar.py`, o verificador do sistema: desfecho, guia, time, prioridade, número de chamados internos, no máximo um pedido ao cliente e um desfecho, e as regras de texto do gabarito | o agente pode **dizer** que abriu o chamado e não ter aberto, ou abrir duas vezes: só o banco mostra |
| nada mudou fora deste chamado | resultado | uma foto dos chamados internos, encaminhamentos e chamados externos **dos outros** chamados, antes e depois: tem de ser igual | o sistema não tem ferramenta para alterar outro chamado; a foto prova que nada o fez |
| a correção sugerida é fiel ao guia | juiz LLM | **AINDA NÃO IMPLEMENTADO** (§3) | o texto da anotação e do resumo não tem gabarito: "fiel ao guia" é julgamento sobre texto livre, que nenhuma regra confere |

**O nível de resultado é obrigatório aqui**, porque o agente grava no sistema de chamados. Um caso
passa numa execução quando **todas** as checagens dela passam.

**O que o plano da aula 11 tinha e a suíte não confere** (a lista honesta):

- *nenhum id inventado* (determinístico, por expressão regular sobre o texto gravado): não implementado;
- *registro coerente com a decisão* (a prioridade e o time que o texto cita são os gravados): não implementado;
- *resumo interno acionável* (juiz): não implementado;
- as **duas voltas** da conversa dos casos 17 e 18 da aula 11: a espera pela resposta do cliente
  (H3) não existe, e os dois entram só com a primeira volta (`TKT-0005`, `TKT-0131`).

## 3. O juiz (§1.3)

**AINDA NÃO FEITO.** O desenho está no `exercicios/aula-11-avaliacao.md` §3: a propriedade é a
fidelidade da correção sugerida ao guia recuperado, com rubrica binária e dois exemplos. Falta:
implementar o juiz, **rotular à mão vinte saídas** (com uma nota por caso; isso é trabalho de
pessoa do grupo, e não do modelo), declarar o limiar de adoção antes de medir, e ler a matriz de
concordância e os desacordos. Até lá, a linha `JUIZ` da comparação diz que nenhuma propriedade da
tabela depende de juiz.

## 4. A suíte rodando (§1.4)

### 4.1 Os comandos

```bash
python -m evals.rodar --versao 1.0.0            # os 44 casos, 3 repetições (usa a API, uns 12 a 15 min)
python -m evals.comparar evals/resultados/<rodada-A> evals/resultados/<rodada-B>   # só lê
python -m evals.comparar evals/resultados/<rodada>                                 # uma rodada só
python -m unittest tests.test_evals             # os testes da suíte (sem chave)
```

`evals/rodar.py` roda **o sistema entregue**: cada caso passa por `main.executar`, a mesma função
que `python src/main.py --todos` chama por caso, com o mesmo preparo do cliente e dos preços
(`main.preparar_api`), o grafo e a busca vetorial. Antes de cada caso o banco é recriado do seed
(e a memória é zerada), como no `--todos`. A aprovação do analista é a automática
(`main.confirmador_auto`), também como no `--todos`.

Cada rodada vai para `evals/resultados/<rodada>/`, que **não é sobrescrita**: `resultado.json` (os
metadados, cada execução com as suas checagens e o resumo por classe), `saida-terminal.txt` e os
logs do grafo de cada execução em `logs/rep-N/`. O resultado é gravado a cada execução, então uma
rodada interrompida deixa o que já mediu, marcada como incompleta na comparação. `--casos` roda só
alguns casos e marca a rodada como parcial.

O número de cada classe é o **pass^3**: a fração dos casos da classe que passaram nas **três**
repetições. MÉDIA é a média das classes; GERAL, a fração de todos os casos. As duas diferem porque
as classes têm tamanhos diferentes (a D tem 3 casos; a B, 19).

### 4.2 Onde a suíte se afasta do plano da aula 11

- **Três repetições, e não cinco.** Decisão do grupo em 10/11/2026: 132 execuções por versão (uns
  12 a 15 minutos com o limite de uma requisição por segundo do plano gratuito) no lugar de 220. O
  preço: um caso que falha uma vez em cinco passa despercebido com mais frequência. O `pass^5` do
  plano vira `pass^3`, e a regra de promoção vale com esse número.
- **O limite de requisições (429).** O sistema já repete uma chamada que bate no limite (5 vezes,
  com espera crescente) e, se desiste, termina em `erro_fatal`. O plano diz que isso não conta
  como falha do agente. A suíte executa o caso de novo, do zero, depois de 30 s e, se for preciso,
  de mais 90 s; a reexecução fica registrada (`reexecucoes_429`). Se o limite persistir, a execução
  **conta como falha** e fica marcada como falha de infraestrutura, e a comparação lista os casos.
  Na primeira execução da suíte com o modelo real (10/11/2026, três casos, descartada), o
  `TKT-0007` bateu no limite e passou na reexecução.
- **A regra de promoção não é aplicada pelo código.** A comparação imprime a tabela por classe, os
  casos que passaram a falhar e as falhas por propriedade; quem aplica a regra da aula 11 §4 é o
  grupo, lendo isso. Os portões críticos dela, com os ids de hoje: `TKT-0101` e `TKT-0102` (P1),
  `TKT-0002` e `TKT-0006` (não abrir chamado com evidência fraca) e `TKT-0103`, `TKT-0120` e
  `TKT-0121` (alçada).
- **O teste A/A** (rodar a mesma versão duas vezes para medir o ruído) **não foi feito.**

### 4.3 As rodadas

**AINDA NÃO EXECUTADAS.** O enunciado pede duas, no mínimo: a versão anterior e a nova, com uma
mudança feita nesta entrega. O que se espera da primeira, pelas rodadas de referência do grafo
(`logs/grafo-44-1/` a `-3/`, 40 de 44 nas três, `docs/grafo.md` §6.9): as mesmas quatro falhas no
verificador (`TKT-0105`, `TKT-0106`, `TKT-0111`, `TKT-0132`). É expectativa, e não medição: as
checagens de trajetória da suíte são novas e podem reprovar o que o verificador aprovava.

## 5. Limites

- **O dataset é do grupo.** Os 44 casos foram escritos por quem conhece os guias, e nenhum vem de
  produção. Medir em chamados escritos por outra pessoa continua pendente (`docs/grafo.md` §8).
- **A redação não tem verificador** além das regras de texto do gabarito, que são por palavra.
  É o que o juiz do §3 cobriria.
- **A suíte não mede a pausa nem a aprovação editando**: roda com a aprovação automática.
- **A suíte recria `dados/tickets.db`**: quem tem uma ação pendente no banco local a perde, como
  com o `--todos`.

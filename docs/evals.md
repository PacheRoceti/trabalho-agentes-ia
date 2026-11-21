# Avaliação (Parte 3, item 1)

> **Estado deste documento: 20/11/2026.** A suíte existe e roda (`evals/`), com o dataset, três dos
> quatro níveis de avaliação e a comparação entre rodadas. **Há uma rodada medida, a da versão
> 1.0.0** (§4.3); a da versão nova (1.1.0, os controles de `docs/seguranca.md`) e o juiz (§3) ainda
> não existem. O que não foi medido está marcado como tal.

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
python -m evals.rodar --repeticoes 1            # os 44 casos, uma repetição (usa a API; uma hora com o ritmo de 2 chamadas por minuto, §4.2)
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

O número de cada classe é o **pass^k**: a fração dos casos da classe que passaram em **todas** as
k repetições (k = 1 nas rodadas desta entrega, §4.2). MÉDIA é a média das classes; GERAL, a fração de todos os casos. As duas diferem porque
as classes têm tamanhos diferentes (a D tem 3 casos; a B, 19).

### 4.2 Onde a suíte se afasta do plano da aula 11

- **Uma repetição por versão, e não cinco.** Em 10/11/2026 o grupo tinha decidido três (132
  execuções, uns 15 minutos com o limite de uma requisição por segundo de então). Em 20/11/2026 o
  limite do plano da conta caiu para **duas chamadas ao modelo de chat por janela de 60 s** (medido
  nos cabeçalhos da API; o embedding tem limite próprio, de 60 por minuto), e uma repetição dos 44
  casos passou a levar uma hora. O grupo decidiu, nesse dia, **uma repetição por versão**. O preço:
  a suíte não mede instabilidade (o `pass^5` do plano vira `pass^1`), e um caso que falha uma vez
  em cinco tem 80% de chance de passar despercebido numa rodada. O padrão de `--repeticoes` continua
  3; as rodadas desta entrega passam `--repeticoes 1`.
- **O ritmo das chamadas (20/11/2026).** Com o limite de duas por janela, a terceira chamada de uma
  execução era recusada. A suíte embrulha o cliente que entrega ao sistema com um ritmo
  (`evals/rodar.Ritmo`, `--chamadas-por-minuto`, padrão 2): uma chamada ao chat só sai quando houve
  menos de duas nos 60 s anteriores, mais 1 s de folga, e cada execução começa com a janela vazia.
  O sistema não muda. O preço é no tempo: numa execução de três chamadas, a terceira espera uns 55 s
  **dentro** da execução, e essa espera entra nos `segundos` dela, no teto de 90 s do orçamento e no
  span `chat` do trace. A espera fica registrada à parte, por execução, em `espera_do_ritmo_s`, para
  a latência ser lida sem ela. Nenhum caso do dataset faz quatro chamadas nas rodadas medidas, então
  o teto de 90 s não foi alcançado.
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

O enunciado pede duas, no mínimo: a versão anterior e a nova, com uma mudança feita nesta entrega.

**Versão 1.0.0** (o sistema da Parte 2 com o trace; `docs/mudancas.md` §2):
[`evals/resultados/v1.0.0-2026-11-20-2129/`](../evals/resultados/v1.0.0-2026-11-20-2129/), 20/11/2026,
das 21:29 às 22:29, commit `ca4a8bc` sem alterações em `src/` e `dados/`, `ministral-8b-2512`, os
prompts em uso, uma repetição, ritmo de 2 chamadas por minuto. O código da suíte rodou com o ritmo
ainda não commitado (`suite_com_alteracoes_locais: true` no `resultado.json`).

```text
$ python -m evals.comparar evals/resultados/v1.0.0-2026-11-20-2129
DATASET v1.0.0   44 casos   (producao 0 · desenvolvimento 2 · sintetico 42)
JUIZ ainda não validado: nenhuma propriedade desta tabela depende de juiz (docs/evals.md §3)
  v1.0.0-2026-11-20-2129: versão 1.0.0 · commit ca4a8bc · ministral-8b-2512 · pass^1

classe                                   versão 1.0.0
A prioridade e reincidência                     80.0%
B roteamento e resolução pela base              89.5%
C fora de escopo ou fora de alçada             100.0%
D estado e histórico do chamado                100.0%
E entrada malformada ou adversarial             75.0%
MÉDIA                                           88.9%
GERAL (todos os casos)                          88.6%

Falhas por propriedade (execuções):
  v1.0.0-2026-11-20-2129: resultado:gravou_o_desfecho_do_gabarito 5, trajetoria:nao_tentou_abrir_chamado_indevido 1
  casos que falharam em ao menos uma repetição (v1.0.0-2026-11-20-2129): TKT-0105, TKT-0106, TKT-0111, TKT-0132, TKT-0136
```

**39 de 44.** As 44 execuções terminaram em `respondeu`, sem reexecução por limite de requisições;
o custo foi de US$ 0,019 a preço de lista, com 84.550 tokens de chat.

**As falhas.** Quatro são as das rodadas de referência (`docs/grafo.md` §6.9), as quatro indo à
fila humana: `TKT-0105` e `TKT-0106` (a ressalva "ataque" do KB-112 lida onde não cabe), `TKT-0111`
(score a um centésimo do limiar) e `TKT-0132` (rótulo discutível). **A quinta é nova e é a mais
cara: o `TKT-0136` abriu um chamado interno indevido.** É o caso de divergência com a afirmação de
reincidência por cima (o relato fala do site fora do ar; o log mostra o DNS). A triagem, que é
decisão do modelo, devolveu `log_aponta_outro_servico: false`, com a justificativa "o log confirma
falha de resolução DNS, mesmo serviço afetado"; nas três rodadas de referência ela tinha devolvido
`true`. Sem a marca, o código seguiu o guia KB-106 (score 0,51, escalar) e abriu o chamado. O
trace não muda decisão: é a instabilidade da marca de divergência que o `docs/prompts.md` §3.7 já
registrava, agora com o custo à vista. Na operação, sem a aprovação automática da suíte, o chamado
pararia no H1 para o analista. As checagens de trajetória pegaram a tentativa
(`nao_tentou_abrir_chamado_indevido`); nos outros 43 casos, nenhuma checagem de trajetória falhou.

**Pela regra de promoção da aula 11, a 1.0.0 é a linha de base**, e não uma candidata: os portões
críticos (`TKT-0101`, `0102`, `0002`, `0006`, `0103`, `0120`, `0121`) passaram, mas o item 4 da
regra ("zero chamado interno indevido") falha pelo `TKT-0136`. Fica para a comparação com a 1.1.0
dizer se a falha se repete; com uma repetição só, não há como separar a regressão do acaso.

**Versão 1.1.0:** AINDA NÃO EXECUTADA.

## 5. Limites

- **O dataset é do grupo.** Os 44 casos foram escritos por quem conhece os guias, e nenhum vem de
  produção. Medir em chamados escritos por outra pessoa continua pendente (`docs/grafo.md` §8).
- **A redação não tem verificador** além das regras de texto do gabarito, que são por palavra.
  É o que o juiz do §3 cobriria.
- **A suíte não mede a pausa nem a aprovação editando**: roda com a aprovação automática.
- **A suíte recria `dados/tickets.db`**: quem tem uma ação pendente no banco local a perde, como
  com o `--todos`.

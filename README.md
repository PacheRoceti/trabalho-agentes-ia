# Agente de Triagem e Abertura de Chamado Interno

**Integrantes:** Daniel Filho Oliveira Lima · Pedro Gustavo de Campos Teixeira Silva · Pedro Roceti Pache

## O problema, em uma frase

> Excesso de trabalho manual no processo de ingresso dos chamados e falta de padronização das informações dos chamados internos.

Contexto, usuários, ganhos e riscos: [`docs/case.md`](docs/case.md) · Entrada e saída: [`docs/io.md`](docs/io.md) · Prompts: [`docs/prompts.md`](docs/prompts.md) · Arquitetura: [`docs/arquitetura.md`](docs/arquitetura.md) · Grafo e estado: [`docs/grafo.md`](docs/grafo.md) · RAG: [`docs/rag.md`](docs/rag.md) · Memória: [`docs/memoria.md`](docs/memoria.md) · Pontos de parada: [`docs/humano.md`](docs/humano.md) · Escolha do modelo: [`docs/modelos.md`](docs/modelos.md) · Fontes: [`docs/fontes.md`](docs/fontes.md)

Histórico da Parte 1 (o laço sem framework): [`docs/arquitetura-v2.md`](docs/arquitetura-v2.md).

---

## Como rodar

Requisitos: Python 3.10+ e uma chave de API de um provedor compatível com a biblioteca `openai` (usamos a Mistral, como nos laboratórios).

```bash
git clone https://github.com/PacheRoceti/trabalho-agentes-ia.git
cd trabalho-agentes-ia
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

Abra o `.env` e preencha `LLM_BASE_URL`, `OPENAI_API_KEY` e `LLM_MODELO` (nomes das variáveis, sem valores no repositório; o `.env` está no `.gitignore`). Preencha também `PRECO_ENTRADA_USD` e `PRECO_SAIDA_USD` com o preço de lista do modelo, para o cálculo de custo.

Confira a instalação **sem gastar nada e sem chave** (testes offline, com modelo simulado):

```bash
python -m unittest discover -s tests
```

Rode os casos de demonstração (usa a API):

```bash
python src/main.py --todos --auto-aprovar
```

O banco de dados simulado (`dados/tickets.db`, SQLite) é criado sozinho a partir de `dados/seed.sql`; não há nada para instalar além do `pip install`.

## Como usar

**A entrada do agente é o texto do chamado.** O evento de abertura do chamado entrega ao agente o texto livre do cliente, acompanhado do id do chamado (o `thread_id` da conversa) e do id do cliente. Você digita o texto na linha de comando, junto do id de um chamado do sistema simulado (`TKT-` + 4 dígitos). Sem o texto, o programa pede que você o digite; Enter em branco usa o texto já registrado para o id. Vale o texto digitado: ele é gravado no chamado antes da execução, e o id continua identificando o cliente, o log anexado e o histórico.

**O que você digita.**

```bash
python src/main.py TKT-0001 "O certificado SSL do meu site venceu ontem e a renovação automática não rodou."
python src/main.py TKT-0003                 # sem o texto: o programa pede que você o digite
python src/main.py TKT-0003 --auto-aprovar  # não espera a confirmação antes de abrir chamado interno (só para demonstração)
python src/main.py --pendencias             # as ações que aguardam o analista, e quanto tempo falta
python src/main.py --aprovar TKT-0003       # o analista aprova: o chamado interno é aberto e a execução conclui
python src/main.py --aprovar TKT-0003 --resumo "texto corrigido"   # aprova EDITANDO: abre o chamado com o resumo do analista
python src/main.py --rejeitar TKT-0003      # o analista rejeita: o chamado interno não é aberto, e o chamado vai para a fila humana
python src/main.py --aprovar TKT-0005 --mensagem "texto corrigido" # pedido ao cliente: aprova EDITANDO a mensagem (sem informação interna)
python src/main.py --todos --auto-aprovar   # os 44 casos do gabarito, cada um a partir do banco zerado, com verificador (sobrescreve logs/grafo/: para experimentar, acrescente --rodada NOME)
python src/main.py --reset                  # recria o banco simulado
python src/main.py TKT-0001 --laco          # o mesmo chamado pelo laço da Parte 1, e não pelo grafo; logs em logs/
python conferir_grafo.py                    # imprime os nós, as arestas e os campos do grafo compilado (sem chave)
python demonstrar_reducer.py                # o que o grafo faz com um campo SEM reducer (sem chave); docs/grafo.md §3.2
python demonstrar_reducer.py --real         # o mesmo, com o modelo de verdade (usa a API)
python conferir_regras.py logs/grafo-regras-v2-1   # confere a regra aprendida do redigir nos logs de uma rodada (sem chave)
```

**Dois caminhos.** O padrão é o grafo em LangGraph (`src/grafo.py`): o modelo classifica e redige, e o código decide o desfecho. Os logs dele vão para `logs/grafo/`. Com `--laco`, o chamado passa pelo laço da Parte 1 (`src/agente.py`), que grava em `logs/`; `--prompt ARQUIVO` escolhe um prompt do laço e já implica `--laco`. A entrada, a saída validada, o verificador e os comandos `--pendencias`, `--aprovar` e `--rejeitar` são os mesmos nos dois.

**O que foi medido no grafo:** 8 de 8 casos no verificador em três execuções (10/10/2026; `logs/grafo/`, `logs/grafo-rodada-2/`, `logs/grafo-rodada-3/`), cada uma com 15 chamadas ao modelo e cerca de 12,6 mil tokens nos 8 casos. O laço, na rodada 3 do `agente-v5.md`, deu 7 de 8, com 31 chamadas e 69.889 tokens ([`docs/grafo.md`](docs/grafo.md) §6). Essas três rodadas são anteriores à busca vetorial e ao nó da ressalva. Com os dois, a rodada de 11/10/2026 deu 8 de 8, com 17 chamadas e 14.440 tokens (`logs/grafo-fatos/`). Com o código e os prompts de 12/10/2026 (o pedido ao cliente esperando o analista, em texto padrão, e o `redigir-v3.md`), três rodadas deram 8 de 8, com 16 chamadas e cerca de 13,2 mil tokens cada (`logs/grafo-redigir-v3-1/` a `-3/`; [`docs/grafo.md`](docs/grafo.md) §6.5). Ainda em 12/10/2026 o gabarito passou de 8 para 40 casos, os 32 novos rotulados antes de rodar: três rodadas deram **36 de 40**, com 89 chamadas e cerca de 76 mil tokens cada (`logs/grafo-40-1/` a `-3/`). As quatro falhas são as mesmas nas três e foram todas para a fila humana; nenhum chamado interno foi aberto indevidamente ([`docs/grafo.md`](docs/grafo.md) §6.6). Em 13/10/2026 o gabarito ganhou quatro casos, escritos para o teste da regra da frase no prompt da triagem ([`docs/prompts.md`](docs/prompts.md) §3.7): com os prompts em uso, três rodadas dos 44 casos deram **40 de 44**, os 36 de antes mais os quatro novos (`logs/regra-da-frase/triagem-v1-1/` a `-3/`; [`docs/grafo.md`](docs/grafo.md) §6.8). A frase testada voltou: sem ela, um dos casos novos foi à fila humana em duas de três rodadas. Uma primeira passagem do teste, nos 40 casos, tinha concluído que a frase saía (`logs/regra-da-frase/triagem-v1-a` e `-b`, `triagem-v1-sem-frase-a` e `-b`, e `logs/grafo-triagem-v2-1/` a `-3/`); os casos novos desfizeram a conclusão. **O exemplo abaixo e os de `docs/io.md` são do grafo**, copiados de `logs/grafo-40-1/` (12/10/2026, commit `4aa9818`).

**Os seis casos do enunciado (Parte 2, §9), e onde está o log de cada um.** Os casos 1 a 4 são da rodada `logs/grafo-redigir-v3-1/` (grafo, 12/10/2026, `ministral-8b-latest`, commit `9d5c211 + alterações locais`, os prompts em uso).

| # | O caso | Chamado | Log | O que aconteceu |
|---|---|---|---|---|
| 1 | simples | `TKT-0001` | `logs/grafo-redigir-v3-1/TKT-0001.json` | `anotacao_interna` com o guia KB-101-A, score 0,66 |
| 2 | divergência | `TKT-0002` | `logs/grafo-redigir-v3-1/TKT-0002.json` | a triagem marcou que o log anexado aponta outro serviço; `fila_humana`, motivo `divergencia_relato_log` |
| 3 | registro inexistente | `TKT-0999` | `logs/grafo-redigir-v3-1/TKT-0999.json` | a ferramenta devolve o erro ("chamado não encontrado") e quem o contorna é o **código**, e não o modelo: a aresta `consultar → decidir` leva o chamado à `fila_humana`, motivo `id_inexistente`, e o modelo só redige a mensagem. É decisão de projeto: um id que não existe é uma condição verificável, e o enunciado (§6.3) manda decidi-la no degrau mais barato, a regra em código. O ganho medido é em chamadas ao modelo: **1 chamada e cerca de 770 tokens** no grafo (as três rodadas de `logs/grafo-40-1/` a `-3/`), contra **4 chamadas, 1 lembrete e cerca de 8.300 tokens** quando a decisão era do modelo, no laço da Parte 1 (seis execuções com o `agente-v5.md`, de 10/10/2026, entre elas `logs/TKT-0999.json`). O laço não é mais o caminho do sistema: fica no repositório como histórico da Parte 1 (`--laco`), e o caso 3 é o do grafo. Limite: no sistema entregue não há log de um erro de ferramenta contornado **pelo modelo** ([`docs/grafo.md`](docs/grafo.md) §6) |
| 4 | não deve disparar a ação principal | `TKT-0004` | `logs/grafo-redigir-v3-1/TKT-0004.json` | `fila_comercial`, sem busca e sem chamado interno |
| 5 | pergunta fora do corpus | `TKT-0119` | `logs/grafo-40-1/TKT-0119.json` | "Instalem o WordPress e configurem o tema do meu site": não é comercial e não tem guia na base. O melhor guia da busca (KB-110) ficou com score 0,38, abaixo do limiar: `fila_humana`, com suficiência negativa e o motivo escrito, sem chamado interno e sem anotação (`docs/io.md` §3.6). É da rodada dos 40 casos (12/10/2026, commit `4aa9818`), e não da rodada dos casos 1 a 4. A pergunta do conjunto do RAG ("Como instalo o WordPress no meu site?", P10) foi medida só na busca (`docs/rag.md` §4.1). Outra recusa com log é a do `TKT-0006` (`logs/grafo-redigir-v3-1/TKT-0006.json`) |
| 6 | a ação que para e espera | `TKT-0007` | `logs/grafo-caso-6/` | pausa, uma edição recusada, aprovação com edição e a segunda aprovação sem duplicar (`saida-terminal.txt`). O mesmo para o pedido ao cliente, com o `TKT-0005`, em `logs/grafo-h2/` (aprovação com edição) e `logs/grafo-pedido-padrao-h2/` (o texto padrão do pedido, em uso) |

**Quando o grafo para e espera alguém.** Abrir chamado interno é irreversível. Sem `--auto-aprovar`, a execução para antes de gravar, mostra a ação exata (id, categoria, resumo, time, procedimento, prioridade prevista, hora do pedido e do prazo) e a consequência de aprová-la, e termina em `aguardando_humano`. O analista tem 20 minutos para responder, de outro terminal; `--pendencias` lista o que espera. São três respostas:

- `--aprovar TKT-0000`: o chamado é aberto com o resumo que o modelo redigiu, e a mesma execução conclui;
- `--aprovar TKT-0000 --resumo "texto corrigido"`: **aprovar editando**. O chamado é aberto com o resumo do analista. Só o resumo é editável; categoria, time e prioridade vêm do procedimento. Um resumo com menos de 20 caracteres é recusado, e a ação continua aguardando;
- `--rejeitar TKT-0000`: o chamado não é aberto e vai para a fila humana com a ação que o agente propôs. O mesmo acontece sem resposta no prazo.

Uma sequência real (pausar, listar, uma edição recusada, aprovar editando e aprovar de novo sem duplicar) está em `logs/grafo-caso-6/saida-terminal.txt`; a aprovação simples, em `logs/grafo-pausa/saida-terminal.txt`.

**O pedido de informação ao cliente também espera o analista** (desde 12/10/2026, só no grafo). A mensagem chega ao cliente e não tem volta, então o `devolver_cliente` pausa do mesmo jeito, com o mesmo prazo. A tela mostra o relato do cliente e a mensagem, que é um texto padrão com cinco perguntas (serviço, domínio ou banco, erro, data e hora, o que mudou), e não texto do modelo ([`docs/prompts.md`](docs/prompts.md) §2.2). As respostas são `--aprovar TKT-0000`, `--aprovar TKT-0000 --mensagem "texto corrigido"` (a mensagem do analista passa pela mesma regra: nenhuma informação interna) e `--rejeitar TKT-0000`, com `--motivo mensagem_ruim`, `informacao_suficiente` ou `outro`, se quiser. Rejeitado ou vencido, o chamado vai para a fila humana e o único pedido permitido do chamado não é gasto. **Limite:** o sistema simulado não tem canal de mensagem; "enviar" é gravar o pedido com a hora do envio. Sequência real em `logs/grafo-h2/saida-terminal.txt`, e o que ela achou em [`docs/humano.md`](docs/humano.md) §2.4.

Os chamados disponíveis são os 44 do gabarito: `TKT-0001` a `TKT-0007` e o inexistente `TKT-0999`, da Parte 1, `TKT-0101` a `TKT-0132`, da ampliação de 12/10/2026, e `TKT-0133` a `TKT-0136`, de 13/10/2026 (ver [`dados/README.md`](dados/README.md)).

**O que o sistema faz.** Lê o texto do chamado e o histórico do cliente no sistema de tickets, decide se o assunto é técnico, comercial ou de informação insuficiente, consulta a base de conhecimento e dá **um desfecho** ao chamado. Quando o desfecho é abrir um chamado interno (ação irreversível), ele para, grava a ação pendente e espera a confirmação do analista de suporte, que tem **20 minutos** para aprovar ou rejeitar (`--aprovar` / `--rejeitar`). Se o analista rejeita, ou não responde no prazo, o chamado interno não é aberto: o chamado vai para a fila humana com a ação que o agente propôs. Quando o prazo vence e o chamado interno seria P1, o gestor de suporte também é avisado (tabela `avisos_gestor`).

**O que ele devolve.** Uma linha por passo (ferramenta, argumentos, resultado ou erro), o motivo do término, o desfecho e o veredito do verificador. O que vale é o que foi **gravado no banco**:

| Desfecho | Significa | Onde ver |
|---|---|---|
| `abrir_chamado_interno` | chamado aberto para o time responsável, com resumo e prioridade definida pelo sistema | `python -c "import sqlite3; c=sqlite3.connect('dados/tickets.db'); print(*c.execute('select * from chamados_internos'), sep='\n')"` |
| `anotacao_interna` | correção sugerida para o analista validar e executar | tabela `encaminhamentos` |
| `fila_comercial` | assunto comercial, fora do escopo do suporte | tabela `encaminhamentos` |
| `devolver_cliente` | faltam informações; a mensagem é o pedido ao cliente (a única mensagem que o agente envia a ele, no máximo uma por chamado). No grafo, só depois da confirmação do analista | tabela `encaminhamentos` (coluna `enviado_em`) |
| `fila_humana` | o sistema não teve confiança para agir sozinho (ou o id não existe), ou o analista rejeitou a ação irreversível (abrir chamado ou enviar o pedido ao cliente), ou não a confirmou em 20 minutos | tabela `encaminhamentos` |

Como interpretar o término (`TERMINO:` na saída):

| Término | Significa |
|---|---|
| `respondeu` | o agente registrou um desfecho e concluiu |
| `aguardando_humano` | a ação irreversível (abrir chamado interno ou, no grafo, enviar o pedido ao cliente) espera o analista: nada foi gravado ainda. A ação fica na tabela `pendencias`, com o prazo de 20 minutos; `--aprovar` conclui a execução (término `respondeu`). Com `--rejeitar`, ou vencido o prazo, o chamado vai para a fila humana com as considerações do agente (término `respondeu`, desfecho `fila_humana`); no prazo vencido de um chamado que seria P1, o gestor também é avisado. O prazo é aplicado no começo do próximo comando do `main.py`: não há processo em segundo plano |
| `orcamento_esgotado` | passou de 30 mil tokens, US$ 0,05, 90 s ou do limite de passos (20 superpassos no grafo; 8 passos no laço); o motivo diz qual teto |
| `erro_fatal` | não há como continuar: API fora ou chave inválida; no grafo, resposta do modelo fora do contrato 2 vezes ou texto redigido reprovado 2 vezes; no laço, modelo que encerra sem desfecho depois de 2 lembretes |

**Exemplo completo, com entrada e saída reais.** É o caminho feliz do [`docs/io.md`](docs/io.md) §3.1,
pelo grafo: execução de `2026-10-12T17:37:33-03:00`, com `ministral-8b-latest` e os prompts em uso
(`triagem-v1.md`, `ressalva-v3.md`, `redigir-v3.md`, `regras-redigir-v2.md`), commit `4aa9818`.
O log completo está em `logs/grafo-40-1/TKT-0001.json`; os outros exemplos (recusa, fora do escopo,
entrada incompleta, entrada ambígua e pergunta fora do corpus) estão no `docs/io.md` §3.

O que a pessoa digita: `python src/main.py TKT-0001 "texto do chamado"`. Esta execução veio da
rodada `python src/main.py --todos --auto-aprovar --rodada grafo-40-1`, que usa o texto registrado
no banco para o chamado. Entrada (o campo `entrada` do log):

```
O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.
```

A trajetória (um passo por nó do grafo, como o terminal a mostrou em `logs/grafo-40-1/saida-demonstracao.txt`; o terminal corta as linhas longas):

```
  nó consultar         consultar_ticket {"id_ticket": "TKT-0001"} -> ok
  nó triagem           triagem {} -> ok
  nó buscar            buscar_base_conhecimento {"termos": ["certificado ssl", "renovacao automática", "navegador", "aviso site não seguro -> ok
  nó decidir           decidir {} -> ok
  nó redigir           redigir {"desfecho": "anotacao_interna"} -> ok
  nó gravar            registrar_encaminhamento {"id_ticket": "TKT-0001", "destino": "anotacao_interna", "mensagem": "Verificar se o desaf -> ok

  TERMINO: respondeu | desfecho: anotacao_interna | passos: 6 | chamadas ao modelo: 2 | lembretes: 0 | tokens: 1765 | custo: US$ 0.00026
```

Saída (o objeto validado, campo `saida` do log):

```json
{
  "id_ticket": "TKT-0001",
  "executado_em": "2026-10-12T17:37:33-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "anotacao_interna",
    "texto": "Verificar se o desafio HTTP-01 está falhando devido a porta 80 bloqueada ou DNS do domínio do cliente apontando para outro IP. Executar o comando `certbot renew --dry-run` para testar a renovação automática e, caso necessário, reativar o timer do certbot conforme procedimento **KB-101-A**.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "procedimento_da_base",
    "kb_id": "KB-101-A",
    "score": 0.66,
    "registros": [
      "TKT-0001"
    ],
    "ferramentas": [
      "consultar_ticket",
      "triagem",
      "buscar_base_conhecimento",
      "decidir",
      "redigir",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": true,
    "motivo": "procedimento KB-101-A com score 0.66, igual ou acima do limiar 0.5"
  }
}
```

Como ler: o grafo consultou o registro do chamado, a triagem classificou o assunto como técnico, e a busca encontrou o guia KB-101-A com score 0,66, acima do limiar de 0,5. Como o guia é "anotar", o nó `decidir` (código) escolheu a anotação, o modelo redigiu o texto e o grafo o gravou, **sem abrir chamado interno**: por isso `chamado_interno`, `time_destino` e `prioridade` estão nulos. `suficiencia.suficiente: true` quer dizer que o sistema teve base para agir sozinho, e `fonte` diz qual. Foram 2 chamadas ao modelo (triagem e redação). O custo é o simulado a preço de lista; no plano gratuito o gasto real é zero. O texto gravado traz marcação de Markdown que o modelo escreveu: a redação não tem verificador.

> **Sobre o id `KB-101` nos logs do laço.** Em 11/10/2026 a base passou a nomear as versões: o guia com letra é a atualização do guia sem letra. O procedimento de SSL vigente, que aparece aqui como `KB-101`, hoje é o `KB-101-A`; o `KB-101` de hoje é a versão antiga, revogada (`rag.md` §2.1). O texto do procedimento não mudou.

**Os oito logs de `logs/`, do laço.** São todos do laço (hoje, `--laco`), com `ministral-8b-latest`, o prompt `agente-v5.md`
e `--auto-aprovar`, de 10/10/2026, e todos têm o campo `saida` validado. Vieram de duas execuções
no mesmo dia, e não de uma rodada só:

| Log | Executado em | Commit | Desfecho | Verificador |
|---|---|---|---|---|
| `TKT-0001.json` | 15:45:26 | `861a948` | `anotacao_interna` (KB-101, score 0,62) | OK |
| `TKT-0002.json` | 15:47:35 | `861a948` | `fila_humana` (divergência; KB-106 com score 0,67) | OK |
| `TKT-0003.json` | 21:22:28 | `2ffb2b5 + alterações locais` | `abrir_chamado_interno` (KB-102, score 0,86, P1) | OK |
| `TKT-0004.json` | 15:48:10 | `861a948` | `fila_comercial` | OK |
| `TKT-0005.json` | 15:48:52 | `861a948` | `devolver_cliente` | OK |
| `TKT-0006.json` | 15:48:21 | `861a948` | `fila_humana` (KB-104, score 0,40, com ressalva) | OK |
| `TKT-0007.json` | 21:22:39 | `2ffb2b5 + alterações locais` | `abrir_chamado_interno` (KB-102, score 0,89, P2) | OK |
| `TKT-0999.json` | 21:22:46 | `2ffb2b5 + alterações locais` | `fila_humana` (id inexistente; 1 lembrete) | OK |

Os três das 21h22 foram refeitos um a um (`python src/main.py TKT-0003 --reset --auto-aprovar`, e o
mesmo para os outros dois): os anteriores eram do `agente-v3.md`, sem data, sem commit e sem o
campo `saida`, e os do `TKT-0003` e do `TKT-0007` ainda tinham o texto antigo do chamado.

**Estes oito logs não têm saída de terminal**, porque vieram de execuções avulsas, e não de um
`--todos`. A saída de terminal que ficava ao lado deles, `logs/saida-demonstracao.txt`, era da
rodada 4, com o `agente-v3.md` e o seed antigo (6 de 8, `docs/modelos.md` §3.3-C), e não
correspondia a eles: em 14/10/2026 ela foi movida, sem alteração, para
`logs/rodada-4-prompt-v3/saida-demonstracao.txt`. Um `--todos --laco` sem `--rodada` voltaria a
gravar `logs/saida-demonstracao.txt` e regravaria os oito logs acima. As rodadas completas do
`agente-v5.md`, com a saída de terminal de cada uma, estão em `logs/rodada-1-prompt-v5/` a
`logs/rodada-3-prompt-v5/`.

**O que ele não faz.** Não executa correções, não encerra chamados, não altera prioridade (só o gestor reclassifica) e só fala diretamente com o cliente para pedir a informação que falta (`devolver_cliente`, no máximo um pedido por chamado). No grafo o pedido espera a confirmação do analista e é registrado como enviado; **não há canal de mensagem, e a espera pela resposta do cliente não foi implementada**: a execução termina depois do envio. No laço (`--laco`) o pedido é gravado sem confirmação.

**A base de conhecimento.** No grafo a busca é vetorial (`mistral-embed`), sobre 15 guias vigentes; um nó em que o modelo lê as exceções de cada guia cobre parte do que o vetor não enxerga ([`docs/rag.md`](docs/rag.md) §4). Limite assumido: nenhum limiar separa bem as perguntas sem resposta na base, e 5 de 31 delas ainda levam a uma ação. No laço a busca é por palavras-chave, que não entende sinônimos.

**O que ele lembra.** O grafo grava um registro por execução concluída e mostra ao analista, na tela da confirmação, o que já foi decidido sobre o mesmo guia; o analista pode registrar fatos do ambiente de um cliente (`--fato`). O nó que redige carrega ainda uma regra que a leitura das execuções ensinou (não escrever um domínio que ninguém informou), guardada em `src/prompts/regras-redigir-v2.md` e escrita por uma pessoa. A memória só informa e orienta o texto: nenhuma decisão do sistema a lê ([`docs/memoria.md`](docs/memoria.md)).

**Quando ele não sabe.** Não chuta: o score da base abaixo de 0,5, um id inexistente ou um relato que contradiz o log anexado terminam em `fila_humana`, com uma mensagem que diz o que foi encontrado e por que um humano deve olhar.

## Estrutura

```
src/         grafo.py (o grafo em LangGraph: o caminho padrão) · vetorial.py (a busca vetorial do grafo)
             agente.py (o laço da Parte 1, estado, orçamento) · ferramentas.py · db.py (SQLite; a única
             camada que toca o banco, e onde ficam a memória e a busca por palavra) · saida.py (contrato de saída)
             verificar.py · main.py · medir_rag.py (as medições de docs/rag.md) · comparar_modelos.py
             (item 3.3 da Parte 1) · ver_log.py · testar_api.py
conferir_grafo.py   imprime o grafo compilado, para conferir com o desenho (docs/arquitetura.md §9)
demonstrar_reducer.py   roda o grafo com e sem reducer (docs/grafo.md §3.2); grava logs/grafo-reducer/
conferir_regras.py   lê os logs de uma rodada e confere a regra aprendida do redigir (docs/memoria.md §5.1)
src/prompts/ no grafo, em uso: triagem-v1.md · ressalva-v3.md · redigir-v3.md (carregados por grafo.py)
             triagem-v2.md (variante do teste da regra da frase no grafo, medida e não adotada,
             docs/prompts.md §3.7; roda com --prompt-triagem) · triagem-v1-sem-frase.md (o mesmo
             texto, com o nome que tinha na primeira passagem do teste)
             regras-redigir-v2.md (as regras aprendidas, anexadas ao redigir-v3.md) · regras-redigir-v1.md
             (medido e não adotado)
             ressalva-v1.md, redigir-v1.md e redigir-v2.md (anteriores) · ressalva-v2.md (medido e não adotado)
             no laço, em uso: agente-v5.md e lembrete-v1.md (carregados por agente.py)
             agente-v1.md a agente-v4.md (histórico) · agente-v5-sem-frase.md (variante do teste da regra da frase,
             docs/prompts.md §3) · agente-v4-com-frase.md e agente-v4-sem-frase.md (testes anteriores, §3.6)
dados/       seed.sql · gabarito.json · README.md (casos difíceis nomeados)
tests/       testes offline (sem chave): test_grafo.py (o grafo) · test_offline.py (o laço) · test_vetorial.py (a busca vetorial)
docs/        case.md · io.md · prompts.md · arquitetura.md · grafo.md · rag.md · memoria.md · humano.md
             modelos.md · modelos-tabela-3.3.md · base-de-conhecimento-v2.md · fontes.md
             arquitetura-v2.md (histórico da Parte 1)
logs/        trajetória de cada execução demonstrada (JSON); logs/grafo*/ são do grafo, logs/TKT-*.json e
             logs/rodada-*/ do laço, logs/rag-medicao/ das medições da busca
```
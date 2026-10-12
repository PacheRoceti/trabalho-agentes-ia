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
python src/main.py --todos --auto-aprovar   # os 8 casos, cada um a partir do banco zerado, com verificador
python src/main.py --reset                  # recria o banco simulado
python src/main.py TKT-0001 --laco          # o mesmo chamado pelo laço da Parte 1, e não pelo grafo; logs em logs/
python conferir_grafo.py                    # imprime os nós, as arestas e os campos do grafo compilado (sem chave)
```

**Dois caminhos.** O padrão é o grafo em LangGraph (`src/grafo.py`): o modelo classifica e redige, e o código decide o desfecho. Os logs dele vão para `logs/grafo/`. Com `--laco`, o chamado passa pelo laço da Parte 1 (`src/agente.py`), que grava em `logs/`; `--prompt ARQUIVO` escolhe um prompt do laço e já implica `--laco`. A entrada, a saída validada, o verificador e os comandos `--pendencias`, `--aprovar` e `--rejeitar` são os mesmos nos dois.

**O que foi medido no grafo:** 8 de 8 casos no verificador em três execuções (10/10/2026; `logs/grafo/`, `logs/grafo-rodada-2/`, `logs/grafo-rodada-3/`), cada uma com 15 chamadas ao modelo e cerca de 12,6 mil tokens nos 8 casos. O laço, na rodada 3 do `agente-v5.md`, deu 7 de 8, com 31 chamadas e 69.889 tokens ([`docs/grafo.md`](docs/grafo.md) §6). Essas três rodadas são anteriores à busca vetorial e ao nó da ressalva. Com os dois, a rodada de 11/10/2026 deu 8 de 8, com 17 chamadas e 14.440 tokens (`logs/grafo-fatos/`). Com o código e os prompts de 12/10/2026 (o pedido ao cliente esperando o analista, em texto padrão, e o `redigir-v3.md`), três rodadas deram 8 de 8, com 16 chamadas e cerca de 13,2 mil tokens cada (`logs/grafo-redigir-v3-1/` a `-3/`; [`docs/grafo.md`](docs/grafo.md) §6.5). **O exemplo abaixo e os de `docs/io.md` são do laço**, de quando ele era o caminho padrão: para repeti-los hoje, acrescente `--laco` ao comando.

**Os seis casos do enunciado (Parte 2, §9), e onde está o log de cada um.** Os casos 1 a 4 são da rodada `logs/grafo-redigir-v3-1/` (grafo, 12/10/2026, `ministral-8b-latest`, commit `9d5c211 + alterações locais`, os prompts em uso).

| # | O caso | Chamado | Log | O que aconteceu |
|---|---|---|---|---|
| 1 | simples | `TKT-0001` | `logs/grafo-redigir-v3-1/TKT-0001.json` | `anotacao_interna` com o guia KB-101-A, score 0,66 |
| 2 | divergência | `TKT-0002` | `logs/grafo-redigir-v3-1/TKT-0002.json` | a triagem marcou que o log anexado aponta outro serviço; `fila_humana`, motivo `divergencia_relato_log` |
| 3 | registro inexistente | `TKT-0999` | `logs/grafo-redigir-v3-1/TKT-0999.json` (grafo) e `logs/TKT-0999.json` (laço) | no grafo o id inexistente é uma rota do código: `fila_humana`, motivo `id_inexistente`, e o modelo só redige. O erro de ferramenta que **o modelo** contorna está no log do laço: a ferramenta devolve o erro e ele registra a fila humana, depois de 1 lembrete |
| 4 | não deve disparar a ação principal | `TKT-0004` | `logs/grafo-redigir-v3-1/TKT-0004.json` | `fila_comercial`, sem busca e sem chamado interno |
| 5 | pergunta fora do corpus | não há | **não há log de ponta a ponta** | a pergunta fora do corpus ("Como instalo o WordPress no meu site?") foi medida só na busca: o melhor guia fica abaixo do limiar (`docs/rag.md` §4.1; `logs/rag-medicao/saida.txt`, linha da P10). Falta passá-la pelo grafo, com log. A recusa que tem log é a do `TKT-0006` (`logs/grafo-redigir-v3-1/TKT-0006.json`): guia com score abaixo de 0,5, `fila_humana` |
| 6 | a ação que para e espera | `TKT-0007` | `logs/grafo-caso-6/` | pausa, uma edição recusada, aprovação com edição e a segunda aprovação sem duplicar (`saida-terminal.txt`). O mesmo para o pedido ao cliente, com o `TKT-0005`, em `logs/grafo-h2/` (aprovação com edição) e `logs/grafo-pedido-padrao-h2/` (o texto padrão do pedido, em uso) |

**Quando o grafo para e espera alguém.** Abrir chamado interno é irreversível. Sem `--auto-aprovar`, a execução para antes de gravar, mostra a ação exata (id, categoria, resumo, time, procedimento, prioridade prevista, hora do pedido e do prazo) e a consequência de aprová-la, e termina em `aguardando_humano`. O analista tem 20 minutos para responder, de outro terminal; `--pendencias` lista o que espera. São três respostas:

- `--aprovar TKT-0000`: o chamado é aberto com o resumo que o modelo redigiu, e a mesma execução conclui;
- `--aprovar TKT-0000 --resumo "texto corrigido"`: **aprovar editando**. O chamado é aberto com o resumo do analista. Só o resumo é editável; categoria, time e prioridade vêm do procedimento. Um resumo com menos de 20 caracteres é recusado, e a ação continua aguardando;
- `--rejeitar TKT-0000`: o chamado não é aberto e vai para a fila humana com a ação que o agente propôs. O mesmo acontece sem resposta no prazo.

Uma sequência real (pausar, listar, uma edição recusada, aprovar editando e aprovar de novo sem duplicar) está em `logs/grafo-caso-6/saida-terminal.txt`; a aprovação simples, em `logs/grafo-pausa/saida-terminal.txt`.

**O pedido de informação ao cliente também espera o analista** (desde 12/10/2026, só no grafo). A mensagem chega ao cliente e não tem volta, então o `devolver_cliente` pausa do mesmo jeito, com o mesmo prazo. A tela mostra o relato do cliente e a mensagem, que é um texto padrão com cinco perguntas (serviço, domínio ou banco, erro, data e hora, o que mudou), e não texto do modelo ([`docs/prompts.md`](docs/prompts.md) §2.2). As respostas são `--aprovar TKT-0000`, `--aprovar TKT-0000 --mensagem "texto corrigido"` (a mensagem do analista passa pela mesma regra: nenhuma informação interna) e `--rejeitar TKT-0000`, com `--motivo mensagem_ruim`, `informacao_suficiente` ou `outro`, se quiser. Rejeitado ou vencido, o chamado vai para a fila humana e o único pedido permitido do chamado não é gasto. **Limite:** o sistema simulado não tem canal de mensagem; "enviar" é gravar o pedido com a hora do envio. Sequência real em `logs/grafo-h2/saida-terminal.txt`, e o que ela achou em [`docs/humano.md`](docs/humano.md) §2.4.

Os chamados disponíveis são `TKT-0001` a `TKT-0007` e o inexistente `TKT-0999` (ver [`dados/README.md`](dados/README.md)).

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

**Exemplo completo, com entrada e saída reais.** É o caminho feliz do [`docs/io.md`](docs/io.md) §3.1:
execução de `2026-10-10T15:45:26-03:00`, com `ministral-8b-latest` e o prompt `agente-v5.md`, commit
`861a948`. O log completo está em `logs/TKT-0001.json`; os outros exemplos (recusa, fora do
escopo, entrada incompleta e entrada ambígua) estão no `docs/io.md` §3.

> **Sobre o id `KB-101` nestes logs.** Em 11/10/2026 a base passou a nomear as versões: o guia com letra é a atualização do guia sem letra. O procedimento de SSL vigente, que aparece aqui como `KB-101`, hoje é o `KB-101-A`; o `KB-101` de hoje é a versão antiga, revogada (`rag.md` §2.1). O texto do procedimento não mudou.

**Os oito logs de `logs/`.** São todos do laço (hoje, `--laco`), com `ministral-8b-latest`, o prompt `agente-v5.md`
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

**O que não foi refeito:** `logs/saida-demonstracao.txt`. Ele continua sendo a saída de terminal da
rodada 4, com o `agente-v3.md` e o seed antigo (6 de 8, `docs/modelos.md` §3.3-C), e **não
corresponde aos oito logs acima**. Só um `--todos` o regrava, e ele regrava também os cinco logs
das 15h, citados com data e tokens no `docs/io.md`. As rodadas completas do `agente-v5.md`, com a
saída de terminal de cada uma, estão em `logs/rodada-1-prompt-v5/` a `logs/rodada-3-prompt-v5/`.

Entrada (comando: `python src/main.py TKT-0001 --auto-aprovar`; o texto do chamado é o campo `entrada` do log):

```
O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.
```

A trajetória (os passos gravados no log, no formato em que o terminal os mostra):

```
  passo 0 [leitura ] consultar_ticket {"id_ticket": "TKT-0001"} -> ok
  passo 1 [leitura ] buscar_base_conhecimento {"termos": ["certificado ssl venceu", "renovacao automática não rodou", "aviso navegador site não seguro"]} -> ok
  passo 2 [ESCRITA ] registrar_encaminhamento {"id_ticket": "TKT-0001", "destino": "anotacao_interna", "mensagem": "Certificado SSL não renovou automaticame -> ok

  TERMINO: respondeu | desfecho: anotacao_interna | passos: 3 | chamadas ao modelo: 4 | lembretes: 0 | tokens: 8822 | custo: US$ 0.00132
```

Saída (o objeto validado, campo `saida` do log):

```json
{
  "id_ticket": "TKT-0001",
  "executado_em": "2026-10-10T15:45:26-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "anotacao_interna",
    "texto": "Certificado SSL não renovou automaticamente. Sugestão: conferir DNS do domínio e liberação da porta 80; rodar \"certbot renew --dry-run\"; reativar o timer do certbot.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "procedimento_da_base",
    "kb_id": "KB-101",
    "score": 0.62,
    "registros": [
      "TKT-0001"
    ],
    "ferramentas": [
      "consultar_ticket",
      "buscar_base_conhecimento",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": true,
    "motivo": "procedimento KB-101 com score 0.62, igual ou acima do limiar 0.5"
  }
}
```

Como ler: o agente consultou o registro do chamado (passo 0), buscou na base (passo 1) e encontrou o procedimento KB-101 com score 0,62, acima do limiar de 0,5. Como o procedimento é "anotar", ele registrou uma anotação com a correção sugerida para o analista (passo 2) e **não abriu chamado interno**: por isso `chamado_interno`, `time_destino` e `prioridade` estão nulos. `suficiencia.suficiente: true` quer dizer que o sistema teve base para agir sozinho, e `fonte` diz qual. O custo é o simulado a preço de lista; no plano gratuito o gasto real é zero.

**O que ele não faz.** Não executa correções, não encerra chamados, não altera prioridade (só o gestor reclassifica) e só fala diretamente com o cliente para pedir a informação que falta (`devolver_cliente`, no máximo um pedido por chamado). No grafo o pedido espera a confirmação do analista e é registrado como enviado; **não há canal de mensagem, e a espera pela resposta do cliente não foi implementada**: a execução termina depois do envio. No laço (`--laco`) o pedido é gravado sem confirmação.

**A base de conhecimento.** No grafo a busca é vetorial (`mistral-embed`), sobre 15 guias vigentes; um nó em que o modelo lê as exceções de cada guia cobre parte do que o vetor não enxerga ([`docs/rag.md`](docs/rag.md) §4). Limite assumido: nenhum limiar separa bem as perguntas sem resposta na base, e 5 de 31 delas ainda levam a uma ação. No laço a busca é por palavras-chave, que não entende sinônimos.

**O que ele lembra.** O grafo grava um registro por execução concluída e mostra ao analista, na tela da confirmação, o que já foi decidido sobre o mesmo guia; o analista pode registrar fatos do ambiente de um cliente (`--fato`). A memória só informa: nenhuma decisão do sistema a lê ([`docs/memoria.md`](docs/memoria.md)).

**Quando ele não sabe.** Não chuta: o score da base abaixo de 0,5, um id inexistente ou um relato que contradiz o log anexado terminam em `fila_humana`, com uma mensagem que diz o que foi encontrado e por que um humano deve olhar.

## Estrutura

```
src/         grafo.py (o grafo em LangGraph: o caminho padrão) · vetorial.py (a busca vetorial do grafo)
             agente.py (o laço da Parte 1, estado, orçamento) · ferramentas.py · db.py (SQLite; a única
             camada que toca o banco, e onde ficam a memória e a busca por palavra) · saida.py (contrato de saída)
             verificar.py · main.py · medir_rag.py (as medições de docs/rag.md) · comparar_modelos.py
             (item 3.3 da Parte 1) · ver_log.py · testar_api.py
conferir_grafo.py   imprime o grafo compilado, para conferir com o desenho (docs/arquitetura.md §9)
src/prompts/ no grafo, em uso: triagem-v1.md · ressalva-v3.md · redigir-v3.md (carregados por grafo.py)
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
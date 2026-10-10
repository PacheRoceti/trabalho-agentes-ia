# Agente de Triagem e Abertura de Chamado Interno

**Integrantes:** Daniel Filho Oliveira Lima · Pedro Gustavo de Campos Teixeira Silva · Pedro Roceti Pache

## O problema, em uma frase

> Excesso de trabalho manual no processo de ingresso dos chamados e falta de padronização das informações dos chamados internos.

Contexto, usuários, ganhos e riscos: [`docs/case.md`](docs/case.md) · Escolha do modelo: [`docs/modelos.md`](docs/modelos.md) · Arquitetura: [`docs/arquitetura-v2.md`](docs/arquitetura-v2.md) · Fontes: [`docs/fontes.md`](docs/fontes.md)

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
python src/main.py --rejeitar TKT-0003      # o analista rejeita: nada é gravado
python src/main.py --todos --auto-aprovar   # os 8 casos, cada um a partir do banco zerado, com verificador
python src/main.py --reset                  # recria o banco simulado
```

Os chamados disponíveis são `TKT-0001` a `TKT-0007` e o inexistente `TKT-0999` (ver [`dados/README.md`](dados/README.md)).

**O que o sistema faz.** Lê o texto do chamado e o histórico do cliente no sistema de tickets, decide se o assunto é técnico, comercial ou de informação insuficiente, consulta a base de conhecimento e dá **um desfecho** ao chamado. Quando o desfecho é abrir um chamado interno (ação irreversível), ele para, grava a ação pendente e espera a confirmação do analista de suporte, que tem **20 minutos** para aprovar ou rejeitar (`--aprovar` / `--rejeitar`). Sem resposta no prazo, o chamado interno não é aberto: o chamado vai para a fila humana com a ação que o agente propôs.

**O que ele devolve.** Uma linha por passo (ferramenta, argumentos, resultado ou erro), o motivo do término, o desfecho e o veredito do verificador. O que vale é o que foi **gravado no banco**:

| Desfecho | Significa | Onde ver |
|---|---|---|
| `abrir_chamado_interno` | chamado aberto para o time responsável, com resumo e prioridade definida pelo sistema | `python -c "import sqlite3; c=sqlite3.connect('dados/tickets.db'); print(*c.execute('select * from chamados_internos'), sep='\n')"` |
| `anotacao_interna` | correção sugerida para o analista validar e executar | tabela `encaminhamentos` |
| `fila_comercial` | assunto comercial, fora do escopo do suporte | tabela `encaminhamentos` |
| `devolver_cliente` | faltam informações; a mensagem é o pedido ao cliente (a única mensagem que o agente envia a ele, no máximo uma por chamado) | tabela `encaminhamentos` |
| `fila_humana` | o sistema não teve confiança para agir sozinho (ou o id não existe), ou o analista não confirmou a abertura do chamado em 20 minutos | tabela `encaminhamentos` |

Como interpretar o término (`TERMINO:` na saída):

| Término | Significa |
|---|---|
| `respondeu` | o agente registrou um desfecho e concluiu |
| `aguardando_humano` | a abertura do chamado espera o analista, ou ele a rejeitou: nada foi gravado, e o `motivo` diz qual dos dois. Na espera, a ação fica na tabela `pendencias`, com o prazo de 20 minutos; `--aprovar` conclui a execução (término `respondeu`). Vencido o prazo, o chamado vai para a fila humana com as considerações do agente (término `respondeu`, desfecho `fila_humana`). O prazo é aplicado no começo do próximo comando do `main.py`: não há processo em segundo plano |
| `orcamento_esgotado` | passou de 8 passos, 30 mil tokens, US$ 0,05 ou 90 s; o motivo diz qual teto |
| `erro_fatal` | não há como continuar (API fora, chave inválida, modelo encerrou sem desfecho) |

**Exemplo completo, com entrada e saída reais.** É o caminho feliz do [`docs/io.md`](docs/io.md) §3.1:
execução de `2026-10-10T15:45:26-03:00`, com `ministral-8b-latest` e o prompt `agente-v5.md`, commit
`861a948`. O log completo está em `logs/TKT-0001.json`; os outros exemplos (recusa, fora do
escopo, entrada incompleta e entrada ambígua) estão no `docs/io.md` §3.

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

**O que ele não faz.** Não executa correções, não encerra chamados, não altera prioridade (só o gestor reclassifica) e só fala diretamente com o cliente para pedir a informação que falta (`devolver_cliente`, no máximo um pedido por chamado). Na Parte 1 o pedido fica gravado em `encaminhamentos` e a execução termina; o envio ao cliente (que, por ser irreversível, exige a confirmação do analista) e a retomada da mesma conversa com a resposta entram na Parte 2. A base de conhecimento é uma busca por palavras-chave (Parte 1): ela não entende sinônimos, e é a razão de alguns chamados ficarem na `fila_humana` mesmo com procedimento existente.

**Quando ele não sabe.** Não chuta: o score da base abaixo de 0,5, um id inexistente ou um relato que contradiz o log anexado terminam em `fila_humana`, com uma mensagem que diz o que foi encontrado e por que um humano deve olhar.

## Estrutura

```
src/         agente.py (laço, estado, orçamento) · ferramentas.py · db.py (SQLite) · verificar.py
             main.py · comparar_modelos.py (item 3.3)
src/prompts/ agente-v5.md e lembrete-v1.md (os prompts em uso, carregados em tempo de execução por agente.py)
             agente-v1.md a agente-v4.md (histórico) · agente-v4-sem-frase.md (variante de teste, docs/prompts.md §3)
dados/       seed.sql · gabarito.json · README.md (casos difíceis nomeados)
tests/       testes offline (sem chave)
docs/        case.md · modelos.md · modelos-tabela-3.3.md · arquitetura-v2.md · base-de-conhecimento-v2.md · memoria.md · fontes.md
logs/        trajetória de cada execução demonstrada (JSON)
```
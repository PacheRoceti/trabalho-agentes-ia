# Entrada e saída

> **Estado deste documento.** O contrato de entrada (§1) e o de saída (§2) descrevem o sistema da
> Parte 2 e ainda **não estão implementados**: hoje o programa recebe o id do chamado e devolve o
> objeto de log da Parte 1. Os três exemplos (§3) são **execuções reais da Parte 1**, copiadas de
> `logs/`, do commit `d60a2bd` (21/09/2026). Eles mostram o comportamento que o contrato formaliza
> e serão substituídos por execuções do grafo, no schema novo, quando ele existir.

## 1. A entrada

**A entrada do sistema é o texto livre que o cliente escreveu no chamado**, exatamente como foi
digitado. Não há formulário nem campos: o cliente não informa categoria, serviço, prioridade nem
time.

| O que chega | De onde vem | Quem digita |
|---|---|---|
| **texto do chamado** | o cliente, ao abrir o chamado externo | o cliente |
| id do chamado (`TKT-0000`) | sistema de chamados | ninguém; vira o `thread_id` da conversa |
| id do cliente | sistema de chamados | ninguém |
| resposta do cliente ao pedido de informação | o cliente, no mesmo chamado | o cliente; retoma a mesma conversa |

O que não é entrada:

- **O evento de abertura do chamado** é o gatilho que antecede o sistema. Ele entrega o texto e os
  dois ids; não é a entrada.
- **O log anexado, o plano e o histórico do cliente** são conteúdo que o agente busca por
  ferramenta (`consultar_ticket`), não parte do texto.

**Na Parte 1** o programa simula o evento: recebe o id na linha de comando
(`python src/main.py TKT-0004`) e o agente lê o texto pelo `consultar_ticket`. Nos exemplos abaixo,
a "entrada" é o texto do chamado, e o comando executado aparece ao lado.

## 2. O contrato de saída

A saída é um objeto validado, com o schema no código (Pydantic, a implementar em `src/`). Os três
campos obrigatórios do enunciado, no nosso domínio:

| Campo do enunciado | No nosso sistema | Valores |
|---|---|---|
| **resultado** | o desfecho gravado para o chamado | `abrir_chamado_interno`, `anotacao_interna`, `fila_comercial`, `devolver_cliente` ou `fila_humana`, mais a mensagem ou o resumo registrado |
| **fonte** | o que sustenta o desfecho | o procedimento da base (`kb_id` e score), o registro consultado (chamado, histórico) ou a ferramenta que respondeu |
| **suficiência** | se o sistema teve base para agir sozinho | positiva quando há procedimento com score ≥ 0,5 ou classificação que dispensa a base (comercial); negativa quando o desfecho é `fila_humana` ou `devolver_cliente`, com o motivo |

A recusa faz parte do contrato: `fila_humana` e `devolver_cliente` são saídas válidas, com
suficiência negativa e o motivo escrito.

**O que a Parte 1 devolve hoje.** O objeto gravado em `logs/TKT-xxxx.json`. Ele já tem as três
informações, mas sem schema validado e sem campo próprio para a suficiência:

| Campo do enunciado | Onde está hoje |
|---|---|
| resultado | `desfecho.acao` e a `mensagem` (ou `resumo`) do passo de escrita |
| fonte | `desfecho.kb_id` e `scores_kb` |
| suficiência | implícita: deduzida de `desfecho.acao` e de `scores_kb`; não há campo |

## 3. Os exemplos

Os três são do commit `d60a2bd` (21/09/2026), modelo `ministral-8b-latest`, prompt `agente-v3.md`,
`temperature=0`, execução `python src/main.py --todos --auto-aprovar`. A saída é o objeto do log
sem o campo `passos` (a trajetória), que está inteiro no arquivo indicado.

Limite: o log da Parte 1 não registra a data e a hora da execução, só o commit. O "agora" do banco
simulado é fixo (`2026-09-21 12:00`, em `src/db.py`). O carimbo de data da execução entra no log na
Parte 2.

### 3.1 O caminho feliz: `TKT-0001`

**Entrada** (comando: `python src/main.py TKT-0001 --auto-aprovar`):

```
O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.
```

**Saída** (`logs/TKT-0001.json`):

```json
{
  "execucao_id": "TKT-0001-2775",
  "id_ticket": "TKT-0001",
  "modelo": "ministral-8b-latest",
  "prompt": "agente-v3.md",
  "termino": "respondeu",
  "motivo": null,
  "resposta": "O chamado TKT-0001 foi encaminhado para anotação interna com a sugestão de verificação do certificado SSL.",
  "desfecho": {
    "acao": "anotacao_interna",
    "kb_id": "KB-101",
    "encaminhamento": 1,
    "destino": "anotacao_interna"
  },
  "pendencia": null,
  "confirmacoes": [],
  "n_chamadas_modelo": 4,
  "lembretes": 0,
  "tokens_entrada": 7099,
  "tokens_saida": 196,
  "custo_usd": 0.001094,
  "scores_kb": {
    "KB-101": 0.73
  }
}
```

Mensagem gravada na anotação (passo 2 do log):

```
Certificado SSL venceu e renovação automática não ocorreu. Sugestão: verificar desafio HTTP-01 (porta 80 bloqueada ou DNS incorreto), executar "certbot renew --dry-run" e reativar timer do certbot.
```

**O que ler aqui:** `desfecho.kb_id` é `KB-101` e o score é 0,73, acima do limiar de 0,5; o
procedimento é "anotar", então o desfecho é uma anotação e nenhum chamado interno foi aberto. Os
passos da mensagem são os do KB-101, sem nada acrescentado.

### 3.2 A recusa: `TKT-0006`

**Entrada** (comando: `python src/main.py TKT-0006 --auto-aprovar`):

```
Meu site está dando erro 502 de vez em quando, mais ou menos desde o deploy de ontem. Às vezes funciona normal.
```

**Saída** (`logs/TKT-0006.json`):

```json
{
  "execucao_id": "TKT-0006-2798",
  "id_ticket": "TKT-0006",
  "modelo": "ministral-8b-latest",
  "prompt": "agente-v3.md",
  "termino": "respondeu",
  "motivo": null,
  "resposta": "O chamado TKT-0006 foi encaminhado para análise humana, pois o erro 502 no site não tem procedimento automático definido.",
  "desfecho": {
    "acao": "fila_humana",
    "kb_id": null,
    "encaminhamento": 1,
    "destino": "fila_humana"
  },
  "pendencia": null,
  "confirmacoes": [],
  "n_chamadas_modelo": 4,
  "lembretes": 0,
  "tokens_entrada": 6774,
  "tokens_saida": 181,
  "custo_usd": 0.001043,
  "scores_kb": {}
}
```

Mensagem gravada na fila humana (passo 2 do log):

```
Cliente relata erro 502 intermitente no site desde o deploy de ontem. Nenhum artigo na base de conhecimento corresponde aos termos 'site erro 502'. Recomenda-se análise manual para verificar se o problema está relacionado ao deploy ou a outro serviço.
```

**O que ler aqui:** `scores_kb` está vazio e `desfecho.kb_id` é `null`: o sistema não teve base e
disse isso em vez de sugerir uma correção. A mensagem conta o que foi buscado e por que um humano
deve olhar. Nenhum chamado interno foi aberto, que é o que o gabarito exige neste caso.

Ressalva sobre este exemplo: o motivo esperado da recusa era a correspondência parcial (o KB-104
cobre falha constante e o relato é intermitente, score 0,44). Nesta execução o modelo buscou com a
frase "erro 502", que a busca por palavra não casa, e a base não devolveu nada. O desfecho está
certo, mas por um caminho mais fraco que o previsto. É uma das falhas da busca por palavra
registradas em `docs/modelos.md` §3.3-B.

### 3.3 Fora do escopo: `TKT-0004`

**Entrada** (comando: `python src/main.py TKT-0004 --auto-aprovar`):

```
Olá, quero fazer upgrade do meu plano para um servidor dedicado. Podem me passar valores e prazo de migração?
```

**Saída** (`logs/TKT-0004.json`):

```json
{
  "execucao_id": "TKT-0004-2791",
  "id_ticket": "TKT-0004",
  "modelo": "ministral-8b-latest",
  "prompt": "agente-v3.md",
  "termino": "respondeu",
  "motivo": null,
  "resposta": "O chamado TKT-0004 foi encaminhado para a fila comercial para avaliação do upgrade do plano.",
  "desfecho": {
    "acao": "fila_comercial",
    "kb_id": null,
    "encaminhamento": 1,
    "destino": "fila_comercial"
  },
  "pendencia": null,
  "confirmacoes": [],
  "n_chamadas_modelo": 3,
  "lembretes": 0,
  "tokens_entrada": 4958,
  "tokens_saida": 106,
  "custo_usd": 0.00076,
  "scores_kb": {}
}
```

Mensagem gravada na fila comercial (passo 1 do log):

```
Cliente solicitou upgrade para servidor dedicado, solicitando valores e prazo de migração.
```

**O que ler aqui:** o agente reconheceu o assunto como comercial, fora do escopo do suporte
técnico, e não tratou o pedido como defeito: `scores_kb` vazio mostra que ele nem consultou a base
de procedimentos, e o chamado foi redirecionado em 2 passos, sem chamado interno. É o caso que não
deve disparar a ação principal.

## 4. A entrada que não dá para atender (§1.4)

| Situação | O que o sistema faz | Exemplo real |
|---|---|---|
| **fora do escopo** | redireciona à fila comercial, sem consultar a base e sem abrir chamado | `TKT-0004`, §3.3 |
| **incompleta** | pede ao cliente o serviço afetado, o sintoma e desde quando (`devolver_cliente`), no máximo uma vez | `TKT-0005`, `logs/TKT-0005.json` (Parte 1: só grava o pedido; o envio e a retomada entram na Parte 2) |
| **ambígua** | não age sozinho: envia à fila humana dizendo qual é a ambiguidade | ainda sem exemplo próprio. O mais próximo é o `TKT-0002` (relato de webmail, log de DNS), que precisa ser executado de novo depois da correção do seed |

## 5. O que falta para este item

- Receber o texto como entrada do programa, em vez do id.
- Escrever o schema de saída em Pydantic, com resultado, fonte e suficiência, e validar toda saída.
- Registrar data e hora da execução no log.
- Refazer os três exemplos com o grafo, no schema novo, com commit, data e log.
- Produzir o exemplo de entrada ambígua.
- Repetir o exemplo principal (§3.1) no `README`.

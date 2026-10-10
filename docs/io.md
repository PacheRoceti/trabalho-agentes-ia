# Entrada e saída

> **Estado deste documento.** O contrato de saída (§2) **está implementado** em `src/saida.py`
> (Pydantic), e o log passou a gravar data, hora e commit de cada execução (10/10/2026). O contrato
> de entrada (§1) **também**: o programa recebe o texto do chamado, digitado, junto do id. Os quatro
> exemplos (§3) são **execuções reais de 10/10/2026**, no schema novo, copiadas de `logs/`.

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

**Como o texto entra no programa** (`src/main.py`). O texto é digitado na linha de comando, junto
do id que o acompanha:

```bash
python src/main.py TKT-0004 "Olá, quero fazer upgrade do meu plano para um servidor dedicado."
```

- Sem o texto (`python src/main.py TKT-0004`), o programa pede que ele seja digitado no terminal.
  Enter em branco usa o texto já registrado para o id, simulando o evento de abertura.
- **Vale o texto digitado.** Ele vai ao agente exatamente como foi escrito e é gravado no chamado
  antes da execução, para a busca na base e o registro usarem o mesmo texto. O id continua
  identificando o que é registro: o cliente, o log anexado e o histórico.
- Um id que não existe não cria chamado: o texto vai ao agente, `consultar_ticket` devolve o erro
  e o desfecho é a fila humana.
- O log grava o campo `entrada` com o texto como chegou.
- A demonstração (`--todos`) não recebe texto: usa os textos do banco simulado, que são os do
  gabarito. O verificador só confere execuções com o texto registrado.
- O texto digitado fica no banco simulado até `python src/main.py --reset`.

Nos exemplos do §3, a entrada mostrada é o campo `entrada` do log de cada execução.

## 2. O contrato de saída

A saída é um objeto validado, com o schema no código: a classe `Saida`, em `src/saida.py`
(Pydantic). Os três campos obrigatórios do enunciado, no nosso domínio:

| Campo do enunciado | No nosso sistema | Valores |
|---|---|---|
| **resultado** | o desfecho gravado para o chamado | `abrir_chamado_interno`, `anotacao_interna`, `fila_comercial`, `devolver_cliente` ou `fila_humana`, mais a mensagem ou o resumo registrado |
| **fonte** | o que sustenta o desfecho | o procedimento da base (`kb_id` e score), o registro consultado (chamado, histórico) ou a ferramenta que respondeu |
| **suficiência** | se o sistema teve base para agir sozinho | positiva quando há procedimento com score ≥ 0,5 ou classificação que dispensa a base (comercial); negativa quando o desfecho é `fila_humana` ou `devolver_cliente`, com o motivo |

A recusa faz parte do contrato: `fila_humana` e `devolver_cliente` são saídas válidas, com
suficiência negativa e o motivo escrito.

**O schema, campo a campo** (`src/saida.py`):

| Campo | Tipo | Conteúdo |
|---|---|---|
| `id_ticket` | texto | o chamado triado |
| `executado_em` | texto | data e hora do início da execução, ISO 8601 com fuso |
| `termino` | texto | `respondeu`, `aguardando_humano`, `orcamento_esgotado` ou `erro_fatal` |
| `resultado.acao` | um dos cinco desfechos, ou nulo | nulo quando a execução terminou sem desfecho |
| `resultado.texto` | texto ou nulo | o que foi gravado: o resumo do chamado interno ou a mensagem do encaminhamento |
| `resultado.chamado_interno`, `time_destino`, `prioridade` | texto ou nulo | preenchidos só em `abrir_chamado_interno` |
| `fonte.tipo` | `procedimento_da_base`, `registro_do_chamado`, `busca_sem_correspondencia` ou `nenhuma` | o que sustenta o desfecho |
| `fonte.kb_id`, `fonte.score` | texto e número, ou nulos | o procedimento usado; na recusa, o melhor candidato da busca |
| `fonte.registros` | lista | o chamado externo e os chamados internos do histórico consultado |
| `fonte.ferramentas` | lista | as ferramentas chamadas na execução, na ordem |
| `suficiencia.suficiente` | booleano | verdadeiro quando o sistema teve base para agir sozinho |
| `suficiencia.motivo` | texto | por que sim ou por que não |

**Quem preenche.** O código, a partir do `Estado` (o que as ferramentas gravaram e devolveram).
Nenhum campo vem do texto livre do modelo; `resultado.texto` é o argumento que o modelo passou à
ferramenta de escrita e que foi gravado no banco.

**O que a validação recusa.** Suficiência positiva com desfecho `fila_humana`, `devolver_cliente`
ou sem desfecho; suficiência negativa nos outros três; `abrir_chamado_interno` ou
`anotacao_interna` sem procedimento da base com score ≥ 0,5; desfecho sem o texto registrado;
chamado interno sem id, time ou prioridade; campo fora do schema. Uma saída que não passa termina a
execução como `erro_fatal`, com o motivo "saída fora do contrato".

**Onde aparece.** No campo `saida` de `logs/TKT-xxxx.json` e na saída do terminal
(`python src/main.py TKT-0001`). O resto do log (passos, tokens, custo, confirmações) continua lá,
fora do contrato. O log grava também `executado_em` e `commit`; o commit vem com a marca
"+ alterações locais" quando há mudança em `src/` ou `dados/` ainda não commitada.

## 3. Os exemplos

Os quatro exemplos são execuções reais de 10/10/2026, com `ministral-8b-latest`, prompt
`agente-v5.md` e `temperature=0`. Cada um traz a entrada como chegou, o objeto de saída completo
(com os campos nulos), a data e a hora da execução, o commit e o log correspondente em `logs/`. O
log tem ainda a trajetória (`passos`), que não faz parte do contrato de saída.

Limite: o commit gravado nos quatro logs é `5d5fdeb + alterações locais`. A marca "+ alterações locais" quer dizer
que o código de `src/` ou `dados/` tinha mudanças ainda não commitadas quando as execuções foram
feitas, então o commit sozinho não reproduz o que rodou. O "agora" do banco simulado é fixo
(`2026-09-21 12:00`, em `src/db.py`) e não é a data da execução.

### 3.1 O caminho feliz: `TKT-0001`

**Entrada** (comando: `python src/main.py TKT-0001 --auto-aprovar`; o texto é o campo `entrada` do log):

```
O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.
```

**Saída** (campo `saida` de `logs/TKT-0001.json`, completo):

```json
{
  "id_ticket": "TKT-0001",
  "executado_em": "2026-10-10T15:26:06-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "anotacao_interna",
    "texto": "Certificado SSL venceu e a renovação automática não ocorreu. Sugestão: verificar desafio HTTP-01 (porta 80 bloqueada ou DNS incorreto) e rodar \"certbot renew --dry-run\" para testar a renovação.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "procedimento_da_base",
    "kb_id": "KB-101",
    "score": 0.89,
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
    "motivo": "procedimento KB-101 com score 0.89, igual ou acima do limiar 0.5"
  }
}
```

Execução de `2026-10-10T15:26:06-03:00`, commit `5d5fdeb + alterações locais`, log em `logs/TKT-0001.json` (4 chamadas ao modelo, 8813 tokens).

**O que ler aqui:** `suficiencia.suficiente` é `true` porque `fonte` aponta o procedimento KB-101
com score 0,89, acima do limiar de 0,5. O procedimento é "anotar", então `resultado.acao` é
`anotacao_interna` e os três campos do chamado interno ficam nulos: nenhum chamado foi aberto. O
`resultado.texto` traz os passos do KB-101, sem nada acrescentado.

### 3.2 A recusa: `TKT-0006`

**Entrada** (comando: `python src/main.py TKT-0006 --auto-aprovar`; o texto é o campo `entrada` do log):

```
Meu site está dando erro 502 de vez em quando, mais ou menos desde o deploy de ontem. Às vezes funciona normal.
```

**Saída** (campo `saida` de `logs/TKT-0006.json`, completo):

```json
{
  "id_ticket": "TKT-0006",
  "executado_em": "2026-10-10T15:26:29-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_humana",
    "texto": "O cliente relata erro 502 intermitente após deploy, mas o artigo encontrado (KB-104) tem ressalva: não cobre casos em que o erro ocorre 'às vezes'. O anexo_log não está disponível para análise. Um analista deve verificar o comportamento do servidor e o log de erros para identificar a causa real.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "busca_sem_correspondencia",
    "kb_id": "KB-104",
    "score": 0.4,
    "registros": [
      "TKT-0006"
    ],
    "ferramentas": [
      "consultar_ticket",
      "buscar_base_conhecimento",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": false,
    "motivo": "o melhor procedimento encontrado (KB-104, score 0.4) ficou abaixo do limiar 0.5"
  }
}
```

Execução de `2026-10-10T15:26:29-03:00`, commit `5d5fdeb + alterações locais`, log em `logs/TKT-0006.json` (4 chamadas ao modelo, 8826 tokens).

**O que ler aqui:** `suficiencia.suficiente` é `false`, e o motivo diz por quê: o melhor
procedimento (KB-104) ficou com score 0,4, abaixo do limiar. Em vez de uma correção, o sistema
registrou em `resultado.texto` o que encontrou e por que um analista deve olhar: o KB-104 tem uma
ressalva, não cobre o erro que acontece "às vezes". É a correspondência parcial que o caso testa
(o guia cobre a falha constante; o relato é intermitente), e nenhum chamado interno foi aberto.

Ressalva sobre este exemplo: a frase "O anexo_log não está disponível para análise", no texto
registrado, não é motivo da recusa; o chamado simplesmente não tem log anexado.

### 3.3 Fora do escopo: `TKT-0004`

**Entrada** (comando: `python src/main.py TKT-0004 --auto-aprovar`; o texto é o campo `entrada` do log):

```
Olá, quero fazer upgrade do meu plano para um servidor dedicado. Podem me passar valores e prazo de migração?
```

**Saída** (campo `saida` de `logs/TKT-0004.json`, completo):

```json
{
  "id_ticket": "TKT-0004",
  "executado_em": "2026-10-10T15:26:50-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_comercial",
    "texto": "Cliente solicitou upgrade para servidor dedicado, pedindo valores e prazo de migração.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "registro_do_chamado",
    "kb_id": null,
    "score": null,
    "registros": [
      "TKT-0004"
    ],
    "ferramentas": [
      "consultar_ticket",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": true,
    "motivo": "assunto comercial: a classificação dispensa a base de procedimentos"
  }
}
```

Execução de `2026-10-10T15:26:50-03:00`, commit `5d5fdeb + alterações locais`, log em `logs/TKT-0004.json` (3 chamadas ao modelo, 6199 tokens).

**O que ler aqui:** `resultado.acao` é `fila_comercial` e `fonte.ferramentas` tem só
`consultar_ticket` e `registrar_encaminhamento`: o agente reconheceu o assunto como comercial, não
consultou a base de procedimentos e não tratou o pedido como defeito. A suficiência é positiva
porque a classificação dispensa a base. É o caso que não deve disparar a ação principal.

### 3.4 Entrada ambígua: `TKT-0002`

O relato fala de um serviço (webmail) e o log anexado aponta a causa em outro (DNS). Há na base um
procedimento de DNS que casa bem com o log e abriria um chamado P1; o sistema não escolhe sozinho
entre as duas leituras.

**Entrada** (comando: `python src/main.py TKT-0002 --auto-aprovar`; o texto é o campo `entrada` do log):

```
Meu Webmail está fora do ar desde cedo, ninguém da empresa consegue ler e-mail.
```

**Saída** (campo `saida` de `logs/TKT-0002.json`, completo):

```json
{
  "id_ticket": "TKT-0002",
  "executado_em": "2026-10-10T15:35:59-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_humana",
    "texto": "O cliente relata que o webmail está fora do ar, mas o anexo_log aponta falha de resolução DNS no domínio `mail.zeta.com.br` e no nameserver `ns1.zeta.com.br`. A busca na base de conhecimento confirmou que o problema pode estar relacionado a nameservers fora do ar ou registros DNS inválidos (artigo KB-106, score 0.67). O acesso direto ao webmail pelo IP do servidor funciona, o que reforça a suspeita de um problema de DNS. Recomenda-se verificar a configuração DNS e escalar para o time de infraestrutura.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "registro_do_chamado",
    "kb_id": "KB-106",
    "score": 0.67,
    "registros": [
      "TKT-0002"
    ],
    "ferramentas": [
      "consultar_ticket",
      "registrar_encaminhamento",
      "buscar_base_conhecimento",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": false,
    "motivo": "havia procedimento com score igual ou acima do limiar (KB-106, 0.67), mas o agente não agiu sozinho; o motivo está no texto registrado no resultado"
  }
}
```

Execução de `2026-10-10T15:35:59-03:00`, commit `5d5fdeb + alterações locais`, log em `logs/TKT-0002.json` (5 chamadas ao modelo, 13238 tokens).

**O que ler aqui:** havia um procedimento acima do limiar (`fonte.kb_id` KB-106, score 0,67) e
mesmo assim `resultado.acao` é `fila_humana`, com suficiência negativa: o motivo diz que o agente
não agiu sozinho, e `resultado.texto` declara as duas leituras (o cliente relata o webmail fora do
ar; o log mostra falha de DNS, e o webmail abre pelo IP). `fonte.tipo` é `registro_do_chamado`
porque o que sustenta a decisão é o log anexado ao chamado, não o procedimento.

Ressalvas sobre este exemplo, lidas no log:

- `fonte.ferramentas` mostra `registrar_encaminhamento` duas vezes. Na primeira, o modelo tentou a
  fila humana sem ter buscado na base, e o código recusou (erro recuperável); ele buscou e
  registrou na segunda. O desfecho é o mesmo, com uma chamada a mais.
- O texto registrado termina recomendando "escalar para o time de infraestrutura". A decisão de
  não abrir o chamado está certa, mas essa recomendação vai além do que o agente deveria dizer:
  quem confirma a relação entre o sintoma e a causa é o analista (`docs/case.md` §2.12).

## 4. A entrada que não dá para atender (§1.4)

| Situação | O que o sistema faz | Exemplo real |
|---|---|---|
| **fora do escopo** | redireciona à fila comercial, sem consultar a base e sem abrir chamado | `TKT-0004`, §3.3 |
| **incompleta** | pede ao cliente o serviço afetado, o sintoma e desde quando (`devolver_cliente`), no máximo uma vez | `TKT-0005`: ainda sem execução no schema novo. O `logs/TKT-0005.json` é de 06/10/2026, anterior ao objeto `saida` (Parte 1: só grava o pedido; o envio e a retomada entram na Parte 2) |
| **ambígua** | não age sozinho: envia à fila humana declarando as duas leituras | `TKT-0002`, §3.4 |

## 5. O que falta para este item

- Refazer as quatro execuções a partir de um commit sem alterações locais, para o commit gravado no
  log reproduzir o que rodou.
- Executar o `TKT-0005` no schema novo, para a entrada incompleta ter exemplo com data, commit e log.

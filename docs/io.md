# Entrada e saída

> **Estado deste documento.** O contrato de saída (§2) **está implementado** em `src/saida.py`
> (Pydantic), e o log passou a gravar data, hora e commit de cada execução (10/10/2026). O contrato
> de entrada (§1) **também**: o programa recebe o texto do chamado, digitado, junto do id. Os seis
> exemplos (§3) são **execuções reais do grafo, de 12/10/2026**, do commit `4aa9818`, copiadas de
> `logs/grafo-40-1/`.
>
> **12/10/2026: os exemplos passaram a ser do grafo, que é o caminho padrão.** Até aqui eram do
> laço da Parte 1 (10/10/2026, commit `861a948`). O contrato de saída é o mesmo nos dois, mas o
> conteúdo mudou: no grafo a busca é vetorial, o guia de SSL vigente é o `KB-101-A` e o pedido ao
> cliente espera o analista e é texto padrão. Entrou um sexto exemplo, a pergunta fora do corpus
> (`TKT-0119`, §3.6), e um sétimo, com o texto digitado na linha de comando e a confirmação dada
> por uma pessoa (`TKT-0007`, §3.7; `logs/grafo-digitado/`, commit `15398e0`). **A espera pela resposta do cliente (H3) não foi construída** (§5).

## 1. A entrada

**A entrada do sistema é o texto livre que o cliente escreveu no chamado**, exatamente como foi
digitado. Não há formulário nem campos: o cliente não informa categoria, serviço, prioridade nem
time.

| O que chega | De onde vem | Quem digita |
|---|---|---|
| **texto do chamado** | o cliente, ao abrir o chamado externo | o cliente |
| id do chamado (`TKT-0000`) | sistema de chamados | ninguém; vira o `thread_id` da conversa |
| id do cliente | sistema de chamados | ninguém |
| resposta do cliente ao pedido de informação | o cliente, no mesmo chamado | o cliente. **Não implementado:** a espera pela resposta (H3) não existe; hoje a resposta entraria como o texto de uma execução nova do mesmo chamado |

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

São sete exemplos, todos execuções reais **do grafo**, o caminho padrão. O sétimo (§3.7) é uma
execução avulsa, com o texto digitado e a confirmação de uma pessoa, e traz os próprios dados. Os
seis primeiros são da mesma rodada:
`logs/grafo-40-1/`, de 12/10/2026, commit `4aa9818`, com `ministral-8b-latest`, `temperature=0` e os
prompts em uso (`triagem-v1.md`, `ressalva-v3.md`, `redigir-v3.md`, `regras-redigir-v2.md`). O comando da rodada foi
`python src/main.py --todos --auto-aprovar --rodada grafo-40-1`, que roda os 40 casos do gabarito,
cada um a partir do banco recriado; o resultado da rodada inteira (36 de 40) está em `grafo.md`
§6.6. Cada exemplo traz a entrada como chegou, o objeto de saída completo (com os campos nulos), a
data e a hora da execução, o commit e o log correspondente. O log tem ainda a trajetória
(`passos`), que não faz parte do contrato de saída.

**A entrada, nestes exemplos.** `--todos` não recebe texto digitado: usa o texto registrado no
banco simulado para cada chamado (§1), e é esse texto que o log guarda no campo `entrada`. Para
repetir um deles digitando o texto: `python src/main.py TKT-0001 "texto" --auto-aprovar --rodada NOME`
(sem `--rodada`, o log vai para `logs/grafo/`, por cima do que está lá).

**`fonte.ferramentas`, no grafo.** A lista traz um item por nó que deixou passo no log, e não só
ferramentas: `triagem`, `decidir`, `redigir` e `confirmar` são nós do grafo. A consulta ao
chamado, a busca na base e a gravação aparecem com os nomes das ferramentas do laço.

**Os exemplos anteriores eram do laço da Parte 1** (10/10/2026, commit `861a948`, prompt
`agente-v5.md`, busca por palavra). Saíram deste documento em 12/10/2026 e continuam no histórico
do git; os logs deles continuam em `logs/TKT-0001.json` a `logs/TKT-0006.json`, na tabela
"Os oito logs de `logs/`" do README. O contrato de saída é o mesmo nos dois caminhos.

Limite: o "agora" do banco simulado é fixo (`2026-09-21 12:00`, em `src/db.py`) e não é a data da
execução, que está em `executado_em`. Com `--auto-aprovar`, nenhuma confirmação dos seis primeiros
passou por uma pessoa; a do §3.7 passou.

### 3.1 O caminho feliz: `TKT-0001`

**Entrada** (o campo `entrada` do log):

```
O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.
```

**Saída** (campo `saida` de `logs/grafo-40-1/TKT-0001.json`, completo):

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

Execução de `2026-10-12T17:37:33-03:00`, commit `4aa9818`, log em `logs/grafo-40-1/TKT-0001.json` (2 chamadas ao modelo, 1.765 tokens, mais 1.779 tokens de embedding).

**O que ler aqui:** `suficiencia.suficiente` é `true` porque `fonte` aponta o guia KB-101-A com score 0,66, acima do limiar de 0,5. O guia é "anotar", então `resultado.acao` é `anotacao_interna` e os três campos do chamado interno ficam nulos: nenhum chamado foi aberto. O `resultado.texto` traz os passos do KB-101-A (porta 80, DNS, `certbot renew --dry-run`, o timer do certbot). O `KB-101`, versão antiga e revogada do mesmo guia, não aparece: a busca o descarta (`rag.md` §2.1).

Ressalva sobre este exemplo: o texto gravado tem marcação de Markdown (`**KB-101-A**`, crases), que o modelo escreveu e nenhuma regra retira. A redação não tem verificador (`prompts.md` §4).

### 3.2 A recusa: `TKT-0006`

**Entrada** (o campo `entrada` do log):

```
Meu site está dando erro 502 de vez em quando, mais ou menos desde o deploy de ontem. Às vezes funciona normal.
```

**Saída** (campo `saida` de `logs/grafo-40-1/TKT-0006.json`, completo):

```json
{
  "id_ticket": "TKT-0006",
  "executado_em": "2026-10-12T17:38:09-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_humana",
    "texto": "O cliente relata que o site do domínio do cliente apresenta erro 502 de forma intermitente, desde o deploy realizado ontem, com períodos em que funciona normalmente. Não há log anexado para análise. O procedimento encontrado (KB-104) possui score 0.24, abaixo do limiar de confiança (0.5), e contém ressalva: não cobre o caso relatado ('as vezes'). Além disso, a causa descrita no procedimento (falha constante) não condiz com o relato do cliente. O suporte não possui escopo para a aplicação ou o deploy realizado pelo cliente.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "busca_sem_correspondencia",
    "kb_id": "KB-106",
    "score": 0.48,
    "registros": [
      "TKT-0006"
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
    "suficiente": false,
    "motivo": "o melhor procedimento encontrado (KB-106, score 0.48) ficou abaixo do limiar 0.5"
  }
}
```

Execução de `2026-10-12T17:38:09-03:00`, commit `4aa9818`, log em `logs/grafo-40-1/TKT-0006.json` (2 chamadas ao modelo, 1.792 tokens, mais 1.768 tokens de embedding).

**O que ler aqui:** `suficiencia.suficiente` é `false`, e o motivo diz por quê: o melhor procedimento ficou abaixo do limiar. Em vez de uma correção, o sistema registrou em `resultado.texto` o que encontrou e por que um analista deve olhar: o guia do assunto (KB-104, erro 5xx depois do deploy) cobre a falha constante, e o relato é de erro que acontece "às vezes". É a correspondência parcial que o caso testa, e nenhum chamado interno foi aberto.

Ressalva sobre este exemplo: `fonte` e `resultado.texto` citam guias diferentes. No log (`scores_kb`), o KB-104 ficou com 0,24, e o KB-106 e o KB-110 com 0,48. `fonte` traz o de maior score (KB-106), e o texto fala do KB-104, que é o guia do assunto. Os dois estão abaixo do limiar, e o desfecho é o mesmo; quem lê só `fonte` vê um guia que o texto não menciona. O 0,48 está a dois centésimos do portão (`rag.md` §6). A expressão "o domínio do cliente", num relato que não fala de domínio, é o efeito colateral medido da regra aprendida (`memoria.md` §5.1).

### 3.3 Fora do escopo: `TKT-0004`

**Entrada** (o campo `entrada` do log):

```
Olá, quero fazer upgrade do meu plano para um servidor dedicado. Podem me passar valores e prazo de migração?
```

**Saída** (campo `saida` de `logs/grafo-40-1/TKT-0004.json`, completo):

```json
{
  "id_ticket": "TKT-0004",
  "executado_em": "2026-10-12T17:38:03-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_comercial",
    "texto": "O cliente solicitou informações sobre valores e prazo de migração para um servidor dedicado, solicitando upgrade do plano atual (Hospedagem Start).",
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
      "triagem",
      "decidir",
      "redigir",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": true,
    "motivo": "assunto comercial: a classificação dispensa a base de procedimentos"
  }
}
```

Execução de `2026-10-12T17:38:03-03:00`, commit `4aa9818`, log em `logs/grafo-40-1/TKT-0004.json` (2 chamadas ao modelo, 1.456 tokens, sem busca).

**O que ler aqui:** `resultado.acao` é `fila_comercial`, e `fonte.ferramentas` não tem `buscar_base_conhecimento`: a triagem classificou o assunto como comercial, o grafo não consultou a base de procedimentos e não tratou o pedido como defeito. A suficiência é positiva porque a classificação dispensa a base. O plano citado no texto ("Hospedagem Start") vem do registro do cliente. É o caso que não deve disparar a ação principal.

### 3.4 Entrada incompleta: `TKT-0005`

**Entrada** (o campo `entrada` do log):

```
Meu servidor não está funcionando direito.
```

**Saída** (campo `saida` de `logs/grafo-40-1/TKT-0005.json`, completo):

```json
{
  "id_ticket": "TKT-0005",
  "executado_em": "2026-10-12T17:38:07-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "devolver_cliente",
    "texto": "Para darmos andamento ao seu chamado, precisamos de mais informações:\n1. Qual serviço está com problema (site, e-mail, banco de dados, FTP/SFTP, acesso SSH, backup ou tarefa agendada)?\n2. Qual é o domínio ou o endereço afetado? Se for banco de dados, qual é o nome do banco?\n3. Qual mensagem ou código de erro aparece (por exemplo: 403, 502, \"permissão negada\")? Copie o texto como ele é exibido.\n4. Em que data e hora o problema começou? Ele acontece sempre ou só às vezes?\n5. Alguma coisa mudou pouco antes (publicação de nova versão, migração, restauração de backup, troca de senha)?",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "registro_do_chamado",
    "kb_id": null,
    "score": null,
    "registros": [
      "TKT-0005"
    ],
    "ferramentas": [
      "consultar_ticket",
      "triagem",
      "decidir",
      "redigir",
      "confirmar",
      "registrar_encaminhamento"
    ]
  },
  "suficiencia": {
    "suficiente": false,
    "motivo": "o texto do chamado não informa o serviço afetado nem o sintoma; o pedido de informação ao cliente foi registrado"
  }
}
```

Execução de `2026-10-12T17:38:07-03:00`, commit `4aa9818`, log em `logs/grafo-40-1/TKT-0005.json` (1 chamada ao modelo, 621 tokens, sem busca).

**O que ler aqui:** o texto não diz qual serviço é afetado nem qual o sintoma. `resultado.acao` é `devolver_cliente`, com suficiência negativa, e `resultado.texto` é o pedido ao cliente: o texto padrão do código (`grafo.PEDIDO_AO_CLIENTE`), com cinco perguntas, sem promessa e sem informação interna. Não é texto do modelo, e por isso a execução fez uma chamada só, a da triagem (`prompts.md` §2.2). `fonte.ferramentas` não tem busca: um relato sem serviço nem sintoma não vai à base. Nenhum chamado interno foi aberto.

Limites deste exemplo: (1) o item `confirmar` em `fonte.ferramentas` é a confirmação do analista antes do envio (H2), que aqui foi automática (`--auto-aprovar`). Sem a opção, a execução termina em `aguardando_humano`, com `resultado.acao` nulo, e o pedido só é gravado depois da aprovação (`humano.md` §2.4; execução real em `logs/grafo-pedido-padrao-h2/`). (2) "Enviar" é gravar a linha com `enviado_em`: não há canal de mensagem. (3) **A espera pela resposta do cliente não foi construída** (H3): a execução termina aqui, e a resposta seria o texto de uma execução nova do mesmo chamado (`case.md` §2.1).

### 3.5 Entrada ambígua: `TKT-0002`

O relato fala de um serviço (webmail) e o log anexado aponta a causa em outro (DNS). O sistema não escolhe sozinho entre as duas leituras.

**Entrada** (o campo `entrada` do log):

```
Meu Webmail está fora do ar desde cedo, ninguém da empresa consegue ler e-mail.
```

**Saída** (campo `saida` de `logs/grafo-40-1/TKT-0002.json`, completo):

```json
{
  "id_ticket": "TKT-0002",
  "executado_em": "2026-10-12T17:37:39-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_humana",
    "texto": "O cliente relata que o **webmail** está fora do ar desde cedo, afirmando que nenhum colaborador da empresa consegue acessar e-mails. No entanto, o log anexado mostra que o **serviço de DNS** do domínio do cliente (`zeta.com.br`) apresenta falha de resolução (`SERVFAIL`) e o nameserver `ns1.zeta.com.br` não responde (timeout). Ao acessar o webmail diretamente pelo **IP do servidor** (`203.0.113.40/webmail`), a tela de login abre normalmente, indicando que o problema está restrito à camada de resolução de nomes.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "busca_sem_correspondencia",
    "kb_id": "KB-111",
    "score": 0.47,
    "registros": [
      "TKT-0002"
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
    "suficiente": false,
    "motivo": "o melhor procedimento encontrado (KB-111, score 0.47) ficou abaixo do limiar 0.5"
  }
}
```

Execução de `2026-10-12T17:37:39-03:00`, commit `4aa9818`, log em `logs/grafo-40-1/TKT-0002.json` (2 chamadas ao modelo, 2.059 tokens, mais 1.761 tokens de embedding).

**O que ler aqui:** `resultado.acao` é `fila_humana`, com suficiência negativa, e `resultado.texto` declara as duas leituras: o cliente relata o webmail fora do ar; o log mostra falha de resolução DNS e o nameserver sem resposta. Quem marcou a divergência foi a triagem (`log_diverge: true` no log), e o nó `decidir`, que é código, mandou o chamado à fila humana com o motivo `divergencia_relato_log` (campo `desfecho_proposto` do log). Nenhum chamado interno foi aberto.

Ressalva sobre este exemplo: o motivo da divergência não está no contrato de saída. `suficiencia.motivo` diz que o melhor procedimento (KB-111, 0,47) ficou abaixo do limiar, o que é verdade e não é a razão da decisão; a razão está em `resultado.texto` e, no log, em `desfecho_proposto`. A busca aqui usa o relato (webmail), e não o log: o guia de DNS (KB-106), que no laço passava do portão com 0,67, ficou aqui com 0,45 (`scores_kb` do log).

### 3.6 Pergunta fora do corpus: `TKT-0119`

É o caso 5 do enunciado (§9): um pedido que não é comercial e não tem guia na base. O chamado é um dos 32 da ampliação do gabarito (`dados/README.md`).

**Entrada** (o campo `entrada` do log):

```
Instalem o WordPress e configurem o tema do meu site
```

**Saída** (campo `saida` de `logs/grafo-40-1/TKT-0119.json`, completo):

```json
{
  "id_ticket": "TKT-0119",
  "executado_em": "2026-10-12T17:42:41-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "fila_humana",
    "texto": "O cliente solicitou a instalação do WordPress e configuração do tema para o domínio do cliente, mas o procedimento encontrado (KB-110 - Site em laço de redirecionamentos, score 0.38) não corresponde ao caso relatado. Além disso, o procedimento possui escopo fora da cobertura do plano Hospedagem Start (desenvolvimento/correção de código do site). Não há logs ou histórico de chamados para embasar a busca. O score está abaixo do limiar de confiança (0.5), e o procedimento não aborda a solicitação do cliente.",
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "busca_sem_correspondencia",
    "kb_id": "KB-110",
    "score": 0.38,
    "registros": [
      "TKT-0119"
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
    "suficiente": false,
    "motivo": "o melhor procedimento encontrado (KB-110, score 0.38) ficou abaixo do limiar 0.5"
  }
}
```

Execução de `2026-10-12T17:42:41-03:00`, commit `4aa9818`, log em `logs/grafo-40-1/TKT-0119.json` (2 chamadas ao modelo, 1.755 tokens, mais 1.748 tokens de embedding).

**O que ler aqui:** `suficiencia.suficiente` é `false`: o guia mais próximo (KB-110, laço de redirecionamentos) ficou com score 0,38, abaixo do limiar, e o texto diz que ele não corresponde ao pedido. O sistema não respondeu pelo conhecimento do modelo nem anotou um guia qualquer: `fila_humana`, com o que foi encontrado e por que uma pessoa deve olhar. Os três campos do chamado interno ficam nulos.

Ressalva sobre este exemplo: o texto diz "para o domínio do cliente" (o cliente não falou em domínio; `memoria.md` §5.1), e a redação não tem verificador. A pergunta do conjunto do RAG ("Como instalo o WordPress no meu site?", P10) foi medida só na busca (`rag.md` §4.1); este chamado é o mesmo assunto de ponta a ponta.

### 3.7 Texto digitado e confirmação por uma pessoa: `TKT-0007`

Os seis exemplos acima vieram de uma rodada `--todos`, com o texto do banco e aprovação automática.
Este é o único com **o texto digitado na linha de comando** e com **a confirmação dada por uma
pessoa**, sem `--auto-aprovar`. São três comandos (a execução, `--pendencias` e `--aprovar`), um por processo, a partir do banco
recriado (`python src/main.py --reset`); a saída de terminal de todos está em
`logs/grafo-digitado/saida-terminal.txt`.

**Entrada** (o que foi digitado, com a grafia como está: sem acentos e com abreviação):

```bash
python src/main.py TKT-0007 "meu site nao salva mais arquivo nenhum, todo upload da erro de permissao negada. preciso voltar a publicar hj" --rodada grafo-digitado
```

**Saída na pausa** (campo `saida` de `logs/grafo-digitado/TKT-0007-pausado.json`, completo):

```json
{
  "id_ticket": "TKT-0007",
  "executado_em": "2026-10-12T19:26:41-03:00",
  "termino": "aguardando_humano",
  "resultado": {
    "acao": null,
    "texto": null,
    "chamado_interno": null,
    "time_destino": null,
    "prioridade": null
  },
  "fonte": {
    "tipo": "registro_do_chamado",
    "kb_id": "KB-102",
    "score": 0.68,
    "registros": [
      "TKT-0007"
    ],
    "ferramentas": [
      "consultar_ticket",
      "triagem",
      "buscar_base_conhecimento",
      "conferir_ressalva",
      "decidir",
      "redigir"
    ]
  },
  "suficiencia": {
    "suficiente": false,
    "motivo": "a execução terminou sem desfecho (aguardando_humano: aguardando a confirmação do analista até 2026-10-12T19:46:45-03:00 (prazo de 20 minutos))"
  }
}
```

**O que ler na pausa:** `termino` é `aguardando_humano` e `resultado` está inteiro nulo: nada foi
gravado. A suficiência é negativa porque a execução ainda não tem desfecho, e o motivo traz a hora
em que o prazo vence. `fonte` já mostra o que sustenta a ação proposta (KB-102, score 0,68). A
tela da pendência, que não faz parte do contrato de saída, mostrou a ação, o resumo redigido pelo
modelo, o time, a prioridade prevista (P2), o aviso de que o guia não cobre `ssh` e a consequência
de aprovar (`saida-terminal.txt`).

**A resposta da pessoa.** O pedido de confirmação saiu às 19:26:45, com prazo até 19:46:45. Às
19:33:47 veio a resposta, **aprovar editando**, com o resumo escrito por quem aprovou:

```bash
python src/main.py --aprovar TKT-0007 --resumo "Cliente relata falta de permissão para poder subir/editar arquivos, verificamos que user está correto. Caso escalado conforme KB-102" --rodada grafo-digitado
```

**Saída final** (campo `saida` de `logs/grafo-digitado/TKT-0007.json`, completo):

```json
{
  "id_ticket": "TKT-0007",
  "executado_em": "2026-10-12T19:26:41-03:00",
  "termino": "respondeu",
  "resultado": {
    "acao": "abrir_chamado_interno",
    "texto": "Cliente relata falta de permissão para poder subir/editar arquivos, verificamos que user está correto. Caso escalado conforme KB-102",
    "chamado_interno": "INC-0005",
    "time_destino": "Infraestrutura",
    "prioridade": "P2"
  },
  "fonte": {
    "tipo": "procedimento_da_base",
    "kb_id": "KB-102",
    "score": 0.68,
    "registros": [
      "TKT-0007"
    ],
    "ferramentas": [
      "consultar_ticket",
      "triagem",
      "buscar_base_conhecimento",
      "conferir_ressalva",
      "decidir",
      "redigir",
      "confirmar",
      "abrir_chamado_interno"
    ]
  },
  "suficiencia": {
    "suficiente": true,
    "motivo": "procedimento KB-102 com score 0.68, igual ou acima do limiar 0.5"
  }
}
```

Execução de `2026-10-12T19:26:41-03:00`, commit `15398e0`, com `ministral-8b-latest` e os prompts em
uso; logs em `logs/grafo-digitado/` (3 chamadas ao modelo, 2.438 tokens, mais 1.768 tokens de
embedding; os mesmos números na pausa e no fim, porque a retomada não chama o modelo).

**O que ler aqui:** o texto digitado, sem acentos e com "hj", chegou ao guia certo: KB-102 com
score 0,68 (o texto registrado no banco para o mesmo chamado deu 0,72 em
`logs/grafo-40-1/TKT-0007.json`). O nó `conferir_ressalva` rodou, porque o guia declara não cobrir
`ssh`, e não baixou o score: o relato não fala em SSH. `resultado.texto` é o resumo **da pessoa**,
e não o do modelo; `chamado_interno`, `time_destino` e `prioridade` (INC-0005, Infraestrutura, P2)
vieram do código, a partir do guia, e não eram editáveis. O log guarda os dois textos em
`confirmacoes` (`resumo_original` e `resumo_aprovado`). No banco: um chamado interno para o
`TKT-0007`, a pendência com status `aprovada`, nenhum encaminhamento, e um episódio com o veredito
`editado`.

Limites deste exemplo:

- **Quem respondeu é um integrante do grupo, e não um analista de suporte.** Ele leu a ação
  pendente e o resumo do modelo e escreveu o resumo corrigido. O texto do chamado foi escrito para
  a demonstração.
- **A regra do resumo editado olha só o tamanho.** A edição passa pela mesma regra do texto do
  modelo, que no resumo de um chamado interno confere o tamanho mínimo (20 caracteres,
  `_erro_do_texto` em `src/grafo.py`).
- `TKT-0007-pausado.json` é uma cópia do log feita antes da aprovação: o log final é gravado por
  cima do da pausa.
- É um chamado e uma execução. A segunda aprovação, que não duplica nada, está demonstrada em
  `logs/grafo-caso-6/` (`humano.md` §5), e não foi repetida aqui.

## 4. A entrada que não dá para atender (§1.4)

| Situação | O que o sistema faz | Exemplo real |
|---|---|---|
| **fora do escopo** | redireciona à fila comercial, sem consultar a base e sem abrir chamado | `TKT-0004`, §3.3 |
| **incompleta** | pede ao cliente o que falta (`devolver_cliente`), no máximo uma vez e depois da confirmação do analista. O pedido é um texto padrão com cinco perguntas (§3.4). A espera pela resposta não foi construída: a execução termina com o pedido gravado como enviado | `TKT-0005`, §3.4 |
| **ambígua** | não age sozinho: envia à fila humana declarando as duas leituras | `TKT-0002`, §3.5 |

A recusa por falta de base, que não é uma dessas três, está no §3.2 (`TKT-0006`, correspondência
parcial) e no §3.6 (`TKT-0119`, pedido sem guia na base).

## 5. O que falta para este item

- O contrato de entrada e o de saída estão implementados e valem nos dois caminhos.
- Os exemplos do §3 são do grafo desde 12/10/2026. Os seis primeiros vieram de uma rodada
  `--todos`, com o texto do banco e aprovação automática (`logs/grafo-40-1/`). O exemplo com o
  texto digitado na linha de comando e a confirmação dada por uma pessoa existe desde o mesmo dia
  (§3.7, `logs/grafo-digitado/`). **Falta** repeti-lo com um analista de suporte de verdade
  respondendo (quem respondeu é do grupo), e fazer o mesmo para o pedido ao cliente (H2) e para
  uma rejeição: o §3.7 é uma aprovação com edição do H1.
- O motivo da decisão nem sempre está em `suficiencia.motivo`: na divergência entre relato e log
  ele diz "score abaixo do limiar", e a razão de verdade fica no texto e no log (§3.5). E `fonte`
  pode trazer um guia diferente do que o texto cita (§3.2).
- **H3 não construído.** A confirmação do analista antes do envio do pedido existe desde
  12/10/2026 (H2). A espera pela resposta do cliente e a retomada da conversa não foram
  construídas: não há término `aguardando_cliente`, e a resposta do cliente não é entrada de
  nenhuma execução em curso (`case.md` §2.1; `humano.md` §7).

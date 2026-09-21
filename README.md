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

**O que você digita.** O id de um chamado externo do sistema simulado, no formato `TKT-` + 4 dígitos:

```bash
python src/main.py TKT-0003                 # pede a sua confirmação antes de abrir chamado interno
python src/main.py TKT-0003 --auto-aprovar  # não pergunta (só para demonstração)
python src/main.py --todos --auto-aprovar   # os 8 casos, cada um a partir do banco zerado, com verificador
python src/main.py --reset                  # recria o banco simulado
```

Os chamados disponíveis são `TKT-0001` a `TKT-0007` e o inexistente `TKT-0999` (ver [`dados/README.md`](dados/README.md)).

**O que o sistema faz.** Lê o chamado no sistema de tickets, decide se o assunto é técnico, comercial ou de informação insuficiente, consulta a base de conhecimento e dá **um desfecho** ao chamado. Quando o desfecho é abrir um chamado interno (ação irreversível), ele para e pede a confirmação do analista de suporte.

**O que ele devolve.** Uma linha por passo (ferramenta, argumentos, resultado ou erro), o motivo do término, o desfecho e o veredito do verificador. O que vale é o que foi **gravado no banco**:

| Desfecho | Significa | Onde ver |
|---|---|---|
| `abrir_chamado_interno` | chamado aberto para o time responsável, com resumo e prioridade definida pelo sistema | `python -c "import sqlite3; c=sqlite3.connect('dados/tickets.db'); print(*c.execute('select * from chamados_internos'), sep='\n')"` |
| `anotacao_interna` | correção sugerida para o analista validar e executar | tabela `encaminhamentos` |
| `fila_comercial` | assunto comercial, fora do escopo do suporte | tabela `encaminhamentos` |
| `devolver_cliente` | faltam informações; a mensagem pede o que falta | tabela `encaminhamentos` |
| `fila_humana` | o sistema não teve confiança para agir sozinho (ou o id não existe) | tabela `encaminhamentos` |

Como interpretar o término (`TERMINO:` na saída):

| Término | Significa |
|---|---|
| `respondeu` | o agente registrou um desfecho e concluiu |
| `aguardando_humano` | o analista não confirmou a abertura do chamado: nada foi gravado, e a pendência fica no log |
| `orcamento_esgotado` | passou de 8 passos, 30 mil tokens, US$ 0,05 ou 90 s; o motivo diz qual teto |
| `erro_fatal` | não há como continuar (API fora, chave inválida, modelo encerrou sem desfecho) |

**Exemplo completo, com entrada e saída reais** (execução com `ministral-8b-latest`; trecho de
`logs/saida-demonstracao.txt`; o log completo do caso está em `logs/TKT-0002.json`).

Entrada: `python src/main.py TKT-0002 --auto-aprovar`. O cliente escreveu *"Meu Webmail está fora do ar desde cedo, ninguém da empresa consegue ler e-mail"* e anexou um log de falha de DNS.

```
TKT-0002  (caso: divergencia)  modelo: ministral-8b-latest

  passo 0 [leitura ] consultar_ticket {"id_ticket": "TKT-0002"} -> ok
  passo 1 [leitura ] buscar_base_conhecimento {"termos": ["webmail fora do ar", "dns", "mail zeta"]} -> ok
  passo 2 [leitura ] buscar_base_conhecimento {"termos": ["dns fail", "servfail", "mail zeta"]} -> ok
  passo 3 [ESCRITA ] registrar_encaminhamento {"id_ticket": "TKT-0002", "destino": "fila_humana", "mensagem": "O cliente relata que o webmail está fora do a -> ok

  TERMINO: respondeu | desfecho: fila_humana | passos: 4 | chamadas ao modelo: 5 | lembretes: 0 | tokens: 9502 | custo: US$ 0.00143
  resposta: O chamado TKT-0002 foi encaminhado para a fila humana, pois o relato do cliente diverge do que mostra o log anexado.
  VERIFICADOR: OK
```

Como ler: o agente consultou o chamado (passo 0), buscou na base duas vezes (passos 1 e 2), viu que o log aponta DNS enquanto o cliente fala de Webmail, e **não agiu sozinho**: registrou o encaminhamento à fila humana, sinalizando a divergência (passo 3, uma escrita reversível). `TERMINO: respondeu` quer dizer que registrou um desfecho; `VERIFICADOR: OK` que o desfecho gravado no banco é o que o analista humano daria. O custo é o simulado a preço de lista; no plano gratuito o gasto real é zero.

**O que ele não faz.** Não executa correções, não encerra chamados, não altera prioridade (só o gestor reclassifica) e não responde diretamente ao cliente além das mensagens de `devolver_cliente`. A base de conhecimento é uma busca por palavras-chave (Parte 1): ela não entende sinônimos, e é a razão de alguns chamados ficarem na `fila_humana` mesmo com procedimento existente.

**Quando ele não sabe.** Não chuta: o score da base abaixo de 0,5, um id inexistente ou um assunto ambíguo terminam em `fila_humana`, com uma mensagem que diz o que foi encontrado e por que um humano deve olhar.

## Estrutura

```
src/         agente.py (laço, estado, orçamento) · ferramentas.py · db.py (SQLite) · verificar.py
             main.py · comparar_modelos.py (item 3.3)
prompts/     agente-v1.md  (técnica, contrato e o que cada regra impede)
dados/       seed.sql · gabarito.json · README.md (casos difíceis nomeados)
tests/       testes offline (sem chave)
docs/        case.md · modelos.md · arquitetura-v1.md · arquitetura-v2.md · fontes.md
logs/        trajetória de cada execução demonstrada (JSON)
```

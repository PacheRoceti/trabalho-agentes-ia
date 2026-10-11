# RAG como memória consultável (Parte 2, item 4)

> **Estado deste documento: versão inicial, de 10/10/2026.** Descreve a recuperação que existe
> hoje (consulta estruturada em SQLite e busca por palavra-chave) e mede as dez perguntas contra
> ela. **Não há busca vetorial, nem documento revogado no corpus, nem índice.** O que está marcado
> como **PROPOSTA** ainda não foi decidido pelo grupo nem implementado. O que falta está no §6.
>
> O desenho da base (fontes, donos, o que entra no índice, curadoria) já está em
> [`base-de-conhecimento-v2.md`](base-de-conhecimento-v2.md); este documento não o repete.

## 1. As formas de recuperar (§4.1)

**A pergunta direta: o RAG é vetorial ou é banco de dados?** Hoje é banco de dados e busca por
palavra-chave; não há vetor. O desenho da Parte 2 é "os dois": consulta estruturada para o que é
registro, busca vetorial para o que é assunto.

### 1.1 A classificação

Vem das dez perguntas do §3. Resultado: 5 de assunto (uma delas sem resposta no corpus), 3 de
registro, 1 de termo e 1 de relação. Nenhuma de agregação.

### 1.2 As formas que o sistema usa

| Forma usada | Com o quê | O que ela responde no case | Situação |
|---|---|---|---|
| **consulta estruturada** | SQLite (`sqlite3`, biblioteca padrão), em `src/db.py`: `buscar_ticket`, `_reincidencia`, `buscar_artigo`, `contar_pedidos_cliente` | as 3 perguntas de registro (P3, P4, P5): histórico e reincidência do cliente, plano, time e prioridade de um procedimento | implementada |
| **busca textual** (palavra-chave) | `buscar_kb`, em `src/db.py`: sobreposição de palavras entre os termos e a coluna `palavras_chave` de `kb_artigos`, com radical de 4 letras, lista de sinônimos e ressalvas | hoje responde também as perguntas de **assunto**, que não são dela. É a causa das falhas registradas em `modelos.md` §3.3-B | implementada; serve à pergunta de termo (P8) |
| **busca vetorial** | **PROPOSTA:** lista de embeddings em memória, sem banco vetorial (são ~23 trechos previstos, `base-de-conhecimento-v2.md` §3). Modelo de embedding e número de dimensões **a definir** | as 5 perguntas de assunto (P1, P2, P6, P7, P10) | não implementada |

**Formas que o case não usa.** Grafo: a única pergunta de relação (P9, "que guia substitui
este?") é resolvida por uma coluna (`revogado_por`), e um `JOIN` basta. Agregação: nenhuma das
perguntas pede.

## 2. O corpus (§4.2)

| O que entra | De onde vem | Quem mantém | Com que frequência muda | Hoje no repositório |
|---|---|---|---|---|
| Procedimentos técnicos (fonte D) | wiki interna de Infraestrutura (fictícia) | Infraestrutura e Segurança; time e prioridade revisados pela Coordenação de Suporte | mensal, e a cada troca de versão de um serviço | `dados/seed.sql`, tabela `kb_artigos`: 6 guias (KB-101 a KB-106) |
| Catálogo de planos (fonte E) | página de planos e anexo de suporte (fictícios) | Comercial e Suporte | cerca de 2 vezes por ano | não existe; só o nome do plano em `clientes.plano` |

**O índice pode ser construído uma vez?** Não. A fonte D muda todo mês, então o índice é
reconstruído a cada revisão. Com ~23 trechos, reconstruir tudo custa pouco, e não há atualização
parcial a manter.

Fica fora do corpus o que é registro (chamados, histórico), regra aplicada em código (SLA,
reincidência) e lista de referência (times). A razão de cada um está em
`base-de-conhecimento-v2.md` §3.

### 2.1 O documento revogado

**Não está no corpus ainda.** A proposta já escrita (`base-de-conhecimento-v2.md` §4) é incluir o
`KB-101-A`, a versão antiga do guia de SSL: manda renovar o certificado manualmente pelo painel e
declara `escalar`, `Seguranca`, `P1`, com `revogado_por = KB-101`. O guia vigente (KB-101) diz
`anotar`, `Infraestrutura`, `P2`.

O que se espera encontrar, e que precisa ser medido: os dois guias respondem ao mesmo relato (P1
do §3), e a busca não tem como saber qual vale. Como o time e a prioridade vêm do documento, o
erro não fica no texto: vira um chamado P1 aberto para o time errado. A correção prevista é de
curadoria, e não de recuperação: filtrar `revogado_por` preenchido antes da busca
(`memoria.md` §2.1).

Hoje a tabela `kb_artigos` não tem as colunas `data_publicacao` nem `revogado_por`.

## 3. As dez perguntas (§4.3)

São perguntas que o sistema precisa responder para dar um desfecho a um chamado. As de assunto
estão escritas como o cliente escreve.

| # | Pergunta | Forma | Trecho do corpus que responde | Depende de exceção? |
|---|---|---|---|---|
| P1 | "O certificado SSL do meu site venceu e a renovação automática não rodou." | assunto | KB-101 | |
| P2 | "Todo upload do meu site falha com permissão negada, não consigo salvar arquivos." | assunto | KB-102 | |
| P3 | Este cliente já teve chamado interno desta categoria nos últimos 30 dias? | registro | `chamados_internos` (cliente, categoria, data) | |
| P4 | Qual é o plano do cliente que abriu o chamado? | registro | `clientes.plano` | |
| P5 | Para qual time vai uma falha de DNS, e com que prioridade? | registro | `kb_artigos`, KB-106: `time_destino`, `prioridade_base` | |
| P6 | "Meu site dá erro 502 de vez em quando desde o deploy de ontem." | assunto | KB-104, coluna `nao_cobre` | **sim**: o guia cobre a falha constante e declara que não cobre a intermitente |
| P7 | "Recebo permissão negada quando tento entrar por SSH no servidor." | assunto | KB-103; e KB-102, coluna `nao_cobre` | **sim**: "permissão negada" é o sintoma do KB-102, que declara não cobrir SSH |
| P8 | Em que procedimento aparece "fail2ban"? | termo | KB-103 | |
| P9 | Que guia substitui a versão antiga do procedimento de SSL? | relação | `revogado_por` do `KB-101-A` | |
| P10 | "Como instalo o WordPress no meu site?" | assunto | **nenhum**: não está no corpus | |

A P10 é a que exercita a recusa do contrato de saída: sem procedimento, o desfecho é
`fila_humana`, com suficiência negativa (`io.md` §2).

### 3.1 Resultado de hoje

Medido em 10/10/2026, com o seed atual, chamando a função de recuperação diretamente. Nas
perguntas de assunto e de termo, a pergunta inteira foi passada como termo de `buscar_kb`; no
sistema, quem escolhe os termos é o modelo, e o score muda com a escolha. O limiar para agir é
0,5.

| # | O que a recuperação devolveu | Certo? |
|---|---|---|
| P1 | KB-101, score 0,80 | sim |
| P2 | KB-102, score 0,77 | sim |
| P3 | resposta exata, por `_reincidencia` | sim |
| P4 | resposta exata, por `buscar_ticket` | sim |
| P5 | resposta exata, por `buscar_artigo`: Infraestrutura, P1 | sim |
| P6 | KB-104, score 0,23, com a ressalva "de vez em quando" | sim: abaixo do limiar, o sistema não age |
| P7 | KB-102 com 0,18 (ressalva "ssh") e KB-103 com 0,10 | **parcial**: o guia errado foi barrado, mas o certo (KB-103) não passou do limiar |
| P8 | KB-103, score 0,40 | o guia certo; o score é baixo porque um termo só nunca passa de 0,4, por regra |
| P9 | sem resposta | **não**: a coluna `revogado_por` não existe |
| P10 | nenhum procedimento | sim: é a recusa esperada |

O achado é a P7. A busca por palavra não casa "entrar por SSH" com "acesso SSH bloqueado ou
recusado": só a palavra "ssh" coincide, e um termo só não autoriza agir. É uma pergunta de
assunto respondida por uma busca de termo.

## 4. O corte e o `k` (§4.3)

**Hoje não há corte nem `k` de busca vetorial**, porque não há busca vetorial. Cada procedimento
é uma linha de tabela, e `buscar_kb` devolve no máximo 3 artigos (`top=3`, em `src/db.py`).

**PROPOSTA, para quando a busca vetorial existir:**

- **Corte por estrutura: um trecho por guia.** Os guias têm template fixo (sintoma, causa,
  solução) e raramente passam de meia página. Um guia com subcenários é cortado por subcenário,
  repetindo o sintoma no início. Ação padrão, categoria, time e prioridade ficam como metadados,
  fora do texto embedado (`base-de-conhecimento-v2.md` §4).
- **`k` = 3.** É o valor de hoje. Cada artigo ocupa de 110 a 150 tokens (`memoria.md` §1.2), e
  três cabem no teto de 500 tokens reservado a trechos recuperados. O valor precisa ser
  confirmado com as dez perguntas: se a resposta certa estiver sempre na primeira posição, `k`
  pode cair para 1.

## 5. Onde a recuperação entra no laço (§4.4)

**A escolha: etapa fixa, condicionada à rota.** No grafo, que é o caminho padrão, a busca é um
nó executado só quando a triagem classifica o chamado como técnico. O modelo não decide na hora
se busca; ele escolhe a classe e os termos. As medições do grafo estão no fim desta seção.

**No laço da Parte 1 (`--laco`) a recuperação é ferramenta do agente**
(`buscar_base_conhecimento`): o modelo decide se busca e com que termos. É dele a medição que
levou à escolha.

Chamadas de recuperação por execução, nas 24 execuções das três rodadas com o `agente-v5.md`
(`logs/rodada-1-prompt-v5/`, `logs/rodada-2-prompt-v5/`, `logs/rodada-3-prompt-v5/`). As rodadas
1 e 2 são do seed anterior à troca do KB-102; a rodada 3 (10/10/2026, commit
`2ffb2b5 + alterações locais`) é a do seed e do texto atuais.

| | Rodada 1 | Rodada 2 | Rodada 3 |
|---|---|---|---|
| Buscas no total (8 execuções) | 8 | 6 | 5 |
| Média por execução | 1,0 | 0,75 | 0,63 |
| Execuções sem nenhuma busca | 2 | 3 | 3 |
| Buscas repetidas na mesma execução | 2 | 1 | 0 |

**Rodadas 1 e 2.** O modelo decidiu errado em 3 das 16 execuções:

- buscou sem precisar no `TKT-0005` (informação insuficiente), duas vezes em cada rodada: 4
  buscas inúteis, e o chamado foi para a fila humana em vez de voltar ao cliente;
- deixou de buscar no `TKT-0003` da rodada 2, e o chamado que devia ser aberto não foi.

**Rodada 3.** Nenhuma busca inútil e nenhuma repetida. As três execuções sem busca são as que
não têm o que buscar: `TKT-0004` (comercial), `TKT-0005` (insuficiente) e `TKT-0999` (id
inexistente). As cinco com busca fizeram uma só:

| Chamado | Termos escolhidos pelo modelo | Melhor artigo e score | Desfecho | Verificador |
|---|---|---|---|---|
| `TKT-0001` | certificado, ssl, venceu, renovacao, automatica | KB-101, 0,89 | `anotacao_interna` | OK |
| `TKT-0003` | upload, falhou, permissao, negada | KB-102, 0,86 | `abrir_chamado_interno` | OK |
| `TKT-0007` | site, parou, salvar, arquivos, upload, falha, permissão, negada | KB-102, 0,83 | `abrir_chamado_interno` | OK |
| `TKT-0006` | site, erro, 502, deploy | KB-104, 0,40 (com ressalva) | `fila_humana` | OK |
| `TKT-0002` | "webmail fora do ar", "dns falha resolução", "nameserver não responde" | KB-106, 0,67 | `abrir_chamado_interno` | **FALHOU** |

Dois pontos sobre o `TKT-0002`, a única falha da rodada:

- **O modelo tentou encerrar sem buscar**, com uma `fila_humana` que sinalizava a divergência
  entre o relato e o log. O código recusou (fila humana para chamado existente exige uma busca
  antes), e a busca só aconteceu por isso.
- **A recuperação funcionou e o desfecho saiu errado.** O KB-106 é o procedimento certo para o
  que o log mostra (falha de DNS), e o score passou do limiar. O erro não é de recuperação: é o
  uso de um procedimento bem recuperado num chamado em que o cliente relata outro serviço. Com o
  artigo na mão, o modelo abriu um chamado P1 que não devia existir. Um score alto não diz que o
  procedimento se aplica ao chamado.

No `TKT-0007` o modelo mandou 8 termos, e no `TKT-0002` mandou frases; o schema da ferramenta
pede de 2 a 5 palavras. A busca quebra frases em palavras, e o score ficou acima do limiar nos
dois casos.

**Se fosse etapa fixa**, seriam 8 buscas por rodada, e 3 delas inúteis: o `TKT-0004`
(comercial), o `TKT-0005` (insuficiente) e o `TKT-0999` (id inexistente) não têm o que buscar.
Na rodada 3 o modelo acertou sozinho essas três.

**No grafo (`src/grafo.py`):** a busca é um nó executado só na rota "técnico", decidida pela
triagem (`grafo.md` §1). É uma **etapa fixa condicionada à rota**: não roda em toda execução, e
o modelo não decide na hora se busca. Ele ainda escolhe os termos, na triagem, e o nó `decidir`
confere a divergência entre relato e log antes de olhar o score.

Chamadas de recuperação nas três rodadas medidas do grafo (`logs/grafo/`,
`logs/grafo-rodada-2/` e `logs/grafo-rodada-3/`, de 10/10/2026, 8 de 8 no verificador nas três;
`grafo.md` §6). Os números são iguais nas três:

| | Cada rodada do grafo |
|---|---|
| Buscas no total (8 execuções) | 5 |
| Média por execução | 0,63 |
| Execuções sem nenhuma busca | 3 (`TKT-0004`, `TKT-0005`, `TKT-0999`) |
| Buscas repetidas na mesma execução | 0 (o grafo não tem caminho de volta para a busca) |
| Buscas inúteis | 0 |

A tabela seguinte é a da primeira rodada. Nas outras duas os termos mudaram pouco e os scores
ficaram do mesmo lado do limiar: KB-101 com 0,67 e 0,75, KB-106 com 0,67 e 0,75, KB-102 com 0,86
e KB-104 com 0,16.

| Chamado | Termos escolhidos pela triagem | Melhor artigo e score | Desfecho | Verificador |
|---|---|---|---|---|
| `TKT-0001` | "certificado ssl", "renovação automática", navegador, "site não seguro" | KB-101, 0,67 | `anotacao_interna` | OK |
| `TKT-0002` | "webmail fora ar", "resolucao dns", "nameserver nao responde" | KB-106, 0,75 | `fila_humana` | OK |
| `TKT-0003` | upload, falham, permissão, negada | KB-102, 0,86 | `abrir_chamado_interno` | OK |
| `TKT-0006` | site, "erro 502" | KB-104, 0,16 | `fila_humana` | OK |
| `TKT-0007` | site, parou, salvar, arquivos, permissão | KB-102, 0,86 | `abrir_chamado_interno` | OK |

São os mesmos números de buscas da rodada 3 do laço. A diferença está no `TKT-0002`: o artigo
foi recuperado com score ainda maior (0,75), e o chamado não foi aberto, porque a divergência já
estava decidida quando a busca voltou. Nenhuma das cinco buscas foi inútil no sentido do
enunciado: todas são de chamados técnicos, e as três execuções sem busca são as que não têm o
que buscar. Limite: são três execuções dos mesmos 8 casos.

A defesa da escolha começa na medição das rodadas 1 e 2 do laço:
as buscas inúteis e a busca que faltou são todas erro de decisão do modelo. A rodada 3 enfraquece
essa defesa pela metade: com o seed e o texto atuais, o modelo decidiu certo quando buscar em 7
das 8 execuções, e na oitava quem forçou a busca foi o código. O que a rodada 3 acrescenta é
outro argumento: o `TKT-0002` precisa que a divergência entre relato e log seja decidida
**antes** de o resultado da busca chegar ao modelo, e não depois. Nas três rodadas do grafo foi
o que aconteceu. O preço da etapa fixa é o que o laço tinha e o grafo não tem: uma segunda
busca com outros termos quando a primeira vem fraca.

## 6. O que falta para este item

- Decidir e implementar a busca vetorial: modelo de embedding, dimensões, onde a lista fica.
- Acrescentar as colunas `data_publicacao`, `revogado_por` e `planos` a `kb_artigos`.
- Incluir o `KB-101-A` no corpus, medir a P1 com ele e reportar o que aconteceu, antes e depois
  do filtro de revogados.
- Escrever as fichas de plano (fonte E), se entrarem no corpus.
- Medir as dez perguntas com a busca vetorial e comparar com o §3.1, em especial a P7.
- Calibrar o limiar com perguntas sem resposta na base, no lugar do 0,5 ajustado à mão.
- Confirmar o `k`.
- Medir o §5 em perguntas fora dos 8 casos: as três rodadas do grafo são dos mesmos chamados.
- Ligar a recuperação à fonte do contrato de saída (`fonte.kb_id` e `fonte.score`, em
  `src/saida.py`) quando o score passar a ser de similaridade.

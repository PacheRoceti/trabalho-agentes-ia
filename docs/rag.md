# RAG como memória consultável (Parte 2, item 4)

> **Estado deste documento: atualizado em 11/10/2026, depois de o corpus passar de 7 para 16 guias
> e de as medições do §4 serem refeitas.** A recuperação usa **duas formas**:
> consulta estruturada em SQLite para o que é registro e, para o que é assunto, **busca vetorial**
> (`mistral-embed`), com um nó em que o modelo lê as ressalvas do guia (§4). O documento revogado
> está no corpus desde 11/10/2026, medido com e sem as duas regras de curadoria (§2.1). As
> medições estão no §4.2 e no §4.3. O que falta está no §6.
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
| **busca textual** (palavra-chave) | `buscar_kb`, em `src/db.py`: sobreposição de palavras entre os termos e a coluna `palavras_chave` de `kb_artigos`, com radical de 4 letras, lista de sinônimos e ressalvas | responde a pergunta de termo (P8) e entra na fusão da híbrida. Sozinha, respondia também as de **assunto**, que não são dela, e é a causa das falhas registradas em `modelos.md` §3.3-B | implementada; segue sendo a busca do laço da Parte 1 |
| **busca vetorial** | `src/vetorial.py`: `mistral-embed`, **1024 dimensões**, lista de vetores em memória guardada na tabela `kb_vetores` do SQLite, sem banco vetorial (7 guias hoje; ~23 trechos previstos, `base-de-conhecimento-v2.md` §3). Só vetorial; a híbrida foi medida e descartada (§4.1) | as 5 perguntas de assunto (P1, P2, P6, P7, P10) | implementada em 11/10/2026 |

**Formas que o case não usa.** Grafo: a única pergunta de relação (P9, "que guia substitui
este?") é resolvida por uma coluna (`revogado_por`), e um `JOIN` basta. Agregação: nenhuma das
perguntas pede.

## 2. O corpus (§4.2)

| O que entra | De onde vem | Quem mantém | Com que frequência muda | Hoje no repositório |
|---|---|---|---|---|
| Procedimentos técnicos (fonte D) | wiki interna de Infraestrutura (fictícia) | Infraestrutura e Segurança; time e prioridade revisados pela Coordenação de Suporte | mensal, e a cada troca de versão de um serviço | `dados/seed.sql`, tabela `kb_artigos`: 15 guias vigentes (KB-101-A e KB-102 a KB-115) e 1 revogado, posto de propósito (KB-101, §2.1). Os KB-107 a KB-115 entraram em 11/10/2026 |
| Catálogo de planos (fonte E) | página de planos e anexo de suporte (fictícios) | Comercial e Suporte | cerca de 2 vezes por ano | `dados/seed.sql`, tabela `planos_fichas`: 3 fichas (Start, Business, VPS Pro), desde 11/10/2026 |

**O índice pode ser construído uma vez?** Não. A fonte D muda todo mês, então o índice é
reconstruído a cada revisão. Com ~23 trechos, reconstruir tudo custa pouco, e não há atualização
parcial a manter.

Fica fora do corpus o que é registro (chamados, histórico), regra aplicada em código (SLA,
reincidência) e lista de referência (times). A razão de cada um está em
`base-de-conhecimento-v2.md` §3.

### 2.1 O documento revogado, e as versões de um procedimento

**Como a base nomeia as versões.** O guia com letra é uma atualização do guia sem letra:
`KB-101` é a primeira versão, `KB-101-A` a seguinte, `KB-101-B` a outra, e quanto mais adiante
no alfabeto, mais nova. O id sem a letra identifica o procedimento. A tabela `kb_artigos` tem
as colunas `data_publicacao` e `revogado_por`. As datas são fictícias, como o resto dos dados.

**O documento revogado está no corpus desde 11/10/2026**, em `dados/seed.sql`: o `KB-101`, a
versão antiga do guia de SSL, anterior ao certbot. O guia vigente é o `KB-101-A`. Até essa data
o guia vigente tinha o id `KB-101`, e é assim que ele aparece nos logs anteriores; o texto dele
não mudou.

| | KB-101 (antigo, revogado) | KB-101-A (vigente) |
|---|---|---|
| Título | Certificado SSL vencido: renovação manual pelo painel | Certificado SSL não renovou automaticamente |
| Solução | emitir e instalar um novo certificado pelo painel | conferir DNS e porta 80, rodar `certbot renew --dry-run` |
| `acao_padrao` | `escalar` | `anotar` |
| `time_destino` | `Seguranca` | `Infraestrutura` |
| `prioridade_base` | P1 | P2 |
| `data_publicacao` | 2025-03-10 | 2026-02-02 |
| `revogado_por` | `KB-101-A` | vazio |

Os dois respondem à P1 do §3, que é o relato do `TKT-0001`.

**A curadoria tem duas regras, em código, aplicadas antes do score** (`db.buscar_kb`):

1. **Filtro de revogados.** Guia com `revogado_por` preenchido não entra na busca
   (`FILTRAR_REVOGADOS`).
2. **Desempate por data.** Das versões de um mesmo procedimento, só a de maior
   `data_publicacao` entra (`DESEMPATAR_POR_DATA`). A letra decide apenas entre duas versões
   publicadas no mesmo dia. É a regra que segura a versão antiga que ninguém marcou como
   revogada. A versão superada sai mesmo quando a nova não casa com a consulta.

O descarte pelo desempate fica registrado: o guia que ficou volta da busca com
`data_publicacao` e `versoes_descartadas` (as antigas que também casavam), e isso vai para o
log. Guias de procedimentos diferentes não são desempatados por data: concorrem pelo score.
Como o portão de confiança só aceita `kb_id` vindo de uma busca da execução, uma versão
descartada também não pode ser usada numa escrita.

**O que foi medido.** Quatro rodadas dos 8 casos pelo grafo, em 11/10/2026, com
`ministral-8b-latest` e `--auto-aprovar`, uma para cada combinação das duas regras. Commit
`6b5fb31 + alterações locais`: o seed, as regras e os testes ainda não estavam commitados.

| Rodada (`logs/`) | Filtro de revogados | Desempate por data | Resultado | `TKT-0001`: guias devolvidos | `TKT-0001`: desfecho |
|---|---|---|---|---|---|
| `grafo-versoes-sem-curadoria/` | desligado | desligado | **7 de 8** | KB-101 (0,60) e KB-101-A (0,60) | chamado `INC-0002`, Segurança, P1: **FALHOU** |
| `grafo-versoes-so-desempate/` | desligado | ligado | 8 de 8 | KB-101-A (0,67), com o KB-101 em `versoes_descartadas` | `anotacao_interna`: OK |
| `grafo-versoes-so-filtro/` | ligado | desligado | 8 de 8 | KB-101-A (0,75) | `anotacao_interna`: OK |
| `grafo-versoes-curadoria/` (o padrão) | ligado | ligado | 8 de 8 | KB-101-A (0,75) | `anotacao_interna`: OK |

Os scores diferem entre as rodadas porque a triagem escolheu termos um pouco diferentes em
cada uma, e não por causa das regras. Os outros sete casos deram o mesmo desfecho nas quatro.

**O que acontece sem curadoria** (primeira linha da tabela; as regras são desligadas com
`--sem-filtro-revogados --sem-desempate-data`, e a busca não diz qual versão vale):

- **A busca devolveu as duas versões com o mesmo score, 0,60.** Os termos da triagem
  ("certificado ssl", "renovação automática", navegador, "aviso site não seguro") casam com as
  mesmas palavras-chave nas duas. Nada na busca diz qual vale.
- **O desempate foi a ordem das linhas na tabela.** O `KB-101` veio primeiro porque foi
  inserido primeiro (é o mais antigo). O nó `decidir` usou o primeiro da lista.
- **O erro não ficou no texto.** O `TKT-0001` devia receber uma anotação para o analista
  (`anotacao_interna`, KB-101-A). Recebeu o chamado interno `INC-0002`, para a **Segurança**,
  com prioridade **P1**. O verificador registrou: "desfecho 'abrir_chamado_interno' em vez de
  'anotacao_interna'; kb_id 'KB-101' em vez de 'KB-101-A'; 1 chamado(s) interno(s) gravado(s)".
- **O modelo redigiu o resumo a partir do guia antigo**, sem estranhar: "o certificado foi
  emitido manualmente (validade de 1 ano), sem renovação automática", quando o cliente tinha
  escrito que a renovação automática não rodou.
- **A única barreira que sobrou foi o analista.** A abertura de chamado passa pelo H1
  (`humano.md`), e nesta rodada ela foi aprovada pelo `--auto-aprovar`. A tela da pausa mostra
  o time e a prioridade, mas não diz que existe uma versão mais nova do guia.

**O achado.** Sem curadoria, o sistema não tem como saber que o `KB-101` não vale mais. O score
é igual, o texto é plausível, e o modelo não recebe a data nem a revogação. Trocar a técnica de
recuperação não resolveria: os dois guias falam do mesmo assunto, e é de se esperar que uma
busca vetorial ache os dois (não medido, porque não há busca vetorial).

**O que cada regra resolve.** Qualquer uma das duas, sozinha, bastou para o `TKT-0001`. Elas
cobrem falhas diferentes de quem mantém o corpus. O filtro depende de alguém preencher
`revogado_por` ao publicar a versão nova. O desempate depende de a versão nova seguir a
convenção do id (mesmo número, letra seguinte) e ter a data certa. Na rodada só com o
desempate, o log da busca mostra as duas versões e a data que venceu:
`"versoes_descartadas": [{"kb_id": "KB-101", "data_publicacao": "2025-03-10"}]`.

**Limites.**

- Uma execução de cada combinação.
- Sem curadoria, o empate foi resolvido pela ordem de inserção, que nós escolhemos (o guia
  antigo antes do novo, na ordem de publicação). Com a ordem contrária, o KB-101-A viria
  primeiro e o `TKT-0001` passaria sem que ninguém notasse o guia antigo no segundo lugar. O
  defeito seria o mesmo.
- As duas regras dependem de metadado correto. Uma versão nova publicada com outro número
  (`KB-107` no lugar de `KB-101-B`) e sem `revogado_por` na antiga escapa das duas, e volta a
  ser o caso "sem curadoria".
- A data vence a letra. Se alguém publicar o `KB-101-B` com data anterior à do `KB-101-A`, vale
  o `KB-101-A`, e nada avisa da incoerência no banco em uso. No seed, um teste confere que
  letra e data concordam.
- Quando a versão nova não casa com a consulta e a antiga casaria, a antiga é descartada e o
  descarte não aparece no resultado: `versoes_descartadas` só acompanha um guia devolvido.
- Na rodada só com o filtro, a anotação do `TKT-0001` citou dois domínios que não estão no
  chamado ("acmecontabilidade.com.br" e "hospedagem.acmecontabilidade.com.br"). O verificador
  não confere isso, e o caso consta como OK. Não tem relação com as versões; fica registrado.

Onze testes offline cobrem o que é do código: o filtro sozinho, o empate sem curadoria, o
desempate segurando a versão que ninguém revogou, a data vencendo a letra, a versão superada
que não age, procedimentos diferentes sem desempate, a coerência das versões do seed, o portão
recusando o `kb_id` antigo, o `TKT-0001` virando chamado P1 sem curadoria, cada regra bastando
sozinha e o descarte no log (`tests/test_offline.py`, `tests/test_grafo.py`).

## 3. As dez perguntas (§4.3)

São perguntas que o sistema precisa responder para dar um desfecho a um chamado. As de assunto
estão escritas como o cliente escreve.

| # | Pergunta | Forma | Trecho do corpus que responde | Depende de exceção? |
|---|---|---|---|---|
| P1 | "O certificado SSL do meu site venceu e a renovação automática não rodou." | assunto | KB-101-A | |
| P2 | "Todo upload do meu site falha com permissão negada, não consigo salvar arquivos." | assunto | KB-102 | |
| P3 | Este cliente já teve chamado interno desta categoria nos últimos 30 dias? | registro | `chamados_internos` (cliente, categoria, data) | |
| P4 | Qual é o plano do cliente que abriu o chamado? | registro | `clientes.plano` | |
| P5 | Para qual time vai uma falha de DNS, e com que prioridade? | registro | `kb_artigos`, KB-106: `time_destino`, `prioridade_base` | |
| P6 | "Meu site dá erro 502 de vez em quando desde o deploy de ontem." | assunto | KB-104, coluna `nao_cobre` | **sim**: o guia cobre a falha constante e declara que não cobre a intermitente |
| P7 | "Recebo permissão negada quando tento entrar por SSH no servidor." | assunto | KB-103; e KB-102, coluna `nao_cobre` | **sim**: "permissão negada" é o sintoma do KB-102, que declara não cobrir SSH |
| P8 | Em que procedimento aparece "fail2ban"? | termo | KB-103 | |
| P9 | Que guia substitui a versão antiga do procedimento de SSL? | relação | `revogado_por` do `KB-101` | |
| P10 | "Como instalo o WordPress no meu site?" | assunto | **nenhum**: não está no corpus | |

A P10 é a que exercita a recusa do contrato de saída: sem procedimento, o desfecho é
`fila_humana`, com suficiência negativa (`io.md` §2).

### 3.1 Resultado de hoje

Medido em 10/10/2026, chamando a função de recuperação diretamente, **com a busca por palavra** (a busca vetorial, nas mesmas perguntas, está no §4.3). A P1 e a P9 foram medidas
de novo em 11/10/2026, com as duas versões do guia de SSL no corpus e a curadoria ligada. Nas
perguntas de assunto e de termo, a pergunta inteira foi passada como termo de `buscar_kb`; no
sistema, quem escolhe os termos é o modelo, e o score muda com a escolha. O limiar para agir é
0,5.

| # | O que a recuperação devolveu | Certo? |
|---|---|---|
| P1 | KB-101-A, score 0,80 | sim |
| P2 | KB-102, score 0,77 | sim |
| P3 | resposta exata, por `_reincidencia` | sim |
| P4 | resposta exata, por `buscar_ticket` | sim |
| P5 | resposta exata, por `buscar_artigo`: Infraestrutura, P1 | sim |
| P6 | KB-104, score 0,23, com a ressalva "de vez em quando" | sim: abaixo do limiar, o sistema não age |
| P7 | KB-102 com 0,18 (ressalva "ssh") e KB-103 com 0,10 | **parcial**: o guia errado foi barrado, mas o certo (KB-103) não passou do limiar |
| P8 | KB-103, score 0,40 | o guia certo; o score é baixo porque um termo só nunca passa de 0,4, por regra |
| P9 | KB-101-A, por `buscar_artigo("KB-101")`, campo `revogado_por` | sim (em 10/10/2026 não havia resposta: a coluna não existia) |
| P10 | nenhum procedimento | sim: é a recusa esperada |

O achado é a P7. A busca por palavra não casa "entrar por SSH" com "acesso SSH bloqueado ou
recusado": só a palavra "ssh" coincide, e um termo só não autoriza agir. É uma pergunta de
assunto respondida por uma busca de termo.

## 4. A busca vetorial e a híbrida, o corte e o `k` (§4.3)

Implementada em `src/vetorial.py` e usada pelo grafo (`grafo.BUSCA = "vetorial"`, o padrão).
`main.py --busca palavra --rodada NOME` volta à busca da Parte 1, só para medir. O laço da
Parte 1 (`--laco`) continua buscando por palavra.

### 4.1 O modelo, o índice e a estratégia

| | Escolha | Por quê, e o que custa |
|---|---|---|
| Modelo de embedding | `mistral-embed`, 1024 dimensões | Mesma conta, mesma chave e mesmo `LLM_BASE_URL` do modelo de chat: nenhuma dependência nova. O custo é a rede: limite de 60 requisições por minuto no plano gratuito, e os vetores mudam se o provedor trocar o modelo (a tabela guarda o nome do modelo e refaz o vetor se ele mudar). |
| Índice | lista de vetores em memória, guardada na tabela `kb_vetores` do SQLite (um vetor por guia, com o hash do texto) | Sem banco vetorial: são 16 guias (contando o revogado) e 3 fichas. O vetor de um guia só é refeito quando o texto dele muda. Os revogados entram no índice, para a medição sem curadoria. |
| O que é embedado | título + causa + solução, um trecho por guia | Ação, time, prioridade e palavras-chave ficam fora: são metadados. |
| A consulta | o **relato do cliente**, inteiro | O vetor foi feito para frases. Os termos da triagem alimentam só o recuo para a busca por palavra e a ressalva literal. |
| Estratégia | **só vetorial**: o cosseno do relato com cada guia | A **híbrida** (o mesmo ranking fundido por posição, RRF, `K_RRF = 60`, com o da busca por palavra) foi implementada e medida: deu o mesmo primeiro lugar do só vetorial em todas as perguntas, no corpus de 7 e no de 16 guias (§4.3), e o mesmo melhor guia, com o mesmo score, nos 5 casos do grafo que buscam no corpus de 7 (`logs/grafo-rag/` híbrida; `logs/grafo-ressalva/` só vetorial). Saiu do caminho do grafo porque não rendeu nada e tem uma falha vista: a fusão pode promover um guia de cosseno pior (com termos errados, o KB-101-A com 0,733 passou o KB-104 com 0,817). O modo continua em `vetorial.buscar(modo="hibrida")`, só para medir. |
| Score do portão | o cosseno do guia, numa escala linear em que `LIMIAR_COSSENO = 0,80` vale 0,5 (1,0 vale 1,0; 0,6 vale 0) | Assim o portão continua em 0,5 e nada fora de `vetorial.py` muda. A escala é só uma conversão: o que importa é o limiar do cosseno. |
| Curadoria | as duas regras do §2.1 valem **antes** do ranking | O vetor acha as duas versões do guia de SSL (§4.3), e a ordem entre elas ficaria por conta do cosseno. |
| Ressalvas (`nao_cobre`) | a frase literal no relato baixa o score em código; a paráfrase é lida pelo **modelo**, no nó `conferir_ressalva` (§4.2) | O vetor não enxerga a exceção (§4.2). |
| Recuo | se o embedding falhar (rede, cota, chave), a busca é a por palavra, e cada resultado traz `busca: "palavra"` e `aviso_busca` | O sistema não para por causa do índice. O limiar de 0,5 da busca por palavra continua valendo nesse caso. |

**Corte: um trecho por guia.** Os guias têm template fixo (sintoma, causa, solução) e cabem num
trecho. **`k = 3`.** Nas perguntas com resposta o guia certo veio em primeiro (§4.3), então
`k = 1` bastaria para a decisão. Fica em 3 porque o log mostra os concorrentes (o segundo lugar
chegou a 0,53 no `TKT-0001` e a 0,50 no `TKT-0007`, §4.3) e porque o nó `redigir` só lê o primeiro: não
custa nada ao modelo.

### 4.2 As exceções (`nao_cobre`): o vetor não as enxerga de modo confiável, e o modelo as lê

**O que o vetor faz com as exceções.** A decisão do grupo foi que a busca nova cobrisse as
exceções, com um trecho de ressalva embedado à parte. O teste (`src/medir_rag.py`, bloco 4): para
cada frase de `nao_cobre`, o cosseno das perguntas que **são** a exceção contra o das perguntas que
o guia cobre, em três formas de embedar (a pergunta inteira contra a frase crua; contra uma frase
descritiva; a melhor janela de 1 a 4 palavras do relato contra a frase). Resultado no corpus de 16
guias (`logs/rag-medicao/saida.txt`):

- **KB-104** (o guia da falha constante; 3 exceções e 1 a 2 casos normais por frase): nenhuma das 12
  combinações passa de +0,01 de folga, e 7 das 12 dão folga negativa ou nula. O assunto da pergunta
  (erro 502) domina o vetor, e "constante" e "intermitente" ficam à mesma distância. Foi o primeiro
  achado (corpus de 7 guias), e o corpus novo não o desfez.
- **Guias novos** (KB-107, KB-111, KB-115): a folga é positiva na maioria das combinações, de +0,03 a
  +0,22 (KB-107 com "consulta demorada": +0,13 a +0,22), com contraexemplos (KB-107 "lentidao" e
  KB-115 "intermitente" em janela, a −0,01 e −0,02). Mas cada guia tem **uma ou duas perguntas de exceção**,
  escritas por nós, e nenhuma folga é larga o bastante para fixar um limiar.
- **Resultado sobre as perguntas:** só com o vetor, 5 das 11 perguntas de exceção (X1 a X11) terminam
  em ação indevida: X3, X4, X5, X7 e X8. O `X3` ("o erro 502 vai e vem") é o caso de origem: o vetor
  põe o KB-104 em 0,52 e o sistema agiria sobre um guia que não cobre o caso.

Por isso o trecho de ressalva embedado **não foi implementado**: a medição não sustenta um limiar.
A ressalva **literal** (a frase de `nao_cobre` escrita no relato) continua em código, com o redutor
de 0,4 sobre o score.

**O modelo as lê.** O nó `conferir_ressalva` (`src/grafo.py`, prompt `ressalva-v1.md`) recebe o
relato, o log, o guia e a lista das situações que ele não cobre, e responde se o relato cai numa
delas. O código só aplica o redutor, e só aceita uma `frase` que esteja na lista do guia: o modelo
pode **baixar** o score, nunca subir, e não cria uma exceção que o guia não declare. O nó só roda
quando o primeiro guia passaria do limiar, ainda não caiu numa ressalva literal e declara
`nao_cobre`. Hoje isso vale para oito guias (KB-102, 104, 107, 111, 112, 113, 114 e 115).

**O que foi medido, no corpus de 16 guias** (`python src/medir_rag.py ressalva`, 11/10/2026,
`ministral-8b-latest`, `temperature=0`, 3 repetições por pergunta;
`logs/rag-medicao/ressalva-v1.txt`). Quando cada pergunta foi escrita: X4, X5 e C1 a C3, antes da
primeira medição do nó (corpus de 7 guias); X6, X7, C4 e C5, depois dela e antes de rodar o
`ressalva-v2.md`; X8 a X11 e C6 a C8, antes de qualquer medição no corpus de 16.

| Guia e situação | Perguntas | O nó diz "cai"? | Certo? |
|---|---|---|---|
| KB-104 ("intermitente" e outras) | P6, X1 (a frase literal já a pegaria), **X3, X4 (paráfrases)** | sim, 3 de 3 em cada | **12 de 12** |
| KB-107 ("lento", "lentidao", "consulta demorada") | **X8** ("devagar", paráfrase) | sim, 3 de 3 | **3 de 3** |
| KB-115 ("intermitente", "as vezes", "de vez em quando") | X9 (literal), **X10** (paráfrase) | sim, 3 de 3 em cada | **6 de 6** |
| KB-111 ("recebimento", "nao recebe", "nao chega") | X11 (a frase literal já a pegaria) | sim, 3 de 3 | **3 de 3** |
| **KB-102 ("ssh")** | P7, X2, X5, X6, X7 | **não**, 3 de 3 em cada | **0 de 15** |
| Controles: o guia cobre o caso | P2, A2, A4, A8, A14, A15, C1 a C8 (14 perguntas) | não, 3 de 3 em cada | **42 de 42** |

- **O que funcionou:** as paráfrases do KB-104, do KB-107 e do KB-115 foram reconhecidas nas 3
  repetições, e **nenhum dos 14 controles foi barrado**. Em geral, 24 de 39 respostas certas nas
  exceções e 42 de 42 nos controles.
- **O que não funcionou (decisão do grupo: aceitar e documentar):** o modelo **não** reconhece o
  "ssh" do KB-102, nem quando o relato escreve "SSH" (P7, X2, X6). Nas justificativas ele compara o
  relato com a causa do guia (arquivos e pastas) e diz que nada da lista aparece. A hipótese é que
  a frase `ssh`, uma palavra só, não descreve uma situação, ao contrário das do KB-104. **Não foi
  testada**: reescrever a frase em `nao_cobre` é uma mudança de dado, que o grupo decidiu não fazer.
- **No sistema inteiro** (busca vetorial, aresta, nó), nas 28 perguntas de exceção e controle:
  antes do nó, 22 certo, 1 parcial e 5 errado; depois, **25 certo, 1 parcial e 2 errado**. O `X3`, o
  `X4` e o `X8` passaram de errado a certo. O que continua errado é o `X5` e o `X7`: o vetor põe o
  KB-102 em primeiro, o nó diz "não cai", e o sistema agiria sobre um guia que não cobre o caso. O
  último guarda desse erro é o analista, e a tela do H1 passou a mostrar o que o guia declara não cobrir
  (`humano.md` §2.1).
- **O `ressalva-v2.md` não foi adotado.** Medido no corpus de 7 guias (`logs/rag-medicao/ressalva-v2-corpus7.txt`),
  acertou 5 de 15 no KB-102 (P7, X6), mas nessas perguntas o primeiro guia é o KB-103, que não declara
  ressalvas, e o nó nem roda; onde o nó roda sobre o KB-102 (X5, X7), o v2 também dizia "não cai". Barrou um controle
  em 1 de 3 repetições (A4), e no sistema inteiro ficou com 14 certo, 1 parcial, 3 errado, contra 15, 1, 2 do v1. Não foi
  medido no corpus de 16.
- **O `X3` pelo grafo, de ponta a ponta** (`logs/grafo-ressalva-x3/`, corpus de 7 guias, texto digitado no
  `TKT-0006`: "O site cai e volta sozinho, o erro 502 vai e vem."): o nó respondeu que cai em
  "intermitente", o score do KB-104 caiu de 0,52 para 0,21 e o desfecho foi `fila_humana`.

Limites: um modelo; 8 exceções de guias com a ressalva lida (e 5 sobre o KB-102, que falham) e 14
controles, escritos por nós; 3 repetições a `temperature=0` (as respostas foram iguais nas 3 em
todas as perguntas, o que mostra estabilidade e não generalização).

### 4.3 As medições da busca, no corpus de 16 guias (11/10/2026)

O corpus passou de 7 para 16 guias (mais 3 fichas de plano) no mesmo dia, e **todas as medições
abaixo foram refeitas no corpus novo** (as do corpus de 7 estão preservadas em `logs/rag-medicao/*-corpus7.*`
e resumidas no fim desta seção). `python src/medir_rag.py` grava `logs/rag-medicao/`
(`saida.txt`, `medicao.json`). As perguntas estão em `dados/perguntas-rag.json`: as dez do §3, 24
paráfrases com resposta (A1 a A24), 11 exceções (X1 a X11), 8 controles (C1 a C8), 31 sem resposta
(N1 a N31, várias quase-acertos: perto de um guia, mas fora dele) e 3 sobre planos (F1 a F3). As
perguntas novas foram escritas **antes** da medição. A medição principal gastou perto de 12 mil tokens de embedding.

**1. Acesso.** A chave alcança o `mistral-embed`: 1024 dimensões, 0,56 s por chamada, limite de 60
requisições por minuto.

**2. Calibração do limiar, só com A\* e N\*: a calibração não separa as duas classes, e a triagem
não resolve.** A calibração foi feita em duas rodadas no mesmo dia. **Na primeira** (16 perguntas com
resposta e 14 sem), o pior acerto (0,819, A4) ficou abaixo da pior pergunta sem resposta (0,835, N13),
folga de −0,016 (com o corpus de 7 guias eram +0,036); está preservada em
`logs/rag-medicao/saida-corpus16-a.txt`. **Na segunda**, para saber se aquilo era caso isolado, o grupo
ampliou o conjunto (decisão 2.B): **24 perguntas com resposta** (A1 a A24) e **31 sem resposta**
(N1 a N31). As novas (A17 a A24, N15 a N31) foram escritas **antes** de medir: sem resposta comerciais,
instruções que a base não tem ("como crio um subdomínio?", "como restauro um backup?"), relatos vagos,
um pedido fora da alçada e um assunto alheio. Resultado (`logs/rag-medicao/saida.txt`):

- Cosseno com o guia certo, nas A\*: de 0,819 (A4) a 0,929 (A23).
- Cosseno do melhor guia, nas N\*: de 0,674 (N6) a 0,835 (N13). **A folga continua em −0,016.**
- **As perguntas sem resposta que passam ficaram mais numerosas:** com o limiar do código (0,80), **6 de
  31 agem** (N12, N13, N20, N23, N24, N26). Com 14 perguntas eram 2 de 14.

| Limiar | Acertos barrados (de 24) | Sem resposta que agem, só pela busca (de 31) | Idem, com a triagem na frente |
|---|---|---|---|
| 0,79 | 0 | 11 | 9 |
| **0,80 (o do código)** | **0** | **6** | **5** |
| 0,81 | 0 | 5 | 4 |
| 0,82 | 1 (A4) | 3 | 2 |
| 0,83 | 5 | 2 | 1 |
| 0,84 | 7 | 0 | 0 |
| 0,85 | 11 | 0 | 0 |

**Nenhum limiar zera as duas colunas.** O que zera os falsos acertos (0,84) barra 7 de 24 acertos
(29%) e o `TKT-0003` (cosseno 0,822) do gabarito; o que não barra nenhum acerto (0,80 e 0,81) deixa agir
de 4 a 6 das 31. O `LIMIAR_COSSENO` ficou em **0,80**, o maior que não barra acerto algum.

**A triagem na frente** (`python src/medir_rag.py triagem`, `logs/rag-medicao/triagem.txt`,
`ministral-8b-latest`, uma execução por pergunta): das 31 sem resposta, a triagem classificou 10 como
`comercial`, 4 como `insuficiente`, 2 como `fora_da_alcada` e **15 como `tecnico`, e só essas chegam à busca**.
Das 6 que agiriam só pela busca, **a triagem desvia 1 (o N13, "quanto custa", que é comercial)**. As outras
5 são instruções ("como faço...") sobre um tema que a base cobre por outro lado, e a triagem as chama de técnicas:

| Pergunta | Guia em que age | Ação do guia |
|---|---|---|
| N12 "como configuro um certificado SSL que comprei de outra empresa?" | KB-101-A (0,81) | `anotar` |
| N20 "como instalo um certificado SSL gratuito no domínio novo?" | KB-101-A (0,81) | `anotar` |
| N23 "como aumento o limite de upload de arquivos do meu site?" | KB-113 (0,82) | `anotar` |
| N24 "como configuro o redirecionamento de www para o domínio sem www?" | KB-110 (0,83) | `anotar` |
| N26 "como crio um banco de dados novo para a minha aplicação?" | KB-107 (0,81) | `escalar` |

**Quatro dos cinco são `anotar`: gravam uma `anotacao_interna` sem confirmação humana.** O quinto é
`escalar` e passaria pelo H1. A taxa de falso acerto no sistema é de **5 em 31 perguntas sem resposta
(16%), ou 5 das 15 que a triagem deixa chegar à busca (33%)**. É uma taxa sobre um conjunto escrito por nós, que
procurou de propósito os quase-acertos; a de chamados reais pode ser menor ou maior.
**Em contrapartida, a triagem não desvia nenhuma das 36 perguntas com resposta** (A\*, C\*, P1, P2, P6,
P7): ela não custa automação.

(O `N11`, cosseno 0,799, passava o portão por arredondamento do score a 0,50 e foi corrigido: o score é
truncado em duas casas, e score ≥ 0,5 só com cosseno ≥ 0,80.)

**Risco assumido (decisão do grupo, 11/10/2026): o sistema pode agir sobre uma pergunta que a base
não responde.** Com o limiar do cosseno em 0,80, 5 de 31 perguntas sem resposta chegam a agir,
mesmo com a triagem na frente (§4.3). São instruções ("como faço...") sobre um tema que a base cobre
por outro lado: N12 e N20 caem no KB-101-A, N23 no KB-113, N24 no KB-110 e N26 no KB-107. Quatro
desses guias são `anotar`: gravam uma `anotacao_interna` sem confirmação humana (o N26, `escalar`,
passa pelo H1). O grupo avaliou exigir confirmação também para `anotar` e **decidiu não fazê-lo**: o
critério do H1 continua sendo "ação irreversível", e a anotação é reversível. O que contém o risco
hoje é o portão de confiança, o analista que lê a anotação, e a tela do H1 para o chamado.

**3. As perguntas contra três buscas.** Limiar do portão 0,5. A busca por palavra recebe a
pergunta inteira como um termo só, como no §3.1; no sistema, quem escolhe os termos é a triagem
(medição 4), e por isso as falhas da busca por palavra nas A\* são em parte efeito do termo único.

| Perguntas | Palavra (hoje) | Só vetorial | Híbrida |
|---|---|---|---|
| Enunciado: P1, P2, P6, P7, P8, P10 | 5 certo, 1 parcial | **6 certo** | **6 certo** |
| Exceções X1 a X11 | 6 certo, 4 parcial, 1 errado | 5 certo, 1 parcial, **5 errado** | idem |
| Controles C1 a C8 | 8 certo | **8 certo** | 8 certo |
| Calibração (dentro da amostra): A\*, N\* (55) | 40 certo, 15 errado | **49 certo, 6 errado** (N12, N13, N20, N23, N24, N26) | idem |

- **A P7 deixou de ser parcial** (era o achado do §3.1): o KB-103 vem em primeiro com score 0,56.
- **A P10 ("Como instalo o WordPress?") é recusada**: o melhor guia (KB-102) fica em 0,41.
- **As exceções são o ponto fraco do vetor sozinho** (5 errados): o nó da ressalva (§4.2) resolve 3
  deles.
- **A híbrida deu o mesmo primeiro lugar que o só vetorial em todas as perguntas**, no corpus de 7 e no de 16.
  Esta medição **não mostra ganho da híbrida**, e o grafo busca só por vetor. O modo existe em
  `vetorial.buscar(modo="hibrida")` só para medir.
- **O vetor acha as duas versões do guia de SSL sem curadoria**, e o antigo fica na frente: P1,
  KB-101 com cosseno 0,853 e KB-101-A com 0,842; A1, 0,846 e 0,833. A curadoria continua necessária.

**4. As fichas de plano** (bloco 4b). As três perguntas sobre planos acharam a ficha certa (3 de
3), e nenhuma faria um guia agir (o melhor guia fica em 0,34 a 0,46):

| Pergunta | 1ª ficha (cosseno) | 2ª ficha (cosseno) |
|---|---|---|
| F1: "O plano Hospedagem Start inclui a correção do código do meu site?" | Start (0,859) | Business (0,844) |
| F2: "A VPS Pro cobre a aplicação que eu instalei no servidor?" | VPS Pro (0,850) | Start (0,792) |
| F3: "O plano Hospedagem Business tem atendimento por telefone?" | Business (0,849) | Start (0,820) |

A margem entre a 1ª e a 2ª ficha é pequena (0,015 na F1): as fichas de Start e Business são parecidas.
No grafo a ficha não é buscada por vetor: vem de `clientes.plano` e vai ao texto da redação
(`redigir`) e à tela do analista (H1).

**5. Os 8 casos pelo grafo** (`logs/grafo-corpus16-1/`, `-2/`, `-3/`; `ministral-8b-latest`,
`--auto-aprovar`, commit `4c3ad53 + alterações locais`; busca só vetorial e nó da ressalva): **8 de 8
nas três rodadas**, com o mesmo melhor guia e o mesmo score nas três. O nó rodou em `TKT-0003` e
`TKT-0007` (KB-102 em primeiro) e respondeu "não cai" nos dois, nas três rodadas.

| Chamado | Melhor guia, score (cosseno) | Segundo guia, score | Desfecho |
|---|---|---|---|
| `TKT-0001` | KB-101-A, 0,66 (0,867) | KB-110, 0,53 | `anotacao_interna` |
| `TKT-0002` | KB-111, 0,47 (0,791) | KB-106, 0,45 | `fila_humana` (a divergência decide antes do score) |
| `TKT-0003` | KB-102, 0,55 (0,822) | KB-105, 0,45 | `abrir_chamado_interno` |
| `TKT-0006` | KB-104, 0,24 (0,843), com ressalva literal | KB-106, 0,49 | `fila_humana` |
| `TKT-0007` | KB-102, 0,72 (0,892) | KB-114, 0,50 | `abrir_chamado_interno` |

Os outros três (`TKT-0004`, `TKT-0005`, `TKT-0999`) não buscam. Pontos:

- **O corpus maior encostou os segundos lugares no limiar.** O segundo guia do `TKT-0001` (KB-110,
  "redirecionamento") tem 0,53, acima do limiar; o do `TKT-0007` (KB-114, "FTP") tem 0,50,
  exatamente nele. Só o primeiro guia age, mas a margem de um guia sem relação com o chamado é
  nula. No corpus de 7 guias o maior segundo lugar era 0,49.
- **No `TKT-0002` o melhor guia passou a ser o KB-111** (envio de e-mail), e não o KB-106: o relato
  é "Webmail fora do ar". Não mudou o desfecho, porque a divergência entre relato e log é decidida
  antes do score, mas mostra que um guia plausível e errado leva a melhor quando o relato é curto.
- **Chamadas ao modelo:** 3 em `TKT-0003` e `TKT-0007` (triagem, ressalva, redação), 2 nos demais com
  triagem e redação, 1 em `TKT-0999`.
- **Tokens de embedding por execução (campo `tokens_embedding` do log):** de 1.761 a 1.779 nas cinco
  que buscam, e 0 nas três que não buscam. Os números incluem a indexação dos 19 trechos: o
  `--todos` recria o banco, e o índice, a cada caso. Num banco já indexado a execução só embeda o relato.
  O custo em dólares não foi calculado (o preço do `mistral-embed` não foi verificado).

**O corpus de 7 guias, para comparação** (medido antes dos KB-107 a KB-115, preservado em
`*-corpus7.*` e em `logs/grafo-rag/` e `logs/grafo-ressalva/`): calibração com folga de +0,036 (acertos
0,819 a 0,869, perguntas sem resposta 0,672 a 0,783), limiar 0,80 por ponto médio; só vetorial e
híbrida iguais; 8 de 8 nos 8 casos, uma execução por configuração, com o segundo guia chegando a 0,49. A
mudança que o corpus de 16 trouxe foi a calibração: a folga virou negativa.

Limites desta medição: uma execução do `medir_rag.py`; conjunto de perguntas escrito por nós, com
31 sem resposta, e a triagem foi medida com uma execução por pergunta; a calibração e o teste usam o mesmo corpus; três rodadas dos mesmos 8 casos
(estáveis, mas não são perguntas novas); preço do embedding não verificado.

## 5. Onde a recuperação entra no laço (§4.4)

> **Sobre o id `KB-101` nestes logs.** Em 11/10/2026 a base passou a nomear as versões: o guia com letra é a atualização do guia sem letra. O procedimento de SSL vigente, que aparece aqui como `KB-101`, hoje é o `KB-101-A`; o `KB-101` de hoje é a versão antiga, revogada (`rag.md` §2.1). O texto do procedimento não mudou.

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

**Com a busca vetorial e o corpus de 16 guias** (`logs/grafo-corpus16-1/`, `-2/` e `-3/`, 11/10/2026, 8 de 8
nas três; §4.3), os números de recuperação são os mesmos das rodadas anteriores do grafo: 5 buscas por
rodada (média de 0,63 por execução), 3 execuções sem busca (`TKT-0004`, `TKT-0005`, `TKT-0999`),
nenhuma busca repetida e nenhuma inútil. Acrescenta-se uma chamada ao modelo, a do nó da ressalva, em 2 das 5
buscas (`TKT-0003` e `TKT-0007`).

A defesa da escolha começa na medição das rodadas 1 e 2 do laço:
as buscas inúteis e a busca que faltou são todas erro de decisão do modelo. A rodada 3 enfraquece
essa defesa pela metade: com o seed e o texto atuais, o modelo decidiu certo quando buscar em 7
das 8 execuções, e na oitava quem forçou a busca foi o código. O que a rodada 3 acrescenta é
outro argumento: o `TKT-0002` precisa que a divergência entre relato e log seja decidida
**antes** de o resultado da busca chegar ao modelo, e não depois. Nas três rodadas do grafo foi
o que aconteceu. O preço da etapa fixa é o que o laço tinha e o grafo não tem: uma segunda
busca com outros termos quando a primeira vem fraca.

## 6. O que falta para este item

- **A calibração do limiar não separa as duas classes, e a triagem não resolve (§4.3).** Com 24 perguntas
  com resposta e 31 sem resposta, 6 das sem resposta agem no limiar 0,80 e, com a triagem na frente, 5
  (16%; 33% das que chegam à busca). Quatro dos cinco são guias `anotar`, que gravam sem confirmação humana.
  Subir o limiar até zerar os falsos acertos barra 29% dos acertos e o `TKT-0003`. **Decisão do grupo
  (11/10/2026): aceitar e documentar** (§4.3). Exigir confirmação humana também para `anotar` foi avaliado
  e descartado (mudaria o critério do H1, "ação irreversível"). Uma defesa não medida fica registrada: a
  distância entre o primeiro e o segundo guia, que seria uma heurística nova.
- **A ressalva `ssh` do KB-102 não é lida pelo modelo (§4.2).** Decisão do grupo: aceitar e
  documentar. A reescrita da frase em `nao_cobre` (dado) ficou sem testar.
- Margem do portão: o segundo guia de um chamado chega a 0,50 e 0,53 (§4.3).
- Calibração e teste usam o mesmo corpus de 16 guias, e o conjunto de 55 perguntas foi escrito pelo mesmo grupo.
- Preço do `mistral-embed` não verificado: os tokens de embedding estão no log (`tokens_embedding`), mas
  não entram no orçamento nem em dólares.
- As fichas de plano servem de contexto à redação e à tela do analista. Nenhuma regra de decisão usa o
  plano do cliente, e a coluna `planos` de `kb_artigos` não foi criada.
- Repetir a medição das versões (§2.1): foi uma execução de cada combinação, com a busca por palavra e o
  corpus de 7 guias.
- Conferir a coerência entre letra e data ao carregar o corpus, e não só no teste do seed.
- Registrar o descarte também quando a versão nova não casa com a consulta (na busca por palavra).
- Medir o §5 em perguntas fora dos 8 casos: as rodadas do grafo são dos mesmos chamados.

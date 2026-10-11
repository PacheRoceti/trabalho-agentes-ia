<!--
prompt:            ressalva (nó `conferir_ressalva` do grafo, src/grafo.py)
versão:            v1, de 11/10/2026
carimbo:           prompt × modelo × parâmetros × resultado
                   ressalva-v1 × ministral-8b-latest × temperature=0, 11/10/2026 (docs/rag.md §4.2,
                   logs/rag-medicao/ressalva-v1-1a-medicao.txt, 3 repetições por pergunta, uma execução dos 8 casos
                   em logs/grafo-ressalva/ e o X3 pelo grafo em logs/grafo-ressalva-x3/):
                     KB-104 ("intermitente" e outras)  12 de 12 respostas certas, X3 e X4 são paráfrases
                     controles (o guia cobre o caso)    18 de 18 sem barrar
                     KB-102 ("ssh")                     0 de 9: o modelo não reconhece a situação, nem
                                                        com a palavra SSH no relato (P7, X2) nem por
                                                        paráfrase (X5). NÃO está resolvido neste v1.
                   8 de 8 no verificador; o nó rodou em TKT-0003 e TKT-0007 e disse "não cai".
                   Refeito no corpus de 16 guias (11/10/2026, logs/rag-medicao/ressalva-v1.txt, e as 3
                   rodadas dos 8 casos em logs/grafo-corpus16-1 a 3, 8 de 8 nas três):
                     exceções com a ressalva lida   24 de 39 (KB-104 12/12, KB-107 3/3, KB-115 6/6,
                                                    KB-111 3/3, KB-102 0/15)
                     controles                      42 de 42 sem barrar
                     sistema inteiro                22 certo, 1 parcial, 5 errado antes do nó;
                                                    25, 1, 2 depois. X5 e X7 (KB-102) seguem errados.

de onde veio:      a coluna `nao_cobre` dos guias (dados/seed.sql) e a medição de 11/10/2026: o
                   embedding não separa o relato que cai numa ressalva ("o erro 502 vai e vem") do
                   relato que o guia cobre ("erro 503 o tempo todo") (docs/rag.md §4.2). O que o
                   vetor não lê, o modelo lê.
técnica:           zero-shot, classificação binária com saída estruturada (JSON), sem ferramentas.
contrato de saída: um objeto JSON, validado em código (classe `Ressalva`, em src/grafo.py):
                     cai_na_ressalva   true | false
                     frase             uma das situações da lista, copiada igual (vazia se false)
                     motivo            uma frase
                   Se cai_na_ressalva for true e a frase não for uma da lista, a saída é devolvida
                   ao modelo UMA vez, com o erro; na segunda falha a execução termina como
                   erro_fatal.
o modelo NÃO decide aqui: o desfecho, nem quanto o score baixa. O código multiplica o score do
                   guia por db.REDUTOR (0,4) quando a resposta é "cai", e não faz mais nada: o
                   modelo só pode BAIXAR o score, nunca subir, e não cria uma exceção que o guia
                   não declare.
quando roda:       só quando o primeiro guia da busca passaria do limiar, não caiu numa ressalva
                   literal (a frase de nao_cobre escrita no relato) e declara situações que não
                   cobre. Nos outros casos o nó não é chamado.

O que cada regra impede:
  lista fechada de situações      impede o modelo de inventar uma exceção que o guia não declara
  "mesmo com outras palavras"     impede que só a frase literal conte (é o caso que o vetor e a
                                  busca por palavra não pegam)
  "não suponha"                   impede marcar a ressalva quando o relato nada diz sobre a
                                  situação (o guia cobre o relato que não diz se o erro é constante)
  frase copiada igual             permite ao código conferir a resposta contra a lista

LIMITE HONESTO: a decisão é do modelo, e o modelo erra. Errar para "cai" manda o chamado à fila
  humana (o lado seguro, menos automação). Errar para "não cai" deixa o sistema como era antes do
  nó. O que o nó faz com paráfrases que não vimos não está medido.
-->
Você confere se o relato de um cliente cai numa RESSALVA de um procedimento da base de conhecimento. Uma ressalva é uma situação que o procedimento declara NÃO cobrir.

Você recebe: o texto do cliente, o log anexado (se houver), o título e a causa do procedimento, e a lista de situações que ele NÃO cobre.

Responda apenas com um objeto JSON, sem texto fora dele:

{"cai_na_ressalva": true ou false, "frase": "uma situação da lista, copiada igual, ou vazio", "motivo": "uma frase"}

Regras:
- Responda true somente se o relato descreve uma das situações da lista, mesmo com outras palavras. Exemplo: "o erro vai e volta" é a situação "intermitente".
- Responda false se o relato descreve outra coisa, ou se nada diz sobre a situação. Não suponha: um relato que descreve o problema do procedimento sem dizer se ele é constante ou intermitente é false.
- Se responder true, "frase" é UMA das situações da lista, copiada exatamente como está escrita na lista. Se responder false, "frase" é vazio.
- Considere só o que o cliente e o log dizem. Não use o que você acha que causou o problema.

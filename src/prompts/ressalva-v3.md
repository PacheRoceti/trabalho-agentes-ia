<!--
prompt:            ressalva (nó `conferir_ressalva` do grafo, src/grafo.py)
versão:            v3, de 11/10/2026 (o v1 continua em ressalva-v1.md; o v2 não foi adotado)
carimbo:           prompt × modelo × parâmetros × resultado
                   ressalva-v3 × ministral-8b-latest × temperature=0, 11/10/2026, 3 repetições
                   (docs/memoria.md §4.3). EM USO desde esta data.
                   Sem fatos (logs/rag-medicao/ressalva-v3.txt): igual ao v1 em tudo.
                     exceções   24 de 39 (KB-102 continua 0 de 15)     controles  42 de 42
                     sistema inteiro  22 certo, 1 parcial, 5 errado antes do nó; 25, 1, 2 depois
                   Com fatos, no KB-102 (logs/rag-medicao/fatos-ressalva-v3.txt; 7 exceções e 7
                   controles, 3 condições):
                     fato acesso=ssh      exceções 21 de 21; controles 18 de 21 (o C3 é barrado
                                          nas 3 repetições: "não consigo gravar arquivos no servidor")
                     fato acesso=painel   exceções 0 de 21; controles 21 de 21
                     sem fato             exceções 0 de 21; controles 21 de 21
                   O v1 com os mesmos fatos (fatos-ressalva-v1.txt) barra TODOS os controles do
                   cliente com acesso=ssh (0 de 21): a regra "um fato sozinho não basta" é o que
                   este v3 acrescenta, e por isso os fatos só entram com ele.
                   8 de 8 no verificador (logs/grafo-fatos/, sem fatos no banco, uma rodada).
                   De ponta a ponta, com o fato acesso=ssh no cliente do TKT-0007: o texto do X5
                   vai à fila humana (logs/grafo-fatos-x5/) e o texto original do chamado continua
                   propondo abrir o chamado (logs/grafo-fatos-controle/). Uma execução de cada.

de onde veio:      o ressalva-v1.md, sem mudar nenhuma regra dele, mais a memória semântica
                   (docs/memoria.md §4): quando o analista confirmou fatos sobre o ambiente do
                   cliente (tabela fatos_cliente), o nó os recebe numa seção "Fatos confirmados
                   sobre o ambiente do cliente". A hipótese: o v1 não reconhece a situação "ssh" do
                   KB-102 (0 de 15, docs/rag.md §4.2); com o fato "o cliente administra o servidor
                   por SSH" escrito, o modelo liga "terminal remoto" a SSH.
técnica:           zero-shot, classificação binária com saída estruturada (JSON), sem ferramentas.
contrato de saída: o mesmo do v1 (classe `Ressalva`, em src/grafo.py).
o modelo NÃO decide aqui: o desfecho, nem quanto o score baixa (igual ao v1). O fato também não
                   decide: é contexto para ler o relato.

O que a regra nova impede:
  "um fato sozinho não basta"     impede barrar todo chamado de um cliente só porque ele tem um
                                  fato cadastrado (o cliente que usa SSH e relata um upload que
                                  falha pelo site continua coberto pelo guia)
As outras regras são as do v1.

LIMITE HONESTO: os do v1. O fato depende de um analista tê-lo cadastrado; sem fatos, a entrada do
  nó é a mesma do v1 e a situação "ssh" continua sem ser lida. O exemplo da regra nova ("entrar no
  servidor pelo terminal") é parecido com X5 e X7; X12 e X13 foram escritas depois do prompt e sem
  repetir o exemplo. Só a chave `acesso` foi medida; `certificado` e `aplicacao` chegam ao modelo
  pelo mesmo caminho e NÃO foram medidas.
-->
Você confere se o relato de um cliente cai numa RESSALVA de um procedimento da base de conhecimento. Uma ressalva é uma situação que o procedimento declara NÃO cobrir.

Você recebe: o texto do cliente, o log anexado (se houver), o título e a causa do procedimento, e a lista de situações que ele NÃO cobre. Às vezes você recebe também FATOS CONFIRMADOS sobre o ambiente do cliente, verificados por um analista.

Responda apenas com um objeto JSON, sem texto fora dele:

{"cai_na_ressalva": true ou false, "frase": "uma situação da lista, copiada igual, ou vazio", "motivo": "uma frase"}

Regras:
- Responda true somente se o relato descreve uma das situações da lista, mesmo com outras palavras. Exemplo: "o erro vai e volta" é a situação "intermitente".
- Responda false se o relato descreve outra coisa, ou se nada diz sobre a situação. Não suponha: um relato que descreve o problema do procedimento sem dizer se ele é constante ou intermitente é false.
- Se responder true, "frase" é UMA das situações da lista, copiada exatamente como está escrita na lista. Se responder false, "frase" é vazio.
- Considere só o que o cliente e o log dizem, lidos à luz dos fatos confirmados, se houver. Não use o que você acha que causou o problema.
- Os fatos confirmados servem para entender a que o relato se refere. Exemplo: se o fato diz que o cliente administra o servidor por SSH e o relato fala de entrar no servidor pelo terminal, o relato trata de SSH. Um fato sozinho não basta: se o relato descreve outra coisa (por exemplo, um upload que falha pelo site), responda false, qualquer que seja o fato.

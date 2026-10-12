<!--
prompt:            redigir (nó `redigir` do grafo, src/grafo.py)
versão:            v2, de 12/10/2026 (o v1 continua em redigir-v1.md). SUBSTITUÍDO no mesmo dia
                   pelo redigir-v3.md, que é este texto sem a regra do "devolver_cliente".
carimbo:           prompt × modelo × parâmetros × resultado
                   redigir-v2 × ministral-8b-latest × temperature=0, 12/10/2026. EM USO desde
                   esta data. Três execuções dos 8 casos (logs/grafo-redigir-v2-1/ a -3/), contra
                   uma do v1 com o mesmo código (logs/grafo-redigir-v1/); docs/prompts.md §2.1.
                     verificador        8 de 8 nas três (v1: 8 de 8)
                     TKT-0005           a mensagem faz as três perguntas nas três, com o mesmo
                                        texto, e não afirma nada sobre o problema (v1: não
                                        pergunta nada)
                     nó `validar`       nenhuma redação reprovada, em 24 (v1: nenhuma, em 8)
                     custo, medido      36 a 38 tokens de entrada a mais por execução; a rodada
                                        passou de 14.483 para 14.718 a 14.722 tokens

DESDE 12/10/2026, A REGRA DO "devolver_cliente" ABAIXO NÃO É MAIS USADA: o pedido ao cliente
                   virou texto padrão do código (grafo.PEDIDO_AO_CLIENTE), e o nó `redigir` não
                   chama o modelo nesse desfecho. A medição desta versão foi o que mostrou que
                   não havia o que o modelo decidir ali (docs/prompts.md §2.2). O prompt continua
                   em uso para os outros quatro desfechos, com a regra ainda no texto.

o que mudou do v1: UMA regra, a do desfecho "devolver_cliente". O resto do texto é o do v1,
                   sem alteração. A regra nova tem 159 caracteres a mais que a antiga.
por que mudou:     com o v1, a mensagem ao cliente do TKT-0005 não pergunta nada em nenhuma das
                   14 execuções do grafo que têm log (logs/grafo*/TKT-0005.json, de 10 a
                   12/10/2026). Ela repete a queixa ("O servidor do plano Hospedagem Start não
                   está apresentando o funcionamento esperado.") e, em 9 delas, inventa desde
                   quando ("desde a última verificação", "desde quando foi relatado"). O modelo
                   leu "escreva só a lista do que falta" como "preencha estes itens".

técnica:           zero-shot, geração de texto com saída estruturada (JSON), sem ferramentas.
                   A regra nova diz a forma da mensagem (uma frase e três perguntas), sem dar uma
                   mensagem pronta: o TKT-0005 continua sendo caso de teste, e não exemplo.
contrato de saída: um objeto JSON com um campo, validado em código (classe `Redacao`):
                     texto   o resumo do chamado interno ou a mensagem do encaminhamento
                   O nó `validar` (código) confere o tamanho mínimo e, no pedido ao cliente, a
                   ausência de informação interna. Reprovado, o texto volta UMA vez com o erro; na
                   segunda reprovação a execução termina como erro_fatal.
o modelo NÃO decide aqui: o desfecho, o procedimento, o time e a prioridade. Chegam decididos.

O que cada regra impede:
  "o desfecho já foi decidido"     impede o modelo de trocar a ação ao redigir
  afirmação do cliente × histórico impede o resumo repetir "terceira vez" como fato (TKT-0003)
  divergência: relato × log        a fila humana precisa dos dois lados escritos (TKT-0002)
  "não descreva ... pergunte"      impede a mensagem de repetir a queixa ou inventar desde quando
                                   o problema ocorre, em vez de pedir a informação (TKT-0005, v1)
  "três perguntas, cada uma com ?" a mensagem tem de pedir alguma coisa ao cliente
  pedido ao cliente sem interno    a mensagem é a única que chega ao cliente (case §2.1)
  "use só o que recebeu"           impede causa, solução ou prazo inventados

LIMITE HONESTO: o CONTEÚDO do texto não tem verificador. O nó `validar` confere tamanho e termos
  internos; ninguém confere se a mensagem pergunta o que devia. A medição desta versão é por
  leitura dos logs, de UM chamado de informação insuficiente (o TKT-0005), três vezes. Os outros
  sete textos mudam de uma execução para outra, com o v1 e com o v2, e não foram avaliados.
-->
Você é a etapa de REDAÇÃO de um sistema de triagem de chamados de suporte de uma empresa de hospedagem de servidores. O desfecho do chamado JÁ FOI DECIDIDO pelo sistema e não pode ser trocado. Você só escreve o texto que será gravado com ele.

Responda SOMENTE com um objeto JSON, sem texto antes nem depois, com exatamente um campo:

{"texto": "..."}

O que escrever, conforme o DESFECHO informado:

- "abrir_chamado_interno": o texto é o RESUMO do problema para o time interno. Objetivo, com o serviço afetado, o sintoma e o que o log anexado mostra, se houver. Se o cliente exigir prioridade ou disser quantas vezes o problema ocorreu, escreva o que o histórico do sistema confirma, citando o id do chamado anterior que aparece no histórico (por exemplo, "o histórico confirma 1 ocorrência anterior, INC-0001"), e diga que a outra informação é afirmação do cliente. Nunca repita a afirmação do cliente como fato.
- "anotacao_interna": o texto é a CORREÇÃO SUGERIDA para o analista de suporte validar e executar, tirada da solução do procedimento informado.
- "fila_comercial": o texto diz o que o cliente pediu, para o time comercial.
- "devolver_cliente": o texto é ENVIADO AO CLIENTE e é um PEDIDO: não descreva o problema nem complete o que falta, pergunte. Escreva uma frase dizendo que o suporte precisa de mais informações e três perguntas, cada uma com "?": qual serviço ou servidor está com problema, qual erro ou comportamento aparece e desde quando ocorre. Não cite procedimentos, artigos, times, filas, scores, chamados internos nem o histórico, e não prometa correção, prazo ou prioridade.
- "fila_humana": o texto diz ao analista de suporte por que uma pessoa deve olhar, conforme o MOTIVO informado:
  - "id_inexistente": diga que o id do chamado não existe no sistema de tickets;
  - "fora_da_alcada": diga o que o cliente pediu (encerrar um chamado ou mudar a prioridade);
  - "pedido_ja_feito": diga que o chamado já recebeu um pedido de informação e o que ainda falta;
  - "divergencia_relato_log": escreva os dois lados, nomeando os serviços: o que o cliente relata e o que o log anexado mostra;
  - "sem_procedimento": diga o que foi buscado e que nenhum procedimento corresponde;
  - "score_abaixo_do_limiar": diga qual procedimento foi encontrado, o score, e que não é seguro agir sozinho. Se o procedimento veio com RESSALVA, diga que ele não cobre o caso relatado.

Regras:
- Use apenas as informações recebidas. Não invente causa, solução, prazo nem procedimento.
- Não prometa correção, prazo ou prioridade.
- Se a mensagem trouxer "ERRO DA TENTATIVA ANTERIOR", reescreva o texto corrigindo exatamente o que o erro aponta.

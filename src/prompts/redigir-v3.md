<!--
prompt:            redigir (nó `redigir` do grafo, src/grafo.py)
versão:            v3, de 12/10/2026 (o v1 e o v2 continuam em redigir-v1.md e redigir-v2.md)
carimbo:           prompt × modelo × parâmetros × resultado
                   redigir-v3 × ministral-8b-latest × temperature=0, 12/10/2026. EM USO desde
                   esta data. Três execuções dos 8 casos (logs/grafo-redigir-v3-1/ a -3/), contra
                   três do v2 com o mesmo código (logs/grafo-pedido-padrao-1/ a -3/);
                   docs/prompts.md §2.3.
                     verificador      8 de 8 nas três (v2: 8 de 8 nas três)
                     nó `validar`     nenhuma redação reprovada, em 21 (v2: nenhuma, em 21)
                     custo, medido    119 tokens de entrada a menos em cada execução que redige
                                      (7 dos 8 casos); a rodada passou de 13.855 a 13.912 tokens
                                      para 13.122 a 13.191

o que mudou do v2: saiu UMA regra, a do desfecho "devolver_cliente" (466 caracteres). O resto do
                   texto é o do v2, sem alteração.
por que saiu:      desde 12/10/2026 o pedido ao cliente é texto padrão do código
                   (grafo.PEDIDO_AO_CLIENTE), e o nó `redigir` não chama o modelo nesse desfecho
                   (docs/prompts.md §2.2). A regra ia ao modelo nas outras redações sem servir a
                   nenhuma.

técnica:           zero-shot, geração de texto com saída estruturada (JSON), sem ferramentas.
contrato de saída: um objeto JSON com um campo, validado em código (classe `Redacao`):
                     texto   o resumo do chamado interno ou a mensagem do encaminhamento
                   O nó `validar` (código) confere o tamanho mínimo. Reprovado, o texto volta UMA
                   vez com o erro; na segunda reprovação a execução termina como erro_fatal.
o modelo NÃO decide aqui: o desfecho, o procedimento, o time e a prioridade. Chegam decididos.
o modelo NÃO escreve:     o pedido de informação ao cliente. Este prompt redige quatro dos cinco
                          desfechos: abrir_chamado_interno, anotacao_interna, fila_comercial e
                          fila_humana. Nenhum desses textos chega ao cliente.

O que cada regra impede:
  "o desfecho já foi decidido"     impede o modelo de trocar a ação ao redigir
  afirmação do cliente × histórico impede o resumo repetir "terceira vez" como fato (TKT-0003)
  divergência: relato × log        a fila humana precisa dos dois lados escritos (TKT-0002)
  "use só o que recebeu"           impede causa, solução ou prazo inventados

LIMITE HONESTO: o CONTEÚDO do texto não tem verificador. Dois defeitos medidos com o v1 e o v2
  continuam sem regra aqui (docs/prompts.md §2.1): o resumo que diz que um score acima do limiar
  "não atinge o limiar" (TKT-0003) e o domínio inventado na anotação (TKT-0001).
-->
Você é a etapa de REDAÇÃO de um sistema de triagem de chamados de suporte de uma empresa de hospedagem de servidores. O desfecho do chamado JÁ FOI DECIDIDO pelo sistema e não pode ser trocado. Você só escreve o texto que será gravado com ele.

Responda SOMENTE com um objeto JSON, sem texto antes nem depois, com exatamente um campo:

{"texto": "..."}

O que escrever, conforme o DESFECHO informado:

- "abrir_chamado_interno": o texto é o RESUMO do problema para o time interno. Objetivo, com o serviço afetado, o sintoma e o que o log anexado mostra, se houver. Se o cliente exigir prioridade ou disser quantas vezes o problema ocorreu, escreva o que o histórico do sistema confirma, citando o id do chamado anterior que aparece no histórico (por exemplo, "o histórico confirma 1 ocorrência anterior, INC-0001"), e diga que a outra informação é afirmação do cliente. Nunca repita a afirmação do cliente como fato.
- "anotacao_interna": o texto é a CORREÇÃO SUGERIDA para o analista de suporte validar e executar, tirada da solução do procedimento informado.
- "fila_comercial": o texto diz o que o cliente pediu, para o time comercial.
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

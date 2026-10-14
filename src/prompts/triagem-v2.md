<!--
prompt:            triagem (nó `triagem` do grafo, src/grafo.py)
versão:            v2, de 13/10/2026. Variante do teste da regra da frase (docs/prompts.md §3.7),
                   medida e NÃO ADOTADA: o prompt em uso é o triagem-v1.md. Este arquivo foi o
                   prompt carregado pelo grafo por algumas horas, da noite de 13/10 à madrugada
                   de 14/10/2026, entre as duas passagens do teste, sem commit.
                   Como rodar: python src/main.py --todos --auto-aprovar --rodada NOME
                               --prompt-triagem triagem-v2.md
carimbo:           prompt × modelo × parâmetros × resultado
                   triagem-v2 × ministral-8b-latest × temperature=0, 13 e 14/10/2026, commit
                   "6116341 + alterações locais". Três execuções dos 44 casos
                   (logs/regra-da-frase/triagem-v2-1 a -3), intercaladas com três do v1
                   (logs/regra-da-frase/triagem-v1-1 a -3).
                     verificador      39, 40 e 39 de 44 (v1: 40 de 44 nas três)
                     TKT-0134         marcado como divergência e mandado à fila humana em duas de
                                      três; o esperado é abrir chamado interno (v1: certo nas três)
                     classe           igual à do v1 nos 43 casos que passam pela triagem
                     divergência      TKT-0123 e TKT-0124 marcados nas três (v1: 1 e 2 de 3)
                     custo, medido    73.767 a 73.786 tokens de entrada por rodada (v1: 74.876 a
                                      74.888): de 18 a 31 a menos em cada execução com triagem
                   ANTES, nos 40 casos que o gabarito tinha (13/10/2026): três execuções em
                   logs/grafo-triagem-v2-1/ a -3/, 36 de 40 nas três, com os mesmos desfechos do
                   v1; e duas com o mesmo texto, sob o nome triagem-v1-sem-frase.md
                   (logs/regra-da-frase/triagem-v1-sem-frase-a e -b), também 36 de 40. Foi com
                   esses números que a primeira passagem concluiu que a frase saía.

o que mudou do v1: saiu UMA frase, a última da regra do campo log_aponta_outro_servico (102
                   caracteres): "Uma afirmação do cliente que o histórico não confirma ("é a
                   terceira vez") NÃO é divergência: é false." O resto do texto é o do v1, sem
                   alteração (conferido com diff, descontado o cabeçalho).
por que NÃO foi adotado: pelo critério do enunciado, a frase volta se, sem ela, aparece o que ela
                   impedia. Apareceu: num chamado com log que confirma o relato e uma afirmação
                   do cliente que o histórico não confirma (TKT-0134), a triagem marcou divergência
                   em duas de três execuções. O prompt não encolheu sem perder comportamento.
                   Os 40 casos da primeira passagem não tinham um caso assim.

Cabeçalho completo (técnica, contrato, o que cada regra impede): triagem-v1.md.

LIMITE HONESTO: três execuções por versão, e a diferença está em um caso de quatro escritos para
  o teste. O erro foi para o lado seguro (fila humana, nenhum chamado indevido).
-->
Você é a etapa de TRIAGEM de um sistema de suporte de uma empresa de hospedagem de servidores. Você recebe o texto que o cliente escreveu ao abrir um chamado e o registro do chamado (log anexado, plano e histórico de chamados internos do cliente). Você NÃO resolve o problema, NÃO escolhe o desfecho e NÃO escreve ao cliente: só classifica.

Responda SOMENTE com um objeto JSON, sem texto antes nem depois, com exatamente estes campos:

{"classe": "...", "log_aponta_outro_servico": true ou false, "termos_busca": ["..."], "justificativa": "..."}

classe: uma de quatro, em minúsculas e sem acento:
- "tecnico": problema de servidor, site, certificado, permissão de arquivos, acesso, e-mail, DNS, backup;
- "comercial": planos, preços, upgrade, contratação, cobrança;
- "insuficiente": o texto não diz qual serviço é afetado nem qual o sintoma;
- "fora_da_alcada": o cliente pede APENAS para encerrar um chamado ou para mudar a prioridade de um chamado, sem relatar um problema técnico. Um problema técnico acompanhado de exigência de prioridade continua sendo "tecnico".

log_aponta_outro_servico: true SOMENTE quando existe log anexado E ele aponta outro serviço ou outra causa, diferente do que o cliente relata (o cliente descreve o sintoma que vê; o log mostra a causa em outro lugar). Sem log anexado, ou com log que confirma o relato, é false.

termos_busca: só quando a classe é "tecnico". De 2 a 5 palavras soltas em português, minúsculas e sem acento, tiradas do relato, que nomeiem o serviço e o sintoma. Não escreva frases. Nas outras classes, devolva uma lista vazia.

justificativa: UMA frase dizendo por que essa classe, com base no que está escrito. Não invente causa nem solução.

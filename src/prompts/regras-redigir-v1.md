<!--
arquivo:           regras aprendidas do nó `redigir` (a MEMÓRIA PROCEDURAL do grafo, docs/memoria.md §5)
versão:            v1, de 12/10/2026. MEDIDO E NÃO ADOTADO: o arquivo em uso é o regras-redigir-v2.md
como é usado:      o texto abaixo deste bloco é anexado ao fim do prompt de sistema do nó `redigir`
                   (grafo._regras_aprendidas). Vai em TODA chamada do nó: é regra, não se busca.
                   `--sem-memoria` não o carrega. O nome do arquivo vai ao campo `prompt` do log.
quem escreve:      só uma pessoa, à mão, neste arquivo. O modelo e o código não escrevem regra.
                   Uma regra por versão: regra nova = regras-redigir-v2.md, medida em rodada própria.
o que é recusado:  regra que cite um cliente (CLI-00) ou um chamado (TKT-0000, INC-0000). A regra
                   nasce do erro num chamado e não pode carregar o titular dele (enunciado §5.4).
                   A conferência é em código, na carga; recusada, a execução termina em erro_fatal.

carimbo:           prompt × modelo × parâmetros × resultado
                   redigir-v3 + regras-redigir-v1 × ministral-8b-latest × temperature=0, 12/10/2026,
                   commit "c849ce1 + alterações locais". Três execuções dos 8 casos
                   (logs/grafo-regras-v1-1/ a -3/), contra as três sem regra
                   (logs/grafo-redigir-v3-1/ a -3/); docs/memoria.md §5.1.
                     verificador        8 de 8 nas três (sem regra: 8 de 8 nas três)
                     domínio inventado  em 2 de 3 rodadas (sem regra: 1 de 3). A REGRA NÃO FUNCIONOU.
                                        Nas duas, o texto traz o domínio inventado e, colada nele,
                                        a frase que a regra mandava pôr no lugar ("domínio não
                                        informado").
                     custo, medido      91 tokens de entrada a mais em cada execução que redige
                                        (7 dos 8 casos); a rodada foi de 13.122 a 13.191 tokens
                                        para 13.781 a 13.876

AS REGRAS, e de onde cada uma veio:

  R1 (12/10/2026)  só citar domínio, IP, servidor ou banco que veio nas informações recebidas
     o que impede:  a anotação que manda o analista conferir um domínio que ninguém informou.
     origem:        leitura das rodadas pelo grupo (docs/prompts.md §2.1 e §2.3). No chamado do
                    certificado SSL vencido, a anotação citou "acmecontabilidade.com.br", que não
                    está no relato, no log anexado nem no banco: o modelo o montou a partir do
                    nome do cliente. Apareceu com o redigir-v1, o v2 e o v3; com o v3, em 1 de 3
                    rodadas (logs/grafo-redigir-v3-3/, o log do caso simples).
     EXCEÇÃO DECLARADA à política do docs/memoria.md §1.4 (regra só depois de 3 correções do
                    mesmo padrão, vindas do analista): esta veio da leitura do grupo, porque 8
                    chamados simulados não produzem três correções de um analista de verdade.
     como conferir: python conferir_regras.py logs/NOME   (domínio do texto que não está na entrada)
-->
Regras aprendidas em execuções anteriores (valem para todos os desfechos):
- Só cite domínio, endereço IP, nome de servidor ou nome de banco de dados que apareça, escrito igual, nas informações recebidas. Não monte um domínio a partir do nome do cliente e não dê exemplo de domínio. Se o texto precisar de um e ele não foi informado, escreva "domínio não informado".

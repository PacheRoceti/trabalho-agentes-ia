<!--
arquivo:           regras aprendidas do nó `redigir` (a MEMÓRIA PROCEDURAL do grafo, docs/memoria.md §5)
versão:            v2, de 12/10/2026 (o v1 continua em regras-redigir-v1.md: medido e NÃO adotado)
como é usado:      o texto abaixo deste bloco é anexado ao fim do prompt de sistema do nó `redigir`
                   (grafo._regras_aprendidas). Vai em TODA chamada do nó: é regra, não se busca.
                   `--sem-memoria` não o carrega. O nome do arquivo vai ao campo `prompt` do log.
quem escreve:      só uma pessoa, à mão, neste arquivo. O modelo e o código não escrevem regra.
o que é recusado:  regra que cite um cliente ou um chamado pelo identificador (enunciado §5.4).
                   A conferência é em código, na carga; recusada, a execução termina em erro_fatal.

o que mudou do v1: a MESMA regra R1, com outra redação. O v1 proibia ("não monte um domínio a
                   partir do nome do cliente") e dava uma frase para pôr no lugar ("domínio não
                   informado"). Medido, não funcionou: o domínio inventado apareceu em 2 de 3
                   rodadas (sem a regra, 1 de 3), e a frase do lugar passou a aparecer colada ao
                   domínio inventado. O v2 diz só o que escrever.

carimbo:           prompt × modelo × parâmetros × resultado
                   redigir-v3 + regras-redigir-v2 × ministral-8b-latest × temperature=0, 12/10/2026,
                   commit "c849ce1 + alterações locais". EM USO desde esta data. Três execuções
                   dos 8 casos (logs/grafo-regras-v2-1/ a -3/), contra as três sem regra
                   (logs/grafo-redigir-v3-1/ a -3/); docs/memoria.md §5.1.
                     verificador        8 de 8 nas três (sem regra: 8 de 8 nas três)
                     domínio inventado  em 0 de 3 rodadas (sem regra: 1 de 3; com o v1: 2 de 3)
                     nó `validar`       nenhuma redação reprovada, em 21
                     custo, medido      55 tokens de entrada a mais em cada execução que redige
                                        (7 dos 8 casos); a rodada foi de 13.122 a 13.191 tokens
                                        para 13.400 a 13.511
                   LIMITE HONESTO: três rodadas contra uma base de 1 em 3 não separam a regra do
                   acaso. E a regra tem um efeito que ninguém pediu: a expressão "o domínio do
                   cliente" passou a aparecer em textos que não falavam de domínio (por exemplo,
                   "o domínio do cliente apresenta falha no upload"). A expressão está em 3 a 5
                   dos 7 textos de cada rodada; sem a regra, em nenhum.

A REGRA, e de onde veio:

  R1 (12/10/2026)  falar do domínio sem escrever um endereço que ninguém informou
     o que impede:  a anotação que manda o analista conferir um domínio que não está no chamado.
     origem:        leitura das rodadas pelo grupo (docs/prompts.md §2.1 e §2.3): no chamado do
                    certificado SSL vencido, a anotação citou um domínio montado a partir do nome
                    do cliente, com o redigir-v1, o v2 e o v3.
     EXCEÇÃO DECLARADA à política do docs/memoria.md §1.4 (regra só depois de 3 correções do
                    mesmo padrão, vindas do analista): esta veio da leitura do grupo, porque 8
                    chamados simulados não produzem três correções de um analista de verdade.
     como conferir: python conferir_regras.py logs/NOME   (domínio do texto que não está na entrada)
-->
Regra aprendida em execuções anteriores (vale para todos os desfechos):
- Quando o texto falar do domínio do cliente e o endereço não estiver escrito nas informações recebidas, escreva apenas "o domínio do cliente", sem endereço nenhum.

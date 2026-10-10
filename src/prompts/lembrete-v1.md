<!--
prompt:            lembrete-de-desfecho
versão:            v1  (texto que estava na constante LEMBRETE de src/agente.py; movido para arquivo
                   em 10/10/2026, sem alteração de conteúdo)
onde é usado:      no laço (src/agente.py): quando o modelo encerra sem ter registrado desfecho, o
                   código envia este texto como mensagem de usuário, até MAX_LEMBRETES (2) vezes.
                   Sem efeito depois disso, a execução termina como erro_fatal.
técnica:           instrução direta (zero-shot), sem exemplos.
contrato de saída: uma chamada de ferramenta de escrita (abrir_chamado_interno ou
                   registrar_encaminhamento). Texto sem chamada de ferramenta conta como falha.
o que impede:      o modelo narrar a ação ("registrei", "encaminhei") sem chamar a ferramenta, visto
                   no TKT-0999 nas rodadas 1 e 2 e no TKT-0003 na rodada 1.
-->
Você ainda NÃO registrou nenhum desfecho: escrever no texto que registrou ou encaminhou não registra nada. Chame agora a ferramenta de escrita correta (abrir_chamado_interno ou registrar_encaminhamento), seguindo o procedimento.

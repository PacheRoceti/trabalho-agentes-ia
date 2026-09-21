| Caso | ministral-3b-latest | ministral-8b-latest | ministral-14b-latest |
|---|---|---|---|
| TKT-0001 (simples) | FALHOU: desfecho 'fila_humana' em vez de 'anotacao_interna'; kb_id 'None' em vez de 'KB-101' | OK | OK |
| TKT-0002 (divergencia) | OK | OK | OK |
| TKT-0003 (escalonamento_reincidencia) | FALHOU: desfecho 'fila_humana' em vez de 'abrir_chamado_interno'; kb_id 'None' em vez de 'KB-102'; time_destino 'None' em vez de 'Infraestrutura'; prioridade 'None' em vez de 'P1'; 0 chamado(s) interno(s) gravado(s) para TKT-0003 | FALHOU: desfecho 'fila_humana' em vez de 'abrir_chamado_interno'; kb_id 'None' em vez de 'KB-102'; time_destino 'None' em vez de 'Infraestrutura'; prioridade 'None' em vez de 'P1'; 0 chamado(s) interno(s) gravado(s) para TKT-0003 | FALHOU: desfecho 'fila_humana' em vez de 'abrir_chamado_interno'; kb_id 'None' em vez de 'KB-102'; time_destino 'None' em vez de 'Infraestrutura'; prioridade 'None' em vez de 'P1'; 0 chamado(s) interno(s) gravado(s) para TKT-0003 |
| TKT-0999 (registro_inexistente) | OK | OK | OK |
| TKT-0006 (correspondencia_parcial) | OK | OK | FALHOU: desfecho 'abrir_chamado_interno' em vez de 'fila_humana'; 1 chamado(s) interno(s) gravado(s) para TKT-0006 |
| **Acertos** | 3 de 5 | 4 de 5 | 3 de 5 |
| **Tokens médios por execução** | 9,062 | 7,294 | 6,999 |
| **Chamadas ao modelo (média)** | 4.8 | 4.0 | 3.8 |
| **Custo médio por execução (US$)** | 0.00091 | 0.00109 | 0.00140 |
| **Latência média (s)** | 3.4 | 5.0 | 7.5 |

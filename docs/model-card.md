# Model card: Agente de Triagem e Abertura de Chamado Interno

**Revisão de 21/11/2026 (Parte 3, item 2).** Este card descreve a **versão 1.1.0** do sistema
(`src/versao.py`), commit `fa74011`. As medições são as rodadas da suíte de avaliação em
`evals/resultados/` (`docs/evals.md` §4). A primeira versão do card foi escrita na Parte 2, sobre o
commit `77757ea` e a execução de referência `logs/grafo-44-3/`. O que mudou desde então está no
campo 12 e em `docs/mudancas.md`.

**Como ler a evidência.**
- **Linhas de código.** `arquivo:linha` se refere ao commit `925b464`, cujo `src/` e `tests/` são os do `fa74011`.
- **Testes.** Os testes são citados pelo nome: `python -m unittest discover -s tests` roda os **214** testes offline, sem chave e sem rede. Todos passaram em 21/11/2026: 206 sobre o `925b464`, e 214 com as correções da devolutiva da Parte 2 (`docs/mudancas.md` §1), ainda não commitadas quando esta linha foi escrita.
- **Lacunas.** Um campo sem evidência leva a marca **LACUNA** com um número. A seção final reúne todas, cada uma com a correção proposta.
- **Lacunas resolvidas.** Ficam riscadas, com a data e o que as resolveu.

---

## 1. Identificação

| | Afirmação | Evidência |
|---|---|---|
| Nome | Agente de Triagem e Abertura de Chamado Interno | `README.md` L1 |
| Versão | **1.1.0**, commit `fa74011`. A versão vai a cada trace, no atributo `triagem.versao` | `src/versao.py`; atributo da raiz em `src/telemetria.py:123` (`telemetria.raiz`) |
| Data | 20/11/2026 (a rodada da 1.1.0) | `evals/resultados/v1.1.0-2026-11-20-2244/resultado.json` |
| Integrantes | Daniel Filho Oliveira Lima · Pedro Gustavo de Campos Teixeira Silva · Pedro Roceti Pache | `README.md` L3 |
| Responsável quando algo dá errado | Pedro Roceti Pache | **LACUNA L1**: o repositório lista autores, e não responsáveis por papel |

## 2. Finalidade

**Afirmação.** O agente faz, nesta ordem:
1. Recebe o texto de um chamado externo de uma empresa de hospedagem.
2. Consulta o registro, o log anexado e o histórico.
3. Classifica o assunto e consulta a base de conhecimento.
4. Dá um de cinco desfechos:
   - abrir chamado interno, com confirmação do analista;
   - anotar a correção sugerida;
   - encaminhar ao comercial;
   - pedir informação ao cliente, com confirmação do analista;
   - mandar à fila humana.

**Evidência.**
- O caso de negócio: `docs/case.md` L227.
- Os desfechos possíveis no código: nó `decidir`, em `src/grafo.py:430-461`.
- Na rodada da 1.1.0, os 44 chamados terminaram em 17 `fila_humana`, 11 `abrir_chamado_interno`, 10 `anotacao_interna`, 4 `fila_comercial` e 2 `devolver_cliente`. A contagem é do atributo `triagem.desfecho`, lida por `python -m evals.metricas` (`docs/observabilidade.md` §6.1).

**Fora de escopo.** O agente não deve ser usado para:

| Afirmação | Evidência |
|---|---|
| Executar correção no ambiente do cliente | ausência de ferramenta: `src/ferramentas.py:3-12` e `FUNCOES`, em `src/ferramentas.py:318` |
| Encerrar um chamado ou alterar a prioridade de um existente | Ausência de ferramenta. O grafo só grava pelo nó `gravar` (`src/grafo.py:621`), por meio de `db.abrir_chamado`, `db.registrar_encaminhamento`, `db.registrar_pedido_cliente` e `db.avisar_gestor`. A última é chamada no prazo vencido de um P1 e no teto do C3 |
| Resolver o problema do cliente, ou conversar com ele além do pedido de informação | `docs/case.md` L227 |
| Processar chamados reais enquanto a conta do provedor for do plano gratuito | Decisão do grupo, em `docs/modelos.md` L46. **É uma declaração, e não um controle:** nada no código impede |

## 3. Autoridade

A especificação segue o formato da nota 01 da aula 12 (§8). A coluna **Onde** diz em que ponto o
limite é aplicado: ausência de ferramenta, código, credencial, plataforma ou prompt. Um limite que
fica só no prompt conta como lacuna.

| Item | Especificação | Onde | Evidência |
|---|---|---|---|
| Escopo de leitura | `consultar_ticket`, `buscar_base_conhecimento` | código | `FUNCOES`, `src/ferramentas.py:318` |
| Escopo de escrita | `abrir_chamado_interno` (irreversível), `registrar_encaminhamento` (reversível), o pedido ao cliente | código | `gravar`, `src/grafo.py:621` |
| Quem escolhe a ação | o **código** escolhe o desfecho; o modelo só classifica, confere a ressalva e redige | código | `decidir`, `src/grafo.py:430-461`; cabeçalho de `src/grafo.py:8-19` |
| Proibido: executar correção, encerrar chamado, reclassificar | não existe ferramenta para isso | ausência de ferramenta | `src/ferramentas.py:3-12`. **LACUNA L2**: nenhum teste falha se alguém acrescentar uma ferramenta de escrita |
| Proibido: agir com correspondência abaixo do limiar de 0,5 | o chamado vai à fila humana | código | `src/grafo.py:454-455`; teste `test_o_grafo_nao_age_quando_o_cosseno_fica_abaixo_do_limiar` |
| Proibido: agir quando o log aponta outro serviço | fila humana antes de olhar o score | código, mas o **sinal** vem do modelo | `src/grafo.py:448-451`. Se o modelo não marcar a divergência, o código não a vê: é o que aconteceu no `TKT-0136` da 1.0.0 (campo 11) |
| **Proibido: escrever ao analista um comando de terminal que o guia recuperado não traz** (controle **C1**, desde a 1.1.0) | o `validar` recusa o texto. Depois de `MAX_REDACOES` (2) recusas, a execução termina em `erro_fatal` e nada é gravado (*fail-closed*) | código | `src/grafo.py:528`, regra em `_comando_fora_do_guia`, `src/grafo.py:1328`; testes `test_c1_comando_plantado_no_log_nao_chega_ao_que_o_analista_executa` e `test_c1_o_que_passa_comando_do_guia_texto_sem_comando_correcao_e_edicao_do_analista`; medido nos casos hostis: 0 textos com o conteúdo plantado na 1.1.0, contra 2 de 2 na 1.0.0 (`docs/evals.md` §4.4) |
| Time e prioridade | Vêm do guia da base, e a reincidência na janela de 30 dias sobe um nível. O modelo e o cliente não escolhem | código | `src/db.py:435-479`; teste `test_reincidencia_sobe_prioridade_no_codigo` |
| A abertura não duplica | a chave ticket+guia é UNIQUE | código e plataforma (UNIQUE no SQLite) | `src/db.py:451-479`; `dados/seed.sql` (`chave_idempotencia ... UNIQUE`); teste `test_idempotencia_nao_duplica_chamado` |
| Pedido ao cliente | no máximo 1 por chamado; texto padrão do código; sem termos internos | código | `src/grafo.py:94-104`, `:442-447`; `TERMOS_INTERNOS`, `src/ferramentas.py:46`; testes `test_um_pedido_de_informacao_por_chamado` e `test_h2_o_envio_e_idempotente_pelo_chamado` |
| "Envio" ao cliente | **não há canal**: enviar é gravar a linha com `enviado_em` | código | `db.registrar_pedido_cliente`, `src/db.py:520-527` |
| Credencial do modelo | uma chave (`OPENAI_API_KEY`) para chat **e** embedding | credencial | `.env.example`; `src/vetorial.py:5-6`. **LACUNA L3**: não é uma identidade própria do agente, e a conta dona da chave é de um integrante |
| Credencial do banco | **nenhuma**: o processo abre o SQLite com acesso total a todas as tabelas | — | `db.conectar`, `src/db.py:208`. **LACUNA L4**: todo limite de escrita está só no código |
| Limite por execução | Tetos de 8 passos, 30.000 tokens, US$ 0,05 e 90 s (`Orcamento`), e 20 superpassos | código | `src/agente.py:184-191`; `src/grafo.py:71`, `_teto` em `:216`; testes `test_teto_de_tokens_termina_antes_da_redacao` e `test_limite_de_superpassos_e_declarado_no_codigo`. Medido: US$ 0,00043 por execução, nenhuma com orçamento esgotado (`docs/observabilidade.md` §6) |
| Repetição da mesma ação (detector de laço, desde 21/11/2026) | o passo que repete outro da trajetória (mesmo nó, mesmos argumentos, mesmo resultado) encerra a execução em `erro_fatal`; nada executa depois, além do `finalizar` (*fail-closed*) | código | `grafo.passo_repetido`, no fim de `src/grafo.py`; testes `test_a_mesma_redacao_repetida_e_laco_e_termina_sem_gravar` e `test_depois_do_laco_nenhum_no_executa_alem_do_finalizar` (`tests/test_devolutiva.py`); `docs/mudancas.md` §1 |
| Limite por janela (dia ou mês) | não existe | — | **LACUNA L5**: o limite de requisições do plano é do provedor, e não configuração nossa |
| **Retomada depois de uma queda** (controle **C3**, desde a 1.1.0) | Cada execução interrompida é retomada no máximo `MAX_FALHAS_DE_RETOMADA` (3) vezes com falha. Depois disso não é retomada de novo, o gestor é avisado e nenhum desfecho é gravado por essa rotina (*fail-closed*) | código | `retomar_interrompidas`, `src/grafo.py:1384`; `src/db.py:920-952`; testes `test_c3_execucao_que_falha_sempre_para_no_teto_e_o_gestor_e_avisado` e `test_c3_o_que_passa_falha_passageira_e_retomada_normalmente` |
| Limiar de aprovação humana | **Toda** abertura de chamado interno (H1) e **todo** pedido ao cliente (H2) esperam o analista, com prazo de 20 min. O silêncio não executa a ação | código | `PRAZO_CONFIRMACAO_MIN`, `src/ferramentas.py:29`; `interrupt`, `src/grafo.py:596`; testes `test_sem_resposta_do_analista_o_grafo_pausa_no_interrupt` e `test_prazo_vencido_de_p1_vai_a_fila_humana_e_avisa_o_gestor` |
| **A aprovação automática só para medir** (controle **C2**, desde a 1.1.0) | `--auto-aprovar` sem `--rodada` nem `--todos` é recusado antes de qualquer execução | código | `src/main.py:409`, `erro_do_auto_aprovar`, `src/main.py:567`; testes `test_c2_auto_aprovar_avulso_e_recusado_antes_de_executar` e `test_c2_o_que_passa_auto_aprovar_para_medir_e_o_usuario_que_aprova` |
| Quando um controle falha | O modelo indisponível dá `erro_fatal` e nada é gravado (*fail-closed* na escrita). O C1 e o C3 também são *fail-closed*. O embedding indisponível faz a busca recuar para a busca por palavra (*fail-open* na leitura, sem erro: é o modo de falha silenciosa F3 de `docs/observabilidade.md` §3) | código | `src/grafo.py:239-247`; `src/vetorial.py:143-151`. **LACUNA L6**: não há teste do caminho de API indisponível |
| Quem pode suspender o agente | **Ninguém, por um mecanismo do sistema.** Na prática, quem tem a máquina para o vigia (`src/vigiar_prazos.py`) e não roda o `main.py`, mas não há chave, flag nem registro de suspensão | — | **LACUNA L7** |
| Instrução no prompt | as regras de formato e de "não decidir o desfecho" dos prompts | prompt | `src/prompts/triagem-v1.md`, `redigir-v3.md`. Nenhum limite desta tabela está só no prompt |

## 4. Ferramentas e integrações

| Ferramenta ou integração | Permissão | Evidência |
|---|---|---|
| `consultar_ticket` | leitura (`tickets_externos`, `chamados_internos`) | `src/ferramentas.py:85` |
| `buscar_base_conhecimento` | leitura (`kb_artigos`, `kb_vetores`), mais o **envio do relato ao provedor** para o embedding | `src/vetorial.py:138-151` |
| `abrir_chamado_interno` | escrita irreversível (`chamados_internos`) | `src/db.py:451-479` |
| `registrar_encaminhamento` | escrita (`encaminhamentos`) | `src/db.py:500` |
| API de chat da Mistral (compatível com `openai`) | envio a terceiro: o texto, o cliente, o plano, o log anexado e o histórico | `src/grafo.py:273-286` |
| API de embedding (`mistral-embed`) | envio a terceiro: o relato do cliente | `src/vetorial.py:29` |
| OpenTelemetry (SDK local) | escrita do trace em arquivo, ao lado do log; nada sai da máquina | `src/telemetria.py`; `requirements.txt` (`opentelemetry-api`, `-sdk`, `-semantic-conventions`, versões fixas) |
| Servidor MCP, multiagente, multimídia | **nenhum**: as frentes opcionais da Parte 3 não foram usadas | — |

## 5. Modelo e provedor

| | Afirmação | Evidência |
|---|---|---|
| Modelo | `ministral-8b-2512`, temperatura 0 | atributos `gen_ai.request.model` e `gen_ai.request.temperature` da raiz dos traces de `evals/resultados/v1.1.0-2026-11-20-2244/` |
| Versão datada | **Fixada** para o chat: as rodadas da Parte 3 registram a versão datada, e não o alias. ~~LACUNA L8~~, resolvida em 17/10/2026 | idem |
| Embedding | `mistral-embed`, **pelo alias** | `src/vetorial.py:29`. **LACUNA L32**: o fornecedor pode mover o alias e mudar todos os scores sem uma linha do projeto mudar (`docs/seguranca.md`, ASI04) |
| Provedor | Mistral AI, plano gratuito: 2 requisições por minuto no chat, lidas dos cabeçalhos da resposta | `docs/modelos.md` L19-29; `docs/evals.md` §4.2 |
| Região de processamento | não verificada | **LACUNA L9** |
| Retenção e uso para treino | o plano gratuito **pode** usar os dados para treino; as fontes divergem | `docs/modelos.md` L46, L245. **LACUNA L10**: as fontes são agregadores, e não os termos da Mistral |

## 6. Dados

**Todos os dados do repositório são simulados**: clientes, domínios e servidores fictícios
(`dados/seed.sql` L2-3). Os IPs são da faixa de documentação 203.0.113.0/24 e os e-mails usam o domínio
reservado `.example`. Mesmo assim, o sistema foi desenhado para receber texto livre de cliente, que em
produção traz nome, e-mail, IP e trechos de log de usuários finais.

**O mapa completo de onde o dado pessoal entra, fica e sai** está em `docs/seguranca.md` §5.1.
Para cada lugar, o mapa traz o dado, a finalidade, a base legal e o prazo de guarda. Os lugares são:
- a entrada;
- o prompt e o embedding enviados ao provedor;
- o checkpoint e as pendências;
- o chamado interno e o encaminhamento;
- as memórias episódica e semântica;
- o log e o trace.

O que a memória não guarda, e o ponto do código que impede a gravação, está em §5.2 do mesmo documento.
Neste card ficam as lacunas que aquele mapa aponta:

| Lugar | Lacuna |
|---|---|
| Entrada, prompt, embedding, checkpoint, pendências, chamado, encaminhamento, memórias, log e trace | **LACUNAS L18 a L26**: nenhuma base legal (LGPD, art. 7º) está declarada pelo responsável. As candidatas estão na seção Lacunas |
| Log e trace (`logs/**`, `evals/resultados/**`) | **LACUNA L11**: o texto inteiro do cliente fica guardado sem prazo, num repositório git |
| Checkpoint e pendência nunca resolvidos | **LACUNA L12**: não são removidos |
| Log anexado | **LACUNA L27**: vai inteiro ao provedor |

## 7. Avaliação

| | Afirmação | Evidência |
|---|---|---|
| Golden dataset | **v1.1.0**, 47 casos: os 44 da v1.0.0 mais 3 hostis. Cada caso tem `origem`, `classe` (5 classes, de A a E) e `por_que_existe`. Há casos de recusa: fila humana, id inexistente, fora de escopo. Os sintéticos têm revisor declarado. ~~LACUNA L28~~ (suíte sem versão), resolvida em 20/11/2026: o dataset é versionado | `evals/dataset/v1.0.0.json`, `v1.1.0.json`; `docs/evals.md` §1 |
| Níveis | determinístico, trajetória e resultado (o banco antes e depois); cada propriedade com a justificativa do nível | `evals/checagens.py`; `docs/evals.md` §2 |
| Resultado da versão em uso (1.1.0) | **40 de 44 (90,9%)**, pass^1. As 4 falhas são as mesmas desde 12/10/2026 (`TKT-0105`, `TKT-0106`, `TKT-0111`, `TKT-0132`), todas à fila humana, e nenhum chamado foi aberto indevidamente | `evals/resultados/v1.1.0-2026-11-20-2244/`; `docs/evals.md` §4.3 |
| Comparação com a versão anterior (1.0.0) | A 1.0.0 deu 39 de 44 (88,6%), com o `TKT-0136` aberto indevidamente. Nenhum caso passou a falhar na 1.1.0. A diferença não é atribuída aos controles, porque o ruído entre repetições não foi medido | `python -m evals.comparar evals/resultados/v1.0.0-2026-11-20-2129 evals/resultados/v1.1.0-2026-11-20-2244`; `docs/evals.md` §4.3 |
| Casos hostis (a mudança desta entrega) | Os textos com o conteúdo plantado foram de 2 de 2 na 1.0.0 para 0 na 1.1.0. O custo foi 1 `erro_fatal` (`TKT-0138`) | `evals/resultados/v1.0.0-hostis-2026-11-21/`, `v1.1.0-hostis-2026-11-21/`; `docs/evals.md` §4.4 |
| SLO de qualidade | pelo menos 75% das execuções com desfecho certo; medido **90,9%** na 1.1.0, com 36% do orçamento de erro consumido | `docs/observabilidade.md` §8 |
| Repetições | **1 por versão** (pass^1), por causa do limite do plano. O pass^3 previsto não foi medido | `docs/evals.md` §4.2 |
| Concordância do juiz com humano | **O juiz existe, mas não foi validado.** A rubrica `evals/prompts/juiz-v1.0.0.md` confere a fidelidade da correção ao guia, e os 22 itens estão separados para rótulo humano. Não há rótulo, limiar nem matriz ainda, e o juiz não foi rodado | `evals/juiz/rotulos-v1.0.0.json` (`rotulado_por: null`); `docs/evals.md` §3. **LACUNA L13** |
| Testes offline (código, sem modelo) | 214 testes passam com as correções da devolutiva (206 no `925b464`) | `python -m unittest discover -s tests`, rodado em 21/11/2026: `Ran 214 tests`, `OK` |

## 8. Limites conhecidos

| Afirmação | Evidência |
|---|---|
| Guias de segurança (KB-112) com relato em linguagem de usuário vão à fila humana, em vez de abrir chamado: o `conferir_ressalva` lê a ressalva "ataque" onde ela não cabe | `TKT-0105` e `TKT-0106`, nas duas versões |
| A busca não acha o guia "anotar" quando o relato vem com exigência de prioridade | `TKT-0111` |
| Um relato que diz o serviço, mas não o sintoma, vai à fila humana em vez de pedir informação. O rótulo é discutido pelo próprio grupo | `TKT-0132`; `_nota` do caso em `dados/gabarito.json` |
| A divergência entre relato e log depende de o modelo marcar o sinal. Quando ele não marca, o chamado é aberto | `src/grafo.py:448-451`; `TKT-0136` na 1.0.0 (campo 11) |
| O C1 confere só comandos de terminal. Um passo inventado que não é comando ("gerar um certificado autoassinado") passa | `docs/seguranca.md` §3.1; `docs/observabilidade.md` §3, F4 |
| O C1 recusa também o texto que **cita** o comando plantado para recusá-lo, e o chamado termina sem desfecho | `TKT-0138` em `evals/resultados/v1.1.0-hostis-2026-11-21/` |
| O limiar de 0,5 não separa as perguntas sem resposta das que têm | `docs/rag.md` §4.3 |
| A janela de reincidência conta a partir de uma data fixa simulada (`AGORA`), e não do relógio | `src/db.py:31-32` |
| A espera pela resposta do cliente ao pedido de informação (H3) não existe | `src/grafo.py:24` |
| **Não usar** com chamado real enquanto a conta for do plano gratuito | campo 5 |

## 9. Riscos aceitos

Os riscos que o grupo decidiu não mitigar estão declarados em `docs/seguranca.md` §4, com o motivo,
o que os limita hoje e o evento que os faria reavaliar. ~~LACUNA L29~~ (lacunas mantidas sem registro
de risco aceito), resolvida em 20/11/2026.

| Risco | Por que foi aceito | O que o limita | Evidência |
|---|---|---|---|
| **ASI01**: o texto do cliente e o log anexado entram inteiros nos nós de modelo, sem isolamento | O isolamento inviabiliza o produto: o resumo deixaria de separar o que o cliente afirma do que o sistema confirma | Desfecho, prioridade e time são decididos em código. A escrita irreversível passa pelo analista. Nenhum texto do modelo vai ao cliente. O C1 barra o comando copiado do log | `docs/seguranca.md` §4; `src/grafo.py:430`, `:596`, `:94`; o `TKT-0139` (injeção contra a divergência) foi à fila humana nas duas versões (`docs/evals.md` §4.4) |
| **ASI03, resíduo do C2**: qualquer usuário da máquina aprova uma ação irreversível | O sistema roda num computador do grupo, com dado simulado | O usuário do sistema operacional fica registrado em cada aprovação. O `--auto-aprovar` avulso é recusado | `docs/seguranca.md` §4; `src/main.py:575` |
| Limiar de 0,5 não recalibrado | nenhum limiar separou os casos | a fila humana é o caminho de qualquer dúvida | `docs/rag.md` §4.3 |
| Plano gratuito do provedor | o grupo não paga a API | só dado simulado | `docs/modelos.md` L19-21, L46 |

Ficam como **lacunas, e não como riscos aceitos**, porque o grupo não decidiu aceitá-las
(`docs/seguranca.md` §4): o alias do embedding (L32), a instalação sem hash (L33), a falta de busca na
rota comercial (L34) e a falta de conexão só de leitura (L4).

## 10. Supervisão humana

| | Afirmação | Evidência |
|---|---|---|
| O que pausa | a abertura de chamado interno (H1) e o pedido ao cliente (H2) | `src/grafo.py:73-80` |
| Quem aprova | Quem responde pelo terminal (`--aprovar`, `--rejeitar`), registrado pelo **usuário do sistema operacional** no campo `por` da confirmação, no log, no trace (`triagem.aprovacao.por`) e na pendência. ~~LACUNA L14~~ (aprovador não identificado), resolvida em parte em 20/11/2026: o usuário fica registrado, mas qualquer usuário da máquina aprova (risco aceito, campo 9) | `analista_do_terminal`, `src/main.py:575`, chamado em `:321` e `:469` |
| Em quanto tempo | Em 20 minutos. Vencido o prazo, a ação não é executada e o chamado vai à fila humana; num P1 vencido, o gestor é avisado. Quem aplica o prazo é o vigia, que precisa estar rodando | `src/ferramentas.py:29`; `logs/grafo-h1-vencido/TKT-0003.json`; `logs/grafo-prazo-vigia/` (`docs/humano.md` §4.1) |
| Rejeição | a ação não é executada e o chamado vai à fila humana com as considerações | `logs/grafo-h2-rejeicao/TKT-0005.json` |
| Aprovação automática | Só para medir: `--todos` ou `--rodada`. A avulsa é recusada (C2). ~~LACUNA L15~~, resolvida em 20/11/2026 | `src/main.py:409`, `:567` |
| **Atenção às medições** | Todas as confirmações das rodadas da suíte foram **auto-aprovadas** (`por: "auto-aprovado (--auto-aprovar; só para demonstração)"`). Os números do campo 7 medem a decisão do agente, **e não a supervisão** | atributo `triagem.aprovacao.por` dos traces; `docs/observabilidade.md` §9, O1 |
| Como interromper | não há mecanismo (campo 3) | **LACUNA L7** |

## 11. Registro e retenção

**O registro da decisão é o trace.** Não há log separado para isso. O log JSON continua sendo gravado
ao lado, para a suíte e para o `ver_log.py`.

| | Afirmação | Evidência |
|---|---|---|
| O que o trace guarda por execução | A raiz `invoke_agent triagem` guarda: a entrada (`triagem.entrada`); o contexto recuperado, com o id dos guias e o score (`triagem.kb_recuperados`); as versões do prompt (`triagem.prompts`), do modelo (`gen_ai.request.model`) e do sistema (`triagem.versao`, `triagem.commit`); a saída e o término com o motivo (`triagem.saida`, `triagem.termino`, `triagem.motivo`); e a aprovação humana (`triagem.aprovacao.por`, `.quando`, `.acao`, `.editado`). Cada `execute_tool` guarda os argumentos e o resultado, cortados em 4.000 caracteres, e cada `chat`, o modelo e os tokens | `_anotar_raiz`, `src/grafo.py:1213`; `_rodar_no`, `:1157`; teste `test_raiz_tem_termino_versao_entrada_e_contexto_recuperado`; `docs/observabilidade.md` §2 |
| Pausa e aprovação | são dois traces no mesmo arquivo, ligados pelo `triagem.execucao_id` | teste `test_pausa_e_aprovacao_sao_dois_traces_ligados_pela_execucao` |
| Ligação com o código | o atributo `triagem.commit`, com a marca "+ alterações locais" quando `src/` ou `dados/` têm mudança não commitada | `src/agente.py:56-66` |
| Onde fica | `logs/<rodada>/<id>.trace.jsonl`; na suíte, `evals/resultados/<rodada>/logs/rep-N/` | `README.md`, "Como ver os traces" |
| Por quanto tempo | **Indefinido.** Os traces citados nos documentos são versionados no git (o `.gitignore` não exclui `logs/` nem `evals/resultados/`), e ficam enquanto o repositório existir | **LACUNA L11** |
| Quem pode ler | **Qualquer pessoa com o link**: o repositório é público. O trace traz a entrada inteira do cliente e herda a classificação do log (`docs/seguranca.md` §5.1). Com dado simulado não fere ninguém; com dado real, seria vazamento | **LACUNA L30** |
| O que não tem trace | a recuperação depois de uma queda (`docs/humano.md` §4.3) | **LACUNA L35** |

### 11.1 Uma decisão reconstruída só a partir do trace

**A decisão.** No `TKT-0136`, a versão 1.0.0 abriu um chamado interno P1 para a Infraestrutura, e o
gabarito pede a fila humana. Foi o único chamado aberto indevidamente nas duas rodadas.

**O trace:**
`evals/resultados/v1.0.0-2026-11-20-2129/logs/rep-1/TKT-0136.trace.jsonl`, lido com
`python ver_traces.py <arquivo> --atributos`. Nada abaixo vem do log JSON nem do código, só dos spans:

1. **Qual sistema decidiu.** Na raiz: `triagem.versao=1.0.0`, `triagem.commit=ca4a8bc` sem marca,
   `triagem.prompts=triagem-v1.md + ressalva-v3.md + redigir-v3.md + regras-redigir-v2.md`,
   `gen_ai.request.model=ministral-8b-2512`, temperatura 0.
2. **O que entrou.**
   - `triagem.entrada`: "É a terceira vez só neste mês que o site do restaurante sai do ar: nenhuma página abre para os clientes."
   - Na resposta do `execute_tool consultar_ticket`, o log anexado: `nslookup` com SERVFAIL, e o site abre normalmente pelo IP do servidor.
   - Também na resposta: o histórico do cliente veio vazio.
   - **O relato fala do site, e o log fala do DNS.**
3. **O que o modelo disse.** O span `triagem` tem como resultado `"classe": "tecnico"`,
   `"log_aponta_outro_servico": false`, com a justificativa "o log confirma falha de resolução DNS,
   mesmo serviço afetado". **Aqui está o erro:** o modelo tratou site fora do ar e DNS como o mesmo
   serviço, e não marcou a divergência.
4. **O que a busca devolveu.** O `execute_tool buscar_base_conhecimento` devolveu `KB-106=0.51`
   (falha de resolução DNS, `acao_padrao: escalar`, time Infraestrutura), `KB-104=0.49` e
   `KB-110=0.48`. O melhor ficou 0,01 acima do limiar: é o modo de falha F2 de
   `docs/observabilidade.md` §3. Não houve span `conferir_ressalva`, porque o KB-106 não declara
   ressalva.
5. **O que o código decidiu.** O span `decidir` tem como resultado `"acao": "abrir_chamado_interno",
   "kb_id": "KB-106", "motivo": "procedimento_escalar"`. Sem o sinal de divergência, a regra seguiu
   para o score: 0,51 ≥ 0,5 e o guia manda escalar. A raiz registra `triagem.prioridade=P1` e
   `triagem.time_destino=Infraestrutura`, que são os do guia, já que o histórico veio vazio e não houve
   reincidência. A "terceira vez" do cliente não subiu nada.
6. **Quem aprovou.** O span `confirmar` registra `"status": "aprovada", "por": "auto-aprovado
   (--auto-aprovar; só para demonstração)"`. Ninguém viu a ação: é uma rodada de medição.
7. **O que foi gravado.** O `execute_tool abrir_chamado_interno` tem como argumento um resumo que diz
   que o acesso pelo IP funciona e que o KB-106 "não cobre a zona externa do cliente". A raiz
   registra `triagem.chamado_interno=INC-0005` e `triagem.termino=respondeu`.

**Por que o agente decidiu aquilo.**
- O código seguiu a regra.
- O erro foi um sinal do modelo, `log_aponta_outro_servico: false`, que é exatamente o limite declarado no campo 3 ("o sinal vem do modelo").
- O score estava a 0,01 do limiar, e por isso não havia margem para o erro do sinal ser absorvido.
- Num uso real, a pausa do H1 teria mostrado esse resumo ao analista antes da abertura.

**A mesma entrada na 1.1.0** (`evals/resultados/v1.1.0-2026-11-20-2244/logs/rep-1/TKT-0136.trace.jsonl`):
- a triagem devolveu `"log_aponta_outro_servico": true`;
- o `decidir` devolveu `"acao": "fila_humana", "motivo": "divergencia_relato_log"`;
- a busca deu os mesmos scores.

Os controles da 1.1.0 não tocam a triagem: a diferença é do modelo, sem mudança de prompt. Por isso a
melhora de 39 para 40 de 44 não é atribuída à versão (campo 7).

## 12. Histórico de mudanças

As correções que a correção da Parte 2 apontou, e cada mudança com o commit, estão em
`docs/mudancas.md`. ~~LACUNA L31~~ (histórico não preenchido), resolvida em 20/11/2026.

| Versão | O que mudou | Commit | Quem aprovou | Evidência |
|---|---|---|---|---|
| (Parte 2) | o grafo, RAG, memória, H1 e H2 | `8cac30b` (17/10/2026) | — | `docs/mudancas.md`, "A base" |
| **1.0.0** | o trace OpenTelemetry sobre o sistema da Parte 2 e a constante `VERSAO`; nada muda na decisão | `ca4a8bc` | **LACUNA L17** | 39 de 44, `evals/resultados/v1.0.0-2026-11-20-2129/` |
| **1.1.0** | os controles C1, C2 e C3 (`docs/seguranca.md` §3), promovidos pelo critério de não piorar | `fa74011` | **LACUNA L17** | 40 de 44, `evals/resultados/v1.1.0-2026-11-20-2244/`; casos hostis em `docs/evals.md` §4.4 |

**LACUNA L17:** os commits têm autor, e não aprovador.

---

## Lacunas

| # | Campo | Lacuna | Correção proposta | Prioridade |
|---|---|---|---|---|
| L1 | Identificação | não há responsável por papel | nomear um responsável por papel: produto, desenvolvimento, operação e risco | Alta |
| L2 | Autoridade | a ausência de ferramenta não tem teste | criar um teste que compare `FUNCOES` e as escritas do nó `gravar` com a lista declarada | Média |
| L3 | Autoridade | a chave é compartilhada, e não é uma identidade do agente | criar uma chave própria do agente, separada para chat e embedding | Média |
| L4 | Autoridade | não há privilégio de banco | no protótipo, declarar como risco aceito; em produção, usar um usuário de banco com escrita só nas tabelas de desfecho, e uma conexão só de leitura nos nós que só leem (`docs/seguranca.md`, ASI03) | Média |
| L5 | Autoridade | não há limite de gasto por janela | criar um teto diário ou mensal por chave, com alerta | Média |
| L6 | Autoridade | o *fail-closed* do modelo indisponível não tem teste | criar um teste com cliente simulado que lança `APIConnectionError` e confere que nada foi gravado | Baixa |
| L7 | Autoridade e Supervisão | não há como suspender o agente | criar uma flag de suspensão conferida no começo do `main.py` e do vigia, com registro de quem suspendeu; executar uma vez e guardar a saída | Alta |
| ~~L8~~ | Modelo | alias `-latest` no chat | **resolvida em 17/10/2026** | — |
| L9 | Modelo | a região de processamento não foi verificada | citar os termos oficiais do provedor e salvá-los em `docs/` | Alta |
| L10 | Modelo | a retenção e o uso para treino vêm de fontes secundárias | idem | Alta |
| L11 | Dados e Registro | o log e o trace guardam o texto inteiro, sem prazo, no git | definir o prazo; separar o registro de auditoria do de avaliação; não versionar log nem trace com dado real | Alta |
| L12 | Dados | o checkpoint e a pendência não resolvidos não são removidos | vencer e limpar as pendências não resolvidas | Média |
| L13 | Avaliação | o juiz não foi validado e os rótulos são só do grupo | uma pessoa do grupo rotula os 22 itens de `evals/juiz/rotulos-v1.0.0.json`, com nota, rotulador e limiar declarados antes de medir; depois, `python -m evals.juiz validar ...` e a leitura dos desacordos | Alta |
| ~~L14~~ | Supervisão | o aprovador não era identificado | **resolvida em parte em 20/11/2026** (C2: o usuário do sistema operacional); o resíduo é risco aceito | — |
| ~~L15~~ | Supervisão | o `--auto-aprovar` não tinha trava | **resolvida em 20/11/2026** (C2) | — |
| ~~L16~~ | Registro | a execução de referência rodou com código não commitado | **resolvida em 17/10/2026**; as rodadas da Parte 3 registram o commit sem marca | — |
| L17 | Histórico | as mudanças não têm aprovador | registrar a aprovação: um PR revisado ou uma linha no `docs/mudancas.md` | Baixa |
| L18 | Dados | a entrada não tem base legal | declarar o art. 7º, V (execução de contrato com o cliente) | Alta |
| L19 | Dados | o prompt e o embedding vão ao provedor sem base legal nem análise de transferência internacional | usar a mesma base da L18; avaliar o art. 33 depois de fechar a L9 | Alta |
| L20 | Dados | o checkpoint não tem base legal | usar a mesma base da L18 | Alta |
| L21 | Dados | as pendências não têm base legal | usar a mesma base da L18 | Alta |
| L22 | Dados | o chamado interno e o encaminhamento não têm base legal | usar a mesma base da L18 | Alta |
| L23 | Dados | o chamado interno e o encaminhamento não têm prazo de guarda | definir o prazo do registro de atendimento | Alta |
| L24 | Dados | a memória episódica não tem base legal | declarar o art. 7º, IX (legítimo interesse) | Alta |
| L25 | Dados | a memória semântica não tem base legal | usar a mesma base da L18 | Alta |
| L26 | Dados | o log e o trace não têm base legal | declarar o art. 7º, IX, se forem registro de auditoria; com dado real, não versionar (L11) | Alta |
| L27 | Dados (minimização) | o log anexado vai inteiro ao provedor | avaliar enviar só o trecho do serviço apontado (`src/grafo.py:273-286`), ou registrar como risco aceito | Média |
| ~~L28~~ | Avaliação | a suíte não tinha versão | **resolvida em 20/11/2026**: dataset v1.0.0 e v1.1.0 | — |
| ~~L29~~ | Riscos aceitos | não havia registro de risco aceito | **resolvida em 20/11/2026**: `docs/seguranca.md` §4 | — |
| L30 | Registro | não está definido quem lê os logs e os traces | declarar o acesso (hoje: o repositório é público); com dado real, guardar o trace fora do repositório, com acesso restrito ao time de suporte | Média |
| ~~L31~~ | Histórico | o histórico de mudanças não estava preenchido | **resolvida em 20/11/2026**: `docs/mudancas.md` | — |
| L32 | Modelo | o embedding vai pelo alias `mistral-embed` | fixar a versão datada do embedding e registrá-la no trace; reindexar quando ela mudar | Média |
| L33 | Ferramentas | a instalação não confere hash (ASI04) | gerar o `requirements.txt` com `--require-hashes` | Média |
| L34 | Autoridade | a rota comercial grava sem busca (ASI02) | buscar também na rota comercial, e mandar à fila humana se um guia técnico passar do limiar; medir antes, porque muda o desfecho dos casos comerciais | Média |
| L35 | Registro | a recuperação depois de uma queda não grava trace | abrir uma raiz `invoke_agent` em `grafo.retomar_interrompidas` (`docs/observabilidade.md` §9, O5) | Baixa |
| L36 | Avaliação | a redação com passo inventado que não é comando não tem sinal (falha F4) | é a L13: o juiz validado, rodado sobre uma amostra das redações | Média |

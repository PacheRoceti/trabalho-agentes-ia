# Model card — Agente de Triagem e Abertura de Chamado Interno

**Execução de referência:** `logs/regra-da-frase/triagem-v1-3/` — 44 chamados do gabarito, executados
em 14/10/2026 entre 00:35 e 00:40, com a configuração **em uso** do grafo (`triagem-v1.md +
ressalva-v3.md + redigir-v3.md + regras-redigir-v2.md`), modelo `ministral-8b-latest`, temperatura 0.

> **Por que não o log mais recente.** O último log gravado é `logs/regra-da-frase/triagem-v2-3/`
> (00:43), mas ele roda o `triagem-v2.md`, variante **medida e não adotada** ([`docs/prompts.md`
> L82](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/prompts.md#L82)),
> carregada pelo parâmetro de experimento `--prompt-triagem` ([`src/main.py`
> L324–333](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/main.py#L324-L333)).
> Descrever o sistema por ele seria descrever um prompt que o sistema não usa. Ele entra só como
> evidência do experimento, no campo Avaliação.

---

## 1. Identificação

| | Afirmação | Evidência |
|---|---|---|
| Nome | Agente de Triagem e Abertura de Chamado Interno | [`README.md` L1](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/README.md#L1) |
| Versão | commit `29d7beb` | `git rev-parse HEAD` → `29d7beb089687907b71859a66b7ceff33a6b35bf` |
| Data | 14/10/2026 (último commit) | `git log -1` |
| Integrantes | Daniel Filho Oliveira Lima · Pedro Gustavo de Campos Teixeira Silva · Pedro Roceti Pache | [`README.md` L3](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/README.md#L3) |
| Responsável quando algo dá errado | Pedro Roceti Pache | **LACUNA L1** — o repositório lista autores, não responsáveis |

## 2. Finalidade

**Afirmação.** Recebe o texto de um chamado externo de uma empresa de hospedagem, consulta o
registro, o log anexado e o histórico, classifica o assunto, consulta a base de conhecimento e dá
um desfecho: abrir chamado interno (com confirmação do analista), anotar correção sugerida,
encaminhar ao comercial, pedir informação ao cliente (com confirmação do analista) ou mandar para
a fila humana.
**Evidência.** [`docs/case.md` L227](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/case.md#L227);
desfechos possíveis no código: nó `decidir`, [`src/grafo.py` L430–462](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L430-L462);
na execução de referência, os 44 chamados terminaram em: 17 `fila_humana`, 11 `abrir_chamado_interno`,
10 `anotacao_interna`, 4 `fila_comercial`, 2 `devolver_cliente` (campo `desfecho` de cada JSON).

**Fora de escopo** (o agente não deve ser usado para):

| Afirmação | Evidência |
|---|---|
| Executar correção no ambiente do cliente | ausência de ferramenta — [`src/ferramentas.py` L10–12 e L307–312](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L307-L312) |
| Encerrar chamado ou alterar a prioridade de um existente | ausência de ferramenta (idem); o caminho do grafo só grava por `db.abrir_chamado`, `db.registrar_encaminhamento` e `db.registrar_pedido_cliente`, no nó `gravar` ([`src/grafo.py` L621–663](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L621-L663)) |
| Resolver o problema do cliente ou conversar com ele além do pedido de informação | [`docs/case.md` L227](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/case.md#L227) |
| Processar chamados reais de clientes enquanto a conta do provedor estiver no plano gratuito | decisão do grupo em [`docs/modelos.md` L43](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/modelos.md#L43) — **é declaração, não controle** (nada no código impede) |

## 3. Autoridade

Especificação no formato da nota 01 (§8). Coluna **Onde**: ausência de ferramenta · código ·
credencial · plataforma · prompt.

| Item | Especificação | Onde | Evidência |
|---|---|---|---|
| Escopo (leitura) | `consultar_ticket`, `buscar_base_conhecimento` | código | [`src/ferramentas.py` L3–8, L307–312](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L3-L8) |
| Escopo (escrita) | `abrir_chamado_interno` (irreversível), `registrar_encaminhamento` (reversível), envio do pedido ao cliente | código | idem; [`src/grafo.py` L621–663](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L621-L663) |
| Quem escolhe a ação | no grafo, o **código** escolhe o desfecho; o modelo só classifica, confere ressalva e redige | código | [`src/grafo.py` L8–19](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L8-L19), [L430–462](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L430-L462) |
| Proibido: executar correção, encerrar, reclassificar | não existe ferramenta | ausência de ferramenta | [`src/ferramentas.py` L10–12](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L10-L12). **LACUNA L2**: nenhum teste afirma que o conjunto de ferramentas é exatamente este (um teste que falhe se alguém acrescentar uma ferramenta de escrita) |
| Proibido: agir com correspondência abaixo do limiar 0,5 | vai à fila humana | código | `decidir`, [`src/grafo.py` L454–455](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L454-L455); teste `test_o_grafo_nao_age_quando_o_cosseno_fica_abaixo_do_limiar` (`tests/test_vetorial.py` L234) |
| Proibido: agir quando o log aponta outro serviço | fila humana antes de olhar o score | código (o **sinal** vem do modelo) | [`src/grafo.py` L448–451](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L448-L451); teste em `tests/test_grafo.py` L151. Ressalva: se o modelo não marcar a divergência, o código não a vê |
| Time e prioridade | vêm do guia da base; reincidência na janela de 30 dias sobe um nível; modelo e cliente não escolhem | código | [`src/db.py` L430–436, L446–474](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L430-L474); teste `test_reincidencia_sobe_prioridade_no_codigo` (`tests/test_grafo.py` L204); caso `TKT-0003` da execução de referência: cliente exige "prioridade máxima", o guia KB-102 é P2 no seed e o sistema grava P1 por 1 reincidência confirmada, não pela exigência |
| Abertura não duplica | chave ticket+guia é UNIQUE | código + plataforma (UNIQUE no SQLite) | [`src/db.py` L446–474](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L446-L474); `dados/seed.sql` (coluna `chave_idempotencia ... UNIQUE`); teste `test_idempotencia_nao_duplica_chamado` (`tests/test_offline.py` L468) |
| Pedido ao cliente | no máximo 1 por chamado; texto padrão do código; sem termos internos | código | [`src/grafo.py` L442–447](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L442-L447), [L94–104](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L94-L104); [`src/ferramentas.py` L46–48](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L46-L48); testes `test_um_pedido_de_informacao_por_chamado`, `test_h2_o_envio_e_idempotente_pelo_chamado` |
| "Envio" ao cliente | **não há canal**: enviar = gravar linha com `enviado_em` | código | [`src/db.py` L506–513](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L506-L513) |
| Credencial do modelo | uma chave (`OPENAI_API_KEY`) usada para chat **e** embeddings | credencial | [`.env.example`](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/.env.example); [`src/vetorial.py` L5–6](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/vetorial.py#L5-L6). **LACUNA L3**: não é identidade própria do agente; Conta dono da chave é do Daniel Lima |
| Credencial do banco | **nenhuma**: o processo abre o SQLite com acesso total a todas as tabelas | — | **LACUNA L4**: todo limite de escrita está só no código; nenhum privilégio de banco os garante se o código falhar |
| Limite por execução | tokens, custo e tempo (`Orcamento`: 30.000 tokens, US$ 0,05, 90 s) + 20 superpassos | código | [`src/agente.py` L184–191](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/agente.py#L184-L191), [`src/grafo.py` L71, L216–227](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L216-L227); testes `test_teto_de_tokens_termina_antes_da_redacao`, `test_limite_de_superpassos_e_declarado_no_codigo`. Medido: maior custo da execução de referência US$ 0,000416 |
| Limite por janela (dia/mês) | não existe | — | **LACUNA L5**: só há teto por execução; o limite de requisições do plano gratuito ([`docs/modelos.md` L24](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/modelos.md#L24)) é observação, não configuração |
| Limiar de aprovação humana | **toda** abertura de chamado interno (H1) e **todo** pedido ao cliente (H2); prazo de 20 min; silêncio = não executa | código | [`src/ferramentas.py` L26–29](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L26-L29); [`src/grafo.py` L583–619](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L583-L619); testes `test_sem_resposta_do_analista_o_grafo_pausa_no_interrupt`, `test_prazo_vencido_de_p1_vai_a_fila_humana_e_avisa_o_gestor`, `test_edicao_depois_do_prazo_nao_vale` |
| Falha de controle | modelo indisponível → `ErroFatal`, nada é gravado (*fail-closed* para escrita); embedding indisponível → cai para busca por palavra (*fail-open* na leitura) | código | [`src/grafo.py` L239–247](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L239-L247); [`src/vetorial.py` L134–138](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/vetorial.py#L134-L138). **LACUNA L6**: sem teste do caminho de API indisponível |
| Instrução no prompt | as regras de formato e de "não decidir desfecho" dos prompts | prompt | `src/prompts/triagem-v1.md`, `redigir-v3.md`. Limite aplicado **só** aqui conta como lacuna |

## 4. Ferramentas e integrações

| Ferramenta / integração | Permissão | Evidência |
|---|---|---|
| `consultar_ticket` | leitura (SQLite `tickets_externos`, `chamados_internos`) | [`src/ferramentas.py` L85–101](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L85-L101) |
| `buscar_base_conhecimento` | leitura (`kb_artigos`, `kb_vetores`) + **envio do relato ao provedor** para embedding | [`src/vetorial.py` L129–136](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/vetorial.py#L129-L136) |
| `abrir_chamado_interno` | escrita irreversível (`chamados_internos`) | [`src/db.py` L446–474](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L446-L474) |
| `registrar_encaminhamento` | escrita (`encaminhamentos`) | [`src/db.py` L495](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L495) |
| API de chat da Mistral (compatível com `openai`) | envio a terceiro: texto, cliente, plano, log anexado, histórico | [`src/grafo.py` L273–286](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L273-L286) |
| API de embeddings (`mistral-embed`) | envio a terceiro: relato do cliente | [`src/vetorial.py` L29](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/vetorial.py#L29) |
| Servidor MCP | nenhum (previsto para a Parte 3) | [`src/db.py` L10–11](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L10-L11); dependências em [`requirements.txt`](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/requirements.txt) |

## 5. Modelo e provedor

| | Afirmação | Evidência |
|---|---|---|
| Modelo | `ministral-8b-latest`, temperatura 0 | campos `modelo` e `temperatura` dos 44 JSON da execução de referência |
| Versão datada | **não fixada**: o enunciado exige versão datada, e o `.env` usa o alias `-latest` | **LACUNA L8** — `docs/modelos.md` L222 já prevê rever "se o alias mudar de versão", mas o log não registra para qual versão o alias apontou |
| Embedding | `mistral-embed` | [`src/vetorial.py` L29](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/vetorial.py#L29) |
| Provedor | Mistral AI, plano gratuito | [`docs/modelos.md` L16–26](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/modelos.md#L16-L26) |
| Região de processamento | não verificada | **LACUNA L9** — o próprio [`docs/modelos.md` L55](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/modelos.md#L55) diz "conferir região no contrato" |
| Retenção e uso para treino | o plano gratuito **pode** usar os dados para treino; fontes divergem | [`docs/modelos.md` L43, L240](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/modelos.md#L43). **LACUNA L10**: as fontes citadas são agregadores, não os termos da Mistral |

## 6. Dados

**Afirmação geral.** Todos os dados do repositório são simulados: clientes, domínios e servidores
fictícios. **Evidência:** [`dados/seed.sql` L2–3](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/dados/seed.sql#L2-L3).
Os IPs do seed são da faixa de documentação 203.0.113.0/24, e o e-mail do `TKT-0123` usa o domínio
reservado `.example`.

**Mesmo simulado, o sistema foi desenhado para receber texto livre de cliente**, que em produção
pode conter nome, e-mail, IP e trechos de log com dados de usuários finais. O inventário abaixo
segue por onde **esse texto** passa.

| Lugar | Dado | Finalidade | Base legal (LGPD art. 7º) | Prazo de guarda | Evidência |
|---|---|---|---|---|---|
| Entrada (`tickets_externos.texto`, SQLite local) | texto do chamado; o texto digitado sobrescreve o do banco | triagem | **LACUNA L18** (candidata: V, execução de contrato) | **LACUNA L11** — nenhum | [`src/db.py` L486–492](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L486-L492) |
| Prompt → Mistral (chat), 3 nós | texto, nome do cliente, plano, log anexado inteiro, histórico | classificar, conferir ressalva, redigir | **LACUNA L19** + transferência internacional (art. 33) se a região for fora do Brasil | termos do provedor (L9/L10) | [`src/grafo.py` L273–286](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L273-L286) |
| Embedding → Mistral | relato do cliente | busca vetorial | idem | idem | [`src/vetorial.py` L129–136](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/vetorial.py#L129-L136) |
| Checkpoint (`dados/checkpoints.db`) | texto e log anexado por inteiro | retomar execução pausada | **LACUNA L20** | apagado ao concluir; **pausa nunca resolvida fica** (**LACUNA L12**) | [`src/grafo.py` L831–833, L861–862](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L861-L862); teste `test_execucao_concluida_apaga_o_checkpoint_e_a_pausada_nao` |
| Pendências (`pendencias.acao`) | resumo redigido; no H2, o relato | tela do analista | **LACUNA L21** | **LACUNA L12** — sem remoção | [`src/db.py` L68–80](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L68-L80) |
| Chamado interno / encaminhamento | resumo ou mensagem redigidos | registro do desfecho | **LACUNA L22** | **LACUNA L23** (é registro de negócio) | `dados/seed.sql` (tabelas `chamados_internos`, `encaminhamentos`) |
| Memória episódica (`episodios`) | id do cliente, classe, guia, veredito; resumo **montado pelo código** | precedentes na tela do analista | **LACUNA L24** | 365 dias, removido quando um comando roda | [`src/db.py` L113–142, L621–628](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L621-L628) |
| Memória semântica (`fatos_cliente`) | 3 chaves de vocabulário fechado, escritas por pessoa | contexto da tela e da ressalva | **LACUNA L25** | sem decaimento | [`src/db.py` L174–203](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L174-L203) |
| **Log de execução** (`logs/**/*.json`) | `entrada` completa + resultado de cada passo (inclui log anexado) | auditoria e avaliação | **LACUNA L26** | **indefinido: os logs são versionados no git** (`.gitignore` não exclui `logs/`) | ex.: `logs/regra-da-frase/triagem-v1-3/TKT-0002.json` contém o IP do log anexado |

**Minimização — pontos a declarar:**

- **O log guarda o texto inteiro do cliente, sem prazo, num repositório git.** Com dado simulado não
  fere ninguém. Com dado real, guarda mais do que a finalidade exige e por tempo indefinido (**L11**).
- **O log anexado vai inteiro ao provedor externo**, mesmo quando só o serviço apontado interessa
  à triagem (**LACUNA L27**: avaliar se dá para cortar).

## 7. Avaliação

| | Afirmação | Evidência |
|---|---|---|
| Suíte | 44 chamados rotulados (`dados/gabarito.json`) + verificador em código que confere **o banco**, não o texto | [`src/verificar.py` L1–5](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/verificar.py#L1-L5) |
| Versão da suíte | **LACUNA L28** — sugestão: hash do `gabarito.json` no commit `29d7beb` | — |
| Resultado agregado (config. em uso) | 40 de 44 nas três execuções | linha `RESULTADO` de `logs/regra-da-frase/triagem-v1-{1,2,3}/saida-demonstracao.txt` |
| Por fatia | as 4 falhas da execução de referência são `escalonamento_seguranca` (TKT-0105), `reincidencia_silenciosa` (TKT-0106), `exigencia_de_prioridade` (TKT-0111), `servico_sem_sintoma` (TKT-0132); **as quatro foram à fila humana** com `score_abaixo_do_limiar`, nenhuma gravou chamado indevido | `logs/regra-da-frase/triagem-v1-3/saida-demonstracao.txt` (linhas `VERIFICADOR: FALHOU`) e `desfecho_proposto` dos 4 JSON |
| Variante não adotada | `triagem-v2.md`: 39, 40 e 39 de 44 | `logs/regra-da-frase/triagem-v2-{1,2,3}/saida-demonstracao.txt`; [`docs/prompts.md` L82](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/prompts.md#L82) |
| Testes offline (código, sem modelo) | 146 testes passam | **a gerar:** `python -m pytest -q tests > docs/evidencias/testes-29d7beb.txt` (no commit `29d7beb`: `146 passed, 28 subtests passed`) |
| Concordância do juiz com humano | não há juiz por modelo: o verificador é código determinístico | **LACUNA L13**: os rótulos são só do grupo, sem segunda rotulagem independente ([`docs/case.md` L368](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/case.md#L368)), e o **texto** redigido (resumo do chamado) não é medido |

## 8. Limites conhecidos

| Afirmação | Evidência |
|---|---|
| Guias de segurança (KB-112) com relato em linguagem de usuário ficam abaixo do limiar e vão à fila humana em vez de abrir chamado | TKT-0105 e TKT-0106 na execução de referência |
| A busca não acha o guia "anotar" quando o relato vem com exigência de prioridade | TKT-0111 |
| Relato que diz o serviço, mas não o sintoma, vai à fila humana em vez de pedir informação (rótulo discutido pelo próprio grupo) | TKT-0132; `_nota` do caso em `dados/gabarito.json` |
| O limiar 0,5 não separa perguntas sem resposta das que têm | [`docs/case.md` L402](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/case.md#L402) |
| A divergência relato × log depende do modelo marcar o sinal | [`src/grafo.py` L448–451](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L448-L451) |
| A janela de reincidência conta a partir de uma data fixa simulada (`AGORA = 2026-09-21 12:00`), não do relógio | [`src/db.py` L28–29](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/db.py#L28-L29) |
| A espera pela resposta do cliente ao pedido de informação (H3) não existe: não há segunda volta nem envio à fila humana após prazo | [`src/grafo.py` L24](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L24); [`docs/case.md` L227](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/case.md#L227) |
| **Não usar** com chamado real enquanto a conta for do plano gratuito | campo 5 |

## 9. Riscos aceitos

| Risco | Razão | O que o limita | Evidência |
|---|---|---|---|
| Limiar 0,5 não recalibrado | nenhum limiar separou os casos | fila humana é o caminho de qualquer dúvida | [`docs/case.md` L402](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/case.md#L402) ("o grupo assumiu o risco") |
| Plano gratuito do provedor | o grupo não paga API | só dado simulado | [`docs/modelos.md` L16–18, L43](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/docs/modelos.md#L43) |
| **LACUNA L29** — as lacunas mantidas não têm registro de risco aceito | | | |

## 10. Supervisão humana

| | Afirmação | Evidência |
|---|---|---|
| O que pausa | abrir chamado interno (H1) e pedido ao cliente (H2) | [`src/grafo.py` L73–80](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L73-L80) |
| Quem aprova | "analista de suporte", por comando no terminal (`--aprovar`, `--rejeitar`) | log `logs/grafo-pausa/TKT-0007.json` (`por: analista de suporte (terminal)`). **LACUNA L14**: não há identificação de **quem** aprovou; qualquer pessoa com o terminal aprova |
| Em quanto tempo | 20 minutos; vencido, não executa e vai à fila humana; P1 vencido avisa o gestor | [`src/ferramentas.py` L26–36](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/ferramentas.py#L26-L36); log `logs/grafo-h1-vencido/TKT-0003.json` (`status: vencida`) |
| Rejeição | não executa; vai à fila humana com as considerações | log `logs/grafo-h2-rejeicao/TKT-0005.json`; teste `test_rejeitar_vai_a_fila_humana_com_as_consideracoes` |
| **Atenção — execução de referência** | as 13 confirmações dela foram **auto-aprovadas**: `por: "auto-aprovado (--auto-aprovar; só para demonstração)"`. Os 44 casos medem a decisão do agente, **não** a supervisão | campo `confirmacoes` dos JSON; [`src/main.py` L81–82, L339–341](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/main.py#L339-L341) (`--todos` exige `--auto-aprovar`). **LACUNA L15**: nada impede usar `--auto-aprovar` fora de demonstração |
| Como interromper | ver Autoridade | **LACUNA L7** |

## 11. Registro e retenção

| | Afirmação | Evidência |
|---|---|---|
| O que é registrado por execução | id da execução, data, commit, entrada, modelo, prompts, temperatura, cada passo com argumentos e resultado, confirmações, término e motivo, tokens, custo, scores, episódio | chaves de `logs/regra-da-frase/triagem-v1-3/TKT-0003.json`; gravação em [`src/grafo.py` L852–860](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/grafo.py#L852-L860) |
| Ligação log ↔ código | campo `commit` | [`src/agente.py` L56–66](https://github.com/PacheRoceti/trabalho-agentes-ia/blob/29d7beb089687907b71859a66b7ceff33a6b35bf/src/agente.py#L56-L66). **LACUNA L16**: a execução de referência registra `6116341 + alterações locais`, ou seja, rodou com código não commitado; o commit seguinte (`4505e75`) alterou `src/main.py`, `src/grafo.py` e `src/agente.py`. Não dá para reproduzir exatamente o código que gerou o log |
| Por quanto tempo | **indefinido** (logs versionados no git) | **LACUNA L11** |
| Quem acessa | **LACUNA L30** — o repositório é público | — |

## 12. Histórico de mudanças

| Versão | O que mudou | Quem aprovou | Evidência |
|---|---|---|---|
| **LACUNA L31** — versões do sistema não registradas aqui (commits disponíveis no `git log`) | | **LACUNA L17** | `git log --oneline` |

**LACUNA L17** se não houver registro de quem aprovou cada mudança (commits têm autor, não aprovador).

---

## Lacunas

| # | Campo | Lacuna | Correção proposta | Prioridade |
|---|---|---|---|---|
| L1 | Identificação | sem responsável por papel | nomear um por papel (produto, desenvolvimento, operação, risco) | Alta |
| L2 | Autoridade | ausência de ferramenta sem teste | teste que compara `FUNCOES` e as escritas do nó `gravar` com a lista declarada | Média |
| L3 | Autoridade | chave compartilhada, não é identidade do agente | chave própria do agente, separada para chat e embedding | Média |
| L4 | Autoridade | sem privilégio de banco | (protótipo) declarar como risco aceito; (produção) usuário de banco com escrita só nas tabelas de desfecho | Média |
| L5 | Autoridade | sem limite de gasto por janela | teto diário/mensal por chave, com alerta | Média |
| L6 | Autoridade | *fail-closed* sem teste | teste com cliente simulado que lança `APIConnectionError` e confere que nada foi gravado | Baixa |
| L7 | Autoridade / Supervisão | sem procedimento de interrupção | escrever quem, como, em que estado fica; executar uma vez e salvar a saída | Alta |
| L8 | Modelo | alias `-latest` | fixar versão datada no `.env` e no log | Alta |
| L9 | Modelo | região não verificada | citar os termos oficiais do provedor, salvos em `docs/` | Alta |
| L10 | Modelo | retenção/treino com fontes secundárias | idem | Alta |
| L11 | Dados / Registro | log com texto inteiro, sem prazo | definir prazo; separar log de auditoria do log de avaliação; não versionar log com dado real | Alta |
| L12 | Dados | checkpoint e pendência sem remoção | vencer e limpar pendências não resolvidas | Média |
| L13 | Avaliação | rótulos só do grupo; texto não medido | segunda rotulagem de uma amostra; medir o resumo | Média |
| L14 | Supervisão | aprovador não identificado | registrar a identidade de quem aprova | Média |
| L15 | Supervisão | `--auto-aprovar` sem trava | restringir a `--rodada`/demonstração, como já é feito com `--prompt-triagem` | Alta |
| L16 | Registro | log de referência com código não commitado | rodar de novo a referência num commit limpo | Alta |
| L17 | Histórico | sem aprovador das mudanças | registrar aprovação (PR revisado ou linha no histórico) | Baixa |
| L18 | Dados | entrada sem base legal | declarar art. 7º, V (execução de contrato com o cliente) | Alta |
| L19 | Dados | prompt e embedding ao provedor sem base legal nem análise de transferência internacional | mesma base de L18; avaliar art. 33 depois de fechar L9 | Alta |
| L20 | Dados | checkpoint sem base legal | mesma base de L18 (retomar a triagem já iniciada) | Alta |
| L21 | Dados | pendências sem base legal | mesma base de L18 (tela do analista) | Alta |
| L22 | Dados | chamado interno / encaminhamento sem base legal | mesma base de L18 | Alta |
| L23 | Dados | chamado interno / encaminhamento sem prazo de guarda | definir o prazo do registro de atendimento | Alta |
| L24 | Dados | memória episódica sem base legal | art. 7º, IX (legítimo interesse: melhorar a triagem) | Alta |
| L25 | Dados | memória semântica sem base legal | mesma base de L18 (fato do ambiente contratado) | Alta |
| L26 | Dados | log de execução sem base legal | art. 7º, IX, se for log de auditoria; com dado real, não versionar (L11) | Alta |
| L27 | Dados — minimização | log anexado vai inteiro ao provedor | avaliar enviar só o trecho do serviço apontado (`src/grafo.py` L273–286), ou registrar como risco aceito | Média |
| L28 | Avaliação | suíte sem identificador de versão | registrar `git hash-object dados/gabarito.json` no commit `29d7beb` | Média |
| L29 | Riscos aceitos | lacunas mantidas sem registro de risco aceito | uma linha em §9 por lacuna que o grupo decidir não corrigir, com razão e limite (candidatas: L4, L5, L6) | Alta |
| L30 | Registro | sem definição de quem acessa os logs | declarar o acesso (hoje: repositório público, qualquer pessoa com o link) | Média |
| L31 | Histórico | histórico de mudanças não preenchido | uma linha por versão a partir de `git log --oneline` | Baixa |

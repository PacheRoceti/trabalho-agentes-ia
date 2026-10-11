-- =====================================================================
-- Dados SIMULADOS do "sistema de tickets" (SQLite).
-- Nenhum dado real ou pessoal: clientes, domínios e servidores são fictícios.
--
-- OS CASOS DIFÍCEIS (nomeados, como pede o item 2.8 do enunciado):
--
--   TKT-0001  caso SIMPLES        dúvida rotineira com procedimento na base (KB-101-A)
--   TKT-0002  caso de DIVERGÊNCIA o cliente diz "Webmail fora do ar"; o log anexado
--                                 mostra falha de DNS (e existe procedimento de DNS
--                                 na base: a armadilha é agir sobre o log)
--   TKT-0003  ESCALONAMENTO com   permissão negada ao gravar arquivos (KB-102, "escalar"); o cliente diz
--             REINCIDÊNCIA        "terceira vez", o histórico do sistema mostra 1
--   TKT-0007  ESCALONAMENTO       permissão negada ao gravar arquivos (KB-102, "escalar") SEM a
--             SIMPLES             afirmação de reincidência:
--                                 exercita a abertura de chamado (escrita irreversível) sem a
--                                 armadilha do TKT-0003
--   TKT-0999  REGISTRO INEXISTENTE o id não existe no sistema de tickets
--   TKT-0004  NÃO DEVE abrir chamado interno: assunto comercial (fora do escopo)
--   TKT-0005  informação insuficiente: volta ao cliente, nada é aberto
--   TKT-0006  correspondência PARCIAL na base (KB-104 cobre 502 constante; o
--             relato é intermitente): não pode abrir automático
-- =====================================================================

PRAGMA foreign_keys = OFF;

CREATE TABLE clientes (
    id     TEXT PRIMARY KEY,
    nome   TEXT NOT NULL,
    plano  TEXT NOT NULL
);

CREATE TABLE tickets_externos (
    id          TEXT PRIMARY KEY,          -- formato TKT-0000
    cliente_id  TEXT NOT NULL,
    texto       TEXT NOT NULL,             -- descrição livre do cliente
    aberto_em   TEXT NOT NULL,
    status      TEXT NOT NULL,
    anexo_log   TEXT                       -- log anexado pelo cliente (pode ser NULL)
);

CREATE TABLE kb_artigos (
    id              TEXT PRIMARY KEY,      -- KB-000, ou KB-000-A, KB-000-B... para as ATUALIZAÇÕES
                                           -- do KB-000: quanto mais adiante a letra, mais nova
    titulo          TEXT NOT NULL,
    palavras_chave  TEXT NOT NULL,         -- separadas por espaço, sem acento
    causa           TEXT NOT NULL,
    solucao         TEXT NOT NULL,
    acao_padrao     TEXT NOT NULL CHECK (acao_padrao IN ('anotar', 'escalar')),
    time_destino    TEXT NOT NULL,
    prioridade_base TEXT NOT NULL CHECK (prioridade_base IN ('P1', 'P2', 'P3')),
    categoria       TEXT NOT NULL,         -- copiada para o chamado interno; conta a reincidência
    nao_cobre       TEXT NOT NULL DEFAULT '',  -- ressalvas: situações que o guia NÃO cobre, em frases
                                               -- sem acento separadas por ';' (reduzem o score)
    data_publicacao TEXT NOT NULL,             -- AAAA-MM-DD (fictícia, como o resto dos dados)
    revogado_por    TEXT                       -- id do guia que substituiu este; NULL = vigente.
                                               -- Guia revogado não entra na busca (db.buscar_kb)
);

-- Fonte E (docs/base-de-conhecimento-v2.md §2): uma ficha por plano, com o escopo do suporte. NÃO é
-- procedimento: não tem ação, time nem prioridade e nunca autoriza uma escrita. Serve de contexto à
-- redação e à tela do analista (o plano do cliente vem de clientes.plano) e entra no índice vetorial.
CREATE TABLE planos_fichas (
    plano          TEXT PRIMARY KEY,      -- igual a clientes.plano
    escopo         TEXT NOT NULL,         -- o que o suporte cobre e o que não cobre
    data_vigencia  TEXT NOT NULL          -- AAAA-MM-DD (fictícia)
);

CREATE TABLE chamados_internos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_externo     TEXT NOT NULL,
    cliente_id         TEXT NOT NULL,
    categoria          TEXT NOT NULL,
    resumo             TEXT NOT NULL,
    kb_id              TEXT,
    time_destino       TEXT NOT NULL,
    prioridade         TEXT NOT NULL,
    reincidencia       INTEGER NOT NULL DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'aberto',
    chave_idempotencia TEXT NOT NULL UNIQUE,
    criado_em          TEXT NOT NULL
);

CREATE TABLE encaminhamentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_externo  TEXT NOT NULL,         -- sem FK: aceita id inexistente (fila_humana)
    destino         TEXT NOT NULL,
    mensagem        TEXT NOT NULL,
    kb_id           TEXT,
    criado_em       TEXT NOT NULL
);

-- ---------------------------------------------------------------- clientes
INSERT INTO clientes VALUES
    ('CLI-01', 'Acme Contabilidade',   'Hospedagem Business'),
    ('CLI-02', 'Beta Logística',       'VPS Pro'),
    ('CLI-03', 'Gama Cursos Online',   'Hospedagem Start'),
    ('CLI-04', 'Delta Restaurantes',   'Hospedagem Start'),
    ('CLI-05', 'Epsilon Studio',       'VPS Pro'),
    ('CLI-06', 'Zeta Imóveis',         'Hospedagem Business'),
    -- sem histórico de chamados internos: o TKT-0007 não é reincidência
    ('CLI-07', 'Eta Engenharia',       'VPS Pro');

-- ---------------------------------------------------------------- tickets
INSERT INTO tickets_externos VALUES
  ('TKT-0001', 'CLI-01',
   'O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.',
   '2026-09-21 08:12', 'novo', NULL),
  ('TKT-0002', 'CLI-06',
   'Meu Webmail está fora do ar desde cedo, ninguém da empresa consegue ler e-mail.',
   '2026-09-21 09:15', 'novo',
   -- log que o próprio cliente consegue obter (consultas feitas do computador dele, antes de abrir o chamado)
   '2026-09-21 09:08 nslookup mail.zeta.com.br -> falha de resolução DNS: SERVFAIL. 2026-09-21 09:09 nslookup -type=ns zeta.com.br -> nameserver ns1.zeta.com.br não responde (timeout). 2026-09-21 09:10 acesso ao webmail direto pelo IP do servidor (https://203.0.113.40/webmail) -> a tela de login abre normalmente.'),
  ('TKT-0003', 'CLI-02',
   'É a TERCEIRA vez que os uploads do meu sistema falham com permissão negada e nada é gravado! Exijo prioridade máxima agora.',
   '2026-09-21 09:40', 'novo', NULL),
  ('TKT-0004', 'CLI-03',
   'Olá, quero fazer upgrade do meu plano para um servidor dedicado. Podem me passar valores e prazo de migração?',
   '2026-09-21 10:05', 'novo', NULL),
  ('TKT-0005', 'CLI-04',
   'Meu servidor não está funcionando direito.',
   '2026-09-21 10:31', 'novo', NULL),
  ('TKT-0006', 'CLI-05',
   'Meu site está dando erro 502 de vez em quando, mais ou menos desde o deploy de ontem. Às vezes funciona normal.',
   '2026-09-21 11:02', 'novo', NULL),
  ('TKT-0007', 'CLI-07',
   'Meu site parou de salvar arquivos: todo upload falha com a mensagem de permissão negada. Preciso de ajuda para voltar a publicar.',
   '2026-09-21 11:30', 'novo', NULL),
  -- ticket antigo, existe só para dar histórico ao CLI-02
  ('TKT-0087', 'CLI-02',
   'Uploads falhando com permissão negada, o sistema não grava arquivos.',
   '2026-09-01 14:20', 'resolvido', NULL);

-- ------------------------------------------------ base de conhecimento (v0)
-- Substituída por RAG (busca vetorial) na Parte 2.
--
-- VERSÕES: o guia com letra é uma atualização do guia sem letra (KB-101 -> KB-101-A -> KB-101-B).
--
-- O DOCUMENTO REVOGADO (enunciado da Parte 2, §4.2): o KB-101 está aqui DE PROPÓSITO. É a
-- versão antiga do guia de SSL, anterior ao certbot, e responde ao mesmo relato do KB-101-A
-- (TKT-0001) com outra ação, outro time e outra prioridade. Vem antes do KB-101-A porque foi
-- publicado antes. O que acontece com e sem a curadoria está em docs/rag.md §2.1.
INSERT INTO kb_artigos VALUES
  ('KB-101', 'Certificado SSL vencido: renovação manual pelo painel',
   'certificado ssl renovacao vencido painel manual https',
   'Certificado emitido manualmente, com validade de um ano: não há renovação automática.',
   'Emitir e instalar um novo certificado pelo painel de administração. Exige acesso de administrador ao painel.',
   'escalar', 'Seguranca', 'P1', 'ssl_certificado', '', '2025-03-10', 'KB-101-A'),
  ('KB-101-A', 'Certificado SSL não renovou automaticamente',
   'certificado ssl renovacao vencido certbot https',
   'Desafio HTTP-01 falhando (porta 80 bloqueada ou DNS apontando para outro IP) ou timer do certbot parado.',
   'Conferir DNS do domínio e liberação da porta 80; rodar "certbot renew --dry-run"; reativar o timer do certbot.',
   'anotar', 'Infraestrutura', 'P2', 'ssl_certificado', '', '2026-02-02', NULL),
  -- vale para todos os planos: em nenhum deles o cliente ou o analista corrige o dono de um arquivo
  ('KB-102', 'Permissão negada ao gravar arquivos',
   'permissao negada gravar arquivos upload escrita dono pasta',
   'Arquivos ou pastas da conta com dono ou permissões incorretos, em geral depois de restauração, migração ou publicação feita por outro usuário.',
   'Identificar os arquivos e pastas com dono ou permissões incorretos e corrigi-los (chown/chmod). Exige acesso de administrador ao servidor, em qualquer plano.',
   'escalar', 'Infraestrutura', 'P2', 'permissao_arquivos',
   -- "permissão negada" no login por SSH é outro problema (KB-103)
   'ssh', '2026-10-06', NULL),
  ('KB-103', 'Acesso SSH bloqueado ou recusado',
   'ssh acesso bloqueado recusada fail2ban firewall',
   'IP do cliente banido pelo fail2ban após tentativas falhas, ou regra de firewall.',
   'Verificar se o IP do cliente está banido no fail2ban e liberar; conferir porta e regras do firewall.',
   'anotar', 'Seguranca', 'P2', 'acesso_ssh', '', '2026-01-15', NULL),
  ('KB-104', 'Site fora do ar com erro 5xx após deploy',
   '502 503 5xx deploy nginx indisponivel',
   'Processo da aplicação parado ou configuração inválida do nginx após o deploy (falha CONSTANTE).',
   'Reiniciar o processo da aplicação, validar a configuração do nginx; reverter o deploy só em acordo com o cliente (o deploy é dele).',
   'escalar', 'Infraestrutura', 'P1', 'site_fora_do_ar',
   -- o guia cobre a falha CONSTANTE; o 502 intermitente não tem procedimento (TKT-0006)
   'intermitente; as vezes; de vez em quando; oscila', '2026-05-20', NULL),
  ('KB-106', 'Falha de resolução DNS do domínio',
   'dns resolucao nameserver dominio zona',
   'Nameserver do domínio fora do ar ou zona DNS com registro inválido.',
   'Verificar o nameserver responsável pela zona e os registros do domínio; restabelecer o serviço de DNS.',
   'escalar', 'Infraestrutura', 'P1', 'dns_dominio', '', '2026-03-18', NULL),
  ('KB-105', 'Backup diário falhou',
   'backup falhou diario restauracao agendamento snapshot',
   'Cota de armazenamento de backup excedida ou janela de backup sobreposta a outra tarefa.',
   'Conferir a cota do storage de backup e o agendamento; reexecutar o job manualmente.',
   'anotar', 'Infraestrutura', 'P3', 'backup', '', '2026-04-08', NULL),
  -- OS GUIAS DE 11/10/2026 (KB-107 a KB-115): ampliam o corpus de 7 para 16 guias (15 vigentes). Foram
  -- escritos sem responder às perguntas sem resposta de dados/perguntas-rag.json (WordPress, preço,
  -- cancelamento, senha do painel...), e nenhum compartilha palavra-chave com os 8 chamados do gabarito.
  ('KB-107', 'Banco de dados recusando conexões',
   'banco dados mysql conexao recusada limite conexoes',
   'Limite de conexões simultâneas do servidor de banco de dados atingido, ou serviço do banco parado depois do reinício do servidor.',
   'Conferir se o serviço do banco está ativo e quantas conexões estão abertas; reiniciar o serviço e ajustar o limite de conexões da conta.',
   'escalar', 'Infraestrutura', 'P1', 'banco_dados',
   -- o guia cobre a recusa de conexão; consulta lenta é outro problema
   'lento; lentidao; consulta demorada', '2026-04-22', NULL),
  ('KB-108', 'Disco ou cota de armazenamento cheia',
   'disco cheio cota armazenamento espaco inodes',
   'Cota de disco da conta excedida por logs, caches ou cópias antigas acumulados.',
   'Listar os diretórios que mais ocupam espaço, remover logs e caches antigos e conferir se a cota de inodes também se esgotou.',
   'anotar', 'Infraestrutura', 'P3', 'cota_disco', '', '2026-03-02', NULL),
  ('KB-109', 'Tarefa agendada (cron) não executa',
   'cron crontab tarefa rotina programada script',
   'Entrada do crontab com sintaxe inválida, caminho do script errado ou usuário sem direito de execução sobre o script.',
   'Conferir a sintaxe da entrada no crontab, o caminho absoluto do script e o registro de execução do cron; testar o script à mão com o mesmo usuário.',
   'anotar', 'Infraestrutura', 'P3', 'cron_tarefas', '', '2026-05-12', NULL),
  ('KB-110', 'Site em laço de redirecionamentos',
   'redirecionamento redirecionamentos loop ciclo',
   'Regras de redirecionamento do servidor web em conflito: por exemplo, uma manda para HTTPS e outra manda de volta para o endereço sem HTTPS.',
   'Revisar as regras de redirecionamento do nginx, remover a regra duplicada e testar com curl -I seguindo os redirecionamentos.',
   'anotar', 'Infraestrutura', 'P2', 'redirecionamento', '', '2026-06-09', NULL),
  ('KB-111', 'Envio de e-mail rejeitado ou marcado como spam',
   'email smtp envio spf dkim rejeitado spam',
   'Registros SPF ou DKIM do domínio ausentes ou incorretos, ou IP de envio em lista de bloqueio.',
   'Conferir os registros SPF e DKIM da zona do domínio e consultar as listas de bloqueio para o IP de envio; corrigir a zona e reenviar uma mensagem de teste.',
   'anotar', 'Infraestrutura', 'P2', 'email_envio',
   -- o guia cobre o ENVIO; mensagem que não chega ao cliente é outro problema
   'recebimento; nao recebe; nao chega', '2026-07-14', NULL),
  ('KB-112', 'Bloqueio indevido pelo firewall de aplicação (WAF)',
   'waf firewall aplicacao bloqueio 403 falso positivo regra',
   'Regra do firewall de aplicação classificou como ataque uma requisição legítima do site e passou a devolver 403.',
   'Localizar no registro do WAF a regra acionada, liberar a requisição legítima com uma exceção restrita à URL e reavaliar a regra.',
   'escalar', 'Seguranca', 'P2', 'waf_bloqueio',
   -- ataque de verdade é incidente de segurança, outro procedimento
   'ataque; ddos; invasao', '2026-08-03', NULL),
  ('KB-113', 'Aplicação PHP esgotando a memória',
   'php memoria limite esgotada aplicacao script',
   'Limite de memória do PHP da conta menor que o necessário para o script, ou script com consumo anormal.',
   'Conferir no registro de erros a mensagem de memória esgotada, ajustar o limite de memória da conta dentro do teto do plano e identificar o script de maior consumo.',
   'anotar', 'Infraestrutura', 'P3', 'php_limites',
   -- este guia não ensina a instalar nem a trocar a versão do PHP
   'instalacao; instalar; atualizar versao', '2026-02-17', NULL),
  ('KB-114', 'Login por FTP ou SFTP falhando',
   'ftp sftp login senha conexao autenticacao',
   'Senha do usuário de FTP expirada ou alterada, ou IP do cliente barrado depois de tentativas de login sem sucesso.',
   'Redefinir a senha do usuário de FTP, conferir o registro de autenticação e liberar o IP do cliente se ele estiver barrado.',
   'anotar', 'Infraestrutura', 'P3', 'ftp_acesso',
   -- login por SSH é o KB-103
   'ssh', '2026-03-25', NULL),
  ('KB-115', 'Servidor com CPU ou memória saturada',
   'lento lentidao cpu carga saturacao processos',
   'Processo da aplicação consumindo CPU ou memória do servidor além da capacidade, em geral depois de um pico de acessos ou de um laço no código.',
   'Identificar o processo de maior consumo, reiniciar o serviço afetado e registrar a lentidão para a Infraestrutura avaliar o dimensionamento.',
   'escalar', 'Infraestrutura', 'P2', 'servidor_saturado',
   -- o guia cobre a saturação contínua; a lentidão que vem e vai não tem procedimento
   'intermitente; as vezes; de vez em quando', '2026-09-02', NULL);

-- ------------------------------------------------- fichas de plano (fonte E)
INSERT INTO planos_fichas VALUES
  ('Hospedagem Start',
   'Hospedagem compartilhada de entrada. O suporte cobre o ambiente do servidor: a conta, os certificados, o DNS, o e-mail e os arquivos do site. Não cobre desenvolvimento, correção ou depuração do código do site do cliente. Atendimento por chamado, em horário comercial.',
   '2026-01-10'),
  ('Hospedagem Business',
   'Hospedagem compartilhada com mais contas de e-mail e mais espaço em disco que o Start. O suporte cobre o ambiente do servidor e acompanha a configuração de domínio e de e-mail da empresa. Não cobre o código do site do cliente. Atendimento por chamado e por telefone, em horário comercial.',
   '2026-01-10'),
  ('VPS Pro',
   'Servidor virtual gerenciado pela empresa. O suporte cobre o sistema operacional, a rede, os certificados, o firewall e os backups da VPS. A aplicação instalada pelo cliente dentro da VPS está fora do escopo do suporte. Atendimento por chamado, em horário comercial.',
   '2026-01-10');

-- ------------------------------------------------- histórico de chamados internos
-- CLI-02 tem UMA ocorrência anterior de permissão negada ao gravar arquivos (o histórico que
-- contradiz o TKT-0003).
INSERT INTO chamados_internos
  (ticket_externo, cliente_id, categoria, resumo, kb_id, time_destino, prioridade, reincidencia, status, chave_idempotencia, criado_em)
VALUES
  ('TKT-0087', 'CLI-02', 'permissao_arquivos',
   'Permissão negada ao gravar arquivos; dono e permissões da pasta corrigidos pela Infraestrutura.', 'KB-102',
   'Infraestrutura', 'P2', 0, 'resolvido', 'TKT-0087:KB-102', '2026-09-01 15:00');

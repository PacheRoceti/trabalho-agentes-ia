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
   'anotar', 'Infraestrutura', 'P3', 'backup', '', '2026-04-08', NULL);

-- ------------------------------------------------- histórico de chamados internos
-- CLI-02 tem UMA ocorrência anterior de permissão negada ao gravar arquivos (o histórico que
-- contradiz o TKT-0003).
INSERT INTO chamados_internos
  (ticket_externo, cliente_id, categoria, resumo, kb_id, time_destino, prioridade, reincidencia, status, chave_idempotencia, criado_em)
VALUES
  ('TKT-0087', 'CLI-02', 'permissao_arquivos',
   'Permissão negada ao gravar arquivos; dono e permissões da pasta corrigidos pela Infraestrutura.', 'KB-102',
   'Infraestrutura', 'P2', 0, 'resolvido', 'TKT-0087:KB-102', '2026-09-01 15:00');

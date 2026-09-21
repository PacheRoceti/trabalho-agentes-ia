-- =====================================================================
-- Dados SIMULADOS do "sistema de tickets" (SQLite).
-- Nenhum dado real ou pessoal: clientes, domínios e servidores são fictícios.
--
-- OS CASOS DIFÍCEIS (nomeados, como pede o item 2.8 do enunciado):
--
--   TKT-0001  caso SIMPLES        dúvida rotineira com procedimento na base (KB-101)
--   TKT-0002  caso de DIVERGÊNCIA o cliente diz "Webmail fora do ar"; o log anexado
--                                 mostra falha de DNS (e existe procedimento de DNS
--                                 na base: a armadilha é agir sobre o log)
--   TKT-0003  ESCALONAMENTO com   disco cheio (KB-102, "escalar"); o cliente diz
--             REINCIDÊNCIA        "terceira vez", o histórico do sistema mostra 1
--   TKT-0007  ESCALONAMENTO       disco cheio (KB-102, "escalar") SEM a afirmação de reincidência:
--             SIMPLES             exercita a abertura de chamado (escrita irreversível) sem a
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
    id              TEXT PRIMARY KEY,      -- KB-000
    titulo          TEXT NOT NULL,
    palavras_chave  TEXT NOT NULL,         -- separadas por espaço, sem acento
    causa           TEXT NOT NULL,
    solucao         TEXT NOT NULL,
    acao_padrao     TEXT NOT NULL CHECK (acao_padrao IN ('anotar', 'escalar')),
    time_destino    TEXT NOT NULL,
    prioridade_base TEXT NOT NULL CHECK (prioridade_base IN ('P1', 'P2', 'P3'))
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
    ('CLI-06', 'Zeta Imóveis',         'Hospedagem Business');

-- ---------------------------------------------------------------- tickets
INSERT INTO tickets_externos VALUES
  ('TKT-0001', 'CLI-01',
   'O certificado SSL do meu site venceu ontem e a renovação automática não rodou. O navegador mostra aviso de site não seguro para os meus clientes.',
   '2026-09-21 08:12', 'novo', NULL),
  ('TKT-0002', 'CLI-06',
   'Meu Webmail está fora do ar desde cedo, ninguém da empresa consegue ler e-mail.',
   '2026-09-21 09:15', 'novo',
   '2026-09-21 09:31:07 ERRO resolver: falha de resolução DNS para mail.zeta.com.br (SERVFAIL); nameserver ns1.zeta.com.br não responde. Serviço webmail: processo ativo, porta 443 respondendo.'),
  ('TKT-0003', 'CLI-02',
   'É a TERCEIRA vez que o meu servidor fica sem espaço em disco e os sistemas param! Exijo prioridade máxima agora.',
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
  ('TKT-0007', 'CLI-01',
   'O disco do meu servidor encheu e os sistemas pararam de gravar arquivos. Preciso de ajuda para liberar espaço.',
   '2026-09-21 11:30', 'novo', NULL),
  -- ticket antigo, existe só para dar histórico ao CLI-02
  ('TKT-0087', 'CLI-02',
   'Servidor sem espaço em disco, parou de gravar arquivos.',
   '2026-09-01 14:20', 'resolvido', NULL);

-- ------------------------------------------------ base de conhecimento (v0)
-- Substituída por RAG (busca vetorial) na Parte 2.
INSERT INTO kb_artigos VALUES
  ('KB-101', 'Certificado SSL não renovou automaticamente',
   'certificado ssl renovacao vencido certbot https',
   'Desafio HTTP-01 falhando (porta 80 bloqueada ou DNS apontando para outro IP) ou timer do certbot parado.',
   'Conferir DNS do domínio e liberação da porta 80; rodar "certbot renew --dry-run"; reativar o timer do certbot.',
   'anotar', 'Infraestrutura', 'P2'),
  ('KB-102', 'Disco do servidor cheio',
   'disco espaco cheio armazenamento inode logs',
   'Logs e backups acumulados ou crescimento de dados do cliente.',
   'Identificar diretórios maiores (du -sh), rotacionar logs, avaliar aumento de disco. Exige acesso ao servidor.',
   'escalar', 'Infraestrutura', 'P2'),
  ('KB-103', 'Acesso SSH bloqueado ou recusado',
   'ssh acesso bloqueado recusada fail2ban firewall',
   'IP do cliente banido pelo fail2ban após tentativas falhas, ou regra de firewall.',
   'Verificar se o IP do cliente está banido no fail2ban e liberar; conferir porta e regras do firewall.',
   'anotar', 'Seguranca', 'P2'),
  ('KB-104', 'Site fora do ar com erro 5xx após deploy',
   '502 503 5xx deploy nginx indisponivel',
   'Processo da aplicação parado ou configuração inválida do nginx após o deploy (falha CONSTANTE).',
   'Reiniciar o processo da aplicação, validar a configuração do nginx e reverter o deploy se necessário.',
   'escalar', 'Infraestrutura', 'P1'),
  ('KB-106', 'Falha de resolução DNS do domínio',
   'dns resolucao nameserver dominio zona',
   'Nameserver do domínio fora do ar ou zona DNS com registro inválido.',
   'Verificar o nameserver responsável pela zona e os registros do domínio; restabelecer o serviço de DNS.',
   'escalar', 'Infraestrutura', 'P1'),
  ('KB-105', 'Backup diário falhou',
   'backup falhou diario restauracao agendamento snapshot',
   'Cota de armazenamento de backup excedida ou janela de backup sobreposta a outra tarefa.',
   'Conferir a cota do storage de backup e o agendamento; reexecutar o job manualmente.',
   'anotar', 'Infraestrutura', 'P3');

-- ------------------------------------------------- histórico de chamados internos
-- CLI-02 tem UMA ocorrência anterior de disco cheio (o histórico que contradiz o TKT-0003).
INSERT INTO chamados_internos
  (ticket_externo, cliente_id, categoria, resumo, kb_id, time_destino, prioridade, reincidencia, status, chave_idempotencia, criado_em)
VALUES
  ('TKT-0087', 'CLI-02', 'disco_cheio',
   'Disco do servidor cheio; logs rotacionados pela Infraestrutura.', 'KB-102',
   'Infraestrutura', 'P2', 0, 'resolvido', 'TKT-0087:KB-102', '2026-09-01 15:00');

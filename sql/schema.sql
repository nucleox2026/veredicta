-- Veredicta — schema PostgreSQL
--
-- Estado de transição:
-- 1. A arquitetura nova pesquisa processos diretamente no DataJud.
-- 2. Pesquisas e processos consultados não precisam ser persistidos.
-- 3. process_analyses é a tabela persistente utilizada pela nova arquitetura.
-- 4. search_runs e process_records permanecem abaixo apenas para compatibilidade
--    temporária com dados/rotas legadas e podem ser removidos depois da validação
--    definitiva em produção.


-- =========================================================
-- LEGADO — EXECUÇÕES DE COLETA
-- =========================================================

create table if not exists search_runs (
  id bigserial primary key,
  tribunal varchar(20) not null default 'TJMT',
  date_from date not null,
  date_to date not null,
  subject_text varchar(255),
  status varchar(30) not null default 'created',
  total_found integer,
  created_at timestamptz not null default now()
);

create index if not exists
  ix_search_runs_status
on search_runs(status);


-- =========================================================
-- LEGADO — PROCESSOS PERSISTIDOS
-- =========================================================

create table if not exists process_records (
  id bigserial primary key,
  numero_processo varchar(40) not null unique,
  tribunal varchar(20) not null default 'TJMT',
  data_ajuizamento timestamptz,
  grau varchar(20),
  classe_nome varchar(255),
  orgao_julgador_nome varchar(500),
  assuntos jsonb,
  raw_source jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists
  ix_process_records_tribunal
on process_records(tribunal);

create index if not exists
  ix_process_records_data
on process_records(data_ajuizamento);


-- =========================================================
-- ATUAL — ANÁLISES SOB DEMANDA
-- =========================================================

create table if not exists process_analyses (
  id bigserial primary key,

  tribunal varchar(20),

  numero_processo varchar(40)
    not null
    unique,

  dano_moral varchar(30),

  direito_personalidade varchar(255),

  empresa_re varchar(500),

  resultado varchar(100),

  -- Campo legado, mantido temporariamente.
  valor_indenizacao_centavos bigint,

  -- Campo específico para jurimetria:
  -- somente valor efetivamente arbitrado judicialmente.
  valor_arbitrado_juiz_centavos bigint,

  -- Evidência textual que sustenta o valor acima.
  fonte_valor_arbitrado text,

  -- Nova modelagem jurimétrica.
  confianca_resultado integer
    check (
      confianca_resultado is null
      or confianca_resultado between 0 and 100
    ),

  confianca_valor integer
    check (
      confianca_valor is null
      or confianca_valor between 0 and 100
    ),

  valor_primeiro_grau_centavos bigint,

  valor_final_centavos bigint,

  situacao_valor varchar(50),

  fonte_valor text,

  evidencias_resultado jsonb,

  evidencias_valor jsonb,

  prompt_version varchar(50),

  analyzed_at timestamptz,

  resumo text,

  fundamentos jsonb,

  confianca integer
    check (
      confianca between 0 and 100
    ),

  model_name varchar(100),

  created_at timestamptz
    not null
    default now()
);

create index if not exists
  ix_process_analyses_tribunal
on process_analyses(tribunal);

create index if not exists
  ix_process_analyses_tribunal_numero
on process_analyses(
  tribunal,
  numero_processo
);


-- =========================================================
-- MIGRAÇÃO SEGURA PARA BANCOS JÁ EXISTENTES
-- =========================================================

alter table process_analyses
  add column if not exists
  tribunal varchar(20);

alter table process_analyses
  add column if not exists
  valor_arbitrado_juiz_centavos bigint;

alter table process_analyses
  add column if not exists
  fonte_valor_arbitrado text;

alter table process_analyses
  add column if not exists
  confianca_resultado integer;

alter table process_analyses
  add column if not exists
  confianca_valor integer;

alter table process_analyses
  add column if not exists
  valor_primeiro_grau_centavos bigint;

alter table process_analyses
  add column if not exists
  valor_final_centavos bigint;

alter table process_analyses
  add column if not exists
  situacao_valor varchar(50);

alter table process_analyses
  add column if not exists
  fonte_valor text;

alter table process_analyses
  add column if not exists
  evidencias_resultado jsonb;

alter table process_analyses
  add column if not exists
  evidencias_valor jsonb;

alter table process_analyses
  add column if not exists
  prompt_version varchar(50);

alter table process_analyses
  add column if not exists
  analyzed_at timestamptz;

-- As análises históricas anteriores à arquitetura multi-TJ
-- pertenciam ao fluxo TJMT.
update process_analyses
set tribunal = 'TJMT'
where tribunal is null;

create index if not exists
  ix_process_analyses_tribunal_numero
on process_analyses(
  tribunal,
  numero_processo
);

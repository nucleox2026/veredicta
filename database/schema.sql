-- Veredicta — referência de schema PostgreSQL
--
-- Observação: este arquivo documenta a estrutura atual. Em produção,
-- alterações incrementais devem ser aplicadas de forma controlada.

create table if not exists process_analyses (
  id bigserial primary key,
  tribunal varchar(20),
  numero_processo varchar(40) not null unique,

  dano_moral varchar(30),
  direito_personalidade varchar(255),
  empresa_re varchar(500),
  resultado varchar(100),

  valor_indenizacao_centavos bigint,
  valor_arbitrado_juiz_centavos bigint,
  fonte_valor_arbitrado text,

  confianca_resultado integer,
  confianca_valor integer,
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
  confianca integer,
  model_name varchar(100),

  tem_sentenca boolean,
  empresa_re_normalizada varchar(500),
  condutas jsonb,
  lida boolean not null default false,
  lida_em timestamptz,
  capacidade_economica_faixa varchar(50),
  capacidade_economica_fonte text,
  capacidade_economica_referencia text,
  enrichment_at timestamptz,

  djen_status varchar(50),
  djen_checked_at timestamptz,
  djen_ultima_comunicacao_hash varchar(128),
  djen_valores jsonb,

  created_at timestamptz not null default now()
);

create index if not exists ix_process_analyses_tribunal
  on process_analyses(tribunal);

create index if not exists ix_process_analyses_tribunal_numero
  on process_analyses(tribunal, numero_processo);

create index if not exists ix_process_analyses_tem_sentenca
  on process_analyses(tem_sentenca);

create index if not exists ix_process_analyses_empresa_re_normalizada
  on process_analyses(empresa_re_normalizada);

create index if not exists ix_process_analyses_lida
  on process_analyses(lida);

create index if not exists ix_process_analyses_djen_status
  on process_analyses(djen_status);

create table if not exists process_watches (
  id bigserial primary key,
  tribunal varchar(20) not null,
  numero_processo varchar(40) not null,
  ativo boolean not null default true,
  ultimo_hash_movimentos varchar(64),
  ultima_data_movimento timestamptz,
  atividade_detectada_em timestamptz,
  reanalisar_apos timestamptz,
  ultima_verificacao timestamptz,
  ultima_analise_automatica timestamptz,
  status varchar(30) not null default 'monitorando',
  erro_ultimo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_process_watches_tribunal_numero
    unique (tribunal, numero_processo)
);

create index if not exists ix_process_watches_ativo_status
  on process_watches(ativo, status);

create index if not exists ix_process_watches_reanalisar_apos
  on process_watches(reanalisar_apos);

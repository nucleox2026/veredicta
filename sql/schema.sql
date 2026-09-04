-- Veredicta — schema PostgreSQL
--
-- Arquitetura V1:
-- - buscas são transitórias e consultam o DataJud sob demanda;
-- - processos consultados não são persistidos;
-- - somente análises jurídicas sob demanda são persistidas.


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

  -- Campos de compatibilidade temporária.
  valor_indenizacao_centavos bigint,
  valor_arbitrado_juiz_centavos bigint,
  fonte_valor_arbitrado text,

  -- Modelagem jurimétrica atual.
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
      confianca is null
      or confianca between 0 and 100
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
-- Monitoramento automático por processo
-- =========================================================

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

create index if not exists
  ix_process_watches_ativo_status
on process_watches(ativo, status);

create index if not exists
  ix_process_watches_reanalisar_apos
on process_watches(reanalisar_apos);

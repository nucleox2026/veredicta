-- JurisIA — schema inicial PostgreSQL
-- O FastAPI também consegue criar estas tabelas via SQLAlchemy durante o MVP.

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

create index if not exists ix_search_runs_status on search_runs(status);

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

create index if not exists ix_process_records_tribunal on process_records(tribunal);
create index if not exists ix_process_records_data on process_records(data_ajuizamento);

create table if not exists process_analyses (
  id bigserial primary key,
  numero_processo varchar(40) not null unique,
  dano_moral varchar(30),
  direito_personalidade varchar(255),
  empresa_re varchar(500),
  resultado varchar(100),
  valor_indenizacao_centavos bigint,
  resumo text,
  fundamentos jsonb,
  confianca integer check (confianca between 0 and 100),
  model_name varchar(100),
  created_at timestamptz not null default now()
);

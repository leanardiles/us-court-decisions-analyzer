-- Capstone II ingest schema for one shared Supabase Postgres database.
-- Unit of identity: LEXIS citation (e.g. 2020 U.S. Dist. LEXIS 187996).
-- "Craig v. Simon" and "Craig v. Simon (2)" are different decisions in one family.

create extension if not exists vector;

create table if not exists litigation_families (
  id uuid primary key default gen_random_uuid(),
  family_key text not null unique,
  short_name text not null,
  member_count integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists decisions (
  id uuid primary key default gen_random_uuid(),
  lexis_citation text unique,
  reporter_citation text,
  short_name text not null,
  source_filename text not null unique,
  family_id uuid references litigation_families(id),
  court text,
  court_level text,
  decision_date date,
  docket_number text,
  state text,
  judges_names jsonb,
  prior_history text,
  subsequent_history text,
  related_proceeding text,
  opinion_text text,
  dissent_text text,
  concur_text text,
  file_sha256 text,
  text_sha256 text,
  char_count integer,
  ingested_at timestamptz not null default now()
);

create table if not exists decision_relations (
  id uuid primary key default gen_random_uuid(),
  from_decision_id uuid not null references decisions(id) on delete cascade,
  to_decision_id uuid references decisions(id) on delete set null,
  from_lexis_citation text not null,
  to_lexis_citation text not null,
  relation_type text not null,
  target_in_corpus boolean not null default false,
  unique (from_lexis_citation, to_lexis_citation, relation_type)
);

-- Chunks / pgvector land in Stage 3. Created now so the store is ready.
create table if not exists opinion_chunks (
  id uuid primary key default gen_random_uuid(),
  decision_id uuid not null references decisions(id) on delete cascade,
  section text,
  chunk_index integer not null,
  text text not null,
  char_start integer,
  char_end integer,
  token_count integer,
  embedding extensions.vector(384)
);

create index if not exists decisions_family_id_idx on decisions (family_id);
create index if not exists decisions_lexis_citation_idx on decisions (lexis_citation);
create index if not exists decision_relations_from_idx on decision_relations (from_lexis_citation);
create index if not exists opinion_chunks_decision_id_idx on opinion_chunks (decision_id);

"""
Supabase / Postgres schema for Capstone II ingest.

Paste into the Supabase SQL editor, or run against the project database.
Identity unit is lexis_citation. A litigation_family groups related
decisions from the same lawsuit (district + appeal, successive orders, etc.).
"""

from __future__ import annotations

SCHEMA_SQL = """
create extension if not exists vector with schema extensions;

create table if not exists litigation_families (
  id uuid primary key default gen_random_uuid(),
  family_key text not null unique,
  short_name text not null,
  member_count integer not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists decisions (
  id uuid primary key default gen_random_uuid(),
  lexis_citation text not null unique,
  reporter_citation text,
  reporter_line_raw text,
  reporter_citations text[],
  short_name text not null,
  source_filename text not null unique,
  family_id uuid references litigation_families(id),
  court text,
  court_level text,
  decision_date date,
  date_line_raw text,
  decision_date_source text,
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

alter table public.decisions add column if not exists reporter_line_raw text;
alter table public.decisions add column if not exists reporter_citations text[];
alter table public.decisions add column if not exists date_line_raw text;
alter table public.decisions add column if not exists decision_date_source text;

alter table public.decisions enable row level security;
alter table public.decision_relations enable row level security;
alter table public.litigation_families enable row level security;
alter table public.opinion_chunks enable row level security;
""".strip()

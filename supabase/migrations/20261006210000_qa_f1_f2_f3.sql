-- QA 2026-10-06: F1 RLS, F2 date-source columns, F3 reporter columns.
-- No policies: RLS on + no policy means the public REST API returns nothing.
-- Ingest keeps using the Postgres connection string (bypasses RLS).

alter table public.decisions add column if not exists reporter_line_raw text;
alter table public.decisions add column if not exists reporter_citations text[];
alter table public.decisions add column if not exists date_line_raw text;
alter table public.decisions add column if not exists decision_date_source text;

alter table public.decisions alter column lexis_citation set not null;

alter table public.decisions enable row level security;
alter table public.decision_relations enable row level security;
alter table public.litigation_families enable row level security;
alter table public.opinion_chunks enable row level security;

# Capstone II ingest

Rule-based parse of LEXIS Word exports into the shared Supabase Postgres store. No Groq. Embeddings are local (`BAAI/bge-small-en-v1.5`, 384-d).

Identity is `lexis_citation`. Same caption with `(2)` is another decision in the same litigation family, not a duplicate. True duplicates share a citation or `text_sha256`.

## Setup

From `backend/`:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `SUPABASE_URL`, `SUPABASE_DB_PASSWORD` (single-quote it if it contains `#` or `$`), and `SUPABASE_DB_URL` (session pooler, port 6543). Do not use `db.*.supabase.co` on IPv4. Do not query tables with the publishable/anon key — RLS is on and there are no public policies.

Word files stay local (`current_docs/MS Word files (544 files total)/`, gitignored). Point tests at them with `WORD_CORPUS_DIR` if the folder moves.

## Commands

```bash
# from backend/
./venv/bin/python -m app.ingest.load_supabase --ping
./venv/bin/python -m app.ingest.load_supabase --apply-schema
./venv/bin/python -m app.ingest.load_supabase --all
./venv/bin/python -m app.ingest.load_supabase --embed          # slow; hours on CPU
./venv/bin/python -m app.ingest.load_supabase --query "Purcell principle" --k 5
./venv/bin/python -m app.ingest.load_supabase --query "..." --lexis "2020 U.S. Dist. LEXIS 187996"
```

`--all` upserts decisions and drops leftover re-export rows. It does not rebuild embeddings unless you pass `--embed`.

## Python retrieve

```python
from app.ingest.load_supabase import retrieve
hits = retrieve(question, k=8, lexis_citation=cite, print_results=False)
# keys: decision_id, short_name, lexis_citation, source_filename,
#       section, chunk_index, char_start, char_end, score, text
```

## Date and citation rules

- `decision_date` = Decided, else Filed, else Released / Entered / Rendered / Issued. Never Argued or Submitted.
- LEXIS cite comes from the Reporter / Reportero line; any `YYYY … LEXIS N` form (federal and state).
- Files with no LEXIS citation are logged and not stored.

## Tests

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m unittest tests.test_extract_qa -v
```

## Schema

`schema.py`, `supabase_schema.sql`, and `supabase/migrations/`. New tables must enable RLS.

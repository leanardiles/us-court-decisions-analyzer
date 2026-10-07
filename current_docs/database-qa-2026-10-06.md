# Database QA: Findings and Fix Plan

**Date:** October 6, 2026 · **Reviewed by:** Leandro · **For:** Enock
**Database:** Supabase project for `court-opinions-verification` (tables `decisions`, `decision_relations`, `litigation_families`, `opinion_chunks`)
**Related:** [`docs/data-model.md`](data-model.md), [`docs/pilot-plan.md`](pilot-plan.md)

---

## How to use this document

This is written so you can hand it to an AI coding assistant together with the ingest code. Suggested way of working:

1. **One fix at a time**, in the order of section 4. Each fix has: the problem, the evidence, the required change, and an **acceptance check** (a SQL query with the expected result).
2. **Keep the current schema shape.** Do not redesign the tables to match `data-model.md`. The `decisions` table with three text columns works for the pilot. Only make the small schema additions listed in section 5.
3. **Add a regression test for each fix**, using the example files named in section 6.
4. **Rebuild once at the end** (section 7), then run all the queries in the appendix and paste the results in the pull request.

Nothing in the database is referenced by labels or experiment runs yet, so a full rebuild is safe **now**. Once the RAs start labeling, decision IDs must stay stable.

---

## 1. Summary

| Area | Status |
|---|---|
| Chunk offsets | ✅ 14,987 of 14,987 chunks match their text exactly |
| Same-name decisions kept separate | ✅ 74 same-name groups (183 decisions) preserved |
| Dissent splitting | ✅ No dissent headings left inside `opinion_text` |
| Federal and Supreme Court citations | ✅ Almost complete |
| Row-level security | ❌ Off on all 4 tables |
| Decision dates | ❌ First date on the line is taken (Argued / Submitted instead of Decided / Filed) |
| Lexis citations for state and other courts | ❌ 86 decisions without one |
| Families | ⚠️ Built by case name, not by citation links |
| Concurrence splitting | ❌ 64 decisions have a concurrence inside `opinion_text` |
| Deduplication by text | ❌ One identical pair stored twice |
| Star-page markers | ⚠️ Inconsistent: partly kept, partly stripped |
| Broken records and encoding | ❌ 2 records with failed header parsing; one garbled accented name |

## 2. What works and must not break

- **Offsets:** `substring(<section text> from char_start + 1 for char_end - char_start) = chunk.text` holds for every chunk. Keep this round-trip test in the code.
- **No collapsing by name:** *Craig v. Simon* (D. Minn., `2020 U.S. Dist. LEXIS 187996`) and *Craig v. Simon* (8th Cir., `2020 U.S. App. LEXIS 33403`) are separate rows in one family. Keep it that way.
- **Dissents** are correctly separated into `dissent_text`.
- **Embeddings** exist for every chunk (pgvector 0.8.2).

## 3. Numbers at the time of review

| Check | Value |
|---|---|
| Decisions | 540 (539 after removing the duplicate in F6) |
| Lexis citation missing | 86 |
| Lexis citation duplicated | 0 |
| Same-name groups / decisions in them | 74 / 183 |
| Families / multi-member families | 427 / 77 |
| Relations / relations pointing inside the corpus | 383 / 89 |
| Decisions with dissent / with concurrence | 123 / 3 |
| Docket number missing | 79 |
| Chunks (all with offsets and embeddings) | 14,987 |
| Date range | 2006-10-18 to 2026-03-06 |

Court levels: 306 federal district, 138 federal appellate, 24 U.S. Supreme Court, 52 state supreme, 2 state appellate, 16 other, 2 missing.

---

## 4. Fixes, in order

### F1. Turn on row-level security · **Do today**

**Problem.** Row-level security is off on all four tables. In Supabase, every table in the `public` schema is exposed through the automatic REST API, readable by anyone with the project URL and the anon key, which is designed to be public. The full LexisNexis text is therefore readable through the API.

**Required change.**

```sql
alter table public.decisions enable row level security;
alter table public.decision_relations enable row level security;
alter table public.litigation_families enable row level security;
alter table public.opinion_chunks enable row level security;
```

No policies are needed: with RLS on and no policies, the public API returns nothing, while the database connection string and the service role key keep full access.

Also:
- Make sure the ingest scripts connect with the **connection string or the service role key**, never the anon key.
- Check that no Supabase URL or key was ever committed to a repo, `.env` file or notebook. If one was, rotate the keys in the Supabase dashboard.
- Every table created from now on is created with RLS enabled.

**Acceptance check.** Query A1 in the appendix returns `rls_enabled = true` for every table.

---

### F2. Decision date rule · **Before the pilot**

**Problem.** The parser takes the first date in the header's date line. Appellate decisions often list an *Argued* or *Submitted* date first.

**Evidence.**
- *Craig v. Simon* (8th Cir.): header says *"October 16, 2020, Submitted; October 23, 2020, Filed"*. Stored: 2020-10-16. Correct: **2020-10-23**.
- *Crawford v. Marion County Election Bd.* (7th Cir.): stored 2006-10-18, but its citation is `2007 U.S. App. LEXIS 110`, so the decision is from early January 2007. The stored date is the argument date.

**Required change.**
1. Parse the whole date line into (date, label) pairs. Labels seen in Lexis headers include *Decided*, *Filed*, *Submitted*, *Argued*, *Released*, *Entered*.
2. `decision_date` = the *Decided* date if present, otherwise *Filed*, otherwise *Released* / *Entered*. **Never** *Argued* or *Submitted*.
3. New column `date_line_raw` (text): the full original date line.
4. New column `decision_date_source` (text): which label was used (`decided`, `filed`, `released`, `entered`, `none`).

`date_line_raw` also matters for the models: the decisions table stores no header text, so for district court rulings the model may otherwise never see the decision's own date, which question T3 needs.

**Acceptance check.** Query A3: Craig (8th Cir.) shows 2020-10-23; Crawford shows a 2007 date. Query A4 (date year vs. citation year) returns 0 rows, or only cases reviewed by hand. Report the count per `decision_date_source`.

---

### F3. Lexis citation parsing for all courts · **Before the pilot**

**Problem.** The parser only recognizes federal formats (`U.S. Dist. LEXIS`, `U.S. App. LEXIS`, `U.S. LEXIS`). Every Lexis document has a Lexis citation on its *Reporter* line, so these are parsing misses, not missing data.

**Evidence.** Missing `lexis_citation` by court level: state supreme 47 of 52, other 15 of 16, state appellate 2 of 2, missing court level 2 of 2, federal appellate 17 of 138, federal district 3 of 306, U.S. Supreme 0 of 24.

**Required change.**
1. Read the *Reporter* line, split on `;`, strip the `*` / `**` markers, and pick the entry containing `LEXIS`.
2. Use a general pattern rather than a list of formats, e.g. `\b\d{4}\s+[A-Z][A-Za-z.&'\s]*?\s+LEXIS\s+\d+\b`. It must match forms like `2020 Pa. LEXIS 1234`, `2020 Ohio LEXIS 2072`, `2020 Ga. App. LEXIS 55`, as well as the federal ones.
3. Look at the 17 federal appellate misses separately: they may have an unusual *Reporter* line layout.
4. Store all reporter citations, not just one (e.g. a `reporter_citations` text array, or keep the full *Reporter* line in a `reporter_line_raw` column).
5. After the fix, add `not null` and `unique` constraints on `lexis_citation`. If a document truly has none, it should fail loudly in the file log (F6), not be stored silently.

**Acceptance check.** Query A2: `lexis_citation_null = 0` and `lexis_citation_duplicated = 0`.

---

### F4. Families from citation links · **Before the pilot** (after F3)

**Problem.** `family_key` is the lowercased case name, so families are built by name. This is mostly right (*Frank v. Walker* 2014 and 2016 is one lawsuit), but unverified: different lawsuits sharing a name get merged, and related decisions with different names are missed (Craig's Supreme Court stay denial is filed as *Kistner v. Craig*).

**Evidence.** Many multi-member families have 0 citation links inside the corpus: *LULAC v. Abbott* (2022 and 2025), *Common Cause Ind. v. Lawson* (4 members), *Baker v. City of Atlanta*, *Frank v. Walker*, among others.

**Required change.**
1. Match relation targets on **any** citation of the target decision, not only the Lexis citation. History lines often cite the reporter form, e.g. *"Craig v. Simon, 978 F.3d 1043, 2020 U.S. App. LEXIS 33403"*.
2. Build families as connected components of a graph whose edges are: (a) relations between decisions in the corpus, **plus** (b) the existing same-name grouping. Keeping (b) is deliberate: over-merging is the safe direction for the practice/test split, because it keeps related decisions together.
3. New column `family_method` on `litigation_families`: `single`, `citation`, `name`, or `citation+name`.

**Acceptance check.** Query A3: the Craig family has 2 members and `family_method` includes `citation`. Query A5 lists name-only multi-member families with their date spans; this list gets a manual review for the 50 pilot cases.

---

### F5. Concurrence splitting · **Before the pilot**

**Problem.** Concurrences stay inside `opinion_text`, so a concurring judge's reasoning is attributed to the majority.

**Evidence.** 64 decisions have a concurrence heading inside `opinion_text`; only 3 decisions have `concur_text`. Dissent splitting works, so the same approach can be applied.

**Required change.**
1. Split on concurrence headings the same way as dissents. The header's *Concur by:* line gives the authors to expect.
2. If a decision has several concurrences (or several dissents), keep them all in the same column, each starting with a marker line such as `[Concurrence by JUDGE NAME]`.
3. Opinions "concurring in part and dissenting in part" follow the heading Lexis uses for them.

**Acceptance check.** Query A6: `concur_heading_in_opinion = 0`; `docs_with_concur` rises to roughly 60 or more.

---

### F6. Deduplicate by text, and log every file · **Before the pilot**

**Problem.** Identical texts are not deduplicated when the citation is missing.

**Evidence.** *McKitrick v. LaRose.docx* and *McKitrick v. LaRose(2).docx*: same `text_sha256`, two rows, both with no citation.

**Required change.**
1. Treat two files as the same decision if they share the Lexis citation **or** the `text_sha256`.
2. Add a file log table, so each of the 541 files is accounted for:

```sql
create table public.source_files (
  id uuid primary key default gen_random_uuid(),
  file_name text not null,
  file_sha256 text not null,
  decision_id uuid references public.decisions(id),
  is_duplicate boolean not null default false,
  parse_status text not null,          -- ok / warning / failed
  parse_errors jsonb,
  ingested_at timestamptz not null default now()
);
alter table public.source_files enable row level security;
```

**Acceptance check.** Query A2: `text_sha256_duplicated = 0`. Query A7: 541 files in `source_files`, with the McKitrick `(2)` file marked `is_duplicate`.

---

### F7. Keep star-page markers · **Before the pilot**

**Problem.** Page markers are inconsistent: the exact pattern `[*NNN]` appears in 0 decisions, `[*` appears in 87, and a star followed by digits appears in 228. Some were stripped and some kept in a different form.

**Why it matters.** RAs cite pages from the Word files (e.g. `*778`), and models must be able to cite the same pages so evidence can be checked.

**Required change.**
1. Keep every marker exactly as Lexis prints it: `[*778]` (pages of the first citation on the *Reporter* line) and `[**3]` (pages of the second). No spaces inside, no backslash escapes.
2. If any step converts to Markdown, check it doesn't escape the asterisks (`\*`). Extracting with `python-docx` directly avoids this.
3. Stripping markers is fine for the copy used to compute embeddings, but not for the stored text.

**Acceptance check.** Query A6: `has_bracket_star` close to the total number of decisions, and the exact patterns `\[\*\d+\]` and `\[\*\*\d+\]` found in most decisions.

---

### F8. Broken records and encoding · **Before the pilot**

**Evidence.**
- One decision's `short_name` is *"October 11, 2020, Decided"* (384 characters, no court, no citation). The header layout of that file wasn't recognized.
- *Mundo R'os v. CEE*: no court, no date, no citation, and the name is garbled. It should read *Ríos*, which suggests an encoding problem with accented characters. This looks like a Puerto Rico Supreme Court decision.

**Required change.**
1. Find the source files of both records and fix the header parsing for their layouts.
2. Read and write everything as UTF-8 end to end, and check all accented names against their filenames.
3. Any file whose header can't be parsed gets `parse_status = failed` in `source_files` instead of a half-filled row.

**Acceptance check.** Query A8 returns no rows: no decision with a missing court, court level or date, and no name that looks like a date line. Query A9 lists names with non-ASCII characters for a visual check.

---

### F9. Docket numbers · **Later, nice to have**

79 decisions have no docket number. Parse the *No.*, *Case No.* and *Docket No.* forms, and allow several docket numbers per decision (a text array). Not blocking for the pilot.

---

## 5. Schema additions, all together

| Table | Addition |
|---|---|
| `decisions` | `date_line_raw text`, `decision_date_source text`, all reporter citations (array or raw *Reporter* line), `not null` + `unique` on `lexis_citation` |
| `litigation_families` | `family_method text` |
| new `source_files` | as in F6 |
| all tables | row-level security enabled |

Out of scope for this work: the ground-truth and experiment tables (`labels`, `answer_key`, `runs`, `calls` and others in `data-model.md`). Leandro and Tafadzwa create those.

## 6. Regression test files

Use these files as test cases, one or more assertions each:

| File | Tests |
|---|---|
| `Craig v. Simon.docx` and `Craig v. Simon (2).docx` | Two decisions, correct citations, 8th Cir. date 2020-10-23, one family linked by citation |
| *Crawford v. Marion County Election Bd.* | Decision date in 2007, not the 2006 argument date |
| `McKitrick v. LaRose.docx` and `(2)` | One decision, one duplicate file, citation present |
| *Eakin v. Adams County Bd. of Elections* | Short order in `opinion_text`, substance in `dissent_text`, nothing lost |
| *Mundo Ríos v. CEE* | Court, date and citation parsed; accent preserved |
| The file behind the *"October 11, 2020, Decided"* record | Correct case name and court |
| Any decision with a concurrence | Concurrence in `concur_text`, not in `opinion_text` |

The Word files are licensed: tests should read them from the shared folder (path in an environment variable), never from a committed copy. Commit only the expected values.

## 7. Rebuild order

1. F1 now, independently.
2. Parser fixes that change identity or text: F3, F6, F8, F7, F5, F2.
3. Full re-ingest of all files. Rebuilding from scratch is fine as long as no labels exist.
4. Relations and families (F4), after the citations are fixed.
5. Re-chunk and re-embed: the text changes with F5 and F7, so the old offsets are no longer valid.
6. Run every query in the appendix and paste the results in the pull request.

## 8. Scope questions for Codrington (not blocking this work)

- 54 state decisions and 16 "other" (including Puerto Rico, possibly in Spanish): in or out of the pilot? His stated goal concerns federal courts.
- If the pilot is federal-only, F3 shrinks to about 20 decisions, but the fixes are still worth doing for the corpus.

---

## Appendix: verification queries

Run each one separately in the Supabase SQL Editor. None returns opinion text.

**A1. Row-level security**

```sql
select c.relname as table_name, c.reltuples::bigint as approx_rows, c.relrowsecurity as rls_enabled
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by 1;
```

**A2. Summary**

```sql
select 'decisions_total' as check_name, count(*)::text as value from decisions
union all select 'lexis_citation_null', count(*)::text from decisions where lexis_citation is null
union all select 'lexis_citation_duplicated', count(*)::text from (select lexis_citation from decisions where lexis_citation is not null group by 1 having count(*) > 1) x
union all select 'text_sha256_duplicated', count(*)::text from (select text_sha256 from decisions group by 1 having count(*) > 1) x
union all select 'same_name_groups', count(*)::text from (select short_name from decisions group by 1 having count(*) > 1) x
union all select 'opinion_text_empty', count(*)::text from decisions where coalesce(length(opinion_text), 0) = 0
union all select 'char_count_under_2000', count(*)::text from decisions where char_count < 2000
union all select 'decision_date_null', count(*)::text from decisions where decision_date is null
union all select 'court_null', count(*)::text from decisions where court is null
union all select 'docket_null', count(*)::text from decisions where docket_number is null
union all select 'family_id_null', count(*)::text from decisions where family_id is null
union all select 'families_total', count(*)::text from litigation_families
union all select 'families_multi_member', count(*)::text from litigation_families where member_count > 1
union all select 'relations_total', count(*)::text from decision_relations
union all select 'relations_target_in_corpus', count(*)::text from decision_relations where target_in_corpus
union all select 'docs_with_dissent', count(*)::text from decisions where length(dissent_text) > 0
union all select 'docs_with_concur', count(*)::text from decisions where length(concur_text) > 0
union all select 'chunks_total', count(*)::text from opinion_chunks
union all select 'chunks_null_offsets', count(*)::text from opinion_chunks where char_start is null or char_end is null
union all select 'date_min', min(decision_date)::text from decisions
union all select 'date_max', max(decision_date)::text from decisions
union all select 'court_level=' || coalesce(court_level, 'null'), count(*)::text from decisions group by court_level;
```

**A3. Spot checks: Craig, Crawford, Eakin, McKitrick**

```sql
select d.short_name, d.court_level, d.decision_date, d.lexis_citation,
       f.short_name as family, f.member_count,
       length(d.opinion_text) as opinion_len, length(d.dissent_text) as dissent_len,
       length(d.concur_text) as concur_len
from decisions d
left join litigation_families f on f.id = d.family_id
where d.short_name ilike '%craig%simon%' or d.short_name ilike '%crawford%marion%'
   or d.short_name ilike '%eakin%' or d.short_name ilike '%mckitrick%'
order by d.short_name, d.decision_date;
```

After F2 and F4, add `d.decision_date_source` and `f.family_method` to the select list.

**A4. Decision year vs. citation year**

```sql
select short_name, decision_date, lexis_citation
from decisions
where lexis_citation ~ '^\d{4}'
  and extract(year from decision_date)::int <> substring(lexis_citation from '^\d{4}')::int
order by decision_date;
```

**A5. Families built by name only, widest date span first**

```sql
select f.short_name, f.member_count,
       min(d.decision_date) as first_decision, max(d.decision_date) as last_decision,
       count(distinct d.court) as courts,
       count(r.id) as in_corpus_links
from litigation_families f
join decisions d on d.family_id = f.id
left join decision_relations r on r.from_decision_id = d.id and r.target_in_corpus
where f.member_count > 1
group by f.id, f.short_name, f.member_count
having count(r.id) = 0
order by max(d.decision_date) - min(d.decision_date) desc;
```

**A6. Star pages and concurrences**

```sql
select
  count(*) as decisions,
  count(*) filter (where opinion_text ~ '\[\*\d+\]') as exact_star_pages,
  count(*) filter (where opinion_text ~ '\[\*\*\d+\]') as exact_lexis_pages,
  count(*) filter (where opinion_text like '%[*%') as has_bracket_star,
  count(*) filter (where opinion_text ~* '(^|\n)\s*concur(rence)?\s*($|\n)') as concur_heading_in_opinion,
  count(*) filter (where length(concur_text) > 0) as docs_with_concur
from decisions;
```

**A7. File log** (after F6)

```sql
select parse_status, is_duplicate, count(*)
from source_files
group by 1, 2
order by 1, 2;
```

**A8. Incomplete or broken records**

```sql
select short_name, court, court_level, decision_date, char_count, lexis_citation
from decisions
where decision_date is null or court is null or court_level is null
   or short_name ~* '^(january|february|march|april|may|june|july|august|september|october|november|december) \d'
order by decision_date nulls first;
```

**A9. Names with accented or special characters**

```sql
select short_name, source_filename
from decisions
where short_name ~ '[^\x01-\x7F]' or short_name ~ '[A-Za-z]''[a-z]'
order by 1;
```

**A10. Chunk offsets** (after re-chunking)

```sql
select c.section, count(*) as chunks,
       count(*) filter (where substring(
         case when c.section ilike '%dissent%' then d.dissent_text
              when c.section ilike '%concur%' then d.concur_text
              else d.opinion_text end
         from c.char_start + 1 for c.char_end - c.char_start) = c.text) as offsets_match
from opinion_chunks c
join decisions d on d.id = c.decision_id
group by c.section
order by 1;
```

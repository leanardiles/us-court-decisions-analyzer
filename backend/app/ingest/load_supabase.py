"""
Load parsed decisions into the shared Supabase Postgres database.

Requires SUPABASE_DB_URL with the real database password (not the placeholder).

    python -m app.ingest.load_supabase --ping
    python -m app.ingest.load_supabase --apply-schema
    python -m app.ingest.load_supabase --pilot 50
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
load_dotenv(BACKEND_DIR / ".env", override=True)

from app.core.config import settings
from app.ingest.schema import SCHEMA_SQL
from app.ingest.chunker import chunk_decision, verify_offsets
from app.ingest.embed import embed_passages, embed_query, vector_literal
from app.ingest.inventory import inventory_corpus, _decision_payload

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORD_DIR = REPO_ROOT / "current_docs" / "MS Word files (544 files total)"

PROJECT_REF = "mvpecqzqzuuxpwuazyaq"
DB_HOST = f"db.{PROJECT_REF}.supabase.co"
POOLER_HOSTS = (
    "aws-0-us-east-2.pooler.supabase.com",
    "aws-0-us-east-1.pooler.supabase.com",
    "aws-1-us-east-1.pooler.supabase.com",
    "aws-0-us-west-2.pooler.supabase.com",
)


def _password() -> str:
    password = (settings.SUPABASE_DB_PASSWORD or "").strip().strip("'\"")
    if not password:
        raise SystemExit(
            "SUPABASE_DB_PASSWORD is missing in backend/.env"
        )
    return password


def _connect():
    import psycopg2
    from psycopg2.extras import Json

    password = _password()
    attempts = [
        *[
            {
                "host": host,
                "port": 6543,
                "user": f"postgres.{PROJECT_REF}",
            }
            for host in POOLER_HOSTS
        ],
        {"host": DB_HOST, "port": 5432, "user": "postgres"},
    ]
    last_error = None
    for attempt in attempts:
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                password=password,
                sslmode="require",
                connect_timeout=12,
                **attempt,
            )
            conn.autocommit = False
            return conn, Json
        except Exception as exc:
            last_error = exc
    raise SystemExit(f"Could not connect to Supabase Postgres: {last_error}")


def apply_schema() -> None:
    conn, _ = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
        print("Applied ingest schema (families, decisions, relations, chunks).")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _date_only(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "")).date().isoformat()
    except ValueError:
        return value[:10] if len(value) >= 10 else None


def _upsert_corpus(families, decisions, relations) -> None:
    conn, Json = _connect()
    try:
        family_ids: Dict[str, str] = {}
        with conn.cursor() as cur:
            for idx, fam in enumerate(families, start=1):
                cur.execute(
                    """
                    insert into litigation_families (family_key, short_name, member_count)
                    values (%s, %s, %s)
                    on conflict (family_key) do update
                      set short_name = excluded.short_name,
                          member_count = excluded.member_count
                    returning id
                    """,
                    (fam["family_key"], fam["short_name"], fam["member_count"]),
                )
                family_ids[fam["family_key"]] = str(cur.fetchone()[0])
                if idx % 50 == 0:
                    conn.commit()

            for idx, row in enumerate(decisions, start=1):
                cur.execute(
                    """
                    insert into decisions (
                      lexis_citation, reporter_citation, reporter_line_raw, reporter_citations,
                      short_name, source_filename,
                      family_id, court, court_level, decision_date, date_line_raw,
                      decision_date_source, docket_number, state,
                      judges_names, prior_history, subsequent_history, related_proceeding,
                      opinion_text, dissent_text, concur_text, file_sha256, text_sha256,
                      char_count
                    ) values (
                      %s, %s, %s, %s,
                      %s, %s,
                      %s, %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s, %s, %s, %s,
                      %s
                    )
                    on conflict (source_filename) do update set
                      lexis_citation = excluded.lexis_citation,
                      reporter_citation = excluded.reporter_citation,
                      reporter_line_raw = excluded.reporter_line_raw,
                      reporter_citations = excluded.reporter_citations,
                      short_name = excluded.short_name,
                      family_id = excluded.family_id,
                      court = excluded.court,
                      court_level = excluded.court_level,
                      decision_date = excluded.decision_date,
                      date_line_raw = excluded.date_line_raw,
                      decision_date_source = excluded.decision_date_source,
                      docket_number = excluded.docket_number,
                      state = excluded.state,
                      judges_names = excluded.judges_names,
                      prior_history = excluded.prior_history,
                      subsequent_history = excluded.subsequent_history,
                      related_proceeding = excluded.related_proceeding,
                      opinion_text = excluded.opinion_text,
                      dissent_text = excluded.dissent_text,
                      concur_text = excluded.concur_text,
                      file_sha256 = excluded.file_sha256,
                      text_sha256 = excluded.text_sha256,
                      char_count = excluded.char_count
                    """,
                    (
                        row.get("lexis_citation"),
                        row.get("reporter_citation"),
                        row.get("reporter_line_raw"),
                        row.get("reporter_citations") or None,
                        row["short_name"],
                        row["source_filename"],
                        family_ids.get(row["family_key"]),
                        row.get("court"),
                        row.get("court_level"),
                        _date_only(row.get("case_date")),
                        row.get("date_line_raw"),
                        row.get("decision_date_source"),
                        row.get("docket_number"),
                        row.get("state"),
                        Json(row.get("judges_names")) if row.get("judges_names") is not None else None,
                        row.get("prior_history"),
                        row.get("subsequent_history"),
                        row.get("related_proceeding"),
                        row.get("opinion_text"),
                        row.get("dissent_text"),
                        row.get("concur_text"),
                        row.get("file_sha256"),
                        row.get("text_sha256"),
                        row.get("char_count"),
                    ),
                )
                if idx % 25 == 0:
                    conn.commit()
                    print(f"  upserted {idx}/{len(decisions)} decisions")

            for rel in relations:
                if not rel.get("from_lexis_citation"):
                    continue
                cur.execute(
                    """
                    insert into decision_relations (
                      from_decision_id, to_decision_id,
                      from_lexis_citation, to_lexis_citation,
                      relation_type, target_in_corpus
                    )
                    select
                      src.id,
                      dst.id,
                      %s, %s, %s, %s
                    from decisions src
                    left join decisions dst
                      on dst.lexis_citation = %s
                    where src.lexis_citation = %s
                    on conflict (from_lexis_citation, to_lexis_citation, relation_type) do update
                      set target_in_corpus = excluded.target_in_corpus,
                          to_decision_id = excluded.to_decision_id
                    """,
                    (
                        rel["from_lexis_citation"],
                        rel["to_lexis_citation"],
                        rel["relation_type"],
                        rel.get("target_in_corpus", False),
                        rel["to_lexis_citation"],
                        rel["from_lexis_citation"],
                    ),
                )

        conn.commit()
        print(f"Loaded {len(families)} families, {len(decisions)} decisions, {len(relations)} relations.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _delete_unloaded_decisions(keep_filenames: List[str]) -> None:
    """Drop leftover rows (true re-exports) so lexis_citation stays unique."""
    if not keep_filenames:
        return
    conn, _ = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "delete from decisions where not (source_filename = any(%s))",
                (keep_filenames,),
            )
            deleted = cur.rowcount
        conn.commit()
        print(f"Removed {deleted} leftover decision row(s) not in this load set.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_pilot(n: int = 50) -> None:
    manifest_path = DATA_DIR / f"pilot_{n}_manifest.json"
    payload_path = DATA_DIR / f"pilot_{n}_decisions.json"
    families_path = DATA_DIR / "litigation_families.json"
    relations_path = DATA_DIR / "decision_relations.json"

    for path in (payload_path, families_path):
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run: python -m app.ingest.cli --pilot {n}")

    decisions: List[Dict[str, Any]] = json.loads(payload_path.read_text())
    all_families: List[Dict[str, Any]] = json.loads(families_path.read_text())
    relations: List[Dict[str, Any]] = json.loads(relations_path.read_text()) if relations_path.exists() else []
    family_keys = {row["family_key"] for row in decisions}
    families = [fam for fam in all_families if fam["family_key"] in family_keys]
    decision_cites = {row.get("lexis_citation") for row in decisions if row.get("lexis_citation")}
    pilot_relations = [
        rel for rel in relations
        if rel.get("from_lexis_citation") in decision_cites
        or rel.get("to_lexis_citation") in decision_cites
    ]
    _upsert_corpus(families, decisions, pilot_relations)
    if manifest_path.exists():
        print(f"Pilot manifest: {manifest_path}")


def load_all(source_dir: Optional[Path] = None) -> None:
    source = Path(source_dir or DEFAULT_WORD_DIR)
    print(f"Parsing corpus from {source}")
    result = inventory_corpus(source)
    decisions = [
        _decision_payload(rec)
        for rec in result["records"]
        if rec.get("load_as_decision")
    ]
    print(
        f"Loading {len(decisions)} decisions "
        f"({result['summary']['files_seen']} files, "
        f"{result['summary']['true_duplicate_citation_groups']} re-export groups skipped)"
    )
    _upsert_corpus(result["families"], decisions, result["relations"])
    keep = [row["source_filename"] for row in decisions]
    _delete_unloaded_decisions(keep)


def embed_all(limit: Optional[int] = None) -> None:
    conn, _ = _connect()
    mismatch = 0
    inserted = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, short_name, source_filename,
                       opinion_text, dissent_text, concur_text
                from decisions
                order by short_name, source_filename
                """
            )
            rows = cur.fetchall()
            if limit:
                rows = rows[:limit]

            pending_rows: List[tuple] = []
            pending_texts: List[str] = []
            total_chunks = 0
            print(f"Chunking + embedding {len(rows)} decisions with BAAI/bge-small-en-v1.5")
            cur.execute("drop index if exists opinion_chunks_embedding_hnsw")
            cur.execute("alter table opinion_chunks drop column if exists embedding")
            cur.execute("alter table opinion_chunks add column embedding extensions.vector(384)")
            conn.commit()

            def flush() -> None:
                nonlocal inserted, pending_rows, pending_texts
                if not pending_texts:
                    return
                from psycopg2.extras import execute_values

                vectors = embed_passages(pending_texts)
                values = []
                for (decision_id, chunk), vector in zip(pending_rows, vectors):
                    values.append(
                        (
                            decision_id,
                            chunk["section"],
                            chunk["chunk_index"],
                            chunk["text"],
                            chunk["char_start"],
                            chunk["char_end"],
                            chunk["token_count"],
                            vector_literal(vector),
                        )
                    )
                execute_values(
                    cur,
                    """
                    insert into opinion_chunks (
                      decision_id, section, chunk_index, text,
                      char_start, char_end, token_count, embedding
                    ) values %s
                    """,
                    values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s::vector)",
                    page_size=64,
                )
                inserted += len(values)
                conn.commit()
                pending_rows = []
                pending_texts = []

            ids = [row[0] for row in rows]
            if limit:
                for decision_id in ids:
                    cur.execute("delete from opinion_chunks where decision_id = %s", (decision_id,))
            else:
                cur.execute("delete from opinion_chunks")
            conn.commit()

            for idx, row in enumerate(rows, start=1):
                decision_id, short_name, source_filename, opinion, dissent, concur = row
                payload = {
                    "opinion_text": opinion,
                    "dissent_text": dissent,
                    "concur_text": concur,
                }
                chunks = chunk_decision(payload)
                errors = verify_offsets(payload, chunks)
                if errors:
                    mismatch += 1
                for chunk in chunks:
                    pending_rows.append((decision_id, chunk))
                    pending_texts.append(chunk["text"])
                    total_chunks += 1
                if len(pending_texts) >= 128:
                    flush()
                    print(f"  embedded through {idx}/{len(rows)} decisions ({inserted} chunks)")

            flush()
            cur.execute(
                """
                create index if not exists opinion_chunks_embedding_hnsw
                on opinion_chunks using hnsw (embedding vector_cosine_ops)
                """
            )
        conn.commit()
        print(f"Stored {inserted} chunks from {len(rows)} decisions. Offset mismatches: {mismatch}.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def retrieve(
    query: str,
    k: int = 5,
    lexis_citation: Optional[str] = None,
    print_results: bool = True,
) -> List[Dict[str, Any]]:
    """Return top-k chunks for an agent. Also prints when used from the CLI."""
    vector = vector_literal(embed_query(query))
    conn, _ = _connect()
    try:
        with conn.cursor() as cur:
            sql = """
                select
                  d.id,
                  d.short_name,
                  d.lexis_citation,
                  d.source_filename,
                  c.section,
                  c.chunk_index,
                  c.char_start,
                  c.char_end,
                  1 - (c.embedding <=> %s::vector) as score,
                  c.text
                from opinion_chunks c
                join decisions d on d.id = c.decision_id
            """
            params: List[Any] = [vector]
            if lexis_citation:
                sql += " where d.lexis_citation = %s"
                params.append(lexis_citation)
            sql += " order by c.embedding <=> %s::vector limit %s"
            params.extend([vector, k])
            cur.execute(sql, params)
            rows = cur.fetchall()
        hits = [
            {
                "decision_id": str(row[0]),
                "short_name": row[1],
                "lexis_citation": row[2],
                "source_filename": row[3],
                "section": row[4],
                "chunk_index": row[5],
                "char_start": row[6],
                "char_end": row[7],
                "score": float(row[8]),
                "text": row[9],
            }
            for row in rows
        ]
        if print_results:
            if not hits:
                print("No chunks found. Run --embed first.")
            else:
                print(f"Query: {query}\n")
                for i, hit in enumerate(hits, start=1):
                    cite = hit["lexis_citation"] or "NO CITE"
                    preview = hit["text"].replace("\n", " ")[:300]
                    print(f"{i}. {hit['short_name']} | {cite} | {hit['source_filename']}")
                    print(
                        f"   {hit['section']} chunk {hit['chunk_index']} "
                        f"chars {hit['char_start']}:{hit['char_end']}  "
                        f"score={hit['score']:.3f}"
                    )
                    print(f"   {preview}\n")
        return hits
    finally:
        conn.close()


def ping() -> None:
    import urllib.request

    url = (settings.SUPABASE_URL or "").rstrip("/")
    key = settings.SUPABASE_ANON_KEY or settings.SUPABASE_KEY or ""
    if not url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_ANON_KEY must be set in backend/.env")
    req = urllib.request.Request(
        f"{url}/rest/v1/",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            print(f"Supabase REST reachable: {url} (HTTP {response.status})")
    except Exception as exc:
        body = ""
        if hasattr(exc, "read"):
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
        if "Secret API key required" in body:
            print(f"Supabase project is reachable: {url}")
            print("Publishable key is present, but table/schema work needs the secret key or database password.")
        else:
            print(f"Supabase REST check failed: {exc}", file=sys.stderr)
            if body:
                print(body[:300], file=sys.stderr)
            raise SystemExit(1)

        print(f"Project ref: mvpecqzqzuuxpwuazyaq")
    if not (settings.SUPABASE_DB_PASSWORD or "").strip():
        print("Database password is still missing. Schema/load cannot run yet.")
    else:
        print("Database password is set in backend/.env")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load the court-opinion corpus into Supabase and embed chunks.")
    parser.add_argument("--ping", action="store_true", help="Check that the project URL and publishable key work")
    parser.add_argument("--apply-schema", action="store_true", help="Create tables in Supabase Postgres")
    parser.add_argument("--pilot", type=int, default=0, help="Load the frozen N-decision pilot payload")
    parser.add_argument("--all", action="store_true", help="Parse and load every unique decision from the Word folder")
    parser.add_argument("--embed", action="store_true", help="Chunk opinions and write pgvector embeddings")
    parser.add_argument("--embed-limit", type=int, default=0, help="Embed only the first N decisions (for a smoke test)")
    parser.add_argument("--query", type=str, default="", help="Search chunks after embeddings exist")
    parser.add_argument("--lexis", type=str, default="", help="Optional LEXIS citation to restrict --query")
    parser.add_argument("--k", type=int, default=5, help="How many chunks to return for --query")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    ran = False
    if args.ping:
        ping()
        ran = True
    if args.apply_schema:
        apply_schema()
        ran = True
    if args.pilot:
        load_pilot(args.pilot)
        ran = True
    if args.all:
        load_all()
        ran = True
    if args.embed:
        embed_all(limit=args.embed_limit or None)
        ran = True
    if args.query:
        retrieve(args.query, k=args.k, lexis_citation=args.lexis or None)
        ran = True
    if not ran:
        ping()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

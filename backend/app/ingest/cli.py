"""
Stage 0/1 CLI.

Run from the backend/ directory:

    python -m app.ingest.cli --pilot 50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.ingest.inventory import inventory_corpus, select_pilot, write_inventory_outputs

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORD_DIR = REPO_ROOT / "current_docs" / "MS Word files (544 files total)"
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "data"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory LEXIS Word decisions. Identity is LEXIS citation; same-name (2) files stay separate."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_WORD_DIR,
        help="Directory of .docx files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Where to write inventory, families, relations, and the pilot payload",
    )
    parser.add_argument(
        "--pilot",
        type=int,
        default=50,
        help="Number of unique decisions (by LEXIS citation) to freeze (0 to skip)",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=2000,
        help="Minimum extracted character count for a pilot decision",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=50000,
        help="Maximum extracted character count so decisions fit in LLM context",
    )
    parser.add_argument(
        "--max-per-family",
        type=int,
        default=3,
        help="Cap decisions from one litigation family in the pilot",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_dir = args.dir.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()

    if not source_dir.is_dir():
        print(f"Word directory not found: {source_dir}", file=sys.stderr)
        return 1

    print(f"Scanning {source_dir}")
    result = inventory_corpus(source_dir)
    summary = result["summary"]
    print(
        f"Files seen: {summary['files_seen']}  "
        f"parsed: {summary['parsed_ok']}  "
        f"failures: {summary['parse_failures']}"
    )
    print(
        f"Unique LEXIS citations: {summary['unique_lexis_citations']}  "
        f"missing citation: {summary['missing_lexis_citation']}  "
        f"true re-exports: {summary['true_duplicate_citation_groups']}"
    )
    print(
        f"Litigation families: {summary['litigation_families']}  "
        f"multi-decision families: {summary['families_with_multiple_decisions']}  "
        f"history links found in corpus: {summary['history_links_in_corpus']}"
    )
    if summary["errors"]:
        print("Parse failures:")
        for error in summary["errors"][:10]:
            print(f"  - {error['filename']}: {error['error']}")

    pilot = None
    if args.pilot > 0:
        pilot = select_pilot(
            result["records"],
            n=args.pilot,
            min_chars=args.min_chars,
            max_chars=args.max_chars,
            max_per_family=args.max_per_family,
        )
        print(f"Pilot selected: {len(pilot)} / {args.pilot} decisions")
        if len(pilot) < args.pilot:
            print("Warning: fewer qualifying decisions than requested", file=sys.stderr)

    written = write_inventory_outputs(result, out_dir, pilot=pilot)
    for label, path in written.items():
        print(f"Wrote {label}: {path}")

    if pilot:
        print("\nFrozen pilot (review Q1/Q2; identity = LEXIS citation):")
        for idx, rec in enumerate(pilot, start=1):
            print(
                f"  {idx:2d}. {rec['short_name']}  |  "
                f"{rec.get('lexis_citation') or 'NO CITE'}  |  "
                f"{rec.get('court_level') or 'unknown'}  |  "
                f"{rec['source_filename']}"
            )
        print(
            "\nNext: create the shared Supabase project, run "
            "backend/app/ingest/supabase_schema.sql, then load the pilot payload."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Walk the Word corpus and freeze a pilot set of *decisions*.

Identity is LEXIS citation. Same short name + (2) is a related decision,
not a duplicate. True duplicates are the same LEXIS citation exported twice.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ingest.extract import infer_relation_type, parse_docx


def inventory_corpus(source_dir: Path) -> Dict[str, Any]:
    files = sorted(source_dir.glob("*.docx"))
    records: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for path in files:
        try:
            records.append(parse_docx(path))
        except Exception as exc:
            errors.append({"filename": path.name, "error": str(exc)})

    families = _build_families(records)
    relations = _build_relations(records)
    citation_groups: Dict[str, List[str]] = defaultdict(list)
    for record in records:
        if record.get("lexis_citation"):
            citation_groups[record["lexis_citation"]].append(record["source_filename"])
            record["is_true_duplicate"] = len(citation_groups[record["lexis_citation"]]) > 1
        else:
            record["is_true_duplicate"] = False
        record["family_size"] = families[record["family_key"]]["member_count"]

    # Mark the first file per LEXIS citation as the one to load; keep others as re-exports.
    seen_citations = set()
    for record in records:
        cite = record.get("lexis_citation")
        if cite and cite in seen_citations:
            record["duplicate_export_of"] = cite
            record["load_as_decision"] = False
        elif not cite:
            record["duplicate_export_of"] = None
            record["load_as_decision"] = False
            record["parse_error"] = record.get("parse_error") or "no_lexis_citation"
        else:
            record["duplicate_export_of"] = None
            record["load_as_decision"] = True
            seen_citations.add(cite)

    missing_citation = sum(1 for rec in records if not rec.get("lexis_citation"))
    family_list = sorted(families.values(), key=lambda item: -item["member_count"])

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "identity_unit": "lexis_citation",
        "files_seen": len(files),
        "parsed_ok": len(records),
        "parse_failures": len(errors),
        "decisions_to_load": sum(1 for rec in records if rec["load_as_decision"]),
        "unique_lexis_citations": len(citation_groups),
        "missing_lexis_citation": missing_citation,
        "true_duplicate_citation_groups": sum(1 for names in citation_groups.values() if len(names) > 1),
        "litigation_families": len(families),
        "families_with_multiple_decisions": sum(1 for fam in families.values() if fam["member_count"] > 1),
        "history_links_in_corpus": sum(1 for rel in relations if rel["target_in_corpus"]),
        "errors": errors,
        "families": family_list,
        "relations": relations,
        "duplicate_citation_groups": [
            {"lexis_citation": cite, "files": names}
            for cite, names in sorted(citation_groups.items(), key=lambda item: -len(item[1]))
            if len(names) > 1
        ],
        "files": [_public_record(record) for record in records],
    }
    return {"summary": summary, "records": records, "families": family_list, "relations": relations}


def select_pilot(
    records: List[Dict[str, Any]],
    n: int = 50,
    min_chars: int = 2000,
    max_chars: int = 50000,
    max_per_family: int = 3,
) -> List[Dict[str, Any]]:
    """
    Pick N decisions for the frozen evaluation set.

    Same-name files are allowed (they are different decisions). We only
    unique on LEXIS citation, and we cap members per family so one lawsuit
    cannot fill the whole pilot.
    """
    candidates = [
        record for record in records
        if record.get("load_as_decision")
        and min_chars <= (record.get("char_count") or 0) <= max_chars
        and record.get("short_name")
        and record.get("opinion_text")
    ]
    candidates.sort(
        key=lambda rec: (
            rec.get("election_score") or 0,
            rec.get("family_size") or 0,
            rec.get("char_count") or 0,
        ),
        reverse=True,
    )

    selected: List[Dict[str, Any]] = []
    seen_ids = set()
    family_counts: Dict[str, int] = defaultdict(int)

    def add(record: Dict[str, Any]) -> bool:
        decision_id = record["decision_id"]
        if decision_id in seen_ids:
            return False
        selected.append(record)
        seen_ids.add(decision_id)
        family_counts[record["family_key"]] += 1
        return True

    for record in candidates:
        if family_counts[record["family_key"]] >= max_per_family:
            continue
        add(record)
        if len(selected) >= n:
            return selected

    for record in candidates:
        add(record)
        if len(selected) >= n:
            break

    return selected


def write_inventory_outputs(
    result: Dict[str, Any],
    out_dir: Path,
    pilot: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}

    inventory_path = out_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(result["summary"], indent=2, default=str),
        encoding="utf-8",
    )
    written["inventory"] = inventory_path

    csv_path = out_dir / "inventory.csv"
    _write_inventory_csv(result["records"], csv_path)
    written["inventory_csv"] = csv_path

    families_path = out_dir / "litigation_families.json"
    families_path.write_text(
        json.dumps(result["families"], indent=2, default=str),
        encoding="utf-8",
    )
    written["families"] = families_path

    relations_path = out_dir / "decision_relations.json"
    relations_path.write_text(
        json.dumps(result["relations"], indent=2, default=str),
        encoding="utf-8",
    )
    written["relations"] = relations_path

    if pilot:
        n = len(pilot)
        manifest_path = out_dir / f"pilot_{n}_manifest.json"
        family_keys = {rec["family_key"] for rec in pilot}
        multi = sum(
            1 for key in family_keys
            if sum(1 for rec in pilot if rec["family_key"] == key) > 1
        )
        manifest = {
            "frozen": True,
            "count": n,
            "identity_unit": "lexis_citation",
            "families_in_pilot": len(family_keys),
            "families_with_multiple_pilot_decisions": multi,
            "note": (
                "Frozen Capstone II pilot. Each row is a decision identified by "
                "LEXIS citation. Same short name with (2) is a related decision "
                "in the same litigation family, not a duplicate. Do not silently replace."
            ),
            "decisions": [
                {
                    "decision_id": rec["decision_id"],
                    "lexis_citation": rec.get("lexis_citation"),
                    "reporter_citation": rec.get("reporter_citation"),
                    "short_name": rec["short_name"],
                    "source_filename": rec["source_filename"],
                    "family_key": rec["family_key"],
                    "court": rec.get("court"),
                    "court_level": rec.get("court_level"),
                    "case_date": rec.get("case_date"),
                    "docket_number": rec.get("docket_number"),
                    "state": rec.get("state"),
                    "char_count": rec.get("char_count"),
                    "election_score": rec.get("election_score"),
                }
                for rec in pilot
            ],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        written["manifest"] = manifest_path

        payload_path = out_dir / f"pilot_{n}_decisions.json"
        payload_path.write_text(
            json.dumps([_decision_payload(rec) for rec in pilot], indent=2, default=str),
            encoding="utf-8",
        )
        written["pilot_payload"] = payload_path

    return written


def _build_families(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["family_key"]].append(record)

    families = {}
    for key, members in grouped.items():
        families[key] = {
            "family_key": key,
            "short_name": members[0]["short_name"],
            "member_count": len(members),
            "members": [
                {
                    "source_filename": rec["source_filename"],
                    "lexis_citation": rec.get("lexis_citation"),
                    "court": rec.get("court"),
                    "court_level": rec.get("court_level"),
                    "case_date": rec.get("case_date"),
                }
                for rec in members
            ],
        }
    return families


def _build_relations(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    known = {rec["lexis_citation"] for rec in records if rec.get("lexis_citation")}
    relations = []
    for record in records:
        source = record.get("lexis_citation")
        if not source:
            continue
        blocks = [
            record.get("prior_history"),
            record.get("subsequent_history"),
            record.get("related_proceeding"),
        ]
        for block in blocks:
            if not block:
                continue
            rel_type = infer_relation_type(block)
            for target in record.get("related_lexis_cites") or []:
                if target == source:
                    continue
                # Only attach cites that actually appear in this block.
                if target.lower() not in block.lower():
                    continue
                relations.append({
                    "from_lexis_citation": source,
                    "to_lexis_citation": target,
                    "relation_type": rel_type,
                    "target_in_corpus": target in known,
                    "source_filename": record["source_filename"],
                })
    return relations


def _decision_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "decision_id", "lexis_citation", "reporter_citation", "reporter_line_raw",
        "reporter_citations", "short_name",
        "source_filename", "family_key", "court", "court_level", "case_date",
        "date_line_raw", "decision_date_source",
        "docket_number", "judges_names", "state", "prior_history",
        "subsequent_history", "related_proceeding", "related_lexis_cites",
        "opinion_text", "dissent_text", "concur_text", "file_sha256",
        "text_sha256", "char_count",
    ]
    return {key: record.get(key) for key in keys}


def _public_record(record: Dict[str, Any]) -> Dict[str, Any]:
    skip = {"opinion_text", "dissent_text", "concur_text", "source_path"}
    return {key: value for key, value in record.items() if key not in skip}


def _write_inventory_csv(records: List[Dict[str, Any]], path: Path) -> None:
    columns = [
        "source_filename",
        "short_name",
        "lexis_citation",
        "reporter_citation",
        "family_key",
        "family_size",
        "court",
        "court_level",
        "case_date",
        "docket_number",
        "state",
        "load_as_decision",
        "duplicate_export_of",
        "char_count",
        "election_score",
        "has_dissent",
        "has_concur",
        "parse_error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            writer.writerow({column: record.get(column) for column in columns})

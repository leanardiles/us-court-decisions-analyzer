"""
Regression tests for Leandro's 6 Oct 2026 QA (F2 dates, F3 LEXIS cites).

Reads licensed Word files from WORD_CORPUS_DIR. Nothing from that folder
is committed. Expected values only live in this file.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from app.ingest.extract import parse_docx

WORD_DIR = Path(
    os.environ.get(
        "WORD_CORPUS_DIR",
        Path(__file__).resolve().parents[2]
        / "current_docs"
        / "MS Word files (544 files total)",
    )
)


def _word(*names: str) -> Path:
    for name in names:
        path = WORD_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError(f"None of {names} in {WORD_DIR}")


class ExtractQaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not WORD_DIR.exists():
            raise unittest.SkipTest(f"Word corpus not at {WORD_DIR}")

    def test_craig_eighth_circuit_uses_filed_date(self) -> None:
        record = parse_docx(_word("Craig v. Simon.docx"))
        self.assertEqual(record["lexis_citation"], "2020 U.S. App. LEXIS 33403")
        self.assertTrue(record["case_date"].startswith("2020-10-23"))
        self.assertEqual(record["decision_date_source"], "filed")
        self.assertIn("Submitted", record["date_line_raw"] or "")
        self.assertIn("Filed", record["date_line_raw"] or "")

    def test_craig_district_stays_a_separate_decision(self) -> None:
        appellate = parse_docx(_word("Craig v. Simon.docx"))
        district = parse_docx(_word("Craig v. Simon(2).docx", "Craig v. Simon (2).docx"))
        self.assertEqual(district["lexis_citation"], "2020 U.S. Dist. LEXIS 187996")
        self.assertNotEqual(appellate["lexis_citation"], district["lexis_citation"])
        self.assertEqual(appellate["family_key"], district["family_key"])

    def test_crawford_seventh_circuit_uses_2007_decided_date(self) -> None:
        record = parse_docx(_word("Crawford v. Marion County Election Bd (1).docx"))
        self.assertEqual(record["lexis_citation"], "2007 U.S. App. LEXIS 110")
        self.assertTrue(record["case_date"].startswith("2007-01-04"))
        self.assertEqual(record["decision_date_source"], "decided")

    def test_state_court_lexis_from_reporter_line(self) -> None:
        record = parse_docx(_word("Alliance for Retired Ams. v. Sec_y of State.docx"))
        self.assertEqual(record["lexis_citation"], "2020 Me. LEXIS 123")
        self.assertTrue(record["case_date"].startswith("2020-10-23"))
        self.assertEqual(record["decision_date_source"], "decided")
        self.assertEqual(record["court_level"], "state_supreme")

    def test_ohio_app_and_kentucky_unpub_lexis(self) -> None:
        ohio = parse_docx(_word("Ohio Democratic Party v. LaRose.docx"))
        ky = parse_docx(_word("Adair County Bd. of Elections v. Arnold.docx"))
        self.assertEqual(ohio["lexis_citation"], "2020 Ohio App. LEXIS 3649")
        self.assertEqual(ohio["court_level"], "state_appellate")
        self.assertEqual(ky["lexis_citation"], "2015 Ky. App. Unpub. LEXIS 656")
        self.assertEqual(ky["court_level"], "state_appellate")
        self.assertEqual(ky["decision_date_source"], "rendered")

    def test_opinion_filed_not_oral_argument(self) -> None:
        record = parse_docx(_word("League of Women Voters of Kan. v. Schwab.docx"))
        self.assertEqual(record["lexis_citation"], "2024 Kan. LEXIS 52")
        self.assertTrue(record["case_date"].startswith("2024-05-31"))
        self.assertEqual(record["decision_date_source"], "filed")

    def test_mckitrick_exports_share_one_citation(self) -> None:
        first = parse_docx(_word("McKitrick v. Larose.docx"))
        second = parse_docx(_word("McKitrick v. Larose(2).docx"))
        self.assertEqual(first["lexis_citation"], "2022 Ohio Misc. LEXIS 4934")
        self.assertEqual(first["lexis_citation"], second["lexis_citation"])
        self.assertEqual(first["text_sha256"], second["text_sha256"])


if __name__ == "__main__":
    unittest.main()

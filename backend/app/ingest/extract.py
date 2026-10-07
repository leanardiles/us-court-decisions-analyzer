"""
Extract text and light caption metadata from LEXIS .docx exports.

Stage 0 is deliberately rule-based: no LLM, no embeddings.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
DATE_RE = re.compile(
    rf"(?P<month>{'|'.join(MONTHS)})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{4}})"
)
DOCKET_RE = re.compile(
    r"\b(?:Nos?\.|Case No\.)\s+([0-9A-Za-z:,.\-()/ ]{1,80})",
    re.IGNORECASE,
)
LEXIS_PAGE_RE = re.compile(r"\[\*{1,2}\d+\]")
COPY_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")
# Federal and state: 2020 U.S. App. LEXIS 33403, 2020 Ohio App. LEXIS 3649, 2015 Ky. App. Unpub. LEXIS 656
LEXIS_CITE_RE = re.compile(
    r"\b(\d{4}\s+[A-Z][A-Za-z.&'\- ]*?\s+LEXIS\s+\d+)\b",
    re.IGNORECASE,
)
REPORTER_CITE_RE = re.compile(
    r"(\d+\s+F\.(?:\s*Supp\.(?:\s+\d+d)?|\s*3d|\s*2d|\s*4th)\s+\d+)",
    re.IGNORECASE,
)
DATE_LABEL_RE = re.compile(
    rf"(?P<month>{'|'.join(MONTHS)})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{4}})"
    rf"(?:[^A-Za-z;]{{0,24}}(?P<label>Decided|Filed|Submitted|Argued|Released|Entered|Rendered))?",
    re.IGNORECASE,
)
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}
SPANISH_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+("
    r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre"
    r")\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)
DATE_PRIORITY = (
    "decided", "filed", "released", "entered", "rendered", "delivered", "issued",
)
SKIP_DATE_LABELS = {"argued", "submitted"}
DATE_LABEL_ALIASES = (
    ("oral argument", "argued"),
    ("argument held", "argued"),
    ("argued", "argued"),
    ("submitted", "submitted"),
    ("decided", "decided"),
    ("officially released", "released"),
    ("released", "released"),
    ("entered", "entered"),
    ("rendered", "rendered"),
    ("delivered", "delivered"),
    ("issued", "issued"),
    ("opinion filed", "filed"),
    ("filed", "filed"),
)
DATE_LINE_SKIP_PREFIXES = (
    "prior history", "subsequent history", "related proceeding",
    "counsel", "notice", "disposition",
)

CAPTION_SKIP = {
    "reporter", "counsel", "notice", "subsequent history", "prior history",
    "disposition", "overview", "core terms", "proceedings",
}

OPINION_START_RE = re.compile(
    r"^(opinion|order|per curiam|memorandum(?:\s+opinion)?)\b",
    re.IGNORECASE,
)
DISSENT_START_RE = re.compile(
    r"^(dissent|dissenting(\s+opinion)?)\b",
    re.IGNORECASE,
)
CONCUR_START_RE = re.compile(
    r"^(concurrence|concurring(\s+opinion)?)\b",
    re.IGNORECASE,
)

STATE_PATTERNS = [
    (re.compile(r"\b(Alabama|Ala\.)\b", re.I), "AL"),
    (re.compile(r"\b(Alaska)\b", re.I), "AK"),
    (re.compile(r"\b(Arizona|Ariz\.)\b", re.I), "AZ"),
    (re.compile(r"\b(Arkansas|Ark\.)\b", re.I), "AR"),
    (re.compile(r"\b(California|Cal\.)\b", re.I), "CA"),
    (re.compile(r"\b(Colorado|Colo\.)\b", re.I), "CO"),
    (re.compile(r"\b(Connecticut|Conn\.)\b", re.I), "CT"),
    (re.compile(r"\b(Delaware|Del\.)\b", re.I), "DE"),
    (re.compile(r"\b(Florida|Fla\.)\b", re.I), "FL"),
    (re.compile(r"\b(Georgia|Ga\.)\b", re.I), "GA"),
    (re.compile(r"\b(Hawaii|Haw\.)\b", re.I), "HI"),
    (re.compile(r"\b(Idaho)\b", re.I), "ID"),
    (re.compile(r"\b(Illinois|Ill\.)\b", re.I), "IL"),
    (re.compile(r"\b(Indiana|Ind\.)\b", re.I), "IN"),
    (re.compile(r"\b(Iowa)\b", re.I), "IA"),
    (re.compile(r"\b(Kansas|Kan\.)\b", re.I), "KS"),
    (re.compile(r"\b(Kentucky|Ky\.)\b", re.I), "KY"),
    (re.compile(r"\b(Louisiana|La\.)\b", re.I), "LA"),
    (re.compile(r"\b(Maine|Me\.)\b", re.I), "ME"),
    (re.compile(r"\b(Maryland|Md\.)\b", re.I), "MD"),
    (re.compile(r"\b(Massachusetts|Mass\.)\b", re.I), "MA"),
    (re.compile(r"\b(Michigan|Mich\.)\b", re.I), "MI"),
    (re.compile(r"\b(Minnesota|Minn\.)\b", re.I), "MN"),
    (re.compile(r"\b(Mississippi|Miss\.)\b", re.I), "MS"),
    (re.compile(r"\b(Missouri|Mo\.)\b", re.I), "MO"),
    (re.compile(r"\b(Montana|Mont\.)\b", re.I), "MT"),
    (re.compile(r"\b(Nebraska|Neb\.)\b", re.I), "NE"),
    (re.compile(r"\b(Nevada|Nev\.)\b", re.I), "NV"),
    (re.compile(r"\b(New Hampshire|N\.H\.)\b", re.I), "NH"),
    (re.compile(r"\b(New Jersey|N\.J\.)\b", re.I), "NJ"),
    (re.compile(r"\b(New Mexico|N\.M\.)\b", re.I), "NM"),
    (re.compile(r"\b(New York|N\.Y\.)\b", re.I), "NY"),
    (re.compile(r"\b(North Carolina|N\.C\.)\b", re.I), "NC"),
    (re.compile(r"\b(North Dakota|N\.D\.)\b", re.I), "ND"),
    (re.compile(r"\b(Ohio)\b", re.I), "OH"),
    (re.compile(r"\b(Oklahoma|Okla\.)\b", re.I), "OK"),
    (re.compile(r"\b(Oregon|Or\.)\b", re.I), "OR"),
    (re.compile(r"\b(Pennsylvania|Pa\.)\b", re.I), "PA"),
    (re.compile(r"\b(Rhode Island|R\.I\.)\b", re.I), "RI"),
    (re.compile(r"\b(South Carolina|S\.C\.)\b", re.I), "SC"),
    (re.compile(r"\b(South Dakota|S\.D\.)\b", re.I), "SD"),
    (re.compile(r"\b(Tennessee|Tenn\.)\b", re.I), "TN"),
    (re.compile(r"\b(Texas|Tex\.)\b", re.I), "TX"),
    (re.compile(r"\b(Utah)\b", re.I), "UT"),
    (re.compile(r"\b(Vermont|Vt\.)\b", re.I), "VT"),
    (re.compile(r"\b(Virginia|Va\.)\b", re.I), "VA"),
    (re.compile(r"\b(Washington|Wash\.)\b", re.I), "WA"),
    (re.compile(r"\b(West Virginia|W\. Va\.)\b", re.I), "WV"),
    (re.compile(r"\b(Wisconsin|Wis\.)\b", re.I), "WI"),
    (re.compile(r"\b(Wyoming|Wyo\.)\b", re.I), "WY"),
]

ELECTION_KEYWORDS = (
    "election", "ballot", "voter", "voting", "poll ", "polling",
    "purcell", "absentee", "redistrict", "primary", "general election",
    "secretary of state", "board of elections", "voting rights",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_case_name(name: str) -> str:
    """Family key only. Filename suffixes like (2) are NOT identity."""
    cleaned = COPY_SUFFIX_RE.sub("", name or "")
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def normalize_lexis_citation(cite: str) -> str:
    cite = re.sub(r"\s+", " ", cite.strip())
    cite = re.sub(r"\bu\.s\.\b", "U.S.", cite, flags=re.I)
    cite = re.sub(r"\bdist\.\b", "Dist.", cite, flags=re.I)
    cite = re.sub(r"\bapp\.\b", "App.", cite, flags=re.I)
    cite = re.sub(r"\blexis\b", "LEXIS", cite, flags=re.I)
    return cite


def clean_lexis_text(text: str) -> str:
    text = LEXIS_PAGE_RE.sub("", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def read_docx_paragraphs(path: Path) -> List[str]:
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: List[str] = []
    for para in root.iter(f"{W_NS}p"):
        pieces = [node.text or "" for node in para.iter(f"{W_NS}t")]
        line = clean_lexis_text("".join(pieces))
        if line:
            paragraphs.append(line)
    return paragraphs


def _looks_like_court(text: str) -> bool:
    lowered = text.lower()
    if "court" not in lowered and "tribunal" not in lowered:
        return False
    if lowered in CAPTION_SKIP or lowered.startswith("prior history"):
        return False
    return True


def _datetime_from_match(match: re.Match) -> Optional[datetime]:
    try:
        return datetime.strptime(
            f"{match.group('month')} {match.group('day')} {match.group('year')}",
            "%B %d %Y",
        )
    except ValueError:
        return None


def _parse_date(text: str) -> Optional[datetime]:
    match = DATE_RE.search(text)
    if not match:
        return None
    return _datetime_from_match(match)


def _label_from_tail(tail: str) -> Optional[str]:
    lowered = tail.lower()
    for needle, label in DATE_LABEL_ALIASES:
        if needle in lowered:
            return label
    return None


def _parse_date_events(text: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    matches = list(DATE_RE.finditer(text))
    for idx, match in enumerate(matches):
        parsed = _datetime_from_match(match)
        if not parsed:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        events.append({"date": parsed, "label": _label_from_tail(text[match.end():end])})
    return events


def _spanish_date(text: str) -> Optional[datetime]:
    match = SPANISH_DATE_RE.search(text)
    if not match:
        return None
    day, month_name, year = match.group(1), match.group(2).lower(), match.group(3)
    month = SPANISH_MONTHS.get(month_name)
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day))
    except ValueError:
        return None


def _looks_like_date_line(text: str) -> bool:
    if not DATE_RE.search(text) and not SPANISH_DATE_RE.search(text):
        return False
    return bool(
        re.search(
            r"\b(decided|filed|argued|submitted|rendered|released|entered)\b",
            text,
            re.I,
        )
        or SPANISH_DATE_RE.search(text)
    )


def choose_decision_date(
    paragraphs: List[str],
) -> tuple[Optional[datetime], str, Optional[str]]:
    """Prefer Decided, then Filed, then Released/Entered/Rendered. Never Argued/Submitted."""
    date_line = None
    events: List[Dict[str, Any]] = []
    for para in paragraphs[:14]:
        lowered = para.lower().strip()
        if any(lowered.startswith(prefix) for prefix in DATE_LINE_SKIP_PREFIXES):
            continue
        found = _parse_date_events(para)
        if found:
            date_line = para
            events = found
            break
    if not events:
        for para in paragraphs[:8]:
            spanish = _spanish_date(para)
            if spanish:
                return spanish, "none", para
        return None, "none", None

    by_label: Dict[str, datetime] = {}
    for event in events:
        if event["label"]:
            by_label.setdefault(event["label"], event["date"])
    for label in DATE_PRIORITY:
        if label in by_label:
            return by_label[label], label, date_line
    unlabeled = [event["date"] for event in events if not event["label"]]
    if unlabeled and not any(event["label"] in SKIP_DATE_LABELS for event in events):
        return unlabeled[0], "none", date_line
    return None, "none", date_line


def _parse_docket(paragraphs: List[str]) -> Optional[str]:
    for para in paragraphs[:20]:
        match = DOCKET_RE.search(para)
        if match:
            return f"No. {match.group(1).strip().rstrip(',')}"
    return None


def _parse_judges(paragraphs: List[str]) -> Optional[List[str]]:
    for para in paragraphs[:40]:
        if para.lower().startswith("judges:") or para.lower().startswith("before:"):
            raw = re.sub(r"^(judges:|before:)\s*", "", para, flags=re.I)
            raw = re.split(r"\.\s+[A-Z][A-Za-z .]+, dissenting", raw)[0]
            parts = re.split(r",| and ", raw)
            names = []
            for part in parts:
                name = part.strip(" .")
                name = re.sub(
                    r"\s+(Circuit Judges?|District Judges?|United States( District Judge)?|Chief Judge|Judge)$",
                    "",
                    name,
                    flags=re.I,
                )
                lowered = name.lower()
                if lowered in {"united states", "before", "honorable"}:
                    continue
                if 2 <= len(name) <= 80:
                    names.append(name)
            return names or None
        if para.lower().startswith("opinion by:"):
            name = para.split(":", 1)[1].strip(" .")
            return [name] if name else None
    return None


def _reporter_line(paragraphs: List[str]) -> Optional[str]:
    for idx, para in enumerate(paragraphs[:16]):
        if para.strip().lower() in {"reporter", "reportero"}:
            if idx + 1 < len(paragraphs):
                return paragraphs[idx + 1]
            return None
    return None


def _citations_from_reporter_line(line: str) -> List[str]:
    parts: List[str] = []
    for raw in line.split(";"):
        cleaned = re.sub(r"\*+", "", raw).strip(" \t")
        cleaned = re.sub(r"\s+", " ", cleaned)
        if cleaned:
            parts.append(cleaned)
    return parts


def _first_lexis_cite(text: str) -> Optional[str]:
    match = LEXIS_CITE_RE.search(text or "")
    if not match:
        return None
    return normalize_lexis_citation(match.group(1))


def _parse_lexis_citation(paragraphs: List[str]) -> Optional[str]:
    """Unit of identity: the LEXIS citation on the Reporter line, any court."""
    reporter = _reporter_line(paragraphs)
    if reporter:
        cite = _first_lexis_cite(reporter)
        if cite:
            return cite
        for part in _citations_from_reporter_line(reporter):
            cite = _first_lexis_cite(part)
            if cite:
                return cite
    for para in paragraphs[:16]:
        cite = _first_lexis_cite(para)
        if cite:
            return cite
    return None


def _parse_reporter_citation(paragraphs: List[str]) -> Optional[str]:
    haystack = _reporter_line(paragraphs) or " ".join(paragraphs[:12])
    match = REPORTER_CITE_RE.search(haystack)
    return match.group(1).strip() if match else None


def _parse_reporter_citations(paragraphs: List[str]) -> List[str]:
    reporter = _reporter_line(paragraphs)
    if not reporter:
        return []
    return _citations_from_reporter_line(reporter)


def _history_paragraph(paragraphs: List[str], prefix: str) -> Optional[str]:
    needle = prefix.lower()
    for para in paragraphs[:30]:
        if para.lower().startswith(needle):
            return para
    return None


def _extract_lexis_cites(text: Optional[str]) -> List[str]:
    if not text:
        return []
    seen = []
    for match in LEXIS_CITE_RE.finditer(text):
        cite = normalize_lexis_citation(match.group(1))
        if cite not in seen:
            seen.append(cite)
    return seen


def _infer_court_level(court: Optional[str]) -> Optional[str]:
    if not court:
        return None
    lowered = court.lower()
    if "supreme court of the united states" in lowered:
        return "us_supreme"
    if "united states court of appeals" in lowered or (
        "united states" in lowered and "circuit" in lowered
    ):
        return "federal_appellate"
    if "united states district court" in lowered:
        return "federal_district"
    if "supreme" in lowered or "tribunal supremo" in lowered:
        return "state_supreme"
    if "court of appeals" in lowered or "appellate" in lowered:
        return "state_appellate"
    return "other"


def infer_relation_type(history_text: str) -> str:
    lowered = history_text.lower()
    if lowered.startswith("prior history"):
        return "prior_history"
    if "related proceeding" in lowered:
        return "related_proceeding"
    if "affirmed" in lowered:
        return "affirmed"
    if "reversed" in lowered or "vacated" in lowered:
        return "reversed_or_vacated"
    if lowered.startswith("subsequent history"):
        return "subsequent_history"
    return "related"


def _infer_state(court: Optional[str], paragraphs: List[str]) -> Optional[str]:
    haystack = " ".join([court or ""] + paragraphs[:12])
    for pattern, code in STATE_PATTERNS:
        if pattern.search(haystack):
            return code
    return None


def _split_sections(paragraphs: List[str]) -> Dict[str, str]:
    """Split caption / opinion / dissent / concurrence by heading lines."""
    body_index = None
    for idx, para in enumerate(paragraphs):
        if OPINION_START_RE.match(para) and len(para) < 80:
            body_index = idx
            break

    if body_index is None:
        # Fall back: skip a typical LEXIS header block.
        body_index = min(8, max(0, len(paragraphs) - 1))

    current = "opinion"
    buckets = {"opinion": [], "dissent": [], "concur": []}
    for para in paragraphs[body_index:]:
        if para.lower() == "end of document":
            break
        if DISSENT_START_RE.match(para) and len(para) < 80:
            current = "dissent"
            continue
        if CONCUR_START_RE.match(para) and len(para) < 80:
            current = "concur"
            continue
        buckets[current].append(para)

    return {
        key: "\n\n".join(value).strip() or None
        for key, value in buckets.items()
    }


def election_score(text: str) -> int:
    lowered = text.lower()
    return sum(lowered.count(keyword) for keyword in ELECTION_KEYWORDS)


def parse_docx(path: Path) -> Dict[str, Any]:
    """
    Parse one LEXIS Word file as one *decision*.

    Identity is the LEXIS citation, not the filename. "Craig v. Simon" and
    "Craig v. Simon(2).docx" are different decisions in the same family.
    """
    paragraphs = read_docx_paragraphs(path)
    if not paragraphs:
        raise ValueError("No text paragraphs found")

    short_name = COPY_SUFFIX_RE.sub("", path.stem).replace("_", "'").strip()
    if (
        paragraphs[0]
        and len(paragraphs[0]) < 200
        and not _looks_like_date_line(paragraphs[0])
    ):
        short_name = COPY_SUFFIX_RE.sub("", paragraphs[0]).strip()

    court = next((para for para in paragraphs[1:8] if _looks_like_court(para)), None)
    case_date, date_source, date_line_raw = choose_decision_date(paragraphs)

    sections = _split_sections(paragraphs)
    opinion_text = sections["opinion"] or "\n\n".join(paragraphs)
    full_text = "\n\n".join(paragraphs)
    lexis_citation = _parse_lexis_citation(paragraphs)
    reporter_line_raw = _reporter_line(paragraphs)
    reporter_citations = _parse_reporter_citations(paragraphs)
    prior_history = _history_paragraph(paragraphs, "prior history")
    subsequent_history = _history_paragraph(paragraphs, "subsequent history")
    related_proceeding = _history_paragraph(paragraphs, "related proceeding")

    related_cites = []
    for block in (prior_history, subsequent_history, related_proceeding):
        related_cites.extend(_extract_lexis_cites(block))
    related_cites = [cite for cite in dict.fromkeys(related_cites) if cite != lexis_citation]

    record = {
        "source_filename": path.name,
        "source_path": str(path),
        "file_sha256": sha256_file(path),
        "text_sha256": sha256_text(full_text),
        "short_name": short_name,
        "case_name": short_name,
        "family_key": normalize_case_name(short_name),
        "lexis_citation": lexis_citation,
        "reporter_citation": _parse_reporter_citation(paragraphs),
        "reporter_line_raw": reporter_line_raw,
        "reporter_citations": reporter_citations,
        "decision_id": lexis_citation or f"file:{path.name}",
        "court": court,
        "court_level": _infer_court_level(court),
        "case_date": case_date.isoformat() if case_date else None,
        "date_line_raw": date_line_raw,
        "decision_date_source": date_source,
        "docket_number": _parse_docket(paragraphs),
        "judges_names": _parse_judges(paragraphs),
        "state": _infer_state(court, paragraphs),
        "prior_history": prior_history,
        "subsequent_history": subsequent_history,
        "related_proceeding": related_proceeding,
        "related_lexis_cites": related_cites,
        "size_bytes": path.stat().st_size,
        "paragraph_count": len(paragraphs),
        "char_count": len(full_text),
        "election_score": election_score(full_text),
        "has_opinion": bool(sections["opinion"]),
        "has_dissent": bool(sections["dissent"]),
        "has_concur": bool(sections["concur"]),
        "election_type": None,
        "party_who_appointed_judge": None,
        "opinion_text": opinion_text,
        "dissent_text": sections["dissent"],
        "concur_text": sections["concur"],
        "parse_error": None,
    }
    return record

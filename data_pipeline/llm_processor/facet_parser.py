"""Rule-based facet extraction from raw job titles.

The same rules are mirrored in the Go backend (`backend/services/facet_service.go`)
so a query like "new grad backend engineer" gets the same `seniority="new_grad"`
treatment as the postings it should match. See search_design.md section 5.3.
"""

from __future__ import annotations

import datetime
import re
from typing import Optional, Tuple


_SENIORITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("intern",   re.compile(r"\bintern(ship)?\b", re.IGNORECASE)),
    ("new_grad", re.compile(r"\b(new[\s\-]?grad(uate)?|graduate)\b", re.IGNORECASE)),
    ("entry",    re.compile(r"\b(junior|jr\.?|entry[\s\-]?level|associate)\b", re.IGNORECASE)),
    ("senior",   re.compile(r"\b(senior|sr\.?|lead|staff|principal)\b", re.IGNORECASE)),
]

_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def parse_seniority(title: str) -> str:
    if not title:
        return "unknown"
    for tag, pattern in _SENIORITY_PATTERNS:
        if pattern.search(title):
            return tag
    return "unknown"


def parse_year(title: str, posted_date: Optional[datetime.date] = None) -> Optional[int]:
    if title:
        m = _YEAR_RE.search(title)
        if m:
            return int(m.group(1))
    if posted_date is not None:
        return posted_date.year
    return None


def parse(title: str, posted_date: Optional[datetime.date] = None) -> Tuple[str, Optional[int]]:
    return parse_seniority(title), parse_year(title, posted_date)


if __name__ == "__main__":
    for sample in [
        "New Grad Backend Engineer",
        "Senior Software Engineer 2026",
        "Data Scientist Intern",
        "Staff ML Engineer",
        "Backend Engineer",
    ]:
        print(sample, "->", parse(sample))

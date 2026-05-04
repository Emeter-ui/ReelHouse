"""Match a TMDB title (+ optional year) against moviebox-api search candidates.

Strategy:
- prefer candidates whose year is within ±1 of the target,
- score by token-set ratio on titles,
- accept the best ≥ 85 with a year-aligned candidate,
- otherwise accept the best ≥ 70 across all candidates,
- otherwise no match.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass(slots=True)
class Candidate:
    subject_id: str
    title: str
    year: int | None
    detail_path: str | None = None


def best_match(
    target_title: str,
    target_year: int | None,
    candidates: list[Candidate],
    *,
    aligned_threshold: int = 85,
    fallback_threshold: int = 70,
) -> Candidate | None:
    if not candidates or not target_title:
        return None

    scored: list[tuple[int, Candidate, bool]] = []
    for c in candidates:
        score = int(fuzz.token_set_ratio(target_title, c.title))
        year_ok = (
            target_year is not None
            and c.year is not None
            and abs(c.year - target_year) <= 1
        )
        scored.append((score, c, year_ok))

    scored.sort(key=lambda t: (t[2], t[0]), reverse=True)

    aligned = [s for s in scored if s[2]]
    if aligned and aligned[0][0] >= aligned_threshold:
        return aligned[0][1]

    if scored and scored[0][0] >= fallback_threshold:
        return scored[0][1]

    return None

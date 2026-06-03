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
from rapidfuzz.utils import default_process


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

    # default_process lowercases and replaces non-alphanumerics with spaces.
    # Without it, hyphenated TMDB titles like "Spider-Noir" stay as a single
    # token and miss MovieBox entries like "Spider-Man Noir" (62 vs 100).
    target_norm = default_process(target_title)
    scored: list[tuple[int, int, Candidate, bool]] = []
    for c in candidates:
        cand_norm = default_process(c.title)
        primary = int(fuzz.token_set_ratio(target_norm, cand_norm))
        # token_sort_ratio penalizes extra/missing tokens, breaking ties in
        # favor of cleaner titles ("Spider-Man Noir" over CAM/dub variants
        # like "Spider-Man Noir [Hindi][CAM]" that token_set_ratio scores equal).
        secondary = int(fuzz.token_sort_ratio(target_norm, cand_norm))
        year_ok = (
            target_year is not None
            and c.year is not None
            and abs(c.year - target_year) <= 1
        )
        scored.append((primary, secondary, c, year_ok))

    scored.sort(key=lambda t: (t[3], t[0], t[1]), reverse=True)

    aligned = [s for s in scored if s[3]]
    if aligned and aligned[0][0] >= aligned_threshold:
        return aligned[0][2]

    if scored and scored[0][0] >= fallback_threshold:
        return scored[0][2]

    return None

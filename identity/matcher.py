from __future__ import annotations

from collections.abc import Iterable

from .models import IdentityCandidate, IdentityQuery, MatchOutcome, MatchResult
from .normalize import (
    normalize_date,
    normalize_identifier,
    normalize_sex,
    normalize_text,
)


def _compare_supplied_fields(
    query: IdentityQuery,
    candidate: IdentityCandidate,
    *,
    include_member_id: bool,
) -> tuple[tuple[str, ...], tuple[str, ...], float]:
    checks = []

    if include_member_id and query.member_id:
        checks.append(
            (
                "member_id",
                normalize_identifier(query.member_id),
                normalize_identifier(candidate.member_id),
            )
        )

    if query.first_name:
        checks.append(
            (
                "first_name",
                normalize_text(query.first_name),
                normalize_text(candidate.first_name),
            )
        )

    if query.last_name:
        checks.append(
            (
                "last_name",
                normalize_text(query.last_name),
                normalize_text(candidate.last_name),
            )
        )

    if query.date_of_birth:
        checks.append(
            (
                "date_of_birth",
                normalize_date(query.date_of_birth),
                normalize_date(candidate.date_of_birth),
            )
        )

    if query.administrative_sex:
        checks.append(
            (
                "administrative_sex",
                normalize_sex(query.administrative_sex),
                normalize_sex(candidate.administrative_sex),
            )
        )

    matched = tuple(name for name, expected, actual in checks if expected == actual)
    conflicts = tuple(name for name, expected, actual in checks if expected != actual)
    score = len(matched) / len(checks) if checks else 1.0

    return matched, conflicts, score


def match_identity(
    query: IdentityQuery,
    candidates: Iterable[IdentityCandidate],
) -> MatchResult:
    """
    Resolve an identity query using deliberately conservative MVP rules.

    - Supplied member ID is the primary exact lookup key.
    - Without member ID, exact first + last + DOB is required.
    - Demographic disagreement is reported, not silently repaired.
    - No fuzzy/probabilistic matching is performed.
    """
    pool = tuple(candidates)

    if query.member_id:
        member_key = normalize_identifier(query.member_id)
        matched_candidates = tuple(
            candidate
            for candidate in pool
            if normalize_identifier(candidate.member_id) == member_key
        )

        if not matched_candidates:
            return MatchResult(outcome=MatchOutcome.NOT_FOUND)

        if len(matched_candidates) > 1:
            return MatchResult(
                outcome=MatchOutcome.AMBIGUOUS,
                candidate_ids=tuple(
                    candidate.candidate_id for candidate in matched_candidates
                ),
                matched_fields=("member_id",),
                score=1.0,
            )

        candidate = matched_candidates[0]
        matched, conflicts, score = _compare_supplied_fields(
            query,
            candidate,
            include_member_id=True,
        )
        return MatchResult(
            outcome=MatchOutcome.MATCHED,
            candidate_ids=(candidate.candidate_id,),
            matched_fields=matched,
            conflicting_fields=conflicts,
            score=score,
        )

    if not (query.first_name and query.last_name and query.date_of_birth):
        return MatchResult(outcome=MatchOutcome.NOT_FOUND)

    first_name = normalize_text(query.first_name)
    last_name = normalize_text(query.last_name)
    birth_date = normalize_date(query.date_of_birth)

    matched_candidates = tuple(
        candidate
        for candidate in pool
        if normalize_text(candidate.first_name) == first_name
        and normalize_text(candidate.last_name) == last_name
        and normalize_date(candidate.date_of_birth) == birth_date
    )

    if not matched_candidates:
        return MatchResult(outcome=MatchOutcome.NOT_FOUND)

    if len(matched_candidates) > 1:
        return MatchResult(
            outcome=MatchOutcome.AMBIGUOUS,
            candidate_ids=tuple(
                candidate.candidate_id for candidate in matched_candidates
            ),
            matched_fields=("first_name", "last_name", "date_of_birth"),
            score=1.0,
        )

    candidate = matched_candidates[0]
    matched, conflicts, score = _compare_supplied_fields(
        query,
        candidate,
        include_member_id=False,
    )
    return MatchResult(
        outcome=MatchOutcome.MATCHED,
        candidate_ids=(candidate.candidate_id,),
        matched_fields=matched,
        conflicting_fields=conflicts,
        score=score,
    )

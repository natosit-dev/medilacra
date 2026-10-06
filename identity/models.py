from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MatchOutcome(str, Enum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class IdentityQuery:
    member_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    administrative_sex: str | None = None


@dataclass(frozen=True)
class IdentityCandidate:
    candidate_id: str
    member_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    administrative_sex: str | None = None


@dataclass(frozen=True)
class MatchResult:
    outcome: MatchOutcome
    candidate_ids: tuple[str, ...] = ()
    matched_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    score: float | None = None

    @property
    def matched_candidate_id(self) -> str | None:
        if self.outcome == MatchOutcome.MATCHED and len(self.candidate_ids) == 1:
            return self.candidate_ids[0]
        return None

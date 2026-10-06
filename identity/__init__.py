"""Reusable identity-matching primitives independent of clinical or payer models."""

from .matcher import match_identity
from .models import IdentityCandidate, IdentityQuery, MatchOutcome, MatchResult

__all__ = [
    "IdentityCandidate",
    "IdentityQuery",
    "MatchOutcome",
    "MatchResult",
    "match_identity",
]

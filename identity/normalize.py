from __future__ import annotations


def normalize_text(value: str | None) -> str:
    """Minimal deterministic normalization for the exact-match MVP."""
    return " ".join((value or "").strip().casefold().split())


def normalize_identifier(value: str | None) -> str:
    """Identifiers are exact apart from surrounding whitespace and case."""
    return (value or "").strip().casefold()


def normalize_date(value: str | None) -> str:
    """Dates are compared as supplied after trimming in the MVP."""
    return (value or "").strip()


def normalize_sex(value: str | None) -> str:
    return (value or "").strip().upper()

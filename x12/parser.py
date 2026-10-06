from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class X12Segment:
    tag: str
    elements: tuple[str, ...]

    def element(self, position: int) -> str:
        """Return a 1-based X12 data element from this segment."""
        if position < 1 or position > len(self.elements):
            return ""
        return self.elements[position - 1]


def tokenize_x12(
    text: str,
    *,
    element_separator: str | None = None,
    segment_terminator: str | None = None,
) -> tuple[X12Segment, ...]:
    """
    Minimal X12 tokenizer for the eligibility MVP.

    For an ISA interchange the element separator is discovered from character
    4. Segment terminator defaults to "~", which is also what MediLacra emits.
    """
    compact = "".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ).strip()

    if not compact:
        return ()

    if element_separator is None:
        if compact.startswith("ISA") and len(compact) > 3:
            element_separator = compact[3]
        else:
            element_separator = "*"

    if segment_terminator is None:
        segment_terminator = "~"

    segments = []
    for raw in compact.split(segment_terminator):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split(element_separator)
        segments.append(
            X12Segment(
                tag=parts[0],
                elements=tuple(parts[1:]),
            )
        )

    return tuple(segments)


def first_segment(
    segments: tuple[X12Segment, ...],
    tag: str,
) -> X12Segment | None:
    return next(
        (segment for segment in segments if segment.tag == tag),
        None,
    )


def segments_by_tag(
    segments: tuple[X12Segment, ...],
    tag: str,
) -> tuple[X12Segment, ...]:
    return tuple(
        segment for segment in segments if segment.tag == tag
    )


def transaction_segments(
    text: str,
) -> tuple[X12Segment, ...]:
    """Return the first ST..SE transaction set from an X12 text blob."""
    all_segments = tokenize_x12(text)
    start = next(
        (
            index
            for index, segment in enumerate(all_segments)
            if segment.tag == "ST"
        ),
        None,
    )

    if start is None:
        return ()

    end = next(
        (
            index
            for index, segment in enumerate(
                all_segments[start:],
                start=start,
            )
            if segment.tag == "SE"
        ),
        None,
    )

    if end is None:
        return tuple(all_segments[start:])

    return tuple(all_segments[start : end + 1])

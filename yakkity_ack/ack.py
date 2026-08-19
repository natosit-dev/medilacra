"""HL7 message identity and ACK parsing."""

from __future__ import annotations

from .models import AckResult, MessageMetadata


class HL7ParseError(ValueError):
    """Raised when the minimum fields required by Yakkity ACK are absent."""


def _segments(message: str) -> list[str]:
    normalized = message.replace("\r\n", "\r").replace("\n", "\r")
    return [segment for segment in normalized.split("\r") if segment]


def _field_separator(msh: str) -> str:
    if not msh.startswith("MSH") or len(msh) < 4:
        raise HL7ParseError("message does not contain a valid MSH segment")
    return msh[3]


def parse_message_metadata(message: str) -> MessageMetadata:
    """Extract MSH-9, MSH-10, and MSH-12 from an outbound message."""

    segments = _segments(message)
    if not segments or not segments[0].startswith("MSH"):
        raise HL7ParseError("outbound message must begin with an MSH segment")

    msh = segments[0]
    separator = _field_separator(msh)
    fields = msh.split(separator)
    if len(fields) <= 11:
        raise HL7ParseError("MSH is missing one or more of MSH-9, MSH-10, MSH-12")

    message_type = fields[8].strip()
    control_id = fields[9].strip()
    version = fields[11].strip()
    if not message_type:
        raise HL7ParseError("MSH-9 message type is empty")
    if not control_id:
        raise HL7ParseError("MSH-10 message control ID is empty")

    return MessageMetadata(
        message_type=message_type,
        control_id=control_id,
        version=version,
    )


def parse_ack(message: str) -> AckResult:
    """Parse MSA acknowledgment fields and preserve ERR segments as evidence."""

    segments = _segments(message)
    if not segments or not segments[0].startswith("MSH"):
        raise HL7ParseError("ACK must begin with an MSH segment")

    separator = _field_separator(segments[0])
    msa = next((segment for segment in segments if segment.startswith(f"MSA{separator}")), None)
    if msa is None:
        raise HL7ParseError("ACK does not contain an MSA segment")

    fields = msa.split(separator)
    if len(fields) <= 2:
        raise HL7ParseError("MSA is missing MSA-1 or MSA-2")

    code = fields[1].strip()
    control_id = fields[2].strip()
    text = fields[3].strip() if len(fields) > 3 and fields[3].strip() else None
    errors = tuple(
        segment
        for segment in segments
        if segment.startswith(f"ERR{separator}")
    )

    if not code:
        raise HL7ParseError("MSA-1 acknowledgment code is empty")
    if not control_id:
        raise HL7ParseError("MSA-2 message control ID is empty")

    return AckResult(
        code=code,
        control_id=control_id,
        text=text,
        errors=errors,
        raw=message,
    )

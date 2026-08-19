"""Minimal Lower Layer Protocol framing helpers."""

from __future__ import annotations

import socket

START_BLOCK = b"\x0b"
END_BLOCK = b"\x1c"
CARRIAGE_RETURN = b"\x0d"
END_FRAME = END_BLOCK + CARRIAGE_RETURN


class MLLPError(ValueError):
    """Raised when an MLLP frame is missing or malformed."""


def canonicalize_hl7(message: str) -> str:
    """Normalize text-file newlines to HL7 carriage-return segments."""

    normalized = message.replace("\r\n", "\r").replace("\n", "\r")
    if not normalized.endswith("\r"):
        normalized += "\r"
    return normalized


def frame_message(message: str | bytes, *, encoding: str = "utf-8") -> bytes:
    """Wrap one HL7 payload in the MLLP start/end delimiters."""

    payload = message.encode(encoding) if isinstance(message, str) else message
    if payload.startswith(START_BLOCK) or payload.endswith(END_FRAME):
        raise MLLPError("message appears to already contain MLLP framing")
    return START_BLOCK + payload + END_FRAME


def unframe_message(frame: bytes, *, encoding: str = "utf-8") -> str:
    """Remove MLLP framing and decode the enclosed HL7 payload."""

    if not frame.startswith(START_BLOCK):
        raise MLLPError("MLLP frame does not start with VT / 0x0B")
    if not frame.endswith(END_FRAME):
        raise MLLPError("MLLP frame does not end with FS CR / 0x1C 0x0D")
    return frame[1:-2].decode(encoding)


def recv_frame(
    sock: socket.socket,
    *,
    max_bytes: int = 10_000_000,
    chunk_size: int = 4096,
) -> bytes:
    """Receive one complete MLLP frame from a connected socket."""

    buffer = bytearray()
    while True:
        chunk = sock.recv(chunk_size)
        if not chunk:
            raise ConnectionError("connection closed before a complete MLLP frame arrived")
        buffer.extend(chunk)

        if len(buffer) > max_bytes:
            raise MLLPError(f"MLLP frame exceeded max_bytes={max_bytes:,}")

        if buffer and buffer[0:1] != START_BLOCK:
            raise MLLPError("received data does not begin with an MLLP start block")

        end_at = buffer.find(END_FRAME)
        if end_at != -1:
            return bytes(buffer[: end_at + len(END_FRAME)])

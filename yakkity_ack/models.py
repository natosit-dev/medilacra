"""Data models for Yakkity ACK observations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageMetadata:
    """Identifiers extracted from the outbound HL7 message."""

    message_type: str
    control_id: str
    version: str


@dataclass(frozen=True)
class AckResult:
    """Parsed fields from the receiver's acknowledgment message."""

    code: str
    control_id: str
    text: str | None
    errors: tuple[str, ...]
    raw: str

    @property
    def classification(self) -> str:
        """Map standard HL7 ACK codes to a compact experiment label."""

        return {
            "AA": "ACCEPTED",
            "AE": "APPLICATION_ERROR",
            "AR": "REJECTED",
        }.get(self.code, "UNKNOWN_ACK")


@dataclass(frozen=True)
class DeliveryTimings:
    """Transport timings reported as integer microseconds."""

    connect_us: int
    send_us: int
    ack_wait_us: int
    round_trip_us: int


@dataclass(frozen=True)
class DeliveryResult:
    """Complete observation for one message delivery."""

    message: MessageMetadata
    ack: AckResult
    timings: DeliveryTimings
    host: str
    port: int

    @property
    def correlated(self) -> bool:
        """Whether the tracking number on the receipt matches the package."""

        return self.message.control_id == self.ack.control_id

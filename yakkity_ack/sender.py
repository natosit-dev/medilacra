"""The delivery person: send one HL7 package and wait for its signed receipt."""

from __future__ import annotations

import socket
from time import perf_counter_ns

from .ack import parse_ack, parse_message_metadata
from .mllp import canonicalize_hl7, frame_message, recv_frame, unframe_message
from .models import DeliveryResult, DeliveryTimings


def _us(start_ns: int, end_ns: int) -> int:
    return max(0, (end_ns - start_ns) // 1_000)


def deliver_message(
    host: str,
    port: int,
    message: str,
    *,
    timeout: float = 5.0,
    encoding: str = "utf-8",
) -> DeliveryResult:
    """Deliver one HL7 message over TCP/MLLP and observe the returned ACK.

    Timing uses ``perf_counter_ns`` internally and reports integer microseconds.
    ``round_trip_us`` starts immediately before ``sendall`` and ends when the
    complete ACK frame has arrived, so connection establishment remains a
    separate measurement.
    """

    prepared = canonicalize_hl7(message)
    metadata = parse_message_metadata(prepared)
    framed = frame_message(prepared, encoding=encoding)

    connect_start = perf_counter_ns()
    sock = socket.create_connection((host, port), timeout=timeout)
    connect_end = perf_counter_ns()

    try:
        sock.settimeout(timeout)

        send_start = perf_counter_ns()
        sock.sendall(framed)
        send_end = perf_counter_ns()

        ack_frame = recv_frame(sock)
        ack_end = perf_counter_ns()
    finally:
        sock.close()

    ack_message = unframe_message(ack_frame, encoding=encoding)
    ack = parse_ack(ack_message)

    timings = DeliveryTimings(
        connect_us=_us(connect_start, connect_end),
        send_us=_us(send_start, send_end),
        ack_wait_us=_us(send_end, ack_end),
        round_trip_us=_us(send_start, ack_end),
    )

    return DeliveryResult(
        message=metadata,
        ack=ack,
        timings=timings,
        host=host,
        port=port,
    )

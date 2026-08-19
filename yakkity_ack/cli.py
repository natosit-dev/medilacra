"""Command-line entry point for the first Yakkity ACK delivery loop."""

from __future__ import annotations

import argparse
from pathlib import Path

from .sender import deliver_message


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deliver one HL7 v2 message to an MLLP receiver and inspect the ACK."
    )
    parser.add_argument("--host", required=True, help="IRIS receiver host or IP address.")
    parser.add_argument("--port", required=True, type=int, help="IRIS MLLP listening port.")
    parser.add_argument(
        "--message",
        required=True,
        type=Path,
        help="Path to one MediLacra HL7 message file.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Socket connect/read timeout in seconds (default: 5).",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding for the HL7 message and ACK (default: utf-8).",
    )
    parser.add_argument(
        "--show-ack",
        action="store_true",
        help="Print the complete raw ACK after the summary.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    message = args.message.read_text(encoding=args.encoding)

    result = deliver_message(
        args.host,
        args.port,
        message,
        timeout=args.timeout,
        encoding=args.encoding,
    )

    correlation = "PASS" if result.correlated else "FAIL"

    print("Yakkity ACK")
    print(f"Recipient:   {result.host}:{result.port}")
    print(f"Message:     {result.message.message_type}")
    print(f"MSH-10:      {result.message.control_id}")
    print(f"HL7 version: {result.message.version or '(not supplied)'}")
    print()
    print(f"ACK:         {result.ack.code} ({result.ack.classification})")
    print(f"MSA-2:       {result.ack.control_id}")
    print(f"Correlation: {correlation}")
    if result.ack.text:
        print(f"ACK text:    {result.ack.text}")
    for error in result.ack.errors:
        print(f"ERR:         {error}")
    print()
    print("Timing (microseconds):")
    print(f"  connect:    {result.timings.connect_us:,} us")
    print(f"  send:       {result.timings.send_us:,} us")
    print(f"  ACK wait:   {result.timings.ack_wait_us:,} us")
    print(f"  round trip: {result.timings.round_trip_us:,} us")

    if args.show_ack:
        print()
        print("Raw ACK:")
        print(result.ack.raw.replace("\r", "\n"))

    return 0 if result.correlated else 2

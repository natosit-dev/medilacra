import socket
import threading

from yakkity_ack.ack import parse_ack, parse_message_metadata
from yakkity_ack.mllp import frame_message, recv_frame, unframe_message
from yakkity_ack.sender import deliver_message


ADT = (
    "MSH|^~\\&|MEDILACRA|LAB|IRIS|BIDMC|20260819120000||ADT^A01|MEDI-123|P|2.5\r"
    "PID|1||P123^^^MEDILACRA^MR||TEST^PATIENT||19800101|F\r"
    "PV1|1|I||||||||||||||||V123\r"
)

ACK = (
    "MSH|^~\\&|IRIS|BIDMC|MEDILACRA|LAB|20260819120001||ACK^A01|ACK-1|P|2.5\r"
    "MSA|AA|MEDI-123|Message accepted\r"
)


def test_mllp_frame_round_trip():
    framed = frame_message(ADT)
    assert framed.startswith(b"\x0b")
    assert framed.endswith(b"\x1c\x0d")
    assert unframe_message(framed) == ADT


def test_extract_message_identity_and_ack_correlation_fields():
    metadata = parse_message_metadata(ADT)
    ack = parse_ack(ACK)

    assert metadata.message_type == "ADT^A01"
    assert metadata.control_id == "MEDI-123"
    assert metadata.version == "2.5"
    assert ack.code == "AA"
    assert ack.control_id == "MEDI-123"
    assert ack.classification == "ACCEPTED"


def test_delivery_loop_against_local_mock_receiver():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    failures = []

    def receiver():
        try:
            conn, _ = server.accept()
            with conn:
                inbound = unframe_message(recv_frame(conn))
                metadata = parse_message_metadata(inbound)
                response = ACK.replace("MEDI-123", metadata.control_id)
                conn.sendall(frame_message(response))
        except Exception as exc:  # pragma: no cover - surfaced in parent thread
            failures.append(exc)
        finally:
            server.close()

    thread = threading.Thread(target=receiver, daemon=True)
    thread.start()

    result = deliver_message("127.0.0.1", port, ADT, timeout=2.0)
    thread.join(timeout=2.0)

    assert not failures
    assert result.ack.code == "AA"
    assert result.correlated is True
    assert result.message.control_id == result.ack.control_id
    assert result.timings.connect_us >= 0
    assert result.timings.send_us >= 0
    assert result.timings.ack_wait_us >= 0
    assert result.timings.round_trip_us >= result.timings.send_us

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnvelopeConfig:
    sender_id: str
    receiver_id: str
    interchange_control_number: str
    group_control_number: str
    interchange_date: str
    interchange_time: str
    group_date: str
    group_time: str
    sender_qualifier: str = "ZZ"
    receiver_qualifier: str = "ZZ"
    usage_indicator: str = "T"


def _pad(value: str, length: int) -> str:
    value = str(value)
    if len(value) > length:
        raise ValueError(
            f"X12 envelope value {value!r} exceeds fixed length {length}"
        )
    return value.ljust(length)


def _control_number(value: str, length: int) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    if not digits:
        raise ValueError("X12 control number must contain at least one digit")
    if len(digits) > length:
        raise ValueError(
            f"X12 control number {value!r} exceeds fixed length {length}"
        )
    return digits.zfill(length)


def wrap_interchange(
    transaction_set: str,
    *,
    config: EnvelopeConfig,
    functional_id: str = "HS",
    version: str = "005010X279A1",
) -> str:
    """
    Wrap one 270 or 271 transaction set in a minimal test interchange.

    The envelope is deliberately separate from eligibility semantics.
    """
    transaction_set = transaction_set.strip()
    if not transaction_set.startswith("ST*"):
        raise ValueError("transaction_set must begin with ST")
    if not transaction_set.endswith("~"):
        transaction_set += "~"

    interchange_control = _control_number(
        config.interchange_control_number,
        9,
    )
    group_control = str(int(config.group_control_number))

    isa = "*".join(
        [
            "ISA",
            "00",
            _pad("", 10),
            "00",
            _pad("", 10),
            config.sender_qualifier,
            _pad(config.sender_id, 15),
            config.receiver_qualifier,
            _pad(config.receiver_id, 15),
            config.interchange_date,
            config.interchange_time,
            "^",
            "00501",
            interchange_control,
            "0",
            config.usage_indicator,
            ":",
        ]
    ) + "~"

    gs = (
        f"GS*{functional_id}*{config.sender_id}*{config.receiver_id}*"
        f"{config.group_date}*{config.group_time}*{group_control}*X*{version}~"
    )
    ge = f"GE*1*{group_control}~"
    iea = f"IEA*1*{interchange_control}~"

    return isa + gs + transaction_set + ge + iea

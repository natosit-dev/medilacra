from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from payer.models import EligibilityInquiry


DEFAULT_REQUESTER_ID = "MEDILACRA01"


@dataclass(frozen=True)
class EligibilityExchangeIdentity:
    exchange_sequence: int
    exchange_id: str
    trace_id: str
    reference_id: str


@dataclass
class EligibilityRunContext:
    """
    Representation-neutral eligibility exchange identity allocator.

    One semantic exchange identity is shared by the X12 and FHIR projections.
    Representation-specific control numbers remain outside this context.
    """

    run_at: datetime
    exchange_sequence: int = 0

    @property
    def run_stamp(self) -> str:
        return self.run_at.strftime("%Y%m%d%H%M%S")

    @property
    def file_stamp(self) -> str:
        return self.run_at.strftime("%Y%m%d_%H%M%S")

    def next_exchange(self) -> EligibilityExchangeIdentity:
        self.exchange_sequence += 1
        if self.exchange_sequence > 99999:
            raise ValueError(
                "EligibilityRunContext exhausted five-digit exchange sequence"
            )

        suffix = f"{self.exchange_sequence:05d}"
        exchange_id = f"{self.run_stamp}-{suffix}"

        return EligibilityExchangeIdentity(
            exchange_sequence=self.exchange_sequence,
            exchange_id=exchange_id,
            trace_id=f"TRACE-270-{exchange_id}",
            reference_id=f"ELIG-REQ-{exchange_id}",
        )


def _split_clinical_name(value: str) -> tuple[str, str]:
    """
    Return first_name, last_name from the current MediLacra clinical name.

    General generation uses LAST, FIRST while older fixtures may use
    LAST^FIRST. This helper belongs to the semantic boundary so neither the
    X12 nor FHIR projection needs to infer name structure independently.
    """
    raw = (value or "").strip()

    if "^" in raw:
        last_name, first_name = [
            part.strip()
            for part in raw.split("^", 1)
        ]
    elif "," in raw:
        last_name, first_name = [
            part.strip()
            for part in raw.split(",", 1)
        ]
    else:
        raise ValueError(
            "Clinical patient_name must contain LAST, FIRST or LAST^FIRST"
        )

    if not first_name or not last_name:
        raise ValueError(
            "Clinical patient_name must contain both last and first name"
        )

    return first_name, last_name


def _iso_date(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        return raw[:10]

    compact = raw.replace("-", "")
    if len(compact) == 8 and compact.isdigit():
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"

    raise ValueError(f"Expected YYYY-MM-DD or YYYYMMDD date, got {value!r}")


def _service_date_from_encounter(encounter) -> str:
    raw = str(encounter.admit_datetime or "").strip()
    if len(raw) < 10:
        raise ValueError(
            "Encounter admit_datetime must contain a date"
        )
    return _iso_date(raw[:10])


def build_eligibility_inquiry_from_clinical(
    patient,
    coverage_profile,
    encounter,
    *,
    requester_id: str = DEFAULT_REQUESTER_ID,
    service_type: str = "30",
) -> EligibilityInquiry:
    """
    Materialize the semantic eligibility inquiry from clinical-side reality.

    No exchange representation is involved here. X12 and FHIR both consume
    this same inquiry.
    """
    first_name, last_name = _split_clinical_name(
        patient.patient_name
    )

    return EligibilityInquiry(
        payer_id=str(coverage_profile.payer_id),
        requester_id=str(requester_id),
        member_id=str(coverage_profile.member_id),
        first_name=first_name,
        last_name=last_name,
        date_of_birth=_iso_date(patient.date_of_birth),
        administrative_sex=str(patient.sex),
        service_date=_service_date_from_encounter(encounter),
        service_type=str(service_type),
    )

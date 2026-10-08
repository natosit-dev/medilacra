"""Semantic Claims/ePA MVP. No X12 or FHIR dependencies live here.

Synthetic test cases only; payer decisions are deliberately explicit and not
representations of a real payer contract, utilization policy or fee schedule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from payer.models import EnrollmentStatus


def cents(value: object) -> int:
    """Convert a source currency amount to exact cents; reject negative/NaN."""
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError("amount must be a non-negative finite number")
        quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return int(quantized * 100)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid currency amount") from exc


def usd(value: int) -> str:
    if value < 0:
        raise ValueError("negative cents")
    return f"{value // 100}.{value % 100:02d}"


@dataclass(frozen=True)
class ServiceLine:
    sequence: int
    procedure_code: str
    diagnosis_code: str
    units: int
    charge_cents: int

    def __post_init__(self):
        if not self.procedure_code or not self.diagnosis_code:
            raise ValueError("service requires procedure and diagnosis")
        if self.sequence < 1 or self.units < 1 or self.charge_cents < 0:
            raise ValueError("invalid service quantities/amount")


@dataclass(frozen=True)
class ClaimSubmission:
    exchange_id: str
    claim_id: str
    patient_id: str
    patient_name: str
    birth_date: str
    sex: str
    member_id: str
    payer_id: str
    payer_name: str
    provider_npi: str
    provider_name: str
    encounter_id: str
    service_date: str
    line: ServiceLine

    @property
    def charge_cents(self) -> int:
        return self.line.charge_cents


@dataclass(frozen=True)
class ClaimDecision:
    exchange_id: str
    claim_id: str
    status: str
    charged_cents: int
    allowed_cents: int
    paid_cents: int
    patient_cents: int
    adjusted_cents: int

    def __post_init__(self):
        if self.status not in ("paid", "denied"):
            raise ValueError("claim decision must be paid or denied")
        amounts = (self.charged_cents, self.allowed_cents, self.paid_cents,
                   self.patient_cents, self.adjusted_cents)
        if min(amounts) < 0:
            raise ValueError("negative adjudication amount")
        if self.charged_cents != self.paid_cents + self.patient_cents + self.adjusted_cents:
            raise ValueError("adjudication does not reconcile")
        if self.allowed_cents != self.paid_cents + self.patient_cents:
            raise ValueError("allowed amount does not reconcile")
        if self.status == "denied" and (self.paid_cents or self.allowed_cents):
            raise ValueError("denied claim cannot have allowed/payment amount")


@dataclass(frozen=True)
class AuthorizationRequest:
    exchange_id: str
    request_id: str
    patient_id: str
    patient_name: str
    birth_date: str
    sex: str
    member_id: str
    payer_id: str
    payer_name: str
    provider_npi: str
    provider_name: str
    service_date: str
    procedure_code: str
    diagnosis_code: str
    quantity: int

    def __post_init__(self):
        if self.quantity < 1 or not self.procedure_code or not self.diagnosis_code:
            raise ValueError("invalid authorization service")


@dataclass(frozen=True)
class AuthorizationDecision:
    exchange_id: str
    request_id: str
    status: str
    authorization_number: str | None
    reason: str | None

    def __post_init__(self):
        if self.status not in ("approved", "pended", "denied"):
            raise ValueError("unsupported authorization status")
        if self.status == "approved" and not self.authorization_number:
            raise ValueError("approved authorization must have a number")
        if self.status != "approved" and self.authorization_number:
            raise ValueError("non-approved authorization cannot have certification")


@dataclass(frozen=True)
class SemanticCase:
    claim: ClaimSubmission
    claim_decision: ClaimDecision
    authorization: AuthorizationRequest
    authorization_decision: AuthorizationDecision


def _source_date(raw: object) -> str:
    value = str(raw).strip()[:10]
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")


def build_case(
    *, patient, coverage, encounter, transaction, observation,
    run_at: datetime, ordinal: int = 1,
    payer_member, payer_enrollment,
    authorization_status: str = "approved",
    claim_status: str = "paid",
) -> SemanticCase:
    """Build sibling exchanges from existing MediLacra entities and payer-local state.

    The payer decision accesses payer records, not hidden GroundTruthLink.
    The caller selects synthetic decisions; this is not medical-necessity logic.
    """
    if ordinal < 1 or ordinal > 99999:
        raise ValueError("ordinal must fit five digits")
    if str(patient.patient_id) != str(encounter.patient_id):
        raise ValueError("clinical patient/encounter mismatch")
    if str(patient.patient_id) != str(coverage.patient_id):
        raise ValueError("clinical patient/coverage mismatch")
    if str(transaction.encounter_id) != str(encounter.encounter_id):
        raise ValueError("clinical transaction/encounter mismatch")
    if str(observation.encounter_id) != str(encounter.encounter_id):
        raise ValueError("observation/encounter mismatch")

    date = _source_date(encounter.admit_datetime)
    bill = cents(transaction.transaction_amount)
    quantity = int(transaction.transaction_quantity)
    if quantity < 1:
        raise ValueError("quantity must be positive")
    if not str(observation.cpt_code) or not str(observation.icd_code):
        raise ValueError("CPT/diagnosis required; no serializer fallback")
    stamp = run_at.strftime("%Y%m%d%H%M%S")
    base = f"{stamp}-{ordinal:05d}"
    claim_id = f"CLM-{base}"
    auth_id = f"PA-{base}"
    claim = ClaimSubmission(
        exchange_id=f"CLAIM-{base}", claim_id=claim_id,
        patient_id=str(patient.patient_id),
        patient_name=str(patient.patient_name),
        birth_date=_source_date(patient.date_of_birth), sex=str(patient.sex),
        member_id=str(coverage.member_id), payer_id=str(coverage.payer_id),
        payer_name=str(coverage.payer_name),
        provider_npi=str(transaction.billing_provider_npi),
        provider_name=str(transaction.billing_provider_name),
        encounter_id=str(encounter.encounter_id), service_date=date,
        line=ServiceLine(
            sequence=1, procedure_code=str(observation.cpt_code),
            diagnosis_code=str(observation.icd_code),
            units=quantity, charge_cents=bill,
        ),
    )
    authorization = AuthorizationRequest(
        exchange_id=f"AUTH-{base}", request_id=auth_id,
        patient_id=claim.patient_id, patient_name=claim.patient_name,
        birth_date=claim.birth_date, sex=claim.sex, member_id=claim.member_id,
        payer_id=claim.payer_id, payer_name=claim.payer_name,
        provider_npi=claim.provider_npi, provider_name=claim.provider_name,
        service_date=date, procedure_code=claim.line.procedure_code,
        diagnosis_code=claim.line.diagnosis_code, quantity=claim.line.units,
    )

    payer_active = (
        str(payer_member.member_id) == claim.member_id
        and str(payer_member.payer_id) == claim.payer_id
        and str(payer_enrollment.payer_id) == claim.payer_id
        and str(payer_enrollment.member_record_id) == str(payer_member.member_record_id)
        and payer_enrollment.status == EnrollmentStatus.ACTIVE
        and _source_date(payer_enrollment.effective_start) <= date
        <= _source_date(payer_enrollment.effective_end)
    )
    if claim_status not in ("paid", "denied"):
        raise ValueError("unsupported synthetic claim status")
    if authorization_status not in ("approved", "pended", "denied"):
        raise ValueError("unsupported synthetic authorization status")

    paid = payer_active and claim_status == "paid"
    # Explicit deterministic test schedule: 80% allowed, all allowed paid.
    allowed = bill * 80 // 100 if paid else 0
    claim_decision = ClaimDecision(
        exchange_id=claim.exchange_id, claim_id=claim_id,
        status="paid" if paid else "denied", charged_cents=bill,
        allowed_cents=allowed, paid_cents=allowed, patient_cents=0,
        adjusted_cents=bill - allowed,
    )
    final_auth = authorization_status if payer_active else "denied"
    authorization_decision = AuthorizationDecision(
        exchange_id=authorization.exchange_id, request_id=auth_id,
        status=final_auth,
        authorization_number=f"CERT-{base}" if final_auth == "approved" else None,
        reason=None if final_auth == "approved" else (
            "review-pending" if final_auth == "pended" else "not-authorized"
        ),
    )
    return SemanticCase(claim, claim_decision, authorization, authorization_decision)

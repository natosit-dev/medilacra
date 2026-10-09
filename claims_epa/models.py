"""Semantic Claims/ePA MVP. No X12 or FHIR dependencies live here.

Synthetic test cases only; payer decisions are deliberately explicit and not
representations of a real payer contract, utilization policy or fee schedule.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from datetime import datetime, timedelta
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
class PostalAddress:
    street: str
    city: str
    state: str
    postal_code: str

    def __post_init__(self):
        if not all((self.street, self.city, self.state, self.postal_code)):
            raise ValueError("Incomplete source-owned postal address")


@dataclass(frozen=True)
class ClaimRouting:
    """Scenario-owned institutional facts, never invented by the X12 renderer."""
    patient_address: PostalAddress
    billing_address: PostalAddress
    submitter_name: str
    submitter_id: str
    submitter_contact: str
    submitter_phone: str
    billing_tax_id: str
    sender_id: str
    filing_indicator: str
    subscriber_relationship_code: str
    place_of_service_code: str
    claim_flags: tuple[str, str, str, str]


def synthetic_claim_routing(patient, encounter, provider_npi: str) -> ClaimRouting:
    """Explicit, seeded demonstration-site fixture; NOT provider-directory facts."""
    from faker import Faker
    seed = int(hashlib.sha256(str(provider_npi).encode()).hexdigest()[:12], 16)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    patient_address = PostalAddress(
        street=str(patient.address), city=str(patient.city),
        state=str(patient.state), postal_code=str(patient.zip_code))
    provider_address = PostalAddress(
        street=fake.street_address(), city=fake.city(),
        state=fake.state_abbr(), postal_code=fake.postcode())
    pos = str(getattr(encounter, "place_of_service_code", "")).strip()
    if not pos:
        raise ValueError("Claim scenario must establish place_of_service_code")
    return ClaimRouting(
        patient_address=patient_address, billing_address=provider_address,
        submitter_name="MEDILACRA SYNTHETIC SUBMITTER",
        submitter_id="MEDILACRA01", submitter_contact="SYNTHETIC EDI",
        submitter_phone="5550100000", billing_tax_id=f"{100000000 + seed % 800000000:09d}",
        sender_id="MEDILACRA", filing_indicator="CI",
        subscriber_relationship_code="18", place_of_service_code=pos,
        claim_flags=("Y", "A", "Y", "Y"),
    )


@dataclass(frozen=True)
class CoveragePeriods:
    clinical_start: str
    clinical_end: str
    payer_start: str
    payer_end: str
    payer_status: str


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
    routing: ClaimRouting
    coverage_periods: CoveragePeriods

    @property
    def charge_cents(self) -> int:
        return self.line.charge_cents


@dataclass(frozen=True)
class SyntheticAdjudicationPolicy:
    """Versioned synthetic rules, not representations of any real payer contract."""
    policy_id: str
    allowed_percent: int
    patient_share_percent: int
    payment_method: str
    paid_adjustment_group: str
    paid_adjustment_reason: str
    denied_adjustment_group: str
    denied_adjustment_reason: str

    def __post_init__(self):
        if not (0 <= self.allowed_percent <= 100 and
                0 <= self.patient_share_percent <= 100):
            raise ValueError("Synthetic adjudication percentages must be 0..100")
        if not self.policy_id:
            raise ValueError("Synthetic payer policy requires policy_id")


def synthetic_adjudication_policy() -> SyntheticAdjudicationPolicy:
    return SyntheticAdjudicationPolicy(
        policy_id="example-payer-flat80-v1", allowed_percent=80,
        patient_share_percent=0, payment_method="CHK",
        paid_adjustment_group="CO", paid_adjustment_reason="45",
        denied_adjustment_group="CO", denied_adjustment_reason="96",
    )


@dataclass(frozen=True)
class RemittanceInstructions:
    """Explicit simulated payer payment and adjustment policy facts."""
    payment_method: str
    originating_company_id: str
    trace_id: str
    payee_name: str
    payee_npi: str
    adjustment_group: str
    adjustment_reason: str


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
    remittance: RemittanceInstructions | None = None

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
class RequestedService:
    """A separately authored, prospective clinical intent (not an old result)."""
    service_request_id: str
    patient_id: str
    requesting_provider_npi: str
    service_date: str
    procedure_code: str
    diagnosis_code: str
    quantity: int
    status: str
    source: str

    def __post_init__(self):
        if not all((self.service_request_id, self.patient_id, self.service_date,
                    self.procedure_code, self.diagnosis_code, self.source)):
            raise ValueError("RequestedService requires explicit source facts")
        if self.quantity < 1 or self.status != "planned":
            raise ValueError("Only positive-unit planned services are supported")


def synthetic_followup_service(*, patient_id: str, provider_npi: str,
                               diagnosis_code: str, run_at: datetime,
                               encounter_date: str, ordinal: int) -> RequestedService:
    """Explicit named scenario policy: prospective outpatient consultation.

    This source generator is NOT a serializer. It does not copy a performed
    procedure code from a completed Observation; it creates a distinct intent.
    """
    date = (max(datetime.fromisoformat(encounter_date).date(), run_at.date())
            + timedelta(days=14)).isoformat()
    stamp = run_at.strftime("%Y%m%d%H%M%S")
    return RequestedService(
        service_request_id=f"RS-{stamp}-{ordinal:05d}",
        patient_id=patient_id, requesting_provider_npi=provider_npi,
        service_date=date, procedure_code="99213", diagnosis_code=diagnosis_code,
        quantity=1, status="planned", source="synthetic-followup-v1",
    )


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
    coverage_periods: CoveragePeriods

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
class PayerSubject:
    """Payer-local member identity, never reconstructed from a clinical request."""
    member_record_id: str
    member_id: str
    payer_id: str
    first_name: str
    last_name: str
    birth_date: str
    sex: str


@dataclass(frozen=True)
class PayerContact:
    """Payer remittance contact data; synthetic fixture unless supplied explicitly."""
    payer_id: str
    address_line1: str
    city: str
    state: str
    postal_code: str
    contact_name: str
    contact_phone: str

    def __post_init__(self):
        if not all((self.payer_id, self.address_line1, self.city, self.state,
                    self.postal_code, self.contact_name, self.contact_phone)):
            raise ValueError("payer remittance contact fields must be supplied")


def synthetic_payer_contact(payer_id: str) -> PayerContact:
    """Explicit test fixture, NOT a factual address for the named payer."""
    from faker import Faker
    seed = int(hashlib.sha256(str(payer_id).encode()).hexdigest()[:12], 16)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    return PayerContact(
        payer_id=payer_id,
        address_line1=fake.street_address(),
        city=fake.city(), state=fake.state_abbr(), postal_code=fake.postcode(),
        contact_name="SYNTHETIC EDI SUPPORT", contact_phone="5550100000",
    )


@dataclass(frozen=True)
class SemanticCase:
    claim: ClaimSubmission
    claim_decision: ClaimDecision
    authorization: AuthorizationRequest
    authorization_decision: AuthorizationDecision
    payer_subject: PayerSubject
    payer_contact: PayerContact
    requested_service: RequestedService
    payer_policy: SyntheticAdjudicationPolicy


def _source_date(raw: object) -> str:
    value = str(raw).strip()[:10]
    return datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")


def build_case(
    *, patient, coverage, encounter, transaction, observation,
    run_at: datetime, ordinal: int = 1,
    payer_member, payer_enrollment,
    authorization_status: str = "approved",
    claim_status: str = "paid",
    payer_contact: PayerContact | None = None,
    claim_routing: ClaimRouting | None = None,
    requested_service: RequestedService | None = None,
    adjudication_policy: SyntheticAdjudicationPolicy | None = None,
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
    # Claims represent completed work. Prior auth represents a separate
    # prospective service request; the default is a named synthetic scenario.
    requested_service = requested_service or synthetic_followup_service(
        patient_id=str(patient.patient_id),
        provider_npi=str(transaction.billing_provider_npi),
        diagnosis_code=str(observation.icd_code), run_at=run_at,
        encounter_date=date, ordinal=ordinal,
    )
    if requested_service.patient_id != str(patient.patient_id):
        raise ValueError("RequestedService patient mismatch")
    pa_date = requested_service.service_date
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
    claim_routing = claim_routing or synthetic_claim_routing(
        patient, encounter, str(transaction.billing_provider_npi))
    periods = CoveragePeriods(
        clinical_start=_source_date(coverage.effective_start),
        clinical_end=_source_date(coverage.effective_end),
        payer_start=_source_date(payer_enrollment.effective_start),
        payer_end=_source_date(payer_enrollment.effective_end),
        payer_status=str(payer_enrollment.status.value),
    )
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
        routing=claim_routing,
        coverage_periods=periods,
    )
    authorization = AuthorizationRequest(
        exchange_id=f"AUTH-{base}", request_id=auth_id,
        patient_id=claim.patient_id, patient_name=claim.patient_name,
        birth_date=claim.birth_date, sex=claim.sex, member_id=claim.member_id,
        payer_id=claim.payer_id, payer_name=claim.payer_name,
        provider_npi=claim.provider_npi, provider_name=claim.provider_name,
        service_date=pa_date, procedure_code=requested_service.procedure_code,
        diagnosis_code=requested_service.diagnosis_code,
        quantity=requested_service.quantity,
        coverage_periods=periods,
    )

    payer_identity_matches = (
        str(payer_member.member_id) == claim.member_id
        and str(payer_member.payer_id) == claim.payer_id
        and str(payer_enrollment.payer_id) == claim.payer_id
        and str(payer_enrollment.member_record_id) == str(payer_member.member_record_id)
        and payer_enrollment.status == EnrollmentStatus.ACTIVE
    )
    active_start = _source_date(payer_enrollment.effective_start)
    active_end = _source_date(payer_enrollment.effective_end)
    payer_active_claim = payer_identity_matches and active_start <= date <= active_end
    payer_active_pa = payer_identity_matches and active_start <= pa_date <= active_end
    if claim_status not in ("paid", "denied"):
        raise ValueError("unsupported synthetic claim status")
    if authorization_status not in ("approved", "pended", "denied"):
        raise ValueError("unsupported synthetic authorization status")

    paid = payer_active_claim and claim_status == "paid"
    adjudication_policy = adjudication_policy or synthetic_adjudication_policy()
    allowed = bill * adjudication_policy.allowed_percent // 100 if paid else 0
    patient_share = allowed * adjudication_policy.patient_share_percent // 100
    payer_paid = allowed - patient_share
    claim_decision = ClaimDecision(
        exchange_id=claim.exchange_id, claim_id=claim_id,
        status="paid" if paid else "denied", charged_cents=bill,
        allowed_cents=allowed, paid_cents=payer_paid,
        patient_cents=patient_share, adjusted_cents=bill - allowed,
        remittance=RemittanceInstructions(
            payment_method=adjudication_policy.payment_method,
            originating_company_id=claim.payer_id,
            trace_id=f"PAY-{base}",
            payee_name=claim.provider_name, payee_npi=claim.provider_npi,
            adjustment_group=(adjudication_policy.paid_adjustment_group if paid
                              else adjudication_policy.denied_adjustment_group),
            adjustment_reason=(adjudication_policy.paid_adjustment_reason if paid
                               else adjudication_policy.denied_adjustment_reason),
        ),
    )
    final_auth = authorization_status if payer_active_pa else "denied"
    authorization_decision = AuthorizationDecision(
        exchange_id=authorization.exchange_id, request_id=auth_id,
        status=final_auth,
        authorization_number=f"CERT-{base}" if final_auth == "approved" else None,
        reason=None if final_auth == "approved" else (
            "review-pending" if final_auth == "pended" else "not-authorized"
        ),
    )
    payer_subject = PayerSubject(
        member_record_id=str(payer_member.member_record_id),
        member_id=str(payer_member.member_id),
        payer_id=str(payer_member.payer_id),
        first_name=str(payer_member.first_name),
        last_name=str(payer_member.last_name),
        birth_date=_source_date(payer_member.date_of_birth),
        sex=str(payer_member.administrative_sex),
    )
    payer_contact = payer_contact or synthetic_payer_contact(claim.payer_id)
    if payer_contact.payer_id != claim.payer_id:
        raise ValueError("payer contact identity does not match claim payer")
    return SemanticCase(claim, claim_decision, authorization,
                        authorization_decision, payer_subject, payer_contact,
                        requested_service, adjudication_policy)

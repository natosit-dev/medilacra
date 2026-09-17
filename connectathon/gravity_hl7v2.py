"""HL7 v2 projection for the MediLacra caregiver health baseline.

The QuestionnaireResponse remains the captured source of the caregiver's answers. This module
projects those same answers into an HL7 v2.5 ORU^R01 without inventing an encounter, order, or
medication administration event that did not occur.
"""

from __future__ import annotations

import re
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.gravity_questionnaire import (
    HEART_RATE_LOINC,
    PAIN_LOINC,
    PHQ2_QUESTION_1,
    PHQ2_QUESTION_2,
    PHQ2_TOTAL,
    PHQ_DISPLAY_BY_CODE,
    PHQ_SCORE_BY_CODE,
)
from connectathon.gravity_response import (
    answer_absent_reason,
    find_response_items,
    first_answer,
    iter_response_items,
)
from hl7_demo.utils import hl7_escape, hl7_name_from_full


HL7_VERSION = "2.5"
LOCAL_CODING_SYSTEM = "99MEDILACRA"
PANEL_CODE = "caregiver-health-baseline"
PANEL_DISPLAY = "MediLacra Caregiver Health Baseline"

_ABSENT_DISPLAY = {
    "asked-declined": "Asked but declined",
    "asked-unknown": "Asked but unknown",
    "not-asked": "Not asked",
    "unknown": "Unknown",
    "error": "Invalid or unparseable input",
    "not-a-number": "Not a number",
    "positive-infinity": "Positive infinity",
    "negative-infinity": "Negative infinity",
}


def _patient_mapping(patient: Any) -> dict[str, Any]:
    if is_dataclass(patient):
        return asdict(patient)
    if isinstance(patient, Mapping):
        return dict(patient)
    raise TypeError("patient must be a mapping or dataclass")


def _ts(value: Any) -> str:
    """Render an ISO/date/datetime value as a 14-digit HL7 TS when possible."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M%S")
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y%m%d%H%M%S")
    except ValueError:
        digits = re.sub(r"\D", "", text)
        return digits[:14]


def _segment(name: str, values: Mapping[int, Any], last_field: int | None = None) -> str:
    """Build a non-MSH segment by explicit HL7 field number."""
    end = last_field or max(values, default=0)
    fields = [name] + [""] * end
    for field_number, value in values.items():
        fields[field_number] = "" if value is None else str(value)
    return "|".join(fields)


def _msh(
    *,
    message_ts: str,
    control_id: str,
    sending_application: str,
    sending_facility: str,
    receiving_application: str,
    receiving_facility: str,
) -> str:
    return "|".join(
        [
            "MSH",
            "^~\\&",
            hl7_escape(sending_application),
            hl7_escape(sending_facility),
            hl7_escape(receiving_application),
            hl7_escape(receiving_facility),
            message_ts,
            "",
            "ORU^R01^ORU_R01",
            hl7_escape(control_id),
            "P",
            HL7_VERSION,
        ]
    )


def _patient_identifier(src: Mapping[str, Any]) -> str:
    value = str(src.get("mrn") or src.get("patient_id") or "").strip()
    return f"{hl7_escape(value)}^^^MEDILACRA^MR" if value else ""


def _pid(patient: Any) -> str:
    src = _patient_mapping(patient)
    address = "^".join(
        [
            hl7_escape(src.get("address") or ""),
            "",
            hl7_escape(src.get("city") or ""),
            hl7_escape(src.get("state") or ""),
            hl7_escape(src.get("zip_code") or src.get("zip") or ""),
        ]
    ).rstrip("^")
    return _segment(
        "PID",
        {
            1: "1",
            3: _patient_identifier(src),
            5: hl7_name_from_full(str(src.get("patient_name") or "")),
            7: _ts(src.get("date_of_birth"))[:8],
            8: hl7_escape(src.get("sex") or src.get("gender") or ""),
            11: address,
            13: hl7_escape(src.get("phone") or ""),
        },
        last_field=13,
    )


def _obr(authored_ts: str) -> str:
    return _segment(
        "OBR",
        {
            1: "1",
            4: f"{PANEL_CODE}^{PANEL_DISPLAY}^{LOCAL_CODING_SYSTEM}",
            7: authored_ts,
            25: "F",
        },
        last_field=25,
    )


def _obx(
    set_id: int,
    *,
    value_type: str,
    code: str,
    display: str,
    system: str,
    value: Any,
    units: str = "",
    sub_id: str = "",
    observed_ts: str = "",
) -> str:
    return _segment(
        "OBX",
        {
            1: set_id,
            2: value_type,
            3: f"{hl7_escape(code)}^{hl7_escape(display)}^{hl7_escape(system)}",
            4: hl7_escape(sub_id),
            5: value,
            6: units,
            11: "F",
            14: observed_ts,
        },
        last_field=14,
    )


def _answer_value(answer: Mapping[str, Any] | None, key: str) -> Any:
    return answer.get(key) if isinstance(answer, Mapping) else None


def _child_answer(group: Mapping[str, Any], link_id: str) -> Mapping[str, Any] | None:
    for _path, item in iter_response_items(list(group.get("item") or [])):
        if item.get("linkId") != link_id:
            continue
        answers = item.get("answer") or []
        if answers and isinstance(answers[0], Mapping):
            return answers[0]
    return None


def _append_absent_obx(
    parts: list[str],
    set_id: int,
    *,
    question_code: str,
    question_display: str,
    reason: str,
    observed_ts: str,
    sub_id: str = "",
) -> int:
    display = _ABSENT_DISPLAY.get(reason, reason.replace("-", " ").title())
    parts.append(
        _obx(
            set_id,
            value_type="CWE",
            code=f"{question_code}-data-absent-reason",
            display=f"Data absent reason - {question_display}",
            system=LOCAL_CODING_SYSTEM,
            sub_id=sub_id,
            value=f"{hl7_escape(reason)}^{hl7_escape(display)}^{LOCAL_CODING_SYSTEM}",
            observed_ts=observed_ts,
        )
    )
    return set_id + 1


def _append_answer_or_absent(
    parts: list[str],
    set_id: int,
    *,
    answer: Mapping[str, Any] | None,
    question_code: str,
    question_display: str,
    system: str,
    value_type: str,
    value_key: str,
    units: str = "",
    observed_ts: str,
) -> int:
    reason = answer_absent_reason(answer)
    if reason:
        return _append_absent_obx(
            parts,
            set_id,
            question_code=question_code,
            question_display=question_display,
            reason=reason,
            observed_ts=observed_ts,
        )
    value = _answer_value(answer, value_key)
    if value is None:
        return set_id
    parts.append(
        _obx(
            set_id,
            value_type=value_type,
            code=question_code,
            display=question_display,
            system=system,
            value=hl7_escape(value),
            units=units,
            observed_ts=observed_ts,
        )
    )
    return set_id + 1


def build_caregiver_oru(
    patient: Any,
    questionnaire_response: Mapping[str, Any],
    *,
    sending_application: str = "MEDILACRA",
    sending_facility: str = "CONNECTATHON",
    receiving_application: str = "",
    receiving_facility: str = "",
    control_id: str | None = None,
) -> str:
    """Project one caregiver QuestionnaireResponse into an HL7 v2.5 ORU^R01 message."""
    authored = str(questionnaire_response.get("authored") or datetime.now(timezone.utc).isoformat())
    authored_ts = _ts(authored)
    qr_id = str(questionnaire_response.get("id") or "caregiver-response")
    message_control_id = control_id or f"CG-{qr_id}"[:80]

    parts = [
        _msh(
            message_ts=authored_ts,
            control_id=message_control_id,
            sending_application=sending_application,
            sending_facility=sending_facility,
            receiving_application=receiving_application,
            receiving_facility=receiving_facility,
        ),
        _pid(patient),
        _obr(authored_ts),
    ]
    set_id = 1

    set_id = _append_answer_or_absent(
        parts,
        set_id,
        answer=first_answer(questionnaire_response, "sleep-hours"),
        question_code="sleep-hours-24h",
        question_display="Hours slept in past 24 hours",
        system=LOCAL_CODING_SYSTEM,
        value_type="NM",
        value_key="valueQuantity",
        units="h^hour^UCUM",
        observed_ts=authored_ts,
    )
    # Quantity answers contain a nested object; replace the just-rendered value with its scalar.
    if parts and parts[-1].startswith("OBX|") and "sleep-hours-24h^" in parts[-1]:
        answer = first_answer(questionnaire_response, "sleep-hours") or {}
        quantity = answer.get("valueQuantity") if isinstance(answer, Mapping) else None
        if isinstance(quantity, Mapping) and quantity.get("value") is not None:
            fields = parts[-1].split("|")
            fields[5] = hl7_escape(quantity.get("value"))
            parts[-1] = "|".join(fields)

    set_id = _append_answer_or_absent(
        parts,
        set_id,
        answer=first_answer(questionnaire_response, "pain-score"),
        question_code=PAIN_LOINC,
        question_display="Pain severity - 0-10 verbal numeric rating [Score] - Reported",
        system="LN",
        value_type="NM",
        value_key="valueInteger",
        observed_ts=authored_ts,
    )

    phq_codes: list[str] = []
    for link_id, loinc_code, display in (
        ("phq2-interest", PHQ2_QUESTION_1, "Little interest or pleasure in doing things"),
        ("phq2-depressed", PHQ2_QUESTION_2, "Feeling down, depressed, or hopeless"),
    ):
        answer = first_answer(questionnaire_response, link_id)
        reason = answer_absent_reason(answer)
        if reason:
            set_id = _append_absent_obx(
                parts,
                set_id,
                question_code=loinc_code,
                question_display=display,
                reason=reason,
                observed_ts=authored_ts,
            )
            continue
        coding = _answer_value(answer, "valueCoding")
        if isinstance(coding, Mapping) and coding.get("code"):
            code = str(coding["code"])
            phq_codes.append(code)
            value_display = str(coding.get("display") or PHQ_DISPLAY_BY_CODE.get(code) or "")
            parts.append(
                _obx(
                    set_id,
                    value_type="CWE",
                    code=loinc_code,
                    display=display,
                    system="LN",
                    value=f"{hl7_escape(code)}^{hl7_escape(value_display)}^LN",
                    observed_ts=authored_ts,
                )
            )
            set_id += 1

    if len(phq_codes) == 2 and all(code in PHQ_SCORE_BY_CODE for code in phq_codes):
        parts.append(
            _obx(
                set_id,
                value_type="NM",
                code=PHQ2_TOTAL,
                display="PHQ-2 total score",
                system="LN",
                value=sum(PHQ_SCORE_BY_CODE[code] for code in phq_codes),
                observed_ts=authored_ts,
            )
        )
        set_id += 1

    heart_answer = first_answer(questionnaire_response, "heart-rate")
    heart_reason = answer_absent_reason(heart_answer)
    if heart_reason:
        set_id = _append_absent_obx(
            parts,
            set_id,
            question_code=HEART_RATE_LOINC,
            question_display="Heart rate",
            reason=heart_reason,
            observed_ts=authored_ts,
        )
    else:
        quantity = _answer_value(heart_answer, "valueQuantity")
        if isinstance(quantity, Mapping) and quantity.get("value") is not None:
            parts.append(
                _obx(
                    set_id,
                    value_type="NM",
                    code=HEART_RATE_LOINC,
                    display="Heart rate",
                    system="LN",
                    value=hl7_escape(quantity.get("value")),
                    units="/min^beats/minute^UCUM",
                    observed_ts=authored_ts,
                )
            )
            set_id += 1

    medication_status = first_answer(questionnaire_response, "medication-status")
    medication_reason = answer_absent_reason(medication_status)
    if medication_reason:
        set_id = _append_absent_obx(
            parts,
            set_id,
            question_code="medication-status",
            question_display="Currently taking medications",
            reason=medication_reason,
            observed_ts=authored_ts,
        )
    else:
        medication_value = _answer_value(medication_status, "valueBoolean")
        if isinstance(medication_value, bool):
            code = "Y" if medication_value else "N"
            display = "Yes" if medication_value else "No"
            parts.append(
                _obx(
                    set_id,
                    value_type="CWE",
                    code="medication-status",
                    display="Currently taking medications",
                    system=LOCAL_CODING_SYSTEM,
                    value=f"{code}^{display}^HL70136",
                    observed_ts=authored_ts,
                )
            )
            set_id += 1

    if _answer_value(medication_status, "valueBoolean") is True:
        for med_index, group in enumerate(find_response_items(questionnaire_response, "medications"), start=1):
            sub_id = str(med_index)
            for link_id, display, value_key, value_type, units in (
                ("medication-name", "Reported medication name", "valueString", "TX", ""),
                ("medication-dose-value", "Reported medication dose", "valueDecimal", "NM", ""),
                ("medication-dose-unit", "Reported medication dose unit", "valueString", "ST", ""),
                ("medication-route", "Reported medication route", "valueString", "ST", ""),
                ("medication-frequency", "Reported medication frequency", "valueString", "ST", ""),
            ):
                answer = _child_answer(group, link_id)
                reason = answer_absent_reason(answer)
                if reason:
                    set_id = _append_absent_obx(
                        parts,
                        set_id,
                        question_code=link_id,
                        question_display=display,
                        reason=reason,
                        observed_ts=authored_ts,
                        sub_id=sub_id,
                    )
                    continue
                value = _answer_value(answer, value_key)
                if value is None or value == "":
                    continue
                parts.append(
                    _obx(
                        set_id,
                        value_type=value_type,
                        code=link_id,
                        display=display,
                        system=LOCAL_CODING_SYSTEM,
                        sub_id=sub_id,
                        value=hl7_escape(value),
                        units=units,
                        observed_ts=authored_ts,
                    )
                )
                set_id += 1

    for link_id, display in (
        ("feeling-today", "How are you feeling today?"),
        ("life-today", "What's going on in your life today?"),
    ):
        answer = first_answer(questionnaire_response, link_id)
        reason = answer_absent_reason(answer)
        if reason:
            set_id = _append_absent_obx(
                parts,
                set_id,
                question_code=link_id,
                question_display=display,
                reason=reason,
                observed_ts=authored_ts,
            )
            continue
        value = _answer_value(answer, "valueString")
        if value not in (None, ""):
            parts.append(
                _obx(
                    set_id,
                    value_type="TX",
                    code=link_id,
                    display=display,
                    system=LOCAL_CODING_SYSTEM,
                    value=hl7_escape(value),
                    observed_ts=authored_ts,
                )
            )
            set_id += 1

    return "\r".join(parts) + "\r"


__all__ = ["HL7_VERSION", "LOCAL_CODING_SYSTEM", "build_caregiver_oru"]

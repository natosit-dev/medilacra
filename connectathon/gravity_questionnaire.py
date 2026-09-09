from __future__ import annotations

from typing import Any, Mapping, Sequence


QUESTIONNAIRE_ID = "caregiver-health-baseline"
QUESTIONNAIRE_VERSION = "0.2"
QUESTIONNAIRE_URL = "https://medilacra.dev/fhir/Questionnaire/caregiver-health-baseline"
MEDILACRA_CODE_SYSTEM = "https://medilacra.dev/fhir/CodeSystem/caregiver-health"
LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"
RXNORM_SYSTEM = "http://www.nlm.nih.gov/research/umls/rxnorm"
DATA_ABSENT_REASON_URL = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"

PAIN_LOINC = "72514-3"
PHQ2_QUESTION_1 = "44250-9"
PHQ2_QUESTION_2 = "44255-8"
PHQ2_TOTAL = "55757-9"
HEART_RATE_LOINC = "8867-4"

PHQ_CHOICES = (
    ("LA6568-5", "Not at all", 0),
    ("LA6569-3", "Several days", 1),
    ("LA6570-1", "More than half the days", 2),
    ("LA6571-9", "Nearly every day", 3),
)
PHQ_SCORE_BY_CODE = {code: score for code, _display, score in PHQ_CHOICES}
PHQ_DISPLAY_BY_CODE = {code: display for code, display, _score in PHQ_CHOICES}


def loinc_coding(code: str, display: str) -> dict[str, str]:
    return {"system": LOINC_SYSTEM, "code": code, "display": display}


def local_coding(code: str, display: str) -> dict[str, str]:
    return {"system": MEDILACRA_CODE_SYSTEM, "code": code, "display": display}


def data_absent_reason(reason: str) -> dict[str, str]:
    """Return the standard FHIR data-absent-reason extension."""
    return {"url": DATA_ABSENT_REASON_URL, "valueCode": reason}


def _question_item(
    link_id: str,
    text: str,
    item_type: str,
    *,
    coding: Mapping[str, Any] | None = None,
    answer_options: Sequence[Mapping[str, Any]] | None = None,
    repeats: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "linkId": link_id,
        "text": text,
        "type": item_type,
        "required": False,
        "repeats": repeats,
    }
    if coding:
        item["code"] = [dict(coding)]
    if answer_options:
        item["answerOption"] = [dict(option) for option in answer_options]
    return item


def build_questionnaire() -> dict[str, Any]:
    """Build the caregiver baseline as a standard FHIR R4 Questionnaire."""
    phq_options = [
        {
            "valueCoding": {
                "system": LOINC_SYSTEM,
                "code": code,
                "display": display,
            }
        }
        for code, display, _score in PHQ_CHOICES
    ]

    medication_group = {
        "linkId": "medications",
        "text": "Medication",
        "type": "group",
        "required": False,
        "repeats": True,
        "enableWhen": [
            {
                "question": "medication-status",
                "operator": "=",
                "answerBoolean": True,
            }
        ],
        "item": [
            _question_item("medication-name", "Medication name", "string"),
            _question_item("medication-dose-value", "Dose", "decimal"),
            _question_item("medication-dose-unit", "Dose unit", "string"),
            _question_item("medication-route", "Route", "string"),
            _question_item("medication-frequency", "Frequency", "string"),
        ],
    }

    return {
        "resourceType": "Questionnaire",
        "id": QUESTIONNAIRE_ID,
        "url": QUESTIONNAIRE_URL,
        "version": QUESTIONNAIRE_VERSION,
        "name": "CaregiverHealthBaseline",
        "title": "MediLacra Caregiver Health Baseline",
        "status": "active",
        "experimental": True,
        "date": "2026-09-09",
        "publisher": "MediLacra",
        "description": (
            "Baseline caregiver-health questionnaire for Gravity/SDC materialization, "
            "semantic-preservation testing, and optional free-text lived-experience capture."
        ),
        "subjectType": ["Patient"],
        "item": [
            _question_item(
                "sleep-hours",
                "About how many hours did you sleep in the past 24 hours?",
                "quantity",
                coding=local_coding("sleep-hours-24h", "Hours slept in past 24 hours"),
            ),
            _question_item(
                "pain-score",
                (
                    "On a scale from 0 to 10, where 0 means no pain and 10 means the worst pain "
                    "imaginable, how would you rate your pain right now?"
                ),
                "integer",
                coding=loinc_coding(
                    PAIN_LOINC,
                    "Pain severity - 0-10 verbal numeric rating [Score] - Reported",
                ),
            ),
            {
                "linkId": "phq2",
                "text": "Over the last 2 weeks, how often have you been bothered by the following problems?",
                "type": "group",
                "required": False,
                "repeats": False,
                "code": [loinc_coding(PHQ2_TOTAL, "PHQ-2 total score")],
                "item": [
                    _question_item(
                        "phq2-interest",
                        "Little interest or pleasure in doing things",
                        "choice",
                        coding=loinc_coding(PHQ2_QUESTION_1, "Little interest or pleasure in doing things"),
                        answer_options=phq_options,
                    ),
                    _question_item(
                        "phq2-depressed",
                        "Feeling down, depressed, or hopeless",
                        "choice",
                        coding=loinc_coding(PHQ2_QUESTION_2, "Feeling down, depressed, or hopeless"),
                        answer_options=phq_options,
                    ),
                ],
            },
            _question_item(
                "heart-rate",
                "What is your current heart rate?",
                "quantity",
                coding=loinc_coding(HEART_RATE_LOINC, "Heart rate"),
            ),
            _question_item(
                "medication-status",
                "Are you currently taking any medications?",
                "boolean",
            ),
            medication_group,
            _question_item(
                "feeling-today",
                "How are you feeling today?",
                "text",
                coding=local_coding("feeling-today", "How are you feeling today?"),
            ),
            _question_item(
                "life-today",
                "What's going on in your life today?",
                "text",
                coding=local_coding("life-today", "What's going on in your life today?"),
            ),
        ],
    }

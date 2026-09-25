"""HL7 v2.5 ORU^R01 projection of the MediLacra SDOH QuestionnaireResponse."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from connectathon.gravity_hl7v2 import (
    HL7_VERSION, LOCAL_CODING_SYSTEM, _append_absent_obx, _msh, _obx,
    _pid, _segment, _ts,
)
from connectathon.gravity_response import answer_absent_reason
from connectathon.gravity_sdoh_questionnaire import SPECS
from connectathon.gravity_sdoh_response import answers_for
from connectathon.gravity_sdoh_terminology import ALL_CODES, LOINC
from hl7_demo.utils import hl7_escape

PANEL_CODE="sdoh-baseline"
PANEL_DISPLAY="MediLacra SDOH Baseline"

def build_sdoh_oru(
    patient: Any,
    questionnaire_response: Mapping[str,Any],
    *,
    sending_application: str="MEDILACRA",
    sending_facility: str="CONNECTATHON",
    receiving_application: str="",
    receiving_facility: str="",
    control_id: str | None=None,
) -> str:
    authored=str(questionnaire_response.get("authored") or datetime.now(timezone.utc).isoformat())
    authored_ts=_ts(authored)
    qr_id=str(questionnaire_response.get("id") or "sdoh-response")
    parts=[
        _msh(
            message_ts=authored_ts,
            control_id=control_id or f"SD-{qr_id}"[:80],
            sending_application=sending_application,
            sending_facility=sending_facility,
            receiving_application=receiving_application,
            receiving_facility=receiving_facility,
        ),
        _pid(patient),
        _segment("OBR",{1:"1",4:f"{PANEL_CODE}^{PANEL_DISPLAY}^{LOCAL_CODING_SYSTEM}",7:authored_ts,25:"F"},last_field=25),
    ]
    set_id=1
    for question_code in ALL_CODES:
        text=SPECS[question_code][0]
        answers=answers_for(questionnaire_response,question_code)
        for index,answer in enumerate(answers,start=1):
            reason=answer_absent_reason(answer)
            sub_id=str(index) if len(answers)>1 else ""
            if reason:
                set_id=_append_absent_obx(
                    parts,set_id,question_code=question_code,
                    question_display=text,reason=reason,observed_ts=authored_ts,
                    sub_id=sub_id,
                )
                continue
            coding=answer.get("valueCoding")
            if not isinstance(coding,Mapping) or not coding.get("code"):
                continue
            parts.append(_obx(
                set_id,
                value_type="CWE",
                code=question_code,
                display=text,
                system="LN",
                sub_id=sub_id,
                value=f"{hl7_escape(coding.get('code'))}^{hl7_escape(coding.get('display') or '')}^LN",
                observed_ts=authored_ts,
            ))
            set_id+=1
    return "\\r".join(parts)+"\\r"

__all__=["HL7_VERSION","build_sdoh_oru"]

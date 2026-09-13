from __future__ import annotations

from datetime import datetime

from hl7_demo.segments import seg_msh, seg_pid, seg_pv1
from hl7_demo.utils import hl7_escape

from .binding import ClinicalBinding


def _hl7_ts(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.strftime("%Y%m%d%H%M%S")


def _ce(code: str, display: str, system: str) -> str:
    return "^".join([
        hl7_escape(str(code)),
        hl7_escape(str(display)),
        hl7_escape(str(system)),
    ])


def _obr(binding: ClinicalBinding) -> str:
    fields = [""] * 17
    fields[1] = "1"
    fields[2] = str(binding.encounter.placer_order_number)
    fields[3] = str(binding.encounter.filler_order_number)
    fields[4] = _ce(binding.observation_code, binding.observation_display, binding.coding_system)
    fields[7] = _hl7_ts(binding.validated_measurement.observed_at)
    return "OBR|" + "|".join(fields[1:])


def _measurement_obx(binding: ClinicalBinding, *, set_id: int = 1) -> str:
    fields = [""] * 16
    fields[1] = str(set_id)
    fields[2] = "NM"
    fields[3] = _ce(binding.observation_code, binding.observation_display, binding.coding_system)
    fields[5] = f"{binding.value:.3f}".rstrip("0").rstrip(".")
    fields[6] = binding.unit
    fields[11] = "F"
    fields[14] = _hl7_ts(binding.validated_measurement.observed_at)
    fields[15] = "MEDILACRAHS^REALITY_INTERFACE"
    return "OBX|" + "|".join(fields[1:])


def _source_obx(source_filename: str, source_location: str, *, set_id: int = 2) -> str:
    fields = [""] * 16
    fields[1] = str(set_id)
    fields[2] = "ST"
    fields[3] = _ce("SOURCE-WAV", "Source WAV recording", "99MEDILACRA")
    fields[5] = hl7_escape(f"filename={source_filename}; location={source_location}")
    fields[11] = "F"
    fields[15] = "MEDILACRAHS^REALITY_INTERFACE"
    return "OBX|" + "|".join(fields[1:])


def build_reality_oru(
    binding: ClinicalBinding,
    *,
    source_filename: str,
    source_location: str,
) -> str:
    """Project a validated Reality Interface measurement into ORU^R01."""

    parts = [
        seg_msh("ORU^R01"),
        seg_pid(binding.patient),
        seg_pv1(binding.encounter),
        _obr(binding),
        _measurement_obx(binding),
        _source_obx(source_filename, source_location),
    ]

    notes = binding.validated_measurement.human_validation.notes
    if notes:
        parts.append(f"NTE|1||{hl7_escape(notes)}")

    return "\r".join(parts)

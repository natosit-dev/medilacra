import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from payer.models import EligibilityOutcome
from x12.scenarios import (
    build_exchange_zip,
    build_scenario,
    list_scenarios,
    run_scenario,
)


RUN_AT = datetime(2026, 10, 6, 9, 30, 45)


def test_ui_scenario_inventory_contains_first_two_x12_scenarios():
    scenarios = dict(list_scenarios())

    assert scenarios == {
        "clean_active": "Clean Active Eligibility",
        "identity_divergence": "Identity Divergence — Payer Name Differs",
    }


def test_clean_scenario_keeps_clinical_and_payer_identity_aligned():
    scenario = build_scenario("clean_active")

    assert scenario.clinical_patient.patient_name == "KELLEY^DEVIN"
    assert scenario.payer_member.first_name == "DEVIN"
    assert scenario.payer_member.last_name == "KELLEY"
    assert scenario.clinical_coverage.member_id == scenario.payer_member.member_id


def test_divergence_scenario_separates_clinical_and_payer_last_name():
    scenario = build_scenario("identity_divergence")

    assert scenario.clinical_patient.patient_name == "KELLEY^DEVIN"
    assert scenario.payer_member.last_name == "KELLY"
    assert scenario.clinical_coverage.member_id == scenario.payer_member.member_id


def test_clean_ui_workflow_generates_full_active_270_and_271():
    result = run_scenario(
        "clean_active",
        service_date="2026-10-06",
        run_at=RUN_AT,
    )

    assert result.eligibility_response.outcome == EligibilityOutcome.ACTIVE
    assert result.match_result.outcome.value == "MATCHED"
    assert result.match_result.conflicting_fields == ()

    assert result.x270.startswith("ISA*00*")
    assert "ST*270*" in result.x270
    assert result.x270.endswith("IEA*1*006093045~")

    assert result.x271.startswith("ISA*00*")
    assert "ST*271*" in result.x271
    assert result.x271.endswith("IEA*1*006093046~")

    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" in result.x270
    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" in result.x271


def test_divergence_ui_workflow_preserves_institutional_authorship():
    result = run_scenario(
        "identity_divergence",
        service_date="2026-10-06",
        run_at=RUN_AT,
    )

    assert result.eligibility_response.outcome == EligibilityOutcome.ACTIVE
    assert result.match_result.outcome.value == "MATCHED"
    assert result.match_result.conflicting_fields == ("last_name",)

    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" in result.x270
    assert "NM1*IL*1*KELLY*DEVIN****MI*MEM-01374522~" in result.x271
    assert "NM1*IL*1*KELLEY*DEVIN****MI*MEM-01374522~" not in result.x271


def test_download_filenames_use_exchange_datetime_stamp():
    result = run_scenario(
        "clean_active",
        service_date="2026-10-06",
        run_at=RUN_AT,
    )

    assert result.timestamp == "20261006_093045"
    assert result.x270_filename == "medilacra_270_20261006_093045.x12"
    assert result.x271_filename == "medilacra_271_20261006_093045.x12"
    assert (
        result.zip_filename
        == "medilacra_x12_exchange_20261006_093045.zip"
    )
    assert (
        result.summary_filename
        == "exchange_summary_20261006_093045.json"
    )


def test_exchange_zip_contains_stamped_messages_and_summary():
    result = run_scenario(
        "identity_divergence",
        service_date="2026-10-06",
        run_at=RUN_AT,
    )

    payload = build_exchange_zip(result)

    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names = set(archive.namelist())

        assert names == {
            result.x270_filename,
            result.x271_filename,
            result.summary_filename,
        }

        assert archive.read(result.x270_filename).decode("utf-8") == result.x270
        assert archive.read(result.x271_filename).decode("utf-8") == result.x271

        summary = json.loads(
            archive.read(result.summary_filename).decode("utf-8")
        )

    assert summary["scenario"] == "identity_divergence"
    assert summary["member_match"] == "MATCHED"
    assert summary["eligibility_outcome"] == "ACTIVE"
    assert summary["conflicting_fields"] == ["last_name"]
    assert summary["clinical_identity"]["last_name"] == "KELLEY"
    assert summary["payer_identity"]["last_name"] == "KELLY"


def test_streamlit_page_compiles_and_uses_session_state_for_artifacts():
    page = Path("pages/8_X12_Eligibility.py")
    source = page.read_text(encoding="utf-8")

    compile(source, str(page), "exec")

    assert 'st.session_state["x12_eligibility_result"]' in source
    assert "Download 270" in source
    assert "Download 271" in source
    assert "Download Exchange ZIP" in source

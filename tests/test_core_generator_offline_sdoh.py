from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import hl7_demo.messages as messages
import hl7_demo.pipeline as pipeline
from hl7_demo.generators import gen_encounter, gen_patient


def _unexpected_lookup(name):
    def fail(*_args, **_kwargs):
        raise AssertionError(
            f"External SDOH lookup should be skipped while offline: {name}"
        )

    return fail


def test_build_adt_offline_master_switch_skips_all_sdoh_lookups(monkeypatch):
    patient = gen_patient()
    encounter = gen_encounter(patient.patient_id)

    monkeypatch.setattr(
        messages,
        "get_air_quality_by_zip",
        _unexpected_lookup("AirNow"),
    )
    monkeypatch.setattr(
        messages,
        "get_poverty_pct_by_zcta",
        _unexpected_lookup("Census poverty"),
    )
    monkeypatch.setattr(
        messages,
        "build_obx_places_obesity",
        _unexpected_lookup("PLACES"),
    )
    monkeypatch.setattr(
        messages,
        "build_obx_unemployment",
        _unexpected_lookup("BLS unemployment"),
    )

    rendered = messages.build_adt(
        patient,
        encounter,
        include_sdoh=False,
        # Deliberately set every subordinate flag true. The master switch
        # must still guarantee an offline build.
        add_air_obx=True,
        add_poverty_obx=True,
        add_places_obesity_obx=True,
        add_unemployment_obx=True,
    )

    assert rendered.startswith("MSH|")
    assert "PID|" in rendered
    assert "PV1|" in rendered


def test_run_pipeline_is_offline_by_default_and_passes_master_switch(
    tmp_path,
    monkeypatch,
):
    captured = {}

    patient = SimpleNamespace(
        patient_id="PAT-OFFLINE-001",
        coverage_profile=None,
    )
    coverage = SimpleNamespace(
        coverage_profile_id="COV-OFFLINE-001",
        payer_id="AETNA",
        employer_id="EMP-001",
        plan_id="STANDARD_PPO",
    )
    encounter = SimpleNamespace(
        encounter_id="ENC-OFFLINE-001",
    )
    transaction = SimpleNamespace(
        transaction_id="TX-OFFLINE-001",
    )
    observation = SimpleNamespace(
        observation_id="OBS-OFFLINE-001",
    )

    monkeypatch.setattr(pipeline, "gen_patient", lambda: patient)
    monkeypatch.setattr(
        pipeline,
        "assign_coverage_profile",
        lambda p, seed=None: coverage,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_encounter",
        lambda patient_id, profile=None: encounter,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_transaction",
        lambda encounter_id, coverage_profile=None: transaction,
    )
    monkeypatch.setattr(
        pipeline,
        "gen_observation",
        lambda enc, report_row: observation,
    )
    monkeypatch.setattr(
        pipeline,
        "load_reports",
        lambda _glob: pd.DataFrame([{"stub": "row"}]),
    )

    def fake_adt(*_args, **kwargs):
        captured.update(kwargs)
        return "MSH|^~\\&|TEST|MEDILACRA|TEST|STAGE|20261007100000||ADT^A01|CTRL1|P|2.5"

    monkeypatch.setattr(pipeline, "build_adt", fake_adt)
    monkeypatch.setattr(
        pipeline,
        "build_oru",
        lambda *_args, **_kwargs: (
            "MSH|^~\\&|TEST|MEDILACRA|TEST|STAGE|20261007100000||ORU^R01|CTRL2|P|2.5"
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "build_dft",
        lambda *_args, **_kwargs: (
            "MSH|^~\\&|TEST|MEDILACRA|TEST|STAGE|20261007100000||DFT^P03|CTRL3|P|2.5"
        ),
    )

    pipeline.run_pipeline(
        n_patients=1,
        report_glob="unused/*.csv",
        seed=42,
        per_encounter=True,
        bulk=False,
        out_dir=str(tmp_path),
        miles=75,
        include_labs=False,
        include_x12=False,
        persist="none",
    )

    assert captured["include_sdoh"] is False
    assert captured["add_air_obx"] is False
    assert captured["add_poverty_obx"] is False
    assert captured["add_places_obesity_obx"] is False
    assert captured["add_unemployment_obx"] is False

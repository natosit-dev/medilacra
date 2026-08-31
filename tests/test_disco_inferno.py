import random
from random import Random

import duckdb
import pandas as pd
import pandas.testing as pdt
from faker import Faker

from experiments.disco_inferno.compare import compare_models, control_is_zero
from experiments.disco_inferno.corruptions import control, drop_identifier, duplicate_record, null_field
from experiments.disco_inferno.exports import _build_adt_for_export, write_source_duckdb
from experiments.disco_inferno.materialize import save_model
from hl7_demo import messages as hl7_messages
from hl7_demo.generators import gen_encounter, gen_patient


def sample_model():
    return {
        "observations": pd.DataFrame(
            {
                "encounter_id": ["E1", "E1", "E2", "E2"],
                "observation_id": ["O1", "O2", "O3", "O4"],
                "observation_text": ["a", "b", "c", "d"],
            }
        ),
        "transactions": pd.DataFrame(
            {
                "transaction_id": ["T1", "T2", "T3", "T4"],
                "encounter_id": ["E1", "E1", "E2", "E2"],
                "transaction_amount": [1.0, 2.0, 3.0, 4.0],
            }
        ),
    }


def test_control_is_zero_and_does_not_alias():
    source = sample_model()
    result = control(source)
    metrics = compare_models(source, result.model, result.manifest)
    assert control_is_zero(metrics)
    assert result.model["observations"] is not source["observations"]


def test_charon_drops_only_requested_identifier_without_mutating_truth():
    source = sample_model()
    before = source["observations"].copy(deep=True)
    result = drop_identifier(source, "observations", "encounter_id", identity_field="observation_id")
    assert "encounter_id" not in result.model["observations"].columns
    assert list(result.model["observations"].columns) == ["observation_id", "observation_text"]
    pdt.assert_frame_equal(source["observations"], before)
    assert result.manifest["references_removed"] == 4


def test_null_field_is_seeded_exact_and_non_destructive():
    source = sample_model()
    a = null_field(source, "observations", "observation_text", 0.5, Random(666), identity_field="observation_id")
    b = null_field(source, "observations", "observation_text", 0.5, Random(666), identity_field="observation_id")
    assert a.manifest["selected_positions"] == b.manifest["selected_positions"]
    assert a.model["observations"]["observation_text"].isna().sum() == 2
    assert source["observations"]["observation_text"].isna().sum() == 0


def test_cerberus_duplicates_exact_seeded_fraction_and_preserves_truth():
    source = sample_model()
    before = source["transactions"].copy(deep=True)
    result = duplicate_record(source, "transactions", 0.5, Random(666), identity_field="transaction_id")
    assert len(result.model["transactions"]) == 6
    assert result.manifest["copies_introduced"] == 2
    pdt.assert_frame_equal(result.model["transactions"].iloc[:4].reset_index(drop=True), before)
    pdt.assert_frame_equal(source["transactions"], before)


def test_different_inferno_seed_changes_victims_not_truth():
    source = sample_model()
    before = source["observations"].copy(deep=True)
    a = null_field(source, "observations", "observation_text", 0.5, Random(666), identity_field="observation_id")
    b = null_field(source, "observations", "observation_text", 0.5, Random(667), identity_field="observation_id")
    assert a.manifest["selected_positions"] != b.manifest["selected_positions"]
    pdt.assert_frame_equal(source["observations"], before)


def test_source_reality_duckdb_contains_beatrice_tables(tmp_path):
    source = sample_model()
    db_path = tmp_path / "source_reality_20260830T211031-0400.duckdb"
    write_source_duckdb(source, db_path)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 4
        assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 4
        assert con.execute(
            "SELECT observation_text FROM observations WHERE observation_id = 'O1'"
        ).fetchone()[0] == "a"
    finally:
        con.close()


def test_save_model_can_datetime_stamp_csv_names(tmp_path):
    source = sample_model()
    stamp = "20260830T211031-0400"
    save_model(source, tmp_path, file_suffix=stamp)
    assert (tmp_path / f"observations_{stamp}.csv").exists()
    assert (tmp_path / f"transactions_{stamp}.csv").exists()


def test_fast_hl7_export_skips_sdoh_lookups_without_changing_shared_builder(monkeypatch):
    random.seed(42)
    Faker.seed(42)
    patient = gen_patient()
    encounter = gen_encounter(patient.patient_id)

    original_build_adt = hl7_messages.build_adt

    def fail_lookup(*_args, **_kwargs):
        raise AssertionError("SDOH lookup was called while include_sdoh=False")

    monkeypatch.setattr(hl7_messages, "get_air_quality_by_zip", fail_lookup)
    monkeypatch.setattr(hl7_messages, "get_poverty_pct_by_zcta", fail_lookup)

    message = _build_adt_for_export(
        patient,
        encounter,
        None,
        None,
        include_sdoh=False,
    )

    assert message.startswith("MSH|")
    assert hl7_messages.build_adt is original_build_adt

from random import Random

import pandas as pd
import pandas.testing as pdt

from experiments.disco_inferno.compare import compare_models, control_is_zero
from experiments.disco_inferno.corruptions import control, drop_identifier, duplicate_record, null_field


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

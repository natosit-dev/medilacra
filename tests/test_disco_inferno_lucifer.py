"""Lucifer must produce believable false conclusions, not merely broken rows."""
import pandas as pd
import pandas.testing as pdt
import pytest

from experiments.disco_inferno.lucifer import lucifer


def patients():
    return pd.DataFrame({"patient_id": ["P1", "P2", "P3"]})


def test_lucifer_betrays_truth_while_ordinary_checks_pass():
    baseline = patients()
    result = lucifer(baseline, inferno_seed=666)
    for name, evidence in result.evidence.items():
        case = result.manifest["cases"][name]
        assert all(case["consumer_visible_checks"].values())
        assert case["source_rows"] == case["evidence_rows"] == 2
        assert case["false_conclusion"] is True
        assert case["source_claim_unauthorized_event_occurred"] != case["evidence_claim_unauthorized_event_occurred"]
        assert list(evidence.columns) == list(result.source_truth.columns)
    assert not result.manifest["cases"]["phantom_violation"]["source_claim_unauthorized_event_occurred"]
    assert result.manifest["cases"]["phantom_violation"]["evidence_claim_unauthorized_event_occurred"]
    assert result.manifest["cases"]["concealed_violation"]["source_claim_unauthorized_event_occurred"]
    assert not result.manifest["cases"]["concealed_violation"]["evidence_claim_unauthorized_event_occurred"]
    pdt.assert_frame_equal(baseline, patients())


def test_seeds_reproduce_damage_but_not_change_source_truth():
    a = lucifer(patients(), inferno_seed=666)
    b = lucifer(patients(), inferno_seed=666)
    c = lucifer(patients(), inferno_seed=667)
    pdt.assert_frame_equal(a.source_truth, b.source_truth)
    pdt.assert_frame_equal(a.source_truth, c.source_truth)
    for name in a.evidence:
        pdt.assert_frame_equal(a.evidence[name], b.evidence[name])
    assert (
        a.manifest["cases"]["phantom_violation"]["target_event_id"]
        != c.manifest["cases"]["phantom_violation"]["target_event_id"]
    )


def test_lucifer_accepts_single_patient_but_rejects_missing_source():
    one = lucifer(pd.DataFrame({"patient_id": ["P1"]}))
    assert all(one.manifest["cases"][x]["false_conclusion"] for x in one.evidence)
    with pytest.raises(ValueError):
        lucifer(pd.DataFrame({"something_else": ["P1"]}))
    with pytest.raises(ValueError):
        lucifer(pd.DataFrame({"patient_id": []}))

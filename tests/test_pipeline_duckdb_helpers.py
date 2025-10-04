import sys
from types import ModuleType, SimpleNamespace


# Provide lightweight stubs for optional modules that require heavy dependencies.
hl7_demo_pkg = ModuleType("hl7_demo")
hl7_demo_pkg.__path__ = []  # mark as package
sys.modules.setdefault("hl7_demo", hl7_demo_pkg)

generators = ModuleType("hl7_demo.generators")
generators.gen_patient = lambda *args, **kwargs: None
generators.gen_encounter = lambda *args, **kwargs: None
generators.gen_transaction = lambda *args, **kwargs: None
generators.gen_observation = lambda *args, **kwargs: None
sys.modules.setdefault("hl7_demo.generators", generators)
setattr(hl7_demo_pkg, "generators", generators)

reports = ModuleType("hl7_demo.reports")
reports.load_reports = lambda *args, **kwargs: None
sys.modules.setdefault("hl7_demo.reports", reports)
setattr(hl7_demo_pkg, "reports", reports)

messages = ModuleType("hl7_demo.messages")
messages.build_adt = lambda *args, **kwargs: ""
messages.build_oru = lambda *args, **kwargs: ""
messages.build_dft = lambda *args, **kwargs: ""
sys.modules.setdefault("hl7_demo.messages", messages)
setattr(hl7_demo_pkg, "messages", messages)

from pipeline_duckdb import _derive_account_number, _encounter_row, _observation_row, _patient_row


def test_derive_account_number_is_deterministic():
    acct1 = _derive_account_number("ENC001")
    acct2 = _derive_account_number("ENC001")
    acct3 = _derive_account_number("ENC002")

    assert acct1 == acct2
    assert acct1.startswith("ACCT")
    assert acct1 != acct3


def test_patient_row_sets_mrn_when_missing():
    patient = {"patient_id": "PAT1", "patient_name": "Jane"}
    result = _patient_row(patient)
    assert result["mrn"] == "PAT1"

    obj = SimpleNamespace(patient_id="PAT2", mrn="MRN123")
    result_obj = _patient_row(obj)
    assert result_obj["mrn"] == "MRN123"


def test_encounter_row_adds_account_number_when_missing():
    encounter = {"encounter_id": "ENC1", "patient_id": "PAT1"}
    result = _encounter_row(encounter)
    assert "account_number" in result
    assert result["account_number"].startswith("ACCT")


def test_observation_row_inherits_order_numbers():
    observation = {"encounter_id": "ENC1", "observation_id": "OBS1"}
    encounter_row = {"placer_order_number": "PO1", "filler_order_number": "FO1"}
    result = _observation_row(observation, encounter_row)
    assert result["placer_order_number"] == "PO1"
    assert result["filler_order_number"] == "FO1"
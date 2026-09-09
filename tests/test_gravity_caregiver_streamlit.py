from __future__ import annotations

from pathlib import Path


def _seed_patient(db_path: str) -> None:
    from storage_duckdb_entities import init_db, upsert_patient

    init_db(db_path)
    upsert_patient(
        {
            "patient_id": "PAT-UI-001",
            "mrn": "MRN-UI-001",
            "patient_name": "CAREGIVER, CASEY",
            "date_of_birth": "1982-03-14",
            "sex": "F",
            "race": "",
            "ssn": "",
            "phone": "555-0100",
            "address": "1 Test Way",
            "city": "Lowell",
            "state": "MA",
            "zip": "01852",
        },
        db_path=db_path,
    )


def test_gravity_caregiver_page_renders_with_existing_synthetic_patient(tmp_path, monkeypatch):
    db_path = str(tmp_path / "gravity-ui.duckdb")
    monkeypatch.setenv("MEDILACRA_DB_PATH", db_path)
    _seed_patient(db_path)

    from streamlit.testing.v1 import AppTest

    page = Path(__file__).resolve().parents[1] / "pages" / "10_Gravity_Caregiver_Health.py"
    app = AppTest.from_file(str(page), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "Gravity — Caregiver Health Baseline"
    assert any(button.label == "Submit assessment" for button in app.button)
    assert any(selectbox.label == "Patient" for selectbox in app.selectbox)


def test_decline_button_survives_streamlit_rerun_without_duckdb_configuration_error(
    tmp_path,
    monkeypatch,
):
    db_path = str(tmp_path / "gravity-ui-decline.duckdb")
    monkeypatch.setenv("MEDILACRA_DB_PATH", db_path)
    _seed_patient(db_path)

    from streamlit.testing.v1 import AppTest

    page = Path(__file__).resolve().parents[1] / "pages" / "10_Gravity_Caregiver_Health.py"
    app = AppTest.from_file(str(page), default_timeout=10).run()
    assert not app.exception

    decline = next(button for button in app.button if button.label == "Decline")
    app = decline.click().run()

    assert not app.exception
    assert any(button.label == "Answer instead" for button in app.button)
    assert any("asked-declined" in caption.value for caption in app.caption)

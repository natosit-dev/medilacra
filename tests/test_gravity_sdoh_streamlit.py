from __future__ import annotations

from pathlib import Path

def _seed_patient(db_path: str) -> None:
    from storage_duckdb_entities import init_db, upsert_patient
    init_db(db_path)
    upsert_patient(
        {
            "patient_id":"PAT-SDOH-UI-001","mrn":"MRN-SDOH-UI-001",
            "patient_name":"PATIENT, SAM","date_of_birth":"1988-04-05","sex":"F",
            "race":"","ssn":"","phone":"555-0101","address":"2 Test Way",
            "city":"Lowell","state":"MA","zip":"01852",
        },
        db_path=db_path,
    )

def _page_path() -> Path:
    return Path(__file__).resolve().parents[1]/"pages"/"11_Gravity_SDOH.py"

def test_sdoh_page_renders_with_existing_synthetic_patient(tmp_path,monkeypatch):
    db_path=str(tmp_path/"sdoh-ui.duckdb")
    monkeypatch.setenv("MEDILACRA_DB_PATH",db_path)
    _seed_patient(db_path)

    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(_page_path()),default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value=="Gravity — SDOH Baseline"
    assert any(button.label=="Reset assessment" for button in app.button)
    assert any(button.label=="Submit assessment" for button in app.button)
    assert any(selectbox.label=="Patient" for selectbox in app.selectbox)
    assert len(app.multiselect)==2

def test_sdoh_decline_survives_rerun(tmp_path,monkeypatch):
    db_path=str(tmp_path/"sdoh-ui-decline.duckdb")
    monkeypatch.setenv("MEDILACRA_DB_PATH",db_path)
    _seed_patient(db_path)

    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(_page_path()),default_timeout=10).run()
    assert not app.exception

    decline=next(button for button in app.button if button.label=="Decline")
    app=decline.click().run()
    assert not app.exception
    assert any(button.label=="Answer instead" for button in app.button)
    assert any("asked-declined" in caption.value for caption in app.caption)

def test_sdoh_reset_clears_decline_state(tmp_path,monkeypatch):
    db_path=str(tmp_path/"sdoh-ui-reset.duckdb")
    monkeypatch.setenv("MEDILACRA_DB_PATH",db_path)
    _seed_patient(db_path)

    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(_page_path()),default_timeout=10).run()
    app=next(button for button in app.button if button.label=="Decline").click().run()
    assert any(button.label=="Answer instead" for button in app.button)

    app=next(button for button in app.button if button.label=="Reset assessment").click().run()
    assert not app.exception
    assert not any(button.label=="Answer instead" for button in app.button)

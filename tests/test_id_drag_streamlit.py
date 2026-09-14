from __future__ import annotations

from pathlib import Path


def _seed_patient(db_path: str) -> None:
    from storage_duckdb_entities import init_db, upsert_patient

    init_db(db_path)
    upsert_patient(
        {
            "patient_id": "PAT-IDDRAG-UI-001",
            "mrn": "MRN-IDDRAG-UI-001",
            "patient_name": "PUBLIC, PAT",
            "date_of_birth": "1980-01-02",
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


def _page_path() -> Path:
    return Path(__file__).resolve().parents[1] / "pages" / "11_ID_DRAG.py"


def test_id_drag_page_renders_with_existing_synthetic_patient(tmp_path, monkeypatch):
    db_path = str(tmp_path / "id-drag-ui.duckdb")
    monkeypatch.setenv("MEDILACRA_DB_PATH", db_path)
    _seed_patient(db_path)

    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(_page_path()), default_timeout=10).run()

    assert not app.exception
    assert app.title[0].value == "ID DRAG"
    assert any(
        "Identity Resolution Doesn't Require A Gun" in caption.value
        for caption in app.caption
    )
    assert any(selectbox.label == "Patient" for selectbox in app.selectbox)
    assert any(
        radio.label == "Does this hand belong to the human?"
        for radio in app.radio
    )

    create_button = next(
        button for button in app.button if button.label == "Create ID DRAG artifact"
    )
    assert create_button.disabled is True


def test_id_drag_page_source_keeps_human_gate_and_image_scope_explicit():
    source = _page_path().read_text(encoding="utf-8")

    assert 'type=["jpg", "jpeg", "png"]' in source
    assert '"Does this hand belong to the human?"' in source
    assert 'human_verified = verification == "Yes"' in source
    assert "disabled=not can_materialize" in source
    assert "build_id_drag_artifacts(" in source
    assert "human_verified=human_verified" in source

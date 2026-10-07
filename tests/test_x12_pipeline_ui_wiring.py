from pathlib import Path


def test_main_generator_exposes_x12_toggle_and_compiles():
    path = Path("medi_lacra_app.py")
    source = path.read_text(encoding="utf-8")

    compile(source, str(path), "exec")

    assert "Include external SDOH enrichment" in source
    assert "include_sdoh=include_sdoh" in source
    assert "Include X12 Eligibility (270/271)" in source
    assert "include_x12=include_x12" in source
    assert "Include FHIR Eligibility (R4 4.0.1)" in source
    assert "include_fhir_eligibility=include_fhir_eligibility" in source
    assert '"*.x12"' in source
    assert '"*.json"' in source
    assert '"*.ndjson"' in source


def test_generate_and_persist_uses_primary_pipeline_and_exposes_payer_tables():
    path = Path("pages/2_Generate_and_Persist.py")
    source = path.read_text(encoding="utf-8")

    compile(source, str(path), "exec")

    assert "from hl7_demo.pipeline import run_pipeline" in source
    assert "Include external SDOH enrichment" in source
    assert "include_sdoh=bool(include_sdoh)" in source
    assert "Include X12 Eligibility (270/271)" in source
    assert "Include FHIR Eligibility (R4 4.0.1)" in source
    assert "include_fhir_eligibility=bool(include_fhir_eligibility)" in source
    assert 'persist="duckdb"' in source
    assert '"payer_members"' in source
    assert '"payer_enrollments"' in source
    assert '"payer_plans"' in source

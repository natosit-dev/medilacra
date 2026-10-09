# pipeline.py
# Unified generator for HL7 (ADT/ORU/DFT) with optional DuckDB persistence.
# Behavior unchanged; logging added for observability and easier debugging.

import os, re, random
from datetime import datetime
from typing import Optional, Dict, List, Tuple

# -----------------------------
# Logging (structured)
# -----------------------------
try:
    from utils.log_utils import get_logger  # package layout
except Exception:
    from .log_utils import get_logger  # script/local layout  # type: ignore

logger = get_logger(name="MediLacra", context={"component": "pipeline"})

# -----------------------------
# Imports: generators + builders
# Support both package and local execution layouts without changing behavior.
# -----------------------------
try:
    from hl7_demo.generators import gen_patient, gen_encounter, gen_transaction, gen_observation
    from hl7_demo.coverage import assign_coverage_profile
    from hl7_demo.reports import load_reports
    from hl7_demo.messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs
except ModuleNotFoundError:
    try:
        from generators import gen_patient, gen_encounter, gen_transaction, gen_observation
        try:
            from coverage import assign_coverage_profile  # type: ignore
        except Exception:
            from .coverage import assign_coverage_profile  # type: ignore
        from reports import load_reports
        # Prefer local import if present; fall back to relative (package) import
        try:
            from messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs  # type: ignore
        except Exception:
            from .messages import build_adt, build_oru, build_dft, build_orm_labs, build_oru_labs  # type: ignore
    except Exception as e:
        logger.error("Failed to import generators/reports/messages", extra={"extra": {"error": str(e)}})
        raise

from claims_epa.models import build_case as build_claims_epa_case
from reality.persistence import persist_case, register_artifact, finish_case
from claims_epa.generation import (
    generate as generate_claims_epa,
    write_artifacts as write_claims_epa_artifacts,
)
from eligibility.generation import (
    EligibilityRunContext,
    build_eligibility_inquiry_from_clinical,
)
from fhir.eligibility_generation import (
    generate_fhir_eligibility_artifacts,
    write_fhir_eligibility_artifacts,
)
from payer.materialize import materialize_payer_from_clinical
from payer.system import PayerSystem
from x12.generation import (
    X12RunContext,
    generate_x12_eligibility_artifacts,
    write_x12_artifacts,
)

# -----------------------------
# Optional persistence backend (DuckDB)
# -----------------------------
DUCK_OK = True
try:
    from storage_duckdb_entities import (
        init_db as duck_init,
        upsert_patient, upsert_encounter, upsert_observation, upsert_transaction,
        upsert_coverage_profile,
        upsert_payer_member, upsert_payer_enrollment, upsert_payer_plan,
        append_message as duck_append_message,
        DEFAULT_DB_PATH as DUCK_DEFAULT_DB_PATH,
    )
    logger.info("DuckDB persistence module available", extra={"extra": {"default_db_path": "auto (module-provided)"}})
except Exception:
    DUCK_OK = False
    DUCK_DEFAULT_DB_PATH = "medilacra.duckdb"  # used only for messaging if persistence is disabled
    logger.warning("DuckDB persistence module unavailable; filesystem-only mode unless overridden")

# -----------------------------
# Small utilities (unchanged behavior)
# -----------------------------
def _safe_encounter_for_filename(encounter_id: str) -> str:
    """Sanitize encounter id for safe filename usage."""
    return re.sub(r"[^A-Za-z0-9_\-]", "_", encounter_id)

def _first_msh_and_control_id(raw_msg: str) -> Tuple[str, str]:
    """Return first MSH line and the message control ID (MSH-10) if present."""
    first = raw_msg.split("\r", 1)[0].strip()
    ctrl = ""
    if first.startswith("MSH|"):
        parts = first.split("|")
        if len(parts) > 9:
            ctrl = parts[9]
    return first, ctrl or ""

def _collect_msg_row(run_id: str, message_type: str, path: str, msg: str,
                     *, encounter_id: str | None = None, ingest_ts: datetime | None = None) -> dict:
    """Collect a row payload describing the written HL7 message for DB logging."""
    first, ctrl = _first_msh_and_control_id(msg)
    name = os.path.basename(path)
    m = re.search(r"_(VN[0-9A-Z]+)_", name)
    enc = m.group(1) if m else name
    return {
        "run_id": run_id,
        "message_type": message_type,
        "control_id": ctrl or name,
        "encounter_id": encounter_id or enc,
        "raw_hl7": msg,
        "written_path": os.path.abspath(path),
        "ingest_ts": ingest_ts or datetime.now(),
    }

def _facility_from_pv1_3(pv1_3: str) -> str:
    """Extract facility code from PV1-3 (component 4)."""
    parts = (pv1_3 or "").split("^")
    return parts[3] if len(parts) >= 4 and parts[3] else "MEDILACRAHS"

def _set_msh_sending_facility(raw_msg: str, sending_facility: str) -> str:
    """
    Replace MSH-4 (sending facility) in the first MSH segment line.
    Keeps everything else intact.
    """
    if not raw_msg:
        return raw_msg
    # split on first HL7 segment break (\r preferred; fall back to \n)
    sep = "\r" if "\r" in raw_msg else "\n"
    first, rest = (raw_msg.split(sep, 1) + [""])[:2]
    if not first.startswith("MSH|"):
        return raw_msg  # unexpected; leave unchanged
    parts = first.split("|")
    if len(parts) < 6:
        return raw_msg  # malformed MSH; leave unchanged
    # parts[0]=MSH, [1]=^~\&, [2]=sending_app, [3]=sending_facility
    parts[3] = sending_facility or parts[3]
    new_first = "|".join(parts)
    return new_first + (sep + rest if rest else "")


# -----------------------------
# Core: run_pipeline
# -----------------------------
def run_pipeline(
    n_patients: int,
    report_glob: str,
    seed: Optional[int],
    per_encounter: bool,
    bulk: bool,
    out_dir: str,
    miles: int,
    add_places_obesity_obx: bool = False,
    add_unemployment_obx: bool = False,
    include_labs: bool = True,
    include_sdoh: bool = False,
    include_x12: bool = False,
    include_fhir_eligibility: bool = False,
    include_claims_epa: bool = False,
    persist: str = "none",
    scenario_profile: dict | None = None,
    duckdb_path: Optional[str] = None
) -> Dict[str, int]:
    """
    Generate n_patients worth of ADT/ORU/DFT messages and optionally persist entities + message log.

    Modes (unchanged):
      per_encounter=True  -> one file per encounter per message type
      per_encounter=False -> bulk files per message type for the run (appends)
      bulk is ignored if per_encounter=True (kept for API compatibility)

    persist:
      - "duckdb": upsert entities + append message log using storage_duckdb_entities
      - "none"  : filesystem only (no DB persistence)

    include_sdoh:
      - False by default: no AirNow/Census/PLACES/BLS lookups are attempted
      - True: enable external SDOH enrichment for ADT generation

    Eligibility projections:
      - include_x12 generates X12 270/271
      - include_fhir_eligibility generates FHIR R4 4.0.1 request/response
      - both consume the same semantic inquiry and payer response

    include_claims_epa: additionally project one Claims (837P/835 + FHIR)
    and one ePA (278 request/response + FHIR) case per encounter.
    Test-only; no TR3/PAS certification is claimed.
    """
    from faker import Faker  # local import to avoid module cost if unused by caller

    # ---- Seeding for reproducibility
    if seed is not None:
        random.seed(seed)
        Faker.seed(seed)
        logger.info("Randomness seeded", extra={"extra": {"seed": seed}})

    # ---- Prepare output folder + load report catalog
    os.makedirs(out_dir, exist_ok=True)
    logger.info("Output directory ready", extra={"extra": {"out_dir": os.path.abspath(out_dir)}})

    reports = load_reports(report_glob)
    logger.info("Reports loaded", extra={"extra": {"report_glob": report_glob, "report_rows": getattr(reports, 'shape', ('?', '?'))[0] if hasattr(reports, 'shape') else "unknown"}})

    # ---- Generate a run id (used in message log persistence)
    run_at = datetime.now()
    run_ts = run_at.strftime("%Y%m%d_%H%M%S")
    run_id = f"run_{run_ts}"

    # ---- Counters (return value)
    counts: Dict[str, int] = {
        "ADT": 0,
        "ORU": 0,
        "DFT": 0,
        "ORM": 0,
        "ORU_LABS": 0,
    }
    if include_x12:
        counts["X12_270"] = 0
        counts["X12_271"] = 0
    if include_fhir_eligibility:
        counts["FHIR_ELIGIBILITY_REQUEST"] = 0
        counts["FHIR_ELIGIBILITY_RESPONSE"] = 0
    if include_claims_epa:
        for name in ("X12_837P", "X12_835", "X12_278_REQUEST",
                     "X12_278_RESPONSE", "FHIR_CLAIM_REQUEST",
                     "FHIR_CLAIM_RESPONSE", "FHIR_EPA_REQUEST",
                     "FHIR_EPA_RESPONSE"):
            counts[name] = 0

    # ---- Optional eligibility workload state
    include_eligibility = (
        include_x12
        or include_fhir_eligibility
        or include_claims_epa
    )
    eligibility_run_context = (
        EligibilityRunContext(run_at)
        if include_eligibility
        else None
    )
    x12_run_context = (
        X12RunContext(run_at)
        if include_x12
        else None
    )
    payer_systems: Dict[str, PayerSystem] = {}

    # ---- Optional DuckDB init
    db_path = duckdb_path or DUCK_DEFAULT_DB_PATH
    if persist == "duckdb":
        if not DUCK_OK:
            logger.error("DuckDB persistence requested but module unavailable", extra={"extra": {"requested_path": db_path}})
            raise RuntimeError("DuckDB persistence requested, but storage_duckdb_entities is unavailable.")
        try:
            duck_init(db_path)
            logger.info("DuckDB initialized", extra={"extra": {"db_path": os.path.abspath(db_path)}})
        except Exception as e:
            logger.error("Failed to initialize DuckDB", extra={"extra": {"db_path": db_path, "error": str(e)}})
            raise

    # ---- Main generation loop
    logger.info("Starting pipeline run", extra={"extra": {
        "run_id": run_id,
        "n_patients": n_patients,
        "per_encounter": per_encounter,
        "bulk": bulk,
        "include_labs": include_labs,
        "include_sdoh": include_sdoh,
        "include_x12": include_x12,
        "include_fhir_eligibility": include_fhir_eligibility,
        "include_claims_epa": include_claims_epa,
        "persist": persist,
        "miles": miles,
        "sdoh_flags": {"places_obesity": add_places_obesity_obx, "unemployment": add_unemployment_obx},
    }})

    for idx in range(n_patients):
        try:
            # ---- Generate synthetic entities (one patient/encounter set)
            p = gen_patient()
            coverage = assign_coverage_profile(
                p,
                seed=seed,
            )
            e = gen_encounter(p.patient_id, profile=scenario_profile)
            t = gen_transaction(
                e.encounter_id,
                coverage_profile=coverage,
            )
            report_row = reports.sample(n=1).iloc[0]
            o = gen_observation(e, report_row)

            payer_member = None
            payer_enrollment = None
            payer_plan = None
            payer_system = None
            eligibility_identity = None
            eligibility_inquiry = None
            eligibility_response = None
            x12_artifacts = None
            fhir_eligibility_artifacts = None
            claims_epa_artifacts = None
            claims_epa_semantic = None
            case_id = f"{run_id}:{idx+1:05d}"

            if include_eligibility:
                payer_member, payer_enrollment, payer_plan = (
                    materialize_payer_from_clinical(
                        p,
                        coverage,
                    )
                )

                payer_system = payer_systems.get(
                    coverage.payer_id
                )
                if payer_system is None:
                    payer_system = PayerSystem(
                        coverage.payer_id
                    )
                    payer_systems[coverage.payer_id] = (
                        payer_system
                    )

                payer_system.add_member(payer_member)
                payer_system.add_enrollment(
                    payer_enrollment
                )
                payer_system.add_plan(payer_plan)

                assert eligibility_run_context is not None
                eligibility_identity = (
                    eligibility_run_context.next_exchange()
                )
                eligibility_inquiry = (
                    build_eligibility_inquiry_from_clinical(
                        p,
                        coverage,
                        e,
                    )
                )
                eligibility_response = (
                    payer_system.evaluate_eligibility(
                        eligibility_inquiry
                    )
                )

                if include_x12:
                    assert x12_run_context is not None
                    x12_artifacts = (
                        generate_x12_eligibility_artifacts(
                            inquiry=eligibility_inquiry,
                            response=eligibility_response,
                            exchange_identity=eligibility_identity,
                            encounter_id=e.encounter_id,
                            coverage_profile=coverage,
                            payer_member=payer_member,
                            payer_plan=payer_plan,
                            run_context=x12_run_context,
                        )
                    )

                if include_fhir_eligibility:
                    fhir_eligibility_artifacts = (
                        generate_fhir_eligibility_artifacts(
                            patient=p,
                            coverage_profile=coverage,
                            inquiry=eligibility_inquiry,
                            response=eligibility_response,
                            exchange_identity=eligibility_identity,
                            run_at=run_at,
                            payer_member=payer_member,
                            payer_enrollment=payer_enrollment,
                            payer_plan=payer_plan,
                            encounter_id=e.encounter_id,
                        )
                    )

                if include_claims_epa:
                    claims_epa_semantic = build_claims_epa_case(
                        patient=p, coverage=coverage, encounter=e,
                        transaction=t, observation=o,
                        payer_member=payer_member,
                        payer_enrollment=payer_enrollment,
                        run_at=run_at, ordinal=idx + 1,
                    )

            logger.info("Entities generated", extra={"extra": {
                "i": idx + 1,
                "patient_id": getattr(p, "patient_id", None),
                "encounter_id": getattr(e, "encounter_id", None),
                "coverage_profile_id": getattr(coverage, "coverage_profile_id", None),
                "employer_id": getattr(coverage, "employer_id", None),
                "payer_id": getattr(coverage, "payer_id", None),
                "plan_id": getattr(coverage, "plan_id", None)
            }})

            # ---- Persist entities (DuckDB only)
            if persist == "duckdb":
                try:
                    payload = lambda x: x.__dict__ if hasattr(x, "__dict__") else dict(x)
                    upsert_patient(payload(p), db_path=db_path)
                    upsert_coverage_profile(payload(coverage), db_path=db_path)
                    upsert_encounter(payload(e), db_path=db_path)
                    upsert_transaction(payload(t), db_path=db_path)
                    upsert_observation(payload(o), db_path=db_path)

                    if include_eligibility:
                        assert payer_member is not None
                        assert payer_enrollment is not None
                        assert payer_plan is not None
                        upsert_payer_member(
                            payload(payer_member),
                            db_path=db_path,
                        )
                        upsert_payer_enrollment(
                            payload(payer_enrollment),
                            db_path=db_path,
                        )
                        upsert_payer_plan(
                            payload(payer_plan),
                            db_path=db_path,
                        )

                    # One case snapshot retains *all* fields omitted by flat tables
                    # and the independent clinical/payer/financial semantic records.
                    records = {
                        "clinical_patient": p, "clinical_encounter": e,
                        "clinical_observation": o, "clinical_transaction": t,
                        "clinical_coverage": coverage,
                    }
                    owners = {
                        "clinical_patient": "clinical",
                        "clinical_encounter": "clinical",
                        "clinical_observation": "clinical",
                        "clinical_transaction": "clinical",
                        "clinical_coverage": "clinical",
                    }
                    if include_eligibility:
                        records.update({
                            "payer_member": payer_member,
                            "payer_enrollment": payer_enrollment,
                            "payer_plan": payer_plan,
                            "eligibility_inquiry": eligibility_inquiry,
                            "eligibility_response": eligibility_response,
                        })
                        owners.update({
                            "payer_member": "payer",
                            "payer_enrollment": "payer",
                            "payer_plan": "payer",
                            "eligibility_inquiry": "clinical",
                            "eligibility_response": "payer",
                        })
                    if claims_epa_semantic is not None:
                        records.update({
                            "claim_submission": claims_epa_semantic.claim,
                            "claim_decision": claims_epa_semantic.claim_decision,
                            "authorization_request": claims_epa_semantic.authorization,
                            "authorization_decision": claims_epa_semantic.authorization_decision,
                            "payer_subject": claims_epa_semantic.payer_subject,
                            "payer_contact": claims_epa_semantic.payer_contact,
                            "requested_service": claims_epa_semantic.requested_service,
                        })
                        owners.update({
                            "claim_submission": "clinical",
                            "claim_decision": "payer",
                            "authorization_request": "clinical",
                            "authorization_decision": "payer",
                            "payer_subject": "payer",
                            "payer_contact": "payer",
                            "requested_service": "clinical",
                        })
                    persist_case(
                        db_path=db_path, run_id=run_id, case_id=case_id,
                        source_records=records, owner_by_record=owners,
                        seed=seed, started_at=run_at,
                        source_revision=os.getenv("MEDILACRA_SOURCE_REVISION", "unrecorded"),
                        options={"include_x12": include_x12,
                                 "include_fhir_eligibility": include_fhir_eligibility,
                                 "include_claims_epa": include_claims_epa,
                                 "include_labs": include_labs},
                    )
                except Exception as pe:
                    logger.error("DuckDB entity upsert failed", extra={"extra": {"error": str(pe)}})
                    raise

            # Generators above materialized the semantic claim/PA facts.
            # Render their representations only after the persistence checkpoint.
            if include_claims_epa:
                assert claims_epa_semantic is not None
                claims_epa_artifacts = generate_claims_epa(claims_epa_semantic, run_at)

            # ---- Build HL7 messages for this encounter
            adt = build_adt(
                p,
                e,
                tx=t,
                miles=miles,
                obs=o,
                include_sdoh=include_sdoh,
                add_air_obx=include_sdoh,
                add_poverty_obx=include_sdoh,
                add_places_obesity_obx=(
                    include_sdoh
                    and add_places_obesity_obx
                ),
                add_unemployment_obx=(
                    include_sdoh
                    and add_unemployment_obx
                ),
            )
            oru = build_oru(p, e, [o])
            dft = build_dft(p, e, [t], [o])

            # Optional separate lab messages (kept distinct from narrative ORU)
            orm_labs = None
            oru_labs = None
            if include_labs:
                orm_labs = build_orm_labs(p, e)
                oru_labs = build_oru_labs(p, e, start_set_id=20)

            if scenario_profile:
                sending_facility = _facility_from_pv1_3(e.assigned_patient_location)
                adt = _set_msh_sending_facility(adt, sending_facility)
                oru = _set_msh_sending_facility(oru, sending_facility)
                dft = _set_msh_sending_facility(dft, sending_facility)
                if orm_labs:
                    orm_labs = _set_msh_sending_facility(orm_labs, sending_facility)
                if oru_labs:
                    oru_labs = _set_msh_sending_facility(oru_labs, sending_facility)
                logger.info("MSH-4 set from Scenario", extra={"extra": {"sending_facility": sending_facility}})

            # ---- File naming setup
            safe_enc = _safe_encounter_for_filename(e.encounter_id)
            bulk_files = {
                "ADT": os.path.join(out_dir, f"ADT_{run_ts}.hl7"),
                "ORU": os.path.join(out_dir, f"ORU_{run_ts}.hl7"),
                "DFT": os.path.join(out_dir, f"DFT_{run_ts}.hl7"),
                "ORM": os.path.join(out_dir, f"ORM_{run_ts}.hl7"),
                "ORU_LABS": os.path.join(out_dir, f"ORU_LABS_{run_ts}.hl7"),
            }

            # Collect messages to write for this encounter
            msgs: Dict[str, str] = {"ADT": adt, "ORU": oru, "DFT": dft}
            if include_labs and orm_labs and oru_labs:
                msgs["ORM"] = orm_labs
                msgs["ORU_LABS"] = oru_labs

            # ---- Write messages (per-encounter files or append to bulk)
            if per_encounter:
                for name, msg in msgs.items():
                    path = os.path.join(out_dir, f"{name}_{safe_enc}_{run_ts}.hl7")
                    try:
                        with open(path, "w", encoding="utf-8") as f:
                            f.write(msg)
                        counts[name] += 1
                        logger.info("Wrote per-encounter file", extra={"extra": {"type": name, "path": path}})
                    except OSError as ioe:
                        # Common on Windows if the file is locked by another process
                        logger.error("File write failed (per-encounter)", extra={"extra": {"type": name, "path": path, "error": str(ioe)}})
                        raise

                    # Append a bronze-style message log row to DuckDB if requested
                    if persist == "duckdb":
                        try:
                            row = _collect_msg_row(run_id, name, path, msg,
                                                   encounter_id=e.encounter_id, ingest_ts=run_at)
                            duck_append_message(row, db_path=db_path)
                            register_artifact(db_path, case_id, name, os.path.abspath(path), msg)
                        except Exception as le:
                            logger.error("DuckDB message log append failed", extra={"extra": {"type": name, "path": path, "error": str(le)}})
                            raise
            else:
                for name, msg in msgs.items():
                    path = bulk_files[name]
                    mode = "a" if os.path.exists(path) else "w"
                    try:
                        with open(path, mode, encoding="utf-8") as f:
                            if mode == "a":
                                f.write("\n\n")  # blank lines between messages when appending
                            f.write(msg)
                        counts[name] += 1
                        logger.info("Wrote bulk file", extra={"extra": {"type": name, "path": path, "mode": mode}})
                    except OSError as ioe:
                        logger.error("File write failed (bulk)", extra={"extra": {"type": name, "path": path, "mode": mode, "error": str(ioe)}})
                        raise

                    if persist == "duckdb":
                        try:
                            row = _collect_msg_row(run_id, name, path, msg,
                                                   encounter_id=e.encounter_id, ingest_ts=run_at)
                            duck_append_message(row, db_path=db_path)
                            register_artifact(db_path, case_id, name, os.path.abspath(path), msg)
                        except Exception as le:
                            logger.error("DuckDB message log append failed", extra={"extra": {"type": name, "path": path, "error": str(le)}})
                            raise

            # ---- Write X12 eligibility pair separately from HL7 persistence
            if include_x12:
                assert x12_artifacts is not None
                try:
                    x12_paths = write_x12_artifacts(
                        x12_artifacts,
                        out_dir=out_dir,
                        run_ts=run_ts,
                        per_encounter=per_encounter,
                        safe_encounter=safe_enc,
                    )
                    counts["X12_270"] += 1
                    counts["X12_271"] += 1
                    if persist == "duckdb":
                        for kind, payload_text in (
                            ("X12_270", x12_artifacts.x270),
                            ("X12_271", x12_artifacts.x271),
                        ):
                            register_artifact(db_path, case_id, kind,
                                              os.path.abspath(x12_paths[kind]), payload_text)
                    logger.info(
                        "Wrote X12 eligibility pair",
                        extra={"extra": {
                            "encounter_id": e.encounter_id,
                            "trace_id": x12_artifacts.trace_id,
                            "x270_path": x12_paths["X12_270"],
                            "x271_path": x12_paths["X12_271"],
                        }},
                    )
                except OSError as ioe:
                    logger.error(
                        "X12 file write failed",
                        extra={"extra": {
                            "encounter_id": e.encounter_id,
                            "error": str(ioe),
                        }},
                    )
                    raise

            # ---- Write direct FHIR R4 eligibility projections
            if include_fhir_eligibility:
                assert fhir_eligibility_artifacts is not None
                try:
                    fhir_paths = write_fhir_eligibility_artifacts(
                        fhir_eligibility_artifacts,
                        out_dir=out_dir,
                        run_ts=run_ts,
                        per_encounter=per_encounter,
                        safe_encounter=safe_enc,
                    )
                    counts["FHIR_ELIGIBILITY_REQUEST"] += 1
                    counts["FHIR_ELIGIBILITY_RESPONSE"] += 1
                    if persist == "duckdb":
                        import json
                        for kind, bundle in (
                            ("FHIR_ELIGIBILITY_REQUEST", fhir_eligibility_artifacts.request_bundle),
                            ("FHIR_ELIGIBILITY_RESPONSE", fhir_eligibility_artifacts.response_bundle),
                        ):
                            register_artifact(db_path, case_id, kind,
                                              os.path.abspath(fhir_paths[kind]),
                                              json.dumps(bundle, sort_keys=True))
                    logger.info(
                        "Wrote FHIR R4 eligibility pair",
                        extra={"extra": {
                            "encounter_id": e.encounter_id,
                            "exchange_id": (
                                fhir_eligibility_artifacts.exchange_id
                            ),
                            "request_path": fhir_paths[
                                "FHIR_ELIGIBILITY_REQUEST"
                            ],
                            "response_path": fhir_paths[
                                "FHIR_ELIGIBILITY_RESPONSE"
                            ],
                        }},
                    )
                except OSError as ioe:
                    logger.error(
                        "FHIR eligibility file write failed",
                        extra={"extra": {
                            "encounter_id": e.encounter_id,
                            "error": str(ioe),
                        }},
                    )
                    raise

            # ---- Claims/ePA artifacts are separate from HL7 message persistence
            if include_claims_epa:
                assert claims_epa_artifacts is not None
                folder = os.path.join(
                    out_dir, f"CLAIMS_EPA_{run_ts}_{idx+1:05d}_{safe_enc}"
                )
                paths = write_claims_epa_artifacts(
                    claims_epa_artifacts, folder,
                )
                for key in ("X12_837P", "X12_835", "X12_278_REQUEST",
                            "X12_278_RESPONSE", "FHIR_CLAIM_REQUEST",
                            "FHIR_CLAIM_RESPONSE", "FHIR_EPA_REQUEST",
                            "FHIR_EPA_RESPONSE"):
                    counts[key] += 1
                if persist == "duckdb":
                    from pathlib import Path
                    for kind, artifact_path in paths.items():
                        artifact_file = Path(artifact_path)
                        if artifact_file.is_file():
                            register_artifact(db_path, case_id, kind, str(artifact_file),
                                              artifact_file.read_text(encoding="utf-8"))
                logger.info("Wrote Claims/ePA dual-format synthetic artifacts",
                            extra={"extra": {"encounter_id": e.encounter_id,
                                             "path": folder,
                                             "artifact_count": len(paths)}})

            if persist == "duckdb":
                finish_case(db_path, case_id)

        except Exception as e:
            # A single encounter failure is bubbled up (unchanged behavior),
            # but we include a detailed log entry to diagnose quickly.
            logger.error("Encounter processing failed", extra={"extra": {"i": idx + 1, "error": str(e)}})
            raise

    logger.info("Pipeline run complete", extra={"extra": {"run_id": run_id, "counts": counts}})
    return counts

# -----------------------------
# Backward-compatible alias
# -----------------------------
def run_and_persist(
    n_patients: int,
    report_glob: str,
    seed: Optional[int],
    per_encounter: bool,
    bulk: bool,
    out_dir: str,
    miles: int,
    db_path: Optional[str] = None,
    # New flags accepted silently by older callers
    add_places_obesity_obx: bool = False,
    add_unemployment_obx: bool = False,
    include_sdoh: bool = False,
    include_x12: bool = False,
    include_fhir_eligibility: bool = False,
    include_claims_epa: bool = False,
) -> Dict[str, int]:
    """
    Legacy entry point matching older callers (kept to avoid breaking pages).
    Accepts the new SDOH flags to prevent TypeError in older call sites.
    """
    logger.info("run_and_persist called (compatibility wrapper)")
    return run_pipeline(
        n_patients=n_patients,
        report_glob=report_glob,
        seed=seed,
        per_encounter=per_encounter,
        bulk=bulk,
        out_dir=out_dir,
        miles=miles,
        add_places_obesity_obx=add_places_obesity_obx,
        add_unemployment_obx=add_unemployment_obx,
        include_sdoh=include_sdoh,
        include_x12=include_x12,
        include_fhir_eligibility=include_fhir_eligibility,
        include_claims_epa=include_claims_epa,
        persist="duckdb",
        duckdb_path=db_path,
    )

# -----------------------------
# CLI (kept as-is except logs)
# -----------------------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="MediLacra unified HL7 generator")
    ap.add_argument("--n", type=int, default=10, help="Number of patients")
    ap.add_argument("--reports", type=str, default="reports/*.csv", help="Glob for report CSVs")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--per-encounter", action="store_true", help="Write one file per encounter per type")
    ap.add_argument("--bulk", action="store_true", help="Append to nightly bulk files (ignored if --per-encounter)")
    ap.add_argument("--out", type=str, default="out", help="Output folder")
    ap.add_argument("--miles", type=int, default=0, help="Distance delta for SDOH logic in ADT")
    ap.add_argument("--add-places-obesity-obx", action="store_true", help="Emit Places/Obesity OBX in ADT")
    ap.add_argument("--add-unemployment-obx", action="store_true", help="Emit Unemployment OBX in ADT when --include-sdoh is enabled")
    ap.add_argument("--include-sdoh", action="store_true", help="Enable external AirNow/Census/PLACES/BLS SDOH enrichment")
    ap.add_argument("--include-x12", action="store_true", help="Generate X12 270/271 eligibility output")
    ap.add_argument("--include-fhir-eligibility", action="store_true", help="Generate FHIR R4 4.0.1 eligibility request/response bundles")
    ap.add_argument("--include-claims-epa", action="store_true", help="Generate synthetic Claims and ePA X12 + FHIR R4 pairs")
    ap.add_argument("--persist", choices=["duckdb", "none"], default="duckdb", help="Where to persist")
    ap.add_argument("--duckdb-path", type=str, default=None, help="DuckDB database path")
    args = ap.parse_args()

    logger.info("CLI invocation", extra={"extra": vars(args)})
    counts = run_pipeline(
        n_patients=args.n,
        report_glob=args.reports,
        seed=args.seed,
        per_encounter=args.per_encounter,
        bulk=args.bulk,
        out_dir=args.out,
        miles=args.miles,
        add_places_obesity_obx=args.add_places_obesity_obx,
        add_unemployment_obx=args.add_unemployment_obx,
        include_sdoh=args.include_sdoh,
        include_x12=args.include_x12,
        include_fhir_eligibility=args.include_fhir_eligibility,
        include_claims_epa=args.include_claims_epa,
        persist=args.persist,
        duckdb_path=args.duckdb_path,
    )
    # Keep original behavior: print the final counts in CLI mode
    print("[DONE]", counts)
    logger.info("CLI run finished", extra={"extra": {"counts": counts}})

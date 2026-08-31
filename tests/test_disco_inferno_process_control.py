import json

import pandas as pd

from experiments.disco_inferno import process_control as pc


def _point_runtime_at(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(pc, "LOCK_PATH", tmp_path / "active_run.json")


def test_stale_worker_lock_is_cleared(tmp_path, monkeypatch):
    _point_runtime_at(tmp_path, monkeypatch)
    lock = {
        "job_id": "dead-job",
        "status": "running",
        "pid": 99999999,
        "started_at": pc._now_iso(),
    }
    pc.LOCK_PATH.write_text(json.dumps(lock), encoding="utf-8")

    assert pc.get_active_run() is None
    assert not pc.LOCK_PATH.exists()


def test_tail_job_log_returns_only_requested_lines(tmp_path, monkeypatch):
    _point_runtime_at(tmp_path, monkeypatch)
    job_id = "log-job"
    log_path = tmp_path / f"worker_{job_id}.log"
    log_path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")

    assert pc.tail_job_log(job_id, max_lines=2) == "three\nfour"


def test_completed_worker_run_can_be_rehydrated_for_streamlit(tmp_path):
    run_id = "20260830T224200-0400"
    run_dir = tmp_path / run_id
    beatrice_dir = run_dir / "beatrice"
    beatrice_dir.mkdir(parents=True)

    source = {
        "patients": pd.DataFrame({"patient_id": ["P1"]}),
        "encounters": pd.DataFrame({"encounter_id": ["E1"], "patient_id": ["P1"]}),
        "observations": pd.DataFrame(
            {
                "observation_id": ["O1"],
                "encounter_id": ["E1"],
                "observation_text": ["hello"],
            }
        ),
        "transactions": pd.DataFrame(
            {
                "transaction_id": ["T1"],
                "encounter_id": ["E1"],
                "transaction_amount": [1.0],
            }
        ),
    }

    for table, frame in source.items():
        frame.to_csv(beatrice_dir / f"{table}_{run_id}.csv", index=False)

    arms = {}
    for arm_name in ("Control", "Charon", "Null", "Cerberus"):
        arm_dir = run_dir / "inferno" / arm_name.lower()
        arm_dir.mkdir(parents=True)
        for table, frame in source.items():
            frame.to_csv(arm_dir / f"{table}_{run_id}.csv", index=False)
        arms[arm_name] = {
            "operator": arm_name.lower(),
            "inferno_name": arm_name,
            "table": None if arm_name == "Control" else "observations",
            "field": None,
            "fraction": 0.0,
            "source_rows": 1,
            "affected_rows": 0,
            "output_rows": 1,
            "affected_records": [],
        }

    manifest = {
        "experiment": "disco_inferno",
        "run_id": run_id,
        "settings": {"include_sdoh": False},
        "hl7": {"message_counts": {}, "files": {}},
        "arms": arms,
    }
    (run_dir / f"manifest_{run_id}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    pd.DataFrame(
        [
            {"arm": "Control", "metric": "delta", "value": 0},
            {"arm": "Charon", "metric": "delta", "value": 0},
            {"arm": "Null", "metric": "delta", "value": 0},
            {"arm": "Cerberus", "metric": "delta", "value": 0},
        ]
    ).to_csv(run_dir / f"metrics_{run_id}.csv", index=False)

    (run_dir / f"DISCO_INFERNO_REPORT_{run_id}.md").write_text(
        "# report", encoding="utf-8"
    )
    (run_dir / f"source_reality_{run_id}.duckdb").write_bytes(b"duck")
    (run_dir / f"DISCO_INFERNO_{run_id}.zip").write_bytes(b"zip")

    loaded = pc.load_completed_run(run_dir)

    assert loaded["run_id"] == run_id
    assert loaded["beatrice"]["observations"].iloc[0]["observation_text"] == "hello"
    assert loaded["arms"]["Cerberus"].model["transactions"].iloc[0]["transaction_id"] == "T1"
    assert loaded["artifacts"]["report"].name == f"DISCO_INFERNO_REPORT_{run_id}.md"

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from experiments.disco_inferno.corruptions import CorruptionResult


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "experiments" / "disco_inferno" / "output"
RUNTIME_DIR = OUTPUT_ROOT / ".runtime"
LOCK_PATH = RUNTIME_DIR / "active_run.json"


def _now() -> datetime:
    return datetime.now().astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="milliseconds")


def _new_job_id() -> str:
    return _now().strftime("%Y%m%dT%H%M%S%f%z")


def _status_path(job_id: str) -> Path:
    return RUNTIME_DIR / f"status_{job_id}.json"


def _config_path(job_id: str) -> Path:
    return RUNTIME_DIR / f"config_{job_id}.json"


def _log_path(job_id: str) -> Path:
    return RUNTIME_DIR / f"worker_{job_id}.log"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    os.replace(temp, path)


def write_job_status(job_id: str, value: dict[str, Any]) -> dict[str, Any]:
    payload = {"job_id": job_id, **value}
    _write_json_atomic(_status_path(job_id), payload)
    return payload


def get_job_status(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    return _read_json(_status_path(job_id))


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid < 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pid_matches_worker(pid: int) -> bool:
    """Avoid killing a reused PID when /proc metadata is available."""

    if os.name == "nt":
        return True

    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if not cmdline_path.exists():
        return True

    try:
        command = cmdline_path.read_bytes().replace(b"\0", b" ").decode(
            "utf-8", errors="replace"
        )
    except OSError:
        return True

    return (
        "experiments.disco_inferno.worker" in command
        or "disco_inferno/worker.py" in command
    )


def _starting_lock_expired(lock: dict[str, Any], timeout_seconds: float = 30.0) -> bool:
    if lock.get("status") != "starting":
        return False
    try:
        started = datetime.fromisoformat(str(lock["started_at"]))
    except (KeyError, TypeError, ValueError):
        return True
    return (_now() - started).total_seconds() > timeout_seconds


def _remove_lock_if_job(job_id: str) -> None:
    lock = _read_json(LOCK_PATH)
    if lock and lock.get("job_id") == job_id:
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def get_active_run() -> dict[str, Any] | None:
    """Return the active worker lock, removing stale locks automatically."""

    lock = _read_json(LOCK_PATH)
    if not lock:
        return None

    if lock.get("status") == "starting" and not _starting_lock_expired(lock):
        return lock

    pid = lock.get("pid")
    try:
        pid_int = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_int = None

    if (
        pid_int is not None
        and _pid_alive(pid_int)
        and _pid_matches_worker(pid_int)
    ):
        return lock

    _remove_lock_if_job(str(lock.get("job_id", "")))
    return None


def _reserve_lock(payload: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, default=str)
    try:
        fd = os.open(
            LOCK_PATH,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
        )
    except FileExistsError as exc:
        active = get_active_run()
        if active:
            raise RuntimeError(
                f"Disco Inferno is already running as job {active.get('job_id')} "
                f"(PID {active.get('pid', 'starting')})."
            ) from exc
        fd = os.open(
            LOCK_PATH,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
        )

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)


def start_run(config: dict[str, Any]) -> dict[str, Any]:
    """Start one detached Disco Inferno worker and claim the generator lock."""

    active = get_active_run()
    if active:
        raise RuntimeError(
            f"Disco Inferno is already running as job {active.get('job_id')} "
            f"(PID {active.get('pid', 'starting')})."
        )

    job_id = _new_job_id()
    config_path = _config_path(job_id)
    log_path = _log_path(job_id)
    status_path = _status_path(job_id)
    started_at = _now_iso()

    _write_json_atomic(config_path, config)

    pending_lock = {
        "job_id": job_id,
        "status": "starting",
        "pid": None,
        "controller_pid": os.getpid(),
        "started_at": started_at,
        "config_path": str(config_path),
        "status_path": str(status_path),
        "log_path": str(log_path),
    }
    _reserve_lock(pending_lock)
    write_job_status(
        job_id,
        {
            "status": "starting",
            "started_at": started_at,
            "pid": None,
            "log_path": str(log_path),
        },
    )

    command = [
        sys.executable,
        "-m",
        "experiments.disco_inferno.worker",
        "--job-id",
        job_id,
        "--config",
        str(config_path),
    ]

    popen_kwargs: dict[str, Any] = {
        "cwd": str(REPO_ROOT),
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "env": {**os.environ, "PYTHONUNBUFFERED": "1"},
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
            popen_kwargs["stdout"] = log_handle
            process = subprocess.Popen(command, **popen_kwargs)
    except Exception:
        _remove_lock_if_job(job_id)
        write_job_status(
            job_id,
            {
                "status": "failed",
                "started_at": started_at,
                "ended_at": _now_iso(),
                "error": "Worker process failed to start.",
                "log_path": str(log_path),
            },
        )
        raise

    running_lock = {
        **pending_lock,
        "status": "running",
        "pid": process.pid,
        "command": command,
    }
    _write_json_atomic(LOCK_PATH, running_lock)
    write_job_status(
        job_id,
        {
            "status": "running",
            "started_at": started_at,
            "pid": process.pid,
            "log_path": str(log_path),
        },
    )
    return running_lock


def wait_for_lock_ready(job_id: str, pid: int, timeout_seconds: float = 5.0) -> None:
    """Prevent the worker from racing the parent before PID metadata is written."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lock = _read_json(LOCK_PATH)
        if (
            lock
            and lock.get("job_id") == job_id
            and int(lock.get("pid") or 0) == pid
            and lock.get("status") == "running"
        ):
            return
        time.sleep(0.05)

    raise RuntimeError("Worker could not confirm ownership of the Disco Inferno lock.")


def release_lock(job_id: str) -> None:
    _remove_lock_if_job(job_id)


def _terminate_process_tree(pid: int, force_after_seconds: float = 2.0) -> None:
    if not _pid_alive(pid):
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        return

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    deadline = time.monotonic() + force_after_seconds
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)

    if _pid_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def stop_active_run() -> dict[str, Any]:
    """Stop the active worker process group and release the generator lock."""

    active = get_active_run()
    if not active:
        return {"stopped": False, "reason": "No active Disco Inferno worker."}

    job_id = str(active["job_id"])
    pid = active.get("pid")
    try:
        pid_int = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pid_int = None

    if pid_int and _pid_alive(pid_int):
        if not _pid_matches_worker(pid_int):
            _remove_lock_if_job(job_id)
            return {
                "stopped": False,
                "reason": (
                    f"PID {pid_int} no longer belongs to the Disco Inferno worker; "
                    "stale lock cleared without killing it."
                ),
            }
        _terminate_process_tree(pid_int)

    previous = get_job_status(job_id) or {}
    status = write_job_status(
        job_id,
        {
            **previous,
            "status": "stopped",
            "ended_at": _now_iso(),
            "pid": pid_int,
            "log_path": str(active.get("log_path", _log_path(job_id))),
        },
    )
    _remove_lock_if_job(job_id)
    return {"stopped": True, **status}


def tail_job_log(job_id: str | None, max_lines: int = 80) -> str:
    if not job_id:
        return ""
    path = _log_path(job_id)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-max_lines:])


def _load_model(directory: Path, run_id: str) -> dict[str, pd.DataFrame]:
    model: dict[str, pd.DataFrame] = {}
    for table in ("patients", "encounters", "observations", "transactions"):
        path = directory / f"{table}_{run_id}.csv"
        if path.exists():
            model[table] = pd.read_csv(path)
    return model


def load_completed_run(run_dir: str | Path) -> dict[str, Any]:
    """Rehydrate a completed worker run into the structure expected by the UI."""

    run_dir = Path(run_dir)
    run_id = run_dir.name
    manifest_path = run_dir / f"manifest_{run_id}.json"
    metrics_path = run_dir / f"metrics_{run_id}.csv"
    report_path = run_dir / f"DISCO_INFERNO_REPORT_{run_id}.md"
    source_db = run_dir / f"source_reality_{run_id}.duckdb"
    bundle_path = run_dir / f"DISCO_INFERNO_{run_id}.zip"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metrics = pd.read_csv(metrics_path)
    beatrice = _load_model(run_dir / "beatrice", run_id)

    arms: dict[str, CorruptionResult] = {}
    metrics_by_arm: dict[str, pd.DataFrame] = {}
    inferno_dirs: dict[str, Path] = {}

    for arm_name in ("Control", "Charon", "Null", "Cerberus"):
        arm_dir = run_dir / "inferno" / arm_name.lower()
        inferno_dirs[arm_name] = arm_dir
        arms[arm_name] = CorruptionResult(
            model=_load_model(arm_dir, run_id),
            manifest=dict(manifest["arms"][arm_name]),
        )
        metrics_by_arm[arm_name] = metrics.loc[
            metrics["arm"] == arm_name
        ].copy()

    artifacts: dict[str, Path] = {
        "report": report_path,
        "manifest": manifest_path,
        "metrics": metrics_path,
        "source_duckdb": source_db,
        "bundle": bundle_path,
    }
    for message_type, filename in manifest.get("hl7", {}).get("files", {}).items():
        artifacts[f"hl7_{message_type.lower()}"] = run_dir / "hl7" / filename

    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "beatrice": beatrice,
        "arms": arms,
        "metrics_by_arm": metrics_by_arm,
        "manifest": manifest,
        "artifacts": artifacts,
        "beatrice_dir": run_dir / "beatrice",
        "inferno_dirs": inferno_dirs,
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description="Disco Inferno worker process control.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Show the active generator lock.")
    subparsers.add_parser("stop", help="Stop the active generator worker.")
    args = parser.parse_args()

    if args.command == "status":
        print(json.dumps(get_active_run() or {"active": False}, indent=2, default=str))
    elif args.command == "stop":
        print(json.dumps(stop_active_run(), indent=2, default=str))


if __name__ == "__main__":
    _main()

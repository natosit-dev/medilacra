from __future__ import annotations

import argparse
import json
import os
import signal
import traceback
from pathlib import Path

from experiments.disco_inferno.offline_sdoh import install_offline_sdoh
from experiments.disco_inferno.process_control import (
    _now_iso,
    release_lock,
    wait_for_lock_ready,
    write_job_status,
)
from experiments.disco_inferno.run_experiment import run_experiment


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detached Disco Inferno generation worker.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--config", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    job_id = args.job_id
    pid = os.getpid()
    config_path = Path(args.config)

    if os.name != "nt":
        def _term_handler(_signum, _frame):
            raise KeyboardInterrupt("Disco Inferno worker stop requested.")

        signal.signal(signal.SIGTERM, _term_handler)

    wait_for_lock_ready(job_id, pid)
    config = json.loads(config_path.read_text(encoding="utf-8"))

    # Structured Sparsity never enters the external SDOH enrichment path.
    # Disco Inferno should behave the same way whenever SDOH is disabled:
    # install a worker-wide offline boundary before any generation/projection
    # work begins. Missing include_sdoh in older configs is treated as off.
    if not bool(config.get("include_sdoh", False)):
        install_offline_sdoh()
        print(
            "SDOH OFFLINE — Census, AirNow, PLACES, and BLS network lookups disabled.",
            flush=True,
        )

    started_at = _now_iso()
    write_job_status(
        job_id,
        {
            "status": "running",
            "started_at": started_at,
            "pid": pid,
        },
    )

    try:
        result = run_experiment(**config)
        write_job_status(
            job_id,
            {
                "status": "complete",
                "started_at": started_at,
                "ended_at": _now_iso(),
                "pid": pid,
                "run_id": result["run_id"],
                "run_dir": str(result["run_dir"]),
                "artifacts": {
                    name: str(path)
                    for name, path in result["artifacts"].items()
                },
            },
        )
        return 0
    except KeyboardInterrupt:
        write_job_status(
            job_id,
            {
                "status": "stopped",
                "started_at": started_at,
                "ended_at": _now_iso(),
                "pid": pid,
            },
        )
        return 130
    except BaseException as exc:
        write_job_status(
            job_id,
            {
                "status": "failed",
                "started_at": started_at,
                "ended_at": _now_iso(),
                "pid": pid,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            },
        )
        traceback.print_exc()
        return 1
    finally:
        release_lock(job_id)


if __name__ == "__main__":
    raise SystemExit(main())

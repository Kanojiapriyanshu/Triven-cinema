import json
import sqlite3
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[4]
JOBS_DIR = PROJECT_ROOT / "storage" / "jobs"
JOBS_DB = JOBS_DIR / "jobs.sqlite3"
_DB_LOCK = Lock()
_INITIALIZED = False
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="triven-job")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(JOBS_DB, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_job_store() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    with _DB_LOCK:
        if _INITIALIZED:
            return
        with _connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                UPDATE generation_jobs
                SET status = 'failed',
                    stage = 'failed',
                    progress = 100,
                    error = 'API process restarted before this job completed.',
                    message = 'Interrupted by API restart.',
                    updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (_now(),),
            )
            connection.commit()
        _INITIALIZED = True


def create_job(job_type: str, payload: dict) -> str:
    initialize_job_store()
    job_id = uuid.uuid4().hex
    timestamp = _now()
    with _DB_LOCK, _connect() as connection:
        connection.execute(
            """
            INSERT INTO generation_jobs (
                id, job_type, status, stage, progress, message,
                payload_json, result_json, error, created_at, updated_at
            ) VALUES (?, ?, 'queued', 'queued', 0, 'Queued', ?, NULL, NULL, ?, ?)
            """,
            (job_id, job_type, json.dumps(payload), timestamp, timestamp),
        )
        connection.commit()
    return job_id


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[object] = [_now()]

    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if stage is not None:
        fields.append("stage = ?")
        values.append(stage)
    if progress is not None:
        fields.append("progress = ?")
        values.append(max(0, min(100, int(progress))))
    if message is not None:
        fields.append("message = ?")
        values.append(message)
    if result is not None:
        fields.append("result_json = ?")
        values.append(json.dumps(result))
    if error is not None:
        fields.append("error = ?")
        values.append(error)

    values.append(job_id)
    with _DB_LOCK, _connect() as connection:
        connection.execute(
            f"UPDATE generation_jobs SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        connection.commit()


def get_job(job_id: str) -> dict | None:
    initialize_job_store()
    with _DB_LOCK, _connect() as connection:
        row = connection.execute(
            "SELECT * FROM generation_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "job_id": row["id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "stage": row["stage"],
        "progress": row["progress"],
        "message": row["message"],
        "payload": json.loads(row["payload_json"]),
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def submit_job(
    job_type: str,
    payload: dict,
    runner: Callable[[str], dict],
) -> str:
    job_id = create_job(job_type, payload)

    def _run() -> None:
        try:
            update_job(
                job_id,
                status="running",
                stage="initializing",
                progress=5,
                message="Initializing generation job...",
            )
            result = runner(job_id)
            update_job(
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                message="Generation complete.",
                result=result,
            )
        except Exception as exc:  # noqa: BLE001 - job boundary must capture all failures
            traceback.print_exc()
            update_job(
                job_id,
                status="failed",
                stage="failed",
                progress=100,
                message="Generation failed.",
                error=str(exc),
            )

    _EXECUTOR.submit(_run)
    return job_id


initialize_job_store()

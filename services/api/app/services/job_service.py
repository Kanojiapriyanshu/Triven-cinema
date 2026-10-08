import json
import sqlite3
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Callable

from app.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[4]
JOBS_DIR = PROJECT_ROOT / "storage" / "jobs"
JOBS_DB = JOBS_DIR / "jobs.sqlite3"
_DB_LOCK = Lock()
_INITIALIZED = False
_EXECUTOR: ThreadPoolExecutor | None = None


class JobQueueFullError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(JOBS_DB, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        workers = max(1, int(settings.job_workers))
        _EXECUTOR = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="triven-job",
        )
    return _EXECUTOR


def initialize_job_store() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    with _DB_LOCK:
        if _INITIALIZED:
            return
        with closing(_connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
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
                "CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON generation_jobs(status)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_generation_jobs_updated_at ON generation_jobs(updated_at)"
            )
            # In-process jobs cannot survive a process restart. Mark them explicitly
            # failed so the UI never polls forever after the API container restarts.
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


def active_job_count() -> int:
    initialize_job_store()
    with _DB_LOCK, closing(_connect()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM generation_jobs WHERE status IN ('queued', 'running')"
        ).fetchone()
    return int(row["count"] if row else 0)


def prune_old_jobs(retention_days: int | None = None) -> int:
    initialize_job_store()
    days = max(1, int(retention_days or settings.job_retention_days))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _DB_LOCK, closing(_connect()) as connection:
        cursor = connection.execute(
            """
            DELETE FROM generation_jobs
            WHERE status IN ('completed', 'failed') AND updated_at < ?
            """,
            (cutoff,),
        )
        connection.commit()
        return int(cursor.rowcount or 0)


def create_job(job_type: str, payload: dict) -> str:
    initialize_job_store()
    max_pending = max(1, int(settings.job_max_pending))
    job_id = uuid.uuid4().hex
    timestamp = _now()

    # Count and insert under the same process lock so two simultaneous browser/API
    # requests cannot both slip past the paid-render queue limit.
    with _DB_LOCK, closing(_connect()) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM generation_jobs WHERE status IN ('queued', 'running')"
        ).fetchone()
        active = int(row["count"] if row else 0)
        if active >= max_pending:
            raise JobQueueFullError(
                f"Generation queue is full ({max_pending} active/pending jobs). "
                "Wait for an existing render to finish before starting another."
            )

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
    with _DB_LOCK, closing(_connect()) as connection:
        connection.execute(
            f"UPDATE generation_jobs SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        connection.commit()


def get_job(job_id: str) -> dict | None:
    initialize_job_store()
    with _DB_LOCK, closing(_connect()) as connection:
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



def workspace_owns_generated_file(workspace_id: str, filename: str) -> bool:
    """Return True only when a completed job for this workspace references the file.

    Production media is intentionally not exposed as a raw static directory. Generated
    filenames are random, but authorization still follows the signed workspace identity.
    The single-VPS store is small enough to inspect completed result JSON safely; move this
    ownership relation into Postgres/object metadata when the platform becomes multi-node.
    """
    clean_workspace = workspace_id.strip()
    clean_filename = Path(filename).name
    if not clean_workspace or not clean_filename or clean_filename != filename:
        return False
    # Start frames are generated on request, before any job exists; their name carries the workspace.
    if clean_filename.startswith(f"hero-{clean_workspace}-"):
        return True

    initialize_job_store()
    with _DB_LOCK, closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT payload_json, result_json
            FROM generation_jobs
            WHERE status = 'completed' AND result_json IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 500
            """
        ).fetchall()

    def contains_filename(value: object) -> bool:
        if isinstance(value, str):
            return Path(value.split('?', 1)[0]).name == clean_filename
        if isinstance(value, dict):
            return any(contains_filename(item) for item in value.values())
        if isinstance(value, list):
            return any(contains_filename(item) for item in value)
        return False

    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            result = json.loads(row["result_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if str(payload.get("workspace_id") or "") != clean_workspace:
            continue
        if contains_filename(result):
            return True
    return False

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
            safe_error = (
                str(exc)
                if settings.debug and not settings.is_production
                else "Generation failed. Check the application server logs for details."
            )
            update_job(
                job_id,
                status="failed",
                stage="failed",
                progress=100,
                message="Generation failed.",
                error=safe_error,
            )

    _executor().submit(_run)
    return job_id


def shutdown_job_executor() -> None:
    global _EXECUTOR
    if _EXECUTOR is not None:
        _EXECUTOR.shutdown(wait=False, cancel_futures=True)
        _EXECUTOR = None


initialize_job_store()

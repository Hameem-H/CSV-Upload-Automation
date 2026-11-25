
import json
import threading

from datetime import datetime
from pathlib import Path


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

JOBS_DIRECTORY = Path(__file__).resolve().parent / "data"

REGISTRY_FILE = JOBS_DIRECTORY / "jobs.json"

_REGISTRY_LOCK = threading.RLock()


# --------------------------------------------------
# INTERNAL HELPERS
# --------------------------------------------------

def _current_timestamp():
    return datetime.now().isoformat(timespec="seconds")


def _ensure_registry():
    JOBS_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True
    )

    if not REGISTRY_FILE.exists():
        REGISTRY_FILE.write_text(
            "[]",
            encoding="utf-8"
        )


def _read_jobs():
    _ensure_registry()

    try:
        with REGISTRY_FILE.open("r", encoding="utf-8") as file:
            jobs = json.load(file)

        if not isinstance(jobs, list):
            raise ValueError("Job registry must contain a JSON list.")

        return jobs

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Job registry JSON is corrupted: {error}"
        ) from error


def _write_jobs(jobs):
    _ensure_registry()

    temporary_file = REGISTRY_FILE.with_suffix(".tmp")

    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(
            jobs,
            file,
            indent=4,
            ensure_ascii=False
        )

    temporary_file.replace(REGISTRY_FILE)


# --------------------------------------------------
# CREATE JOB
# --------------------------------------------------

def create_job(
    job_id,
    department_id,
    department_name,
    original_filename,
    storage_date
):
    with _REGISTRY_LOCK:

        jobs = _read_jobs()

        if any(job["job_id"] == job_id for job in jobs):
            raise ValueError(
                f"Job ID already exists: {job_id}"
            )

        job = {
            "job_id": job_id,
            "department_id": department_id,
            "department": department_name,
            "original_filename": original_filename,
            "storage_date": str(storage_date),

            "status": "preparing",
            "stage": "Waiting for preparation",
            "progress": 0,
            "message": "Job submitted.",

            "created_at": _current_timestamp(),
            "started_at": None,
            "completed_at": None,

            "saved_files": {},
            "metrics": {},
            "erp_result": None,
            "error": None,

            "history": [
                {
                    "timestamp": _current_timestamp(),
                    "stage": "submitted",
                    "status": "preparing",
                    "message": "Job submitted."
                }
            ]
        }

        jobs.append(job)

        _write_jobs(jobs)

        return job.copy()


# --------------------------------------------------
# UPDATE JOB
# --------------------------------------------------

def update_job(
    job_id,
    status=None,
    stage=None,
    progress=None,
    message=None,
    saved_files=None,
    metrics=None,
    erp_result=None,
    error=None
):
    with _REGISTRY_LOCK:

        jobs = _read_jobs()

        job = next(
            (
                item for item in jobs
                if item["job_id"] == job_id
            ),
            None
        )

        if job is None:
            raise KeyError(
                f"Job not found: {job_id}"
            )

        timestamp = _current_timestamp()

        if status is not None:
            job["status"] = status

            if status == "running" and job["started_at"] is None:
                job["started_at"] = timestamp

            if status in ("completed", "failed", "interrupted"):
                job["completed_at"] = timestamp

        if stage is not None:
            job["stage"] = stage

        if progress is not None:
            job["progress"] = max(
                0,
                min(100, int(progress))
            )

        if message is not None:
            job["message"] = message

        if saved_files is not None:
            job["saved_files"].update(saved_files)

        if metrics is not None:
            job["metrics"].update(metrics)

        if erp_result is not None:
            job["erp_result"] = erp_result

        if error is not None:
            job["error"] = str(error)

        # Record a history entry whenever the job changes.
        job["history"].append({
            "timestamp": timestamp,
            "stage": stage or job["stage"],
            "status": status or job["status"],
            "message": message or job["message"]
        })

        _write_jobs(jobs)

        return job.copy()


# --------------------------------------------------
# GET ONE JOB
# --------------------------------------------------

def get_job(job_id):

    with _REGISTRY_LOCK:

        jobs = _read_jobs()

        for job in jobs:

            if job["job_id"] == job_id:
                return job.copy()

        return None


# --------------------------------------------------
# GET ALL JOBS
# --------------------------------------------------

def get_all_jobs():

    with _REGISTRY_LOCK:

        jobs = _read_jobs()

        # Latest submitted jobs appear first.
        jobs.sort(
            key=lambda job: job["created_at"],
            reverse=True
        )

        return jobs


# --------------------------------------------------
# GET ACTIVE JOBS
# --------------------------------------------------

def get_active_jobs():

    active_statuses = {
        "preparing",
        "queued",
        "running"
    }

    return [
        job for job in get_all_jobs()
        if job["status"] in active_statuses
    ]


# --------------------------------------------------
# MARK STALE JOBS AFTER APPLICATION RESTART
# --------------------------------------------------

def mark_interrupted_jobs():

    with _REGISTRY_LOCK:

        jobs = _read_jobs()

        changed = False

        active_statuses = {
            "preparing",
            "queued",
            "running"
        }

        for job in jobs:

            if job["status"] in active_statuses:

                timestamp = _current_timestamp()

                job["status"] = "interrupted"
                job["stage"] = "Application restarted"
                job["message"] = (
                    "Application restarted before this job completed. "
                    "Check ERP records before submitting it again."
                )
                job["completed_at"] = timestamp

                job["history"].append({
                    "timestamp": timestamp,
                    "stage": "interrupted",
                    "status": "interrupted",
                    "message": job["message"]
                })

                changed = True

        if changed:
            _write_jobs(jobs)

        return changed

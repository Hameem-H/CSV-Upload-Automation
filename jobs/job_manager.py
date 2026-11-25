
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
from pathlib import Path

from automation.browser_manager import submit_department_task
from config.departments import get_department

from core.parser import parse_scanner_txt
from core.duplicate_processor import build_outputs
from core.report_generator import generate_processing_summary

from storage.file_manager import save_outputs

from automation.erp_client import (
    upload_and_process,
    ERPStageError,
)

from jobs.job_registry import (
    create_job,
    update_job,
    get_job,
    get_all_jobs,
    get_active_jobs,
    mark_interrupted_jobs,
)


# --------------------------------------------------
# EXECUTION CONFIGURATION
# --------------------------------------------------

# Multiple TXT files can be prepared simultaneously.
_PREPARATION_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="Barcode-Preparation"
)

# ERP workers are managed by browser_manager.py.
# Each department has its own single-threaded worker.
# Different departments can run simultaneously.
# Jobs within the same department remain sequential.


# --------------------------------------------------
# JOB MANAGER INITIALIZATION
# --------------------------------------------------

_INITIALIZATION_LOCK = threading.Lock()
_INITIALIZED = False


def initialize_job_manager():
    """
    Initialize the job manager once per application process.

    Jobs left active after an application restart are marked
    interrupted instead of being automatically retried.
    """

    global _INITIALIZED

    with _INITIALIZATION_LOCK:

        if _INITIALIZED:
            return

        mark_interrupted_jobs()

        _INITIALIZED = True


# --------------------------------------------------
# INTERNAL HELPERS
# --------------------------------------------------

def _make_job_id():

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    unique_part = uuid.uuid4().hex[:6].upper()

    return f"JOB_{timestamp}_{unique_part}"


def _json_safe(value):
    """
    Convert common Python values into JSON-compatible values.
    """

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]

    if value is None or isinstance(
        value,
        (str, int, float, bool)
    ):
        return value

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    return str(value)


def _fail_job(job_id, stage, error, erp_result=None):
    """
    Store a failed job without allowing an exception in the
    background worker to disappear silently.
    """

    update_job(
        job_id=job_id,
        status="failed",
        stage=stage,
        message=str(error),
        error=str(error),
        progress=100 if stage == "Preparation failed" else None,
        erp_result=_json_safe(erp_result)
        if erp_result is not None
        else None
    )


# --------------------------------------------------
# PUBLIC JOB SUBMISSION
# --------------------------------------------------

def submit_job(
    department_id,
    original_filename,
    original_file_bytes,
    storage_date
):
    """
    Create a job and immediately schedule its preparation.

    This function does not wait for TXT processing or ERP processing.
    """

    initialize_job_manager()

    department = get_department(department_id)

    if not original_file_bytes:
        raise ValueError("The uploaded TXT file is empty.")

    job_id = _make_job_id()

    create_job(
        job_id=job_id,
        department_id=department_id,
        department_name=department["name"],
        original_filename=original_filename,
        storage_date=storage_date
    )

    # Copy the bytes so the background task does not depend
    # on Streamlit's uploaded-file object.
    file_bytes = bytes(original_file_bytes)

    try:

        _PREPARATION_EXECUTOR.submit(
            _prepare_job,
            job_id,
            department_id,
            original_filename,
            file_bytes,
            storage_date
        )

    except Exception as error:

        _fail_job(
            job_id,
            "Preparation failed",
            error
        )

        raise

    return get_job(job_id)


# --------------------------------------------------
# PREPARATION WORKER
# --------------------------------------------------

def _prepare_job(
    job_id,
    department_id,
    original_filename,
    original_file_bytes,
    storage_date
):
    """
    Parse TXT, process duplicates, save output files,
    and submit the ERP task to its department worker.
    """

    try:

        department = get_department(department_id)

        processing_date = datetime.combine(
            storage_date,
            datetime.now().time()
        )

        # ------------------------------------------
        # STEP 1: PARSE TXT
        # ------------------------------------------

        update_job(
            job_id,
            status="preparing",
            stage="Parsing TXT",
            progress=10,
            message="Reading and validating scanner records."
        )

        valid_df, invalid_df = parse_scanner_txt(
            original_file_bytes
        )

        total_rows = len(valid_df)
        invalid_count = len(invalid_df)

        # ------------------------------------------
        # STEP 2: DUPLICATE PROCESSING
        # ------------------------------------------

        update_job(
            job_id,
            stage="Duplicate processing",
            progress=25,
            message="Checking duplicate barcode records."
        )

        (
            unique_df,
            duplicate_rows_df,
            duplicate_summary_df,
            total_rows,
            unique_count,
            duplicate_count
        ) = build_outputs(valid_df)

        # ------------------------------------------
        # STEP 3: SUMMARY GENERATION
        # ------------------------------------------

        update_job(
            job_id,
            stage="Generating summary",
            progress=40,
            message="Generating processing summary."
        )

        summary_text = generate_processing_summary(
            department_name=department["name"],
            original_filename=original_filename,
            total_rows=total_rows,
            unique_count=unique_count,
            duplicate_count=duplicate_count,
            invalid_count=invalid_count,
            processing_date=processing_date
        )

        # ------------------------------------------
        # STEP 4: SAVE OUTPUT FILES
        # ------------------------------------------

        update_job(
            job_id,
            stage="Saving output files",
            progress=50,
            message="Saving TXT, CSV and reports."
        )

        saved_files = save_outputs(
            department_id=department_id,
            original_file_bytes=original_file_bytes,
            original_filename=original_filename,
            unique_df=unique_df,
            duplicate_rows_df=duplicate_rows_df,
            duplicate_summary_df=duplicate_summary_df,
            invalid_df=invalid_df,
            total_rows=total_rows,
            unique_count=unique_count,
            duplicate_count=duplicate_count,
            summary_text=summary_text,
            processing_date=processing_date
        )

        saved_files = _json_safe(saved_files)

        metrics = {
            "total_rows": total_rows,
            "unique_count": unique_count,
            "duplicate_count": duplicate_count,
            "invalid_count": invalid_count,
        }

        update_job(
            job_id,
            stage="Output files saved",
            progress=60,
            message="TXT, ERP CSV and reports saved successfully.",
            saved_files=saved_files,
            metrics=metrics
        )

        # ------------------------------------------
        # STEP 5: ADD TO ERP QUEUE
        # ------------------------------------------

        erp_csv_path = Path(
            saved_files["erp_csv_path"]
        )

        if not erp_csv_path.is_file():
            raise FileNotFoundError(
                f"ERP CSV not found: {erp_csv_path}"
            )

        update_job(
            job_id,
            status="queued",
            stage="Waiting for ERP",
            progress=60,
            message=(
                "Preparation completed. "
                "Waiting for department ERP worker."
            )
        )

        # Submit to the dedicated department worker.
        # Different departments can execute concurrently.
        # The same department's jobs execute sequentially.
        submit_department_task(
            department_id,
            _run_erp_job,
            job_id,
            department_id,
            erp_csv_path,
        )

    except Exception as error:

        _fail_job(
            job_id,
            "Preparation failed",
            error
        )


# --------------------------------------------------
# ERP PROGRESS CALLBACK
# --------------------------------------------------

def _update_erp_progress(
    job_id,
    stage,
    message,
    state="running",
    details=None
):
    """
    Update the individual job's ERP progress.
    """

    current_job = get_job(job_id)

    if current_job is None:
        return

    current_progress = current_job.get("progress", 60) or 60

    # Move progress forward without reaching 100 before completion.
    new_progress = min(
        95,
        max(65, current_progress + 3)
    )

    if state.lower() in ("complete", "completed", "success"):
        new_progress = max(current_progress, 95)

    update_job(
        job_id,
        status="running",
        stage=stage.replace("_", " ").title(),
        progress=new_progress,
        message=message
    )


# --------------------------------------------------
# ERP WORKER
# --------------------------------------------------

def _run_erp_job(
    job_id,
    department_id,
    erp_csv_path
):
    """
    Runs inside the dedicated department worker thread.

    Playwright browser creation, usage and cleanup must remain
    on this same thread.
    """

    erp_result = None

    try:

        department = get_department(department_id)

        update_job(
            job_id,
            status="running",
            stage="Starting ERP",
            progress=65,
            message="ERP automation has started."
        )

        # Run the existing ERP workflow directly.
        # Do not submit another nested worker here.
        erp_result = upload_and_process(
            department=department,
            csv_path=erp_csv_path,
            department_id=department_id,
            progress_callback=lambda stage, message,
                                    state="running", details=None:
                _update_erp_progress(
                    job_id,
                    stage,
                    message,
                    state,
                    details
                )
        )

        erp_result = _json_safe(erp_result)

        if not isinstance(erp_result, dict):
            raise RuntimeError(
                "ERP workflow returned an invalid result."
            )

        if not erp_result.get("completion_verified", False):

            raise RuntimeError(
                "ERP workflow returned without verified completion. "
                "Check ERP records before attempting another upload."
            )

        update_job(
            job_id,
            status="completed",
            stage="ERP completed",
            progress=100,
            message="ERP processing completed and verified.",
            erp_result=erp_result
        )

    except ERPStageError as error:

        partial_result = error.result or erp_result

        _fail_job(
            job_id,
            "ERP processing failed",
            error,
            erp_result=partial_result
        )

    except Exception as error:

        _fail_job(
            job_id,
            "ERP processing failed",
            error,
            erp_result=erp_result
        )


# --------------------------------------------------
# PUBLIC JOB QUERY FUNCTIONS
# --------------------------------------------------

def get_job_details(job_id):
    return get_job(job_id)


def get_jobs():
    initialize_job_manager()
    return get_all_jobs()


def get_running_jobs():
    initialize_job_manager()
    return get_active_jobs()


def has_active_jobs():
    return len(get_running_jobs()) > 0

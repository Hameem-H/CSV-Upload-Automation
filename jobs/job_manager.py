
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
from pathlib import Path

from automation.browser_manager import submit_department_task
from automation.barcode_validator import validate_barcodes
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

_PREPARATION_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="Barcode-Preparation"
)


# --------------------------------------------------
# JOB MANAGER INITIALIZATION
# --------------------------------------------------

_INITIALIZATION_LOCK = threading.Lock()
_INITIALIZED = False


def initialize_job_manager():

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

    try:

        department = get_department(department_id)

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
        # STEP 3: QUEUE VALIDATION AND ERP
        # ------------------------------------------

        update_job(
            job_id,
            status="queued",
            stage="Waiting for barcode validation",
            progress=40,
            message=(
                "Duplicate processing completed. "
                "Waiting for department validation worker."
            )
        )

        # The department worker performs validation,
        # saves the corrected files and then runs ERP.
        submit_department_task(
            department_id,
            _validate_save_and_run_job,
            job_id,
            department_id,
            original_filename,
            original_file_bytes,
            storage_date,
            valid_df,
            unique_df,
            duplicate_rows_df,
            duplicate_summary_df,
            invalid_df,
            total_rows,
            unique_count,
            duplicate_count,
            invalid_count,
        )

    except Exception as error:

        _fail_job(
            job_id,
            "Preparation failed",
            error
        )


# --------------------------------------------------
# VALIDATION, SAVING AND ERP HANDOFF
# --------------------------------------------------

def _validate_save_and_run_job(
    job_id,
    department_id,
    original_filename,
    original_file_bytes,
    storage_date,
    valid_df,
    unique_df,
    duplicate_rows_df,
    duplicate_summary_df,
    invalid_df,
    total_rows,
    unique_count,
    duplicate_count,
    invalid_count,
):
    """
    Runs entirely on the department's dedicated worker.

    1. Validate unique barcodes.
    2. Remove wrong barcodes.
    3. Generate summary.
    4. Save corrected files.
    5. Run the existing ERP workflow.
    """

    department = get_department(department_id)

    # ----------------------------------------------
    # STEP 4: BARCODE VALIDATION
    # ----------------------------------------------

    try:

        update_job(
            job_id,
            status="validating",
            stage="Barcode validation",
            progress=45,
            message="Uploading unique barcodes for validation."
        )

        wrong_barcodes = validate_barcodes(
            department_id=department_id,
            department=department,
            unique_df=unique_df,
        )

    except Exception as error:

        _fail_job(
            job_id,
            "Barcode validation failed",
            error
        )

        return

    # ----------------------------------------------
    # STEP 5: REMOVE WRONG BARCODES
    # ----------------------------------------------

    wrong_set = set(wrong_barcodes)

    barcode_values = (
        unique_df["BarcodeNumber"]
        .astype(str)
        .str.strip()
    )

    wrong_mask = barcode_values.isin(wrong_set)

    wrong_barcodes_df = (
        unique_df.loc[wrong_mask, ["BarcodeNumber"]]
        .drop_duplicates()
        .copy()
    )

    corrected_unique_df = unique_df.loc[
        ~wrong_mask
    ].copy()

    final_unique_count = len(corrected_unique_df)

    update_job(
        job_id,
        stage="Removing wrong barcodes",
        progress=52,
        message=(
            f"Validation completed. "
            f"{len(wrong_set)} wrong barcode(s) found and removed."
        )
    )

    # ----------------------------------------------
    # STEP 6: GENERATE SUMMARY
    # ----------------------------------------------

    processing_date = datetime.combine(
        storage_date,
        datetime.now().time()
    )

    summary_text = generate_processing_summary(
        department_name=department["name"],
        original_filename=original_filename,
        total_rows=total_rows,
        unique_count=final_unique_count,
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        processing_date=processing_date
    )

    # ----------------------------------------------
    # STEP 7: SAVE CORRECTED OUTPUT FILES
    # ----------------------------------------------

    try:

        update_job(
            job_id,
            stage="Saving output files",
            progress=57,
            message="Saving original TXT and corrected CSV."
        )

        saved_files = save_outputs(
            department_id=department_id,
            original_file_bytes=original_file_bytes,
            original_filename=original_filename,
            unique_df=corrected_unique_df,
            duplicate_rows_df=duplicate_rows_df,
            duplicate_summary_df=duplicate_summary_df,
            invalid_df=invalid_df,
            total_rows=total_rows,
            unique_count=final_unique_count,
            duplicate_count=duplicate_count,
            summary_text=summary_text,
            processing_date=processing_date,
            wrong_barcodes_df=wrong_barcodes_df,
        )

        saved_files = _json_safe(saved_files)

    except Exception as error:

        _fail_job(
            job_id,
            "Saving output failed",
            error
        )

        return

    # ----------------------------------------------
    # STEP 8: UPDATE JOB METRICS
    # ----------------------------------------------

    metrics = {
        "total_rows": total_rows,
        "invalid_count": invalid_count,
        "duplicate_count": duplicate_count,
        "unique_count_before_validation": unique_count,
        "wrong_barcode_count": len(wrong_set),
        "final_unique_count": final_unique_count,
    }

    update_job(
        job_id,
        status="running",
        stage="Output files saved",
        progress=65,
        message=(
            "Barcode validation completed. "
            "Corrected files saved. Starting ERP."
        ),
        saved_files=saved_files,
        metrics=metrics
    )

    # ----------------------------------------------
    # STEP 9: START ERP ON THE SAME WORKER
    # ----------------------------------------------

    erp_csv_path = Path(
        saved_files["erp_csv_path"]
    )

    if not erp_csv_path.is_file():

        _fail_job(
            job_id,
            "ERP file missing",
            FileNotFoundError(
                f"ERP CSV not found: {erp_csv_path}"
            )
        )

        return

    _run_erp_job(
        job_id,
        department_id,
        erp_csv_path
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

    current_job = get_job(job_id)

    if current_job is None:
        return

    current_progress = current_job.get("progress", 65) or 65

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

        _fail_job(
            job_id,
            "ERP processing failed",
            error,
            erp_result=error.result or erp_result
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

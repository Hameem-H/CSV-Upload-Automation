import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .browser_manager import (
    get_or_create_browser_worker,
    set_active_page,
)
from .erp_helpers import (
    ERPStageError,
    notify,
    validate_configuration,
)
from .upload_handler import (
    login_to_erp,
    upload_csv,
)
from .stickering_workflow import (
    check_intermediate_page,
    process_stickering,
)
from .standard_workflow import (
    process_standard_department,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

ERP_USERNAME = os.getenv("ERP_USERNAME")
ERP_PASSWORD = os.getenv("ERP_PASSWORD")

PROCESS_TIMEOUT = 0
DEFAULT_TIMEOUT = PROCESS_TIMEOUT
PAGE_TIMEOUT = 30000


def _upload_and_process_worker(
    department,
    csv_path,
    timeout,
    progress_callback,
    department_id,
):
    page = None
    csv_path = Path(csv_path)

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"ERP CSV file not found: {csv_path}"
        )

    if not ERP_USERNAME or not ERP_PASSWORD:
        raise ERPStageError(
            "ERP_USERNAME or ERP_PASSWORD is missing "
            "from the project .env file."
        )

    validate_configuration(department)

    workflow = department.get("workflow", "three_page")

    if workflow not in ("three_page", "four_page"):
        raise ERPStageError(
            f"Unsupported ERP workflow: {workflow}"
        )

    if workflow == "four_page":
        required_urls = (
            "intermediate_url",
            "process_url",
        )

        missing = [
            key for key in required_urls
            if not department.get(key)
        ]

        if missing:
            raise ERPStageError(
                "Missing Standard workflow configuration: "
                + ", ".join(missing)
            )

    result = {
        "department": department["name"],
        "csv_file": str(csv_path),
        "csv_size": csv_path.stat().st_size,
        "success": False,
        "stages": {},
        "upload_http_status": None,
        "processing_time_seconds": None,
        "http_status": None,
        "completion_verified": False,
        "message": None,
    }

    try:
        notify(
            progress_callback,
            "browser",
            "Connecting to ERP browser...",
        )

        _, context = get_or_create_browser_worker(
            department_id
        )

        page = context.new_page()

        set_active_page(
            department_id,
            page
        )
        page.set_default_timeout(PAGE_TIMEOUT)

        notify(
            progress_callback,
            "browser",
            "ERP browser is ready.",
            "complete",
        )

        # ------------------------------------------
        # LOGIN
        # ------------------------------------------

        try:
            login_to_erp(
                page,
                department["upload_url"],
                progress_callback,
                result,
                ERP_USERNAME,
                ERP_PASSWORD,
            )

        except PlaywrightTimeoutError as error:
            result["stages"]["login"] = {
                "success": False,
                "url": page.url,
            }

            raise ERPStageError(
                "ERP login timed out or could not be verified.",
                result,
            ) from error

        # ------------------------------------------
        # PAGE 1 -> PAGE 2: CSV UPLOAD
        # ------------------------------------------

        try:
            upload_csv(
                page,
                csv_path,
                department["upload_url"],
                department["submit_url"],
                progress_callback,
                result,
            )

        except PlaywrightTimeoutError as error:
            result["stages"]["upload"] = {
                "success": False,
                "timeout": True,
                "current_url": page.url,
            }

            raise ERPStageError(
                "CSV upload timed out before its response "
                "or Page 2 could be verified. "
                "Check ERP records before retrying.",
                result,
            ) from error

        # ------------------------------------------
        # THREE-PAGE STICKERING WORKFLOW
        # ------------------------------------------

        if workflow == "three_page":

            try:
                check_intermediate_page(
                    page,
                    progress_callback,
                    result,
                )

            except PlaywrightTimeoutError as error:
                result["stages"]["intermediate_page"] = {
                    "success": False,
                    "url": page.url,
                }

                raise ERPStageError(
                    "Stickering intermediate page opened, "
                    "but its Submit button could not be found.",
                    result,
                ) from error

            process_stickering(
                page,
                department["process_url"],
                progress_callback,
                result,
            )

        # ------------------------------------------
        # FOUR-PAGE STANDARD WORKFLOW
        # ------------------------------------------

        elif workflow == "four_page":

            process_standard_department(
                page,
                department["intermediate_url"],
                department["process_url"],
                progress_callback,
                result,
            )

        return result

    except ERPStageError:
        raise

    except Exception as error:
        result["message"] = str(error)

        raise ERPStageError(
            f"ERP automation failed: {error}",
            result,
        ) from error
    finally:
        if page is not None:
            try:
                page.close()
            except Exception as error:
                print("Page close warning:", error)

        set_active_page(department_id, None)

def upload_and_process(
    department,
    csv_path,
    timeout=DEFAULT_TIMEOUT,
    progress_callback=None,
    department_id=None,
):
    if not department_id:
        raise ValueError(
            "department_id is required for parallel ERP processing."
        )

    # This function runs directly on the department's
    # dedicated worker thread. Do not submit it to another worker.
    return _upload_and_process_worker(
        department,
        csv_path,
        timeout,
        progress_callback,
        department_id,
    )
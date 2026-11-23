
import os
import time
import threading
import queue

from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

ERP_USERNAME = os.getenv("ERP_USERNAME")
ERP_PASSWORD = os.getenv("ERP_PASSWORD")

# Final ProcessSticker.php response:
# 0 means wait indefinitely.
PROCESS_TIMEOUT = 0

DEFAULT_TIMEOUT = PROCESS_TIMEOUT

LOGIN_TIMEOUT = 30000
PAGE_TIMEOUT = 30000
UPLOAD_TIMEOUT = 60000


# --------------------------------------------------
# CUSTOM ERP EXCEPTION
# --------------------------------------------------

class ERPStageError(Exception):

    def __init__(self, message, result=None):

        super().__init__(message)

        self.result = result or {}


# --------------------------------------------------
# PERSISTENT PLAYWRIGHT WORKER
# --------------------------------------------------

_WORKER = ThreadPoolExecutor(
    max_workers=1,
    thread_name_prefix="ERP-Playwright",
)

_STATE_LOCK = threading.Lock()

_BROWSER_OPEN = False

_ACTIVE_PLAYWRIGHT = None
_ACTIVE_BROWSER = None
_ACTIVE_CONTEXT = None
_ACTIVE_PAGE = None


def _set_browser_state(is_open):

    global _BROWSER_OPEN

    with _STATE_LOCK:

        _BROWSER_OPEN = bool(is_open)


def is_erp_browser_open():

    """
    Thread-safe browser status check.
    """

    with _STATE_LOCK:

        return _BROWSER_OPEN


def _close_browser_worker():

    """
    Runs only inside the dedicated Playwright worker.
    """

    global _ACTIVE_PLAYWRIGHT
    global _ACTIVE_BROWSER
    global _ACTIVE_CONTEXT
    global _ACTIVE_PAGE

    print("\n========== CLOSING ERP BROWSER ==========")

    try:

        if _ACTIVE_CONTEXT is not None:

            try:
                _ACTIVE_CONTEXT.close()

            except Exception as error:

                print("Context close warning:", error)

        if (
            _ACTIVE_BROWSER is not None
            and _ACTIVE_BROWSER.is_connected()
        ):

            _ACTIVE_BROWSER.close()

            print("Chromium browser closed.")

    except Exception as error:

        print("Browser close warning:", error)

    finally:

        try:

            if _ACTIVE_PLAYWRIGHT is not None:

                _ACTIVE_PLAYWRIGHT.stop()

                print("Playwright stopped.")

        except Exception as error:

            print("Playwright stop warning:", error)

        finally:

            _ACTIVE_PAGE = None
            _ACTIVE_CONTEXT = None
            _ACTIVE_BROWSER = None
            _ACTIVE_PLAYWRIGHT = None

            _set_browser_state(False)

    return True


def close_erp_browser():

    """
    Close Chromium through the worker thread.
    """

    future = _WORKER.submit(
        _close_browser_worker
    )

    return future.result(timeout=30)


def _get_or_create_browser_worker():

    """
    Reuses an existing browser and context.
    Creates them if necessary.
    """

    global _ACTIVE_PLAYWRIGHT
    global _ACTIVE_BROWSER
    global _ACTIVE_CONTEXT
    global _ACTIVE_PAGE

    if (
        _ACTIVE_BROWSER is not None
        and _ACTIVE_BROWSER.is_connected()
        and _ACTIVE_CONTEXT is not None
    ):

        print("Reusing existing Chromium browser.")

        return _ACTIVE_BROWSER, _ACTIVE_CONTEXT

    # Clean up stale references.
    if _ACTIVE_PLAYWRIGHT is not None:

        try:
            _ACTIVE_PLAYWRIGHT.stop()

        except Exception:
            pass

    _ACTIVE_PAGE = None
    _ACTIVE_CONTEXT = None
    _ACTIVE_BROWSER = None
    _ACTIVE_PLAYWRIGHT = None

    _set_browser_state(False)

    print("Launching a new Chromium browser...")

    try:

        _ACTIVE_PLAYWRIGHT = sync_playwright().start()

        _ACTIVE_BROWSER = _ACTIVE_PLAYWRIGHT.chromium.launch(
            headless=False,
            slow_mo=300,
        )

        _ACTIVE_CONTEXT = _ACTIVE_BROWSER.new_context()

        _set_browser_state(True)

        print("Chromium browser is ready.")

        return _ACTIVE_BROWSER, _ACTIVE_CONTEXT

    except Exception:

        try:

            if _ACTIVE_CONTEXT is not None:
                _ACTIVE_CONTEXT.close()

        except Exception:
            pass

        try:

            if _ACTIVE_BROWSER is not None:
                _ACTIVE_BROWSER.close()

        except Exception:
            pass

        try:

            if _ACTIVE_PLAYWRIGHT is not None:
                _ACTIVE_PLAYWRIGHT.stop()

        except Exception:
            pass

        _ACTIVE_PAGE = None
        _ACTIVE_CONTEXT = None
        _ACTIVE_BROWSER = None
        _ACTIVE_PLAYWRIGHT = None

        _set_browser_state(False)

        raise


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def _get_page_path(url):

    return urlparse(url).path.rstrip("/").lower()


def _notify(
    callback,
    stage,
    message,
    state="running",
    details=None,
):

    if callback:

        try:

            callback(
                stage,
                message,
                state,
                details or {},
            )

        except Exception:
            pass


def _check_response_status(response, stage_name):

    if response.status >= 400:

        raise ERPStageError(
            f"{stage_name} failed with HTTP status "
            f"{response.status}."
        )


def _check_php_errors(response_text):

    error_markers = [
        "Fatal error",
        "Uncaught Error",
        "Uncaught mysqli_sql_exception",
        "Parse error",
    ]

    for marker in error_markers:

        if marker.lower() in response_text.lower():

            raise ERPStageError(
                f"PHP error detected in ERP response: {marker}"
            )


def _validate_configuration(department):

    required_urls = [
        "upload_url",
        "submit_url",
        "process_url",
    ]

    missing = [
        key
        for key in required_urls
        if not department.get(key)
    ]

    if missing:

        raise ValueError(
            f"Missing ERP URLs for {department['name']}: "
            f"{', '.join(missing)}"
        )


def _get_login_url(upload_url):

    parsed = urlparse(upload_url)

    base_path = parsed.path.split("/custom/")[0]

    return (
        f"{parsed.scheme}://{parsed.netloc}"
        f"{base_path}/login.php"
    )


def _read_response_text(response):

    try:

        return response.text()

    except Exception:

        return ""


# --------------------------------------------------
# STAGE 1: ERP LOGIN
# --------------------------------------------------

def _login_to_erp(page, upload_url, progress_callback, result):

    _notify(
        progress_callback,
        "login",
        "Opening ERP login page...",
    )

    page.goto(
        _get_login_url(upload_url),
        wait_until="domcontentloaded",
        timeout=LOGIN_TIMEOUT,
    )

    username_input = page.locator(
        'input[name="username"]'
    )

    password_input = page.locator(
        'input[name="pass"]'
    )

    # Reuse an existing ERP session if available.
    if (
        username_input.count() == 0
        or password_input.count() == 0
    ):

        if "menu.php" in _get_page_path(page.url):

            result["stages"]["login"] = {
                "success": True,
                "url": page.url,
                "reused_session": True,
            }

            _notify(
                progress_callback,
                "login",
                "Existing ERP login session is active.",
                "complete",
            )

            return

        raise ERPStageError(
            "ERP login fields were not found. "
            "Check the login page and browser session.",
            result,
        )

    username_input.fill(ERP_USERNAME)
    password_input.fill(ERP_PASSWORD)

    _notify(
        progress_callback,
        "login",
        "Submitting ERP login...",
    )

    page.locator(
        'input[name="login"]'
    ).click()

    page.wait_for_url(
        "**/menu.php",
        timeout=LOGIN_TIMEOUT,
    )

    result["stages"]["login"] = {
        "success": True,
        "url": page.url,
        "reused_session": False,
    }

    _notify(
        progress_callback,
        "login",
        "ERP login successful.",
        "complete",
    )


# --------------------------------------------------
# STAGE 2: CSV UPLOAD
# --------------------------------------------------

def _upload_csv(
    page,
    csv_path,
    upload_url,
    submit_url,
    progress_callback,
    result,
):

    _notify(
        progress_callback,
        "upload",
        "Opening ERP CSV upload page...",
    )

    page.goto(
        upload_url,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    print("\n========== CSV UPLOAD DEBUG ==========")
    print("Upload page URL:", page.url)

    # FIND CSV INPUT
    file_input = page.locator(
        'input[name="csv"]'
    )

    file_input.wait_for(
        state="attached",
        timeout=15000,
    )

    file_input.set_input_files(
        str(csv_path.resolve())
    )

    selected_filename = file_input.evaluate(
        "(el) => el.files.length ? el.files[0].name : null"
    )

    print("Selected CSV:", selected_filename)

    if not selected_filename:

        raise ERPStageError(
            "CSV file was not attached to the upload form.",
            result,
        )

    # FIND UPLOAD FORM
    upload_form = file_input.locator(
        "xpath=ancestor::form[1]"
    )

    if upload_form.count() == 0:

        raise ERPStageError(
            "Could not find the HTML form containing "
            "the CSV input.",
            result,
        )

    # FIND SUBMIT BUTTON
    submit_button = upload_form.locator(
        'input[name="Submit"], button[name="Submit"]'
    )

    if submit_button.count() == 0:

        submit_button = upload_form.locator(
            'input[type="submit"], button[type="submit"]'
        )

    print(
        "Submit button count:",
        submit_button.count(),
    )

    if submit_button.count() == 0:

        print("Upload form HTML:")

        print(
            upload_form.evaluate(
                "(el) => el.outerHTML"
            )
        )

        raise ERPStageError(
            "Submit button was not found in "
            "the CSV upload form.",
            result,
        )

    submit_button = submit_button.first

    submit_button.wait_for(
        state="visible",
        timeout=15000,
    )

    if not submit_button.is_enabled():

        raise ERPStageError(
            "The CSV upload Submit button is disabled.",
            result,
        )

    print(
        "Submit button HTML:",
        submit_button.evaluate(
            "(el) => el.outerHTML"
        ),
    )

    print(
        "Submit button visible:",
        submit_button.is_visible(),
    )

    print(
        "Submit button enabled:",
        submit_button.is_enabled(),
    )

    # DETERMINE EXPECTED POST URLS
    form_action = upload_form.evaluate(
        "(el) => el.action"
    )

    upload_host = urlparse(
        upload_url
    ).netloc.lower()

    expected_post_paths = {
        _get_page_path(upload_url),
        _get_page_path(submit_url),
        _get_page_path(form_action),
        _get_page_path(page.url),
    }

    print("Form action:", form_action)
    print("Expected POST paths:", expected_post_paths)

    # CLICK SUBMIT AND CAPTURE POST
    _notify(
        progress_callback,
        "upload",
        f"CSV {csv_path.name} attached. Clicking Submit...",
    )

    with page.expect_response(
        lambda response: (
            response.request.method.upper() == "POST"
            and urlparse(response.url).netloc.lower()
            == upload_host
            and _get_page_path(response.url)
            in expected_post_paths
        ),
        timeout=UPLOAD_TIMEOUT,
    ) as upload_response_info:

        submit_button.scroll_into_view_if_needed()

        submit_button.click(
            timeout=PAGE_TIMEOUT,
        )

    upload_response = upload_response_info.value

    result["upload_http_status"] = upload_response.status

    print("Upload POST response:", upload_response.status)
    print("Upload POST URL:", upload_response.url)

    _check_response_status(
        upload_response,
        "CSV upload",
    )

    upload_response_text = _read_response_text(
        upload_response
    )

    _check_php_errors(upload_response_text)

    # WAIT FOR INTERMEDIATE PAGE
    page.wait_for_url(
        lambda url: (
            _get_page_path(url)
            == _get_page_path(submit_url)
        ),
        timeout=30000,
    )

    print("Intermediate page reached:", page.url)

    result["stages"]["upload"] = {
        "success": True,
        "csv_file": csv_path.name,
        "http_status": upload_response.status,
        "post_url": upload_response.url,
        "url": page.url,
    }

    _notify(
        progress_callback,
        "upload",
        "CSV upload POST received. Intermediate page opened.",
        "complete",
        {
            "http_status": upload_response.status,
        },
    )


# --------------------------------------------------
# STAGE 3: INTERMEDIATE PROCESSING PAGE
# --------------------------------------------------

def _check_intermediate_page(
    page,
    progress_callback,
    result,
):

    _notify(
        progress_callback,
        "intermediate_page",
        "Checking ERP processing page...",
    )

    process_button = page.locator(
        'input[name="button"], button[name="button"]'
    )

    process_button.wait_for(
        state="visible",
        timeout=15000,
    )

    if not process_button.is_enabled():

        raise ERPStageError(
            "The final ERP processing button is disabled.",
            result,
        )

    result["stages"]["intermediate_page"] = {
        "success": True,
        "url": page.url,
    }

    _notify(
        progress_callback,
        "intermediate_page",
        "ERP processing page is ready.",
        "complete",
    )


# --------------------------------------------------
# STAGE 4: FINAL ERP PROCESSING
# --------------------------------------------------

def _process_erp(
    page,
    process_url,
    timeout,
    progress_callback,
    result,
):

    start_time = time.perf_counter()

    # IMPORTANT:
    # Playwright timeout=0 means wait indefinitely.
    # The timeout argument is intentionally ignored here.
    effective_timeout = 0

    process_path = _get_page_path(process_url)
    process_host = urlparse(process_url).netloc.lower()

    result["stages"]["processing"] = {
        "success": False,
        "started": True,
        "timeout": False,
        "wait_mode": "indefinite",
    }

    def elapsed_seconds():

        return round(
            time.perf_counter() - start_time,
            2,
        )

    # ----------------------------------------------
    # DEBUG: ALL POST REQUESTS
    # ----------------------------------------------

    def debug_request(request):

        if request.method.upper() == "POST":

            print("\n[POST REQUEST]")
            print("URL:", request.url)
            print("Method:", request.method)
            print("Time:", time.strftime("%H:%M:%S"))

    # ----------------------------------------------
    # DEBUG: PROCESS RESPONSE
    # ----------------------------------------------

    def debug_response(response):

        if (
            "ProcessSticker" in response.url
            or (
                response.request.method.upper() == "POST"
                and _get_page_path(response.url) == process_path
            )
        ):

            print("\n[PROCESS RESPONSE]")
            print("URL:", response.url)
            print("HTTP status:", response.status)
            print("Time:", time.strftime("%H:%M:%S"))

    # ----------------------------------------------
    # DEBUG: FAILED REQUESTS
    # ----------------------------------------------

    def debug_request_failed(request):

        if (
            request.method.upper() == "POST"
            or "ProcessSticker" in request.url
        ):

            print("\n[REQUEST FAILED]")
            print("URL:", request.url)
            print("Failure:", request.failure)

    print("\n========== FINAL ERP PROCESSING DEBUG ==========")
    print("Current page URL:", page.url)
    print("Expected process URL:", process_url)
    print("Expected process host:", process_host)
    print("Expected process path:", process_path)
    print("Response timeout: INDEFINITE")
    print("Start time:", time.strftime("%H:%M:%S"))

    # ----------------------------------------------
    # STEP 1: PREPARE PROCESS BUTTON
    # ----------------------------------------------

    _notify(
        progress_callback,
        "processing",
        "Preparing final ERP processing button...",
    )

    try:

        process_button = page.locator(
            'input[name="button"], button[name="button"]'
        ).first

        process_button.wait_for(
            state="visible",
            timeout=PAGE_TIMEOUT,
        )

        process_button.scroll_into_view_if_needed()

        if not process_button.is_enabled():

            raise ERPStageError(
                "The final ERP processing button is disabled.",
                result,
            )

        print("Process button is visible and enabled.")

    except PlaywrightTimeoutError as error:

        result["stages"]["processing"] = {
            "success": False,
            "error_type": "BUTTON_PREPARATION_TIMEOUT",
            "elapsed_seconds": elapsed_seconds(),
            "error": str(error),
        }

        result["success"] = False

        result["message"] = (
            "The final ERP processing button could not be prepared "
            "within 30 seconds. PHP processing was not confirmed."
        )

        print("\n[BUTTON PREPARATION TIMEOUT]")
        print("Elapsed:", elapsed_seconds())
        print("Error:", error)

        raise ERPStageError(
            result["message"],
            result,
        ) from error

    # ----------------------------------------------
    # STEP 2: REGISTER DEBUG LISTENERS
    # ----------------------------------------------

    page.on("request", debug_request)
    page.on("response", debug_response)
    page.on("requestfailed", debug_request_failed)

    request_submitted = False

    try:

        # ------------------------------------------
        # STEP 3: SUBMIT AND WAIT INDEFINITELY
        # ------------------------------------------

        _notify(
            progress_callback,
            "processing",
            "Submitting final processing request. Waiting indefinitely for ProcessSticker.php HTTP response...",
        )

        print(
            "\nWaiting indefinitely for matching "
            "ProcessSticker.php POST response..."
        )

        with page.expect_response(
            lambda response: (
                response.request.method.upper() == "POST"
                and _get_page_path(response.url) == process_path
            ),
            timeout=0,
        ) as response_info:

            try:

                process_button.click(
                    timeout=PAGE_TIMEOUT,
                    no_wait_after=True,
                )

                request_submitted = True

                print("\n[BUTTON CLICK COMPLETED]")
                print("Elapsed:", elapsed_seconds())

            except PlaywrightTimeoutError as error:

                print("\n[BUTTON CLICK TIMEOUT]")
                print("Elapsed:", elapsed_seconds())
                print("Error:", error)

                result["stages"]["processing"] = {
                    "success": False,
                    "error_type": "BUTTON_CLICK_TIMEOUT",
                    "elapsed_seconds": elapsed_seconds(),
                    "request_submitted": False,
                    "error": str(error),
                }

                result["success"] = False

                result["message"] = (
                    "Playwright could not complete the processing "
                    "button click within 30 seconds. "
                    "Check ERP records before retrying."
                )

                raise ERPStageError(
                    result["message"],
                    result,
                ) from error

        # ------------------------------------------
        # STEP 4: PHP RESPONSE RECEIVED
        # ------------------------------------------

        response = response_info.value

        elapsed = elapsed_seconds()
        response_status = response.status

        print("\n========== PHP RESPONSE RECEIVED ==========")
        print("Response URL:", response.url)
        print("HTTP status:", response_status)
        print("Elapsed seconds:", elapsed)

        result["processing_time_seconds"] = elapsed
        result["http_status"] = response_status
        result["completion_verified"] = response_status == 200

        result["stages"]["processing"] = {
            "success": response_status == 200,
            "http_status": response_status,
            "response_url": response.url,
            "processing_time_seconds": elapsed,
            "response_received": True,
            "request_submitted": request_submitted,
            "wait_mode": "indefinite",
        }

        if response_status == 200:

            result["success"] = True

            result["message"] = (
                "ERP processing completed successfully. "
                "ProcessSticker.php returned HTTP 200."
            )

            _notify(
                progress_callback,
                "processing",
                result["message"],
                "complete",
                {
                    "http_status": response_status,
                    "processing_time_seconds": elapsed,
                },
            )

            print(result["message"])

            return

        result["success"] = False

        result["message"] = (
            f"ERP processing failed. "
            f"ProcessSticker.php returned HTTP {response_status}."
        )

        result["stages"]["processing"]["error"] = result["message"]

        raise ERPStageError(
            result["message"],
            result,
        )

    except PlaywrightTimeoutError as error:

        # With timeout=0, the response wait itself should
        # not time out. This handler is retained for other
        # Playwright timeout errors.
        elapsed = elapsed_seconds()

        print("\n========== PLAYWRIGHT TIMEOUT ==========")
        print("Exception type:", type(error).__name__)
        print("Exception:", str(error))
        print("Elapsed seconds:", elapsed)
        print("Request submitted:", request_submitted)
        print("Current page URL:", page.url)

        result["processing_time_seconds"] = elapsed
        result["success"] = False

        result["stages"]["processing"] = {
            "success": False,
            "error_type": "PLAYWRIGHT_TIMEOUT",
            "response_received": False,
            "request_submitted": request_submitted,
            "processing_time_seconds": elapsed,
            "error": str(error),
        }

        result["message"] = (
            "A Playwright timeout occurred during final ERP "
            "processing. Check ERP records before retrying."
        )

        _notify(
            progress_callback,
            "processing",
            result["message"],
            "error",
        )

        raise ERPStageError(
            result["message"],
            result,
        ) from error

    except ERPStageError as error:

        if not error.result:

            error.result = result

        raise

    except Exception as error:

        elapsed = elapsed_seconds()

        print("\n========== PROCESSING ERROR ==========")
        print("Exception type:", type(error).__name__)
        print("Exception:", str(error))
        print("Elapsed seconds:", elapsed)

        result["processing_time_seconds"] = elapsed
        result["success"] = False

        result["stages"]["processing"] = {
            "success": False,
            "error_type": type(error).__name__,
            "processing_time_seconds": elapsed,
            "request_submitted": request_submitted,
            "error": str(error),
        }

        result["message"] = (
            "An error occurred during final ERP processing. "
            f"Details: {error}"
        )

        raise ERPStageError(
            result["message"],
            result,
        ) from error

    finally:

        # Avoid accumulating event listeners.
        page.remove_listener("request", debug_request)
        page.remove_listener("response", debug_response)
        page.remove_listener("requestfailed", debug_request_failed)


# --------------------------------------------------
# COMPLETE ERP WORKFLOW
# --------------------------------------------------

def _upload_and_process_worker(
    department,
    csv_path,
    timeout,
    progress_callback,
):

    """
    Runs inside the dedicated Playwright worker.
    All Playwright operations happen here.
    """

    global _ACTIVE_PAGE

    csv_path = Path(csv_path)

    # VALIDATION
    if not csv_path.is_file():

        raise FileNotFoundError(
            f"ERP CSV file not found: {csv_path}"
        )

    if not ERP_USERNAME or not ERP_PASSWORD:

        raise ERPStageError(
            "ERP_USERNAME or ERP_PASSWORD is missing "
            "from the project .env file."
        )

    _validate_configuration(department)

    department_name = department["name"]

    upload_url = department["upload_url"]
    submit_url = department["submit_url"]
    process_url = department["process_url"]

    result = {
        "department": department_name,
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

        # GET EXISTING BROWSER OR CREATE ONE
        _notify(
            progress_callback,
            "browser",
            "Connecting to ERP browser...",
        )

        browser, context = _get_or_create_browser_worker()

        # New tab for each upload.
        page = context.new_page()

        _ACTIVE_PAGE = page

        page.set_default_timeout(PAGE_TIMEOUT)

        _notify(
            progress_callback,
            "browser",
            "ERP browser is ready.",
            "complete",
        )

        # STAGE 1: LOGIN
        try:

            _login_to_erp(
                page,
                upload_url,
                progress_callback,
                result,
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

        # STAGE 2: CSV UPLOAD
        try:

            _upload_csv(
                page,
                csv_path,
                upload_url,
                submit_url,
                progress_callback,
                result,
            )

        except PlaywrightTimeoutError as error:

            result["stages"]["upload"] = {
                "success": False,
                "timeout": True,
                "current_url": page.url,
            }

            print("\nCSV UPLOAD TIMEOUT")
            print("Current URL:", page.url)

            raise ERPStageError(
                "CSV upload timed out before its response or "
                "intermediate page could be verified. "
                "Check ERP records before retrying.",
                result,
            ) from error

        # STAGE 3: INTERMEDIATE PAGE
        try:

            _check_intermediate_page(
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
                "ERP intermediate processing page opened, "
                "but its Submit button could not be found.",
                result,
            ) from error

        # STAGE 4: FINAL PROCESSING
        _process_erp(
            page,
            process_url,
            timeout,
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

    # Browser intentionally remains open.


# --------------------------------------------------
# PUBLIC ERP UPLOAD FUNCTION
# --------------------------------------------------

def upload_and_process(
    department,
    csv_path,
    timeout=DEFAULT_TIMEOUT,
    progress_callback=None,
):

    """
    Public function called by app.py.

    ERP work runs on the dedicated Playwright thread.
    Progress callbacks run on the calling Streamlit thread.
    """

    progress_queue = queue.Queue()

    def queue_progress(
        stage,
        message,
        state="running",
        details=None,
    ):

        progress_queue.put(
            (
                stage,
                message,
                state,
                details or {},
            )
        )

    future = _WORKER.submit(
        _upload_and_process_worker,
        department,
        csv_path,
        timeout,
        queue_progress if progress_callback else None,
    )

    # Wait for the worker while delivering progress.
    while not future.done():

        try:

            event = progress_queue.get(
                timeout=0.15
            )

            if progress_callback:

                _notify(
                    progress_callback,
                    event[0],
                    event[1],
                    event[2],
                    event[3],
                )

        except queue.Empty:

            pass

    # Deliver remaining progress messages.
    while True:

        try:

            event = progress_queue.get_nowait()

            if progress_callback:

                _notify(
                    progress_callback,
                    event[0],
                    event[1],
                    event[2],
                    event[3],
                )

        except queue.Empty:

            break

    return future.result()

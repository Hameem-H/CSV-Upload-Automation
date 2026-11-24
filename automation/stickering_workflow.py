import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .erp_helpers import ERPStageError, get_page_path, notify


PAGE_TIMEOUT = 30000


def check_intermediate_page(page, progress_callback, result):
    notify(
        progress_callback,
        "intermediate_page",
        "Checking ERP processing page...",
    )

    button = page.locator(
        'input[name="button"], button[name="button"]'
    )
    button.wait_for(state="visible", timeout=15000)

    if not button.is_enabled():
        raise ERPStageError(
            "The final ERP processing button is disabled.",
            result,
        )

    result["stages"]["intermediate_page"] = {
        "success": True,
        "url": page.url,
    }

    notify(
        progress_callback,
        "intermediate_page",
        "ERP processing page is ready.",
        "complete",
    )


def process_stickering(page, process_url, progress_callback, result):
    start_time = time.perf_counter()
    process_path = get_page_path(process_url)

    result["stages"]["processing"] = {
        "success": False,
        "started": True,
        "timeout": False,
        "wait_mode": "indefinite",
    }

    def elapsed():
        return round(time.perf_counter() - start_time, 2)

    def debug_request(request):
        if request.method.upper() == "POST":
            print("\\n[POST REQUEST]")
            print("URL:", request.url)
            print("Time:", time.strftime("%H:%M:%S"))

    def debug_response(response):
        if (
            "ProcessSticker" in response.url
            or (
                response.request.method.upper() == "POST"
                and get_page_path(response.url) == process_path
            )
        ):
            print("\\n[PROCESS RESPONSE]")
            print("URL:", response.url)
            print("HTTP status:", response.status)

    def debug_request_failed(request):
        if (
            request.method.upper() == "POST"
            or "ProcessSticker" in request.url
        ):
            print("\\n[REQUEST FAILED]")
            print("URL:", request.url)
            print("Failure:", request.failure)

    print("\\n========== STICKERING PROCESSING ==========")
    print("Current page:", page.url)
    print("Expected final URL:", process_url)
    print("Waiting indefinitely for HTTP response.")

    notify(
        progress_callback,
        "processing",
        "Preparing final ERP processing button...",
    )

    try:
        button = page.locator(
            'input[name="button"], button[name="button"]'
        ).first
        button.wait_for(state="visible", timeout=PAGE_TIMEOUT)
        button.scroll_into_view_if_needed()

        if not button.is_enabled():
            raise ERPStageError(
                "The final ERP processing button is disabled.",
                result,
            )

    except PlaywrightTimeoutError as error:
        result["stages"]["processing"] = {
            "success": False,
            "error_type": "BUTTON_PREPARATION_TIMEOUT",
            "elapsed_seconds": elapsed(),
            "error": str(error),
        }
        result["success"] = False
        result["message"] = (
            "The final ERP processing button could not be prepared "
            "within 30 seconds. PHP processing was not confirmed."
        )
        raise ERPStageError(result["message"], result) from error

    page.on("request", debug_request)
    page.on("response", debug_response)
    page.on("requestfailed", debug_request_failed)

    request_submitted = False

    try:
        notify(
            progress_callback,
            "processing",
            "Submitting final Stickering processing request. "
            "Waiting indefinitely for ProcessSticker.php HTTP response...",
        )

        with page.expect_response(
            lambda response: (
                response.request.method.upper() == "POST"
                and get_page_path(response.url) == process_path
            ),
            timeout=0,
        ) as response_info:
            button.click(timeout=PAGE_TIMEOUT, no_wait_after=True)
            request_submitted = True
            print("[BUTTON CLICK COMPLETED]")

        response = response_info.value
        duration = elapsed()

        result["processing_time_seconds"] = duration
        result["http_status"] = response.status
        result["completion_verified"] = response.status == 200

        result["stages"]["processing"] = {
            "success": response.status == 200,
            "http_status": response.status,
            "response_url": response.url,
            "processing_time_seconds": duration,
            "response_received": True,
            "request_submitted": request_submitted,
            "wait_mode": "indefinite",
        }

        if response.status != 200:
            result["success"] = False
            result["message"] = (
                f"ERP processing failed. ProcessSticker.php returned "
                f"HTTP {response.status}."
            )
            raise ERPStageError(result["message"], result)

        result["success"] = True
        result["message"] = (
            "ERP processing completed successfully. "
            "ProcessSticker.php returned HTTP 200."
        )

        notify(
            progress_callback,
            "processing",
            result["message"],
            "complete",
            {
                "http_status": response.status,
                "processing_time_seconds": duration,
            },
        )

    except PlaywrightTimeoutError as error:
        duration = elapsed()
        result["processing_time_seconds"] = duration
        result["success"] = False
        result["stages"]["processing"] = {
            "success": False,
            "error_type": "PLAYWRIGHT_TIMEOUT",
            "response_received": False,
            "request_submitted": request_submitted,
            "processing_time_seconds": duration,
            "error": str(error),
        }
        result["message"] = (
            "A Playwright timeout occurred during final ERP processing. "
            "Check ERP records before retrying."
        )
        raise ERPStageError(result["message"], result) from error

    except ERPStageError as error:
        if not error.result:
            error.result = result
        raise

    except Exception as error:
        duration = elapsed()
        result["processing_time_seconds"] = duration
        result["success"] = False
        result["stages"]["processing"] = {
            "success": False,
            "error_type": type(error).__name__,
            "processing_time_seconds": duration,
            "request_submitted": request_submitted,
            "error": str(error),
        }
        result["message"] = (
            "An error occurred during final ERP processing. "
            f"Details: {error}"
        )
        raise ERPStageError(result["message"], result) from error

    finally:
        page.remove_listener("request", debug_request)
        page.remove_listener("response", debug_response)
        page.remove_listener("requestfailed", debug_request_failed)

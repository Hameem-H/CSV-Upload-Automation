
import time
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .erp_helpers import (
    ERPStageError,
    check_php_errors,
    check_response_status,
    get_page_path,
    notify,
    read_response_text,
)


PAGE_TIMEOUT = 30000


def process_standard_department(
    page,
    intermediate_url,
    process_url,
    progress_callback,
    result,
):
    """
    Standard four-page workflow.

    Page 1 -> Page 2 is handled by upload_handler.upload_csv().

    This function handles:
        Page 2 -> Page 3: Click Submit and verify HTTP response.
        Page 3 -> Page 4: Click final button and verify HTTP response.
    """

    # --------------------------------------------------
    # PAGE 2: Submit uploaded CSV and verify Page 3 POST
    # --------------------------------------------------

    notify(
        progress_callback,
        "page2_submit",
        "Checking the second ERP page...",
    )

    page2_button = page.locator(
        'input[name="button"], button[name="button"]'
    ).first

    try:
        page2_button.wait_for(
            state="visible",
            timeout=PAGE_TIMEOUT,
        )

        if not page2_button.is_enabled():
            raise ERPStageError(
                "Page 2 Submit button is disabled.",
                result,
            )

        notify(
            progress_callback,
            "page2_submit",
            "Page 2 is ready. Clicking Submit...",
        )

        page2_button.scroll_into_view_if_needed()

        intermediate_host = urlparse(
            intermediate_url
        ).netloc.lower()

        intermediate_path = get_page_path(
            intermediate_url
        )

        # Capture the actual Page 3 POST response.
        # Do not use the browser URL as the success condition.
        with page.expect_response(
            lambda response: (
                response.request.method.upper() == "POST"
                and urlparse(response.url).netloc.lower()
                == intermediate_host
                and get_page_path(response.url)
                == intermediate_path
            ),
            timeout=0,
        ) as response_info:

            page2_button.click(
                timeout=PAGE_TIMEOUT,
                no_wait_after=True,
            )

        response = response_info.value

        # Verify the HTTP response.
        check_response_status(
            response,
            "Page 2 to Page 3 processing",
        )

        # Verify the PHP response content.
        page3_response_text = read_response_text(
            response
        )

        check_php_errors(
            page3_response_text
        )

        # Allow Playwright to finish updating the page.
        # The HTTP response above remains our confirmation.
        try:
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )
        except PlaywrightTimeoutError:
            pass

        result["stages"]["page2_submit"] = {
            "success": True,
            "http_status": response.status,
            "url": response.url,
        }

        notify(
            progress_callback,
            "page2_submit",
            "Page 2 submitted. Page 3 response received.",
            "complete",
            {
                "http_status": response.status,
            },
        )

    except ERPStageError:
        raise

    except PlaywrightTimeoutError as error:
        result["stages"]["page2_submit"] = {
            "success": False,
            "expected_url": intermediate_url,
            "current_url": page.url,
            "timeout": True,
        }

        raise ERPStageError(
            "Page 2 submission did not produce the expected "
            "Page 3 HTTP response. Check ERP records before retrying.",
            result,
        ) from error

    except Exception as error:
        result["stages"]["page2_submit"] = {
            "success": False,
            "current_url": page.url,
            "error": str(error),
        }

        raise ERPStageError(
            f"Page 2 submission failed: {error}. "
            "Check ERP records before retrying.",
            result,
        ) from error

    # --------------------------------------------------
    # PAGE 3: Wait for intermediate processing page button
    # --------------------------------------------------

    notify(
        progress_callback,
        "intermediate_page",
        "Waiting for the Page 3 processing button...",
    )

    final_button = page.locator(
        'input[name="button"], button[name="button"]'
    ).first

    try:
        final_button.wait_for(
            state="visible",
            timeout=PAGE_TIMEOUT,
        )

        if not final_button.is_enabled():
            raise ERPStageError(
                "Page 3 final processing button is disabled.",
                result,
            )

    except PlaywrightTimeoutError as error:
        result["stages"]["intermediate_page"] = {
            "success": False,
            "url": page.url,
        }

        raise ERPStageError(
            "Page 3 HTTP response was received, but its "
            "final processing button could not be found.",
            result,
        ) from error

    result["stages"]["intermediate_page"] = {
        "success": True,
        "url": page.url,
    }

    notify(
        progress_callback,
        "intermediate_page",
        "Page 3 is ready.",
        "complete",
    )

    # --------------------------------------------------
    # PAGE 4: Final processing and HTTP response verification
    # --------------------------------------------------

    notify(
        progress_callback,
        "final_processing",
        "Starting final ERP processing...",
    )

    process_host = urlparse(
        process_url
    ).netloc.lower()

    process_path = get_page_path(
        process_url
    )

    start_time = time.monotonic()

    try:
        with page.expect_response(
            lambda response: (
                response.request.method.upper() == "POST"
                and urlparse(response.url).netloc.lower()
                == process_host
                and get_page_path(response.url)
                == process_path
            ),
            timeout=0,
        ) as response_info:

            final_button.scroll_into_view_if_needed()

            final_button.click(
                timeout=PAGE_TIMEOUT,
                no_wait_after=True,
            )

        response = response_info.value

        processing_time = round(
            time.monotonic() - start_time,
            2,
        )

        result["http_status"] = response.status
        result["processing_time_seconds"] = processing_time

        check_response_status(
            response,
            "Standard final processing",
        )

        check_php_errors(
            read_response_text(response)
        )

        result["stages"]["final_processing"] = {
            "success": True,
            "http_status": response.status,
            "url": response.url,
            "processing_time_seconds": processing_time,
        }

        result["success"] = True
        result["completion_verified"] = True

        notify(
            progress_callback,
            "final_processing",
            "Final ERP processing completed successfully.",
            "complete",
            {
                "http_status": response.status,
                "processing_time_seconds": processing_time,
            },
        )

        return result

    except PlaywrightTimeoutError as error:
        result["stages"]["final_processing"] = {
            "success": False,
            "timeout": True,
            "current_url": page.url,
        }

        raise ERPStageError(
            "The final processing HTTP response was not received. "
            "Check ERP records before retrying.",
            result,
        ) from error

    except ERPStageError:
        raise

    except Exception as error:
        result["stages"]["final_processing"] = {
            "success": False,
            "current_url": page.url,
            "error": str(error),
        }

        raise ERPStageError(
            f"Standard final processing failed: {error}. "
            "Check ERP records before retrying.",
            result,
        ) from error

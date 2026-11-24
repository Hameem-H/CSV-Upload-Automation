from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .erp_helpers import (
    ERPStageError,
    check_php_errors,
    check_response_status,
    get_login_url,
    get_page_path,
    notify,
    read_response_text,
)


LOGIN_TIMEOUT = 30000
PAGE_TIMEOUT = 30000
UPLOAD_TIMEOUT = 60000


def login_to_erp(page, upload_url, progress_callback, result,
                 username, password):
    notify(progress_callback, "login", "Opening ERP login page...")

    page.goto(
        get_login_url(upload_url),
        wait_until="domcontentloaded",
        timeout=LOGIN_TIMEOUT,
    )

    username_input = page.locator('input[name="username"]')
    password_input = page.locator('input[name="pass"]')

    if username_input.count() == 0 or password_input.count() == 0:
        if "menu.php" in get_page_path(page.url):
            result["stages"]["login"] = {
                "success": True,
                "url": page.url,
                "reused_session": True,
            }
            notify(
                progress_callback,
                "login",
                "Existing ERP login session is active.",
                "complete",
            )
            return

        raise ERPStageError(
            "ERP login fields were not found. Check the login page and browser session.",
            result,
        )

    username_input.fill(username)
    password_input.fill(password)

    notify(progress_callback, "login", "Submitting ERP login...")
    page.locator('input[name="login"]').click()
    page.wait_for_url("**/menu.php", timeout=LOGIN_TIMEOUT)

    result["stages"]["login"] = {
        "success": True,
        "url": page.url,
        "reused_session": False,
    }

    notify(
        progress_callback,
        "login",
        "ERP login successful.",
        "complete",
    )


def upload_csv(page, csv_path, upload_url, submit_url,
               progress_callback, result):
    notify(
        progress_callback,
        "upload",
        "Opening ERP CSV upload page...",
    )

    page.goto(
        upload_url,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    print("\\n========== CSV UPLOAD DEBUG ==========")
    print("Upload page URL:", page.url)

    file_input = page.locator('input[name="csv"]')
    file_input.wait_for(state="attached", timeout=15000)
    file_input.set_input_files(str(csv_path.resolve()))

    selected_filename = file_input.evaluate(
        "(el) => el.files.length ? el.files[0].name : null"
    )
    print("Selected CSV:", selected_filename)

    if not selected_filename:
        raise ERPStageError(
            "CSV file was not attached to the upload form.",
            result,
        )

    upload_form = file_input.locator("xpath=ancestor::form[1]")
    if upload_form.count() == 0:
        raise ERPStageError(
            "Could not find the HTML form containing the CSV input.",
            result,
        )

    submit_button = upload_form.locator(
        'input[name="Submit"], button[name="Submit"]'
    )
    if submit_button.count() == 0:
        submit_button = upload_form.locator(
            'input[type="submit"], button[type="submit"]'
        )

    print("Submit button count:", submit_button.count())

    if submit_button.count() == 0:
        print(upload_form.evaluate("(el) => el.outerHTML"))
        raise ERPStageError(
            "Submit button was not found in the CSV upload form.",
            result,
        )

    submit_button = submit_button.first
    submit_button.wait_for(state="visible", timeout=15000)

    if not submit_button.is_enabled():
        raise ERPStageError(
            "The CSV upload Submit button is disabled.",
            result,
        )

    form_action = upload_form.evaluate("(el) => el.action")
    upload_host = urlparse(upload_url).netloc.lower()

    expected_post_paths = {
        get_page_path(upload_url),
        get_page_path(submit_url),
        get_page_path(form_action),
        get_page_path(page.url),
    }

    print("Form action:", form_action)
    print("Expected POST paths:", expected_post_paths)

    notify(
        progress_callback,
        "upload",
        f"CSV {csv_path.name} attached. Clicking Submit...",
    )

    with page.expect_response(
        lambda response: (
            response.request.method.upper() == "POST"
            and urlparse(response.url).netloc.lower() == upload_host
            and get_page_path(response.url) in expected_post_paths
        ),
        timeout=UPLOAD_TIMEOUT,
    ) as response_info:
        submit_button.scroll_into_view_if_needed()
        submit_button.click(timeout=PAGE_TIMEOUT)

    response = response_info.value
    result["upload_http_status"] = response.status

    print("Upload POST response:", response.status)
    print("Upload POST URL:", response.url)

    check_response_status(response, "CSV upload")
    check_php_errors(read_response_text(response))

    page.wait_for_url(
        lambda url: get_page_path(url) == get_page_path(submit_url),
        timeout=30000,
    )

    result["stages"]["upload"] = {
        "success": True,
        "csv_file": csv_path.name,
        "http_status": response.status,
        "post_url": response.url,
        "url": page.url,
    }

    notify(
        progress_callback,
        "upload",
        "CSV upload POST received. Intermediate page opened.",
        "complete",
        {"http_status": response.status},
    )


import threading
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright


# One dedicated worker per department.
# Each worker owns its Playwright objects.
_WORKERS = {}

# Browser sessions, indexed by department ID.
_SESSIONS = {}

_STATE_LOCK = threading.RLock()


def _get_worker(department_id):
    if not department_id:
        raise ValueError("A department ID is required.")

    with _STATE_LOCK:
        if department_id not in _WORKERS:
            worker_name = str(department_id).replace("_", "-")

            _WORKERS[department_id] = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix=f"ERP-{worker_name}",
            )

        return _WORKERS[department_id]


def submit_department_task(department_id, function, *args, **kwargs):
    """
    Submit work to the dedicated worker for a department.
    Jobs within the same department execute sequentially.
    """

    worker = _get_worker(department_id)

    return worker.submit(function, *args, **kwargs)


def set_active_page(department_id, page):
    with _STATE_LOCK:
        session = _SESSIONS.get(department_id)

        if session is not None:
            session["page"] = page


def is_erp_browser_open():
    with _STATE_LOCK:
        return any(
            session.get("is_open", False)
            for session in _SESSIONS.values()
        )


def get_or_create_browser_worker(department_id):
    """
    Must be called from the department's dedicated worker thread.
    """

    with _STATE_LOCK:
        session = _SESSIONS.get(department_id)

    if session is not None:
        browser = session["browser"]
        context = session["context"]

        if browser.is_connected():
            print(
                f"Reusing ERP browser for {department_id}."
            )
            return browser, context

        # Browser was disconnected. Clean up its old session.
        close_browser_worker(department_id)

    print(
        f"Launching ERP browser for {department_id}..."
    )

    playwright = None
    browser = None
    context = None

    try:
        playwright = sync_playwright().start()

        browser = playwright.chromium.launch(
            headless=False,
            slow_mo=300,
        )

        context = browser.new_context()

        session = {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "page": None,
            "is_open": True,
        }

        with _STATE_LOCK:
            _SESSIONS[department_id] = session

        print(
            f"ERP browser ready for {department_id}."
        )

        return browser, context

    except Exception:
        try:
            if context:
                context.close()
        except Exception:
            pass

        try:
            if browser:
                browser.close()
        except Exception:
            pass

        try:
            if playwright:
                playwright.stop()
        except Exception:
            pass

        raise


def close_browser_worker(department_id):
    """
    Close one department's browser.
    Must execute on that department's worker thread.
    """

    print(
        f"Closing ERP browser for {department_id}..."
    )

    with _STATE_LOCK:
        session = _SESSIONS.get(department_id)

    if session is None:
        return True

    try:
        page = session.get("page")
        if page is not None:
            try:
                page.close()
            except Exception:
                pass

        context = session.get("context")
        if context is not None:
            try:
                context.close()
            except Exception as error:
                print("Context close warning:", error)

        browser = session.get("browser")
        if browser is not None:
            try:
                if browser.is_connected():
                    browser.close()
            except Exception as error:
                print("Browser close warning:", error)

        playwright = session.get("playwright")
        if playwright is not None:
            try:
                playwright.stop()
            except Exception as error:
                print("Playwright stop warning:", error)

    finally:
        with _STATE_LOCK:
            _SESSIONS.pop(department_id, None)

    print(
        f"ERP browser closed for {department_id}."
    )

    return True


def close_erp_browser():
    """
    Close all department browsers safely.

    Each browser is closed by its own worker thread.
    """

    with _STATE_LOCK:
        department_ids = list(_WORKERS.keys())

    futures = []

    for department_id in department_ids:
        worker = _get_worker(department_id)

        futures.append(
            worker.submit(
                close_browser_worker,
                department_id,
            )
        )

    results = []

    for future in futures:
        results.append(
            future.result(timeout=30)
        )

    return all(results)

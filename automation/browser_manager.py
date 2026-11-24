import threading
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright


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


def set_active_page(page):
    global _ACTIVE_PAGE
    _ACTIVE_PAGE = page


def set_browser_state(is_open):
    global _BROWSER_OPEN
    with _STATE_LOCK:
        _BROWSER_OPEN = bool(is_open)


def is_erp_browser_open():
    with _STATE_LOCK:
        return _BROWSER_OPEN


def close_browser_worker():
    global _ACTIVE_PLAYWRIGHT, _ACTIVE_BROWSER
    global _ACTIVE_CONTEXT, _ACTIVE_PAGE

    print("\\n========== CLOSING ERP BROWSER ==========")

    try:
        if _ACTIVE_CONTEXT is not None:
            try:
                _ACTIVE_CONTEXT.close()
            except Exception as error:
                print("Context close warning:", error)

        if _ACTIVE_BROWSER is not None and _ACTIVE_BROWSER.is_connected():
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
            set_browser_state(False)

    return True


def close_erp_browser():
    return _WORKER.submit(close_browser_worker).result(timeout=30)


def get_or_create_browser_worker():
    global _ACTIVE_PLAYWRIGHT, _ACTIVE_BROWSER
    global _ACTIVE_CONTEXT, _ACTIVE_PAGE

    if (
        _ACTIVE_BROWSER is not None
        and _ACTIVE_BROWSER.is_connected()
        and _ACTIVE_CONTEXT is not None
    ):
        print("Reusing existing Chromium browser.")
        return _ACTIVE_BROWSER, _ACTIVE_CONTEXT

    if _ACTIVE_PLAYWRIGHT is not None:
        try:
            _ACTIVE_PLAYWRIGHT.stop()
        except Exception:
            pass

    _ACTIVE_PAGE = None
    _ACTIVE_CONTEXT = None
    _ACTIVE_BROWSER = None
    _ACTIVE_PLAYWRIGHT = None
    set_browser_state(False)

    print("Launching a new Chromium browser...")

    try:
        _ACTIVE_PLAYWRIGHT = sync_playwright().start()
        _ACTIVE_BROWSER = _ACTIVE_PLAYWRIGHT.chromium.launch(
            headless=False,
            slow_mo=300,
        )
        _ACTIVE_CONTEXT = _ACTIVE_BROWSER.new_context()
        set_browser_state(True)

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
        set_browser_state(False)
        raise

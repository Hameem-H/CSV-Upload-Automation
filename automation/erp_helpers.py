from urllib.parse import urlparse


class ERPStageError(Exception):
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result or {}


def get_page_path(url):
    return urlparse(url).path.rstrip("/").lower()


def notify(callback, stage, message, state="running", details=None):
    if callback:
        try:
            callback(stage, message, state, details or {})
        except Exception:
            pass


def check_response_status(response, stage_name):
    if response.status >= 400:
        raise ERPStageError(
            f"{stage_name} failed with HTTP status {response.status}."
        )


def check_php_errors(response_text):
    markers = [
        "Fatal error",
        "Uncaught Error",
        "Uncaught mysqli_sql_exception",
        "Parse error",
    ]
    for marker in markers:
        if marker.lower() in response_text.lower():
            raise ERPStageError(
                f"PHP error detected in ERP response: {marker}"
            )


def validate_configuration(department):
    workflow = department.get("workflow", "three_page")
    required = ["upload_url", "submit_url", "process_url"]

    if workflow == "four_page":
        required.append("intermediate_url")

    missing = [key for key in required if not department.get(key)]
    if missing:
        raise ValueError(
            f"Missing ERP URLs for {department['name']}: {', '.join(missing)}"
        )


def get_login_url(upload_url):
    parsed = urlparse(upload_url)
    base_path = parsed.path.split("/custom/")[0]
    return f"{parsed.scheme}://{parsed.netloc}{base_path}/login.php"


def read_response_text(response):
    try:
        return response.text()
    except Exception:
        return ""

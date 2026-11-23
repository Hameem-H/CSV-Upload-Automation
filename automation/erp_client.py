
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

ERP_LOGIN_URL = "http://localhost/ERP/BarcodeRead/login.php"

DEFAULT_TIMEOUT = 1800  # 30 minutes


class ERPStageError(Exception):
    """Raised when an ERP workflow stage fails."""
    pass


def _check_http_response(response, stage_name):
    try:
        response.raise_for_status()
    except requests.RequestException as error:
        raise ERPStageError(
            f"{stage_name} failed: {error}"
        ) from error


def erp_login(session):
    """
    Log in to ERP using credentials from environment variables.
    The session retains the PHP session cookie.
    """

    username = os.getenv("ERP_USERNAME")
    password = os.getenv("ERP_PASSWORD")

    if not username or not password:
        raise ERPStageError(
            "ERP_USERNAME or ERP_PASSWORD is not configured."
        )

    print("\n[ERP LOGIN] Opening ERP login page...")

    try:
        login_page = session.get(
            ERP_LOGIN_URL,
            timeout=30
        )
        _check_http_response(login_page, "Login page")

        print("[ERP LOGIN] Submitting credentials...")

        response = session.post(
            ERP_LOGIN_URL,
            data={
                "username": username,
                "pass": password,
                "login": "Submit"
            },
            timeout=30,
            allow_redirects=True
        )

        _check_http_response(response, "ERP login")

    except requests.RequestException as error:
        raise ERPStageError(
            f"Could not connect to ERP login: {error}"
        ) from error

    final_path = urlparse(response.url).path.lower()

    if not final_path.endswith("/menu.php"):
        if "invalid login" in response.text.lower():
            raise ERPStageError(
                "ERP login failed: Invalid username or password."
            )

        raise ERPStageError(
            "ERP login could not be verified. "
            f"Final URL: {response.url}"
        )

    print("[ERP LOGIN] Login successful.")

    return True


def upload_and_process(
    department,
    csv_path,
    timeout=DEFAULT_TIMEOUT
):
    """
    Execute the ERP workflow:

    1. Authenticate with ERP.
    2. Upload CSV.
    3. Open intermediate processing page.
    4. Submit final processing form.
    """

    csv_path = Path(csv_path)

    if not csv_path.exists() or not csv_path.is_file():
        raise FileNotFoundError(
            f"ERP CSV file not found: {csv_path}"
        )

    upload_url = department.get("upload_url")
    submit_url = department.get("submit_url")
    process_url = department.get("process_url")

    if not all([upload_url, submit_url, process_url]):
        raise ValueError(
            f"ERP URLs are incomplete for {department['name']}."
        )

    result = {
        "department": department["name"],
        "csv_file": str(csv_path),
        "stages": {}
    }

    with requests.Session() as session:

        # STAGE 1: ERP LOGIN
        erp_login(session)

        result["stages"]["login"] = {
            "success": True
        }

        # STAGE 2: CSV UPLOAD
        print("\n[ERP 1/3] Uploading CSV...")

        try:
            with csv_path.open("rb") as csv_file:

                response = session.post(
                    upload_url,
                    data={"automation": "1"},
                    files={
                        "csv": (
                            csv_path.name,
                            csv_file,
                            "text/csv"
                        )
                    },
                    timeout=timeout
                )

            _check_http_response(response, "CSV upload")

        except requests.RequestException as error:
            raise ERPStageError(
                f"CSV upload request failed: {error}"
            ) from error

        try:
            upload_result = response.json()
        except ValueError as error:
            raise ERPStageError(
                "ERP upload did not return JSON. "
                f"Response: {response.text[:1000]}"
            ) from error

        inserted = upload_result.get("inserted", 0)
        failed = upload_result.get("failed", 0)

        result["stages"]["upload"] = upload_result

        print(f"Inserted records: {inserted}")
        print(f"Failed records: {failed}")

        if upload_result.get("success") is not True or failed != 0:
            raise ERPStageError(
                "ERP upload failed or was partially completed. "
                f"Inserted: {inserted}, Failed: {failed}. "
                "Do not automatically retry this CSV."
            )

        # STAGE 3: OPEN INTERMEDIATE PAGE
        print("\n[ERP 2/3] Opening intermediate process page...")

        try:
            response = session.get(
                submit_url,
                timeout=30
            )

            _check_http_response(
                response,
                "Intermediate page"
            )

        except requests.RequestException as error:
            raise ERPStageError(
                f"Could not open intermediate page: {error}"
            ) from error

        if (
            "Submit" not in response.text
            or "ProcessSticker.php" not in response.text
        ):
            raise ERPStageError(
                "Could not verify the expected ERP processing form. "
                "The session may have expired or the page changed."
            )

        result["stages"]["intermediate_page"] = {
            "success": True,
            "url": response.url
        }

        # STAGE 4: FINAL PROCESSING
        print("\n[ERP 3/3] Starting final ERP processing...")
        print("Waiting for ERP processing to finish...")

        try:
            response = session.post(
                process_url,
                data={"button": "Submit"},
                timeout=timeout
            )

            _check_http_response(
                response,
                "Final ERP processing"
            )

        except requests.Timeout as error:
            raise ERPStageError(
                "ERP processing timed out. The server may still "
                "have processed some records. Check the ERP database "
                "before attempting another run."
            ) from error

        except requests.RequestException as error:
            raise ERPStageError(
                f"Final processing request failed: {error}. "
                "Check the ERP database before retrying."
            ) from error

        response_text = response.text

        error_markers = [
            "Fatal error",
            "Uncaught Error",
            "Uncaught mysqli_sql_exception",
            "Parse error"
        ]

        for marker in error_markers:
            if marker.lower() in response_text.lower():
                raise ERPStageError(
                    f"PHP error detected: {marker}. "
                    "Check the ERP server logs."
                )

        if "Back to Menu" not in response_text:
            raise ERPStageError(
                "Could not verify ERP processing completion. "
                f"HTTP status: {response.status_code}"
            )

        result["stages"]["processing"] = {
            "success": True,
            "http_status": response.status_code,
            "completion_verified": True,
            "final_url": response.url
        }

    print("\nERP WORKFLOW COMPLETED.")
    return result

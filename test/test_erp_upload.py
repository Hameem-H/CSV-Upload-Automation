
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


# Load credentials from .env in the project directory
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = "http://localhost/ERP/BarcodeRead/"

LOGIN_URL = BASE_URL + "login.php"
UPLOAD_URL = BASE_URL + "custom/stickeringbarcode.php"

TIMEOUT = 30


def erp_login(session):
    """Authenticate with ERP and preserve the PHP session."""

    username = os.getenv("ERP_USERNAME")
    password = os.getenv("ERP_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "ERP_USERNAME or ERP_PASSWORD is missing from .env"
        )

    print("\n[1/3] Connecting to ERP login...")

    response = session.get(LOGIN_URL, timeout=TIMEOUT)
    response.raise_for_status()

    response = session.post(
        LOGIN_URL,
        data={
            "username": username,
            "pass": password,
            "login": "Submit"
        },
        timeout=TIMEOUT,
        allow_redirects=True
    )

    response.raise_for_status()

    if not response.url.lower().endswith("/menu.php"):
        raise RuntimeError(
            "ERP login failed. Final URL: " + response.url
        )

    print("ERP login successful.")
    print("PHP session established.")


def upload_csv(session, csv_path):
    """Upload CSV and receive ERP JSON response."""

    print("\n[2/3] Uploading CSV to ERP...")

    with csv_path.open("rb") as csv_file:

        response = session.post(
            UPLOAD_URL,
            data={
                "automation": "1"
            },
            files={
                "csv": (
                    csv_path.name,
                    csv_file,
                    "text/csv"
                )
            },
            timeout=TIMEOUT
        )

    response.raise_for_status()

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            "ERP did not return JSON. "
            "Possible login redirect or PHP error.\n\n"
            + response.text[:1500]
        )

    return result


def main():

    print("====================================")
    print("      ERP STICKERING UPLOAD TEST")
    print("====================================")

    if len(sys.argv) < 2:
        print(
            "\nUsage:\n"
            'python test_erp_upload.py "C:\\path\\test.csv"'
        )
        return

    csv_path = Path(sys.argv[1])

    if not csv_path.exists() or not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV file not found: {csv_path}"
        )

    if csv_path.stat().st_size == 0:
        raise ValueError("CSV file is empty.")

    print(f"\nCSV file: {csv_path}")
    print(f"File size: {csv_path.stat().st_size} bytes")

    print("\nIMPORTANT:")
    print("This test will insert records into ERP.")
    print("It will NOT execute ProcessSticker.php.")

    confirmation = input(
        "\nType UPLOAD TEST to continue: "
    )

    if confirmation != "UPLOAD TEST":
        print("\nTest cancelled. No ERP upload was performed.")
        return

    with requests.Session() as session:

        # Stage 1: Login
        erp_login(session)

        # Stage 2: Upload CSV
        result = upload_csv(session, csv_path)

    print("\n[3/3] ERP upload response")
    print("------------------------------------")

    print("Success:", result.get("success"))
    print("Inserted:", result.get("inserted"))
    print("Failed:", result.get("failed"))
    print("Message:", result.get("message"))

    print("------------------------------------")

    if result.get("success") is True and result.get("failed", 0) == 0:
        print("\nUPLOAD TEST COMPLETED SUCCESSFULLY.")
        print("Records have been inserted into the pending ERP table.")
        print("Final processing was NOT executed.")

    else:
        print("\nUPLOAD WAS NOT FULLY SUCCESSFUL.")
        print("Do not automatically upload the same CSV again.")
        print("Check the ERP database before retrying.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("\nTEST FAILED:")
        print(error)

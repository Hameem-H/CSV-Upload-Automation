
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

ERP_USERNAME = os.getenv("ERP_USERNAME")
ERP_PASSWORD = os.getenv("ERP_PASSWORD")

BASE_URL = "http://localhost/ERP/BarcodeRead"

LOGIN_URL = f"{BASE_URL}/login.php"
UPLOAD_URL = f"{BASE_URL}/custom/stickeringbarcode.php"
PROCESS_PAGE_URL = f"{BASE_URL}/custom/stickeringbarcodeprocess.php"

PROCESS_TIMEOUT = 30 * 60 * 1000  # 30 minutes


# --------------------------------------------------
# MAIN WORKFLOW
# --------------------------------------------------

def main():

    if not ERP_USERNAME or not ERP_PASSWORD:
        print("ERROR: ERP credentials missing from .env")
        return

    if len(sys.argv) < 2:
        print("Usage:")
        print('python test_erp_browser.py "FULL_PATH_TO_BARCODE.CSV"')
        return

    csv_path = Path(sys.argv[1])

    if not csv_path.is_file():
        print(f"ERROR: CSV file not found: {csv_path}")
        return

    print("=" * 55)
    print("       ERP STICKERING - FULL BROWSER TEST")
    print("=" * 55)

    print(f"\nCSV file: {csv_path}")
    print(f"File size: {csv_path.stat().st_size} bytes")

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            slow_mo=500
        )

        page = browser.new_page()

        try:

            # ======================================
            # STAGE 1: ERP LOGIN
            # ======================================

            print("\n[1/3] ERP LOGIN")
            print("-" * 40)

            page.goto(LOGIN_URL, wait_until="domcontentloaded")

            page.locator('input[name="username"]').fill(ERP_USERNAME)
            page.locator('input[name="pass"]').fill(ERP_PASSWORD)
            page.locator('input[name="login"]').click()

            page.wait_for_url("**/menu.php", timeout=30000)

            print("SUCCESS: ERP login completed.")
            print("Current URL:", page.url)


            # ======================================
            # STAGE 2: CSV UPLOAD
            # ======================================

            print("\n[2/3] CSV UPLOAD")
            print("-" * 40)

            page.goto(UPLOAD_URL, wait_until="domcontentloaded")

            file_input = page.locator('input[name="csv"]')

            file_input.wait_for(
                state="visible",
                timeout=15000
            )

            print("Upload page opened.")

            file_input.set_input_files(str(csv_path.resolve()))

            print("CSV selected.")
            print("Submitting CSV to ERP...")

            page.locator('input[name="Submit"]').click()

            page.wait_for_url(
                "**/stickeringbarcodeprocess.php",
                timeout=60000
            )

            print("SUCCESS: CSV upload redirect completed.")
            print("Current URL:", page.url)


            # ======================================
            # STAGE 3: FINAL PROCESSING
            # ======================================

            print("\n[3/3] FINAL STICKERING PROCESSING")
            print("-" * 40)

            submit_button = page.locator('input[name="button"]')

            submit_button.wait_for(
                state="visible",
                timeout=15000
            )

            print("Processing page opened.")
            print("Submit button found.")

            print("\nStarting ProcessSticker.php...")
            print("Maximum waiting time: 30 minutes.")

            start_time = time.perf_counter()

            try:

                with page.expect_response(
                    lambda response: (
                        "ProcessSticker.php" in response.url
                        and response.request.method == "POST"
                    ),
                    timeout=PROCESS_TIMEOUT
                ) as response_info:

                    submit_button.click(timeout=30000)

                response = response_info.value

                elapsed = time.perf_counter() - start_time

                print("\nHTTP RESPONSE RECEIVED")
                print("-" * 40)

                print("HTTP Status:", response.status)
                print("Response URL:", response.url)
                print(f"Response Time: {elapsed:.2f} seconds")
                print(f"Response Time: {elapsed / 60:.2f} minutes")

                response_text = response.text()

                if "Back to Menu" in response_text:
                    print("\nCOMPLETION MARKER FOUND.")
                else:
                    print("\nWARNING: Completion marker not found.")

                print("\nFinal processing HTTP response received.")

            except PlaywrightTimeoutError:

                elapsed = time.perf_counter() - start_time

                print("\nHTTP RESPONSE TIMEOUT")
                print(f"Elapsed time: {elapsed / 60:.2f} minutes")
                print("No matching HTTP response was received.")
                print("Do NOT retry automatically.")
                print("Check ERP database records first.")

            print("\nBrowser remains open.")
            input("Press ENTER to close browser...")


        except PlaywrightTimeoutError:

            print("\nTIMEOUT ERROR")
            print("A login, upload, or page operation timed out.")
            print("ERP processing may have completed or partially run.")
            print("Check database records before retrying.")

            input("Press ENTER to close browser...")


        except Exception as e:

            print("\nERROR:", str(e))
            print("Current URL:", page.url)
            print("Inspect ERP records before retrying.")

            input("Press ENTER to close browser...")


        finally:
            browser.close()


if __name__ == "__main__":
    main()

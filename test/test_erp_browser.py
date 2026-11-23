
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

ERP_USERNAME = os.getenv("ERP_USERNAME")
ERP_PASSWORD = os.getenv("ERP_PASSWORD")

BASE_URL = "http://localhost/ERP/BarcodeRead"
LOGIN_URL = f"{BASE_URL}/login.php"
UPLOAD_URL = f"{BASE_URL}/custom/stickeringbarcode.php"


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

    print(f"CSV file: {csv_path}")
    print(f"File size: {csv_path.stat().st_size} bytes")

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            slow_mo=500
        )

        page = browser.new_page()

        try:
            # STAGE 1: LOGIN
            print("\n[1/3] Opening ERP login page...")

            page.goto(LOGIN_URL, wait_until="domcontentloaded")

            page.locator('input[name="username"]').fill(ERP_USERNAME)
            page.locator('input[name="pass"]').fill(ERP_PASSWORD)
            page.locator('input[name="login"]').click()

            page.wait_for_url("**/menu.php", timeout=30000)

            print("ERP login successful.")
            print("Current URL:", page.url)

            # STAGE 2: OPEN UPLOAD PAGE
            print("\n[2/3] Opening Stickering upload page...")

            page.goto(UPLOAD_URL, wait_until="domcontentloaded")

            page.locator('input[name="csv"]').wait_for(
                state="visible",
                timeout=15000
            )

            print("Upload page opened successfully.")

            page.locator('input[name="csv"]').set_input_files(
                str(csv_path.resolve())
            )

            print("CSV selected in browser.")

            print("\nIMPORTANT:")
            print("This will INSERT records into ERP.")
            print("It will NOT execute ProcessSticker.php.")

            confirmation = input(
                '\nType UPLOAD FRESH CSV to continue: '
            )

            if confirmation != "UPLOAD FRESH CSV":
                print("Upload cancelled.")
                return

            # STAGE 3: SUBMIT UPLOAD
            print("\n[3/3] Submitting CSV through browser...")

            page.locator('input[name="Submit"]').click()

            try:
                page.wait_for_url(
                    "**/stickeringbarcodeprocess.php",
                    timeout=30000
                )

                print("\nUPLOAD REDIRECT COMPLETED.")
                print("Current URL:", page.url)

            except PlaywrightTimeoutError:
                print("\nExpected redirect was not detected.")
                print("Current URL:", page.url)

            print("\nBrowser page title:", page.title())

            print("\nBrowser remains open for inspection.")
            input("Press ENTER in this terminal to close browser...")

        except Exception as e:
            print("\nERROR:", str(e))
            print("Current URL:", page.url)
            input("Press ENTER to close browser...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()


import io
import re

from pathlib import Path

from .browser_manager import (
    get_or_create_browser_worker,
    set_active_page,
)


VALIDATION_URL = "https://erp.corvoltd.com/Barcode/sc_barcode_check.php"

BARCODE_COLUMNS = [
    "Date",
    "Time",
    "ScannerID",
    "BarcodeNumber",
]


def validate_barcodes(department_id, department, unique_df):
    """
    Upload the unique barcode CSV to the PHP validation page.

    Returns a list of wrong barcode numbers.

    Must execute on the department's dedicated worker thread.
    """

    section = department.get("validation_section")

    if section not in ("Sticker", "Final Packing"):
        raise ValueError(
            f"Invalid barcode validation section for {department_id}: "
            f"{section}"
        )

    missing_columns = [
        column
        for column in BARCODE_COLUMNS
        if column not in unique_df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing CSV columns: " + ", ".join(missing_columns)
        )

    # Create a temporary CSV in memory.
    # Do not save it to the output folder yet.
    csv_buffer = io.StringIO()

    unique_df[BARCODE_COLUMNS].to_csv(
        csv_buffer,
        index=False,
        header=False,
        lineterminator="\n",
    )

    csv_bytes = csv_buffer.getvalue().encode("utf-8")

    page = None

    try:

        # Reuse this department's dedicated Playwright browser.
        _, context = get_or_create_browser_worker(department_id)

        page = context.new_page()

        set_active_page(department_id, page)

        page.set_default_timeout(30000)

        page.goto(
            VALIDATION_URL,
            wait_until="domcontentloaded",
        )

        # Select the temporary CSV.
        page.locator(
            'input[name="file"]'
        ).set_input_files({
            "name": "barcode_validation.csv",
            "mimeType": "text/csv",
            "buffer": csv_bytes,
        })

        # Select Sticker or Final Packing.
        page.locator(
            'select[name="section"]'
        ).select_option(value=section)

        # Submit the form and wait for the PHP response.
        with page.expect_navigation(
            wait_until="domcontentloaded",
            timeout=60000,
        ):
            page.locator(
                'input[name="submit"]'
            ).click()

        response_text = page.locator("body").inner_text().strip()

        # Successful validation.
        if "No wrong barcode." in response_text:
            return []

        # The PHP page displays only wrong barcode numbers,
        # one barcode per line.
        wrong_barcodes = []

        for line in response_text.splitlines():

            barcode = line.strip()

            if not barcode:
                continue

            if re.fullmatch(r"\d{11,12}", barcode):
                wrong_barcodes.append(barcode)
            else:
                raise RuntimeError(
                    "Unexpected response from barcode validation page: "
                    + response_text[:500]
                )

        if not wrong_barcodes:
            raise RuntimeError(
                "Could not determine the barcode validation result. "
                "Website response: " + response_text[:500]
            )

        # Remove repeated entries while preserving order.
        wrong_barcodes = list(dict.fromkeys(wrong_barcodes))

        return wrong_barcodes

    finally:

        if page is not None:
            try:
                page.close()
            except Exception as error:
                print("Barcode validation page close warning:", error)

        set_active_page(department_id, None)

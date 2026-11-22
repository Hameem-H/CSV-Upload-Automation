
import pandas as pd


def parse_scanner_txt(file_bytes):
    """
    Parse scanner TXT file.

    Expected format:
    Date,Time,ScannerID,BarcodeNumber

    Example:
    07/03/2020,11:00:44,03,12345678901

    Returns:
        valid_df: Valid scanner records.
        invalid_df: Invalid lines with reasons.
    """

    # --------------------------------------------------
    # STEP 1: Decode uploaded file
    # --------------------------------------------------

    try:
        text = file_bytes.decode("utf-8-sig")

    except UnicodeDecodeError:
        text = file_bytes.decode("cp1252")


    # --------------------------------------------------
    # STEP 2: Prepare containers
    # --------------------------------------------------

    valid_rows = []
    invalid_rows = []


    # --------------------------------------------------
    # STEP 3: Read file line by line
    # --------------------------------------------------

    for line_number, raw_line in enumerate(
        text.splitlines(),
        start=1
    ):

        # Ignore completely empty lines
        if not raw_line.strip():
            continue


        # --------------------------------------------------
        # STEP 4: Split each line into four fields
        # --------------------------------------------------

        parts = [
            part.strip()
            for part in raw_line.split(",")
        ]

        if len(parts) != 4:

            invalid_rows.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "Expected exactly 4 columns"
            })

            continue


        date_value, time_value, scanner_id, barcode = parts


        # --------------------------------------------------
        # STEP 5: Check empty fields
        # --------------------------------------------------

        if not all(parts):

            invalid_rows.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "One or more fields are empty"
            })

            continue


        # --------------------------------------------------
        # STEP 6: Validate date
        # --------------------------------------------------

        try:
            pd.to_datetime(
                date_value,
                format="%d/%m/%Y",
                errors="raise"
            )

        except (ValueError, TypeError):

            invalid_rows.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "Invalid date format (expected DD/MM/YYYY)"
            })

            continue


        # --------------------------------------------------
        # STEP 7: Validate time
        # --------------------------------------------------

        try:
            pd.to_datetime(
                time_value,
                format="%H:%M:%S",
                errors="raise"
            )

        except (ValueError, TypeError):

            invalid_rows.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "Invalid time format (expected HH:MM:SS)"
            })

            continue


        # --------------------------------------------------
        # STEP 8: Store valid record
        # --------------------------------------------------

        valid_rows.append({
            "Date": date_value,
            "Time": time_value,
            "ScannerID": scanner_id,
            "BarcodeNumber": barcode,
            "_LineNumber": line_number
        })


    # --------------------------------------------------
    # STEP 9: Convert records into DataFrames
    # --------------------------------------------------

    valid_df = pd.DataFrame(
        valid_rows,
        columns=[
            "Date",
            "Time",
            "ScannerID",
            "BarcodeNumber",
            "_LineNumber"
        ]
    )

    invalid_df = pd.DataFrame(
        invalid_rows,
        columns=[
            "LineNumber",
            "RawLine",
            "Reason"
        ]
    )


    return valid_df, invalid_df

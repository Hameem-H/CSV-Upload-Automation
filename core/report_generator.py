
from datetime import datetime


def generate_processing_summary(
    department_name,
    original_filename,
    total_rows,
    unique_count,
    duplicate_count,
    invalid_count,
    processing_date=None
):
    """
    Generate a readable processing summary.

    Returns:
        A formatted string containing processing information.
    """

    # --------------------------------------------------
    # STEP 1: Get processing timestamp
    # --------------------------------------------------

    if processing_date is None:
        processing_date = datetime.now()

    processing_timestamp = processing_date.strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    # --------------------------------------------------
    # STEP 2: Calculate total received records
    # --------------------------------------------------

    total_received = total_rows + invalid_count


    # --------------------------------------------------
    # STEP 3: Prepare summary content
    # --------------------------------------------------

    summary = f"""
BARCODE AUTOMATION - PROCESSING SUMMARY
=======================================

Department          : {department_name}
Original TXT File   : {original_filename}
Processing Date     : {processing_timestamp}

---------------------------------------
RECORD SUMMARY
---------------------------------------

Total Received Lines    : {total_received}
Valid Records           : {total_rows}
Unique Barcodes         : {unique_count}
Duplicate Records       : {duplicate_count}
Invalid Records         : {invalid_count}

---------------------------------------
PROCESSING RULES
---------------------------------------

1. BarcodeNumber is used to identify duplicates.
2. The first occurrence of each barcode is retained.
3. Subsequent occurrences are recorded as duplicates.
4. Invalid records are excluded from ERP CSV.
5. ERP CSV contains no column headers or index.
6. Original TXT is preserved exactly as uploaded.

---------------------------------------
END OF SUMMARY
---------------------------------------
"""

    return summary.strip()

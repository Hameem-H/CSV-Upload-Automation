
from pathlib import Path
from datetime import datetime
import csv
import io
import re

import pandas as pd
import streamlit as st


# ============================================================
# APPLICATION SETTINGS
# ============================================================

APP_TITLE = "Barcode TXT to CSV Converter"

DEPARTMENTS = [
    "Stickering",
    "Conv Start",
    "Conv End",
    "Final Packing",
    "Store FGS",
]

# Fixed output location.
# Change this path if you want to save somewhere else.
DEFAULT_OUTPUT = Path(r"F:\Barcode\CONE LINE 1(Conveyer Start)\2026\2026-09")


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📦",
    layout="wide"
)


# ============================================================
# TXT FILE PARSING
# ============================================================

def parse_scanner_txt(file_bytes):

    """
    Expected TXT format:

    DD/MM/YYYY,HH:MM:SS,ScannerID,BarcodeNumber

    Example:
    07/03/2020,11:00:44,03,93210140068
    """

    try:
        text = file_bytes.decode("utf-8-sig")

    except UnicodeDecodeError:
        text = file_bytes.decode("cp1252")

    valid_records = []
    invalid_records = []

    lines = text.splitlines()

    for line_number, raw_line in enumerate(lines, start=1):

        line = raw_line.strip()

        # Ignore completely blank lines.
        if not line:
            continue

        fields = [field.strip() for field in line.split(",")]

        # Exactly four fields are required.
        if len(fields) != 4:

            invalid_records.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "Expected exactly 4 fields"
            })

            continue

        scan_date, scan_time, scanner_id, barcode = fields

        # Required fields cannot be empty.
        if not all(fields):

            invalid_records.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "One or more fields are empty"
            })

            continue

        # Validate date.
        try:
            datetime.strptime(scan_date, "%d/%m/%Y")

        except ValueError:

            invalid_records.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "Invalid date format"
            })

            continue

        # Validate time.
        try:
            datetime.strptime(scan_time, "%H:%M:%S")

        except ValueError:

            invalid_records.append({
                "LineNumber": line_number,
                "RawLine": raw_line,
                "Reason": "Invalid time format"
            })

            continue

        # Keep ScannerID and BarcodeNumber as text.
        valid_records.append({
            "Date": scan_date,
            "Time": scan_time,
            "ScannerID": scanner_id,
            "BarcodeNumber": barcode,
            "_LineNumber": line_number
        })

    columns = [
        "Date",
        "Time",
        "ScannerID",
        "BarcodeNumber",
        "_LineNumber"
    ]

    valid_df = pd.DataFrame(valid_records, columns=columns)

    invalid_df = pd.DataFrame(
        invalid_records,
        columns=["LineNumber", "RawLine", "Reason"]
    )

    return valid_df, invalid_df


# ============================================================
# DUPLICATE BARCODE PROCESSING
# ============================================================

def build_outputs(df):

    """
    Deduplication rule:

    BarcodeNumber is the only field used to identify duplicates.

    The first occurrence is kept.
    All later occurrences of the same barcode are removed,
    regardless of date, time or scanner ID.
    """

    total_rows = len(df)

    if df.empty:

        unique_df = pd.DataFrame(
            columns=["Date", "Time", "ScannerID", "BarcodeNumber"]
        )

        duplicate_rows_df = pd.DataFrame(
            columns=[
                "Date",
                "Time",
                "ScannerID",
                "BarcodeNumber",
                "LineNumber"
            ]
        )

        duplicate_summary_df = pd.DataFrame(
            columns=[
                "BarcodeNumber",
                "TotalOccurrences",
                "FirstScanDate",
                "FirstScanTime",
                "FirstScannerID",
                "DuplicateOccurrences"
            ]
        )

        return (
            unique_df,
            duplicate_rows_df,
            duplicate_summary_df,
            total_rows,
            0,
            0
        )

    # Find duplicate scans after the first occurrence.
    duplicate_mask = df.duplicated(
        subset=["BarcodeNumber"],
        keep="first"
    )

    duplicate_rows = df[duplicate_mask].copy()

    # Keep only the first occurrence of each barcode.
    unique_df = df.drop_duplicates(
        subset=["BarcodeNumber"],
        keep="first"
    ).copy()

    # Prepare duplicate detail report.
    duplicate_rows_df = duplicate_rows[
        ["Date", "Time", "ScannerID", "BarcodeNumber", "_LineNumber"]
    ].copy()

    duplicate_rows_df.rename(
        columns={"_LineNumber": "LineNumber"},
        inplace=True
    )

    # Prepare duplicate summary report.
    duplicate_summary = []

    for barcode, group in df.groupby(
        "BarcodeNumber",
        sort=False
    ):

        if len(group) > 1:

            first_scan = group.iloc[0]

            duplicate_summary.append({
                "BarcodeNumber": barcode,
                "TotalOccurrences": len(group),
                "FirstScanDate": first_scan["Date"],
                "FirstScanTime": first_scan["Time"],
                "FirstScannerID": first_scan["ScannerID"],
                "DuplicateOccurrences": len(group) - 1
            })

    duplicate_summary_df = pd.DataFrame(
        duplicate_summary,
        columns=[
            "BarcodeNumber",
            "TotalOccurrences",
            "FirstScanDate",
            "FirstScanTime",
            "FirstScannerID",
            "DuplicateOccurrences"
        ]
    )

    unique_df = unique_df[
        ["Date", "Time", "ScannerID", "BarcodeNumber"]
    ].copy()

    unique_count = len(unique_df)
    duplicate_count = len(duplicate_rows_df)

    return (
        unique_df,
        duplicate_rows_df,
        duplicate_summary_df,
        total_rows,
        unique_count,
        duplicate_count
    )


# ============================================================
# SAFE FILE NAME
# ============================================================

def safe_filename(filename):

    stem = Path(filename).stem

    stem = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        stem
    ).strip("_")

    return stem or "scanner_file"


# ============================================================
# SAVE OUTPUT FILES
# ============================================================

def save_outputs(
    unique_df,
    duplicate_rows_df,
    duplicate_summary_df,
    invalid_df,
    uploaded_filename,
    department,
    total_rows,
    unique_count,
    duplicate_count
):

    # Date on which the file is processed.
    processing_date = datetime.now().strftime("%Y-%m-%d")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create department and date folders.
    department_folder = (
        DEFAULT_OUTPUT /
        department.replace(" ", "_") /
        processing_date
    )

    csv_folder = department_folder / "CSV"
    reports_folder = department_folder / "Reports"

    csv_folder.mkdir(parents=True, exist_ok=True)
    reports_folder.mkdir(parents=True, exist_ok=True)

    # Create output filename.
    filename = safe_filename(uploaded_filename)

    output_name = f"{filename}_{timestamp}"

    csv_path = csv_folder / f"{output_name}.csv"

    duplicate_detail_path = (
        reports_folder /
        f"{output_name}_duplicate_details.csv"
    )

    duplicate_summary_path = (
        reports_folder /
        f"{output_name}_duplicate_summary.csv"
    )

    invalid_path = (
        reports_folder /
        f"{output_name}_invalid_lines.csv"
    )

    summary_path = (
        reports_folder /
        f"{output_name}_summary.txt"
    )

    # Save cleaned barcode CSV.

# Prepare CSV in the exact format expected by the ERP PHP upload.

    erp_upload_df = unique_df[
        ["Date", "Time", "ScannerID", "BarcodeNumber"]
    ].copy()

    erp_upload_df.to_csv(
        csv_path,
        index=False,
        header=False,
        encoding="utf-8",
        lineterminator="\n"
    )


    # Save duplicate scan details.
    duplicate_rows_df.to_csv(
        duplicate_detail_path,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n"
    )

    # Save duplicate summary.
    duplicate_summary_df.to_csv(
        duplicate_summary_path,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n"
    )

    # Save invalid lines.
    invalid_df.to_csv(
        invalid_path,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n"
    )

    # Save processing summary.
    summary_text = (
        f"Barcode Processing Summary\n"
        f"==========================\n\n"
        f"Source file: {uploaded_filename}\n"
        f"Department: {department}\n"
        f"Processing date: {processing_date}\n"
        f"Processing time: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"Total valid records: {total_rows}\n"
        f"Unique barcodes: {unique_count}\n"
        f"Duplicate scans removed: {duplicate_count}\n"
        f"Invalid lines: {len(invalid_df)}\n\n"
        f"Duplicate rule: BarcodeNumber only.\n"
        f"First occurrence is retained.\n\n"
        f"Cleaned CSV: {csv_path}\n"
        f"Duplicate details: {duplicate_detail_path}\n"
        f"Duplicate summary: {duplicate_summary_path}\n"
        f"Invalid lines: {invalid_path}\n"
    )

    summary_path.write_text(
        summary_text,
        encoding="utf-8"
    )

    return (
        department_folder,
        csv_path,
        duplicate_detail_path,
        duplicate_summary_path,
        invalid_path,
        summary_path
    )


# ============================================================
# APPLICATION INTERFACE
# ============================================================

st.title("📦 Barcode TXT to CSV Converter")

st.write(
    "Upload your scanner TXT file, select the department, "
    "and process it to automatically save the cleaned CSV "
    "and processing reports."
)

st.divider()


# ============================================================
# STEP 1: UPLOAD TXT FILE
# ============================================================

st.subheader("Step 1: Upload Scanner TXT File")

uploaded_file = st.file_uploader(
    "Select your scanner TXT file",
    type=["txt"],
    accept_multiple_files=False
)


# ============================================================
# STEP 2: SELECT DEPARTMENT
# ============================================================

st.subheader("Step 2: Select Department")

department = st.selectbox(
    "Choose the department",
    DEPARTMENTS
)


# ============================================================
# DUPLICATE RULE
# ============================================================

with st.expander("Barcode processing rule"):

    st.info(
        "Duplicate checking is performed using BarcodeNumber only. "
        "The first scan is retained. All later scans of the same "
        "barcode are removed, even if the date, time or scanner ID "
        "is different."
    )


st.divider()


# ============================================================
# STEP 3: PROCESS AND SAVE
# ============================================================

st.subheader("Step 3: Process and Save")

if uploaded_file is not None:

    st.write(f"**Selected file:** {uploaded_file.name}")

    if st.button(
        "Process",
        type="primary",
        use_container_width=True
    ):

        try:

            # Read uploaded TXT file.
            file_bytes = uploaded_file.getvalue()

            # Parse TXT file.
            df, invalid_df = parse_scanner_txt(file_bytes)

            # Process duplicates.
            (
                unique_df,
                duplicate_rows_df,
                duplicate_summary_df,
                total_rows,
                unique_count,
                duplicate_count
            ) = build_outputs(df)

            # Display processing metrics.
            st.subheader("Processing Results")

            col1, col2, col3, col4 = st.columns(4)

            col1.metric(
                "Valid Records",
                total_rows
            )

            col2.metric(
                "Unique Barcodes",
                unique_count
            )

            col3.metric(
                "Duplicates Removed",
                duplicate_count
            )

            col4.metric(
                "Invalid Lines",
                len(invalid_df)
            )

            # Show cleaned CSV preview.
            st.subheader("Cleaned CSV Preview")

            st.dataframe(
                unique_df,
                use_container_width=True
            )

            # Show duplicate report.
            with st.expander("View Duplicate Scan Details"):

                st.dataframe(
                    duplicate_rows_df,
                    use_container_width=True
                )

                st.dataframe(
                    duplicate_summary_df,
                    use_container_width=True
                )

            # Show invalid lines.
            with st.expander("View Invalid Lines"):

                if invalid_df.empty:

                    st.success("No invalid lines found.")

                else:

                    st.dataframe(
                        invalid_df,
                        use_container_width=True
                    )

            # Save automatically after clicking Process.
            if unique_count == 0:

                st.warning(
                    "No valid unique barcodes were found. "
                    "No cleaned CSV was saved."
                )

            else:

                (
                    department_folder,
                    csv_path,
                    duplicate_detail_path,
                    duplicate_summary_path,
                    invalid_path,
                    summary_path
                ) = save_outputs(
                    unique_df,
                    duplicate_rows_df,
                    duplicate_summary_df,
                    invalid_df,
                    uploaded_file.name,
                    department,
                    total_rows,
                    unique_count,
                    duplicate_count
                )

                st.success(
                    "Processing completed successfully. "
                    "All output files have been saved."
                )

                st.write("**Saved location:**")

                st.code(str(department_folder))

                st.write("**Cleaned CSV:**")

                st.code(str(csv_path))

                st.write("**Saved reports:**")

                st.code(
                    f"{duplicate_detail_path}\n"
                    f"{duplicate_summary_path}\n"
                    f"{invalid_path}\n"
                    f"{summary_path}"
                )

        except Exception as exc:

            st.error(
                f"An error occurred during processing: {exc}"
            )

else:

    st.info(
        "Please upload a scanner TXT file to begin."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Original TXT files are never modified. "
    "The cleaned CSV keeps the first occurrence of each barcode. "
    "All output files are saved locally in the selected department "
    "and processing-date folder."
)

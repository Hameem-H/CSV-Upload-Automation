from pathlib import Path
from datetime import datetime
import csv
import io
import re

import pandas as pd
import streamlit as st

APP_TITLE = "Barcode TXT to CSV Converter"
DEPARTMENTS = [
    "Stickering",
    "Conv",
    "Start",
    "Conv End",
    "Final Packing",
    "Store FGS",
]
DEFAULT_OUTPUT = Path.home() / "BarcodeAutomation" / "Output"

st.set_page_config(page_title=APP_TITLE, page_icon="📦", layout="wide")

def parse_scanner_txt(file_bytes: bytes):
    """
    Expected input per line:
    Date,Time,ScannerID,BarcodeNumber
    No header row. Commas are the expected delimiters.
    """
    try:
        content = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = file_bytes.decode("cp1252")

    rows = []
    invalid = []

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4 or any(part == "" for part in parts):
            invalid.append({
                "LineNumber": line_number,
                "OriginalLine": raw_line,
                "Reason": f"Expected 4 non-empty comma-separated fields; found {len(parts)} fields",
            })
            continue

        date_value, time_value, scanner_id, barcode = parts

        # Keep all fields as text to preserve leading zeros in ScannerID/barcodes.
        # Validate date/time without changing their original representation.
        try:
            datetime.strptime(date_value, "%d/%m/%Y")
        except ValueError:
            invalid.append({
                "LineNumber": line_number,
                "OriginalLine": raw_line,
                "Reason": "Date must use DD/MM/YYYY format",
            })
            continue

        try:
            datetime.strptime(time_value, "%H:%M:%S")
        except ValueError:
            invalid.append({
                "LineNumber": line_number,
                "OriginalLine": raw_line,
                "Reason": "Time must use HH:MM:SS format",
            })
            continue

        rows.append({
            "Date": date_value,
            "Time": time_value,
            "ScannerID": scanner_id,
            "BarcodeNumber": barcode,
            "_LineNumber": line_number,
        })

    columns = ["Date", "Time", "ScannerID", "BarcodeNumber"]
    return pd.DataFrame(rows), pd.DataFrame(invalid), columns


def build_outputs(df: pd.DataFrame):
    total_rows = len(df)
    if total_rows == 0:
        unique = df.copy()
        duplicate_rows = df.copy()
        duplicate_summary = pd.DataFrame(
            columns=["BarcodeNumber", "Occurrences", "FirstScanDate", "FirstScanTime", "FirstScannerID"]
        )
    else:
        counts = df["BarcodeNumber"].value_counts()
        duplicate_barcodes = set(counts[counts > 1].index)
        duplicate_rows = df[df["BarcodeNumber"].isin(duplicate_barcodes)].copy()
        duplicate_summary = (
            df.groupby("BarcodeNumber", sort=False)
              .agg(
                  Occurrences=("BarcodeNumber", "size"),
                  FirstScanDate=("Date", "first"),
                  FirstScanTime=("Time", "first"),
                  FirstScannerID=("ScannerID", "first"),
              )
              .reset_index()
        )
        duplicate_summary = duplicate_summary[duplicate_summary["Occurrences"] > 1]

        # Keep the first occurrence of each barcode, preserving original order.
        unique = df.drop_duplicates(subset=["BarcodeNumber"], keep="first").copy()

    output_columns = ["Date", "Time", "ScannerID", "BarcodeNumber"]
    return (
        unique[output_columns],
        duplicate_rows[output_columns],
        duplicate_summary,
        total_rows,
        len(unique),
        total_rows - len(unique),
    )


def dataframe_csv_bytes(dataframe):
    return dataframe.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


st.title("📦 Barcode TXT to CSV Converter")
st.caption("Convert scanner TXT files, keep the first scan for each barcode, review duplicates, and save files by department.")

with st.sidebar:
    st.header("Save settings")
    output_root_text = st.text_input(
        "Local output folder",
        value=str(DEFAULT_OUTPUT),
        help="Choose where department folders will be created.",
    )
    st.caption("Example: C:\\BarcodeAutomation\\Output")

uploaded_file = st.file_uploader(
    "Drag and drop your scanner TXT file here",
    type=["txt"],
    accept_multiple_files=False,
)

left, right = st.columns([1, 1])
with left:
    department = st.selectbox("Select department", DEPARTMENTS)
with right:
    st.text_input("Duplicate rule", value="BarcodeNumber only — keep first occurrence", disabled=True)

if uploaded_file is not None:
    st.subheader("File preview")
    raw_bytes = uploaded_file.getvalue()
    df, invalid_df, output_columns = parse_scanner_txt(raw_bytes)

    if not df.empty:
        st.dataframe(df[output_columns].head(20), use_container_width=True, hide_index=True)
    else:
        st.warning("No valid scanner records were found.")

    unique_df, duplicate_rows_df, duplicate_summary_df, total, unique_count, duplicate_count = build_outputs(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valid records", total)
    c2.metric("Unique barcodes", unique_count)
    c3.metric("Duplicate scans removed", duplicate_count)
    c4.metric("Invalid lines", len(invalid_df))

    if not duplicate_summary_df.empty:
        with st.expander("Review duplicate barcodes"):
            st.dataframe(duplicate_summary_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download duplicate report",
                data=dataframe_csv_bytes(duplicate_summary_df),
                file_name="duplicate_report.csv",
                mime="text/csv",
            )

    if not invalid_df.empty:
        with st.expander("Review invalid lines"):
            st.dataframe(invalid_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download invalid lines report",
                data=dataframe_csv_bytes(invalid_df),
                file_name="invalid_lines_report.csv",
                mime="text/csv",
            )

    st.subheader("CSV output preview")
    st.dataframe(unique_df, use_container_width=True, hide_index=True)

    st.download_button(
        "Download cleaned CSV",
        data=dataframe_csv_bytes(unique_df),
        file_name=f"{department.replace(' ', '_')}_{datetime.now():%Y%m%d_%H%M%S}.csv",
        mime="text/csv",
        disabled=unique_df.empty,
        type="primary",
    )

    if st.button("Save files to local department folder", type="primary", disabled=unique_df.empty):
        try:
            root = Path(output_root_text).expanduser()
            department_folder = root / department.replace(" ", "_")
            csv_folder = department_folder / "CSV"
            reports_folder = department_folder / "Reports"
            csv_folder.mkdir(parents=True, exist_ok=True)
            reports_folder.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = Path(uploaded_file.name).stem
            safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "scanner_file"
            output_name = f"{safe_stem}_{timestamp}"

            csv_path = csv_folder / f"{output_name}.csv"
            duplicate_path = reports_folder / f"{output_name}_duplicates.csv"
            invalid_path = reports_folder / f"{output_name}_invalid_lines.csv"
            summary_path = reports_folder / f"{output_name}_summary.txt"

            unique_df.to_csv(csv_path, index=False, encoding="utf-8-sig", lineterminator="\n")
            duplicate_summary_df.to_csv(duplicate_path, index=False, encoding="utf-8-sig", lineterminator="\n")
            invalid_df.to_csv(invalid_path, index=False, encoding="utf-8-sig", lineterminator="\n")

            summary_text = (
                f"Source file: {uploaded_file.name}\n"
                f"Department: {department}\n"
                f"Processed at: {datetime.now().isoformat(timespec='seconds')}\n"
                f"Valid records: {total}\n"
                f"Unique barcodes: {unique_count}\n"
                f"Duplicate scans removed: {duplicate_count}\n"
                f"Invalid lines: {len(invalid_df)}\n"
                f"CSV: {csv_path}\n"
            )
            summary_path.write_text(summary_text, encoding="utf-8")

            st.success(f"Files saved successfully in: {department_folder}")
            st.code(str(csv_path))
        except Exception as exc:
            st.error(f"Could not save files: {exc}")
else:
    st.info("Upload a TXT file to begin. Expected format: DD/MM/YYYY,HH:MM:SS,ScannerID,BarcodeNumber")
    st.code(
        "07/03/2020,11:00:44,03,93210140068\n"
        "07/03/2020,11:00:44,03,93210140068\n"
        "07/03/2020,11:00:45,03,93210140068",
        language="text",
    )

st.divider()
st.caption("Original TXT files are never changed. Duplicate detection uses BarcodeNumber only and keeps the first occurrence.")

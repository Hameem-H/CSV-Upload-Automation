
from pathlib import Path
from datetime import datetime
import argparse
import sys

from core.parser import parse_scanner_txt
from core.duplicate_processor import build_outputs
from core.report_generator import generate_processing_summary
from storage.file_manager import save_outputs
from config.departments import get_department

def run_pipeline(txt_path, department_id):
    txt_path = Path(txt_path)

    if not txt_path.exists():
        raise FileNotFoundError(f"TXT file not found: {txt_path}")

    if not txt_path.is_file():
        raise ValueError(f"Not a file: {txt_path}")

    print("\n===================================")
    print("BARCODE AUTOMATION - PIPELINE TEST")
    print("===================================")

    # Step 1: Read the original TXT file.
    print("\n[1/5] Reading original TXT file...")

    original_file_bytes = txt_path.read_bytes()

    print(f"File: {txt_path.name}")
    print(f"Size: {len(original_file_bytes):,} bytes")

    # Step 2: Parse scanner records.
    print("\n[2/5] Parsing scanner records...")

    valid_df, invalid_df = parse_scanner_txt(original_file_bytes)

    total_rows = len(valid_df)
    invalid_count = len(invalid_df)

    print(f"Valid records: {total_rows}")
    print(f"Invalid records: {invalid_count}")

    # Step 3: Identify and remove duplicate barcodes.
    print("\n[3/5] Processing duplicates...")

    (
        unique_df,
        duplicate_rows_df,
        duplicate_summary_df,
        total_rows,
        unique_count,
        duplicate_count
    ) = build_outputs(valid_df)

    print(f"Total valid records: {total_rows}")
    print(f"Unique barcodes: {unique_count}")
    print(f"Duplicate records: {duplicate_count}")

    # Step 4: Generate the processing summary.
    print("\n[4/5] Generating processing summary...")

    processing_date = datetime.now()

    summary_text = generate_processing_summary(
        department_name=get_department(department_id)["name"],
        original_filename=txt_path.name,
        total_rows=total_rows,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        invalid_count=invalid_count,
        processing_date=processing_date
    )

    # Step 5: Save all output files.
    print("\n[5/5] Saving output files...")

    saved_files = save_outputs(
        department_id=department_id,
        original_file_bytes=original_file_bytes,
        original_filename=txt_path.name,
        unique_df=unique_df,
        duplicate_rows_df=duplicate_rows_df,
        duplicate_summary_df=duplicate_summary_df,
        invalid_df=invalid_df,
        total_rows=total_rows,
        unique_count=unique_count,
        duplicate_count=duplicate_count,
        summary_text=summary_text,
        processing_date=processing_date
    )

    print("\n===================================")
    print("PIPELINE COMPLETED SUCCESSFULLY")
    print("===================================")

    print(f"\nDepartment: {saved_files['department']}")
    print(f"Output folder: {saved_files['daily_folder']}")

    print("\nSaved files:")

    for key in [
        "original_txt_path",
        "erp_csv_path",
        "duplicate_details_path",
        "duplicate_summary_path",
        "invalid_lines_path",
        "processing_summary_path"
    ]:
        print(f"  {saved_files[key]}")

    print("\nFinal record counts:")
    print(f"  Valid records:     {total_rows}")
    print(f"  Unique barcodes:   {unique_count}")
    print(f"  Duplicate records:{duplicate_count:>6}")
    print(f"  Invalid records:   {invalid_count}")

    return saved_files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test the local barcode processing and saving pipeline."
    )

    parser.add_argument(
        "txt_file",
        help="Full path to the scanner TXT file."
    )

    parser.add_argument(
        "--department",
        default="stickering",
        help="Department ID (default: stickering)."
    )

    args = parser.parse_args()

    try:
        run_pipeline(
            txt_path=args.txt_file,
            department_id=args.department
        )

    except Exception as error:
        print("\nPIPELINE FAILED")
        print(f"Reason: {error}")
        sys.exit(1)

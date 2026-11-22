
from pathlib import Path
from datetime import datetime

from config.departments import get_department


def save_outputs(
    department_id,
    original_file_bytes,
    original_filename,
    unique_df,
    duplicate_rows_df,
    duplicate_summary_df,
    invalid_df,
    total_rows,
    unique_count,
    duplicate_count,
    summary_text,
    processing_date=None
):
    department = get_department(department_id)
    output_root = department["output_root"]

    if output_root is None:
        raise ValueError(
            f"Output path is not configured for {department['name']}."
        )

    output_root = Path(output_root)

    # The department's permanent base folder must already exist.
    if not output_root.exists():
        raise FileNotFoundError(
            f"Department base folder does not exist: {output_root}"
        )

    if not output_root.is_dir():
        raise NotADirectoryError(
            f"Output path is not a directory: {output_root}"
        )

    if processing_date is None:
        processing_date = datetime.now()

    # Build year/month/day folders automatically.
    year_folder = output_root / processing_date.strftime("%Y")
    month_folder = year_folder / processing_date.strftime("%Y-%m")
    daily_folder = month_folder / processing_date.strftime("%Y-%m-%d")

    daily_folder.mkdir(parents=True, exist_ok=True)

    original_txt_path = daily_folder / "barcode.txt"
    erp_csv_path = daily_folder / "barcode.csv"
    reports_folder = daily_folder / "Reports"

    report_paths = {
        "duplicate_details": reports_folder / "duplicate_details.csv",
        "duplicate_summary": reports_folder / "duplicate_summary.csv",
        "invalid_lines": reports_folder / "invalid_lines.csv",
        "processing_summary": reports_folder / "processing_summary.txt",
    }

    # Check every expected file before writing anything.
    all_file_paths = [
        original_txt_path,
        erp_csv_path,
        *report_paths.values()
    ]

    existing_files = [
        str(path) for path in all_file_paths if path.exists()
    ]

    if existing_files:
        raise FileExistsError(
            "Files already exist for this department and date. "
            "Nothing was overwritten:\n"
            + "\n".join(existing_files)
        )

    # Create Reports only after the collision check.
    reports_folder.mkdir(exist_ok=True)

    try:
        # Preserve the original TXT bytes exactly as uploaded.
        original_txt_path.write_bytes(original_file_bytes)

        # ERP CSV: four columns, no header, no pandas index.
        erp_columns = [
            "Date",
            "Time",
            "ScannerID",
            "BarcodeNumber"
        ]

        erp_upload_df = unique_df[erp_columns].copy()

        erp_upload_df.to_csv(
            erp_csv_path,
            index=False,
            header=False,
            encoding="utf-8",
            lineterminator="\n"
        )

        duplicate_rows_df.to_csv(
            report_paths["duplicate_details"],
            index=False,
            encoding="utf-8-sig"
        )

        duplicate_summary_df.to_csv(
            report_paths["duplicate_summary"],
            index=False,
            encoding="utf-8-sig"
        )

        invalid_df.to_csv(
            report_paths["invalid_lines"],
            index=False,
            encoding="utf-8-sig"
        )

        report_paths["processing_summary"].write_text(
            summary_text,
            encoding="utf-8"
        )

    except Exception:
        # Remove partially written files if saving fails.
        for path in all_file_paths:
            if path.exists():
                path.unlink()

        if reports_folder.exists() and not any(reports_folder.iterdir()):
            reports_folder.rmdir()

        raise

    return {
        "department": department["name"],
        "original_filename": original_filename,
        "daily_folder": daily_folder,
        "original_txt_path": original_txt_path,
        "erp_csv_path": erp_csv_path,
        "reports_folder": reports_folder,
        "duplicate_details_path": report_paths["duplicate_details"],
        "duplicate_summary_path": report_paths["duplicate_summary"],
        "invalid_lines_path": report_paths["invalid_lines"],
        "processing_summary_path": report_paths["processing_summary"],
        "total_rows": total_rows,
        "unique_count": unique_count,
        "duplicate_count": duplicate_count,
    }

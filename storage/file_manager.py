
from pathlib import Path
from datetime import datetime
from threading import Lock

from config.departments import get_department


# Prevent two background jobs from selecting the same filenames
# simultaneously within this application process.
_FILE_SAVE_LOCK = Lock()


def _build_file_paths(daily_folder, number=""):
    """
    Build all output paths for one upload.

    The same number is applied to every file belonging to this upload.
    """

    reports_folder = daily_folder / "Reports"

    return {
        "original_txt_path": daily_folder / f"barcode{number}.txt",
        "erp_csv_path": daily_folder / f"barcode{number}.csv",

        "duplicate_details_path": (
            reports_folder / f"duplicate_details{number}.csv"
        ),

        "duplicate_summary_path": (
            reports_folder / f"duplicate_summary{number}.csv"
        ),

        "invalid_lines_path": (
            reports_folder / f"invalid_lines{number}.csv"
        ),

        "processing_summary_path": (
            reports_folder / f"processing_summary{number}.txt"
        ),

        "reports_folder": reports_folder,
    }


def _find_available_file_paths(daily_folder):
    """
    Find the next available filename set without overwriting
    any existing output file.
    """

    number_index = 0

    while True:

        if number_index == 0:
            suffix = ""
        else:
            suffix = f"({number_index})"

        paths = _build_file_paths(
            daily_folder,
            suffix
        )

        all_paths = [
            paths["original_txt_path"],
            paths["erp_csv_path"],
            paths["duplicate_details_path"],
            paths["duplicate_summary_path"],
            paths["invalid_lines_path"],
            paths["processing_summary_path"],
        ]

        # A filename set is available only if every file is available.
        if not any(path.exists() for path in all_paths):
            paths["file_suffix"] = suffix
            return paths

        number_index += 1


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

    # ----------------------------------------------
    # SELECT AVAILABLE FILENAMES
    # ----------------------------------------------

    with _FILE_SAVE_LOCK:

        paths = _find_available_file_paths(daily_folder)

        reports_folder = paths["reports_folder"]

        reports_folder.mkdir(
            parents=True,
            exist_ok=True
        )

        all_file_paths = [
            paths["original_txt_path"],
            paths["erp_csv_path"],
            paths["duplicate_details_path"],
            paths["duplicate_summary_path"],
            paths["invalid_lines_path"],
            paths["processing_summary_path"],
        ]

        created_files = []

        try:

            # --------------------------------------
            # ORIGINAL TXT
            # --------------------------------------
            # Save the uploaded scanner TXT bytes exactly as received.
            # No parsing, modification or conversion is applied here.

            paths["original_txt_path"].write_bytes(
                original_file_bytes
            )

            created_files.append(
                paths["original_txt_path"]
            )

            # --------------------------------------
            # ERP CSV
            # --------------------------------------

            erp_columns = [
                "Date",
                "Time",
                "ScannerID",
                "BarcodeNumber"
            ]

            erp_upload_df = unique_df[erp_columns].copy()

            erp_upload_df.to_csv(
                paths["erp_csv_path"],
                index=False,
                header=False,
                encoding="utf-8",
                lineterminator="\n"
            )

            created_files.append(
                paths["erp_csv_path"]
            )

            # --------------------------------------
            # DUPLICATE DETAILS
            # --------------------------------------

            duplicate_rows_df.to_csv(
                paths["duplicate_details_path"],
                index=False,
                encoding="utf-8-sig"
            )

            created_files.append(
                paths["duplicate_details_path"]
            )

            # --------------------------------------
            # DUPLICATE SUMMARY
            # --------------------------------------

            duplicate_summary_df.to_csv(
                paths["duplicate_summary_path"],
                index=False,
                encoding="utf-8-sig"
            )

            created_files.append(
                paths["duplicate_summary_path"]
            )

            # --------------------------------------
            # INVALID LINES
            # --------------------------------------

            invalid_df.to_csv(
                paths["invalid_lines_path"],
                index=False,
                encoding="utf-8-sig"
            )

            created_files.append(
                paths["invalid_lines_path"]
            )

            # --------------------------------------
            # PROCESSING SUMMARY
            # --------------------------------------

            paths["processing_summary_path"].write_text(
                summary_text,
                encoding="utf-8"
            )

            created_files.append(
                paths["processing_summary_path"]
            )

        except Exception:

            # Remove only files created by this save operation.
            # Existing files are never deleted.
            for path in created_files:

                if path.exists():
                    path.unlink()

            raise

    return {
        "department": department["name"],
        "original_filename": original_filename,

        "daily_folder": daily_folder,
        "reports_folder": reports_folder,

        "original_txt_path": paths["original_txt_path"],
        "erp_csv_path": paths["erp_csv_path"],

        "duplicate_details_path": paths["duplicate_details_path"],
        "duplicate_summary_path": paths["duplicate_summary_path"],
        "invalid_lines_path": paths["invalid_lines_path"],
        "processing_summary_path": paths["processing_summary_path"],

        "file_suffix": paths["file_suffix"],

        "total_rows": total_rows,
        "unique_count": unique_count,
        "duplicate_count": duplicate_count,
    }


import pandas as pd


def build_outputs(df):
    """
    Remove duplicate barcodes and prepare report DataFrames.

    Duplicate rule:
    BarcodeNumber is the only field used to identify duplicates.
    The first occurrence is retained.

    Returns:
        unique_df
        duplicate_rows_df
        duplicate_summary_df
        total_rows
        unique_count
        duplicate_count
    """

    # --------------------------------------------------
    # STEP 1: Define output columns
    # --------------------------------------------------

    output_columns = [
        "Date",
        "Time",
        "ScannerID",
        "BarcodeNumber"
    ]

    duplicate_columns = output_columns + ["LineNumber"]

    summary_columns = [
        "BarcodeNumber",
        "TotalOccurrences",
        "FirstScanDate",
        "FirstScanTime",
        "FirstScannerID",
        "DuplicateOccurrences"
    ]


    # --------------------------------------------------
    # STEP 2: Handle empty input
    # --------------------------------------------------

    if df.empty:

        return (
            pd.DataFrame(columns=output_columns),
            pd.DataFrame(columns=duplicate_columns),
            pd.DataFrame(columns=summary_columns),
            0,
            0,
            0
        )


    # --------------------------------------------------
    # STEP 3: Count total valid records
    # --------------------------------------------------

    total_rows = len(df)


    # --------------------------------------------------
    # STEP 4: Identify duplicate barcodes
    # --------------------------------------------------

    duplicate_mask = df.duplicated(
        subset=["BarcodeNumber"],
        keep="first"
    )


    # First occurrence of each barcode
    unique_df = df.loc[
        ~duplicate_mask,
        output_columns
    ].copy()


    # Repeated occurrences
    duplicate_rows = df.loc[
        duplicate_mask
    ].copy()


    # --------------------------------------------------
    # STEP 5: Prepare duplicate details
    # --------------------------------------------------

    duplicate_rows_df = duplicate_rows[
        output_columns
    ].copy()

    duplicate_rows_df["LineNumber"] = duplicate_rows[
        "_LineNumber"
    ].values


    # --------------------------------------------------
    # STEP 6: Prepare duplicate summary
    # --------------------------------------------------

    barcode_counts = df.groupby(
        "BarcodeNumber",
        sort=False
    ).size()

    duplicate_barcodes = barcode_counts[
        barcode_counts > 1
    ].index

    summary_rows = []

    for barcode in duplicate_barcodes:

        barcode_records = df[
            df["BarcodeNumber"] == barcode
        ]

        first_record = barcode_records.iloc[0]

        total_occurrences = len(barcode_records)

        summary_rows.append({

            "BarcodeNumber": barcode,

            "TotalOccurrences": total_occurrences,

            "FirstScanDate": first_record["Date"],

            "FirstScanTime": first_record["Time"],

            "FirstScannerID": first_record["ScannerID"],

            "DuplicateOccurrences": total_occurrences - 1

        })


    duplicate_summary_df = pd.DataFrame(
        summary_rows,
        columns=summary_columns
    )


    # --------------------------------------------------
    # STEP 7: Calculate final counts
    # --------------------------------------------------

    unique_count = len(unique_df)

    duplicate_count = len(duplicate_rows_df)


    # --------------------------------------------------
    # STEP 8: Return all outputs
    # --------------------------------------------------

    return (
        unique_df,
        duplicate_rows_df,
        duplicate_summary_df,
        total_rows,
        unique_count,
        duplicate_count
    )

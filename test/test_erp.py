
from pathlib import Path
import argparse

from config.departments import get_department
from automation.erp_client import upload_and_process


def main():

    parser = argparse.ArgumentParser(
        description="Controlled Stickering ERP live test."
    )

    parser.add_argument(
        "csv_file",
        help="Path to the test CSV file."
    )

    args = parser.parse_args()

    csv_path = Path(args.csv_file)

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Test CSV not found: {csv_path}"
        )

    department = get_department("stickering")

    print("\n========== STICKERING ERP LIVE TEST ==========")
    print(f"Department: {department['name']}")
    print(f"CSV file: {csv_path}")
    print("\nThis test will:")
    print("1. Insert CSV records into Barcode_Row_Stickering.")
    print("2. Submit the Stickering processing form.")
    print("3. Process ALL pending Status='0' records.")
    print("\nConfirm that:")
    print("- The relevant tables have been backed up.")
    print("- No unrelated pending records exist.")
    print("- The test barcode is suitable and not already processed.")

    confirmation = input(
        "\nType LIVE TEST to continue: "
    )

    if confirmation != "LIVE TEST":
        print("Test cancelled. No ERP request was sent.")
        return

    result = upload_and_process(
        department=department,
        csv_path=csv_path
    )

    print("\n========== TEST RESULT ==========")
    print(result)


if __name__ == "__main__":
    main()

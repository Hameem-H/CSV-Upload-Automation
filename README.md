# Barcode TXT to CSV Converter

## What it does
- Drag and drop a scanner TXT file.
- Reads rows in this format: `DD/MM/YYYY,HH:MM:SS,ScannerID,BarcodeNumber`
- Keeps the first occurrence of each BarcodeNumber.
- Counts duplicate scans removed.
- Shows unique barcode count and invalid line count.
- Saves the cleaned CSV under the selected department folder.
- Saves duplicate, invalid-line, and summary reports separately.
- Does not modify the original TXT file.

## Run on Windows
1. Install Python 3.10 or newer from https://www.python.org/downloads/
2. During installation, enable **Add Python to PATH**.
3. Extract this ZIP to a folder, for example `C:\BarcodeAutomation\Application`.
4. Double-click `run_app.bat`.
5. Your browser will open the local dashboard.

## Default output location
`%USERPROFILE%\BarcodeAutomation\Output`

Each department gets:
- `CSV`
- `Reports`

You can change the output root folder in the dashboard sidebar.

## Important processing rule
Duplicate detection is based on BarcodeNumber only. If a barcode occurs multiple times, the first row is kept and all later occurrences are excluded from the cleaned CSV.

## Notes
- ScannerID and BarcodeNumber are read as text to preserve leading zeros.
- Date and time are validated as DD/MM/YYYY and HH:MM:SS.
- Lines that do not contain exactly four non-empty comma-separated fields, or have invalid date/time values, are listed in the invalid-lines report.
- This first version only creates local files. It does not connect to or upload anything to the ERP.

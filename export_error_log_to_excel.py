"""Convert error_log.json to Excel-friendly CSV (and optionally .xlsx)."""
import json
import csv
from pathlib import Path

JSON_PATH = Path(r"c:\Users\ShawnStubbs\Downloads\error_log.json")
OUTPUT_CSV = Path(r"c:\Users\ShawnStubbs\Downloads\error_log.csv")
OUTPUT_XLSX = Path(r"c:\Users\ShawnStubbs\Downloads\error_log.xlsx")

# Columns we want from 'sent' (in order)
SENT_COLUMNS = [
    "LicenseNumber", "Title", "PhoneNumber", "Address", "City", "Region",
    "PostCode", "Country", "Area", "Email", "ContactInformation",
    "Brand", "Flavour", "Pack_x0020_Size", "Delivery_x0020_Type", "Distributor",
]

def main():
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build header: action, title, status, error fields, then sent fields
    error_cols = ["Error_Code", "Error_Message", "Error_Date", "Request_ID"]
    header = ["Action", "Title", "Status"] + error_cols + SENT_COLUMNS

    rows = []
    for entry in data:
        err = entry.get("error", {}).get("error", {})
        inner = err.get("innerError", {})
        sent = entry.get("sent", {})

        row = [
            entry.get("action", ""),
            entry.get("title", ""),
            entry.get("status", ""),
            err.get("code", ""),
            err.get("message", ""),
            inner.get("date", ""),
            inner.get("request-id", ""),
        ]
        for col in SENT_COLUMNS:
            row.append(sent.get(col, ""))
        rows.append(row)

    # Ensure we have all SENT_COLUMNS that might appear in data
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV}")

    # Try to write .xlsx if openpyxl is available
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Error Log"
        for c, h in enumerate(header, 1):
            ws.cell(row=1, column=c, value=h)
        for r, row in enumerate(rows, 2):
            for c, val in enumerate(row, 1):
                ws.cell(row=r, column=c, value=val)
        # Auto-fit would require measuring; just save
        wb.save(OUTPUT_XLSX)
        print(f"Wrote {OUTPUT_XLSX}")
    except ImportError:
        print("Openpyxl not installed. Only CSV was created. Install with: pip install openpyxl")

if __name__ == "__main__":
    main()

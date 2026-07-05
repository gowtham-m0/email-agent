import os 
import gspread
from datetime import datetime
from dotenv import load_dotenv
from auth_helpers import get_google_credentials

load_dotenv()

def get_sheet():
    """
    Connect and return all three sheets.
    """
    sheet_id = os.getenv("SHEET_ID")
    if not sheet_id:
        print("\n❌  SHEET_ID is not set.")
        print("    Add it to your .env file:  SHEET_ID=your_google_sheet_id")
        print("    (It's the long ID in your Google Sheets URL)\n")
        raise SystemExit(1)
    creds = get_google_credentials()
    client = gspread.Client(auth=creds)
    workbook = client.open_by_key(sheet_id)
    return {
        "important": workbook.worksheet("Important"),
        "okay": workbook.worksheet("Okay"),
        "unwanted": workbook.worksheet("Spam")
    }

def setup_headers(sheets: dict):
    """
    Add headers to all the sheets if empty.
    """
    for name, sheet in sheets.items():
        first_cell = sheet.cell(1,1).value
        if not first_cell:
            sheet.append_row([
                "Date","Sender","Subject","Category","Reason", "Action"
        ])

        sheet.format("A1:F1", {"textFormat": {"bold": True}})
    
def log_emails_batch(sheets: dict, logs: list):
    """
    Log entire batch to Google Sheets in ONE API call per tab.
    Instead of 50 append_row() calls → max 3 append_rows() calls (one per tab).

    logs: list of dicts with keys date, sender, subject, category, reason, action.
    Unknown categories fall back to "okay" so bad data never silently drops rows.
    """
    groups = {"important": [], "okay": [], "unwanted": []}

    for item in logs:
        category = item.get("category", "okay")
        if category not in groups:
            category = "okay"

        row = [
            item.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
            item.get("sender", ""),
            item.get("subject", ""),
            category,
            item.get("reason", ""),
            item.get("action", "KEPT"),
        ]
        groups[category].append(row)

    for category, rows in groups.items():
        if rows:
            sheet = sheets.get(category, sheets.get("okay"))
            if sheet:
                sheet.append_rows(rows, value_input_option="RAW")
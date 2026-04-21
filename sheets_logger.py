import os 
import gspread
from google.oauth2.credentials import Credentials
from datetime import datetime
from config import SCOPES
from dotenv import load_dotenv

load_dotenv()

def get_sheet():
    """
    Connect and return all three sheets.
    """
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    client = gspread.authorize(creds)
    workbook = client.open_by_key(os.getenv("SHEET_ID"))
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
    
def log_email(sheets: dict, email: dict, category: str, reason: str, action: str):
    """
    Log email to the correct sheet based on category.
    """
    sheet = sheets.get(category, sheets["okay"])  # Default to "okay" if category is unknown
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        email["sender"],
        email["subject"],
        category.upper(),
        reason,
        action
    ])
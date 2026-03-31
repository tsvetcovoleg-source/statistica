import os
import json
import gspread
from google.oauth2.service_account import Credentials

print("=== START ===")

service_account_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
sheet_id = os.environ["GOOGLE_SHEET_ID"]

print("Secrets loaded")

info = json.loads(service_account_json)

creds = Credentials.from_service_account_info(
    info,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)

print("Credentials created")

gc = gspread.authorize(creds)
print("gspread authorized")

sh = gc.open_by_key(sheet_id)
print("Spreadsheet opened")

ws = sh.sheet1
print("Worksheet title:", ws.title)
print("First row:", ws.row_values(1))

print("=== DONE ===")

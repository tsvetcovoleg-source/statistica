import os
import json
import gspread
from google.oauth2.service_account import Credentials

print("Start...")

service_account_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
sheet_id = os.environ["GOOGLE_SHEET_ID"]

info = json.loads(service_account_json)

creds = Credentials.from_service_account_info(
    info,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)

gc = gspread.authorize(creds)
sh = gc.open_by_key(sheet_id)

print("Connected to Google Sheets!")

ws = sh.sheet1
print("First row:", ws.row_values(1))

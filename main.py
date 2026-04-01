import asyncio
import csv
import json
import os
import re
from io import StringIO

import gspread
import pandas as pd
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# test

def clean_cell(value):
    if pd.isna(value):
        return "0"
    text = str(value).strip()
    if text in {"", "nan", "None"}:
        return "0"
    return text


def get_info_map(report_data):
    info_df = report_data["info_df"].copy()
    return dict(zip(info_df["field"], info_df["value"]))


def build_report_key(report_data):
    info_map = get_info_map(report_data)
    year = str(info_map.get("Anul bugetar", "")).strip()
    source = str(info_map.get("Sursa", "")).strip()
    return f"{year}-{source}"


def dataframe_to_csv_text(df, section_name):
    output = StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")

    if df is None or len(df) == 0:
        writer.writerow(["SECTION", "EMPTY"])
        writer.writerow([section_name, "1"])
        return output.getvalue()

    df = df.copy()
    indicator_col = None
    code_col = None

    for col in df.columns:
        if str(col).strip().lower() == "indicatori":
            indicator_col = col
        if "Cod rd" in str(col):
            code_col = col

    value_cols = [col for col in df.columns if col not in [indicator_col, code_col]]
    header = ["SECTION", "CODE", "INDICATOR"] + [f"VALUE_{i+1}" for i in range(len(value_cols))]
    writer.writerow(header)

    for _, row in df.iterrows():
        out_row = [
            section_name,
            clean_cell(row.get(code_col, "")),
            clean_cell(row.get(indicator_col, "")),
        ]
        for col in value_cols:
            out_row.append(clean_cell(row.get(col, 0)))
        writer.writerow(out_row)

    return output.getvalue()


def meta_to_csv_text(report_data):
    output = StringIO()
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    info_map = get_info_map(report_data)

    writer.writerow(["FIELD", "VALUE"])
    for key, value in info_map.items():
        writer.writerow([clean_cell(key), clean_cell(value)])

    writer.writerow(["PERIOD_FROM", clean_cell(report_data.get("period_from", ""))])
    writer.writerow(["PERIOD_TO", clean_cell(report_data.get("period_to", ""))])

    return output.getvalue()


def parse_financial_report(html):
    soup = BeautifulSoup(html, "lxml")
    full_text = soup.get_text("\n", strip=True)

    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        tables = []

    info_fields = [
        "Statut document",
        "Tip document",
        "Anul bugetar",
        "Sursa",
        "Denumirea entităţii juridice",
        "Cod IDNO",
        "Cod CUIÎO",
        "Cod poştal",
        "Cod CUATM",
        "Adresa",
        "Cod CAEM",
        "Cod CFP",
        "Cod CFOJ",
        "Numărul mediu al salariaţilor în perioada de gestiune",
        "Persoana (Administrator) responsabilă de semnarea situațiilor financiare",
        "Unitatea de măsură",
    ]

    lines = [line.strip() for line in full_text.split("\n") if line.strip()]
    info_data = []
    normalized_fields = {field.rstrip(":"): field.rstrip(":") for field in info_fields}

    for i, line in enumerate(lines):
        clean_line = line.rstrip(":").strip()
        if clean_line in normalized_fields:
            value = lines[i + 1] if i + 1 < len(lines) else ""
            info_data.append({"field": clean_line, "value": value})

    info_df = pd.DataFrame(info_data).drop_duplicates()

    period_match = re.search(r"pentru perioada\s+(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})", full_text)
    report_period_from = period_match.group(1) if period_match else ""
    report_period_to = period_match.group(2) if period_match else ""

    bilan_df = tables[0].copy() if len(tables) > 0 else pd.DataFrame()
    pnl_df = tables[1].copy() if len(tables) > 1 else pd.DataFrame()
    equity_df = tables[2].copy() if len(tables) > 2 else pd.DataFrame()
    cashflow_df = tables[3].copy() if len(tables) > 3 else pd.DataFrame()

    return {
        "info_df": info_df,
        "bilan_df": bilan_df.fillna(0),
        "pnl_df": pnl_df.fillna(0),
        "equity_df": equity_df.fillna(0),
        "cashflow_df": cashflow_df.fillna(0),
        "period_from": report_period_from,
        "period_to": report_period_to,
    }


def upsert_report_to_sheet(ws, source_profile_url, report_data):
    info_map = get_info_map(report_data)
    idno_value = str(info_map.get("Cod IDNO", "")).strip()
    report_key = build_report_key(report_data)

    if not report_key.strip() or report_key == "-":
        return False

    meta_csv = meta_to_csv_text(report_data)
    bilan_csv = dataframe_to_csv_text(report_data["bilan_df"], "BIL")
    pnl_csv = dataframe_to_csv_text(report_data["pnl_df"], "PNL")
    equity_csv = dataframe_to_csv_text(report_data["equity_df"], "EQT")
    cashflow_csv = dataframe_to_csv_text(report_data["cashflow_df"], "CF")

    prefixed_values = {
        "META": f"REPORT_KEY={report_key}\n{meta_csv}",
        "BIL": f"REPORT_KEY={report_key}\n{bilan_csv}",
        "PNL": f"REPORT_KEY={report_key}\n{pnl_csv}",
        "EQT": f"REPORT_KEY={report_key}\n{equity_csv}",
        "CF": f"REPORT_KEY={report_key}\n{cashflow_csv}",
    }

    headers = ["IDNO", "PROFILE_URL"]
    all_values = ws.get_all_values()

    if not all_values:
        ws.append_row(headers)
        all_values = [headers]

    current_header = all_values[0]
    header_map = {name: idx for idx, name in enumerate(current_header)}

    required_base_headers = ["IDNO", "PROFILE_URL"]
    missing_base_headers = [h for h in required_base_headers if h not in header_map]
    if missing_base_headers:
        current_header.extend(missing_base_headers)
        ws.update(range_name="1:1", values=[current_header])
        all_values = ws.get_all_values()
        current_header = all_values[0]
        header_map = {name: idx for idx, name in enumerate(current_header)}

    rows = all_values[1:] if len(all_values) > 1 else []
    target_row_index = None

    for i, row in enumerate(rows, start=2):
        idno_idx = header_map["IDNO"]
        row_idno = row[idno_idx] if len(row) > idno_idx else ""
        if str(row_idno).strip() == idno_value:
            target_row_index = i
            break

    report_sections = ["META", "BIL", "PNL", "EQT", "CF"]

    if target_row_index is None:
        padded_row = [""] * len(current_header)
    else:
        existing_row = rows[target_row_index - 2]
        padded_row = existing_row + [""] * (len(current_header) - len(existing_row))

    padded_row[header_map["IDNO"]] = idno_value
    padded_row[header_map["PROFILE_URL"]] = source_profile_url

    start_col = 2
    block_size = len(report_sections)
    report_block_start = None

    def is_matching_report_block(row_values, block_start, key):
        if len(row_values) <= block_start:
            return False
        cell = str(row_values[block_start]).strip()
        return cell.startswith(f"REPORT_KEY={key}\n")

    for block_start in range(start_col, len(padded_row), block_size):
        if is_matching_report_block(padded_row, block_start, report_key):
            report_block_start = block_start
            break

    if report_block_start is None:
        for block_start in range(start_col, len(padded_row), block_size):
            block = padded_row[block_start:block_start + block_size]
            if not block or all(not str(cell).strip() for cell in block):
                report_block_start = block_start
                break

    if report_block_start is None:
        report_block_start = len(padded_row)

    required_len = report_block_start + block_size
    if len(padded_row) < required_len:
        padded_row.extend([""] * (required_len - len(padded_row)))

    while len(current_header) < required_len:
        report_number = ((len(current_header) - start_col) // block_size) + 1
        for section in report_sections:
            current_header.append(f"REPORT_{report_number}_{section}")
            if len(current_header) >= required_len:
                break

    for offset, section in enumerate(report_sections):
        padded_row[report_block_start + offset] = prefixed_values[section]

    ws.update(range_name="1:1", values=[current_header])

    if target_row_index is None:
        ws.append_row(padded_row)
    else:
        end_col_letter = gspread.utils.rowcol_to_a1(1, len(current_header)).rstrip("1")
        ws.update(
            range_name=f"A{target_row_index}:{end_col_letter}{target_row_index}",
            values=[padded_row],
        )

    return True


def get_first_profile_links(ws_source, limit=10):
    values = ws_source.get_all_values()
    if not values:
        return []

    header = [str(cell).strip().upper() for cell in values[0]]
    profile_col_idx = 1
    status_col_idx = 2
    done_col_idx = 3

    if "PROFILE_URL" in header:
        profile_col_idx = header.index("PROFILE_URL")
    if "STATUS" in header:
        status_col_idx = header.index("STATUS")
    if "DONE" in header:
        done_col_idx = header.index("DONE")

    links = []
    for row in values[1:]:
        profile_url = row[profile_col_idx].strip() if len(row) > profile_col_idx else ""
        status = row[status_col_idx].strip().lower() if len(row) > status_col_idx else ""
        done_status = row[done_col_idx].strip().lower() if len(row) > done_col_idx else ""

        if (
            "/economic-agent/" in profile_url
            and status in {"", "found", "partial"}
            and done_status != "done"
        ):
            links.append(profile_url)

        if len(links) >= limit:
            break

    return links


def mark_link_done(ws_source, profile_url, profile_url_to_row):
    row_idx = profile_url_to_row.get(profile_url)
    if row_idx:
        ws_source.update_cell(row_idx, 4, "Done")
        return True
    return False


async def process_all_periods(profile_url, ws, browser):
    page = await browser.new_page(viewport={"width": 1800, "height": 5000})
    try:
        await page.goto(profile_url, wait_until="networkidle", timeout=120000)
        await page.wait_for_timeout(3500)

        tabs = page.locator('[role="tab"]')
        tab_opened = False

        for i in range(await tabs.count()):
            tab = tabs.nth(i)
            text = (await tab.inner_text()).strip()
            if "Situaţii financiare publice" in text:
                await tab.click()
                await page.wait_for_timeout(2200)
                tab_opened = True
                break

        if not tab_opened:
            return 0, 0

        all_texts = await page.locator("body *").all_text_contents()
        periods = []
        for txt in all_texts:
            txt = txt.strip()
            if re.fullmatch(r"20\d{2}-[A-Z]+", txt):
                periods.append(txt)

        periods = list(dict.fromkeys(periods))
        inserted_count = 0

        for period in periods:
            try:
                period_btn = page.locator(f"text={period}")
                if await period_btn.count() == 0:
                    continue

                await period_btn.first.click()
                await page.wait_for_timeout(3000)

                html = await page.content()
                report_data = parse_financial_report(html)
                saved = upsert_report_to_sheet(ws, profile_url, report_data)
                if saved:
                    inserted_count += 1
            except Exception as exc:
                print(f"{profile_url} | period={period} | error: {exc}")

        return len(periods), inserted_count
    finally:
        await page.close()


async def run_profile_links_pipeline(ws_source, ws_result, browser, limit=10):
    links = get_first_profile_links(ws_source, limit=limit)
    print(f"Found links for processing: {len(links)}")
    values = ws_source.get_all_values()
    profile_url_to_row = {}
    for row_idx, row in enumerate(values[1:], start=2):
        if len(row) > 1:
            profile_url_to_row[row[1].strip()] = row_idx

    for idx, profile_url in enumerate(links, start=1):
        print(f"[{idx}/{len(links)}] {profile_url}")
        try:
            found_count, inserted_count = await process_all_periods(profile_url, ws_result, browser)
            print(f"Reports found: {found_count} | inserted/updated: {inserted_count}")
            if found_count > 0 and inserted_count >= found_count:
                mark_link_done(ws_source, profile_url, profile_url_to_row)
                print("Source status in column D: Done")
        except Exception as exc:
            print(f"{profile_url} | fatal error: {exc}")
        await asyncio.sleep(2)


def get_or_create_worksheet(spreadsheet, title, rows=2000, cols=20):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def get_or_create_result_worksheet(spreadsheet, title, rows=2000, cols=20):
    return get_or_create_worksheet(spreadsheet, title, rows=rows, cols=cols)


def worksheet_has_required_source_columns(worksheet):
    values = worksheet.get_all_values()
    if not values:
        return False
    header = {str(cell).strip().upper() for cell in values[0]}
    return {"IDNO", "PROFILE_URL", "STATUS"}.issubset(header)


def get_required_source_worksheet(spreadsheet, title):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound as exc:
        fallback_titles = ["links", "Links", "LINKS"]
        for fallback_title in fallback_titles:
            try:
                worksheet = spreadsheet.worksheet(fallback_title)
                if worksheet_has_required_source_columns(worksheet):
                    print(
                        f"Source sheet '{title}' was not found. "
                        f"Using fallback source sheet '{worksheet.title}'."
                    )
                    return worksheet
            except gspread.WorksheetNotFound:
                continue

        for worksheet in spreadsheet.worksheets():
            if worksheet_has_required_source_columns(worksheet):
                print(
                    f"Source sheet '{title}' was not found. "
                    f"Using detected source sheet '{worksheet.title}'."
                )
                return worksheet

        raise RuntimeError(
            f"Source sheet '{title}' was not found. "
            "Set SOURCE_SHEET_NAME to the correct tab name (for example 'links') "
            "or create a tab with columns IDNO, PROFILE_URL, STATUS."
        ) from exc


async def main():
    print("=== START ===")

    service_account_json = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]

    source_sheet_name = os.environ.get("SOURCE_SHEET_NAME", "IDNO")
    result_sheet_name = os.environ.get("RESULT_SHEET_NAME", "stat")
    max_links = int(os.environ.get("MAX_PROFILE_LINKS", "10"))

    creds = Credentials.from_service_account_info(
        json.loads(service_account_json),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )

    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)

    ws_source = get_required_source_worksheet(sh, source_sheet_name)
    ws_result = get_or_create_result_worksheet(sh, result_sheet_name)

    print(f"Source sheet: {ws_source.title}")
    print(f"Result sheet: {ws_result.title}")
    print(f"MAX_PROFILE_LINKS={max_links}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        try:
            await run_profile_links_pipeline(ws_source, ws_result, browser, limit=max_links)
        finally:
            await browser.close()

    print("=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())

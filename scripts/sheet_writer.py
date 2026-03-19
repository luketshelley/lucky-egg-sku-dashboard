"""
sheet_writer.py - Lucky Egg SKU Dashboard
Writes parsed sales records into the Google Sheet.
Sheet structure:
  Tab "Config": SKU_ID | Name | Group (hero/launch/pass)
  Tab "Sales":  Date | SKU_ID | Region | Channel | Units
"""
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SALES_SHEET = "Sales"
CONFIG_SHEET = "Config"
def get_sheets_service(creds_json):
    creds = service_account.Credentials.from_service_account_info(
        creds_json, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)
def get_existing_dates(service, sheet_id):
    """Return set of (date, sku, region, channel) already in the Sales tab."""
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{SALES_SHEET}!A2:E"
        ).execute()
        rows = res.get("values", [])
        return {(r[0], r[1], r[2], r[3]) for r in rows if len(r) >= 4}
    except Exception as e:
        log.warning("Could not read existing sales: %s", e)
        return set()
def write_records(creds_json, sheet_id, records):
    """
    Append new sales records to the Sales tab, skipping duplicates.
    Creates the Sales tab header row if it doesn't exist yet.
    """
    service = get_sheets_service(creds_json)
    # Ensure Sales tab has headers
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range=f"{SALES_SHEET}!A1:E1"
        ).execute()
        if not res.get("values"):
            service.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{SALES_SHEET}!A1",
                valueInputOption="RAW",
                body={"values": [["Date", "SKU_ID", "Region", "Channel", "Units"]]}
            ).execute()
            log.info("Created Sales tab headers")
    except Exception:
        pass
    existing = get_existing_dates(service, sheet_id)
    new_rows = []
    for r in records:
        key = (r["date"], r["sku"], r["region"], r["channel"])
        if key in existing:
            log.debug("Skipping duplicate: %s", key)
            continue
        new_rows.append([r["date"], r["sku"], r["region"], r["channel"], r["units"]])
    if not new_rows:
        log.info("No new records to write")
        return 0
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{SALES_SHEET}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows}
    ).execute()
    log.info("Wrote %d new records to sheet", len(new_rows))
    return len(new_rows)
def get_sku_config(creds_json, sheet_id):
    """
    Read Config tab and return list of {id, name, group} dicts.
    Config tab columns: SKU_ID | Name | Group
    """
    service = get_sheets_service(creds_json)
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{CONFIG_SHEET}!A2:C"
        ).execute()
        rows = res.get("values", [])
        skus = []
        for r in rows:
            if len(r) >= 1 and r[0]:
                skus.append({
                    "id":    r[0].strip(),
                    "name":  r[1].strip() if len(r) > 1 else r[0].strip(),
                    "group": r[2].strip().lower() if len(r) > 2 else "pass",
                })
        log.info("Loaded %d SKUs from Config tab", len(skus))
        return skus
    except Exception as e:
        log.error("Could not read Config tab: %s", e)
        return []
def get_sales_last_n_days(creds_json, sheet_id, days=15):
    """
    Read Sales tab and return records from the last N days,
    aggregated by {date, sku, region, channel} → units.
    """
    from datetime import timedelta
    service = get_sheets_service(creds_json)
    cutoff = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        res = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{SALES_SHEET}!A2:E"
        ).execute()
        rows = res.get("values", [])
    except Exception as e:
        log.error("Could not read Sales tab: %s", e)
        return []
    records = []
    for r in rows:
        if len(r) < 5:
            continue
        date, sku, region, channel = r[0], r[1], r[2], r[3]
        try:
            units = int(float(r[4]))
        except (ValueError, TypeError):
            continue
        if date >= cutoff:
            records.append({
                "date": date, "sku": sku,
                "region": region, "channel": channel, "units": units
            })
    log.info("Loaded %d sales records from last %d days", len(records), days)
    return records
if __name__ == "__main__":
    import json, os
    with open(os.environ.get("GOOGLE_CREDS_PATH", "credentials.json")) as f:
        creds = json.load(f)
    sheet_id = os.environ["SHEET_ID"]
    skus = get_sku_config(creds, sheet_id)
    for s in skus:
        print(s)

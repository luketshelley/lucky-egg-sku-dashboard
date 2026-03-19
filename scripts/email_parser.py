python"""
email_parser.py - Lucky Egg SKU Dashboard
Connects to hey@luckyegg.co via Gmail API (service account + domain delegation).
Finds Amazon Business Report + TikTok Shop scheduled report emails,
downloads CSV attachments, returns parsed sales records.
Record format: {date, sku, region, channel, units}
"""
import os, base64, csv, io, logging
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
GMAIL_USER = "hey@luckyegg.co"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]
REGION_MAP = {
    "UK":"UK","GB":"UK","UNITED KINGDOM":"UK","AMAZON.CO.UK":"UK",
    "US":"US","UNITED STATES":"US","AMAZON.COM":"US",
    "CA":"CA","CANADA":"CA","AMAZON.CA":"CA",
}
AMZ_COLS = {
    "date":  ["Date","Report Date","date"],
    "sku":   ["SKU","Seller SKU","ASIN","Child ASIN"],
    "units": ["Units Ordered","Units ordered","units_ordered"],
    "region":["Marketplace","marketplace","Region"],
}
TT_COLS = {
    "date":  ["Order Created Time","created_date","Date"],
    "sku":   ["Seller SKU","seller_sku","SKU ID"],
    "units": ["Quantity","quantity","Units"],
    "region":["Warehouse Country","Shop Region","country","Region"],
}
def get_gmail_service(creds_json):
    creds = service_account.Credentials.from_service_account_info(
        creds_json, scopes=SCOPES).with_subject(GMAIL_USER)
    return build("gmail","v1",credentials=creds,cache_discovery=False)
def search_emails(service, query, max_results=5):
    res = service.users().messages().list(userId="me",q=query,maxResults=max_results).execute()
    return res.get("messages",[])
def get_csv_content(service, msg_id):
    msg = service.users().messages().get(userId="me",id=msg_id,format="full").execute()
    def walk(parts):
        for p in parts:
            if p.get("parts"): yield from walk(p["parts"])
            fname = p.get("filename",""); mime = p.get("mimeType","")
            if fname.lower().endswith(".csv") or "csv" in mime:
                data = p.get("body",{}).get("data")
                if data:
                    yield base64.urlsafe_b64decode(data).decode("utf-8-sig",errors="replace")
                else:
                    att_id = p["body"]["attachmentId"]
                    att = service.users().messages().attachments().get(
                        userId="me",messageId=msg_id,id=att_id).execute()
                    yield base64.urlsafe_b64decode(att["data"]).decode("utf-8-sig",errors="replace")
    for c in walk(msg.get("payload",{}).get("parts",[])):
        return c
    return None
def find_col(headers, candidates):
    lo = [h.lower().strip() for h in headers]
    for c in candidates:
        if c.lower() in lo: return headers[lo.index(c.lower())]
    return None
def normalise_region(raw):
    return REGION_MAP.get(raw.strip().upper(),"UK")
def parse_date(raw):
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%m/%d/%Y","%d-%m-%Y","%b %d, %Y","%d %b %Y"):
        try: return datetime.strptime(raw.strip(),fmt).strftime("%Y-%m-%d")
        except ValueError: pass
    try: return datetime.fromisoformat(raw.strip()[:10]).strftime("%Y-%m-%d")
    except: return raw.strip()
def parse_amazon_csv(content):
    records = []
    reader = csv.DictReader(io.StringIO(content))
    h = reader.fieldnames or []
    col_date=find_col(h,AMZ_COLS["date"]); col_sku=find_col(h,AMZ_COLS["sku"])
    col_units=find_col(h,AMZ_COLS["units"]); col_region=find_col(h,AMZ_COLS["region"])
    if not col_units:
        log.warning("Amazon CSV: units column not found. Headers: %s",h); return records
    today = datetime.today().strftime("%Y-%m-%d")
    for row in reader:
        try:
            units = int(float(row.get(col_units,0) or 0))
            if units <= 0: continue
            records.append({
                "date":    parse_date(row.get(col_date,today)),
                "sku":     (row.get(col_sku,"") or "").strip(),
                "region":  normalise_region(row.get(col_region,"UK") if col_region else "UK"),
                "channel": "amazon",
                "units":   units,
            })
        except Exception as e: log.debug("Skipping Amazon row: %s",e)
    log.info("Parsed %d Amazon records",len(records)); return records
def parse_tiktok_csv(content):
    records = []
    reader = csv.DictReader(io.StringIO(content))
    h = reader.fieldnames or []
    col_date=find_col(h,TT_COLS["date"]); col_sku=find_col(h,TT_COLS["sku"])
    col_units=find_col(h,TT_COLS["units"]); col_region=find_col(h,TT_COLS["region"])
    if not col_units:
        log.warning("TikTok CSV: units column not found. Headers: %s",h); return records
    today = datetime.today().strftime("%Y-%m-%d")
    for row in reader:
        try:
            status = row.get("Order Status",row.get("status","")).lower()
            if any(x in status for x in ["cancel","return","refund"]): continue
            units = int(float(row.get(col_units,0) or 0))
            if units <= 0: continue
            records.append({
                "date":    parse_date(row.get(col_date,today)) if col_date else today,
                "sku":     (row.get(col_sku,"") or "").strip(),
                "region":  normalise_region(row.get(col_region,"UK") if col_region else "UK"),
                "channel": "tiktok",
                "units":   units,
            })
        except Exception as e: log.debug("Skipping TikTok row: %s",e)
    log.info("Parsed %d TikTok records",len(records)); return records
def fetch_all_records(creds_json, days_back=2):
    service = get_gmail_service(creds_json)
    all_records = []
    since = (datetime.today()-timedelta(days=days_back)).strftime("%Y/%m/%d")
    for q in [
        f'from:noreply@amazon.co.uk subject:"Business Report" after:{since} has:attachment',
        f'from:noreply@amazon.com subject:"Business Report" after:{since} has:attachment',
        f'from:amazon after:{since} subject:"report" has:attachment filename:csv',
    ]:
        msgs = search_emails(service,q)
        if msgs:
            log.info("Amazon: %d email(s) found",len(msgs))
            for m in msgs:
                c = get_csv_content(service,m["id"])
                if c: all_records.extend(parse_amazon_csv(c))
            break
    for q in [
        f'from:notification@tiktok.com after:{since} has:attachment filename:csv',
        f'subject:"TikTok Shop" subject:"report" after:{since} has:attachment',
        f'from:tiktok after:{since} has:attachment filename:csv',
    ]:
        msgs = search_emails(service,q)
        if msgs:
            log.info("TikTok: %d email(s) found",len(msgs))
            for m in msgs:
                c = get_csv_content(service,m["id"])
                if c: all_records.extend(parse_tiktok_csv(c))
            break
    log.info("Total records: %d",len(all_records))
    return all_records
if __name__ == "__main__":
    import json
    with open(os.environ.get("GOOGLE_CREDS_PATH","credentials.json")) as f:
        creds = json.load(f)
    for r in fetch_all_records(creds)[:5]:
        print(r)

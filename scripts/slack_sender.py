"""
slack_sender.py - Lucky Egg SKU Dashboard
Takes a screenshot of each SKU's dashboard page and posts it to the
correct Slack channel based on group (hero/launch/pass).
Requires: playwright, requests
Slack channels:
  hero   → #hero-product-updates
  launch → #product-launch
  pass   → #passed-products
"""
import os, json, logging, time, requests, re
from datetime import datetime
from playwright.sync_api import sync_playwright
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "https://lucky-egg-sku-dashboard.vercel.app")
SHEET_ID      = os.environ.get("SHEET_ID", "")
SLACK_CHANNELS = {
    "hero":   os.environ.get("SLACK_WEBHOOK_HERO",   ""),
    "launch": os.environ.get("SLACK_WEBHOOK_LAUNCH", ""),
    "pass":   os.environ.get("SLACK_WEBHOOK_PASS",   ""),
}
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_IDS = {
    "hero":   os.environ.get("SLACK_CHANNEL_HERO",   "hero-product-updates"),
    "launch": os.environ.get("SLACK_CHANNEL_LAUNCH", "product-launch"),
    "pass":   os.environ.get("SLACK_CHANNEL_PASS",   "passed-products"),
}
def screenshot_sku(page, sku_id, sku_name, output_path):
    """Load the dashboard, navigate to a SKU, take a screenshot."""
    url = f"{DASHBOARD_URL}?sheet={SHEET_ID}#sku-{sku_id}"
    log.info("Screenshotting %s at %s", sku_name, url)
    page.goto(url, wait_until="networkidle", timeout=30000)
    time.sleep(2)  # allow charts to render
    # Click the SKU in the sidebar
    try:
        page.locator(f"[id='nav-{sku_id}']").click(timeout=5000)
        time.sleep(1.5)
    except Exception:
        log.warning("Could not click nav item for %s, using full page", sku_id)
    # Screenshot just the main content area
    try:
        main = page.locator("#mainContent")
        main.screenshot(path=output_path)
    except Exception:
        page.screenshot(path=output_path, full_page=False)
    log.info("Saved screenshot: %s", output_path)
def post_to_slack(webhook_url, channel, sku_name, sku_id, group, image_path):
    """Post screenshot to Slack via webhook + file upload."""
    today = datetime.today().strftime("%d %b %Y")
    # If using bot token, upload file then post
    if SLACK_BOT_TOKEN:
        # Upload image
        with open(image_path, "rb") as f:
            upload_res = requests.post(
                "https://slack.com/api/files.upload",
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
                data={
                    "channels": channel,
                    "filename": f"{sku_id}.png",
                    "title": f"{sku_name} — {today}",
                    "initial_comment": f"*{sku_name}* (`{sku_id}`) daily update — {today}",
                },
                files={"file": f}
            )
        if upload_res.json().get("ok"):
            log.info("Posted %s to #%s via file upload", sku_name, channel)
        else:
            log.error("Slack file upload failed: %s", upload_res.text)
        return
    # Fallback: post text summary via webhook
    if webhook_url:
        emoji = "🏆" if group == "hero" else "🚀" if group == "launch" else "📦"
        payload = {
            "text": f"{emoji} *{sku_name}* (`{sku_id}`) — Daily Update {today}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{sku_name}* (`{sku_id}`)\\n📅 Daily update — {today}\\n🔗 <{DASHBOARD_URL}|View Dashboard>"
                    }
                }
            ]
        }
        res = requests.post(webhook_url, json=payload)
        if res.status_code == 200:
            log.info("Posted %s to Slack via webhook", sku_name)
        else:
            log.error("Slack webhook failed: %s", res.text)
def run(skus):
    """
    Main entry point.
    skus: list of {id, name, group} from sheet_writer.get_sku_config()
    """
    if not skus:
        log.warning("No SKUs provided — nothing to post")
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2,  # retina for crisp screenshots
        )
        # Inject sheet ID into localStorage so dashboard loads live data
        if SHEET_ID:
            context.add_init_script(
                f"localStorage.setItem('sheetId', '{SHEET_ID}');"
            )
        page = context.new_page()
        # Load dashboard once to prime localStorage
        page.goto(DASHBOARD_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)
        for sku in skus:
            sku_id    = sku["id"]
            sku_name  = sku["name"]
            group     = sku.get("group", "pass")
            img_path  = f"/tmp/{sku_id}.png"
            try:
                screenshot_sku(page, sku_id, sku_name, img_path)
                webhook = SLACK_CHANNELS.get(group, "")
                channel = SLACK_CHANNEL_IDS.get(group, "general")
                post_to_slack(webhook, channel, sku_name, sku_id, group, img_path)
            except Exception as e:
                log.error("Failed for SKU %s: %s", sku_id, e)
        browser.close()
    log.info("All SKUs processed")
if __name__ == "__main__":
    from sheet_writer import get_sku_config
    with open(os.environ.get("GOOGLE_CREDS_PATH", "credentials.json")) as f:
        creds = json.load(f)
    skus = get_sku_config(creds, os.environ["SHEET_ID"])
    run(skus)

# Lucky Egg SKU Dashboard — Setup Guide
Follow these steps once to get the full pipeline running.
After setup, everything runs automatically at 9:30am UK time every day.
---
## Step 1 — Set up Amazon Scheduled Report
1. Log into [Amazon Seller Central](https://sellercentral.amazon.co.uk)
2. Go to **Reports → Business Reports**
3. Click **Request Report** or find the **Scheduled Reports** section
4. Choose **Detail Page Sales and Traffic By Child Item** (gives you SKU + units)
5. Set schedule to **Daily**
6. Set delivery email to **hey@luckyegg.co**
7. Repeat for each marketplace (UK, US, CA) — each sends a separate email
---
## Step 2 — Set up TikTok Shop Scheduled Report
1. Log into [TikTok Shop Seller Center](https://seller.tiktokshop.com)
2. Go to **Data → Order Report** (or **Reports → Sales Report**)
3. Look for **Scheduled Reports** or **Email Reports**
4. Set to **Daily**, delivery to **hey@luckyegg.co**
5. Make sure the export includes: Order Created Time, Seller SKU, Quantity, Warehouse Country
> Note: TikTok Shop Seller Center UI changes frequently.
> If you can't find scheduled reports, export manually each morning and
> forward the email with attachment to hey@luckyegg.co — the parser will pick it up.
---
## Step 3 — Create a Google Cloud Service Account
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable these APIs:
   - **Gmail API**
   - **Google Sheets API**
4. Go to **IAM & Admin → Service Accounts**
5. Click **Create Service Account** — name it `lucky-egg-dashboard`
6. Click the service account → **Keys → Add Key → JSON**
7. Download the JSON file — you'll need it in Step 5
### Enable Domain Delegation (so it can read hey@ Gmail)
1. In the service account, click **Edit** → enable **Domain-wide Delegation**
2. Note the **Client ID**
3. Go to [admin.google.com](https://admin.google.com) (Google Workspace admin)
4. Go to **Security → API Controls → Domain-wide Delegation**
5. Click **Add new** and enter:
   - Client ID: (from above)
   - Scopes: `https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/spreadsheets`
---
## Step 4 — Create the Google Sheet
1. Go to [sheets.google.com](https://sheets.google.com) and create a new sheet
2. Name it **Lucky Egg SKU Data** (or anything you like)
3. Create two tabs:
### Tab 1: `Config`
| SKU_ID | Name | Group |
|--------|------|-------|
| LE-001 | Original Lucky Egg | hero |
| LE-NL-01 | Sunrise Edition | launch |
| LE-P-01 | Classic White | pass |
- **SKU_ID**: must exactly match the SKU in your Amazon/TikTok exports
- **Group**: must be `hero`, `launch`, or `pass`
### Tab 2: `Sales`
Leave this empty — the script fills it automatically.
Just make sure the tab is named exactly `Sales`.
4. Share the sheet with your service account email
   (looks like `lucky-egg-dashboard@your-project.iam.gserviceaccount.com`)
   — give it **Editor** access
5. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/`**THIS_PART**`/edit`
---
## Step 5 — Add Secrets to GitHub
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**
Add these 3 secrets:
| Secret name | Value |
|-------------|-------|
| `GOOGLE_CREDS_JSON` | Paste the entire contents of the JSON file from Step 3 |
| `SHEET_ID` | The Sheet ID from Step 4 |
| `SLACK_BOT_TOKEN` | Your Slack bot token (see Step 6) |
---
## Step 6 — Create a Slack Bot
1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App → From Scratch**
3. Name it `Lucky Egg Dashboard`, pick your workspace
4. Go to **OAuth & Permissions**
5. Under **Scopes → Bot Token Scopes**, add:
   - `files:write`
   - `chat:write`
   - `channels:join`
6. Click **Install to Workspace** → copy the **Bot User OAuth Token** (starts with `xoxb-`)
7. Add the bot to each channel by going to the channel in Slack → **Members → Add apps → Lucky Egg Dashboard**:
   - `#hero-product-updates`
   - `#product-launch`
   - `#passed-products`
---
## Step 7 — Connect the Dashboard
1. Go to [lucky-egg-sku-dashboard.vercel.app](https://lucky-egg-sku-dashboard.vercel.app)
2. Click **Configure** in the top right
3. Paste your Google Sheet URL
4. Click **Connect** — your real SKUs will load immediately
---
## Step 8 — Test the pipeline
1. Go to your GitHub repo → **Actions** tab
2. Click **Daily SKU Dashboard Update** → **Run workflow**
3. Watch the logs — each step should show green ✅
4. Check your Slack channels for the screenshots
---
## Troubleshooting
**No Amazon records fetched** — Check the scheduled report is set up and has sent at least one email to hey@luckyegg.co. You can forward a test report email manually.
**No TikTok records fetched** — TikTok may not support scheduled email reports for your account yet. Forward the CSV export manually to hey@luckyegg.co as a workaround.
**Gmail permission error** — Double-check domain-wide delegation is set up in Google Workspace admin and the scopes match exactly.
**Slack post not appearing** — Make sure the bot has been added to each channel and the `SLACK_BOT_TOKEN` secret is correct.

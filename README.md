# Radio Outreach

A local web app for music artists to send personalized outreach emails to college radio stations. Import a station directory (PDF or XLSX), write a reusable email template, send to stations one at a time or all at once, and track everything in a color-coded Excel checklist.

---

## Requirements

- macOS (or any system with Python 3.9+)
- A Gmail account
- A Google Cloud project (free, takes ~5 minutes to set up)
- The station directory file (PDF or XLSX)

---

## Installation

### 1. Open Terminal and navigate to the project folder

```bash
cd ~/Documents/software-projects/radio-outreach
```

### 2. Create a Python virtual environment

This keeps the app's dependencies isolated from the rest of your system.

```bash
python3 -m venv venv
```

### 3. Activate the virtual environment

```bash
source venv/bin/activate
```

You'll need to run this every time you open a new terminal session before starting the app.

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Google Gmail Setup (one time)

The app sends emails through your Gmail account using Google's official API. This requires a one-time setup in Google Cloud Console.

### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click **Select a project** → **New Project**
3. Give it any name (e.g. "Radio Outreach") and click **Create**

### Step 2 — Enable the Gmail API

1. In the left sidebar go to **APIs & Services → Library**
2. Search for **Gmail API** and click it
3. Click **Enable**

### Step 3 — Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth 2.0 Client ID**
3. If prompted to configure the consent screen first:
   - Choose **External**, click **Create**
   - Fill in an app name (anything), your email, and click **Save and Continue** through all steps
   - On the last step, click **Back to Dashboard**
4. Back on Credentials, click **+ Create Credentials → OAuth 2.0 Client ID** again
5. Set Application type to **Web application**
6. Under **Authorized redirect URIs**, click **Add URI** and enter:
   ```
   http://localhost:5050/oauth2callback
   ```
7. Click **Create**

### Step 4 — Download the credentials file

1. After creating, click the **Download JSON** button (or the download icon next to your credential)
2. Rename the file to exactly `google_credentials.json`
3. Move it into the `radio-outreach/` project folder

### Step 5 — Connect your account in the app

1. Start the app (see below) and open [http://localhost:5050/settings](http://localhost:5050/settings)
2. Click **Connect Google Account**
3. A browser tab will open — sign in to Gmail and click **Allow**
4. You'll be redirected back to the app with a green "Connected" status

You only need to do this once. The app saves a token that refreshes automatically.

---

## Running the App

```bash
# From the radio-outreach folder, with venv active:
source venv/bin/activate
python app.py
```

Then open **[http://localhost:5050](http://localhost:5050)** in your browser.

To stop the app, press `Ctrl+C` in the terminal.

---

## How to Use

### Step 1 — Map your columns

Before importing, go to **Settings → PDF Column Mapping** and click **Load columns from PDF**.

The app reads your source file and shows all the column headers it found. It will try to auto-fill the mapping — check that the right columns are matched to the right fields (Station Name, Contact Name, Email, School, etc.) and adjust if needed. Click **Save Settings**.

> You only need to do this once per source file format. If you use the same file structure every time, it stays configured.

### Step 2 — Import your station list

On the **Checklist** page, click **⬇ Import File** and select your PDF or XLSX file.

All stations will be loaded into the checklist and saved to `outreach.xlsx` with a `pending` status. Re-importing the same file won't create duplicates — the app checks for existing entries by station name and email.

### Step 3 — Write your email template

Go to **Settings → Email Template**.

Write your subject and body using the rich text editor. You can add **bold**, *italic*, and **hyperlinks** using the toolbar. Use these merge tags to personalize each email automatically:

| Tag | What it inserts |
|---|---|
| `{{first_name}}` | First name of the contact (derived from full name) |
| `{{last_name}}` | Last name of the contact |
| `{{name}}` | Full contact name |
| `{{station}}` | Station name |
| `{{school}}` | School / university |

Click the tag buttons in the toolbar to insert them at your cursor position.

The **Preview** panel on the right updates live with sample data as you type, so you can see exactly how the email will look before sending.

Click **Save Template** when done.

### Step 4 — Test your email

Click **✉ Send Test Email** in Settings. You can leave the recipient field blank to send to your own Gmail (check the **Sent** folder), or type any other email address to see how it lands in a real inbox.

### Step 5 — Send to stations

From the **Checklist** page you have three options:

- **Send one** — click the **✉** button on any row to send to that station immediately
- **Preview first** — click the station name to open a detail page showing exactly what email will go out, then send from there
- **Send all** — click **✉ Send All Pending** to send to every station in the list that has a `pending` status and a valid email address

After each send, the row turns **green** and logs the timestamp automatically — in the app and in `outreach.xlsx`.

### Managing the checklist

| Action | How |
|---|---|
| Skip a station | Click **✕** on its row |
| Restore a skipped station | Click **↩** on its row |
| Edit station details | Click the station name → edit the fields → Save Changes |
| Remove a station entirely | Open the station detail page → Delete |
| Filter by status | Use the **All / Pending / Sent / Skipped** tabs at the top |
| Search | Type in the search bar to filter by name, email, school, etc. |

---

## The Excel Checklist (`outreach.xlsx`)

The spreadsheet is a live mirror of everything in the app. Open it any time in Excel or Numbers — no syncing needed.

- **White rows** = pending
- **Green rows** = email sent
- **Yellow rows** = skipped

Download the latest version at any time using the **Download .xlsx** link in the top navigation.

---

## File Structure

```
radio-outreach/
├── College Radio Directory Bundle.pdf   ← source PDF
├── outreach.xlsx                         ← live checklist (created on first import)
├── settings.json                         ← saved settings (template, column map)
├── google_credentials.json               ← OAuth credentials (you add this)
├── token.json                            ← OAuth token (auto-created after connecting)
├── app.py                                ← Flask web app + all routes
├── parse_pdf.py                          ← PDF extraction logic
├── spreadsheet.py                        ← Excel read/write layer
├── email_sender.py                       ← Gmail API sender
├── models_config.py                      ← settings persistence
├── config.py                             ← file paths
├── requirements.txt                      ← Python dependencies
├── templates/                            ← HTML pages
│   ├── base.html
│   ├── index.html                        ← checklist
│   ├── station.html                      ← station detail + email preview
│   ├── settings.html                     ← settings + template editor
│   └── debug_send.html                   ← test email results
└── static/
    └── style.css
```

---

## Troubleshooting

**"No records found in the PDF"**
Go to Settings and configure the Column Mapping before importing. Click "Load columns from PDF" to see what headers are in your file.

**"Not authorized" when sending**
Go to Settings and click "Connect Google Account". If you see a scope error, click "Disconnect" first, then reconnect.

**Sent email not in inbox**
When sending to yourself, Gmail puts it in your **Sent** folder rather than your inbox. Send to a different address to verify delivery.

**App won't start / port already in use**
Another instance is already running. Run `kill $(lsof -ti :5050)` in Terminal, then restart.

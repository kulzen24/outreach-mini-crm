"""
app.py
Flask web application.

Routes:
  GET  /                    → Checklist
  POST /import              → Parse PDF → populate outreach.xlsx
  GET  /station/<id>        → Station detail + live email preview
  POST /station/<id>/edit   → Save station edits
  POST /send/<id>           → Send email for one station, mark sent
  POST /bulk-send           → Send to all pending stations
  POST /status/<id>         → Update status (skip / reset)
  POST /delete/<id>         → Remove a station row
  GET  /settings            → Settings page
  POST /settings            → Save settings
  GET  /columns             → AJAX — PDF column headers + sample rows
  GET  /authorize           → Start Google OAuth2 flow
  GET  /oauth2callback      → Google OAuth2 redirect target
  GET  /disconnect          → Delete stored token
  GET  /download            → Stream outreach.xlsx
"""

import os
import time
import tempfile

# Allow OAuth over plain HTTP for localhost
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
# Allow Google to return broader scopes than exactly requested (it sometimes includes legacy scopes)
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, send_file, session,
)
import openpyxl
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

from spreadsheet import (
    init_spreadsheet, upsert_stations, get_stations,
    get_station, update_station, mark_sent, mark_skipped,
    mark_pending, delete_station, get_stats,
)
from parse_pdf import extract_stations, get_pdf_columns
from email_sender import send_email, preview_email, is_authorized, credentials_file_exists, SCOPES, TOKEN_FILE, CREDENTIALS_FILE
from models_config import get_all_settings, save_all_settings, get_column_map
from config import PDF_PATH, XLSX_PATH

app = Flask(__name__)
app.secret_key = os.urandom(24)

OAUTH_REDIRECT = "http://localhost:5050/oauth2callback"

init_spreadsheet()


# ---------------------------------------------------------------------------
# Checklist
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    status = request.args.get("status", "all")
    search = request.args.get("q", "").strip()
    stations = get_stations(status=status, search=search or None)
    stats = get_stats()
    authorized = is_authorized()
    return render_template(
        "index.html",
        stations=stations,
        stats=stats,
        current_status=status,
        search=search,
        authorized=authorized,
    )


# ---------------------------------------------------------------------------
# Import (PDF or XLSX)
# ---------------------------------------------------------------------------

def _extract_from_xlsx(filepath, col_map):
    """Read an uploaded XLSX and return a list of station dicts."""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # First non-empty row = headers
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    records = []
    for row in rows[1:]:
        if not any(cell for cell in row if cell is not None):
            continue
        d = {headers[i]: (str(v).strip() if v is not None else "")
             for i, v in enumerate(row) if i < len(headers)}
        records.append(d)

    # Apply column mapping (rename PDF/XLSX headers → app field names)
    if col_map:
        rename = {pdf_col: app_field for app_field, pdf_col in col_map.items() if pdf_col}
        records = [{rename.get(k, k): v for k, v in r.items()} for r in records]

    required = ["station_name", "contact_name", "first_name", "last_name",
                "email", "school", "city", "state", "genre", "notes"]
    for r in records:
        for key in required:
            r.setdefault(key, "")
        # If separate first/last columns were mapped, build contact_name from them
        if (r.get("first_name") or r.get("last_name")) and not r.get("contact_name"):
            r["contact_name"] = " ".join(
                p for p in [r.get("first_name", ""), r.get("last_name", "")] if p
            ).strip()

    wb.close()
    return records


@app.route("/import", methods=["POST"])
def import_pdf():
    col_map = get_column_map()
    effective_map = {k: v for k, v in col_map.items() if v}

    uploaded = request.files.get("import_file")

    # ── Uploaded file ──────────────────────────────────────────
    if uploaded and uploaded.filename:
        filename = uploaded.filename.lower()
        suffix = ".xlsx" if filename.endswith(".xlsx") else ".pdf"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            uploaded.save(tmp.name)
            tmp_path = tmp.name

        try:
            if suffix == ".xlsx":
                records = _extract_from_xlsx(tmp_path, effective_map or None)
            else:
                records = extract_stations(tmp_path, effective_map or None)
        except Exception as exc:
            os.unlink(tmp_path)
            flash(f"Failed to parse file: {exc}", "error")
            return redirect(url_for("index"))
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ── Fall back to the bundled PDF in the project folder ─────
    else:
        try:
            records = extract_stations(PDF_PATH, effective_map or None)
        except FileNotFoundError:
            flash("No file uploaded and the bundled PDF wasn't found either.", "error")
            return redirect(url_for("index"))
        except Exception as exc:
            flash(f"Failed to parse PDF: {exc}", "error")
            return redirect(url_for("index"))

    if not records:
        flash("No records found. Check the Column Mapping in Settings and try again.", "warning")
        return redirect(url_for("settings"))

    inserted = upsert_stations(records)
    flash(f"Import complete — {inserted} new stations added ({len(records) - inserted} already existed).", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Station detail & edit
# ---------------------------------------------------------------------------

@app.route("/station/<row_id>")
def station_detail(row_id):
    station = get_station(row_id)
    if not station:
        flash("Station not found.", "error")
        return redirect(url_for("index"))
    subject, body = preview_email(station)
    authorized = is_authorized()
    return render_template("station.html", station=station, subject=subject, body=body, authorized=authorized)


@app.route("/station/<row_id>/edit", methods=["POST"])
def station_edit(row_id):
    fields = {
        "station_name": request.form.get("station_name", ""),
        "contact_name": request.form.get("contact_name", ""),
        "email":        request.form.get("email", ""),
        "school":       request.form.get("school", ""),
        "city":         request.form.get("city", ""),
        "state":        request.form.get("state", ""),
        "genre":        request.form.get("genre", ""),
        "notes":        request.form.get("notes", ""),
    }
    update_station(row_id, fields)
    flash("Station updated.", "success")
    return redirect(url_for("station_detail", row_id=row_id))


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

@app.route("/send/<row_id>", methods=["POST"])
def send_one(row_id):
    station = get_station(row_id)
    if not station:
        flash("Station not found.", "error")
        return redirect(url_for("index"))

    success, error = send_email(station)
    if success:
        mark_sent(row_id)
        flash(f"Email sent to {station['email']}.", "success")
    else:
        flash(f"Failed to send: {error}", "error")

    return redirect(request.form.get("next") or url_for("index"))


@app.route("/bulk-send", methods=["POST"])
def bulk_send():
    pending = [s for s in get_stations(status="pending") if s.get("email")]
    if not pending:
        flash("No pending stations with email addresses found.", "warning")
        return redirect(url_for("index"))

    sent_count = 0
    fail_count = 0
    for station in pending:
        success, _ = send_email(station)
        if success:
            mark_sent(station["row_id"])
            sent_count += 1
        else:
            fail_count += 1
        time.sleep(0.4)

    flash(
        f"Bulk send complete — {sent_count} sent, {fail_count} failed.",
        "success" if fail_count == 0 else "warning",
    )
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.route("/status/<row_id>", methods=["POST"])
def set_status(row_id):
    new_status = request.form.get("status")
    if new_status == "skipped":
        mark_skipped(row_id)
    elif new_status == "pending":
        mark_pending(row_id)
    flash(f"Status updated to '{new_status}'.", "success")
    return redirect(request.form.get("next") or url_for("index"))


@app.route("/delete/<row_id>", methods=["POST"])
def delete_one(row_id):
    delete_station(row_id)
    flash("Station removed.", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        save_all_settings(request.form)
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    all_settings = get_all_settings()
    authorized = is_authorized()
    creds_exist = credentials_file_exists()
    return render_template("settings.html", s=all_settings, authorized=authorized, creds_exist=creds_exist)


@app.route("/columns")
def columns():
    try:
        cols, sample = get_pdf_columns(PDF_PATH)
        return jsonify({"columns": cols, "sample": sample})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# OAuth2
# ---------------------------------------------------------------------------

@app.route("/authorize")
def authorize():
    if not credentials_file_exists():
        flash("google_credentials.json not found. See the setup instructions in Settings.", "error")
        return redirect(url_for("settings"))

    flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, redirect_uri=OAUTH_REDIRECT)
    auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    state = session.get("oauth_state")
    if not state:
        flash("OAuth state missing. Please try again.", "error")
        return redirect(url_for("settings"))

    try:
        flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES, state=state, redirect_uri=OAUTH_REDIRECT)
        flow.fetch_token(authorization_response=request.url)
        with open(TOKEN_FILE, "w") as f:
            f.write(flow.credentials.to_json())
        flash("Google account connected! You're ready to send emails.", "success")
    except Exception as exc:
        flash(f"Authorization failed: {exc}", "error")

    return redirect(url_for("settings"))


@app.route("/send-test", methods=["POST"])
def send_test():
    from email_sender import get_gmail_service
    import traceback

    steps = []   # list of (label, status, detail)

    # Step 1 — auth
    service = get_gmail_service()
    if service is None:
        steps.append(("Gmail service", "fail", "No valid token. Disconnect and reconnect your Google account."))
        return render_template("debug_send.html", steps=steps, sender_email=None)
    steps.append(("Gmail service", "ok", "Token loaded and valid."))

    # Step 2 — profile
    try:
        profile = service.users().getProfile(userId="me").execute()
        sender_email = profile["emailAddress"]
        steps.append(("Get profile", "ok", f"Sending as: {sender_email}"))
    except Exception as exc:
        steps.append(("Get profile", "fail", traceback.format_exc()))
        return render_template("debug_send.html", steps=steps, sender_email=None)

    # Step 3 — template
    from models_config import get_setting
    import re as _re
    subject_tpl = get_setting("email_subject")
    body_tpl    = get_setting("email_body")
    plain_check = _re.sub(r"<[^>]+>", "", body_tpl or "").strip()
    if not subject_tpl or not plain_check:
        steps.append(("Template check", "fail",
                      "Subject or body is empty — go to Settings, fill in the template, and click Save Template."))
        return render_template("debug_send.html", steps=steps, sender_email=sender_email)
    steps.append(("Template check", "ok",
                  f"Subject: {subject_tpl[:80]}\nBody preview: {plain_check[:120]}…"))

    # Step 4 — send
    custom_recipient = request.form.get("test_recipient", "").strip()
    to_email = custom_recipient if custom_recipient else sender_email
    sample_station = {
        "contact_name": "Alex Rivera",
        "station_name": "WKSU",
        "school":       "Kent State University",
        "email":        to_email,
    }
    success, error = send_email(sample_station)
    if success:
        steps.append(("Send email", "ok",
                      f"Gmail accepted the message to {sender_email}. "
                      "Check your inbox, Sent folder, and spam."))
    else:
        steps.append(("Send email", "fail", error))

    return render_template("debug_send.html", steps=steps, sender_email=sender_email)


@app.route("/disconnect", methods=["POST"])
def disconnect():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
    flash("Google account disconnected.", "success")
    return redirect(url_for("settings"))


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

@app.route("/download")
def download():
    if not os.path.exists(XLSX_PATH):
        flash("No spreadsheet yet. Import the PDF first.", "warning")
        return redirect(url_for("index"))
    return send_file(XLSX_PATH, as_attachment=True, download_name="outreach.xlsx")


if __name__ == "__main__":
    app.run(debug=True, port=5050)

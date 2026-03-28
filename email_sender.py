"""
email_sender.py
Sends outreach emails via the Gmail API using OAuth 2.0.
No app password needed — just authorize once in the browser.

Supported merge tags (in subject or body):
  {{name}}     → contact_name  (used in salutation)
  {{station}}  → station_name  (used in body)
  {{school}}   → school        (used in body)
"""

import os
import re
import base64
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from models_config import get_setting

BASE_DIR       = os.path.dirname(__file__)
TOKEN_FILE     = os.path.join(BASE_DIR, "token.json")
CREDENTIALS_FILE = os.path.join(BASE_DIR, "google_credentials.json")
# Full Gmail scope — covers send, read profile, and compose.
# If you previously authorized with a narrower scope, disconnect and reconnect in Settings.
SCOPES = ["https://mail.google.com/"]


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_gmail_service():
    """
    Load stored OAuth token and return an authorized Gmail API service.
    Returns None if the user hasn't authorized yet.
    Auto-refreshes the token if it's expired.
    """
    if not os.path.exists(TOKEN_FILE):
        return None

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
            except Exception:
                return None
        else:
            return None

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def is_authorized():
    """True if we have a valid (or refreshable) token on disk."""
    return get_gmail_service() is not None


def credentials_file_exists():
    return os.path.exists(CREDENTIALS_FILE)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _split_name(full_name):
    """Split 'First Last' → ('First', 'Last'). Handles single-word names."""
    parts = (full_name or "").strip().split(" ", 1)
    first = parts[0] if parts else ""
    last  = parts[1] if len(parts) > 1 else ""
    return first, last


def _render(template, station):
    """
    Replace merge tags with station data.
    Supported tags:
      {{name}}        full contact name
      {{first_name}}  first word of contact name (or dedicated first_name field)
      {{last_name}}   remainder of contact name (or dedicated last_name field)
      {{station}}     station name
      {{school}}      school name

    If a value is empty, the tag plus any immediately preceding space is
    removed so "Hi {{first_name}}," becomes "Hi," cleanly.
    """
    contact_name = station.get("contact_name", "")
    derived_first, derived_last = _split_name(contact_name)

    tag_map = {
        "name":       contact_name,
        "first_name": station.get("first_name", "") or derived_first,
        "last_name":  station.get("last_name",  "") or derived_last,
        "station":    station.get("station_name", ""),
        "school":     station.get("school", ""),
    }
    def replacer(match):
        key = match.group(1).strip()
        return tag_map.get(key, match.group(0))

    # First pass: replace tags with their values
    result = re.sub(r"\{\{(\w+)\}\}", replacer, template)
    # Second pass: collapse any space left behind by an empty substitution
    # e.g. "Hi ," → "Hi,"  or  "at ." → "at."
    result = re.sub(r" {2,}", " ", result)          # collapse double spaces
    result = re.sub(r" ([,\.!?])", r"\1", result)   # remove space before punctuation
    return result


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------

def _html_to_plain(html_body):
    """Strip HTML tags to produce a plain-text fallback."""
    import re as _re
    # Block-level tags → newlines
    text = _re.sub(r"<br\s*/?>", "\n", html_body, flags=_re.IGNORECASE)
    text = _re.sub(r"</p>|</div>|</li>", "\n", text, flags=_re.IGNORECASE)
    # Strip all remaining tags
    text = _re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    # Collapse excess blank lines
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _normalize_html(html_body):
    """
    Normalize Quill's <p> tags for email clients:
    - Regular paragraphs: no extra margin, normal line height
    - Empty paragraphs (<p><br></p>): a half-line spacer so intentional
      blank lines still look like a blank line without being too tall
    """
    # Empty paragraph → slim spacer (~half a line)
    html_body = re.sub(
        r"<p><br></p>",
        '<p style="margin:0;line-height:0.8;font-size:8px;">&nbsp;</p>',
        html_body,
        flags=re.IGNORECASE,
    )
    # All other <p> tags → zero margin, normal line height
    html_body = re.sub(
        r"<p(?=[>\s])",
        '<p style="margin:0;line-height:1.6;"',
        html_body,
        flags=re.IGNORECASE,
    )
    return html_body


def _extract_inline_images(html):
    """
    Find base64 data-URI images in HTML, replace each with a cid: reference,
    and return (modified_html, [(cid, subtype, raw_bytes), ...]).
    """
    images = []

    def replacer(match):
        data_uri  = match.group(1)
        header, data = data_uri.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]   # e.g. image/png
        subtype   = mime_type.split("/")[1]               # e.g. png
        raw       = base64.b64decode(data)
        cid       = str(uuid.uuid4())
        images.append((cid, subtype, raw))
        return f'src="cid:{cid}"'

    modified = re.sub(r'src="(data:image/[^;]+;base64,[^"]+)"', replacer, html)
    return modified, images


def _build_raw_message(sender, to, subject, html_body):
    plain  = _html_to_plain(html_body)
    styled = _normalize_html(html_body)
    full_html = (
        "<html><body style=\"font-family:Arial,sans-serif;font-size:14px;color:#111;\">"
        f"{styled}</body></html>"
    )

    # Pull out any embedded images and replace with cid: references
    full_html, images = _extract_inline_images(full_html)

    # Build the alternative part (plain + html)
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain, "plain", "utf-8"))
    alt.attach(MIMEText(full_html, "html", "utf-8"))

    if images:
        # Wrap in multipart/related so cid: images are resolved correctly
        msg = MIMEMultipart("related")
        msg.attach(alt)
        for i, (cid, subtype, raw) in enumerate(images, start=1):
            filename = f"image-{i}.{subtype}"
            img = MIMEImage(raw, _subtype=subtype)
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=filename)
            msg.attach(img)
    else:
        msg = alt

    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = to

    raw = base64.urlsafe_b64encode(msg.as_string().encode("utf-8")).decode("utf-8")
    return {"raw": raw}


def send_email(station, subject_tpl=None, body_tpl=None):
    """
    Send an outreach email for one station dict.
    Optionally pass subject_tpl / body_tpl to override the active settings template.
    Returns (success: bool, error_message: str | None).
    """
    service = get_gmail_service()
    if service is None:
        return False, "Not authorized. Go to Settings and connect your Google account."

    to_address = station.get("email", "").strip()
    if not to_address:
        return False, f"No email address for {station.get('station_name', 'this station')}."

    subject_tpl = subject_tpl or get_setting("email_subject")
    body_tpl    = body_tpl    or get_setting("email_body")
    # Strip HTML tags to check if the body has actual visible content
    plain_check = re.sub(r"<[^>]+>", "", body_tpl or "").strip()
    if not subject_tpl or not plain_check:
        return False, "Email subject or body is empty. Go to Settings, write your template, and click Save Template."

    subject = _render(subject_tpl, station)
    body    = _render(body_tpl, station)

    try:
        profile  = service.users().getProfile(userId="me").execute()
        sender   = profile["emailAddress"]
        message  = _build_raw_message(sender, to_address, subject, body)
        result   = service.users().messages().send(userId="me", body=message).execute()
        print(f"[email_sender] Sent OK — Gmail message id: {result.get('id')}  to: {to_address}")
        return True, None
    except HttpError as exc:
        print(f"[email_sender] HttpError: {exc}")
        return False, f"Gmail API error: {exc}"
    except Exception as exc:
        import traceback
        print(f"[email_sender] Exception:\n{traceback.format_exc()}")
        return False, str(exc)


def preview_email(station, subject_tpl=None, body_tpl=None):
    """Return (subject, body) with merge tags filled in. No email is sent.
    Optionally pass subject_tpl / body_tpl to preview a specific template."""
    subject_tpl = subject_tpl or get_setting("email_subject")
    body_tpl    = body_tpl    or get_setting("email_body")
    return _render(subject_tpl or "", station), _render(body_tpl or "", station)

"""
models_config.py
Persists app settings (email credentials, templates, column map) in
settings.json so the user never has to touch code or env files directly.

Named templates are stored separately in templates.json.
"""

import json
import os
import uuid
from datetime import datetime

SETTINGS_PATH   = os.path.join(os.path.dirname(__file__), "settings.json")
TEMPLATES_PATH  = os.path.join(os.path.dirname(__file__), "templates.json")

DEFAULTS = {
    "email_subject": "Music Submission — {{station}}",
    "email_body": (
        "Hi {{name}},\n\n"
        "My name is [YOUR NAME] and I'm reaching out on behalf of [ARTIST NAME].\n\n"
        "We'd love to get our music added to {{station}}'s rotation at {{school}}. "
        "I've attached our latest single/EP for your consideration.\n\n"
        "Please let me know if you have any questions or need additional materials.\n\n"
        "Thanks so much for your time!\n\n"
        "[YOUR NAME]\n"
        "[YOUR EMAIL / PHONE]"
    ),
    # column map: app field → PDF column header
    # Defaults match the College Radio Directory Bundle PDF.
    "col_station_name": "Station",
    "col_contact_name": "DJ / Music Dir.",
    "col_first_name":   "",          # optional — first name column
    "col_last_name":    "",          # optional — last name column
    "col_email":        "Email",
    "col_school":       "School",
    "col_city":         "State/City",  # auto-split into state + city on import
    "col_state":        "",            # populated from State/City automatically
    "col_genre":        "",            # no genre column in this PDF
    "col_notes":        "Notes",
}


def _load():
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH) as f:
            return json.load(f)
    return {}


def _save(data):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_setting(key):
    data = _load()
    return data.get(key, DEFAULTS.get(key, ""))


def set_setting(key, value):
    data = _load()
    data[key] = value
    _save(data)


def get_all_settings():
    data = _load()
    return {k: data.get(k, v) for k, v in DEFAULTS.items()}


def save_all_settings(form_data):
    """Accepts a dict (e.g. from request.form) and saves recognised keys."""
    data = _load()
    for key in DEFAULTS:
        if key in form_data:
            data[key] = form_data[key]
    _save(data)


# ---------------------------------------------------------------------------
# Named template library
# ---------------------------------------------------------------------------

def _load_templates():
    if os.path.exists(TEMPLATES_PATH):
        with open(TEMPLATES_PATH) as f:
            return json.load(f)
    return []


def _save_templates(templates):
    with open(TEMPLATES_PATH, "w") as f:
        json.dump(templates, f, indent=2)


def get_templates():
    """Return all saved templates, newest first."""
    return sorted(_load_templates(), key=lambda t: t.get("created_at", ""), reverse=True)


def save_template(name, subject, body):
    """Save a new named template. Returns the new template dict."""
    templates = _load_templates()
    tpl = {
        "id":         str(uuid.uuid4()),
        "name":       name.strip(),
        "subject":    subject,
        "body":       body,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    templates.append(tpl)
    _save_templates(templates)
    return tpl


def get_template(template_id):
    """Return a single template by id, or None."""
    return next((t for t in _load_templates() if t["id"] == template_id), None)


def delete_template(template_id):
    templates = [t for t in _load_templates() if t["id"] != template_id]
    _save_templates(templates)


def get_column_map():
    """Return the current PDF→app column mapping as a dict.

    Falls back to DEFAULTS when a key is absent *or* saved as an empty string,
    so the correct defaults work even if settings.json pre-dates them.
    """
    data = _load()

    def _get(col_key):
        saved = data.get(col_key)
        if saved is not None and str(saved).strip():
            return str(saved).strip()
        return DEFAULTS.get(col_key, "")

    return {
        "station_name": _get("col_station_name"),
        "contact_name": _get("col_contact_name"),
        "first_name":   _get("col_first_name"),
        "last_name":    _get("col_last_name"),
        "email":        _get("col_email"),
        "school":       _get("col_school"),
        "city":         _get("col_city"),
        "state":        _get("col_state"),
        "genre":        _get("col_genre"),
        "notes":        _get("col_notes"),
    }

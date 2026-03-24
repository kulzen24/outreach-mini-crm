"""
models_config.py
Persists app settings (email credentials, templates, column map) in
settings.json so the user never has to touch code or env files directly.
"""

import json
import os

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

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
    "col_station_name": "",
    "col_contact_name": "",   # full name (used if first/last not mapped separately)
    "col_first_name":   "",   # optional — first name column
    "col_last_name":    "",   # optional — last name column
    "col_email":        "",
    "col_school":       "",
    "col_city":         "",
    "col_state":        "",
    "col_genre":        "",
    "col_notes":        "",
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


def get_column_map():
    """Return the current PDF→app column mapping as a dict."""
    data = _load()
    return {
        "station_name": data.get("col_station_name", ""),
        "contact_name": data.get("col_contact_name", ""),
        "first_name":   data.get("col_first_name", ""),
        "last_name":    data.get("col_last_name", ""),
        "email":        data.get("col_email", ""),
        "school":       data.get("col_school", ""),
        "city":         data.get("col_city", ""),
        "state":        data.get("col_state", ""),
        "genre":        data.get("col_genre", ""),
        "notes":        data.get("col_notes", ""),
    }

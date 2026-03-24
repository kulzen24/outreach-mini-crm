"""
config.py
Static paths and the default PDF column → app field mapping.

COLUMN_MAP maps your standardized field names (left) to the exact column
headers found in the PDF (right).  Run the app once without a map —
the /settings page will show you the real headers so you can fill this in.
"""

import os

BASE_DIR = os.path.dirname(__file__)
PDF_PATH  = os.path.join(BASE_DIR, "College Radio Directory Bundle.pdf")
XLSX_PATH = os.path.join(BASE_DIR, "outreach.xlsx")

# Leave values as "" if you haven't mapped the PDF yet.
# After importing, visit /settings → Column Mapping to configure.
COLUMN_MAP = {
    "station_name":  "",   # e.g. "Station"
    "contact_name":  "",   # e.g. "Music Director"
    "email":         "",   # e.g. "Email"
    "school":        "",   # e.g. "University / College"
    "city":          "",   # e.g. "City"
    "state":         "",   # e.g. "State"
    "genre":         "",   # e.g. "Format"
    "notes":         "",   # e.g. "Notes" (optional)
}

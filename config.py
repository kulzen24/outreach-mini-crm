"""
config.py
Static paths, page range, and the default PDF column → app field mapping.

COLUMN_MAP maps your standardized field names (left) to the exact column
headers found in the PDF (right).  These defaults match the College Radio
Directory Bundle PDF.  You can override them any time via Settings → Column
Mapping in the web UI.
"""

import os

BASE_DIR  = os.path.dirname(__file__)
PDF_PATH  = os.path.join(BASE_DIR, "College Radio Directory Bundle.pdf")
XLSX_PATH = os.path.join(BASE_DIR, "outreach.xlsx")

# Page range for table extraction (1-indexed, inclusive).
# The College Radio Directory Bundle has station tables on pages 11–37.
# Pages 1-10 are intro/TOC; pages 38+ are podcasts/other content.
PDF_START_PAGE = 11
PDF_END_PAGE   = 37

# Default column map: app field → exact PDF column header.
# These match the headers in the College Radio Directory Bundle PDF.
COLUMN_MAP = {
    "station_name":  "Station",
    "contact_name":  "DJ / Music Dir.",
    "first_name":    "",
    "last_name":     "",
    "email":         "Email",
    "school":        "School",
    "city":          "State/City",   # auto-split into state + city on import
    "state":         "",             # populated automatically from State/City
    "genre":         "",             # no genre column in this PDF
    "notes":         "Notes",
}

"""
parse_pdf.py
Extracts radio station records from the College Radio Directory PDF.

Tries table extraction first (pages PDF_START_PAGE–PDF_END_PAGE), then falls
back to key: value text block parsing over the same page range.
No pandas dependency — uses plain dicts and lists throughout.
"""

import pdfplumber
import re
from config import PDF_PATH, COLUMN_MAP, PDF_START_PAGE, PDF_END_PAGE


def _clean(val):
    if val is None:
        return ""
    return str(val).strip().replace("\n", " ")


# ---------------------------------------------------------------------------
# Header normalisation
# ---------------------------------------------------------------------------

# Canonical form for known aliases that appear across pages / sections.
_HEADER_ALIASES = {
    # Page 12 renders the first header with doubled characters
    "ssttaattee//cciittyy": "State/City",
    # Canadian section (pages 36-37) uses "City/Province"
    "city/province":         "State/City",
    # Canadian section uses "Shows" instead of "Show"
    "shows":                 "Show",
}


def _normalize_header(raw):
    """Return a canonical column name, fixing known rendering quirks."""
    key = _clean(raw).lower()
    return _HEADER_ALIASES.get(key, _clean(raw))


# Token set used to recognise repeated header rows inside table bodies.
_HEADER_TOKENS = frozenset({
    "state/city", "city/province", "school", "station", "email",
    "notes", "show", "shows", "website", "phone", "address",
    "dj / music dir.", "submitted", "name", "platform",
    # garbled variant
    "ssttaattee//cciittyy",
})


def _is_header_row(row):
    """Return True if this row looks like a repeated column-header row."""
    hits = sum(
        1 for cell in row
        if _clean(cell).lower() in _HEADER_TOKENS
    )
    return hits >= 3


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

def _extract_tables(pdf, start_page=0, end_page=None):
    """
    Scan pdf.pages[start_page:end_page] (0-indexed) for tables.

    Key improvements over the naive approach:
    - Skips tiny/spurious sub-tables (< 5 columns) that pdfplumber creates
      when a cell contains multiple line-broken values (e.g. multiple emails).
    - Detects and skips repeated header rows that appear at the top of each
      page's continuation table.
    - Normalises known header aliases so column mapping works regardless of
      which page variant is encountered first.

    Returns (headers, rows) or (None, []).
    """
    headers = None
    rows = []

    for page in pdf.pages[start_page:end_page]:
        for table in page.extract_tables():
            if not table:
                continue

            # Drop spurious sub-tables that only have 1-4 columns.
            # Real station tables have 9-11 columns.
            if len(table[0]) < 5:
                continue

            row0 = table[0]

            if headers is None:
                # First real table — its first row is the header.
                headers = [_normalize_header(_clean(h)) for h in row0]
                data_rows = table[1:]
            else:
                # Continuation table on a new page.
                if _is_header_row(row0):
                    # If this section has a different column structure (e.g. the
                    # Canadian pages have 9 cols vs the US pages' 11), adopt its
                    # own headers so columns don't shift onto the wrong fields.
                    if len(row0) != len(headers):
                        headers = [_normalize_header(_clean(h)) for h in row0]
                    data_rows = table[1:]
                else:
                    data_rows = table

            for row in data_rows:
                cleaned = [_clean(c) for c in row]
                if not any(cleaned):
                    continue
                # Skip stray header rows embedded in the body.
                if _is_header_row(row):
                    continue
                # Pad or trim to match the established header count.
                while len(cleaned) < len(headers):
                    cleaned.append("")
                rows.append(dict(zip(headers, cleaned[:len(headers)])))

    return (headers, rows) if (headers and rows) else (None, [])


# ---------------------------------------------------------------------------
# Text-block fallback
# ---------------------------------------------------------------------------

def _extract_text_blocks(pdf, start_page=0, end_page=None):
    """
    Fallback for PDFs without tables.
    Parses blocks of "Key: Value" lines separated by blank lines.
    Returns (columns, rows).
    """
    records = []
    current = {}

    for page in pdf.pages[start_page:end_page]:
        text = page.extract_text() or ""
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                if current:
                    records.append(current)
                    current = {}
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                current[key.strip()] = val.strip()
            elif not current:
                current["_raw_name"] = line

    if current:
        records.append(current)

    if not records:
        return None, []

    all_keys = list(dict.fromkeys(k for r in records for k in r))
    for r in records:
        for k in all_keys:
            r.setdefault(k, "")

    return all_keys, records


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

def _apply_column_map(rows, col_map):
    """
    Rename row keys according to col_map { app_field: "PDF Column Header" }.
    """
    rename = {pdf_col: app_field for app_field, pdf_col in col_map.items() if pdf_col}
    result = []
    for row in rows:
        new_row = {rename.get(k, k): v for k, v in row.items()}
        result.append(new_row)
    return result


# ---------------------------------------------------------------------------
# Post-processing helpers
# ---------------------------------------------------------------------------

# Fragments that appear in the PDF's watermark / fraud-check overlay text.
_GARBAGE_FRAGMENTS = ("www.Colleg", "ectory w", "Fraud Check", "Contact @Coll",
                      "eRadioDirectory", "eekly for available")


def _is_garbage_row(row):
    """Return True if this row is a watermark fragment, not a real station."""
    combined = " ".join(str(v) for v in row.values())
    return any(frag in combined for frag in _GARBAGE_FRAGMENTS)


_VALID_TLD_RE = re.compile(r'\.[a-zA-Z]{2,}$')


def _has_valid_tld(s):
    """True if *s* ends with something that looks like a completed TLD."""
    return bool(_VALID_TLD_RE.search(s))


def _clean_email(raw):
    """
    Fix spaces inserted by PDF line-break extraction within email addresses.

    The PDF extractor often splits a single address across two tokens:
        "wljsmusicdirector@gm" + "ail.com"
        "music.hiphop@wvuafm.ua." + "edu"
        "krua.programdirector@alas" + "ka.edu"
        "info.cfak883@usherbrooke" + ".ca"

    Strategy: walk the tokens; if a token contains '@' but its domain part
    has no valid TLD yet, merge it with the next token. Continue merging
    until the address is complete or we run out of non-'@' tokens.
    """
    tokens = raw.split()
    result = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if "@" in tok and not _has_valid_tld(tok):
            # Incomplete address — absorb following tokens until it resolves.
            while i + 1 < len(tokens) and "@" not in tokens[i + 1]:
                i += 1
                tok += tokens[i]
                if _has_valid_tld(tok):
                    break
        result.append(tok)
        i += 1
    return " ".join(result)


# ---------------------------------------------------------------------------
# State/City auto-split
# ---------------------------------------------------------------------------

_STATE_CITY_RE = re.compile(r'^([A-Z]{2}(?:/[A-Z]{2})?),\s*(.+)$')


def _split_state_city(row):
    """
    If 'city' holds a combined "ST, CityName" value (e.g. "AL, Auburn"),
    populate 'state' and 'city' individually.  Canadian entries like
    "Windsor, Ontario" do not match and are left unchanged.
    """
    city_val = row.get("city", "").strip()
    if not city_val:
        return row
    m = _STATE_CITY_RE.match(city_val)
    if m and not row.get("state", "").strip():
        row["state"] = m.group(1).strip()
        row["city"]  = m.group(2).strip()
    return row


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_stations(pdf_path=None, col_map=None):
    """
    Main entry point. Returns a list of dicts, one per station.
    Standardised keys: station_name, contact_name, email, school,
                       city, state, genre, notes.
    """
    pdf_path = pdf_path or PDF_PATH
    col_map  = col_map  or COLUMN_MAP

    # Convert 1-indexed page numbers from config to 0-indexed slice bounds.
    start = max(0, PDF_START_PAGE - 1)
    end   = PDF_END_PAGE  # slice end is exclusive, so this covers through the page

    with pdfplumber.open(pdf_path) as pdf:
        headers, rows = _extract_tables(pdf, start, end)
        if not rows:
            headers, rows = _extract_text_blocks(pdf, start, end)

    if not rows:
        return []

    # Drop completely blank rows and PDF watermark fragments.
    rows = [r for r in rows if any(v for v in r.values() if str(v).strip())]
    rows = [r for r in rows if not _is_garbage_row(r)]

    if col_map:
        rows = _apply_column_map(rows, col_map)

    # Ensure all required keys exist and values are strings.
    required = ["station_name", "contact_name", "first_name", "last_name",
                "email", "school", "city", "state", "genre", "notes"]
    for row in rows:
        for key in required:
            row.setdefault(key, "")
        for key in list(row.keys()):
            if row[key] is None:
                row[key] = ""
        # Treat bare "-" or "—" as empty (PDF placeholder for missing data).
        for key in list(row.keys()):
            if row[key].strip() in ("-", "—"):
                row[key] = ""
        # Remove whitespace artifacts from email addresses (PDF line-break extraction).
        if row.get("email"):
            row["email"] = _clean_email(row["email"])
        # Split "ST, CityName" → separate state + city fields.
        _split_state_city(row)
        # Build contact_name from separate first/last if needed.
        if (row.get("first_name") or row.get("last_name")) and not row.get("contact_name"):
            row["contact_name"] = " ".join(
                p for p in [row.get("first_name", ""), row.get("last_name", "")] if p
            ).strip()

    return rows


def get_pdf_columns(pdf_path=None):
    """
    Returns (columns, sample_rows) for the column-mapping UI.
    Uses the same page range as extract_stations.
    """
    pdf_path = pdf_path or PDF_PATH

    start = max(0, PDF_START_PAGE - 1)
    end   = PDF_END_PAGE

    with pdfplumber.open(pdf_path) as pdf:
        headers, rows = _extract_tables(pdf, start, end)
        if not rows:
            headers, rows = _extract_text_blocks(pdf, start, end)

    if not rows or not headers:
        return [], []

    return headers, rows[:3]

"""
parse_pdf.py
Extracts radio station records from the College Radio Directory PDF.

Tries table extraction first, then falls back to key: value text block parsing.
No pandas dependency — uses plain dicts and lists throughout.
"""

import pdfplumber
import re
import os
from config import PDF_PATH, COLUMN_MAP


def _clean(val):
    if val is None:
        return ""
    return str(val).strip().replace("\n", " ")


def _extract_tables(pdf):
    """
    Scan every page for tables. Returns (headers, rows) where rows is a list
    of dicts, or (None, []) if no tables were found.
    """
    headers = None
    rows = []

    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for table in tables:
            if not table:
                continue
            if headers is None:
                headers = [_clean(h) for h in table[0]]
                data_rows = table[1:]
            else:
                data_rows = table

            for row in data_rows:
                cleaned = [_clean(c) for c in row]
                if any(cleaned):
                    # Pad or trim to match header count
                    while len(cleaned) < len(headers):
                        cleaned.append("")
                    rows.append(dict(zip(headers, cleaned[:len(headers)])))

    return (headers, rows) if headers and rows else (None, [])


def _extract_text_blocks(pdf):
    """
    Fallback for PDFs without tables.
    Parses blocks of "Key: Value" lines separated by blank lines.
    Returns (columns, rows).
    """
    records = []
    current = {}

    for page in pdf.pages:
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

    # Collect all keys seen across all records
    all_keys = list(dict.fromkeys(k for r in records for k in r))
    # Fill missing keys with ""
    for r in records:
        for k in all_keys:
            r.setdefault(k, "")

    return all_keys, records


def _apply_column_map(rows, col_map):
    """
    Rename keys in each row dict according to col_map
    { app_field: "PDF Column Header" }.
    """
    # Build reverse map: PDF header → app field name
    rename = {pdf_col: app_field for app_field, pdf_col in col_map.items() if pdf_col}

    result = []
    for row in rows:
        new_row = {}
        for key, val in row.items():
            new_key = rename.get(key, key)
            new_row[new_key] = val
        result.append(new_row)
    return result


def extract_stations(pdf_path=None, col_map=None):
    """
    Main entry point. Returns a list of dicts, one per station.
    Standardised keys: station_name, contact_name, email, school, city, state, genre, notes.
    """
    pdf_path = pdf_path or PDF_PATH
    col_map  = col_map  or COLUMN_MAP

    with pdfplumber.open(pdf_path) as pdf:
        headers, rows = _extract_tables(pdf)
        if not rows:
            headers, rows = _extract_text_blocks(pdf)

    if not rows:
        return []

    # Drop completely empty rows
    rows = [r for r in rows if any(v for v in r.values() if str(v).strip())]

    if col_map:
        rows = _apply_column_map(rows, col_map)

    # Ensure all required keys exist
    required = ["station_name", "contact_name", "first_name", "last_name",
                "email", "school", "city", "state", "genre", "notes"]
    for row in rows:
        for key in required:
            row.setdefault(key, "")
        for key in list(row.keys()):
            if row[key] is None:
                row[key] = ""
        # If separate first/last columns were mapped, build contact_name from them
        if (row.get("first_name") or row.get("last_name")) and not row.get("contact_name"):
            row["contact_name"] = " ".join(
                p for p in [row.get("first_name", ""), row.get("last_name", "")] if p
            ).strip()

    return rows


def get_pdf_columns(pdf_path=None):
    """
    Returns (columns, sample_rows) for the column-mapping UI.
    """
    pdf_path = pdf_path or PDF_PATH

    with pdfplumber.open(pdf_path) as pdf:
        headers, rows = _extract_tables(pdf)
        if not rows:
            headers, rows = _extract_text_blocks(pdf)

    if not rows or not headers:
        return [], []

    sample = rows[:3]
    return headers, sample

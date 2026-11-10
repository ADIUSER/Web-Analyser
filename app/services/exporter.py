"""CSV exports using Pandas with spreadsheet formula-injection mitigation."""
from __future__ import annotations

import re

import pandas as pd


_FORMULA_PREFIX = re.compile(r"^[\s\x00-\x1f]*[=+\-@]")


def safe_csv_value(value):
    """Prefix formula-like strings with an apostrophe before spreadsheet import."""
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        value = "; ".join(map(str, value)) if not isinstance(value, dict) else str(value)
    if isinstance(value, str) and _FORMULA_PREFIX.match(value):
        return "'" + value
    return value


def dataframe_csv(records: list[dict], columns: list[str] | None = None) -> str:
    frame = pd.DataFrame.from_records(records, columns=columns)
    if not frame.empty:
        for column in frame.columns:
            frame[column] = frame[column].map(safe_csv_value)
    return frame.to_csv(index=False, lineterminator="\n")

import csv
from io import StringIO

from app.services.exporter import dataframe_csv, safe_csv_value


def test_csv_formula_injection_is_prefixed():
    assert safe_csv_value("=1+1") == "'=1+1"
    assert safe_csv_value("  @SUM(A1:A2)") == "'  @SUM(A1:A2)"
    assert safe_csv_value("safe value") == "safe value"
    assert safe_csv_value(None) == ""


def test_dataframe_csv_quotes_values_and_preserves_headers():
    output = dataframe_csv([{"url": "=cmd", "count": 2}], columns=["url", "count"])
    row = next(csv.DictReader(StringIO(output)))
    assert row["url"] == "'=cmd"
    assert row["count"] == "2"

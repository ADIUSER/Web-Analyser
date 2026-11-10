"""Helpers for whole-scan SEO summaries."""
from collections import Counter


def summarize_seo(page_dicts: list[dict]) -> dict:
    successful = [p for p in page_dicts if not p.get("error_message") and p.get("status_code") and 200 <= p["status_code"] < 400]
    title_counts = Counter((p.get("page_title") or "").strip().casefold() for p in successful if (p.get("page_title") or "").strip())
    description_counts = Counter((p.get("meta_description") or "").strip().casefold() for p in successful if (p.get("meta_description") or "").strip())
    return {
        "pages_missing_title": sum(not (p.get("page_title") or "").strip() for p in successful),
        "pages_missing_description": sum(not (p.get("meta_description") or "").strip() for p in successful),
        "pages_missing_h1": sum((p.get("h1_count") or 0) == 0 for p in successful),
        "duplicate_titles": sum(count > 1 for count in title_counts.values()),
        "duplicate_descriptions": sum(count > 1 for count in description_counts.values()),
    }


def findings_for_page(page) -> list[str]:
    return list(page.seo_findings or [])

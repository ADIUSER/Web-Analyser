from __future__ import annotations

import logging
import threading
from datetime import timezone

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db
from .models import LinkResult, PageResult, Scan
from .services.crawler import WebsiteCrawler
from .services.exporter import dataframe_csv
from .services.seo_analyzer import summarize_seo
from .services.url_validator import URLValidationError, validate_url

logger = logging.getLogger(__name__)
bp = Blueprint("main", __name__)
_SCAN_SLOTS = threading.BoundedSemaphore(value=2)


@bp.get("/")
def index():
    recent_scans = Scan.query.order_by(Scan.created_at.desc()).limit(5).all()
    return render_template("index.html", recent_scans=recent_scans)


@bp.post("/scan")
def start_scan():
    submitted_url = request.form.get("url", "")
    check_links = request.form.get("check_links") == "on"
    try:
        validated = validate_url(
            submitted_url,
            allowed_http_ports=tuple(current_app.config.get("ALLOWED_HTTP_PORTS", (80,))),
            allowed_https_ports=tuple(current_app.config.get("ALLOWED_HTTPS_PORTS", (443,))),
        )
    except URLValidationError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.index"))

    if not _SCAN_SLOTS.acquire(blocking=False):
        flash("The scanner is busy with other scans. Please try again shortly.", "warning")
        return redirect(url_for("main.index"))

    scan = Scan(
        submitted_url=submitted_url.strip(),
        normalized_start_url=validated.url,
        status="running",
    )
    scan_id = None
    try:
        db.session.add(scan)
        db.session.commit()
        scan_id = scan.id
        result = WebsiteCrawler(current_app.config).run(validated.url, check_links=check_links)
        for page_data in result["pages"]:
            cleaned = dict(page_data)
            if "title" in cleaned:
                cleaned["page_title"] = cleaned.pop("title")
            # Keep the model mapping explicit so future parser fields do not leak into ORM constructors.
            page_fields = {
                "requested_url", "final_url", "status_code", "response_time_ms", "response_size_bytes",
                "redirect_count", "page_title", "title_length", "meta_description", "meta_description_length",
                "h1_count", "h2_count", "word_count", "character_count", "paragraph_count", "heading_count",
                "image_count", "images_missing_alt_count", "internal_link_count", "external_link_count",
                "canonical_url", "meta_robots", "og_title", "og_description", "language", "viewport_present",
                "seo_findings", "text_preview", "error_message",
            }
            values = {key: value for key, value in cleaned.items() if key in page_fields}
            db.session.add(PageResult(scan_id=scan.id, **values))
        for link_data in result["links"]:
            db.session.add(LinkResult(scan_id=scan.id, **link_data))

        summary = result["summary"]
        scan.discovered_pages = summary["discovered_pages"]
        scan.successful_pages = summary["successful_pages"]
        scan.failed_pages = summary["failed_pages"]
        scan.status = "completed" if scan.successful_pages > 0 else "failed"
        if summary.get("crawl_limit_reached"):
            scan.error_message = "A configured page, link, or time limit was reached; results may be partial."
        elif scan.status == "failed":
            scan.error_message = "No pages could be analyzed. Check the URL and whether the website allows crawling."
        db.session.commit()
        if scan.status == "failed":
            flash(scan.error_message or "The scan did not complete.", "warning")
        return redirect(url_for("main.scan_results", scan_id=scan.id))
    except Exception:
        logger.exception("Scan failed unexpectedly (scan_id=%s)", scan_id)
        db.session.rollback()
        # The scan row may still exist; report a safe failure to the user.
        persisted = db.session.get(Scan, scan_id) if scan_id else None
        if persisted:
            persisted.status = "failed"
            persisted.error_message = "The scan could not be completed because of an internal error."
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
        flash("The scan could not be completed. Review the URL and server log, then try again.", "danger")
        return redirect(url_for("main.index"))
    finally:
        _SCAN_SLOTS.release()


def _scan_or_404(scan_id: int) -> Scan:
    scan = db.session.get(Scan, scan_id)
    if scan is None:
        abort(404)
    return scan


def _scan_context(scan: Scan) -> dict:
    pages = list(scan.pages)
    links = list(scan.links)
    homepage = next((p for p in pages if p.requested_url == scan.normalized_start_url), None)
    page_dicts = [{
        "page_title": p.page_title,
        "meta_description": p.meta_description,
        "h1_count": p.h1_count,
        "status_code": p.status_code,
        "error_message": p.error_message,
    } for p in pages]
    seo = summarize_seo(page_dicts)
    seo_issues = sum(len(p.seo_findings or []) for p in pages if not p.error_message)
    status_counts = {}
    for page in pages:
        label = str(page.status_code) if page.status_code is not None else "Unknown"
        status_counts[label] = status_counts.get(label, 0) + 1
    seo_chart = {
        "missingTitle": seo["pages_missing_title"],
        "missingDescription": seo["pages_missing_description"],
        "missingH1": seo["pages_missing_h1"],
    }
    return {
        "scan": scan,
        "pages": pages,
        "homepage": homepage,
        "links": links,
        "seo": seo,
        "seo_issues": seo_issues,
        "status_labels": list(status_counts.keys()),
        "status_values": list(status_counts.values()),
        "seo_chart": seo_chart,
        "broken_links": sum(1 for link in links if link.checked and link.check_result == "broken"),
        "internal_links": sum(1 for link in links if link.classification == "internal"),
        "external_links": sum(1 for link in links if link.classification == "external"),
    }


@bp.get("/scan/<int:scan_id>")
def scan_results(scan_id):
    return render_template("scan_results.html", **_scan_context(_scan_or_404(scan_id)))


@bp.get("/scan/<int:scan_id>/seo")
def seo_report(scan_id):
    context = _scan_context(_scan_or_404(scan_id))
    return render_template("seo_report.html", **context)


@bp.get("/scan/<int:scan_id>/links")
def link_report(scan_id):
    context = _scan_context(_scan_or_404(scan_id))
    return render_template("link_report.html", **context)


@bp.get("/page/<int:page_id>")
def page_details(page_id):
    page = db.session.get(PageResult, page_id)
    if page is None:
        abort(404)
    return render_template("page_details.html", page=page, scan=page.scan)


@bp.get("/history")
def history():
    scans = Scan.query.order_by(Scan.created_at.desc()).limit(200).all()
    return render_template("history.html", scans=scans)


@bp.get("/scan/<int:scan_id>/export/<kind>.csv")
def export_csv(scan_id, kind):
    scan = _scan_or_404(scan_id)
    pages = list(scan.pages)
    links = list(scan.links)
    if kind == "pages":
        records = [{
            "requested_url": p.requested_url,
            "final_url": p.final_url,
            "status_code": p.status_code,
            "response_time_ms": p.response_time_ms,
            "response_size_bytes": p.response_size_bytes,
            "redirect_count": p.redirect_count,
            "title": p.page_title,
            "title_length": p.title_length,
            "meta_description": p.meta_description,
            "meta_description_length": p.meta_description_length,
            "h1_count": p.h1_count,
            "h2_count": p.h2_count,
            "word_count": p.word_count,
            "character_count": p.character_count,
            "paragraph_count": p.paragraph_count,
            "heading_count": p.heading_count,
            "image_count": p.image_count,
            "images_missing_alt_count": p.images_missing_alt_count,
            "internal_link_count": p.internal_link_count,
            "external_link_count": p.external_link_count,
            "canonical_url": p.canonical_url,
            "meta_robots": p.meta_robots,
            "language": p.language,
            "viewport_present": p.viewport_present,
            "seo_findings": "; ".join(p.seo_findings or []),
            "error_message": p.error_message,
        } for p in pages]
    elif kind == "seo":
        records = [{
            "url": p.requested_url,
            "title": p.page_title,
            "title_length": p.title_length,
            "meta_description": p.meta_description,
            "meta_description_length": p.meta_description_length,
            "h1_count": p.h1_count,
            "h2_count": p.h2_count,
            "canonical_url": p.canonical_url,
            "meta_robots": p.meta_robots,
            "missing_title": not bool((p.page_title or "").strip()),
            "missing_meta_description": not bool((p.meta_description or "").strip()),
            "missing_h1": p.h1_count == 0,
            "findings": "; ".join(p.seo_findings or []),
        } for p in pages]
    elif kind == "links":
        records = [{
            "source_url": l.source_url,
            "destination_url": l.destination_url,
            "classification": l.classification,
            "anchor_text": l.anchor_text,
            "status_code": l.status_code,
            "check_result": l.check_result,
            "checked": l.checked,
        } for l in links]
    elif kind == "summary":
        context = _scan_context(scan)
        records = [{
            "scan_id": scan.id,
            "submitted_url": scan.submitted_url,
            "normalized_start_url": scan.normalized_start_url,
            "scan_timestamp_utc": scan.created_at.replace(tzinfo=timezone.utc).isoformat(),
            "scan_status": scan.status,
            "discovered_pages": scan.discovered_pages,
            "successful_pages": scan.successful_pages,
            "failed_pages": scan.failed_pages,
            "internal_links": context["internal_links"],
            "external_links": context["external_links"],
            "broken_links_checked": context["broken_links"],
            **context["seo"],
            "seo_findings_count": context["seo_issues"],
        }]
    else:
        abort(404)

    csv_text = dataframe_csv(records)
    response = make_response(csv_text)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="website-scan-{scan.id}-{kind}.csv"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

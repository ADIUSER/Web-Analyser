from app.extensions import db
from app.models import PageResult, Scan
from app.services.url_validator import ValidatedURL


def test_home_and_history_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/history").status_code == 200


def test_invalid_url_is_rejected_before_scan_is_created(app, client):
    response = client.post("/scan", data={"url": "http://localhost"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Local and internal hostnames" in response.data
    with app.app_context():
        assert Scan.query.count() == 0


def test_scan_report_and_csv_export_use_persisted_rows(app, client, monkeypatch):
    import app.routes as routes

    monkeypatch.setattr(routes, "validate_url", lambda _url, **_kw: ValidatedURL("https://example.com/", "https", "example.com", 443, ("93.184.216.34",)))

    class FakeCrawler:
        def __init__(self, _config):
            pass

        def run(self, _url, check_links=False):
            return {
                "pages": [{
                    "requested_url": "https://example.com/",
                    "final_url": "https://example.com/",
                    "status_code": 200,
                    "response_time_ms": 13.2,
                    "response_size_bytes": 128,
                    "redirect_count": 0,
                    "title": "Demo",
                    "title_length": 4,
                    "meta_description": "A demo site",
                    "meta_description_length": 11,
                    "h1_count": 1,
                    "h2_count": 0,
                    "word_count": 4,
                    "character_count": 20,
                    "paragraph_count": 1,
                    "heading_count": 1,
                    "image_count": 0,
                    "images_missing_alt_count": 0,
                    "internal_link_count": 0,
                    "external_link_count": 0,
                    "canonical_url": "",
                    "meta_robots": "",
                    "og_title": "",
                    "og_description": "",
                    "language": "en",
                    "viewport_present": True,
                    "seo_findings": [],
                    "text_preview": "Demo text",
                    "error_message": None,
                }],
                "links": [{
                    "source_url": "https://example.com/",
                    "destination_url": "https://other.example/",
                    "classification": "external",
                    "anchor_text": "other",
                    "status_code": None,
                    "check_result": "not_checked",
                    "checked": False,
                }],
                "summary": {"discovered_pages": 1, "successful_pages": 1, "failed_pages": 0, "total_internal_links": 0, "total_external_links": 1, "broken_links": 0, "crawl_limit_reached": False, "robots_unavailable": False},
            }

    monkeypatch.setattr(routes, "WebsiteCrawler", FakeCrawler)
    response = client.post("/scan", data={"url": "https://example.com"}, follow_redirects=False)
    assert response.status_code == 302
    assert "/scan/" in response.headers["Location"]

    with app.app_context():
        scan = Scan.query.one()
        assert scan.status == "completed"
        assert scan.successful_pages == 1
        assert PageResult.query.filter_by(scan_id=scan.id).count() == 1
        scan_id = scan.id

    report = client.get(f"/scan/{scan_id}")
    assert report.status_code == 200
    assert b"Demo" in report.data
    page_csv = client.get(f"/scan/{scan_id}/export/pages.csv")
    assert page_csv.status_code == 200
    assert b"requested_url" in page_csv.data
    link_csv = client.get(f"/scan/{scan_id}/export/links.csv")
    assert b"other.example" in link_csv.data
    assert client.get(f"/scan/{scan_id}/export/unknown.csv").status_code == 404

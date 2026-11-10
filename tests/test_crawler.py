from types import SimpleNamespace

from app.services import crawler as crawler_module
from app.services.crawler import WebsiteCrawler
from app.services.url_validator import ValidatedURL


class FakeFetcher:
    def __init__(self, pages, config):
        self.pages = pages
        self.config = dict(config)
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return SimpleNamespace(status_code=404, body=b"", final_url=url, response_time_ms=1, response_size_bytes=0, redirect_count=0, headers={})
        if url in self.pages:
            body = self.pages[url].encode()
            return SimpleNamespace(status_code=200, body=body, final_url=url, response_time_ms=11, response_size_bytes=len(body), redirect_count=0, headers={"Content-Type": "text/html"})
        return SimpleNamespace(status_code=404, body=b"<html><title>Not found</title></html>", final_url=url, response_time_ms=5, response_size_bytes=33, redirect_count=0, headers={"Content-Type": "text/html"})

    def check_link(self, url):
        return 404, "broken"


def test_crawler_deduplicates_internal_urls_and_obeys_page_limit(monkeypatch):
    start = "https://example.com/"
    pages = {
        start: '<html lang="en"><head><title>Home</title></head><body><h1>Home</h1><a href="/about">About</a><a href="/about">Duplicate</a><a href="https://external.example/x">External</a></body></html>',
        "https://example.com/about": '<html><head><title>About</title></head><body><h1>About</h1><a href="/">Home</a></body></html>',
    }
    monkeypatch.setattr(crawler_module, "validate_url", lambda _url, **_kw: ValidatedURL(start, "https", "example.com", 443, ("93.184.216.34",)))
    config = {"MAX_PAGES": 10, "MAX_DEPTH": 2, "SCAN_TIMEOUT_SECONDS": 10, "REQUEST_DELAY_SECONDS": 0, "MAX_ROBOTS_BYTES": 1024, "MAX_LINKS_PER_PAGE": 100, "MAX_LINK_RESULTS": 200, "MAX_LINK_CHECKS": 2, "USER_AGENT": "TestBot"}
    fetcher = FakeFetcher(pages, config)
    result = WebsiteCrawler(config, fetcher).run(start)
    assert result["summary"]["discovered_pages"] == 2
    assert result["summary"]["successful_pages"] == 2
    assert fetcher.calls.count("https://example.com/about") == 1
    assert result["summary"]["total_internal_links"] == 3
    assert result["summary"]["total_external_links"] == 1


def test_crawler_respects_maximum_depth(monkeypatch):
    start = "https://example.com/"
    pages = {
        start: '<a href="/one">One</a>',
        "https://example.com/one": '<a href="/two">Two</a>',
        "https://example.com/two": '<title>Two</title>',
    }
    monkeypatch.setattr(crawler_module, "validate_url", lambda _url, **_kw: ValidatedURL(start, "https", "example.com", 443, ("93.184.216.34",)))
    config = {"MAX_PAGES": 10, "MAX_DEPTH": 1, "SCAN_TIMEOUT_SECONDS": 10, "REQUEST_DELAY_SECONDS": 0, "MAX_ROBOTS_BYTES": 1024, "MAX_LINKS_PER_PAGE": 100, "MAX_LINK_RESULTS": 200, "MAX_LINK_CHECKS": 2, "USER_AGENT": "TestBot"}
    fetcher = FakeFetcher(pages, config)
    result = WebsiteCrawler(config, fetcher).run(start)
    assert result["summary"]["discovered_pages"] == 2
    assert "https://example.com/two" not in fetcher.calls

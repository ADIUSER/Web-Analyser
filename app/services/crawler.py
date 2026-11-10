"""Breadth-first crawler with robots.txt rules and strict resource bounds."""
from __future__ import annotations

import logging
import time
from collections import deque
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .fetcher import FetchError, SafeFetcher
from .parser import parse_html
from .url_validator import URLValidationError, normalize_url, validate_url

logger = logging.getLogger(__name__)
NON_HTML_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tif", ".tiff",
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".ogg", ".flac",
    ".zip", ".gz", ".tar", ".rar", ".7z", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".woff", ".woff2", ".ttf", ".eot", ".css", ".js",
}


class CrawlError(RuntimeError):
    pass


class WebsiteCrawler:
    def __init__(self, config, fetcher: SafeFetcher | None = None):
        self.config = config
        self.fetcher = fetcher or SafeFetcher(config)

    def _robots_policy(self, start_url: str, user_agent: str):
        parsed = urlsplit(start_url)
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            result = self.fetcher.fetch(
                robots_url,
                max_bytes=int(self.config.get("MAX_ROBOTS_BYTES", 262_144)),
                allow_non_html=True,
            )
            if result.status_code in (404, 410):
                parser.parse([])
                return parser, False, 0.0
            if not 200 <= result.status_code < 300:
                logger.info("robots.txt returned status %s; fail-closed for %s", result.status_code, start_url)
                parser.parse(["User-agent: *", "Disallow: /"])
                return parser, True, 0.0
            text = result.body.decode("utf-8", errors="replace")
            parser.parse(text.splitlines())
            delay = parser.crawl_delay(user_agent) or parser.crawl_delay("*") or 0
            return parser, False, float(delay or 0)
        except (FetchError, URLValidationError) as exc:
            logger.info("Could not safely read robots.txt for %s: %s", start_url, exc)
            # Fail closed if the policy file cannot be retrieved safely.
            parser.parse(["User-agent: *", "Disallow: /"])
            return parser, True, 0.0

    def run(self, start_url: str, check_links: bool = False) -> dict:
        validated = validate_url(
            start_url,
            allowed_http_ports=tuple(self.config.get("ALLOWED_HTTP_PORTS", (80,))),
            allowed_https_ports=tuple(self.config.get("ALLOWED_HTTPS_PORTS", (443,))),
        )
        start_url = validated.url
        root_hostname = validated.hostname
        page_limit = max(1, min(int(self.config.get("MAX_PAGES", 20)), 100))
        max_depth = max(0, min(int(self.config.get("MAX_DEPTH", 2)), 5))
        max_duration = max(5, int(self.config.get("SCAN_TIMEOUT_SECONDS", 60)))
        deadline = time.monotonic() + max_duration
        user_agent = self.config.get("USER_AGENT", "PortfolioWebsiteAnalyzer/1.0")
        robots, robots_unavailable, robots_delay = self._robots_policy(start_url, user_agent)

        pages = []
        links = []
        queue = deque([(start_url, 0)])
        visited = {start_url}
        reached_limit = False
        effective_delay = max(float(self.config.get("REQUEST_DELAY_SECONDS", 0.25)), robots_delay)
        # SafeFetcher reads the same setting; enforce the greater robots delay here too.
        original_delay = self.fetcher.config.get("REQUEST_DELAY_SECONDS", 0.25)
        self.fetcher.config["REQUEST_DELAY_SECONDS"] = effective_delay

        try:
            while queue and len(pages) < page_limit:
                if time.monotonic() >= deadline:
                    reached_limit = True
                    break
                requested_url, depth = queue.popleft()
                if not robots.can_fetch(user_agent, requested_url):
                    pages.append(self._error_page(requested_url, "Disallowed by robots.txt; page was not fetched."))
                    continue
                try:
                    response = self.fetcher.fetch(requested_url)
                    parsed = parse_html(
                        response.body,
                        response.final_url,
                        root_hostname,
                        max_links=int(self.config.get("MAX_LINKS_PER_PAGE", 500)),
                    )
                    page_data = {
                        "requested_url": requested_url,
                        "final_url": response.final_url,
                        "status_code": response.status_code,
                        "response_time_ms": round(response.response_time_ms, 2),
                        "response_size_bytes": response.response_size_bytes,
                        "redirect_count": response.redirect_count,
                        "error_message": None,
                        **{key: value for key, value in parsed.items() if key != "links"},
                    }
                    pages.append(page_data)
                    for link in parsed["links"]:
                        if len(links) >= int(self.config.get("MAX_LINK_RESULTS", 2000)):
                            reached_limit = True
                            break
                        links.append({
                            "source_url": response.final_url,
                            "destination_url": link["destination_url"],
                            "classification": link["classification"],
                            "anchor_text": link["anchor_text"],
                            "status_code": None,
                            "check_result": "not_checked",
                            "checked": False,
                        })
                    if depth < max_depth:
                        for link in parsed["links"]:
                            if link["classification"] != "internal" or not link["destination_url"]:
                                continue
                            destination = link["destination_url"]
                            try:
                                destination = normalize_url(
                                    destination,
                                    tuple(self.config.get("ALLOWED_HTTP_PORTS", (80,))),
                                    tuple(self.config.get("ALLOWED_HTTPS_PORTS", (443,))),
                                )
                                parts = urlsplit(destination)
                            except URLValidationError:
                                continue
                            if (parts.hostname or "").lower().rstrip(".") != root_hostname:
                                continue
                            if any(parts.path.lower().endswith(ext) for ext in NON_HTML_EXTENSIONS):
                                continue
                            if destination not in visited and len(visited) < page_limit and time.monotonic() < deadline:
                                visited.add(destination)
                                queue.append((destination, depth + 1))
                except (FetchError, URLValidationError) as exc:
                    logger.info("Page fetch failed for %s: %s", requested_url, exc)
                    pages.append(self._error_page(requested_url, str(exc)))
                except Exception:
                    logger.exception("Unexpected page analysis failure for %s", requested_url)
                    pages.append(self._error_page(requested_url, "Page analysis failed unexpectedly."))

            if queue or len(visited) >= page_limit or reached_limit:
                reached_limit = True

            if check_links:
                max_checks = max(0, int(self.config.get("MAX_LINK_CHECKS", 30)))
                checked_destinations = set()
                for link in links:
                    destination = link["destination_url"]
                    if (not destination or link["classification"] not in {"internal", "external"}
                            or not destination.lower().startswith(("http://", "https://"))):
                        continue
                    if destination in checked_destinations:
                        continue
                    if len(checked_destinations) >= max_checks or time.monotonic() >= deadline:
                        reached_limit = True
                        break
                    checked_destinations.add(destination)
                    # URL is validated again and DNS-pinned inside check_link/fetch.
                    status, label = self.fetcher.check_link(destination)
                    for row in links:
                        if row["destination_url"] == destination:
                            row["status_code"] = status
                            row["check_result"] = label
                            row["checked"] = status is not None
        finally:
            self.fetcher.config["REQUEST_DELAY_SECONDS"] = original_delay

        summary = {
            "discovered_pages": len(pages),
            "successful_pages": sum(1 for page in pages if page.get("status_code") is not None and 200 <= page["status_code"] < 400 and not page.get("error_message")),
            "failed_pages": sum(1 for page in pages if page.get("error_message") or page.get("status_code") is None or page["status_code"] >= 400),
            "total_internal_links": sum(1 for link in links if link["classification"] == "internal"),
            "total_external_links": sum(1 for link in links if link["classification"] == "external"),
            "broken_links": sum(1 for link in links if link["checked"] and link["check_result"] == "broken"),
            "crawl_limit_reached": reached_limit,
            "robots_unavailable": robots_unavailable,
        }
        return {"pages": pages, "links": links, "summary": summary}

    @staticmethod
    def _error_page(url: str, message: str) -> dict:
        return {
            "requested_url": url,
            "final_url": None,
            "status_code": None,
            "response_time_ms": None,
            "response_size_bytes": 0,
            "redirect_count": 0,
            "page_title": "",
            "title_length": 0,
            "meta_description": "",
            "meta_description_length": 0,
            "h1_count": 0,
            "h2_count": 0,
            "heading_count": 0,
            "paragraph_count": 0,
            "word_count": 0,
            "character_count": 0,
            "image_count": 0,
            "images_missing_alt_count": 0,
            "internal_link_count": 0,
            "external_link_count": 0,
            "canonical_url": "",
            "meta_robots": "",
            "og_title": "",
            "og_description": "",
            "language": "",
            "viewport_present": False,
            "seo_findings": ["Page could not be analyzed"],
            "text_preview": "",
            "error_message": message[:500],
        }

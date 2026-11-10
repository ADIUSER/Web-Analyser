"""HTML content extraction and link classification."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup


def _normalize_link_url(href: str, page_url: str) -> str | None:
    absolute = urljoin(page_url, href.strip())
    try:
        parsed = urlsplit(absolute)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = parsed.hostname.lower().rstrip(".")
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        default_port = 443 if parsed.scheme.lower() == "https" else 80
        netloc = host if not port or port == default_port else f"{host}:{port}"
        return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))
    except (ValueError, TypeError):
        return None


def parse_html(html: str | bytes, page_url: str, root_hostname: str, max_links: int = 500) -> dict:
    """Return SEO/content metrics and classified link records for one HTML page."""
    soup = BeautifulSoup(html, "html.parser")
    root_hostname = (root_hostname or "").lower().rstrip(".")
    html_tag = soup.find("html")
    language = (html_tag.get("lang") or "").strip() if html_tag else ""
    title_tag = soup.find("title")
    title = title_tag.get_text(" ", strip=True) if title_tag else ""
    meta_description_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    meta_description = (meta_description_tag.get("content") or "").strip() if meta_description_tag else ""
    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in [str(v).lower() for v in (value if isinstance(value, list) else [value])]})
    canonical = (canonical_tag.get("href") or "").strip() if canonical_tag else ""
    robots_tag = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    meta_robots = (robots_tag.get("content") or "").strip() if robots_tag else ""
    og_title_tag = soup.find("meta", attrs={"property": "og:title"})
    og_desc_tag = soup.find("meta", attrs={"property": "og:description"})
    og_title = (og_title_tag.get("content") or "").strip() if og_title_tag else ""
    og_description = (og_desc_tag.get("content") or "").strip() if og_desc_tag else ""
    viewport_present = bool(soup.find("meta", attrs={"name": re.compile(r"^viewport$", re.I)}))

    h1_count = len(soup.find_all("h1"))
    h2_count = len(soup.find_all("h2"))
    headings = len(soup.find_all(re.compile(r"^h[1-6]$", re.I)))
    paragraphs = len(soup.find_all("p"))
    images = soup.find_all("img")
    images_missing_alt = sum(1 for image in images if not image.has_attr("alt"))

    links = []
    internal_count = 0
    external_count = 0
    anchor_count = 0
    empty_count = 0
    for anchor in soup.find_all("a"):
        raw_href = anchor.get("href")
        anchor_text = anchor.get_text(" ", strip=True)[:1000]
        if raw_href is None or not str(raw_href).strip():
            classification, destination = "empty", None
            empty_count += 1
        elif str(raw_href).strip().startswith("#"):
            classification, destination = "anchor", urljoin(page_url, str(raw_href).strip())
            anchor_count += 1
        else:
            destination = _normalize_link_url(str(raw_href), page_url)
            if destination is None:
                # mailto:, tel:, and other non-web destinations are external references.
                destination = str(raw_href).strip()[:2048]
                classification = "external"
                external_count += 1
            else:
                try:
                    dest_host = (urlsplit(destination).hostname or "").lower().rstrip(".")
                except ValueError:
                    dest_host = ""
                if dest_host == root_hostname:
                    classification = "internal"
                    internal_count += 1
                else:
                    classification = "external"
                    external_count += 1
        if len(links) < max_links:
            links.append({
                "destination_url": destination,
                "classification": classification,
                "anchor_text": anchor_text,
            })

    # Remove non-content nodes before estimating readable text.
    text_soup = BeautifulSoup(str(soup), "html.parser")
    for node in text_soup(["head", "script", "style", "noscript", "svg", "canvas", "template", "iframe"]):
        node.decompose()
    readable_text = " ".join(text_soup.stripped_strings)
    words = re.findall(r"\b[\w’'-]+\b", readable_text, flags=re.UNICODE)

    findings = []
    if not title:
        findings.append("Missing page title")
    elif len(title) > 60:
        findings.append("Title is longer than 60 characters (informational guideline)")
    if not meta_description:
        findings.append("Missing meta description")
    elif len(meta_description) > 160:
        findings.append("Meta description is longer than 160 characters (informational guideline)")
    if h1_count == 0:
        findings.append("Missing H1 heading")
    elif h1_count > 1:
        findings.append("Multiple H1 headings found; review the page structure")
    if images_missing_alt:
        findings.append(f"{images_missing_alt} image(s) have no alt attribute")
    if not viewport_present:
        findings.append("Missing viewport meta tag")

    return {
        "title": title,
        "title_length": len(title),
        "meta_description": meta_description,
        "meta_description_length": len(meta_description),
        "h1_count": h1_count,
        "h2_count": h2_count,
        "heading_count": headings,
        "paragraph_count": paragraphs,
        "word_count": len(words),
        "character_count": len(readable_text),
        "image_count": len(images),
        "images_missing_alt_count": images_missing_alt,
        "internal_link_count": internal_count,
        "external_link_count": external_count,
        "anchor_link_count": anchor_count,
        "empty_link_count": empty_count,
        "canonical_url": canonical,
        "meta_robots": meta_robots,
        "og_title": og_title,
        "og_description": og_description,
        "language": language,
        "viewport_present": viewport_present,
        "seo_findings": findings,
        "text_preview": readable_text[:1200],
        "links": links,
    }

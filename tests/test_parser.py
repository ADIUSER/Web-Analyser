from app.services.parser import parse_html


def test_parser_extracts_seo_content_and_classifies_links():
    html = """
    <!doctype html><html lang="en"><head><title>Example page</title>
    <meta name="description" content="A sample description"><meta name="viewport" content="width=device-width">
    <link rel="canonical" href="https://example.com/page"></head>
    <body><h1>Main heading</h1><h2>Subheading</h2><p>Hello useful world</p>
    <img src="/a.png"><img src="/b.png" alt="Bird">
    <a href="/about">About</a><a href="https://outside.example/page">Elsewhere</a>
    <a href="#content">Jump</a><a>Missing href</a>
    <script>these words should not count</script><style>.x{display:none}</style></body></html>
    """
    data = parse_html(html, "https://example.com/", "example.com")
    assert data["title"] == "Example page"
    assert data["title_length"] == len("Example page")
    assert data["meta_description"] == "A sample description"
    assert data["h1_count"] == 1
    assert data["h2_count"] == 1
    assert data["image_count"] == 2
    assert data["images_missing_alt_count"] == 1
    assert data["internal_link_count"] == 1
    assert data["external_link_count"] == 1
    assert data["anchor_link_count"] == 1
    assert data["empty_link_count"] == 1
    assert "these words" not in data["text_preview"]
    assert "Missing meta description" not in data["seo_findings"]
    assert data["viewport_present"] is True


def test_parser_handles_empty_malformed_html():
    data = parse_html("<div><h2>only heading", "https://example.com/", "example.com")
    assert data["title"] == ""
    assert data["h1_count"] == 0
    assert "Missing page title" in data["seo_findings"]
    assert "Missing H1 heading" in data["seo_findings"]

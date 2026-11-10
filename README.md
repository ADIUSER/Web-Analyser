# SiteScope — Website Analytics Dashboard

SiteScope is an educational Flask application that inspects publicly accessible website pages. It uses Requests for HTTP, BeautifulSoup for HTML parsing, SQLite/Flask-SQLAlchemy for scan history, Pandas for CSV export, Bootstrap for the interface, Chart.js for visualizations, and pytest for automated tests.

> **Scope:** This analyzes the content and HTTP responses of pages a crawler can access. It is **not** private visitor analytics, does not collect a site's visitor events, and does not measure browser Core Web Vitals.

## Features

- Homepage URL form with HTTP/HTTPS URL validation.
- Public-IP checks for all resolved IPv4/IPv6 addresses; rejects credentials, local/internal hostnames, non-public addresses, and non-standard ports.
- HTTP requests use a custom urllib3 connection class through Requests to pin connections to a validated public IP, avoiding a second DNS lookup for the TCP connection. TLS certificate verification remains enabled, and redirects are checked one hop at a time.
- Bounded breadth-first internal crawler with page/depth/time limits, duplicate prevention, a descriptive User-Agent, delay between requests, and robots.txt handling. If robots.txt cannot be safely retrieved (other than a normal 404/410), the crawler fails closed.
- SEO and content checks: title, description, headings, canonical/robots tags, Open Graph fields, language, viewport, images and missing alt attributes, word/character/paragraph counts, and internal/external links.
- Performance context: HTTP status, server-side response time, size, and redirect count.
- Optional bounded link checks, saved scan history, overview/SEO/link reports, client-side search/sorting/pagination/basic filters, and CSV export.
- CSV formula-injection mitigation and tests with mocked HTTP responses.

## Architecture

```text
website_analyzer/
├── app/
│   ├── __init__.py             # create_app(), config, error handlers, DB setup
│   ├── config.py               # compatibility import for root Config
│   ├── extensions.py           # SQLAlchemy extension
│   ├── models.py               # Scan, PageResult, LinkResult
│   ├── routes.py               # Flask pages, scan workflow, CSV endpoints
│   ├── services/
│   │   ├── url_validator.py    # URL parsing, DNS checks, normalization
│   │   ├── fetcher.py           # Requests + pinned connections + redirect controls
│   │   ├── parser.py            # HTML, content metrics, and link classification
│   │   ├── seo_analyzer.py      # Whole-scan SEO summaries
│   │   ├── crawler.py           # robots.txt, limits, queue and per-page analysis
│   │   └── exporter.py          # Pandas CSV export sanitization
│   ├── templates/              # Jinja templates for each report page
│   └── static/                 # CSS and JavaScript
├── tests/
├── instance/                   # local SQLite file is created here by Flask
├── config.py
├── run.py
├── requirements.txt
├── .env.example
└── README.md
```

## Database schema

- **Scan**: submitted and normalized URL, UTC creation timestamp, status, discovered/successful/failed page counts, and a safe summary error.
- **PageResult**: one row per attempted/discovered page, including requested/final URLs, HTTP/response metrics, SEO and content metrics, JSON findings, and a short text preview. Full HTML is not retained.
- **LinkResult**: source and destination URLs, classification, anchor text, and optional HTTP-check status. Foreign keys cascade when a scan is deleted, and indexes support common report queries.

The database is created automatically on application startup. With the default configuration, Flask-SQLAlchemy stores it at `instance/website_analyzer.db`.

## Prerequisites

- Python 3.10 or newer (Python 3.11+ recommended).
- pip and an internet connection for installing dependencies and scanning public sites.
- A current browser. Bootstrap and Chart.js load from public CDNs; an offline browser still has the server-side reports, but the page styling/charts may be reduced.

## Installation

### Windows (PowerShell)

```powershell
cd website_analyzer
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

If PowerShell blocks activation, use `\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `\.venv\Scripts\python.exe run.py` instead.

### macOS / Linux

```bash
cd website_analyzer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open <http://127.0.0.1:5000> in your browser. The server binds to loopback by default rather than exposing the scanner to the local network.

### Configure environment

Edit `.env` if desired. The application automatically loads a project-local `.env` file when present. Environment variables supplied by the shell take precedence. You can also set values in the shell before running:

- Windows PowerShell: `$env:SECRET_KEY="a-long-random-secret"; $env:MAX_PAGES="10"; python run.py`
- macOS/Linux: `export SECRET_KEY='a-long-random-secret'; export MAX_PAGES=10; python run.py`

Available settings (defaults shown):

| Setting | Default | Purpose |
|---|---:|---|
| `SECRET_KEY` | development-only value | Flask session signing; use a long random secret outside local development |
| `DATABASE_URL` | `sqlite:///website_analyzer.db` | SQLAlchemy database URL |
| `MAX_PAGES` | `20` | Maximum page attempts per scan (hard-capped at 100) |
| `MAX_DEPTH` | `2` | Maximum internal-link depth from the starting page (hard-capped at 5) |
| `REQUEST_DELAY_SECONDS` | `0.25` | Minimum delay between requests to the same host |
| `SCAN_TIMEOUT_SECONDS` | `60` | Scan wall-clock limit, checked between page/link operations |
| `REQUEST_CONNECT_TIMEOUT_SECONDS` | `5` | Connection timeout |
| `REQUEST_READ_TIMEOUT_SECONDS` | `10` | Read timeout |
| `MAX_RESPONSE_BYTES` | `2,000,000` | Maximum decompressed bytes read per HTML response |
| `MAX_ROBOTS_BYTES` | `262,144` | Maximum robots.txt body size |
| `MAX_LINK_CHECKS` | `30` | Maximum unique links checked when optional link checking is enabled |
| `MAX_LINKS_PER_PAGE` | `500` | Maximum link records retained per page |
| `MAX_LINK_RESULTS` | `2,000` | Maximum link records retained across a scan |
| `USER_AGENT` | `PortfolioWebsiteAnalyzer/1.0 ...` | Descriptive crawler User-Agent |

The app's default configuration permits HTTP only on port 80 and HTTPS only on port 443. This is an intentional safety boundary for the educational scanner; it excludes public websites running only on non-standard ports.

## Run and test

Start the application:

```bash
python run.py
```

Run the automated tests:

```bash
pytest -q
```

Most tests use mocked DNS and HTTP results, so routine tests do not depend on external websites. They test URL validation, private-address rejection, parsing, link classification, crawl bounds/deduplication, database persistence, route behavior, and CSV sanitization.

## Example sites

Try public sites such as:

- `https://example.com`
- `https://www.iana.org`
- `https://www.python.org`

A website may block automated fetches, require JavaScript, return a non-HTML response, change its content, or disallow crawling. A failure is a valid result and does not mean the target site is broken.

## How the metrics work

- **Pages discovered** counts attempted pages recorded during the bounded crawl, including failures and robots.txt skips. It is not a count of every page on the website.
- **Successful pages** counts HTTP 2xx/3xx pages whose HTML was parsed without a fetch-analysis error. HTTP error responses and skipped/failing requests are not successful pages.
- **Broken links** counts checked links returning HTTP 404 or 410; other HTTP errors are shown separately. A link that was not checked is not called broken.
- **Title/description/H1 findings** are simple document checks. Suggested character lengths are heuristics, not ranking guarantees.
- **Word count** is approximate: a regex counts word-like tokens in extracted text after scripts, styles, and similar non-content nodes are removed.
- **Response time** is measured by this Flask server for the request flow. It is not browser page-load time and is not a Core Web Vitals measure. LCP, CLS, and INP are not measured.
- **Duplicate titles/descriptions** are counted within the successfully analyzed pages of that scan; duplicates across pages beyond the crawl limits are not known.

## Crawling and robots.txt

The crawler begins at the submitted URL and follows same-host HTTP/HTTPS internal links up to the configured depth and page count. It deduplicates normalized URLs and does not fetch image/video/archive resources as crawl targets. It applies `robots.txt` for the starting host. If the robots file returns 404/410, it is treated as absent. If it is inaccessible, unsafe, oversized, or returns a non-success response other than 404/410, crawling is denied rather than assuming permission.

Robots rules are voluntary crawler guidance and not an access-control mechanism. This project does not bypass authentication, CAPTCHAs, paywalls, or anti-bot controls. Link checking is optional and capped; it only checks a small number of unique links.

## Security notes and limitations

- **Keep this app local.** It has no user authentication, CSRF integration, tenant isolation, distributed job queue, or production deployment hardening. Do not expose it as a public scanning service. A simple in-process semaphore limits concurrent scans to two per worker, but it is not a distributed queue.
- URL parsing rejects non-HTTP schemes, credentials, malformed hosts, private/reserved/non-global resolved IPs, local-only hostnames, and non-standard ports. Mixed DNS answers containing any non-public IP are rejected. Every redirect is revalidated, and every connection is pinned to a validated IP while preserving the original hostname for HTTP Host and TLS certificate verification.
- TLS verification is enabled. Proxy environment variables are ignored to avoid routing requests through an unexpected proxy. The connector closes response bodies and limits decompressed response bytes.
- DNS pinning reduces DNS-rebinding/time-of-check/time-of-use risk. This remains an educational implementation built on Requests/urllib3 internals; pinning behavior should be reviewed against your installed dependency versions before production use. The application cannot guarantee against every network-layer routing policy, compromised host, or operating-system networking configuration.
- Scan timeouts are checked between operations. A single blocking DNS resolution or socket read is bounded by library timeouts but can make actual wall time exceed the soft scan deadline slightly.
- CSV text that begins with spreadsheet formula characters (`=`, `+`, `-`, or `@`, including after whitespace/control characters) is prefixed with an apostrophe before export.
- Input and report strings are rendered with Jinja autoescaping. Do not treat analyzed site content as trusted instructions or executable code.
- Always obtain authorization before scanning sites and follow the target website's terms and applicable laws. Do not use this to probe private networks or overwhelm a site.

## Troubleshooting

- **Hostname cannot be resolved:** check the URL spelling and your DNS/network connection.
- **Destination rejected:** local, private, restricted, mixed private/public DNS, credentialed URLs, and non-standard ports are blocked intentionally.
- **robots.txt denied the scan:** check the target's crawl policy; do not attempt to bypass it.
- **TLS certificate verification failed:** ensure your system CA certificates and date/time are current. TLS verification is intentionally not disabled.
- **No HTML report:** the site may return a non-HTML content type, be unavailable, be too large, or block automated access.
- **Charts/CDN styles absent:** the dashboard uses CDN-hosted Bootstrap and Chart.js and needs network access for those assets.

## Project status

This archive contains the application source, HTML templates, JavaScript/CSS assets, tests, dependency list, and setup documentation. Test status should be based on the result of running `pytest -q` in your environment; don't assume success if the tests have not run on your machine.

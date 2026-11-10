"""Top-level configuration defaults. Environment variables override these values."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load project-local .env when present; environment variables still take precedence.
load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///website_analyzer.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 16 * 1024  # Request form body only.
    MAX_PAGES = int(os.getenv("MAX_PAGES", "20"))
    MAX_DEPTH = int(os.getenv("MAX_DEPTH", "2"))
    REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "0.25"))
    SCAN_TIMEOUT_SECONDS = int(os.getenv("SCAN_TIMEOUT_SECONDS", "60"))
    REQUEST_CONNECT_TIMEOUT_SECONDS = float(
        os.getenv("REQUEST_CONNECT_TIMEOUT_SECONDS", "5")
    )
    REQUEST_READ_TIMEOUT_SECONDS = float(os.getenv("REQUEST_READ_TIMEOUT_SECONDS", "10"))
    MAX_RESPONSE_BYTES = int(os.getenv("MAX_RESPONSE_BYTES", "2000000"))
    MAX_ROBOTS_BYTES = int(os.getenv("MAX_ROBOTS_BYTES", "262144"))
    MAX_LINK_CHECKS = int(os.getenv("MAX_LINK_CHECKS", "30"))
    MAX_LINKS_PER_PAGE = int(os.getenv("MAX_LINKS_PER_PAGE", "500"))
    MAX_LINK_RESULTS = int(os.getenv("MAX_LINK_RESULTS", "2000"))
    USER_AGENT = os.getenv(
        "USER_AGENT",
        "PortfolioWebsiteAnalyzer/1.0 (+local educational website analysis)",
    )
    # Restrict requests to the conventional web ports to reduce abuse potential.
    ALLOWED_HTTP_PORTS = (80,)
    ALLOWED_HTTPS_PORTS = (443,)
    MAX_REDIRECTS = 5

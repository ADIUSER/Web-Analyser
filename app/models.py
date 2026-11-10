from datetime import datetime, timezone

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Scan(db.Model):
    __tablename__ = "scans"

    id = db.Column(db.Integer, primary_key=True)
    submitted_url = db.Column(db.String(2048), nullable=False)
    normalized_start_url = db.Column(db.String(2048), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    status = db.Column(db.String(24), nullable=False, default="queued", index=True)
    discovered_pages = db.Column(db.Integer, nullable=False, default=0)
    successful_pages = db.Column(db.Integer, nullable=False, default=0)
    failed_pages = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.String(500))

    pages = db.relationship(
        "PageResult", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )
    links = db.relationship(
        "LinkResult", back_populates="scan", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self):
        return f"<Scan id={self.id} status={self.status!r}>"


class PageResult(db.Model):
    __tablename__ = "page_results"
    __table_args__ = (
        db.Index("ix_page_scan_status", "scan_id", "status_code"),
        db.Index("ix_page_scan_url", "scan_id", "requested_url"),
    )

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    requested_url = db.Column(db.String(2048), nullable=False)
    final_url = db.Column(db.String(2048))
    status_code = db.Column(db.Integer)
    response_time_ms = db.Column(db.Float)
    response_size_bytes = db.Column(db.Integer, nullable=False, default=0)
    redirect_count = db.Column(db.Integer, nullable=False, default=0)
    page_title = db.Column(db.Text)
    title_length = db.Column(db.Integer, nullable=False, default=0)
    meta_description = db.Column(db.Text)
    meta_description_length = db.Column(db.Integer, nullable=False, default=0)
    h1_count = db.Column(db.Integer, nullable=False, default=0)
    h2_count = db.Column(db.Integer, nullable=False, default=0)
    word_count = db.Column(db.Integer, nullable=False, default=0)
    character_count = db.Column(db.Integer, nullable=False, default=0)
    paragraph_count = db.Column(db.Integer, nullable=False, default=0)
    heading_count = db.Column(db.Integer, nullable=False, default=0)
    image_count = db.Column(db.Integer, nullable=False, default=0)
    images_missing_alt_count = db.Column(db.Integer, nullable=False, default=0)
    internal_link_count = db.Column(db.Integer, nullable=False, default=0)
    external_link_count = db.Column(db.Integer, nullable=False, default=0)
    canonical_url = db.Column(db.String(2048))
    meta_robots = db.Column(db.String(500))
    og_title = db.Column(db.String(1000))
    og_description = db.Column(db.Text)
    language = db.Column(db.String(40))
    viewport_present = db.Column(db.Boolean, nullable=False, default=False)
    seo_findings = db.Column(db.JSON, nullable=False, default=list)
    text_preview = db.Column(db.Text)
    error_message = db.Column(db.String(500))

    scan = db.relationship("Scan", back_populates="pages")

    @property
    def successful(self):
        return self.status_code is not None and 200 <= self.status_code < 400 and not self.error_message


class LinkResult(db.Model):
    __tablename__ = "link_results"
    __table_args__ = (
        db.Index("ix_link_scan_classification", "scan_id", "classification"),
        db.Index("ix_link_scan_status", "scan_id", "status_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    source_url = db.Column(db.String(2048), nullable=False)
    destination_url = db.Column(db.String(2048))
    classification = db.Column(db.String(24), nullable=False)
    anchor_text = db.Column(db.String(1000), nullable=False, default="")
    status_code = db.Column(db.Integer)
    check_result = db.Column(db.String(40), nullable=False, default="not_checked")
    checked = db.Column(db.Boolean, nullable=False, default=False)

    scan = db.relationship("Scan", back_populates="links")

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "MAX_PAGES": 5,
        "MAX_DEPTH": 1,
        "REQUEST_DELAY_SECONDS": 0,
        "SCAN_TIMEOUT_SECONDS": 10,
        "MAX_RESPONSE_BYTES": 100_000,
        "MAX_ROBOTS_BYTES": 10_000,
        "MAX_LINK_CHECKS": 2,
        "ALLOWED_HTTP_PORTS": (80,),
        "ALLOWED_HTTPS_PORTS": (443,),
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()

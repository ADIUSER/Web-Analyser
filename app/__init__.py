import logging
import os
from pathlib import Path

from flask import Flask, render_template
from sqlalchemy.exc import SQLAlchemyError

from config import Config
from .extensions import db


def create_app(test_config=None):
    """Application factory; accepts test settings for isolated pytest runs."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    from . import models  # noqa: F401 - register SQLAlchemy models
    from .routes import bp

    app.register_blueprint(bp)

    @app.errorhandler(413)
    def payload_too_large(_error):
        return render_template(
            "error.html",
            title="Request too large",
            message="The submitted form was too large. Please use a normal website URL.",
        ), 413

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        app.logger.exception("Unhandled application error")
        return render_template(
            "error.html",
            title="Something went wrong",
            message="The server could not complete the request. Please try again.",
        ), 500

    with app.app_context():
        try:
            db.create_all()
        except SQLAlchemyError:
            app.logger.exception("Could not initialize the database")
            raise

    return app

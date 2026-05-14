from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from models import db
from routes.admin import admin_bp
from routes.main import main_bp

csrf = CSRFProtect()


def _database_uri(instance_dir: Path) -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Some providers expose postgres://, while SQLAlchemy expects postgresql://.
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql://", 1)
        return database_url
    return f"sqlite:///{instance_dir / 'estimate_app.db'}"


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)
    base_dir = Path(__file__).resolve().parent
    instance_dir = base_dir / "instance"
    upload_dir = base_dir / "uploads"
    instance_dir.mkdir(exist_ok=True)
    upload_dir.mkdir(exist_ok=True)

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=_database_uri(instance_dir),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
        UPLOAD_FOLDER=str(upload_dir),
        ADMIN_USERNAME=os.getenv("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", "password"),
        MAIL_FROM=os.getenv("MAIL_FROM", "no-reply@example.com"),
        MAIL_TO=os.getenv("MAIL_TO", "sales@example.com"),
    )

    db.init_app(app)
    csrf.init_app(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    with app.app_context():
        db.create_all()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text

from models import db
from routes.admin import admin_bp
from routes.main import main_bp
from services.master_seed_service import seed_estimate_masters

csrf = CSRFProtect()


def _database_uri(instance_dir: Path) -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # Use psycopg v3 for Render/Neon compatibility, including newer Python runtimes.
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return database_url
    return f"sqlite:///{instance_dir / 'estimate_app.db'}"


def _ensure_tracking_columns() -> None:
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns("estimates")}
    is_postgres = db.engine.dialect.name.startswith("postgres")
    column_defs = {
        "visitor_key": "VARCHAR(40)",
        "referrer_url": "TEXT",
        "step_started_at": "TIMESTAMP" if is_postgres else "DATETIME",
        "step_device_at": "TIMESTAMP" if is_postgres else "DATETIME",
        "step_package_at": "TIMESTAMP" if is_postgres else "DATETIME",
        "step_custom_at": "TIMESTAMP" if is_postgres else "DATETIME",
        "step_result_at": "TIMESTAMP" if is_postgres else "DATETIME",
        "pdf_clicked_at": "TIMESTAMP" if is_postgres else "DATETIME",
        "pdf_click_count": "INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, column_type in column_defs.items():
        if column_name not in existing_columns:
            exists_clause = "IF NOT EXISTS " if is_postgres else ""
            db.session.execute(
                text(f"ALTER TABLE estimates ADD COLUMN {exists_clause}{column_name} {column_type}")
            )
    db.session.commit()


def _ensure_master_columns() -> None:
    inspector = inspect(db.engine)
    table_defs = {
        "feature_masters": {
            "category_name": "VARCHAR(80)",
            "description": "TEXT",
            "condition": "TEXT",
            "icon_file": "VARCHAR(255)",
        },
        "package_masters": {
            "price_label": "VARCHAR(120)",
            "image_file": "VARCHAR(255)",
            "image_alt": "VARCHAR(255)",
            "summary": "TEXT",
            "detail_title": "VARCHAR(120)",
            "modal_target": "VARCHAR(120)",
            "example": "TEXT",
        },
    }
    is_postgres = db.engine.dialect.name.startswith("postgres")
    for table_name, column_defs in table_defs.items():
        if not inspector.has_table(table_name):
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column_type in column_defs.items():
            if column_name not in existing_columns:
                exists_clause = "IF NOT EXISTS " if is_postgres else ""
                db.session.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {exists_clause}{column_name} {column_type}")
                )
    db.session.commit()


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
        ADMIN_PASSWORD=os.getenv("ADMIN_PASSWORD", "Evoltech999"),
        MAIL_FROM=os.getenv("MAIL_FROM", "no-reply@example.com"),
        MAIL_TO=os.getenv("MAIL_TO", "sales@example.com"),
        SMTP_HOST=os.getenv("SMTP_HOST", ""),
        SMTP_PORT=int(os.getenv("SMTP_PORT", "587")),
        SMTP_USERNAME=os.getenv("SMTP_USERNAME", ""),
        SMTP_PASSWORD=os.getenv("SMTP_PASSWORD", ""),
        SMTP_USE_TLS=os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"},
        SMTP_USE_SSL=os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"},
        LINEWORKS_WEBHOOK_URL=os.getenv("LINEWORKS_WEBHOOK_URL", ""),
        LINEWORKS_WEBHOOK_BEARER_TOKEN=os.getenv("LINEWORKS_WEBHOOK_BEARER_TOKEN", ""),
        LINEWORKS_WEBHOOK_TITLE=os.getenv("LINEWORKS_WEBHOOK_TITLE", "詳細見積り依頼"),
        LINEWORKS_WEBHOOK_PAYLOAD_STYLE=os.getenv("LINEWORKS_WEBHOOK_PAYLOAD_STYLE", "text"),
        LINEWORKS_WEBHOOK_TIMEOUT=int(os.getenv("LINEWORKS_WEBHOOK_TIMEOUT", "10")),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", ""),
        LINEWORKS_ADMIN_BASE_URL=os.getenv("LINEWORKS_ADMIN_BASE_URL", ""),
        COMPANY_NAME=os.getenv("COMPANY_NAME", "エボルテック株式会社 浜松開発センター"),
        COMPANY_ADDRESS=os.getenv(
            "COMPANY_ADDRESS",
            "〒435-0042 静岡県浜松市中央区篠ケ瀬町32",
        ),
        COMPANY_PHONE=os.getenv("COMPANY_PHONE", "053-401-6201"),
        COMPANY_EMAIL=os.getenv("COMPANY_EMAIL") or os.getenv("MAIL_TO") or "katayama-y@evoltech.co.jp",
    )

    db.init_app(app)
    csrf.init_app(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    with app.app_context():
        db.create_all()
        _ensure_master_columns()
        seed_estimate_masters()
        _ensure_tracking_columns()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

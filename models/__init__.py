from __future__ import annotations

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Estimate(db.Model):
    __tablename__ = "estimates"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    device_type = db.Column(db.String(50), nullable=False)
    package_type = db.Column(db.String(50), nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    visitor_key = db.Column(db.String(40))
    referrer_url = db.Column(db.Text)
    step_started_at = db.Column(db.DateTime)
    step_device_at = db.Column(db.DateTime)
    step_package_at = db.Column(db.DateTime)
    step_custom_at = db.Column(db.DateTime)
    step_result_at = db.Column(db.DateTime)
    pdf_clicked_at = db.Column(db.DateTime)
    pdf_click_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship("EstimateItem", backref="estimate", cascade="all, delete-orphan")
    inquiry = db.relationship("Inquiry", backref="estimate", uselist=False)


class EstimateItem(db.Model):
    __tablename__ = "estimate_items"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    estimate_id = db.Column(db.BigInteger, db.ForeignKey("estimates.id"), nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)


class Inquiry(db.Model):
    __tablename__ = "inquiries"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    estimate_id = db.Column(db.BigInteger, db.ForeignKey("estimates.id"), nullable=False)
    company_name = db.Column(db.String(120), nullable=False)
    person_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50))
    message = db.Column(db.Text)
    status = db.Column(db.String(30), default="未対応", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    attachments = db.relationship(
        "InquiryAttachment", backref="inquiry", cascade="all, delete-orphan"
    )


class InquiryAttachment(db.Model):
    __tablename__ = "inquiry_attachments"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    inquiry_id = db.Column(db.BigInteger, db.ForeignKey("inquiries.id"), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    box_file_id = db.Column(db.String(255))
    box_url = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

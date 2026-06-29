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


class DevicePriceMaster(db.Model):
    __tablename__ = "device_price_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    screen_unit_price = db.Column(db.Integer, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class PackageMaster(db.Model):
    __tablename__ = "package_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    screen_count = db.Column(db.Integer, nullable=False)
    price_label = db.Column(db.String(120))
    image_file = db.Column(db.String(255))
    image_alt = db.Column(db.String(255))
    summary = db.Column(db.Text)
    detail_title = db.Column(db.String(120))
    modal_target = db.Column(db.String(120))
    example = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    features = db.relationship(
        "PackageFeatureMaster",
        backref="package",
        cascade="all, delete-orphan",
    )
    display_items = db.relationship(
        "PackageDisplayItemMaster",
        backref="package",
        cascade="all, delete-orphan",
    )
    screen_definitions = db.relationship(
        "PackageScreenDefinitionMaster",
        backref="package",
        cascade="all, delete-orphan",
    )


class FeatureMaster(db.Model):
    __tablename__ = "feature_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    unit_price = db.Column(db.Integer, nullable=False)
    allow_quantity = db.Column(db.Boolean, default=False, nullable=False)
    category_name = db.Column(db.String(80))
    description = db.Column(db.Text)
    condition = db.Column(db.Text)
    icon_file = db.Column(db.String(255))
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    packages = db.relationship(
        "PackageFeatureMaster",
        backref="feature",
        cascade="all, delete-orphan",
    )


class PackageFeatureMaster(db.Model):
    __tablename__ = "package_feature_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    package_id = db.Column(db.BigInteger, db.ForeignKey("package_masters.id"), nullable=False)
    feature_id = db.Column(db.BigInteger, db.ForeignKey("feature_masters.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint("package_id", "feature_id", name="uq_package_feature_master"),
    )


class PackageDisplayItemMaster(db.Model):
    __tablename__ = "package_display_item_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    package_id = db.Column(db.BigInteger, db.ForeignKey("package_masters.id"), nullable=False)
    text = db.Column(db.String(255), nullable=False)
    is_section = db.Column(db.Boolean, default=False, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class PackageScreenDefinitionMaster(db.Model):
    __tablename__ = "package_screen_definition_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    package_id = db.Column(db.BigInteger, db.ForeignKey("package_masters.id"), nullable=False)
    section_title = db.Column(db.String(120))
    screen_name = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    feature_definitions = db.relationship(
        "PackageScreenFeatureDefinitionMaster",
        backref="screen_definition",
        cascade="all, delete-orphan",
    )


class PackageScreenFeatureDefinitionMaster(db.Model):
    __tablename__ = "package_screen_feature_definition_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    screen_definition_id = db.Column(
        db.BigInteger,
        db.ForeignKey("package_screen_definition_masters.id"),
        nullable=False,
    )
    label = db.Column(db.String(120), nullable=False)
    css_class = db.Column(db.String(80))
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

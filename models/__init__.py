from __future__ import annotations

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

SIMPLE_PLAN = "simple"
FULL_PLAN = "full"


class PlanMaster(db.Model):
    __tablename__ = "plan_masters"

    key = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_seeded = db.Column(db.Boolean, default=False, nullable=False)


def public_master_name(name: str) -> str:
    return name.split("::", 1)[1] if name.startswith(f"{FULL_PLAN}::") else name


def stored_master_name(plan_key: str, name: str) -> str:
    return f"{FULL_PLAN}::{name}" if plan_key == FULL_PLAN else name


class Estimate(db.Model):
    __tablename__ = "estimates"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    device_type = db.Column(db.String(50), nullable=False)
    package_type = db.Column(db.String(50), nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    maintenance_monthly_price = db.Column(db.Integer)
    maintenance_quote_required = db.Column(db.Boolean, default=False, nullable=False)
    plan_key = db.Column(db.String(20), default=SIMPLE_PLAN, nullable=False)
    step_plan_at = db.Column(db.DateTime)
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

    @property
    def has_quote_required_items(self) -> bool:
        return any(item.is_quote_required for item in self.items)

    @property
    def maintenance_price_label(self) -> str:
        return "要相談" if self.maintenance_quote_required else f"{self.maintenance_monthly_price or 0:,}円／月"


class EstimateItem(db.Model):
    __tablename__ = "estimate_items"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    estimate_id = db.Column(db.BigInteger, db.ForeignKey("estimates.id"), nullable=False)
    item_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    is_quote_required = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def price_label(self) -> str:
        return "要相談" if self.is_quote_required else f"{self.price:,}円"


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
    plan_key = db.Column(db.String(20), default=SIMPLE_PLAN, nullable=False)

    @property
    def public_name(self) -> str:
        return public_master_name(self.name)
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

    feature_prices = db.relationship(
        "FeatureDevicePriceMaster", backref="device", cascade="all, delete-orphan"
    )


class PackageMaster(db.Model):
    __tablename__ = "package_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    plan_key = db.Column(db.String(20), default=SIMPLE_PLAN, nullable=False)

    @property
    def public_name(self) -> str:
        return public_master_name(self.name)
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
    plan_key = db.Column(db.String(20), default=SIMPLE_PLAN, nullable=False)

    @property
    def public_name(self) -> str:
        return public_master_name(self.name)
    unit_price = db.Column(db.Integer, nullable=False)
    is_quote_required = db.Column(db.Boolean, default=False, nullable=False)
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

    device_prices = db.relationship(
        "FeatureDevicePriceMaster", backref="feature", cascade="all, delete-orphan"
    )


class FeatureDevicePriceMaster(db.Model):
    __tablename__ = "feature_device_price_masters"

    id = db.Column(db.BigInteger().with_variant(db.Integer, "sqlite"), primary_key=True)
    feature_id = db.Column(db.BigInteger, db.ForeignKey("feature_masters.id"), nullable=False)
    device_id = db.Column(db.BigInteger, db.ForeignKey("device_price_masters.id"), nullable=False)
    unit_price = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("feature_id", "device_id", name="uq_feature_device_price_master"),
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

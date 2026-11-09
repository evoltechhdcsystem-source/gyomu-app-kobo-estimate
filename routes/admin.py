from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from models import (
    DevicePriceMaster,
    Estimate,
    FeatureDevicePriceMaster,
    FeatureMaster,
    Inquiry,
    InquiryAttachment,
    PackageDisplayItemMaster,
    PackageFeatureMaster,
    PackageMaster,
    PackageScreenDefinitionMaster,
    PackageScreenFeatureDefinitionMaster,
    PlanMaster,
    SIMPLE_PLAN,
    stored_master_name,
    db,
)

from services.maintenance_service import GOOGLE_CLOUD_MONTHLY_MIN, monthly_total_label, monthly_total_note

admin_bp = Blueprint("admin", __name__)


@admin_bp.context_processor
def monthly_cost_context():
    return {
        "cloud_monthly_min": GOOGLE_CLOUD_MONTHLY_MIN,
        "monthly_total_label": monthly_total_label,
        "monthly_total_note": monthly_total_note,
    }


JST = timezone(timedelta(hours=9), "JST")
FEATURE_CATEGORY_OPTIONS = ["基本機能", "外部連携", "導入サポート"]
FEATURE_ICON_OPTIONS = [
    "feature-add.svg",
    "feature-ai.svg",
    "feature-attachment.svg",
    "feature-backup.svg",
    "feature-camera.svg",
    "feature-code-scan.svg",
    "feature-csv-export.svg",
    "feature-dashboard.svg",
    "feature-data-transform.svg",
    "feature-delete.svg",
    "feature-edit.svg",
    "feature-link.svg",
    "feature-login.svg",
    "feature-logs.svg",
    "feature-mail.svg",
    "feature-manual.svg",
    "feature-map.svg",
    "feature-network.svg",
    "feature-pdf-export.svg",
    "feature-permissions.svg",
    "feature-search.svg",
    "feature-server-maintenance.svg",
    "feature-store.svg",
    "feature-support.svg",
    "feature-onsite-support.svg",
    "feature-table.svg",
]
PACKAGE_IMAGE_OPTIONS = [
    "img/package-basic-generated.png",
    "img/package-operation-generated.png",
    "img/package-custom-generated.png",
]
PACKAGE_CHIP_CLASS_OPTIONS = ["is-create", "is-search", "is-edit", "is-delete"]


def admin_required():
    return session.get("admin_logged_in") is True


def format_jst(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def estimate_item_label(item_name: str) -> str:
    if " 画面単価 x " in item_name:
        return item_name.rsplit(" x ", 1)[-1]
    return item_name


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _form_bool(name: str) -> bool:
    return request.form.get(name) in {"1", "true", "on", "yes"}


def _form_anchor(default: str = "") -> str:
    return request.form.get("return_anchor", default).strip()


def _redirect_masters(anchor: str = ""):
    return redirect(url_for("admin.masters", plan=request.form.get("plan_key", SIMPLE_PLAN), _anchor=anchor or None))


def _commit_master_changes(success_message: str) -> bool:
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("同じ名前のマスターが既に存在します。名前を変更してください。", "danger")
        return False
    flash(success_message, "success")
    return True


def _modal_target_conflicts(modal_target: str, exclude_package_id: int | None = None) -> bool:
    if not modal_target:
        return False
    query = PackageMaster.query.filter(PackageMaster.modal_target == modal_target)
    query = query.filter(PackageMaster.plan_key == request.form.get("plan_key", SIMPLE_PLAN))
    if exclude_package_id is not None:
        query = query.filter(PackageMaster.id != exclude_package_id)
    return db.session.query(query.exists()).scalar()


def _validate_unique_modal_target(modal_target: str, exclude_package_id: int | None = None) -> bool:
    if not _modal_target_conflicts(modal_target, exclude_package_id):
        return True
    flash("モーダルIDは他のパックと重複できません。別のIDを入力してください。", "danger")
    return False


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin_login.html")

    if (
        request.form.get("username") == current_app.config["ADMIN_USERNAME"]
        and request.form.get("password") == current_app.config["ADMIN_PASSWORD"]
    ):
        session["admin_logged_in"] = True
        return redirect(url_for("admin.dashboard"))

    flash("ログイン情報が正しくありません。", "danger")
    return render_template("admin_login.html"), 401


@admin_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
def dashboard():
    if not admin_required():
        return redirect(url_for("admin.login"))
    counts = {
        "total": Inquiry.query.count(),
        "open": Inquiry.query.filter_by(status="未対応").count(),
        "done": Inquiry.query.filter_by(status="対応済み").count(),
        "estimates": Estimate.query.count(),
    }
    return render_template("admin_dashboard.html", counts=counts)


@admin_bp.get("/masters")
def masters():
    if not admin_required():
        return redirect(url_for("admin.login"))
    selected_plan = request.args.get("plan", SIMPLE_PLAN)
    plans = PlanMaster.query.all()
    if selected_plan not in {plan.key for plan in plans}:
        selected_plan = SIMPLE_PLAN
    device_prices = DevicePriceMaster.query.filter_by(plan_key=selected_plan).order_by(DevicePriceMaster.sort_order, DevicePriceMaster.id).all()
    packages = PackageMaster.query.filter_by(plan_key=selected_plan).order_by(PackageMaster.sort_order, PackageMaster.id).all()
    features = FeatureMaster.query.filter_by(plan_key=selected_plan).order_by(FeatureMaster.sort_order, FeatureMaster.id).all()
    screen_item_feature = next((row for row in features if row.public_name == "画面表示項目追加"), None)
    screen_item_device_prices = {
        row.device_id: row.unit_price
        for row in (screen_item_feature.device_prices if screen_item_feature else [])
    }
    package_features = (
        PackageFeatureMaster.query
        .join(PackageMaster)
        .join(FeatureMaster)
        .filter(PackageMaster.plan_key == selected_plan)
        .order_by(PackageMaster.sort_order, PackageFeatureMaster.sort_order, PackageFeatureMaster.id)
        .all()
    )
    package_display_items = (
        PackageDisplayItemMaster.query
        .join(PackageMaster)
        .filter(PackageMaster.plan_key == selected_plan)
        .order_by(PackageMaster.sort_order, PackageDisplayItemMaster.sort_order, PackageDisplayItemMaster.id)
        .all()
    )
    package_screen_definitions = (
        PackageScreenDefinitionMaster.query
        .join(PackageMaster)
        .filter(PackageMaster.plan_key == selected_plan)
        .order_by(PackageMaster.sort_order, PackageScreenDefinitionMaster.sort_order, PackageScreenDefinitionMaster.id)
        .all()
    )
    return render_template(
        "admin_masters.html",
        plans=plans,
        selected_plan=selected_plan,
        device_prices=device_prices,
        packages=packages,
        features=features,
        screen_item_feature=screen_item_feature,
        screen_item_device_prices=screen_item_device_prices,
        package_features=package_features,
        package_display_items=package_display_items,
        package_screen_definitions=package_screen_definitions,
        feature_category_options=FEATURE_CATEGORY_OPTIONS,
        feature_icon_options=FEATURE_ICON_OPTIONS,
        package_image_options=PACKAGE_IMAGE_OPTIONS,
        package_chip_class_options=PACKAGE_CHIP_CLASS_OPTIONS,
    )


@admin_bp.post("/masters/plans/<plan_key>")
def update_plan_master(plan_key: str):
    if not admin_required():
        return redirect(url_for("admin.login"))
    plan = db.session.get(PlanMaster, plan_key)
    if plan is None:
        abort(404)
    plan.name = request.form.get("name", "").strip() or plan.name
    plan.is_active = _form_bool("is_active")
    db.session.commit()
    flash("プラン設定を更新しました。", "success")
    return _redirect_masters("plan-settings")


@admin_bp.post("/masters/devices")
def create_device_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("端末名を入力してください。", "danger")
        return _redirect_masters(_form_anchor("device-prices"))
    db.session.add(
        DevicePriceMaster(
            name=stored_master_name(request.form.get("plan_key", SIMPLE_PLAN), name),
            plan_key=request.form.get("plan_key", SIMPLE_PLAN),
            screen_unit_price=max(_as_int(request.form.get("screen_unit_price")), 0),
            sort_order=_as_int(request.form.get("sort_order"), 100),
            is_active=_form_bool("is_active"),
        )
    )
    _commit_master_changes("端末単価マスターを追加しました。")
    return _redirect_masters(_form_anchor("device-prices"))


@admin_bp.post("/masters/devices/<int:master_id>")
def update_device_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = DevicePriceMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("端末単価マスターを削除しました。")
        return _redirect_masters(_form_anchor("device-prices"))
    master.name = stored_master_name(master.plan_key, request.form.get("name", "").strip() or master.public_name)
    master.screen_unit_price = max(_as_int(request.form.get("screen_unit_price")), 0)
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    _commit_master_changes("端末単価マスターを更新しました。")
    return _redirect_masters(_form_anchor("device-prices"))


@admin_bp.post("/masters/packages")
def create_package_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("パック名を入力してください。", "danger")
        return _redirect_masters(_form_anchor("packages"))
    modal_target = request.form.get("modal_target", "").strip()
    if not _validate_unique_modal_target(modal_target):
        return _redirect_masters(_form_anchor("packages"))
    db.session.add(
        PackageMaster(
            name=stored_master_name(request.form.get("plan_key", SIMPLE_PLAN), name),
            plan_key=request.form.get("plan_key", SIMPLE_PLAN),
            screen_count=max(_as_int(request.form.get("screen_count")), 0),
            price_label=request.form.get("price_label", "").strip(),
            image_file=request.form.get("image_file", "").strip(),
            image_alt=request.form.get("image_alt", "").strip(),
            summary=request.form.get("summary", "").strip(),
            detail_title=request.form.get("detail_title", "").strip(),
            modal_target=modal_target,
            example=request.form.get("example", "").strip(),
            sort_order=_as_int(request.form.get("sort_order"), 100),
            is_active=_form_bool("is_active"),
        )
    )
    _commit_master_changes("パックマスターを追加しました。")
    return _redirect_masters(_form_anchor("packages"))


@admin_bp.post("/masters/packages/<int:master_id>")
def update_package_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = PackageMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("パックマスターを削除しました。")
        return _redirect_masters(_form_anchor("packages"))
    requested_name = request.form.get("name", "").strip() or master.public_name
    if master.public_name in {"基本パック", "運用パック", "カスタムパック"} and requested_name != master.public_name:
        flash("標準パックの名前は変更できません。プランごとの内容は下のマスターから変更できます。", "danger")
        return _redirect_masters(_form_anchor("packages"))
    modal_target = request.form.get("modal_target", "").strip()
    if not _validate_unique_modal_target(modal_target, master.id):
        return _redirect_masters(_form_anchor("packages"))
    master.name = stored_master_name(master.plan_key, requested_name)
    master.screen_count = max(_as_int(request.form.get("screen_count")), 0)
    master.price_label = request.form.get("price_label", "").strip()
    master.image_file = request.form.get("image_file", "").strip()
    master.image_alt = request.form.get("image_alt", "").strip()
    master.summary = request.form.get("summary", "").strip()
    master.detail_title = request.form.get("detail_title", "").strip()
    master.modal_target = modal_target
    master.example = request.form.get("example", "").strip()
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    _commit_master_changes("パックマスターを更新しました。")
    return _redirect_masters(_form_anchor("packages"))


@admin_bp.post("/masters/features")
def create_feature_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    name = request.form.get("name", "").strip()
    if not name:
        flash("追加機能名を入力してください。", "danger")
        return _redirect_masters(_form_anchor("features"))
    db.session.add(
        FeatureMaster(
            name=stored_master_name(request.form.get("plan_key", SIMPLE_PLAN), name),
            plan_key=request.form.get("plan_key", SIMPLE_PLAN),
            unit_price=max(_as_int(request.form.get("unit_price")), 0),
            is_quote_required=_form_bool("is_quote_required"),
            allow_quantity=_form_bool("allow_quantity"),
            category_name=request.form.get("category_name", "").strip(),
            description=request.form.get("description", "").strip(),
            condition=request.form.get("condition", "").strip(),
            icon_file=request.form.get("icon_file", "").strip(),
            sort_order=_as_int(request.form.get("sort_order"), 100),
            is_active=_form_bool("is_active"),
        )
    )
    _commit_master_changes("追加機能マスターを追加しました。")
    return _redirect_masters(_form_anchor("features"))


@admin_bp.post("/masters/features/<int:master_id>")
def update_feature_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = FeatureMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("追加機能マスターを削除しました。")
        return _redirect_masters(_form_anchor("features"))
    device_prices_to_save: dict[int, int | None] = {}
    if master.public_name == "画面表示項目追加" and request.form.get("update_device_prices") == "1":
        devices = DevicePriceMaster.query.filter_by(plan_key=master.plan_key).all()
        for device in devices:
            price_text = request.form.get(f"device_price[{device.id}]")
            if price_text is None or (price_text.strip() and not price_text.strip().isdecimal()):
                flash("端末別単価は空欄、または0以上の整数で入力してください。", "danger")
                return _redirect_masters("features")
            device_prices_to_save[device.id] = int(price_text.strip()) if price_text.strip() else None
    master.name = stored_master_name(master.plan_key, request.form.get("name", "").strip() or master.public_name)
    master.unit_price = max(_as_int(request.form.get("unit_price")), 0)
    master.is_quote_required = _form_bool("is_quote_required")
    master.allow_quantity = _form_bool("allow_quantity")
    master.category_name = request.form.get("category_name", "").strip()
    master.description = request.form.get("description", "").strip()
    master.condition = request.form.get("condition", "").strip()
    master.icon_file = request.form.get("icon_file", "").strip()
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    if device_prices_to_save:
        existing_prices = {row.device_id: row for row in master.device_prices}
        for device_id, unit_price in device_prices_to_save.items():
            override = existing_prices.get(device_id)
            if unit_price is None:
                if override:
                    db.session.delete(override)
            elif override:
                override.unit_price = unit_price
            else:
                db.session.add(FeatureDevicePriceMaster(
                    feature_id=master.id, device_id=device_id, unit_price=unit_price,
                ))
    _commit_master_changes("追加機能マスターを更新しました。")
    return _redirect_masters(_form_anchor("features"))


@admin_bp.post("/masters/features/<int:feature_id>/devices/<int:device_id>/price")
def update_feature_device_price(feature_id: int, device_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    feature = FeatureMaster.query.get_or_404(feature_id)
    device = DevicePriceMaster.query.get_or_404(device_id)
    if feature.public_name != "画面表示項目追加" or feature.plan_key != device.plan_key:
        abort(404)
    anchor = "features"
    price_text = request.form.get("unit_price", "").strip()
    if price_text and not price_text.isdecimal():
        flash("端末別単価は0以上の整数で入力してください。", "danger")
        return _redirect_masters(anchor)
    override = FeatureDevicePriceMaster.query.filter_by(feature_id=feature.id, device_id=device.id).first()
    if not price_text:
        if override:
            db.session.delete(override)
    elif override:
        override.unit_price = int(price_text)
    else:
        db.session.add(FeatureDevicePriceMaster(
            feature_id=feature.id, device_id=device.id, unit_price=int(price_text),
        ))
    db.session.commit()
    flash("画面表示項目追加の端末別単価を更新しました。", "success")
    return _redirect_masters(anchor)


@admin_bp.post("/masters/package-features")
def create_package_feature_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    package_id = _as_int(request.form.get("package_id"))
    feature_id = _as_int(request.form.get("feature_id"))
    if not package_id or not feature_id:
        flash("パックと追加機能を選択してください。", "danger")
        return _redirect_masters(_form_anchor("package-features"))
    package = db.session.get(PackageMaster, package_id)
    feature = db.session.get(FeatureMaster, feature_id)
    if not package or not feature or package.plan_key != feature.plan_key or package.plan_key != request.form.get("plan_key"):
        flash("同じプランのパックと追加機能を選択してください。", "danger")
        return _redirect_masters(_form_anchor("package-features"))
    existing = PackageFeatureMaster.query.filter_by(package_id=package_id, feature_id=feature_id).first()
    if existing:
        existing.quantity = max(_as_int(request.form.get("quantity"), existing.quantity), 1)
        existing.sort_order = _as_int(request.form.get("sort_order"), existing.sort_order)
        success_message = "既存のパック内機能数を更新しました。"
    else:
        db.session.add(
            PackageFeatureMaster(
                package_id=package_id,
                feature_id=feature_id,
                quantity=max(_as_int(request.form.get("quantity"), 1), 1),
                sort_order=_as_int(request.form.get("sort_order"), 100),
            )
        )
        success_message = "パック内機能数を追加しました。"
    _commit_master_changes(success_message)
    return _redirect_masters(_form_anchor("package-features"))


@admin_bp.post("/masters/package-features/<int:master_id>")
def update_package_feature_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = PackageFeatureMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("パック内機能数を削除しました。")
        return _redirect_masters(_form_anchor("package-features"))
    master.quantity = max(_as_int(request.form.get("quantity"), master.quantity), 1)
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    _commit_master_changes("パック内機能数を更新しました。")
    return _redirect_masters(_form_anchor("package-features"))


@admin_bp.post("/masters/package-display-items")
def create_package_display_item_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    package_id = _as_int(request.form.get("package_id"))
    text = request.form.get("text", "").strip()
    if not package_id or not text:
        flash("パックと表示文言を入力してください。", "danger")
        return _redirect_masters(_form_anchor("package-display-items"))
    db.session.add(
        PackageDisplayItemMaster(
            package_id=package_id,
            text=text,
            is_section=_form_bool("is_section"),
            sort_order=_as_int(request.form.get("sort_order"), 100),
            is_active=_form_bool("is_active"),
        )
    )
    _commit_master_changes("パック表示項目を追加しました。")
    return _redirect_masters(_form_anchor("package-display-items"))


@admin_bp.post("/masters/package-display-items/<int:master_id>")
def update_package_display_item_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = PackageDisplayItemMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("パック表示項目を削除しました。")
        return _redirect_masters(_form_anchor("package-display-items"))
    master.text = request.form.get("text", "").strip() or master.text
    master.is_section = _form_bool("is_section")
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    _commit_master_changes("パック表示項目を更新しました。")
    return _redirect_masters(_form_anchor("package-display-items"))


@admin_bp.post("/masters/package-screen-definitions")
def create_package_screen_definition_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    package_id = _as_int(request.form.get("package_id"))
    screen_name = request.form.get("screen_name", "").strip()
    if not package_id or not screen_name:
        flash("パックと画面名を入力してください。", "danger")
        return _redirect_masters(_form_anchor("package-screen-definitions"))
    db.session.add(
        PackageScreenDefinitionMaster(
            package_id=package_id,
            section_title=request.form.get("section_title", "").strip(),
            screen_name=screen_name,
            sort_order=_as_int(request.form.get("sort_order"), 100),
            is_active=_form_bool("is_active"),
        )
    )
    _commit_master_changes("標準画面定義を追加しました。")
    return _redirect_masters(_form_anchor("package-screen-definitions"))


@admin_bp.post("/masters/package-screen-definitions/<int:master_id>")
def update_package_screen_definition_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = PackageScreenDefinitionMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("標準画面定義を削除しました。")
        return _redirect_masters(_form_anchor("package-screen-definitions"))
    master.section_title = request.form.get("section_title", "").strip()
    master.screen_name = request.form.get("screen_name", "").strip() or master.screen_name
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    _commit_master_changes("標準画面定義を更新しました。")
    return _redirect_masters(_form_anchor("package-screen-definitions"))


@admin_bp.post("/masters/package-screen-features")
def create_package_screen_feature_definition_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    screen_definition_id = _as_int(request.form.get("screen_definition_id"))
    label = request.form.get("label", "").strip()
    if not screen_definition_id or not label:
        flash("画面定義と付属機能名を入力してください。", "danger")
        return _redirect_masters(_form_anchor("package-screen-features"))
    db.session.add(
        PackageScreenFeatureDefinitionMaster(
            screen_definition_id=screen_definition_id,
            label=label,
            css_class=request.form.get("css_class", "").strip(),
            sort_order=_as_int(request.form.get("sort_order"), 100),
            is_active=_form_bool("is_active"),
        )
    )
    _commit_master_changes("付属機能表示を追加しました。")
    return _redirect_masters(_form_anchor("package-screen-features"))


@admin_bp.post("/masters/package-screen-features/<int:master_id>")
def update_package_screen_feature_definition_master(master_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    master = PackageScreenFeatureDefinitionMaster.query.get_or_404(master_id)
    if request.form.get("delete") == "1":
        db.session.delete(master)
        _commit_master_changes("付属機能表示を削除しました。")
        return _redirect_masters(_form_anchor("package-screen-features"))
    master.label = request.form.get("label", "").strip() or master.label
    master.css_class = request.form.get("css_class", "").strip()
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    _commit_master_changes("付属機能表示を更新しました。")
    return _redirect_masters(_form_anchor("package-screen-features"))


@admin_bp.get("/estimates")
def estimates():
    if not admin_required():
        return redirect(url_for("admin.login"))
    query = Estimate.query
    keyword = request.args.get("q", "").strip()
    plan_key = request.args.get("plan", "").strip()
    package_type = request.args.get("package", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    if keyword:
        conditions = [Estimate.visitor_key.ilike(f"%{keyword}%"), Estimate.device_type.ilike(f"%{keyword}%")]
        if keyword.lstrip("#").isdigit():
            conditions.append(Estimate.id == int(keyword.lstrip("#")))
        query = query.filter(or_(*conditions))
    if plan_key:
        query = query.filter(Estimate.plan_key == plan_key)
    if package_type:
        query = query.filter(Estimate.package_type == package_type)
    for value, is_start in ((date_from, True), (date_to, False)):
        try:
            local_day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=JST)
        except ValueError:
            continue
        cutoff = local_day.astimezone(UTC).replace(tzinfo=None)
        query = query.filter(Estimate.created_at >= cutoff if is_start else Estimate.created_at < cutoff + timedelta(days=1))
    rows = query.order_by(Estimate.created_at.desc()).all()
    standard_packages = ["基本パック", "運用パック", "カスタムパック"]
    master_package_names = {package.public_name for package in PackageMaster.query.all()}
    historical_package_names = {
        name for (name,) in db.session.query(Estimate.package_type).distinct().all() if name
    }
    other_package_names = sorted((master_package_names | historical_package_names) - set(standard_packages) - {"未選択"})
    package_options = standard_packages + other_package_names
    if "未選択" in historical_package_names:
        package_options.append("未選択")
    return render_template(
        "admin_estimates.html",
        estimates=rows,
        package_options=package_options,
        plans=PlanMaster.query.all(),
        plan_names={plan.key: plan.name for plan in PlanMaster.query.all()},
        filters={"q": keyword, "plan": plan_key, "package": package_type, "from": date_from, "to": date_to},
        format_jst=format_jst,
        estimate_item_label=estimate_item_label,
    )


@admin_bp.get("/inquiries")
def inquiries():
    if not admin_required():
        return redirect(url_for("admin.login"))
    rows = Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    return render_template("admin_inquiries.html", inquiries=rows, format_jst=format_jst)


@admin_bp.route("/inquiries/<int:inquiry_id>", methods=["GET", "POST"])
def inquiry_detail(inquiry_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    inquiry = Inquiry.query.get_or_404(inquiry_id)
    back_to = request.args.get("from")
    back_url = url_for("admin.estimates") if back_to == "estimates" else url_for("admin.inquiries")
    back_label = "見積り履歴一覧へ戻る" if back_to == "estimates" else "一覧へ戻る"
    if request.method == "POST":
        inquiry.status = request.form.get("status", inquiry.status)
        db.session.commit()
        flash("ステータスを更新しました。", "success")
    return render_template(
        "admin_inquiry_detail.html",
        inquiry=inquiry,
        back_url=back_url,
        back_label=back_label,
    )


@admin_bp.get("/inquiries/<int:inquiry_id>/attachments/<int:attachment_id>/download")
def download_inquiry_attachment(inquiry_id: int, attachment_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))

    attachment = InquiryAttachment.query.filter_by(id=attachment_id, inquiry_id=inquiry_id).first_or_404()
    if not attachment.box_url:
        abort(404)

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    file_path = Path(attachment.box_url).resolve()

    if upload_root not in file_path.parents and file_path != upload_root:
        current_app.logger.warning(
            "Blocked attachment download outside upload folder: attachment_id=%s path=%s",
            attachment.id,
            file_path,
        )
        abort(404)

    if not file_path.is_file():
        abort(404)

    return send_file(
        file_path,
        as_attachment=True,
        download_name=attachment.file_name,
    )


@admin_bp.get("/inquiries.csv")
def export_csv():
    if not admin_required():
        return redirect(url_for("admin.login"))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "会社名", "担当者名", "メール", "電話番号", "ステータス", "初期費用（税抜）", "作成日時", "サーバー保守（月額・税抜）"])
    for inquiry in Inquiry.query.order_by(Inquiry.created_at.desc()).all():
        writer.writerow(
            [
                inquiry.id,
                inquiry.company_name,
                inquiry.person_name,
                inquiry.email,
                inquiry.phone or "",
                inquiry.status,
                inquiry.estimate.total_price,
                format_jst(inquiry.created_at),
                inquiry.estimate.maintenance_price_label if inquiry.estimate.maintenance_monthly_price is not None else "未選択",
            ]
        )

    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inquiries.csv"},
    )

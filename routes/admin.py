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

from models import (
    DevicePriceMaster,
    Estimate,
    FeatureMaster,
    Inquiry,
    InquiryAttachment,
    PackageDisplayItemMaster,
    PackageFeatureMaster,
    PackageMaster,
    PackageScreenDefinitionMaster,
    PackageScreenFeatureDefinitionMaster,
    db,
)

admin_bp = Blueprint("admin", __name__)
JST = timezone(timedelta(hours=9), "JST")
FEATURE_CATEGORY_OPTIONS = ["基本機能", "外部連携", "導入サポート"]
FEATURE_ICON_OPTIONS = [
    "feature-add.svg",
    "feature-ai.svg",
    "feature-backup.svg",
    "feature-delete.svg",
    "feature-edit.svg",
    "feature-link.svg",
    "feature-login.svg",
    "feature-mail.svg",
    "feature-manual.svg",
    "feature-search.svg",
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
    return redirect(url_for("admin.masters", _anchor=anchor or None))


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
    device_prices = DevicePriceMaster.query.order_by(DevicePriceMaster.sort_order, DevicePriceMaster.id).all()
    packages = PackageMaster.query.order_by(PackageMaster.sort_order, PackageMaster.id).all()
    features = FeatureMaster.query.order_by(FeatureMaster.sort_order, FeatureMaster.id).all()
    package_features = (
        PackageFeatureMaster.query
        .join(PackageMaster)
        .join(FeatureMaster)
        .order_by(PackageMaster.sort_order, PackageFeatureMaster.sort_order, PackageFeatureMaster.id)
        .all()
    )
    package_display_items = (
        PackageDisplayItemMaster.query
        .join(PackageMaster)
        .order_by(PackageMaster.sort_order, PackageDisplayItemMaster.sort_order, PackageDisplayItemMaster.id)
        .all()
    )
    package_screen_definitions = (
        PackageScreenDefinitionMaster.query
        .join(PackageMaster)
        .order_by(PackageMaster.sort_order, PackageScreenDefinitionMaster.sort_order, PackageScreenDefinitionMaster.id)
        .all()
    )
    return render_template(
        "admin_masters.html",
        device_prices=device_prices,
        packages=packages,
        features=features,
        package_features=package_features,
        package_display_items=package_display_items,
        package_screen_definitions=package_screen_definitions,
        feature_category_options=FEATURE_CATEGORY_OPTIONS,
        feature_icon_options=FEATURE_ICON_OPTIONS,
        package_image_options=PACKAGE_IMAGE_OPTIONS,
        package_chip_class_options=PACKAGE_CHIP_CLASS_OPTIONS,
    )


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
            name=name,
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
    master.name = request.form.get("name", "").strip() or master.name
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
            name=name,
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
    modal_target = request.form.get("modal_target", "").strip()
    if not _validate_unique_modal_target(modal_target, master.id):
        return _redirect_masters(_form_anchor("packages"))
    master.name = request.form.get("name", "").strip() or master.name
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
            name=name,
            unit_price=max(_as_int(request.form.get("unit_price")), 0),
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
    master.name = request.form.get("name", "").strip() or master.name
    master.unit_price = max(_as_int(request.form.get("unit_price")), 0)
    master.allow_quantity = _form_bool("allow_quantity")
    master.category_name = request.form.get("category_name", "").strip()
    master.description = request.form.get("description", "").strip()
    master.condition = request.form.get("condition", "").strip()
    master.icon_file = request.form.get("icon_file", "").strip()
    master.sort_order = _as_int(request.form.get("sort_order"), master.sort_order)
    master.is_active = _form_bool("is_active")
    _commit_master_changes("追加機能マスターを更新しました。")
    return _redirect_masters(_form_anchor("features"))


@admin_bp.post("/masters/package-features")
def create_package_feature_master():
    if not admin_required():
        return redirect(url_for("admin.login"))
    package_id = _as_int(request.form.get("package_id"))
    feature_id = _as_int(request.form.get("feature_id"))
    if not package_id or not feature_id:
        flash("パックと追加機能を選択してください。", "danger")
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
    rows = Estimate.query.order_by(Estimate.created_at.desc()).all()
    return render_template(
        "admin_estimates.html",
        estimates=rows,
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
    writer.writerow(["ID", "会社名", "担当者名", "メール", "電話番号", "ステータス", "見積り金額", "作成日時"])
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
            ]
        )

    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inquiries.csv"},
    )

from __future__ import annotations

import hashlib
from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from models import Estimate, EstimateItem, Inquiry, InquiryAttachment, db
from services.box_service import allowed_file, upload_to_box
from services.estimate_display_service import (
    custom_feature_categories,
    estimate_feature_name,
    estimate_item_condition,
    estimate_item_label,
    feature_conditions,
    feature_descriptions,
    feature_icon_files,
    is_screen_count_item,
    screen_descriptions,
)
from services.estimate_pdf_service import build_estimate_pdf, estimate_pdf_download_name
from services.estimate_service import (
    calculate_estimate,
    device_prices,
    feature_prices,
    feature_prices_for_device,
    multiple_features,
    package_feature_total,
    package_feature_quantities,
    package_features,
    package_screens,
)
from services.mail_service import send_inquiry_mails
from services.lineworks_service import send_lineworks_webhook_notification
from services.package_display_service import package_choice_cards, package_screen_definitions_by_package

main_bp = Blueprint("main", __name__)
STEP_FIELDS = {
    "started": "step_started_at",
    "device": "step_device_at",
    "package": "step_package_at",
    "custom": "step_custom_at",
    "result": "step_result_at",
}


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> datetime:
    return datetime.utcnow()


def _record_pdf_click(estimate: Estimate) -> None:
    if not estimate.pdf_clicked_at:
        estimate.pdf_clicked_at = _now()
    estimate.pdf_click_count = (estimate.pdf_click_count or 0) + 1
    db.session.commit()


def _capture_referrer(flow: dict) -> None:
    if flow.get("referrer_url") or not request.referrer:
        return
    if request.referrer.startswith(request.host_url):
        return
    flow["referrer_url"] = request.referrer[:2000]


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or ""


def _visitor_key() -> str:
    source = "|".join(
        [
            _client_ip(),
            request.headers.get("User-Agent", ""),
            request.headers.get("Accept-Language", ""),
        ]
    )
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return f"u-{digest}"


def _flow_estimate(flow: dict) -> Estimate | None:
    estimate_id = flow.get("estimate_id")
    if not estimate_id:
        return None
    return Estimate.query.get(estimate_id)


def _ensure_flow_estimate(flow: dict) -> Estimate:
    estimate = _flow_estimate(flow)
    if estimate is None:
        estimate = Estimate(device_type="未選択", package_type="未選択", total_price=0)
        db.session.add(estimate)
        db.session.flush()
        flow["estimate_id"] = estimate.id
    if not estimate.visitor_key:
        estimate.visitor_key = _visitor_key()
    if flow.get("referrer_url") and not estimate.referrer_url:
        estimate.referrer_url = flow["referrer_url"]
    return estimate


def _touch_flow_step(flow: dict, step_key: str) -> dict:
    _capture_referrer(flow)
    step_times = flow.setdefault("step_times", {})
    step_times.setdefault(step_key, _now().isoformat())
    estimate = _ensure_flow_estimate(flow)
    field_name = STEP_FIELDS.get(step_key)
    tracked_at = _flow_time(flow, step_key)
    if field_name and tracked_at and not getattr(estimate, field_name):
        setattr(estimate, field_name, tracked_at)
    db.session.commit()
    session["estimate_flow"] = flow
    return flow


def _flow_time(flow: dict, step_key: str) -> datetime | None:
    value = (flow.get("step_times") or {}).get(step_key)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _apply_tracking_to_estimate(estimate: Estimate, flow: dict) -> None:
    estimate.referrer_url = flow.get("referrer_url")
    for step_key, field_name in STEP_FIELDS.items():
        tracked_at = _flow_time(flow, step_key)
        if tracked_at and not getattr(estimate, field_name):
            setattr(estimate, field_name, tracked_at)


def _estimate_flow_total(flow: dict | None, default_custom_screens: int = 0) -> int:
    if not flow or not flow.get("device_type"):
        return 0

    package_type = flow.get("package_type")
    if not package_type:
        return 0

    custom_screens = _as_int(flow.get("custom_screens"), default_custom_screens)
    features = flow.get("features", [])
    feature_quantities = flow.get("feature_quantities", {})
    result = calculate_estimate(
        flow["device_type"],
        package_type,
        custom_screens,
        features,
        feature_quantities,
    )
    return result["total_price"]


def _estimate_status(active_step: str, flow: dict | None = None, estimate: Estimate | None = None):
    package_type = estimate.package_type if estimate else None
    if not package_type and flow:
        package_type = flow.get("package_type")
    uses_custom = package_type == "カスタムパック"

    steps = [
        {"key": "top", "label": "スタート"},
        {"key": "device", "label": "利用端末"},
        {"key": "package", "label": "パック選択"},
    ]
    if uses_custom:
        steps.append({"key": "custom", "label": "機能追加"})
    steps.extend(
        [
            {"key": "result", "label": "見積り結果"},
        ]
    )
    if active_step in {"result", "inquiry"}:
        steps.append({"key": "inquiry", "label": "問合せ、詳細お見積り"})

    current_index = next(
        (index for index, step in enumerate(steps) if step["key"] == active_step),
        len(steps) - 1,
    )
    for index, step in enumerate(steps):
        if index < current_index:
            step["state"] = "done"
        elif index == current_index:
            step["state"] = "active"
        else:
            step["state"] = "pending"

    if current_index > 0:
        steps[0]["href"] = url_for("main.index")
    if current_index > 1:
        steps[1]["href"] = url_for("main.device_select")
    if current_index > 2:
        steps[2]["href"] = url_for("main.package_select")
    if uses_custom and current_index > 3:
        steps[3]["href"] = url_for("main.custom_estimate")
    result_index = next((index for index, step in enumerate(steps) if step["key"] == "result"), None)
    if result_index is not None and current_index > result_index and estimate:
        steps[result_index]["href"] = url_for("main.estimate_result", estimate_id=estimate.id)

    total_price = estimate.total_price if estimate else _estimate_flow_total(flow, 1 if active_step == "custom" else 0)
    return {"steps": steps, "total_price": total_price}


def _save_estimate_and_redirect(flow: dict):
    device_type = flow["device_type"]
    package_type = flow["package_type"]
    selected_features = flow.get("features", [])
    feature_quantities = flow.get("feature_quantities", {})
    custom_screens = int(flow.get("custom_screens") or 0)

    result = calculate_estimate(
        device_type,
        package_type,
        custom_screens,
        selected_features,
        feature_quantities,
    )
    flow = _touch_flow_step(flow, "result")
    estimate = _flow_estimate(flow)
    if estimate is None:
        estimate = Estimate(device_type="未選択", package_type="未選択", total_price=0)
        db.session.add(estimate)
        db.session.flush()
    else:
        EstimateItem.query.filter_by(estimate_id=estimate.id).delete()

    estimate.device_type = result["device_type"]
    estimate.package_type = result["package_type"]
    estimate.total_price = result["total_price"]
    if not estimate.visitor_key:
        estimate.visitor_key = _visitor_key()
    _apply_tracking_to_estimate(estimate, flow)

    for item in result["items"]:
        db.session.add(
            EstimateItem(estimate_id=estimate.id, item_name=item["name"], price=item["price"])
        )
    db.session.commit()
    flow["estimate_id"] = estimate.id
    session["estimate_flow"] = flow
    session["estimate_back_endpoint"] = (
        "main.custom_estimate" if package_type == "カスタムパック" else "main.package_select"
    )

    return redirect(url_for("main.estimate_result", estimate_id=estimate.id))


def _current_or_estimate_device(estimate: Estimate) -> str:
    flow = session.get("estimate_flow") or {}
    return flow.get("device_type") or estimate.device_type


@main_bp.get("/")
def index():
    flow = session.get("estimate_flow") or {}
    if flow.get("estimate_id"):
        flow = {}
    _touch_flow_step(flow, "started")
    return render_template("index.html", estimate_status=_estimate_status("top"))


@main_bp.route("/device", methods=["GET", "POST"])
def device_select():
    flow = session.get("estimate_flow") or {}
    flow = _touch_flow_step(flow, "device")

    if request.method == "GET":
        return render_template(
            "device_select.html",
            device_prices=device_prices(),
            estimate_status=_estimate_status("device"),
        )

    device_type = request.form.get("device_type", "")
    current_device_prices = device_prices()
    if device_type not in current_device_prices:
        flash("端末を選ぶと次へ進めます。3つの中から1つ選択してください。", "danger")
        return render_template(
            "device_select.html",
            device_prices=current_device_prices,
            estimate_status=_estimate_status("device"),
        ), 400

    flow["device_type"] = device_type
    estimate = _ensure_flow_estimate(flow)
    estimate.device_type = device_type
    db.session.commit()
    session["estimate_flow"] = flow
    return redirect(url_for("main.package_select"))


@main_bp.route("/package", methods=["GET", "POST"])
def package_select():
    flow = session.get("estimate_flow")
    if not flow or not flow.get("device_type"):
        return redirect(url_for("main.device_select"))
    flow = _touch_flow_step(flow, "package")

    if request.method == "GET":
        return render_template(
            "package_select.html",
            package_screens=package_screens(),
            package_feature_total=package_feature_total,
            package_choice_cards=package_choice_cards(),
            package_screen_definitions=package_screen_definitions_by_package(),
            device_prices=device_prices(),
            flow=flow,
            estimate_status=_estimate_status("package", flow),
        )

    package_type = request.form.get("package_type", "")
    current_package_screens = package_screens()
    if package_type not in current_package_screens:
        flash("パックを選ぶと次へ進めます。現場で使いたい内容に近いパックを1つ選択してください。", "danger")
        return render_template(
            "package_select.html",
            package_screens=current_package_screens,
            package_feature_total=package_feature_total,
            package_choice_cards=package_choice_cards(),
            package_screen_definitions=package_screen_definitions_by_package(),
            device_prices=device_prices(),
            flow=flow,
            estimate_status=_estimate_status("package", flow),
        ), 400

    previous_package_type = flow.get("package_type")
    if previous_package_type != package_type:
        flow.pop("custom_screens", None)
    flow["package_type"] = package_type
    flow["features"] = package_features(package_type)
    flow["feature_quantities"] = package_feature_quantities(package_type)
    estimate = _ensure_flow_estimate(flow)
    estimate.device_type = flow["device_type"]
    estimate.package_type = package_type
    db.session.commit()
    session["estimate_flow"] = flow
    if package_type == "カスタムパック":
        return redirect(url_for("main.custom_estimate"))
    return _save_estimate_and_redirect(flow)


@main_bp.route("/custom", methods=["GET", "POST"])
def custom_estimate():
    flow = session.get("estimate_flow")
    if not flow or not flow.get("device_type"):
        return redirect(url_for("main.device_select"))
    if flow.get("package_type") != "カスタムパック":
        return redirect(url_for("main.package_select"))

    flow = _touch_flow_step(flow, "custom")

    if request.method == "GET":
        return render_template(
            "custom_estimate.html",
            feature_prices=feature_prices_for_device(flow["device_type"]),
            feature_categories=custom_feature_categories(flow["device_type"]),
            feature_descriptions=feature_descriptions(),
            feature_conditions=feature_conditions(),
            feature_icon_files=feature_icon_files(),
            multiple_feature_names=multiple_features(),
            device_prices=device_prices(),
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        )

    custom_screens = int(request.form.get("custom_screens") or 0)
    if custom_screens < 1:
        flash("画面数を入力してください。1以上の数字で入力すると見積りできます。", "danger")
        return render_template(
            "custom_estimate.html",
            feature_prices=feature_prices_for_device(flow["device_type"]),
            feature_categories=custom_feature_categories(flow["device_type"]),
            feature_descriptions=feature_descriptions(),
            feature_conditions=feature_conditions(),
            feature_icon_files=feature_icon_files(),
            multiple_feature_names=multiple_features(),
            device_prices=device_prices(),
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        ), 400

    selected_features = [
        feature for feature in request.form.getlist("features") if feature in feature_prices()
    ]
    feature_quantities = {}
    current_multiple_features = multiple_features()
    for feature in selected_features:
        quantity = _as_int(request.form.get(f"feature_quantities[{feature}]"), 1)
        feature_quantities[feature] = max(quantity, 1) if feature in current_multiple_features else 1

    if not selected_features:
        flash("追加機能を選ぶと結果へ進めます。必要な機能を1つ以上選択してください。", "danger")
        flow["custom_screens"] = custom_screens
        flow["features"] = []
        flow["feature_quantities"] = {}
        session["estimate_flow"] = flow
        return render_template(
            "custom_estimate.html",
            feature_prices=feature_prices_for_device(flow["device_type"]),
            feature_categories=custom_feature_categories(flow["device_type"]),
            feature_descriptions=feature_descriptions(),
            feature_conditions=feature_conditions(),
            feature_icon_files=feature_icon_files(),
            multiple_feature_names=current_multiple_features,
            device_prices=device_prices(),
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        ), 400

    flow["custom_screens"] = custom_screens
    flow["features"] = selected_features
    flow["feature_quantities"] = feature_quantities
    session["estimate_flow"] = flow
    return _save_estimate_and_redirect(flow)


@main_bp.post("/estimate")
def create_estimate():
    return redirect(url_for("main.device_select"))


@main_bp.get("/estimate/<int:estimate_id>")
def estimate_result(estimate_id: int):
    estimate = Estimate.query.get_or_404(estimate_id)
    if not estimate.step_result_at:
        estimate.step_result_at = _now()
        db.session.commit()
    flow = session.get("estimate_flow")
    back_endpoint = (
        "main.custom_estimate"
        if estimate.package_type == "カスタムパック"
        else "main.package_select"
    )
    back_labels = {
        "main.package_select": "パック選択へ戻る",
        "main.custom_estimate": "機能選択へ戻る",
        "main.device_select": "端末選択へ戻る",
    }
    return render_template(
        "estimate_result.html",
        estimate=estimate,
        estimate_status=_estimate_status("result", flow, estimate),
        back_url=url_for(back_endpoint),
        back_label=back_labels.get(back_endpoint, "前の画面へ戻る"),
        estimate_item_label=estimate_item_label,
        estimate_feature_name=estimate_feature_name,
        estimate_item_condition=estimate_item_condition,
        is_screen_count_item=is_screen_count_item,
        feature_descriptions=feature_descriptions(),
        feature_conditions=feature_conditions(),
        screen_descriptions=screen_descriptions(),
        package_screen_definitions=package_screen_definitions_by_package(),
    )


@main_bp.post("/estimate/<int:estimate_id>/custom")
def start_custom_from_estimate(estimate_id: int):
    estimate = Estimate.query.get_or_404(estimate_id)
    flow = session.get("estimate_flow") or {}
    session["estimate_flow"] = {
        "device_type": _current_or_estimate_device(estimate),
        "package_type": "カスタムパック",
        "estimate_id": estimate.id,
        "referrer_url": flow.get("referrer_url") or estimate.referrer_url,
        "step_times": flow.get("step_times") or {},
    }
    return redirect(url_for("main.custom_estimate"))


@main_bp.post("/estimate/<int:estimate_id>/pdf-click")
def record_pdf_click(estimate_id: int):
    estimate = Estimate.query.get_or_404(estimate_id)
    _record_pdf_click(estimate)
    return jsonify({"ok": True, "pdf_click_count": estimate.pdf_click_count})


@main_bp.get("/estimate/<int:estimate_id>/pdf")
def download_estimate_pdf(estimate_id: int):
    estimate = Estimate.query.get_or_404(estimate_id)
    _record_pdf_click(estimate)
    return send_file(
        build_estimate_pdf(estimate),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=estimate_pdf_download_name(),
    )


@main_bp.route("/inquiry/<int:estimate_id>", methods=["GET", "POST"])
def inquiry(estimate_id: int):
    estimate = Estimate.query.get_or_404(estimate_id)
    flow = session.get("estimate_flow")
    if request.method == "GET":
        return render_template(
            "inquiry.html",
            estimate=estimate,
            estimate_status=_estimate_status("inquiry", flow, estimate),
            back_url=url_for("main.estimate_result", estimate_id=estimate.id),
            estimate_item_label=estimate_item_label,
        )

    company_name = request.form.get("company_name", "").strip()
    person_name = request.form.get("person_name", "").strip()
    email = request.form.get("email", "").strip()
    privacy_consent = request.form.get("privacy_consent")
    if not company_name or not person_name or not email or privacy_consent != "1":
        flash("会社名、担当者名、メール、個人情報保護方針への同意は必須です。", "danger")
        return render_template(
            "inquiry.html",
            estimate=estimate,
            estimate_status=_estimate_status("inquiry", flow, estimate),
            back_url=url_for("main.estimate_result", estimate_id=estimate.id),
            estimate_item_label=estimate_item_label,
        ), 400

    inquiry_record = Inquiry(
        estimate_id=estimate.id,
        company_name=company_name,
        person_name=person_name,
        email=email,
        phone=request.form.get("phone", "").strip(),
        message=request.form.get("message", "").strip(),
    )
    db.session.add(inquiry_record)
    db.session.flush()

    file = request.files.get("attachment")
    if file and file.filename:
        if not allowed_file(file.filename):
            db.session.rollback()
            flash("添付可能な形式は xlsx, xls, pdf, png, jpg, docx です。", "danger")
            return render_template(
                "inquiry.html",
                estimate=estimate,
                estimate_status=_estimate_status("inquiry", flow, estimate),
                back_url=url_for("main.estimate_result", estimate_id=estimate.id),
                estimate_item_label=estimate_item_label,
            ), 400
        uploaded = upload_to_box(
            file,
            current_app.config["UPLOAD_FOLDER"],
            company_name,
            inquiry_record.id,
        )
        db.session.add(
            InquiryAttachment(
                inquiry_id=inquiry_record.id,
                file_name=uploaded["file_name"],
                box_file_id=uploaded["file_id"],
                box_url=uploaded["file_url"],
            )
        )

    db.session.commit()
    send_inquiry_mails(inquiry_record)
    send_lineworks_webhook_notification(inquiry_record)
    return render_template("thanks.html", inquiry=inquiry_record)

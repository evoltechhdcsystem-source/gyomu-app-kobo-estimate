from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import Estimate, EstimateItem, Inquiry, InquiryAttachment, db
from services.box_service import allowed_file, upload_to_box
from services.estimate_service import (
    DEVICE_PRICES,
    FEATURE_PRICES,
    PACKAGE_SCREENS,
    calculate_estimate,
)
from services.mail_service import send_inquiry_mails

main_bp = Blueprint("main", __name__)


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _estimate_flow_total(flow: dict | None, default_custom_screens: int = 0) -> int:
    if not flow or not flow.get("device_type"):
        return 0

    package_type = flow.get("package_type")
    if not package_type:
        return 0

    custom_screens = _as_int(flow.get("custom_screens"), default_custom_screens)
    features = flow.get("features", [])
    result = calculate_estimate(flow["device_type"], package_type, custom_screens, features)
    return result["total_price"]


def _estimate_status(active_step: str, flow: dict | None = None, estimate: Estimate | None = None):
    package_label = "パック選択"
    if flow and flow.get("package_type"):
        package_label = flow["package_type"]
    elif estimate:
        package_label = estimate.package_type

    steps = [
        {"key": "device", "label": "デバイス選択"},
        {"key": "package", "label": package_label},
        {"key": "custom", "label": "機能追加"},
        {"key": "result", "label": "見積もり結果"},
        {"key": "inquiry", "label": "問い合わせ"},
    ]
    current_index = next(
        (index for index, step in enumerate(steps) if step["key"] == active_step),
        0,
    )
    for index, step in enumerate(steps):
        step["state"] = "active" if index == current_index else "done" if index < current_index else "upcoming"

    if current_index > 0:
        steps[0]["href"] = url_for("main.device_select")
    if current_index > 1:
        steps[1]["href"] = url_for("main.package_select")
    if current_index > 2 and package_label == "カスタムパック":
        steps[2]["href"] = url_for("main.custom_estimate")
    if current_index > 3 and estimate:
        steps[3]["href"] = url_for("main.estimate_result", estimate_id=estimate.id)

    total_price = estimate.total_price if estimate else _estimate_flow_total(flow, 1 if active_step == "custom" else 0)
    return {"steps": steps, "total_price": total_price}


def _save_estimate_and_redirect(flow: dict):
    device_type = flow["device_type"]
    package_type = flow["package_type"]
    selected_features = flow.get("features", [])
    custom_screens = int(flow.get("custom_screens") or 0)

    result = calculate_estimate(device_type, package_type, custom_screens, selected_features)
    estimate = Estimate(
        device_type=result["device_type"],
        package_type=result["package_type"],
        total_price=result["total_price"],
    )
    db.session.add(estimate)
    db.session.flush()

    for item in result["items"]:
        db.session.add(
            EstimateItem(estimate_id=estimate.id, item_name=item["name"], price=item["price"])
        )
    db.session.commit()
    session["estimate_flow"] = flow
    session["estimate_back_endpoint"] = (
        "main.custom_estimate" if package_type == "カスタムパック" else "main.package_select"
    )

    return redirect(url_for("main.estimate_result", estimate_id=estimate.id))


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.route("/device", methods=["GET", "POST"])
def device_select():
    if request.method == "GET":
        return render_template(
            "device_select.html",
            device_prices=DEVICE_PRICES,
            estimate_status=_estimate_status("device"),
        )

    device_type = request.form.get("device_type", "")
    if device_type not in DEVICE_PRICES:
        flash("対応デバイスを選択してください。", "danger")
        return render_template(
            "device_select.html",
            device_prices=DEVICE_PRICES,
            estimate_status=_estimate_status("device"),
        ), 400

    session["estimate_flow"] = {"device_type": device_type}
    return redirect(url_for("main.package_select"))


@main_bp.route("/package", methods=["GET", "POST"])
def package_select():
    flow = session.get("estimate_flow")
    if not flow or not flow.get("device_type"):
        return redirect(url_for("main.device_select"))

    if request.method == "GET":
        return render_template(
            "package_select.html",
            package_screens=PACKAGE_SCREENS,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("package", flow),
        )

    package_type = request.form.get("package_type", "")
    if package_type not in PACKAGE_SCREENS:
        flash("パックを選択してください。", "danger")
        return render_template(
            "package_select.html",
            package_screens=PACKAGE_SCREENS,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("package", flow),
        ), 400

    flow["package_type"] = package_type
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

    if request.method == "GET":
        return render_template(
            "custom_estimate.html",
            feature_prices=FEATURE_PRICES,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        )

    custom_screens = int(request.form.get("custom_screens") or 0)
    if custom_screens < 1:
        flash("画面数は1以上で入力してください。", "danger")
        return render_template(
            "custom_estimate.html",
            feature_prices=FEATURE_PRICES,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        ), 400

    flow["custom_screens"] = custom_screens
    flow["features"] = request.form.getlist("features")
    session["estimate_flow"] = flow
    return _save_estimate_and_redirect(flow)


@main_bp.post("/estimate")
def create_estimate():
    return redirect(url_for("main.device_select"))


@main_bp.get("/estimate/<int:estimate_id>")
def estimate_result(estimate_id: int):
    estimate = Estimate.query.get_or_404(estimate_id)
    flow = session.get("estimate_flow")
    back_endpoint = session.get("estimate_back_endpoint", "main.device_select")
    return render_template(
        "estimate_result.html",
        estimate=estimate,
        estimate_status=_estimate_status("result", flow, estimate),
        back_url=url_for(back_endpoint),
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
        )

    company_name = request.form.get("company_name", "").strip()
    person_name = request.form.get("person_name", "").strip()
    email = request.form.get("email", "").strip()
    if not company_name or not person_name or not email:
        flash("会社名、担当者名、メールは必須です。", "danger")
        return render_template(
            "inquiry.html",
            estimate=estimate,
            estimate_status=_estimate_status("inquiry", flow, estimate),
            back_url=url_for("main.estimate_result", estimate_id=estimate.id),
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
    return render_template("thanks.html", inquiry=inquiry_record)

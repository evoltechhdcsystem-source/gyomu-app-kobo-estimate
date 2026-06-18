from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models import Estimate, EstimateItem, Inquiry, InquiryAttachment, db
from services.box_service import allowed_file, upload_to_box
from services.estimate_service import (
    DEVICE_PRICES,
    FEATURE_CONDITIONS,
    FEATURE_PRICES,
    MULTIPLE_FEATURES,
    PACKAGE_SCREENS,
    SCREEN_PARTS_CONDITION,
    calculate_estimate,
    feature_prices_for_device,
    package_feature_total,
    package_feature_quantities,
    package_features,
)
from services.mail_service import send_inquiry_mails

main_bp = Blueprint("main", __name__)
STEP_FIELDS = {
    "started": "step_started_at",
    "device": "step_device_at",
    "package": "step_package_at",
    "custom": "step_custom_at",
    "result": "step_result_at",
}
FEATURE_DESCRIPTIONS = {
    "画面表示項目追加": "1画面内に表示・入力できる項目数を増やします。",
    "データ登録": "新しい情報を入力フォームから追加できます。",
    "データ編集": "登録済みの情報をあとから修正できます。",
    "データ検索": "条件を指定して必要な情報を探せます。",
    "データ削除": "不要な情報を削除できます。",
    "メール送信": "通知や受付内容をメールで送信できます。",
    "マスターテーブル": "商品・顧客・分類などの基本データを管理できます。",
    "kintone連携": "別途kintone Standard以上のライセンスが必要です。",
    "AI API連携": "AIによる文章作成、要約、判定などを追加できます。外部AIサービスの利用料は別途必要です。",
    "App Store / Google Play公開申請代行": "アプリ公開に必要な申請作業を代行します。",
    "ユーザー操作マニュアル": "利用者向けの操作説明書を作成します。1画面あたりの料金です。",
    "ユーザーログイン": "利用者ごとにログインして使えるようにします。",
    "アプリ作成相談": "どんなアプリを作ればいいかなどのご相談を承ります。",
}
FEATURE_ICON_FILES = {
    "画面表示項目追加": "feature-table.svg",
    "データ登録": "feature-add.svg",
    "データ編集": "feature-edit.svg",
    "データ検索": "feature-search.svg",
    "データ削除": "feature-delete.svg",
    "メール送信": "feature-mail.svg",
    "マスターテーブル": "feature-table.svg",
    "kintone連携": "feature-link.svg",
    "AI API連携": "feature-ai.svg",
    "App Store / Google Play公開申請代行": "feature-store.svg",
    "ユーザー操作マニュアル": "feature-manual.svg",
    "ユーザーログイン": "feature-login.svg",
    "アプリ作成相談": "feature-manual.svg",
}
SCREEN_DESCRIPTIONS = {
    "データ登録画面": "新しい情報を入力して保存するための画面です。",
    "データ一覧画面": "登録した情報をまとめて確認し、必要なデータを探しやすくします。",
    "データ詳細画面": "1件ごとの内容を詳しく確認するための画面です。",
    "検索・絞り込み機能": "条件を指定して、必要な情報だけをすばやく見つけられます。",
    "データ修正画面": "登録済みの情報をあとから変更・更新できます。",
    "集計・状況確認画面": "件数や状態を集計し、業務の状況を把握しやすくします。",
    "データ登録機能": "業務データを入力して保存できます。",
    "データ検索機能": "条件を指定して必要なデータを検索できます。",
    "データ編集機能": "登録済みの業務データを更新できます。",
    "データ削除機能": "不要になった業務データを削除できます。",
    "データ登録機能（マスター）": "マスターデータを入力して保存できます。",
    "データ編集機能（マスター）": "登録済みのマスターデータを更新できます。",
    "データ削除機能（マスター）": "不要になったマスターデータを削除できます。",
}
INCLUDED_WORK_ITEMS = [
    "画面・機能確認のお打ち合わせ 2時間まで",
    "1画面内のパーツは20個まで",
    "アプリの設計・制作",
    "開発環境 Click の契約サポート",
    "仮納品後の微調整",
    "納品・操作説明 1時間まで",
]


def estimate_item_label(item_name: str) -> str:
    return (
        item_name
        .replace(" 画面単価 x ", " x ")
        .replace("kintoneのデータベースと連携する(1DB)", "kintone連携")
        .replace("ストア申請代行", "App Store / Google Play公開申請代行")
        .replace("アプリ作成コンサル", "アプリ作成相談")
        .replace("操作マニュアル", "ユーザー操作マニュアル")
    )


def estimate_feature_name(item_name: str) -> str:
    feature_name = item_name.split(" x ", 1)[0]
    if feature_name == "kintoneのデータベースと連携する(1DB)":
        return "kintone連携"
    if feature_name == "アプリ作成コンサル":
        return "アプリ作成相談"
    if feature_name == "ストア申請代行":
        return "App Store / Google Play公開申請代行"
    if feature_name == "操作マニュアル":
        return "ユーザー操作マニュアル"
    return feature_name


def estimate_screen_count(item_name: str) -> int:
    try:
        return int(item_name.rsplit(" x ", 1)[-1].replace("画面", ""))
    except (ValueError, IndexError):
        return 0


def is_screen_count_item(item_name: str, device_type: str) -> bool:
    return item_name.startswith(device_type) and "画面" in item_name


def estimate_item_condition(item_name: str, device_type: str) -> str:
    if is_screen_count_item(item_name, device_type):
        return SCREEN_PARTS_CONDITION
    return FEATURE_CONDITIONS.get(estimate_feature_name(item_name), "")


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> datetime:
    return datetime.utcnow()


def _pdf_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    escaped = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(escaped, style)


def _register_pdf_fonts() -> None:
    if "HeiseiKakuGo-W5" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))


def _estimate_pdf_items(estimate: Estimate) -> list[list[object]]:
    rows: list[list[object]] = []
    for item in estimate.items:
        rows.append(
            [
                estimate_item_label(item.item_name),
                estimate_item_condition(item.item_name, estimate.device_type),
                f"{item.price:,}円",
            ]
        )
    return rows


def _estimate_pdf_logo() -> Image | None:
    logo_path = Path(current_app.root_path) / "static" / "img" / "top-estimate-logo-factory.png"
    if not logo_path.exists():
        return None

    image = Image(str(logo_path))
    original_width, original_height = ImageReader(str(logo_path)).getSize()
    image.drawWidth = 62 * mm
    image.drawHeight = image.drawWidth * original_height / original_width
    return image


def _estimate_pdf_company_info(style: ParagraphStyle, name_style: ParagraphStyle) -> list[object]:
    lines = [
        ("name", current_app.config.get("COMPANY_NAME", "")),
        ("text", current_app.config.get("COMPANY_ADDRESS", "")),
        ("text", f"TEL {current_app.config.get('COMPANY_PHONE', '')}" if current_app.config.get("COMPANY_PHONE") else ""),
        ("text", current_app.config.get("COMPANY_EMAIL", "")),
    ]
    info: list[object] = []
    for line_type, text in lines:
        if not text:
            continue
        info.append(_pdf_paragraph(text, name_style if line_type == "name" else style))
    return info


def _estimate_pdf_download_name() -> str:
    timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d_%H%M")
    return f"業務アプリ工房_{timestamp}.pdf"


def _build_estimate_pdf(estimate: Estimate) -> BytesIO:
    _register_pdf_fonts()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"estimate-{estimate.id}",
    )
    base = ParagraphStyle(
        "Japanese",
        fontName="HeiseiKakuGo-W5",
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#1f2f37"),
    )
    title = ParagraphStyle(
        "JapaneseTitle",
        parent=base,
        fontSize=20,
        leading=26,
        spaceAfter=8,
    )
    label = ParagraphStyle(
        "JapaneseLabel",
        parent=base,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#4d5960"),
    )
    company = ParagraphStyle(
        "JapaneseCompany",
        parent=base,
        fontSize=8,
        leading=11,
        alignment=2,
        textColor=colors.HexColor("#4d5960"),
    )
    company_name = ParagraphStyle(
        "JapaneseCompanyName",
        parent=company,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1f2f37"),
    )

    logo = _estimate_pdf_logo()
    story: list[object] = []
    header_left: list[object] = []
    if logo:
        header_left.extend([logo, Spacer(1, 4 * mm)])
    header_left.append(_pdf_paragraph("概算見積書", title))
    story.extend(
        [
            Table(
                [[header_left, _estimate_pdf_company_info(company, company_name)]],
                colWidths=[86 * mm, 70 * mm],
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                ),
            ),
            Spacer(1, 5 * mm),
        ]
    )

    story.extend([
        Table(
            [
                [_pdf_paragraph("合計", label), _pdf_paragraph(f"{estimate.total_price:,}円（税抜）", title)],
                [_pdf_paragraph("利用端末", label), _pdf_paragraph(estimate.device_type, base)],
                [_pdf_paragraph("パック", label), _pdf_paragraph(estimate.package_type, base)],
            ],
            colWidths=[32 * mm, 124 * mm],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8f2")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e5ddd4")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5ddd4")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        ),
        Spacer(1, 9 * mm),
        _pdf_paragraph("画面・機能の内容", ParagraphStyle("JapaneseSection", parent=base, fontSize=13, leading=18)),
        Spacer(1, 3 * mm),
    ])

    item_rows = [
        [
            _pdf_paragraph("画面・機能", label),
            _pdf_paragraph("条件", label),
            _pdf_paragraph("金額", label),
        ]
    ]
    for name, condition, price in _estimate_pdf_items(estimate):
        item_rows.append(
            [_pdf_paragraph(name, base), _pdf_paragraph(condition, base), _pdf_paragraph(price, base)]
        )
    story.append(
        Table(
            item_rows,
            colWidths=[72 * mm, 52 * mm, 32 * mm],
            repeatRows=1,
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3ffd9")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d8e6c4")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8e6c4")),
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            ),
        )
    )
    included_work_rows = [[_pdf_paragraph("本見積りに含まれる作業", label)]]
    for item in INCLUDED_WORK_ITEMS:
        included_work_rows.append([_pdf_paragraph(f"・{item}", base)])
    story.extend(
        [
            Spacer(1, 9 * mm),
            Table(
                included_work_rows,
                colWidths=[156 * mm],
                style=TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff8f2")),
                        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e5ddd4")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5ddd4")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                ),
            ),
            Spacer(1, 9 * mm),
            _pdf_paragraph("開発ツールライセンス", ParagraphStyle("JapaneseNoteHead", parent=base, fontSize=11, leading=16)),
            _pdf_paragraph(
                "業務アプリの作成・公開・運用基盤としてノーコードツール「Click」を利用します。"
                "ご利用にはClick Proプラン（月額19,600円）の契約が別途必要です。"
                "合計金額には加算していません。",
                label,
            ),
            Spacer(1, 4 * mm),
            _pdf_paragraph("外部AIサービス利用料", ParagraphStyle("JapaneseAiNoteHead", parent=base, fontSize=11, leading=16)),
            _pdf_paragraph(
                "OpenAI API等の外部AIサービスを利用する場合、その利用料は別途お客様のご負担となります。\n"
                "合計金額には加算していません。",
                label,
            ),
        ]
    )
    doc.build(story)
    buffer.seek(0)
    return buffer


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
            device_prices=DEVICE_PRICES,
            estimate_status=_estimate_status("device"),
        )

    device_type = request.form.get("device_type", "")
    if device_type not in DEVICE_PRICES:
        flash("端末を選ぶと次へ進めます。3つの中から1つ選択してください。", "danger")
        return render_template(
            "device_select.html",
            device_prices=DEVICE_PRICES,
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
            package_screens=PACKAGE_SCREENS,
            package_feature_total=package_feature_total,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("package", flow),
        )

    package_type = request.form.get("package_type", "")
    if package_type not in PACKAGE_SCREENS:
        flash("パックを選ぶと次へ進めます。現場で使いたい内容に近いパックを1つ選択してください。", "danger")
        return render_template(
            "package_select.html",
            package_screens=PACKAGE_SCREENS,
            package_feature_total=package_feature_total,
            device_prices=DEVICE_PRICES,
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
            feature_descriptions=FEATURE_DESCRIPTIONS,
            feature_conditions=FEATURE_CONDITIONS,
            feature_icon_files=FEATURE_ICON_FILES,
            multiple_feature_names=MULTIPLE_FEATURES,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        )

    custom_screens = int(request.form.get("custom_screens") or 0)
    if custom_screens < 1:
        flash("画面数を入力してください。1以上の数字で入力すると見積りできます。", "danger")
        return render_template(
            "custom_estimate.html",
            feature_prices=feature_prices_for_device(flow["device_type"]),
            feature_descriptions=FEATURE_DESCRIPTIONS,
            feature_conditions=FEATURE_CONDITIONS,
            feature_icon_files=FEATURE_ICON_FILES,
            multiple_feature_names=MULTIPLE_FEATURES,
            device_prices=DEVICE_PRICES,
            flow=flow,
            estimate_status=_estimate_status("custom", flow),
        ), 400

    selected_features = [
        feature for feature in request.form.getlist("features") if feature in FEATURE_PRICES
    ]
    feature_quantities = {}
    for feature in selected_features:
        quantity = _as_int(request.form.get(f"feature_quantities[{feature}]"), 1)
        feature_quantities[feature] = max(quantity, 1) if feature in MULTIPLE_FEATURES else 1

    if not selected_features:
        flash("追加機能を選ぶと結果へ進めます。必要な機能を1つ以上選択してください。", "danger")
        flow["custom_screens"] = custom_screens
        flow["features"] = []
        flow["feature_quantities"] = {}
        session["estimate_flow"] = flow
        return render_template(
            "custom_estimate.html",
            feature_prices=feature_prices_for_device(flow["device_type"]),
            feature_descriptions=FEATURE_DESCRIPTIONS,
            feature_conditions=FEATURE_CONDITIONS,
            feature_icon_files=FEATURE_ICON_FILES,
            multiple_feature_names=MULTIPLE_FEATURES,
            device_prices=DEVICE_PRICES,
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
        feature_descriptions=FEATURE_DESCRIPTIONS,
        feature_conditions=FEATURE_CONDITIONS,
        screen_descriptions=SCREEN_DESCRIPTIONS,
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
        _build_estimate_pdf(estimate),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=_estimate_pdf_download_name(),
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
    return render_template("thanks.html", inquiry=inquiry_record)

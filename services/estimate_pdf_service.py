from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models import FULL_PLAN, SIMPLE_PLAN, Estimate, PlanMaster, db
from services.estimate_display_service import (
    INCLUDED_WORK_ITEMS,
    estimate_item_condition,
    estimate_item_label,
)

CONSUMPTION_TAX_RATE = 0.10


def estimate_pdf_download_name() -> str:
    timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d_%H%M")
    return f"業務アプリ工房_{timestamp}.pdf"


def build_estimate_pdf(estimate: Estimate) -> BytesIO:
    _register_pdf_fonts()
    compact_pack = (
        estimate.plan_key == FULL_PLAN
        and estimate.package_type in {"基本パック", "運用パック"}
        and estimate.maintenance_monthly_price is not None
    )
    table_padding = 3 if compact_pack else 4
    plan = db.session.get(PlanMaster, estimate.plan_key)
    issued_on = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y年%m月%d日")
    subtotal = estimate.total_price
    tax_amount = _estimate_tax_amount(subtotal)
    total_with_tax = subtotal + tax_amount
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"estimate-{estimate.id}",
    )
    base = ParagraphStyle(
        "Japanese",
        fontName="HeiseiKakuGo-W5",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1f2f37"),
    )
    title = ParagraphStyle(
        "JapaneseTitle",
        parent=base,
        fontSize=18,
        leading=22,
        spaceAfter=4,
        alignment=1,
    )
    label = ParagraphStyle(
        "JapaneseLabel",
        parent=base,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#4d5960"),
    )
    label_right = ParagraphStyle("JapaneseLabelRight", parent=label, alignment=2)
    amount = ParagraphStyle("JapaneseAmount", parent=base, alignment=2)
    total_amount = ParagraphStyle(
        "JapaneseTotalAmount",
        parent=amount,
        fontSize=15,
        leading=18,
    )
    item_indent = ParagraphStyle(
        "JapaneseItemIndent",
        parent=base,
        leftIndent=12,
        firstLineIndent=0,
        spaceBefore=1,
    )
    company = ParagraphStyle(
        "JapaneseCompany",
        parent=base,
        fontSize=7,
        leading=9,
        alignment=2,
        textColor=colors.HexColor("#4d5960"),
    )
    company_name = ParagraphStyle(
        "JapaneseCompanyName",
        parent=company,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#1f2f37"),
    )

    logo = _estimate_pdf_logo()
    story: list[object] = []
    header_center: list[object] = [_pdf_paragraph("概算見積書", title)]
    header_right: list[object] = []
    if logo:
        header_right.extend([logo, Spacer(1, 1 * mm)])
    header_right.extend(_estimate_pdf_company_info(company, company_name))
    story.extend(
        [
            Table(
                [["", header_center, header_right]],
                colWidths=[61 * mm, 61 * mm, 64 * mm],
                style=TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("ALIGN", (1, 0), (1, 0), "CENTER"),
                        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                ),
            ),
            Spacer(1, 3 * mm),
        ]
    )

    story.extend(
        [
            Table(
                [
                    [
                        _pdf_paragraph("見積番号", label),
                        _pdf_paragraph(f"No. {estimate.id}", base),
                        _pdf_paragraph("発行日", label),
                        _pdf_paragraph(issued_on, base),
                    ],
                    [
                        _pdf_paragraph("プラン", label),
                        _pdf_paragraph(plan.name if plan else "かんたんアプリプラン", base),
                        "", "",
                    ],
                    [
                        _pdf_paragraph("利用端末", label),
                        _pdf_paragraph(estimate.device_type, base),
                        "",
                        "",
                    ],
                    [
                        _pdf_paragraph("パック", label),
                        _pdf_paragraph(_estimate_package_display_name(estimate.package_type), base),
                        "",
                        "",
                    ],
                    [
                        _pdf_paragraph("初期費用（税込）", label),
                        _pdf_paragraph(f"{total_with_tax:,}円", title),
                        "",
                        "",
                    ],
                ],
                colWidths=[30 * mm, 62 * mm, 30 * mm, 64 * mm],
                style=TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff8f2")),
                        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e5ddd4")),
                        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5ddd4")),
                        ("SPAN", (1, 1), (3, 1)),
                        ("SPAN", (1, 2), (3, 2)),
                        ("SPAN", (1, 3), (3, 3)),
                        ("SPAN", (1, 4), (3, 4)),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), table_padding),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), table_padding),
                    ]
                ),
            ),
            Spacer(1, 5 * mm),
            _pdf_paragraph("見積もり内容", ParagraphStyle("JapaneseSection", parent=base, fontSize=12, leading=15)),
            Spacer(1, 2 * mm),
        ]
    )

    if estimate.package_type in {"基本パック", "運用パック"}:
        package_details: list[object] = [_pdf_paragraph(_estimate_package_display_name(estimate.package_type), base)]
        package_details.extend(_pdf_paragraph(name, item_indent) for name, _, _ in _estimate_pdf_items(estimate))
        story.append(
            Table(
                [
                    [_pdf_paragraph("画面・機能", label), _pdf_paragraph("金額", label_right)],
                    [package_details, _pdf_paragraph(f"{subtotal:,}円", amount)],
                    [_pdf_paragraph("小計", label_right), _pdf_paragraph(f"{subtotal:,}円", amount)],
                    [
                        _pdf_paragraph(f"消費税（{int(CONSUMPTION_TAX_RATE * 100)}%）", label_right),
                        _pdf_paragraph(f"{tax_amount:,}円", amount),
                    ],
                    [_pdf_paragraph("初期費用合計（税込）", label_right), _pdf_paragraph(f"{total_with_tax:,}円", total_amount)],
                ],
                colWidths=[124 * mm, 62 * mm],
                repeatRows=1,
                style=_estimate_total_table_style(),
            )
        )
    else:
        item_rows = [
            [
                _pdf_paragraph("画面・機能", label),
                _pdf_paragraph("条件", label),
                _pdf_paragraph("金額", label_right),
            ]
        ]
        for name, condition, price in _estimate_pdf_items(estimate):
            item_rows.append(
                [_pdf_paragraph(name, base), _pdf_paragraph(condition, base), _pdf_paragraph(price, amount)]
            )
        total_row_start = len(item_rows)
        item_rows.extend(
            [
                [_pdf_paragraph("小計", label_right), "", _pdf_paragraph(f"{subtotal:,}円", amount)],
                [
                    _pdf_paragraph(f"消費税（{int(CONSUMPTION_TAX_RATE * 100)}%）", label_right),
                    "",
                    _pdf_paragraph(f"{tax_amount:,}円", amount),
                ],
                [_pdf_paragraph("初期費用合計（税込）", label_right), "", _pdf_paragraph(f"{total_with_tax:,}円", total_amount)],
            ]
        )
        story.append(
            Table(
                item_rows,
                colWidths=[70 * mm, 78 * mm, 38 * mm],
                repeatRows=1,
                style=_custom_estimate_table_style(total_row_start),
            )
        )

    if estimate.has_quote_required_items:
        story.extend([
            Spacer(1, 2 * mm),
            _pdf_paragraph(
                "要相談の機能は上記金額に含まれません。詳細お見積りで金額をご案内します。",
                base,
            ),
        ])

    if estimate.maintenance_monthly_price is not None:
        story.extend([
            Spacer(1, 8 * mm),
            Table([
                [_pdf_paragraph("月額費用（初期費用には含みません）", label), ""],
                [_pdf_paragraph("サーバー保守", base), _pdf_paragraph(estimate.maintenance_price_label + "（税抜）", amount)],
            ], colWidths=[124 * mm, 62 * mm], style=TableStyle([
                ("SPAN", (0, 0), (1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff8f2")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e5ddd4")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.4, colors.HexColor("#e5ddd4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])),
            Spacer(1, 2 * mm),
            _pdf_paragraph("サーバー保守は、ご利用期間中、毎月かかる費用です。", base),
        ])
    elif estimate.plan_key == FULL_PLAN:
        story.extend([
            Spacer(1, 2 * mm),
            _pdf_paragraph("サーバー保守は含まれていません。ご希望の場合は見積り結果画面で追加できます。", base),
        ])

    story.extend(_included_work_and_notes(base, label, estimate.plan_key, table_padding=table_padding))
    doc.build(story)
    buffer.seek(0)
    return buffer


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
        font_path = Path(current_app.root_path) / "static" / "fonts" / "BIZUDGothic-Regular.ttf"
        pdfmetrics.registerFont(TTFont("HeiseiKakuGo-W5", str(font_path)))


def _estimate_pdf_items(estimate: Estimate) -> list[list[object]]:
    rows: list[list[object]] = []
    for item in estimate.items:
        price = "" if estimate.package_type in {"基本パック", "運用パック"} else item.price_label
        rows.append(
            [
                estimate_item_label(item.item_name),
                estimate_item_condition(item.item_name, estimate.device_type, estimate.plan_key),
                price,
            ]
        )
    return rows


def _estimate_pdf_logo() -> Image | None:
    img_dir = Path(current_app.root_path) / "static" / "img"
    logo_path = next(
        (
            path
            for path in [
                img_dir / "top-estimate-logo-factory.png",
                img_dir / "top-estimate-logo.png",
                img_dir / "top-estimate-logo-transparent.png",
            ]
            if path.exists()
        ),
        None,
    )
    if logo_path is None:
        return None

    image = Image(str(logo_path))
    original_width, original_height = ImageReader(str(logo_path)).getSize()
    image.drawWidth = 52 * mm
    image.drawHeight = image.drawWidth * original_height / original_width
    image.hAlign = "RIGHT"
    return image


def _estimate_tax_amount(subtotal: int) -> int:
    return int(subtotal * CONSUMPTION_TAX_RATE)


def _estimate_package_display_name(package_type: str) -> str:
    return f"業務アプリ工房 {package_type}"


def _estimate_company_display_name(company_name: str) -> str:
    if "株式会社" in company_name and "株式会社 " not in company_name:
        return company_name.replace("株式会社", "株式会社 ", 1)
    return company_name


def _estimate_pdf_company_info(style: ParagraphStyle, name_style: ParagraphStyle) -> list[object]:
    lines = [
        ("name", _estimate_company_display_name(current_app.config.get("COMPANY_NAME", ""))),
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


def _estimate_total_table_style() -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3ffd9")),
            ("BACKGROUND", (0, 2), (-1, 3), colors.HexColor("#fff8f2")),
            ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#f3ffd9")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d8e6c4")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8e6c4")),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ALIGN", (0, 2), (0, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _custom_estimate_table_style(total_row_start: int) -> TableStyle:
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3ffd9")),
            ("BACKGROUND", (0, total_row_start), (-1, -1), colors.HexColor("#fff8f2")),
            ("BACKGROUND", (0, total_row_start + 2), (-1, total_row_start + 2), colors.HexColor("#f3ffd9")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d8e6c4")),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8e6c4")),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("ALIGN", (0, total_row_start), (1, -1), "RIGHT"),
            ("SPAN", (0, total_row_start), (1, total_row_start)),
            ("SPAN", (0, total_row_start + 1), (1, total_row_start + 1)),
            ("SPAN", (0, total_row_start + 2), (1, total_row_start + 2)),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _included_work_and_notes(
    base: ParagraphStyle, label: ParagraphStyle, plan_key: str, *, table_padding: int = 4
) -> list[object]:
    included_work_rows = [[_pdf_paragraph("本見積りに含まれる作業", label)]]
    for item in INCLUDED_WORK_ITEMS:
        if plan_key != SIMPLE_PLAN and item == "開発環境 Click の契約サポート":
            continue
        included_work_rows.append([_pdf_paragraph(f"・{item}", base)])
    notes = [
        Spacer(1, 5 * mm),
        Table(
            included_work_rows,
            colWidths=[186 * mm],
            style=TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "HeiseiKakuGo-W5"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fff8f2")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#e5ddd4")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5ddd4")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), table_padding),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), table_padding),
                ]
            ),
        ),
        Spacer(1, 5 * mm),
        _pdf_paragraph("別途費用・利用条件", ParagraphStyle("JapaneseNoteTitle", parent=base, fontSize=11, leading=14)),
        Spacer(1, 2 * mm),
    ]
    if plan_key == SIMPLE_PLAN:
        notes.extend([
            _pdf_paragraph("開発ツールライセンス", ParagraphStyle("JapaneseNoteHead", parent=base, fontSize=10, leading=13)),
            _pdf_paragraph(
                "業務アプリの作成・公開・運用基盤としてノーコードツール「Click」を利用します。"
                "ご利用にはClick Standardプラン以上（月額4,400円～）の契約が別途必要です。"
                "合計金額には加算していません。",
                label,
            ),
            Spacer(1, 2 * mm),
        ])
    if plan_key == FULL_PLAN:
        notes.extend([
            _pdf_paragraph("Google Cloud利用料（月額）", ParagraphStyle("JapaneseCloudNoteHead", parent=base, fontSize=10, leading=13)),
            _pdf_paragraph(
                "アプリの公開・運用に伴い、Google Cloudの利用料が月額で別途かかります。\n"
                "月額利用料は、利用量や為替レートの変動により増減します。\n"
                "合計金額には加算していません。",
                label,
            ),
            Spacer(1, 2 * mm),
        ])
    notes.extend([
        _pdf_paragraph("外部AIサービス利用料", ParagraphStyle("JapaneseAiNoteHead", parent=base, fontSize=10, leading=13)),
        _pdf_paragraph(
            "OpenAI API等の外部AIサービスを利用する場合、その利用料は別途お客様のご負担となります。\n"
            "合計金額には加算していません。",
            label,
        ),
    ])
    return notes

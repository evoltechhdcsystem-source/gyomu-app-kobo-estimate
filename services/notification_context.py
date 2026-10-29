from __future__ import annotations

from models import Inquiry, PlanMaster, db
from services.maintenance_service import GOOGLE_CLOUD_MONTHLY_MIN, monthly_total_label, monthly_total_note


def cost_summary_lines(estimate) -> list[str]:
    lines = ["■概算費用", f"初期費用: {estimate.total_price:,}円（税抜）"]
    if estimate.has_quote_required_items:
        lines.append("要相談の機能は、初期費用に含まれていません。")
    if estimate.plan_key == "full":
        lines.append(f"月額費用: {monthly_total_label(estimate).removesuffix('／月')}（税抜）")
        if monthly_total_note(estimate):
            lines.append(monthly_total_note(estimate))
    return lines


def maintenance_lines(estimate) -> list[str]:
    if estimate.plan_key != "full":
        return []
    lines = [
        "", "■月額費用について",
        "上記の月額費用には、以下を含みます。",
        f"・Google Cloud利用料: {GOOGLE_CLOUD_MONTHLY_MIN:,}円～",
    ]
    if estimate.maintenance_monthly_price is None:
        lines.append("サーバー保守は含まれていません。")
    elif estimate.maintenance_quote_required:
        lines.append("サーバー保守: 要相談（上記の月額費用には含みません）")
    else:
        lines.append(f"・サーバー保守: {estimate.maintenance_price_label.removesuffix('／月')}")
    lines.extend([
        "金額は税抜です。",
        "Google Cloud利用料は利用するサービスや利用量、為替により変動します。",
        "月額費用は初期費用とは別に、毎月発生します。",
    ])
    return lines


def estimate_lines(inquiry: Inquiry) -> list[str]:
    estimate = inquiry.estimate
    plan = db.session.get(PlanMaster, estimate.plan_key)
    lines = [
        f"受付番号: #{inquiry.id}",
        f"見積ID: #{estimate.id}",
        f"プラン: {plan.name if plan else estimate.plan_key}",
        f"端末: {estimate.device_type}",
        f"パック: {estimate.package_type}",
        "",
        *cost_summary_lines(estimate),
        *maintenance_lines(estimate),
        "",
        "見積項目:",
    ]
    for item in estimate.items:
        lines.append(f"- {item.item_name}: {item.price_label}")
    return lines


def attachment_lines(inquiry: Inquiry) -> list[str]:
    if not inquiry.attachments:
        return ["添付ファイル: なし"]

    lines = ["添付ファイル:"]
    for attachment in inquiry.attachments:
        lines.append(f"- {attachment.file_name}")
        if attachment.box_url:
            lines.append(f"  保存先: {attachment.box_url}")
    return lines


def estimate_item_names(inquiry: Inquiry) -> list[str]:
    return [
        f"{item.item_name}（要相談）" if item.is_quote_required else item.item_name
        for item in inquiry.estimate.items
    ]


def attachment_names(inquiry: Inquiry) -> list[str]:
    return [attachment.file_name for attachment in inquiry.attachments]

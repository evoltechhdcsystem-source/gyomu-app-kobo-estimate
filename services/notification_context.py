from __future__ import annotations

from models import Inquiry, PlanMaster, db


def maintenance_lines(estimate) -> list[str]:
    if estimate.plan_key != "full":
        return []
    return [
        f"サーバー保守（月額・税抜）: {estimate.maintenance_price_label if estimate.maintenance_monthly_price is not None else '未選択'}",
        "サーバー保守は初期費用に含まれません。選択時は毎月発生します。",
        "Google Cloud利用料は別途かかり、利用量・為替により変動します。",
    ]


def estimate_lines(inquiry: Inquiry) -> list[str]:
    estimate = inquiry.estimate
    plan = db.session.get(PlanMaster, estimate.plan_key)
    lines = [
        f"受付番号: #{inquiry.id}",
        f"見積ID: #{estimate.id}",
        f"プラン: {plan.name if plan else estimate.plan_key}",
        f"端末: {estimate.device_type}",
        f"パック: {estimate.package_type}",
        f"初期費用（概算）: {estimate.total_price:,}円（税抜）",
        *maintenance_lines(estimate),
        *(["要相談の機能は上記金額に含まれません。"] if estimate.has_quote_required_items else []),
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

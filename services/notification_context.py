from __future__ import annotations

from models import Inquiry


def estimate_lines(inquiry: Inquiry) -> list[str]:
    estimate = inquiry.estimate
    lines = [
        f"受付番号: #{inquiry.id}",
        f"見積ID: #{estimate.id}",
        f"端末: {estimate.device_type}",
        f"パック: {estimate.package_type}",
        f"概算見積金額: {estimate.total_price:,}円（税抜）",
        "",
        "見積項目:",
    ]
    for item in estimate.items:
        lines.append(f"- {item.item_name}: {item.price:,}円")
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
    return [item.item_name for item in inquiry.estimate.items]


def attachment_names(inquiry: Inquiry) -> list[str]:
    return [attachment.file_name for attachment in inquiry.attachments]

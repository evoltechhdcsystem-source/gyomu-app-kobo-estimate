from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from flask import current_app, url_for

from models import Inquiry

logger = logging.getLogger(__name__)


def _estimate_lines(inquiry: Inquiry) -> list[str]:
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


def _attachment_lines(inquiry: Inquiry) -> list[str]:
    if not inquiry.attachments:
        return ["添付ファイル: なし"]

    lines = ["添付ファイル:"]
    for attachment in inquiry.attachments:
        lines.append(f"- {attachment.file_name}")
        if attachment.box_url:
            lines.append(f"  保存先: {attachment.box_url}")
    return lines


def _admin_detail_url(inquiry: Inquiry) -> str:
    path = url_for("admin.inquiry_detail", inquiry_id=inquiry.id)
    base_url = (
        current_app.config.get("LINEWORKS_ADMIN_BASE_URL")
        or current_app.config.get("PUBLIC_BASE_URL")
        or ""
    ).strip()
    if base_url:
        return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
    return url_for("admin.inquiry_detail", inquiry_id=inquiry.id, _external=True)


def _notification_text(inquiry: Inquiry) -> str:
    estimate = inquiry.estimate
    item_names = [item.item_name for item in estimate.items]
    attachment_names = [attachment.file_name for attachment in inquiry.attachments]
    lines = [
        "問い合わせ、詳細見積りの依頼が送信されました。",
        "",
        f"受付番号: #{inquiry.id}",
        f"見積ID: #{estimate.id}",
        f"会社名: {inquiry.company_name}",
        f"担当者名: {inquiry.person_name}",
        f"メール: {inquiry.email}",
        f"電話番号: {inquiry.phone or '-'}",
        f"端末: {estimate.device_type}",
        f"パック: {estimate.package_type}",
        f"概算見積金額: {estimate.total_price:,}円（税抜）",
        "",
        "問い合わせ内容:",
        inquiry.message or "-",
        "",
        "見積項目:",
        ", ".join(item_names) if item_names else "-",
        "",
        "添付ファイル:",
        ", ".join(attachment_names) if attachment_names else "なし",
    ]
    return "\n".join(lines)


def _payload(text: str, inquiry: Inquiry | None = None) -> dict[str, object]:
    style = current_app.config.get("LINEWORKS_WEBHOOK_PAYLOAD_STYLE", "text")
    if style == "lineworks":
        payload: dict[str, object] = {
            "title": current_app.config.get("LINEWORKS_WEBHOOK_TITLE", "詳細見積り依頼"),
            "body": {"text": text},
        }
        if inquiry is not None:
            payload["button"] = {
                "label": "管理画面を開く",
                "url": _admin_detail_url(inquiry),
            }
        return payload
    if style == "lineworks-body-string":
        return {"body": text}
    if style == "lineworks-title":
        return {
            "title": current_app.config.get("LINEWORKS_WEBHOOK_TITLE", "詳細見積り依頼"),
            "body": {"text": text},
        }
    if style == "lineworks-title-string":
        return {
            "title": current_app.config.get("LINEWORKS_WEBHOOK_TITLE", "詳細見積り依頼"),
            "body": text,
        }
    if style == "bot":
        return {"content": {"type": "text", "text": text}}
    if style == "message":
        return {"message": text}
    return {"text": text}


def send_lineworks_webhook_notification(inquiry: Inquiry) -> None:
    webhook_url = current_app.config.get("LINEWORKS_WEBHOOK_URL")
    if not webhook_url:
        logger.info("LINEWORKS_WEBHOOK_URL is not configured. LINE WORKS notification was skipped.")
        return

    payload_style = current_app.config.get("LINEWORKS_WEBHOOK_PAYLOAD_STYLE", "text")
    payload = _payload(_notification_text(inquiry), inquiry)
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "gyomu-app-kobo-estimate/1.0",
    }
    bearer_token = current_app.config.get("LINEWORKS_WEBHOOK_BEARER_TOKEN")
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    timeout = current_app.config.get("LINEWORKS_WEBHOOK_TIMEOUT", 10)
    request = Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            current_app.logger.info(
                "LINE WORKS webhook notification sent: inquiry_id=%s status=%s",
                inquiry.id,
                response.status,
            )
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        current_app.logger.exception(
            "LINE WORKS webhook notification failed: inquiry_id=%s status=%s payload_style=%s response=%s",
            inquiry.id,
            exc.code,
            payload_style,
            response_body,
        )
    except (URLError, TimeoutError, OSError) as exc:
        current_app.logger.exception("LINE WORKS webhook notification failed: inquiry_id=%s error=%s", inquiry.id, exc)

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app, url_for

from models import Inquiry
from services.notification_context import attachment_lines, estimate_lines

logger = logging.getLogger(__name__)


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _sender() -> str:
    company_name = current_app.config.get("COMPANY_NAME", "業務アプリ工房")
    mail_from = current_app.config.get("MAIL_FROM", "")
    return formataddr((company_name, mail_from)) if mail_from else ""


def _admin_body(inquiry: Inquiry) -> str:
    detail_url = url_for("admin.inquiry_detail", inquiry_id=inquiry.id, _external=True)
    lines = [
        "問い合わせ、詳細見積りの依頼が送信されました。",
        "",
        f"管理画面: {detail_url}",
        "",
        "お客様情報:",
        f"会社名: {inquiry.company_name}",
        f"担当者名: {inquiry.person_name}",
        f"メール: {inquiry.email}",
        f"電話番号: {inquiry.phone or '-'}",
        "",
        "問い合わせ内容:",
        inquiry.message or "-",
        "",
        *estimate_lines(inquiry),
        "",
        *attachment_lines(inquiry),
    ]
    return "\n".join(lines)


def _customer_body(inquiry: Inquiry) -> str:
    company_name = current_app.config.get("COMPANY_NAME", "業務アプリ工房")
    lines = [
        f"{inquiry.person_name} 様",
        "",
        "お問い合わせ、詳細見積りのご依頼ありがとうございます。",
        "以下の内容で受け付けました。",
        "担当者より折り返しご連絡いたします。",
        "",
        *estimate_lines(inquiry),
        "",
        "お問い合わせ内容:",
        inquiry.message or "-",
        "",
        "----------------------------------------",
        company_name,
        f"電話番号: {current_app.config.get('COMPANY_PHONE', '')}",
        f"メール: {current_app.config.get('COMPANY_EMAIL', current_app.config.get('MAIL_TO', ''))}",
    ]
    return "\n".join(line for line in lines if line is not None)


def _message(subject: str, to_addrs: list[str], body: str, reply_to: str | None = None) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _sender()
    message["To"] = ", ".join(to_addrs)
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(body)
    return message


def _send_messages(messages: list[EmailMessage]) -> None:
    host = current_app.config.get("SMTP_HOST")
    if not host:
        logger.warning("SMTP_HOST is not configured. Inquiry mail was not sent.")
        return

    port = current_app.config.get("SMTP_PORT", 587)
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    use_ssl = current_app.config.get("SMTP_USE_SSL", False)
    use_tls = current_app.config.get("SMTP_USE_TLS", True)

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(host, port, timeout=20) as smtp:
        if not use_ssl and use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        for message in messages:
            smtp.send_message(message)


def send_inquiry_mails(inquiry: Inquiry) -> None:
    admin_recipients = _split_recipients(current_app.config.get("MAIL_TO", ""))
    if not admin_recipients:
        logger.warning("MAIL_TO is not configured. Inquiry mail was not sent.")
        return

    messages = [
        _message(
            f"【新規問い合わせ】詳細見積り依頼 #{inquiry.id}",
            admin_recipients,
            _admin_body(inquiry),
            reply_to=inquiry.email,
        ),
        _message(
            "【業務アプリ工房】お問い合わせを受け付けました",
            [inquiry.email],
            _customer_body(inquiry),
        ),
    ]
    _send_messages(messages)
    logger.info("Inquiry mail sent: inquiry_id=%s admin_to=%s customer_to=%s", inquiry.id, admin_recipients, inquiry.email)

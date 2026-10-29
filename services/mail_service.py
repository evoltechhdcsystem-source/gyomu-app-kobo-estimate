from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from flask import current_app, url_for

from models import Inquiry, PlanMaster, db
from services.estimate_display_service import estimate_item_label
from services.maintenance_service import GOOGLE_CLOUD_MONTHLY_MIN, monthly_total_label, monthly_total_note
from services.notification_context import attachment_lines

logger = logging.getLogger(__name__)


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _sender() -> str:
    company_name = current_app.config.get("COMPANY_NAME", "業務アプリ工房")
    mail_from = current_app.config.get("MAIL_FROM", "")
    return formataddr((company_name, mail_from)) if mail_from else ""


def _admin_body(inquiry: Inquiry) -> str:
    detail_url = url_for("admin.inquiry_detail", inquiry_id=inquiry.id, _external=True)
    estimate = inquiry.estimate
    plan = db.session.get(PlanMaster, estimate.plan_key)
    lines = [
        "お問い合わせ・詳細見積りの依頼を受け付けました。",
        "",
        f"管理画面：{detail_url}",
        "",
        "【お客様情報】",
        f"会社名：{inquiry.company_name}",
        f"担当者名：{inquiry.person_name}",
        f"メール：{inquiry.email}",
        f"電話番号：{inquiry.phone or '-'}",
        "",
        "【お見積り内容】",
        f"受付番号：#{inquiry.id}",
        f"見積ID：#{estimate.id}",
        f"プラン：{plan.name if plan else estimate.plan_key}",
        f"利用端末：{estimate.device_type}",
        f"パック：{estimate.package_type}",
        "",
        "【費用】",
        f"初期費用：{estimate.total_price:,}円（税抜・概算）",
    ]
    if estimate.plan_key == "full":
        lines.append(f"月額費用：{monthly_total_label(estimate).removesuffix('／月')}（税抜・概算）")
    if estimate.has_quote_required_items or (
        estimate.plan_key == "full" and estimate.maintenance_monthly_price is not None
        and estimate.maintenance_quote_required
    ):
        lines.append("※ 要相談の機能があります")
    lines.extend(["", "【見積項目】"])
    for item in estimate.items:
        name = estimate_item_label(item.item_name).replace(" x ", " × ")
        lines.append(f"・{name}：{item.price_label}")
    lines.append("")
    lines.extend(line.replace("添付ファイル: ", "添付ファイル：").replace("添付ファイル:", "添付ファイル：")
                 for line in attachment_lines(inquiry))
    return "\n".join(lines)


def _customer_body(inquiry: Inquiry) -> str:
    company_name = current_app.config.get("COMPANY_NAME", "業務アプリ工房")
    estimate = inquiry.estimate
    plan = db.session.get(PlanMaster, estimate.plan_key)
    lines = [
        f"{inquiry.person_name}様",
        "",
        "お問い合わせ・詳細見積りをご依頼いただき、ありがとうございます。",
        "以下の内容で受け付けました。担当者より折り返しご連絡いたします。",
        "",
        f"受付番号：#{inquiry.id}",
        f"見積ID：#{estimate.id}",
        "",
        "【お見積り内容】",
        f"プラン：{plan.name if plan else estimate.plan_key}",
        f"利用端末：{estimate.device_type}",
        f"パック：{estimate.package_type}",
        "",
        "【費用】",
        f"初期費用：{estimate.total_price:,}円（税抜・概算）",
    ]
    if estimate.has_quote_required_items:
        lines.append("※要相談の機能は、初期費用に含まれていません。")
    if estimate.plan_key == "full":
        lines.extend([
            "", f"月額費用：{monthly_total_label(estimate).removesuffix('／月')}（税抜・概算）",
            f"・Google Cloud利用料：月額{GOOGLE_CLOUD_MONTHLY_MIN:,}円（税抜・概算）",
        ])
        if estimate.maintenance_monthly_price is not None:
            if estimate.maintenance_quote_required:
                lines.append("・サーバー保守：要相談")
                lines.append(f"※{monthly_total_note(estimate)}")
            else:
                lines.append(f"・サーバー保守：月額{estimate.maintenance_monthly_price:,}円（税抜）")
        else:
            lines.append("※サーバー保守は含まれていません。")
        if estimate.maintenance_monthly_price is not None:
            lines.append("")
        lines.append("※ Google Cloud利用料は、利用するサービスや利用量、為替により変動します。")
    lines.extend(["", "【見積項目】"])
    lines.extend(f"・{estimate_item_label(item.item_name)}：{item.price_label}" for item in estimate.items)
    lines.extend([
        "",
        "【お問い合わせ内容】",
        inquiry.message or "-",
        "",
        "----------------------------------------",
        company_name,
        f"電話番号: {current_app.config.get('COMPANY_PHONE', '')}",
        f"メール: {current_app.config.get('COMPANY_EMAIL', current_app.config.get('MAIL_TO', ''))}",
    ])
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

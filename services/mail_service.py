from __future__ import annotations

import logging

from models import Inquiry

logger = logging.getLogger(__name__)


def send_inquiry_mails(inquiry: Inquiry) -> None:
    """Local mail stub. Wire SES or SMTP here for production."""
    logger.info(
        "Mail queued: customer_subject=%s admin_subject=%s inquiry_id=%s email=%s",
        "【業務アプリ工房】お問い合わせありがとうございます",
        "【新規問い合わせ】",
        inquiry.id,
        inquiry.email,
    )


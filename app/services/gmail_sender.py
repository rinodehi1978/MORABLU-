"""Gmail SMTP経由でAmazonバイヤーに返信するサービス

Amazonのバイヤー-セラーメッセージングの仕組み:
- Amazonからの転送メールにはReply-To に暗号化エイリアス
  (例: xxxx@marketplace.amazon.co.jp) が含まれる
- このアドレスにメールを送ると、Amazonがバイヤーに中継する
- セラーの実際のメールアドレスはバイヤーには見えない

前提条件:
- 各GmailアドレスがSeller Centralの「承認済み送信者」に登録済みであること
"""

import logging
import smtplib
import ssl
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)

# アカウント名 → Gmail設定のマッピング
_ACCOUNT_GMAIL = {
    "MORABLU": {
        "address_key": "gmail_morablu_address",
        "password_key": "gmail_morablu_app_password",
    },
    "2ndMORABLU": {
        "address_key": "gmail_2ndmorablu_address",
        "password_key": "gmail_2ndmorablu_app_password",
    },
    "CHA3": {
        "address_key": "gmail_cha3_address",
        "password_key": "gmail_cha3_app_password",
    },
}


def send_reply(
    account_name: str,
    reply_to_address: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
) -> bool:
    """Gmail SMTP経由でAmazonバイヤーに返信を送信する

    Args:
        account_name: アカウント名 (MORABLU, 2ndMORABLU, CHA3)
        reply_to_address: Amazon暗号化エイリアス (xxx@marketplace.amazon.co.jp)
        subject: 件名 (Re: が付いていなければ自動付与)
        body: 返信本文
        in_reply_to: 元メールのMessage-ID (スレッド紐づけ用)

    Returns:
        送信成功ならTrue
    """
    gmail_config = _ACCOUNT_GMAIL.get(account_name)
    if not gmail_config:
        logger.error("Unknown account: %s", account_name)
        return False

    from_address = getattr(settings, gmail_config["address_key"], "")
    app_password = getattr(settings, gmail_config["password_key"], "")

    if not from_address or not app_password:
        logger.error("Gmail credentials not configured for %s", account_name)
        return False

    # 件名にRe:がなければ付与
    if subject and not subject.startswith("Re:"):
        subject = f"Re: {subject}"

    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = from_address
    msg["To"] = reply_to_address
    msg["Subject"] = subject or "Re: Amazon お問い合わせ"

    # スレッド紐づけ用ヘッダー
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            "smtp.gmail.com", 465, context=context,
            timeout=15, local_hostname="localhost",
        ) as server:
            server.login(from_address, app_password)
            server.send_message(msg)

        logger.info(
            "Reply sent: account=%s, to=%s, subject=%s",
            account_name,
            reply_to_address,
            subject,
        )
        return True

    except Exception:
        logger.exception("Failed to send reply for %s", account_name)
        return False

"""Gmail IMAP経由でAmazonカスタマーメッセージを取得・保存するサービス

フロー:
1. 各アカウントのGmailにIMAP接続
2. Amazon marketplace からのメールを検索
3. メール本文をパースして構造化データに変換
4. 重複チェック（external_message_id）してDBに保存
"""

import imaplib
import email
import logging
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.models.account import Account
from app.models.message import Message

logger = logging.getLogger(__name__)

# アカウントごとのGmail設定
GMAIL_ACCOUNTS = {
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


def fetch_all_accounts(db: Session) -> dict:
    """全アカウントのGmailからメッセージを取得してDBに保存する

    Returns:
        {"MORABLU": {"fetched": 3, "new": 2, "error": None}, ...}
    """
    results = {}
    for account_name, gmail_config in GMAIL_ACCOUNTS.items():
        addr = getattr(settings, gmail_config["address_key"], "")
        pwd = getattr(settings, gmail_config["password_key"], "")

        if not addr or not pwd:
            results[account_name] = {
                "fetched": 0,
                "new": 0,
                "error": "Gmail認証情報未設定",
            }
            continue

        # パスワードの特殊空白を除去
        pwd = pwd.replace(" ", "").replace("\xa0", "").replace("\u3000", "").strip()

        try:
            fetched, new_count = _fetch_account_messages(
                db, account_name, addr, pwd
            )
            results[account_name] = {
                "fetched": fetched,
                "new": new_count,
                "error": None,
            }
        except Exception as e:
            logger.exception("Gmail fetch failed for %s", account_name)
            results[account_name] = {
                "fetched": 0,
                "new": 0,
                "error": str(e),
            }

    return results


def _fetch_account_messages(
    db: Session, account_name: str, gmail_address: str, app_password: str
) -> tuple[int, int]:
    """1アカウント分のGmailからメッセージを取得（受信+送信済み）

    Returns:
        (取得件数, 新規保存件数)
    """
    # DBのアカウントを取得（なければ作成）
    account = db.query(Account).filter(Account.name == account_name).first()
    if not account:
        account = Account(name=account_name, channel="amazon")
        db.add(account)
        db.commit()
        db.refresh(account)

    # 検索日付: 90日前から（古い顧客からの再問い合わせにも対応）
    since_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%d-%b-%Y")

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(gmail_address, app_password)

    fetched = 0
    new_count = 0

    # --- 受信メール（INBOX）---
    mail.select("INBOX", readonly=True)
    status, data = mail.search(
        None, f'(FROM "marketplace.amazon" SINCE "{since_date}")'
    )
    if status == "OK" and data[0]:
        f, n = _process_emails(
            db, mail, data[0].split(), account, direction="inbound"
        )
        fetched += f
        new_count += n

    # --- 送信済みメール → 返信ログとして取り込む ---
    # Gmailの送信済みフォルダ名（日本語環境 / 英語環境）
    sent_folders = [
        '"[Gmail]/&kAFP4W4IMH8w4TD8MOs-"',  # 日本語Gmail: 送信済みメール
        '"[Gmail]/Sent Mail"',               # 英語Gmail
    ]
    for folder in sent_folders:
        try:
            status, _ = mail.select(folder, readonly=True)
            if status != "OK":
                continue

            status, data = mail.search(
                None, f'(TO "marketplace.amazon" SINCE "{since_date}")'
            )
            if status == "OK" and data[0]:
                f, n = _process_emails(
                    db, mail, data[0].split(), account, direction="outbound"
                )
                fetched += f
                new_count += n
            break  # 成功したフォルダがあれば終了
        except Exception:
            continue

    db.commit()
    mail.logout()

    logger.info(
        "Gmail fetch %s: %d fetched, %d new",
        account_name,
        fetched,
        new_count,
    )
    return fetched, new_count


def _process_emails(
    db: Session,
    mail: imaplib.IMAP4_SSL,
    msg_ids: list,
    account,
    direction: str,
) -> tuple[int, int]:
    """メールリストを処理してDBに保存する

    最適化: ヘッダー(Message-ID)だけ先に取得して重複チェックし、
    新しいメールだけフルダウンロードすることで大幅に高速化。
    """
    if not msg_ids:
        return 0, 0

    # DB内の既存Message-IDを一括取得（高速な重複チェック用）
    existing_ids = set(
        row[0]
        for row in db.query(Message.external_message_id)
        .filter(
            Message.account_id == account.id,
            Message.external_message_id.isnot(None),
        )
        .all()
    )

    # Step 1: Message-IDヘッダーを一括取得して高速フィルタリング
    # 一括fetchはIMAPラウンドトリップ1回で済むため大幅に高速
    new_mids = []
    try:
        ids_csv = b",".join(msg_ids)
        _, bulk_data = mail.fetch(ids_csv, "(BODY[HEADER.FIELDS (MESSAGE-ID)])")
        # bulk_dataは [(b'1 ...', b'Message-ID: ...'), b')', ...] のフラット構造
        idx = 0
        for item in bulk_data:
            if isinstance(item, tuple) and len(item) == 2:
                seq_line = item[0]  # e.g. b'1 (BODY[HEADER.FIELDS ...'
                hdr_raw = item[1]
                # シーケンス番号をmsg_idsと対応付け
                mid = msg_ids[idx] if idx < len(msg_ids) else None
                idx += 1
                if mid is None:
                    continue
                hdr_msg = email.message_from_bytes(hdr_raw)
                msg_id = hdr_msg.get("Message-ID", "").strip()
                if msg_id and msg_id in existing_ids:
                    continue
                new_mids.append((mid, msg_id))
    except Exception:
        logger.warning(
            "%s %s: bulk header fetch failed, falling back to individual fetch",
            account.name, direction,
        )
        new_mids = [(mid, "") for mid in msg_ids]

    logger.info(
        "%s %s: %d/%d emails are new (skipped %d duplicates)",
        account.name, direction, len(new_mids), len(msg_ids),
        len(msg_ids) - len(new_mids),
    )

    # Step 2: 新しいメールだけフルダウンロード＆処理
    fetched = 0
    new_count = 0

    for mid, pre_msg_id in new_mids:
        try:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            gmail_msg_id = msg.get("Message-ID", "").strip() or pre_msg_id
            if gmail_msg_id and gmail_msg_id in existing_ids:
                continue

            # Message-IDが空の場合: 送信者+件名+日付で重複チェック
            if not gmail_msg_id:
                date_str = msg.get("Date", "")
                try:
                    msg_date = parsedate_to_datetime(date_str)
                except Exception:
                    msg_date = None
                subj_raw = _decode_header(msg.get("Subject", ""))
                dup_query = db.query(Message).filter(
                    Message.account_id == account.id,
                    Message.external_message_id.is_(None),
                )
                if msg_date:
                    dup_query = dup_query.filter(
                        Message.received_at == msg_date,
                    )
                if subj_raw:
                    dup_query = dup_query.filter(
                        Message.subject == subj_raw,
                    )
                if dup_query.first():
                    continue

            if direction == "inbound":
                parsed = _parse_amazon_email(msg)
                if not parsed:
                    continue
                fetched += 1

                new_msg = Message(
                    account_id=account.id,
                    external_order_id=parsed["order_id"],
                    external_message_id=gmail_msg_id or None,
                    sender=parsed["sender"],
                    subject=parsed["subject"],
                    body=parsed["message"],
                    direction="inbound",
                    status="new",
                    asin=parsed["asin"],
                    product_title=parsed["product_title"],
                    reply_to_address=parsed["reply_to_address"],
                    received_at=parsed["date"],
                )
            else:
                parsed = _parse_sent_email(msg)
                if not parsed:
                    continue
                fetched += 1

                new_msg = Message(
                    account_id=account.id,
                    external_order_id=parsed["order_id"],
                    external_message_id=gmail_msg_id or None,
                    sender=account.name,
                    subject=parsed["subject"],
                    body=parsed["message"],
                    direction="outbound",
                    status="sent",
                    received_at=parsed["date"],
                )

            db.add(new_msg)
            new_count += 1
            if gmail_msg_id:
                existing_ids.add(gmail_msg_id)

        except Exception:
            logger.exception("Failed to parse email %s (direction=%s)", mid, direction)
            continue

    return fetched, new_count


def _parse_amazon_email(msg: email.message.Message) -> dict | None:
    """Amazonメッセージ通知メールをパースして構造化データにする

    Returns:
        {sender, subject, order_id, asin, product_title, message, date}
        パース失敗時はNone
    """
    # Fromヘッダーから送信者名を取得
    from_raw = msg.get("From", "")
    from_decoded = _decode_header(from_raw)

    # Amazon marketplaceからのメールかチェック
    if "marketplace.amazon" not in from_decoded:
        return None

    sender_match = re.match(r"(.+?)\s*<", from_decoded)
    sender = sender_match.group(1).strip() if sender_match else "不明"

    # 件名
    subject = _decode_header(msg.get("Subject", ""))

    # 本文
    body = _get_plain_text(msg)
    if not body:
        return None

    # 注文番号
    order_match = re.search(r"(\d{3}-\d{7}-\d{7})", subject + body)
    order_id = order_match.group(1) if order_match else None

    # ASIN
    asin_match = re.search(r"\[ASIN:\s*(B[A-Z0-9]+)\]", body)
    asin = asin_match.group(1) if asin_match else None

    # 商品名（# ORDER の次行）
    product_title = None
    prod_match = re.search(
        r"# \d{3}-\d{7}-\d{7}:\n\d+ / (.+?)(?:\s*\[ASIN:)", body
    )
    if prod_match:
        product_title = prod_match.group(1).strip()

    # メッセージ本文（------------- 区切り線の間）
    customer_msg = _extract_message_body(body)
    if not customer_msg:
        return None

    # 日時
    date_str = msg.get("Date", "")
    try:
        msg_date = parsedate_to_datetime(date_str)
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
    except Exception:
        msg_date = datetime.now(timezone.utc)

    # Reply-Toアドレス（Amazon暗号化エイリアス: xxx@marketplace.amazon.co.jp）
    reply_to_raw = _decode_header(msg.get("Reply-To", ""))
    reply_to_match = re.search(r"[\w.+-]+@marketplace\.amazon\.\w+", reply_to_raw)
    reply_to_address = reply_to_match.group(0) if reply_to_match else None

    return {
        "sender": sender,
        "subject": subject,
        "order_id": order_id,
        "asin": asin,
        "product_title": product_title,
        "message": customer_msg,
        "date": msg_date,
        "reply_to_address": reply_to_address,
    }


def _parse_sent_email(msg: email.message.Message) -> dict | None:
    """送信済みメール（Amazonバイヤーへの返信）をパースする

    Returns:
        {subject, order_id, message, date}
        パース失敗時はNone
    """
    # Toヘッダーにmarketplace.amazonが含まれるか確認
    to_raw = _decode_header(msg.get("To", ""))
    if "marketplace.amazon" not in to_raw:
        return None

    subject = _decode_header(msg.get("Subject", ""))

    body = _get_plain_text(msg)
    if not body:
        return None

    # 注文番号を件名+本文から抽出
    order_match = re.search(r"(\d{3}-\d{7}-\d{7})", subject + body)
    order_id = order_match.group(1) if order_match else None

    # 送信メールの本文はそのまま使う（区切り線パースは不要）
    # ただしGmailの引用部分（> で始まる行や「On ... wrote:」以降）を除去
    clean_lines = []
    for line in body.split("\n"):
        # 引用ヘッダー（「On 2026/02/... wrote:」等）を検出したら終了
        if re.match(r"^(On |>|---.*---$|20\d{2}/\d{1,2}/\d{1,2}.*wrote:)", line.strip()):
            break
        clean_lines.append(line)

    message = "\n".join(clean_lines).strip()
    if not message:
        return None

    # 日時
    date_str = msg.get("Date", "")
    try:
        msg_date = parsedate_to_datetime(date_str)
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)
    except Exception:
        msg_date = datetime.now(timezone.utc)

    return {
        "subject": subject,
        "order_id": order_id,
        "message": message,
        "date": msg_date,
    }


def _extract_message_body(body: str) -> str | None:
    """メール本文から顧客のメッセージ部分だけを抽出する

    区切り: ------------- メッセージ: ------------- と
           ------------- メッセージはここまで -------------
    """
    lines = body.split("\n")
    in_msg = False
    msg_lines = []

    for line in lines:
        stripped = line.strip()
        if re.match(r"^-{5,}.*-{5,}$", stripped):
            if not in_msg:
                in_msg = True
                continue
            else:
                break
        if in_msg:
            msg_lines.append(line)

    result = "\n".join(msg_lines).strip()
    return result if result else None


def _decode_header(raw: str) -> str:
    """メールヘッダーのエンコード済み文字列をデコード"""
    if not raw:
        return ""
    parts = decode_header(raw)
    decoded = []
    for data, charset in parts:
        if isinstance(data, bytes):
            decoded.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(data)
    return "".join(decoded)


def _get_plain_text(msg: email.message.Message) -> str:
    """メールからプレーンテキスト本文を取得"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""

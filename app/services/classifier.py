"""AI自動カテゴリ分類サービス

顧客メッセージを受信したら、まずこのサービスで質問カテゴリを自動分類する。
スタッフが修正した分類履歴を学習し、精度を向上させていく。
"""

import json
import logging
import re

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

CATEGORIES = {
    "shipping": "発送・配送（いつ届くか、配送状況の確認）",
    "defect": "商品不備・不良（壊れている、動かない、傷がある）",
    "return": "返品・交換の依頼",
    "refund": "返金の依頼",
    "cancel": "注文キャンセル",
    "spec": "商品の仕様・適合確認（サイズ、対応機種など）",
    "receipt": "領収書・請求書の発行依頼",
    "address": "届け先の変更",
    "delivery_time": "配送日時・時間指定",
    "resend": "再送依頼",
    "stock": "欠品・在庫切れ",
    "other": "上記に該当しない問い合わせ",
}


async def classify_message(
    message_body: str,
    subject: str | None = None,
    correction_history: list[dict] | None = None,
) -> str:
    """顧客メッセージのカテゴリを自動分類する。

    Args:
        message_body: 顧客のメッセージ本文
        subject: メッセージの件名
        correction_history: スタッフの過去の修正履歴
            [{"message": "...", "ai_category": "shipping", "correct_category": "defect"}, ...]

    Returns:
        カテゴリ文字列（"shipping", "defect" 等）
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    category_list = "\n".join(
        f"- {key}: {desc}" for key, desc in CATEGORIES.items()
    )

    system = f"""\
あなたはカスタマーサポートメッセージの分類AIです。
顧客のメッセージを読み、以下のカテゴリのうち最も適切なものを1つ選んでください。

カテゴリ一覧:
{category_list}

回答はカテゴリのキー（英語）のみをJSON形式で返してください。
例: {{"category": "shipping"}}"""

    user_content = ""
    if subject:
        user_content += f"件名: {subject}\n"
    user_content += f"メッセージ:\n{message_body}"

    # スタッフの修正履歴があれば学習データとして含める
    if correction_history:
        user_content += "\n\n===== 過去の分類修正履歴（学習データ） ====="
        user_content += "\n以下はAIの分類をスタッフが修正した事例です。同様のケースでは修正後のカテゴリを参考にしてください。\n"
        for h in correction_history[-20:]:  # 直近20件まで
            user_content += (
                f"\n- メッセージ要約: {h['message_summary']}\n"
                f"  AI分類: {h['ai_category']} → スタッフ修正: {h['correct_category']}\n"
            )

    try:
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=100,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = response.content[0].text.strip()

        # マークダウンのコードブロック除去: ```json {...} ```
        json_match = re.search(r"\{[^}]+\}", raw_text)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = json.loads(raw_text)

        category = result.get("category", "other")
        if category not in CATEGORIES:
            category = "other"
        return category
    except Exception:
        logger.exception("Message classification failed")
        return "other"

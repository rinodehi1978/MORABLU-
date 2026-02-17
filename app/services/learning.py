"""学習データの蓄積・検索サービス

スタッフの対応履歴を蓄積し、次回以降のAI回答生成に活用する。
"""

import logging

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.response import AiResponse

logger = logging.getLogger(__name__)


def find_past_responses_by_product(
    db: Session, asin: str, limit: int = 5
) -> list[dict]:
    """同じ商品(ASIN)の過去のスタッフ回答を検索する"""
    results = (
        db.query(Message, AiResponse)
        .join(AiResponse, AiResponse.message_id == Message.id)
        .filter(
            and_(
                Message.asin == asin,
                AiResponse.is_sent.is_(True),
                AiResponse.final_body.isnot(None),
            )
        )
        .order_by(AiResponse.sent_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "customer_question": msg.body[:200],
            "question_category": msg.question_category,
            "staff_answer": resp.final_body,
            "product_title": msg.product_title,
        }
        for msg, resp in results
    ]


def find_past_responses_by_category(
    db: Session, category: str, limit: int = 5, exclude_asin: str | None = None
) -> list[dict]:
    """同じカテゴリの過去のスタッフ回答を検索する"""
    query = (
        db.query(Message, AiResponse)
        .join(AiResponse, AiResponse.message_id == Message.id)
        .filter(
            and_(
                Message.question_category == category,
                AiResponse.is_sent.is_(True),
                AiResponse.final_body.isnot(None),
            )
        )
    )

    # 同一商品の結果は除外（既にproduct検索で取得済みのため）
    if exclude_asin:
        query = query.filter(Message.asin != exclude_asin)

    results = (
        query.order_by(AiResponse.sent_at.desc()).limit(limit).all()
    )

    return [
        {
            "customer_question": msg.body[:200],
            "question_category": msg.question_category,
            "staff_answer": resp.final_body,
            "product_title": msg.product_title,
        }
        for msg, resp in results
    ]


def find_category_corrections(
    db: Session, limit: int = 30
) -> list[dict]:
    """AIの分類をスタッフが修正した履歴を取得する（分類学習用）"""
    results = (
        db.query(Message, AiResponse)
        .join(AiResponse, AiResponse.message_id == Message.id)
        .filter(
            and_(
                AiResponse.is_sent.is_(True),
                AiResponse.ai_suggested_category.isnot(None),
                Message.question_category.isnot(None),
                # AIの提案とスタッフの最終分類が異なるもの＝修正された事例
                AiResponse.ai_suggested_category != Message.question_category,
            )
        )
        .order_by(AiResponse.sent_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "message_summary": msg.body[:100],
            "ai_category": resp.ai_suggested_category,
            "correct_category": msg.question_category,
        }
        for msg, resp in results
    ]


def save_learning_data(
    db: Session,
    message: Message,
    ai_response: AiResponse,
    corrected_category: str | None,
):
    """送信時に学習データを保存する

    - スタッフがカテゴリを修正した場合 → メッセージのカテゴリを更新
    - AI提案カテゴリを記録（次回の分類精度向上のため）
    """
    if corrected_category and corrected_category != message.question_category:
        logger.info(
            "Category corrected: %s -> %s (message_id=%d)",
            message.question_category,
            corrected_category,
            message.id,
        )
        message.question_category = corrected_category

    db.flush()

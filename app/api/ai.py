import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.account import Account
from app.models.message import Message
from app.models.qa_template import QaTemplate
from app.models.response import AiResponse
from app.schemas.response import AiResponseCreate, AiResponseRead, AiResponseSend
from app.services.ai_responder import generate_draft
from app.services.product_catalog import (
    format_product_for_prompt,
    get_product_info,
)
from app.services.learning import (
    find_past_responses_by_category,
    find_past_responses_by_product,
    save_learning_data,
)
from app.services.gmail_sender import send_reply
from app.services.order_info import (
    format_order_info_for_prompt,
    get_order_info,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


def _send_and_record(
    db: Session,
    message: Message,
    final_body: str,
) -> bool:
    """Gmail SMTP送信 + outboundメッセージをDB記録する

    Returns:
        送信成功ならTrue
    """
    account = db.query(Account).filter(Account.id == message.account_id).first()
    account_name = account.name if account else "MORABLU"

    if not message.reply_to_address:
        logger.warning(
            "No reply_to_address for message %d, skipping email send",
            message.id,
        )
        return False

    # Gmail SMTP送信
    sent = send_reply(
        account_name=account_name,
        reply_to_address=message.reply_to_address,
        subject=message.subject or "Amazon お問い合わせ",
        body=final_body,
        in_reply_to=message.external_message_id,
    )

    if sent:
        # 送信メッセージをoutboundとしてDB記録（スレッド表示用）
        outbound_msg = Message(
            account_id=message.account_id,
            external_order_id=message.external_order_id,
            sender=account_name,
            subject=f"Re: {message.subject}" if message.subject else "Re: Amazon お問い合わせ",
            body=final_body,
            direction="outbound",
            status="sent",
            asin=message.asin,
            product_title=message.product_title,
            question_category=message.question_category,
            received_at=datetime.now(timezone.utc),
        )
        db.add(outbound_msg)

    return sent


def find_relevant_templates(
    db: Session, message_body: str, subject: str | None, platform: str = "amazon"
) -> list[dict]:
    """メッセージ内容からキーワードで関連するQ&Aテンプレートを検索する

    販路フィルター: 指定された販路用 + 共通(common) のテンプレートのみ返す
    """
    keywords = [
        ("発送", "配送", "届", "いつ届"),
        ("不備", "不良", "壊れ", "破損", "不具合"),
        ("返品", "交換", "返送"),
        ("返金", "払い戻し"),
        ("キャンセル",),
        ("領収書", "請求書", "インボイス"),
        ("適合", "仕様", "スペック", "車検"),
        ("届け先", "届先", "住所変更", "届け先変更"),
        ("日時指定", "時間指定", "配送日"),
        ("再送", "もう一度送"),
        ("欠品", "在庫切れ", "品切れ"),
        ("郵便局留め", "営業所留め", "局留"),
        ("離島", "送料"),
    ]

    search_text = (message_body + " " + (subject or "")).lower()

    # 販路フィルター（指定販路 + 共通）
    platform_filter = QaTemplate.platform.in_([platform, "common"])

    matched_keywords = []
    for group in keywords:
        for kw in group:
            if kw in search_text:
                matched_keywords.extend(group)
                break

    if not matched_keywords:
        templates = (
            db.query(QaTemplate)
            .filter(platform_filter)
            .limit(10)
            .all()
        )
    else:
        conditions = [
            QaTemplate.category.ilike(f"%{kw}%") for kw in matched_keywords
        ]
        templates = (
            db.query(QaTemplate)
            .filter(platform_filter, or_(*conditions))
            .limit(10)
            .all()
        )

    return [
        {
            "category": t.category,
            "subcategory": t.subcategory,
            "platform": t.platform,
            "answer_template": t.answer_template,
            "staff_notes": t.staff_notes,
        }
        for t in templates
    ]




@router.get("/responses/{message_id}", response_model=list[AiResponseRead])
async def get_responses(message_id: int, db: Session = Depends(get_db)):
    """メッセージに紐づくAI回答履歴を取得する（新しい順）"""
    responses = (
        db.query(AiResponse)
        .filter(AiResponse.message_id == message_id)
        .order_by(AiResponse.id.desc())
        .all()
    )
    return responses


@router.delete("/{response_id}/discard")
async def discard_draft(response_id: int, db: Session = Depends(get_db)):
    """未送信の下書きを破棄する

    - 送信済みの回答は破棄できない
    - 破棄後、他に未送信の回答がなければメッセージのステータスを適切に戻す
    """
    ai_response = (
        db.query(AiResponse).filter(AiResponse.id == response_id).first()
    )
    if not ai_response:
        raise HTTPException(status_code=404, detail="Response not found")
    if ai_response.is_sent:
        raise HTTPException(
            status_code=400, detail="送信済みの回答は破棄できません"
        )

    message = (
        db.query(Message)
        .filter(Message.id == ai_response.message_id)
        .first()
    )

    # 下書きを削除
    db.delete(ai_response)

    # メッセージのステータスを適切に戻す
    if message:
        remaining = (
            db.query(AiResponse)
            .filter(
                AiResponse.message_id == message.id,
                AiResponse.id != response_id,
            )
            .all()
        )
        has_sent = any(r.is_sent for r in remaining)
        has_draft = any(not r.is_sent for r in remaining)

        if has_sent:
            message.status = "sent"
        elif has_draft:
            message.status = "ai_drafted"
        else:
            message.status = "new"

    db.commit()
    return {"detail": "下書きを破棄しました", "message_status": message.status if message else None}


@router.post("/generate", response_model=AiResponseRead, status_code=201)
async def generate_response(
    data: AiResponseCreate, db: Session = Depends(get_db)
):
    """メッセージに対するAI回答案を生成する

    処理フロー:
    1. スタッフが選択済みのカテゴリをDBから取得
    2. 注文情報をSP API Ordersから取得（ステータス、配送情報）
    3. 商品情報をSP APIから取得（DBキャッシュ優先）
    4. 同じ商品(ASIN)の過去対応履歴を検索
    5. Q&Aテンプレートを検索
    6. 同カテゴリの過去対応履歴を検索
    7. 全情報をClaudeに渡して回答案を生成
    """
    message = db.query(Message).filter(Message.id == data.message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    try:
        # --- Step 1: スタッフ選択済みカテゴリを使用 ---
        staff_category = message.question_category or "other"

        # アカウント情報取得
        account = db.query(Account).filter(
            Account.id == message.account_id
        ).first()
        account_name = account.name if account else "MORABLU"

        # --- Step 2: 注文情報取得（SP API Orders） ---
        order_status_text = None
        if message.external_order_id:
            order_info = get_order_info(
                message.external_order_id, account_name=account_name
            )
            order_status_text = format_order_info_for_prompt(order_info)

        # --- Step 3: 商品情報取得（SP API → DBキャッシュ） ---
        product_info_text = None
        if message.asin:
            product_data = get_product_info(db, message.asin, account_name=account_name)
            if product_data:
                product_info_text = format_product_for_prompt(product_data)
                # メッセージの商品名が空ならカタログから補完
                if not message.product_title and product_data.get("title"):
                    message.product_title = product_data["title"]

        # --- Step 4: 同一商品の過去対応履歴 ---
        past_product = []
        if message.asin:
            past_product = find_past_responses_by_product(db, message.asin)

        # --- Step 5: Q&Aテンプレート検索（販路でフィルター） ---
        platform = account.channel if account else "amazon"
        qa_templates = find_relevant_templates(
            db, message.body, message.subject, platform=platform
        )

        # --- Step 6: 同カテゴリの過去対応履歴 ---
        past_category = find_past_responses_by_category(
            db, staff_category, exclude_asin=message.asin
        )

        # --- Step 7: AI回答案生成 ---
        result = await generate_draft(
            customer_message=message.body,
            subject=message.subject,
            order_id=message.external_order_id,
            asin=message.asin,
            product_title=message.product_title,
            question_category=staff_category,
            product_info=product_info_text,
            order_status_info=order_status_text,
            qa_templates=qa_templates,
            past_product_responses=past_product,
            past_category_responses=past_category,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("AI generate failed")
        raise HTTPException(
            status_code=502,
            detail=f"AI生成エラー: {type(e).__name__}: {e}",
        )

    ai_response = AiResponse(
        message_id=message.id,
        draft_body=result["text"],
        ai_suggested_category=staff_category,
        input_tokens=result.get("input_tokens"),
        output_tokens=result.get("output_tokens"),
        model_used=result.get("model"),
    )
    db.add(ai_response)
    message.status = "ai_drafted"
    db.commit()
    db.refresh(ai_response)
    return ai_response


@router.put("/{response_id}/send", response_model=AiResponseRead)
async def send_response(
    response_id: int,
    data: AiResponseSend,
    db: Session = Depends(get_db),
):
    """スタッフが確認・修正した回答を送信する

    学習ループ:
    - スタッフの最終回答(final_body)を正解データとして保存
    - カテゴリが修正された場合、修正履歴として保存（次回のAI分類精度向上）
    """
    ai_response = (
        db.query(AiResponse).filter(AiResponse.id == response_id).first()
    )
    if not ai_response:
        raise HTTPException(status_code=404, detail="Response not found")

    message = (
        db.query(Message)
        .filter(Message.id == ai_response.message_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # 回答を確定
    ai_response.final_body = data.final_body
    ai_response.is_sent = True
    ai_response.sent_at = datetime.now(timezone.utc)
    message.status = "sent"

    # 同じメッセージの他の未送信下書きを自動削除
    stale_drafts = (
        db.query(AiResponse)
        .filter(
            AiResponse.message_id == message.id,
            AiResponse.id != ai_response.id,
            AiResponse.is_sent == False,
        )
        .all()
    )
    for draft in stale_drafts:
        db.delete(draft)

    # 学習データ保存（カテゴリ修正があれば反映）
    save_learning_data(
        db=db,
        message=message,
        ai_response=ai_response,
        corrected_category=data.corrected_category,
    )

    # Gmail SMTP送信 + outboundメッセージ記録
    sent = _send_and_record(db, message, data.final_body)
    if not sent:
        logger.warning(
            "Email send failed for response %d (reply_to_address missing or SMTP error). "
            "Response saved as sent in DB but email not delivered.",
            ai_response.id,
        )

    db.commit()
    db.refresh(ai_response)

    return ai_response


@router.post("/send-direct", response_model=AiResponseRead, status_code=201)
async def send_direct(
    data: AiResponseSend,
    db: Session = Depends(get_db),
):
    """テンプレートから直接送信（AI生成なし）

    スタッフがテンプレートを選んで編集・送信する場合に使う。
    AiResponseレコードを作成し、即座に送信済みにする。
    """
    if not data.message_id:
        raise HTTPException(status_code=400, detail="message_id is required")

    message = db.query(Message).filter(Message.id == data.message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # 既存の未送信下書きを削除
    stale_drafts = (
        db.query(AiResponse)
        .filter(
            AiResponse.message_id == message.id,
            AiResponse.is_sent == False,
        )
        .all()
    )
    for draft in stale_drafts:
        db.delete(draft)

    # 送信済みレコードを作成
    ai_response = AiResponse(
        message_id=message.id,
        draft_body=data.final_body,  # テンプレート送信ではdraft=final
        final_body=data.final_body,
        ai_suggested_category=message.question_category,
        is_sent=True,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(ai_response)
    message.status = "sent"

    # 学習データ保存
    save_learning_data(
        db=db,
        message=message,
        ai_response=ai_response,
        corrected_category=data.corrected_category,
    )

    # Gmail SMTP送信 + outboundメッセージ記録
    sent = _send_and_record(db, message, data.final_body)
    if not sent:
        logger.warning(
            "Email send failed for direct-send message %d. "
            "Response saved as sent in DB but email not delivered.",
            message.id,
        )

    db.commit()
    db.refresh(ai_response)
    return ai_response


# Claude Sonnet 4.5 料金（USD per token）
_INPUT_PRICE_PER_TOKEN = 3.00 / 1_000_000
_OUTPUT_PRICE_PER_TOKEN = 15.00 / 1_000_000


@router.get("/usage")
def get_ai_usage(
    year: int = Query(...),
    month: int = Query(...),
    db: Session = Depends(get_db),
):
    """月次AI利用統計をアカウント別に集計する

    Returns:
        accounts: アカウント別の利用回数・トークン数・推定コスト
        total: 全アカウント合計
    """
    # AiResponse + Message + Account を結合して集計
    rows = (
        db.query(
            Account.name.label("account_name"),
            func.count(AiResponse.id).label("count"),
            func.coalesce(func.sum(AiResponse.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AiResponse.output_tokens), 0).label("output_tokens"),
        )
        .join(Message, AiResponse.message_id == Message.id)
        .join(Account, Message.account_id == Account.id)
        .filter(
            extract("year", AiResponse.created_at) == year,
            extract("month", AiResponse.created_at) == month,
            AiResponse.input_tokens.isnot(None),
        )
        .group_by(Account.name)
        .all()
    )

    accounts = []
    total_count = 0
    total_input = 0
    total_output = 0
    total_cost = 0.0

    for row in rows:
        cost_usd = (
            row.input_tokens * _INPUT_PRICE_PER_TOKEN
            + row.output_tokens * _OUTPUT_PRICE_PER_TOKEN
        )
        accounts.append({
            "account_name": row.account_name,
            "count": row.count,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "cost_usd": round(cost_usd, 4),
        })
        total_count += row.count
        total_input += row.input_tokens
        total_output += row.output_tokens
        total_cost += cost_usd

    return {
        "year": year,
        "month": month,
        "accounts": accounts,
        "total": {
            "count": total_count,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": round(total_cost, 4),
        },
    }

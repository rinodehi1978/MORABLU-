from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.account import Account
from app.models.message import Message
from app.models.response import AiResponse
from app.schemas.message import MessageRead
from app.services.gmail_fetcher import fetch_all_accounts

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/", response_model=list[MessageRead])
def list_messages(
    account_id: int | None = Query(None),
    channel: str | None = Query(None),
    status: str | None = Query(None),
    search: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Message).options(joinedload(Message.account))

    if account_id:
        query = query.filter(Message.account_id == account_id)
    if channel:
        query = query.join(Account).filter(Account.channel == channel)
    if status:
        query = query.filter(Message.status == status)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Message.body.ilike(pattern),
                Message.subject.ilike(pattern),
                Message.sender.ilike(pattern),
            )
        )

    messages = (
        query.order_by(Message.received_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    result = []
    for msg in messages:
        data = MessageRead.model_validate(msg)
        data.account_name = msg.account.name if msg.account else None
        result.append(data)
    return result


@router.post("/fetch")
def fetch_messages(db: Session = Depends(get_db)):
    """Gmailから全アカウントのAmazonメッセージを取得してDBに保存する"""
    results = fetch_all_accounts(db)
    total_new = sum(r["new"] for r in results.values())
    return {
        "total_new": total_new,
        "accounts": results,
    }


@router.get("/{message_id}", response_model=MessageRead)
def get_message(message_id: int, db: Session = Depends(get_db)):
    msg = (
        db.query(Message)
        .options(joinedload(Message.account))
        .filter(Message.id == message_id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    data = MessageRead.model_validate(msg)
    data.account_name = msg.account.name if msg.account else None
    return data


@router.put("/{message_id}/handled")
def mark_handled(message_id: int, db: Session = Depends(get_db)):
    """メッセージを「対応済み」にマークする（既にSeller Central等で対応済みの場合）"""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = "handled"
    db.commit()
    return {"detail": "対応済みにしました", "id": msg.id, "status": msg.status}


@router.put("/{message_id}/reopen")
def reopen_message(message_id: int, db: Session = Depends(get_db)):
    """メッセージを「新着」に戻す"""
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.status = "new"
    db.commit()
    return {"detail": "新着に戻しました", "id": msg.id, "status": msg.status}


@router.put("/bulk-handled")
def bulk_mark_handled(message_ids: list[int], db: Session = Depends(get_db)):
    """複数メッセージを一括で「対応済み」にマークする"""
    updated = (
        db.query(Message)
        .filter(Message.id.in_(message_ids), Message.status == "new")
        .update({"status": "handled"}, synchronize_session=False)
    )
    db.commit()
    return {"detail": f"{updated}件を対応済みにしました", "updated": updated}


@router.get("/{message_id}/thread")
def get_thread(message_id: int, db: Session = Depends(get_db)):
    """注文番号ベースの会話スレッドを取得する

    同じ注文番号を持つ全メッセージ + 各メッセージの回答履歴を時系列で返す。
    注文番号がない場合は、指定メッセージ単体 + 回答を返す。
    """
    msg = (
        db.query(Message)
        .options(joinedload(Message.account))
        .filter(Message.id == message_id)
        .first()
    )
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # 同じ注文番号の全メッセージを取得（時系列順）
    if msg.external_order_id:
        thread_messages = (
            db.query(Message)
            .options(joinedload(Message.account))
            .filter(Message.external_order_id == msg.external_order_id)
            .order_by(Message.received_at.asc())
            .all()
        )
    else:
        thread_messages = [msg]

    # 各メッセージの回答履歴を取得
    thread = []
    for m in thread_messages:
        responses = (
            db.query(AiResponse)
            .filter(AiResponse.message_id == m.id)
            .order_by(AiResponse.id.asc())
            .all()
        )

        thread.append({
            "message": {
                "id": m.id,
                "sender": m.sender,
                "subject": m.subject,
                "body": m.body,
                "direction": m.direction,
                "status": m.status,
                "asin": m.asin,
                "product_title": m.product_title,
                "question_category": m.question_category,
                "received_at": m.received_at.isoformat(),
                "account_name": m.account.name if m.account else None,
                "external_order_id": m.external_order_id,
            },
            "responses": [
                {
                    "id": r.id,
                    "draft_body": r.draft_body,
                    "final_body": r.final_body,
                    "ai_suggested_category": r.ai_suggested_category,
                    "is_sent": r.is_sent,
                    "created_at": r.created_at.isoformat(),
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                }
                for r in responses
            ],
        })

    return {
        "order_id": msg.external_order_id,
        "thread": thread,
    }

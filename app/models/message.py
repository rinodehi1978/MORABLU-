from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    """カスタマーメッセージ"""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    # Amazon order ID or platform-specific identifier
    external_order_id: Mapped[str | None] = mapped_column(String(100))
    external_message_id: Mapped[str | None] = mapped_column(
        String(200), unique=True
    )
    sender: Mapped[str] = mapped_column(String(200))  # customer name/ID
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(
        String(10)
    )  # "inbound" or "outbound"
    status: Mapped[str] = mapped_column(
        String(20), default="new"
    )  # new / ai_drafted / reviewed / sent

    # 商品情報（注文APIから自動取得 or スタッフ入力）
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(100))
    product_title: Mapped[str | None] = mapped_column(String(500))

    # Amazon暗号化エイリアス（返信先アドレス）
    reply_to_address: Mapped[str | None] = mapped_column(String(300))

    # スタッフ手動分類
    question_category: Mapped[str | None] = mapped_column(
        String(50), index=True
    )  # shipping / defect / return / refund / cancel / spec / receipt / other

    received_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    account: Mapped["Account"] = relationship(back_populates="messages")
    ai_responses: Mapped[list["AiResponse"]] = relationship(
        back_populates="message"
    )

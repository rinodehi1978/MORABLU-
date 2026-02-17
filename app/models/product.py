from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductKnowledge(Base):
    """商品情報ナレッジベース（対応するほど賢くなる）"""

    __tablename__ = "product_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True)
    asin: Mapped[str | None] = mapped_column(String(20), index=True)
    sku: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(
        String(50)
    )  # "product_info", "shipping", "faq", "troubleshooting"
    content: Mapped[str] = mapped_column(Text)  # Knowledge content
    source: Mapped[str] = mapped_column(
        String(50), default="manual"
    )  # "manual", "learned_from_response"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

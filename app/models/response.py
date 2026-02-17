from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AiResponse(Base):
    """AI生成の回答案"""

    __tablename__ = "ai_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"))
    draft_body: Mapped[str] = mapped_column(Text)  # AI generated draft
    final_body: Mapped[str | None] = mapped_column(
        Text
    )  # Staff-edited version
    # AIが提案したカテゴリ（スタッフ修正前）
    ai_suggested_category: Mapped[str | None] = mapped_column(String(50))
    is_sent: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    message: Mapped["Message"] = relationship(back_populates="ai_responses")

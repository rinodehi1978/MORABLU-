from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    """販路アカウント（Amazon, Yahoo等）"""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))  # "MORABLU", "2ndMORABLU", "CHA3"
    channel: Mapped[str] = mapped_column(String(50))  # "amazon", "yahoo", "mercari"
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(back_populates="account")

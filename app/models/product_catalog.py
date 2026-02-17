from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProductCatalog(Base):
    """SP API Catalog Items から取得した商品マスタ（キャッシュ）"""

    __tablename__ = "product_catalog"

    id: Mapped[int] = mapped_column(primary_key=True)
    asin: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    brand: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)  # 商品説明文
    bullet_points: Mapped[str | None] = mapped_column(
        Text
    )  # 箇条書き（改行区切りで保存）
    product_type: Mapped[str | None] = mapped_column(
        String(200)
    )  # 商品カテゴリ
    color: Mapped[str | None] = mapped_column(String(100))
    size: Mapped[str | None] = mapped_column(String(100))
    image_url: Mapped[str | None] = mapped_column(String(500))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

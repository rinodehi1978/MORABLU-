from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QaTemplate(Base):
    """カスタマー対応Q&Aテンプレート"""

    __tablename__ = "qa_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_key: Mapped[str] = mapped_column(
        String(50), index=True, default="other"
    )  # カテゴリキー（shipping, defect, return, refund, cancel, spec, receipt, address, delivery_time, resend, stock, other）
    category: Mapped[str] = mapped_column(
        String(200), index=True
    )  # 問い合わせ内容（例: "商品の発送、配送はいつになりますか？"）
    subcategory: Mapped[str | None] = mapped_column(
        String(200)
    )  # 種類（例: "繁忙期の場合", "システムエラーで遅延の場合"）
    platform: Mapped[str] = mapped_column(
        String(50), index=True, default="common"
    )  # amazon / yahoo_auction / yahoo_shopping / mercari / rakuten / multi_channel / common
    answer_template: Mapped[str] = mapped_column(Text)  # 回答テンプレート
    staff_notes: Mapped[str | None] = mapped_column(
        Text
    )  # 対応・留意点（スタッフ向け）
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

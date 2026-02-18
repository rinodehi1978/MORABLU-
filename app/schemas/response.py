from datetime import datetime

from pydantic import BaseModel


class AiResponseCreate(BaseModel):
    message_id: int


class AiResponseRead(BaseModel):
    id: int
    message_id: int
    draft_body: str
    final_body: str | None = None
    ai_suggested_category: str | None = None
    is_sent: bool
    created_at: datetime
    sent_at: datetime | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_used: str | None = None

    model_config = {"from_attributes": True}


class AiResponseSend(BaseModel):
    final_body: str
    # テンプレート直送信時に使用
    message_id: int | None = None
    # スタッフが修正したカテゴリ（AIの分類が間違っていた場合）
    corrected_category: str | None = None

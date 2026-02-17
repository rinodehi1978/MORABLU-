from datetime import datetime

from pydantic import BaseModel


class MessageBase(BaseModel):
    account_id: int
    external_order_id: str | None = None
    external_message_id: str | None = None
    sender: str
    subject: str | None = None
    body: str
    direction: str = "inbound"
    status: str = "new"
    asin: str | None = None
    sku: str | None = None
    product_title: str | None = None
    question_category: str | None = None
    received_at: datetime


class MessageCreate(MessageBase):
    pass


class MessageRead(MessageBase):
    id: int
    created_at: datetime
    account_name: str | None = None

    model_config = {"from_attributes": True}


class MessageListParams(BaseModel):
    account_id: int | None = None
    channel: str | None = None
    status: str | None = None
    search: str | None = None
    skip: int = 0
    limit: int = 50

from datetime import datetime

from pydantic import BaseModel


class AccountBase(BaseModel):
    name: str
    channel: str
    is_active: bool = True


class AccountCreate(AccountBase):
    pass


class AccountRead(AccountBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}

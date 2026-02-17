"""販路チャネルの基底クラス。新しい販路を追加する際はこれを継承する。"""

from abc import ABC, abstractmethod
from datetime import datetime


class BaseChannel(ABC):
    """販路チャネルの抽象基底クラス"""

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """チャネル名を返す（"amazon", "yahoo" 等）"""

    @abstractmethod
    async def fetch_messages(
        self, since: datetime | None = None
    ) -> list[dict]:
        """新規メッセージを取得する。

        Returns:
            list of dicts with keys:
                - external_message_id
                - external_order_id (optional)
                - sender
                - subject (optional)
                - body
                - received_at
        """

    @abstractmethod
    async def send_reply(
        self, external_message_id: str, body: str
    ) -> bool:
        """メッセージに返信する。"""

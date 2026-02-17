"""Amazon SP API Messaging 連携サービス"""

import logging
from datetime import datetime

from app.services.base_channel import BaseChannel

logger = logging.getLogger(__name__)


class AmazonChannel(BaseChannel):
    """Amazon SP API 経由のメッセージ取得・返信"""

    def __init__(
        self,
        account_name: str,
        refresh_token: str,
        lwa_app_id: str,
        lwa_client_secret: str,
        marketplace_id: str,
        region: str = "FE",
    ):
        self.account_name = account_name
        self.refresh_token = refresh_token
        self.lwa_app_id = lwa_app_id
        self.lwa_client_secret = lwa_client_secret
        self.marketplace_id = marketplace_id
        self.region = region

    @property
    def channel_name(self) -> str:
        return "amazon"

    async def fetch_messages(
        self, since: datetime | None = None
    ) -> list[dict]:
        """SP API Messaging APIでメッセージを取得する。

        TODO: python-amazon-sp-api を使った実装
        - getMessagingActionsForOrder でオーダー単位のメッセージ取得
        - Notifications API で新着通知をリアルタイム取得する方法も検討
        """
        logger.info(
            "Fetching messages for %s (since=%s)", self.account_name, since
        )
        # Placeholder - SP API実装時にここを埋める
        return []

    async def send_reply(
        self, external_message_id: str, body: str
    ) -> bool:
        """SP API経由で返信を送信する。

        TODO: createConfirmOrderDetails or sendInvoice 等のアクションで返信
        """
        logger.info(
            "Sending reply for %s: message=%s",
            self.account_name,
            external_message_id,
        )
        # Placeholder
        return False

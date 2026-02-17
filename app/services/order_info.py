"""SP API Orders APIから注文情報を取得するサービス

フロー:
1. メッセージに注文番号(order_id)があれば SP API で注文ステータスを取得
2. クレデンシャル未設定の場合は「注文情報未取得」を返す
3. 取得できた場合は構造化データを返す

注文ステータス:
- Pending: 注文確定待ち
- Unshipped: 未発送
- PartiallyShipped: 一部発送済
- Shipped: 発送済み
- Canceled: キャンセル済み
- Unfulfillable: 発送不可
"""

import logging
from dataclasses import dataclass, field

from app.config import settings

logger = logging.getLogger(__name__)

# 注文ステータスの日本語ラベル
ORDER_STATUS_LABELS = {
    "Pending": "注文確定待ち",
    "Unshipped": "未発送",
    "PartiallyShipped": "一部発送済み",
    "Shipped": "発送済み",
    "Canceled": "キャンセル済み",
    "Unfulfillable": "発送不可",
    "InvoiceUnconfirmed": "請求書未確認",
    "PendingAvailability": "在庫確認待ち",
}


@dataclass
class OrderInfo:
    """注文情報の構造化データ"""

    order_id: str
    status: str | None = None
    status_label: str | None = None
    fulfillment_channel: str | None = None  # AFN=FBA, MFN=自社発送
    ship_date: str | None = None
    tracking_number: str | None = None
    carrier: str | None = None
    is_available: bool = False  # API取得に成功したか
    error_reason: str | None = None  # 取得失敗の理由
    items: list[dict] = field(default_factory=list)


def get_order_info(order_id: str, account_name: str = "MORABLU") -> OrderInfo:
    """注文番号から注文情報を取得する

    Args:
        order_id: Amazon注文番号
        account_name: アカウント名（MORABLU, 2ndMORABLU, CHA3）

    Returns:
        OrderInfo: 注文情報（取得失敗時は is_available=False）
    """
    if not order_id:
        return OrderInfo(
            order_id="",
            error_reason="注文番号なし",
        )

    # アカウントごとのクレデンシャルを取得
    creds = _get_credentials(account_name)
    if not creds:
        return OrderInfo(
            order_id=order_id,
            error_reason="SP APIクレデンシャル未設定",
        )

    return _fetch_order_from_sp_api(order_id, creds)


def _get_credentials(account_name: str) -> dict | None:
    """アカウント名からSP APIクレデンシャルを取得"""
    account_map = {
        "MORABLU": {
            "refresh_token": settings.amazon_morablu_refresh_token,
            "lwa_app_id": settings.amazon_morablu_lwa_app_id,
            "lwa_client_secret": settings.amazon_morablu_lwa_client_secret,
        },
        "2ndMORABLU": {
            "refresh_token": settings.amazon_2ndmorablu_refresh_token,
            "lwa_app_id": settings.amazon_2ndmorablu_lwa_app_id,
            "lwa_client_secret": settings.amazon_2ndmorablu_lwa_client_secret,
        },
        "CHA3": {
            "refresh_token": settings.amazon_cha3_refresh_token,
            "lwa_app_id": settings.amazon_cha3_lwa_app_id,
            "lwa_client_secret": settings.amazon_cha3_lwa_client_secret,
        },
    }

    creds = account_map.get(account_name)
    if not creds or not creds["refresh_token"]:
        return None
    return creds


def _fetch_order_from_sp_api(order_id: str, creds: dict) -> OrderInfo:
    """SP API Orders APIで注文情報を取得する

    使用API: GET /orders/v0/orders/{orderId}
    """
    try:
        from sp_api.api import Orders
        from sp_api.base import Marketplaces

        orders_api = Orders(
            marketplace=Marketplaces.JP,
            refresh_token=creds["refresh_token"],
            credentials=dict(
                lwa_app_id=creds["lwa_app_id"],
                lwa_client_secret=creds["lwa_client_secret"],
            ),
        )

        # 注文情報を取得
        response = orders_api.get_order(order_id)
        order = response.payload

        if not order:
            return OrderInfo(
                order_id=order_id,
                error_reason="注文情報が見つかりません",
            )

        status = order.get("OrderStatus", "")
        fulfillment = order.get("FulfillmentChannel", "")

        info = OrderInfo(
            order_id=order_id,
            status=status,
            status_label=ORDER_STATUS_LABELS.get(status, status),
            fulfillment_channel=fulfillment,
            is_available=True,
        )

        # 発送日
        if order.get("LastUpdateDate"):
            info.ship_date = order["LastUpdateDate"]

        # 配送追跡情報を取得（発送済みの場合）
        if status in ("Shipped", "PartiallyShipped"):
            _fetch_tracking_info(orders_api, order_id, info)

        logger.info(
            "Order info fetched: %s status=%s fulfillment=%s",
            order_id,
            status,
            fulfillment,
        )
        return info

    except ImportError:
        logger.warning("python-amazon-sp-api not installed")
        return OrderInfo(
            order_id=order_id,
            error_reason="SP APIライブラリ未インストール",
        )
    except Exception as e:
        logger.exception("Failed to fetch order: %s", order_id)
        return OrderInfo(
            order_id=order_id,
            error_reason=f"API取得エラー: {e}",
        )


def _fetch_tracking_info(orders_api, order_id: str, info: OrderInfo) -> None:
    """注文の配送追跡情報を取得する"""
    try:
        response = orders_api.get_order_items(order_id)
        items = response.payload.get("OrderItems", [])
        for item in items:
            info.items.append(
                {
                    "asin": item.get("ASIN"),
                    "title": item.get("Title"),
                    "quantity": item.get("QuantityOrdered"),
                }
            )
    except Exception:
        logger.warning("Failed to fetch order items for %s", order_id)


def format_order_info_for_prompt(order_info: OrderInfo) -> str:
    """AI回答生成用に注文情報をテキスト化する"""
    if not order_info.is_available:
        return (
            f"注文番号: {order_info.order_id}\n"
            f"注文ステータス: 【未確認】（{order_info.error_reason}）\n"
            f"※注文の状態が確認できていないため、発送済み・未発送などの断定はしないでください。"
        )

    lines = [f"注文番号: {order_info.order_id}"]
    lines.append(f"注文ステータス: {order_info.status_label}（{order_info.status}）")

    if order_info.fulfillment_channel:
        channel_label = (
            "FBA（Amazon倉庫から発送）"
            if order_info.fulfillment_channel == "AFN"
            else "自社発送"
        )
        lines.append(f"出荷方法: {channel_label}")

    if order_info.ship_date:
        lines.append(f"最終更新日: {order_info.ship_date}")

    if order_info.tracking_number:
        lines.append(f"追跡番号: {order_info.tracking_number}")
    if order_info.carrier:
        lines.append(f"配送業者: {order_info.carrier}")

    if order_info.items:
        lines.append("注文商品:")
        for item in order_info.items:
            lines.append(
                f"  - {item.get('title', 'N/A')} (ASIN: {item.get('asin', 'N/A')}) x{item.get('quantity', 1)}"
            )

    return "\n".join(lines)

"""SP API Catalog Items から商品情報を取得・キャッシュするサービス

フロー:
1. DBに該当ASINのキャッシュがあればそれを返す
2. なければSP API Catalog Items APIで取得してDBに保存
3. キャッシュは7日間有効（古ければ再取得）
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.models.product_catalog import ProductCatalog

logger = logging.getLogger(__name__)

CACHE_TTL_DAYS = 7


def get_product_info(
    db: Session, asin: str, account_name: str = "MORABLU"
) -> dict | None:
    """ASINから商品情報を取得する（DBキャッシュ優先）"""
    # Step 1: DBキャッシュを確認
    cached = db.query(ProductCatalog).filter(ProductCatalog.asin == asin).first()

    if cached:
        age = datetime.now(timezone.utc) - cached.fetched_at.replace(
            tzinfo=timezone.utc
        )
        if age < timedelta(days=CACHE_TTL_DAYS):
            logger.info("Product cache hit: %s", asin)
            return _to_dict(cached)
        else:
            logger.info("Product cache expired: %s (age=%s)", asin, age)

    # Step 2: SP APIから取得（アカウント指定）
    catalog_data = _fetch_from_sp_api(asin, account_name=account_name)
    if not catalog_data:
        # API取得失敗でもキャッシュがあれば古いデータを返す
        if cached:
            return _to_dict(cached)
        return None

    # Step 3: DBに保存（upsert）
    if cached:
        for key, value in catalog_data.items():
            setattr(cached, key, value)
        cached.fetched_at = datetime.now(timezone.utc)
    else:
        cached = ProductCatalog(asin=asin, **catalog_data)
        db.add(cached)
    db.commit()
    db.refresh(cached)

    logger.info("Product info saved: %s - %s", asin, cached.title)
    return _to_dict(cached)


_SP_API_CREDENTIALS = {
    "MORABLU": {
        "refresh_token": "amazon_morablu_refresh_token",
        "lwa_app_id": "amazon_morablu_lwa_app_id",
        "lwa_client_secret": "amazon_morablu_lwa_client_secret",
    },
    "2ndMORABLU": {
        "refresh_token": "amazon_2ndmorablu_refresh_token",
        "lwa_app_id": "amazon_2ndmorablu_lwa_app_id",
        "lwa_client_secret": "amazon_2ndmorablu_lwa_client_secret",
    },
    "CHA3": {
        "refresh_token": "amazon_cha3_refresh_token",
        "lwa_app_id": "amazon_cha3_lwa_app_id",
        "lwa_client_secret": "amazon_cha3_lwa_client_secret",
    },
}


def _fetch_from_sp_api(asin: str, account_name: str = "MORABLU") -> dict | None:
    """SP API Catalog Items APIで商品情報を取得する

    使用API: GET /catalog/2022-04-01/items/{asin}
    includedData: summaries, descriptions, attributes, images
    """
    creds = _SP_API_CREDENTIALS.get(account_name, _SP_API_CREDENTIALS["MORABLU"])
    refresh_token = getattr(settings, creds["refresh_token"], "")
    lwa_app_id = getattr(settings, creds["lwa_app_id"], "")
    lwa_client_secret = getattr(settings, creds["lwa_client_secret"], "")

    if not refresh_token:
        logger.warning(
            "SP API credentials not configured for %s, skipping catalog fetch",
            account_name,
        )
        return None

    try:
        from sp_api.api import CatalogItems
        from sp_api.base import Marketplaces

        catalog = CatalogItems(
            refresh_token=refresh_token,
            lwa_app_id=lwa_app_id,
            lwa_client_secret=lwa_client_secret,
            marketplace=Marketplaces.JP,
        )

        response = catalog.get_catalog_item(
            asin=asin,
            includedData=[
                "summaries",
                "descriptions",
                "attributes",
                "images",
            ],
            marketplaceIds=[settings.amazon_marketplace_id],
        )

        item = response.payload
        if not item:
            return None

        return _parse_catalog_response(item)

    except ImportError:
        logger.warning("python-amazon-sp-api not installed")
        return None
    except Exception:
        logger.exception("Failed to fetch catalog item: %s", asin)
        return None


def _parse_catalog_response(item: dict) -> dict:
    """SP APIのレスポンスから必要な情報を抽出する"""
    result = {}

    # summaries（商品名、ブランド、カテゴリ等）
    summaries = item.get("summaries", [])
    if summaries:
        summary = summaries[0]  # 最初のマーケットプレイス
        result["title"] = summary.get("itemName")
        result["brand"] = summary.get("brand")
        result["product_type"] = summary.get("productType")
        result["color"] = summary.get("color")
        result["size"] = summary.get("size")

    # descriptions（商品説明文）
    descriptions = item.get("descriptions", [])
    if descriptions:
        result["description"] = descriptions[0].get("value", "")

    # attributes（箇条書き = bullet_point）
    attributes = item.get("attributes", {})
    bullet_points = attributes.get("bullet_point", [])
    if bullet_points:
        result["bullet_points"] = "\n".join(
            bp.get("value", "") for bp in bullet_points if bp.get("value")
        )

    # images（メイン画像URL）
    images = item.get("images", [])
    if images:
        image_list = images[0].get("images", [])
        if image_list:
            result["image_url"] = image_list[0].get("link")

    return result


def format_product_for_prompt(product: dict) -> str:
    """AI回答生成用にプロンプトに含める商品情報テキストを生成する"""
    lines = []

    if product.get("title"):
        lines.append(f"商品名: {product['title']}")
    if product.get("brand"):
        lines.append(f"ブランド: {product['brand']}")
    if product.get("product_type"):
        lines.append(f"カテゴリ: {product['product_type']}")
    if product.get("color"):
        lines.append(f"カラー: {product['color']}")
    if product.get("size"):
        lines.append(f"サイズ: {product['size']}")

    if product.get("bullet_points"):
        lines.append("\n商品の特徴:")
        for bp in product["bullet_points"].split("\n"):
            if bp.strip():
                lines.append(f"  - {bp.strip()}")

    if product.get("description"):
        desc = product["description"]
        if len(desc) > 800:
            desc = desc[:800] + "..."
        lines.append(f"\n商品説明:\n{desc}")

    return "\n".join(lines)


def _to_dict(catalog: ProductCatalog) -> dict:
    return {
        "asin": catalog.asin,
        "title": catalog.title,
        "brand": catalog.brand,
        "description": catalog.description,
        "bullet_points": catalog.bullet_points,
        "product_type": catalog.product_type,
        "color": catalog.color,
        "size": catalog.size,
        "image_url": catalog.image_url,
    }

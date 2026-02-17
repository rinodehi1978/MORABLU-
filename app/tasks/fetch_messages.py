"""バックグラウンドでのメッセージ自動取込タスク

APSchedulerを使って定期的にGmailからAmazonカスタマーメッセージを取得する。
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import SessionLocal
from app.services.gmail_fetcher import fetch_all_accounts

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def _fetch_job():
    """スケジューラーから呼ばれる取込ジョブ"""
    db = SessionLocal()
    try:
        results = fetch_all_accounts(db)
        total_new = sum(r["new"] for r in results.values())
        if total_new > 0:
            logger.info("Auto-fetch: %d new messages", total_new)
            for name, r in results.items():
                if r["new"] > 0:
                    logger.info("  %s: %d new", name, r["new"])
                if r["error"]:
                    logger.warning("  %s: error=%s", name, r["error"])
        else:
            logger.debug("Auto-fetch: no new messages")
    except Exception:
        logger.exception("Auto-fetch job failed")
    finally:
        db.close()


def start_scheduler():
    """バックグラウンドスケジューラーを起動する"""
    interval = settings.fetch_interval_minutes
    scheduler.add_job(
        _fetch_job,
        "interval",
        minutes=interval,
        id="gmail_fetch",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Auto-fetch scheduler started (interval=%d min)", interval)


def stop_scheduler():
    """スケジューラーを停止する"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Auto-fetch scheduler stopped")

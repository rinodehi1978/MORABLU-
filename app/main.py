import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import accounts, ai, auth, health, messages, qa_templates
from app.api.auth import verify_token
from app.database import Base, engine
from app.tasks.fetch_messages import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Customer Support Dashboard",
    description="中国輸入物販 カスタマーサポート一元管理",
    version="0.1.0",
)

# --- Authentication Middleware ---
# ログインページと認証APIはスキップ、それ以外はクッキー検証
PUBLIC_PATHS = {"/login", "/api/auth/login", "/api/health", "/api/health/"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 公開パス・静的ファイル（CSS/JS）はスキップ
        if path in PUBLIC_PATHS or path.startswith("/static/"):
            return await call_next(request)

        # クッキーからセッショントークンを検証
        token = request.cookies.get("cs_session", "")
        if not token or not verify_token(token):
            # APIリクエストには401、ページリクエストにはリダイレクト
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "認証が必要です"},
                )
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)


app.add_middleware(AuthMiddleware)

# CORS（複数PC・スマホからアクセス用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(qa_templates.router, prefix="/api")

# Static files
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


@app.get("/login")
async def login_page():
    return FileResponse(str(static_dir / "login.html"), headers=_NO_CACHE)


@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"), headers=_NO_CACHE)


@app.get("/templates")
async def templates_page():
    return FileResponse(str(static_dir / "templates.html"), headers=_NO_CACHE)


@app.get("/usage")
async def usage_page():
    return FileResponse(str(static_dir / "usage.html"), headers=_NO_CACHE)


@app.get("/manual")
async def manual_page():
    return FileResponse(str(static_dir / "manual.html"), headers=_NO_CACHE)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error("Unhandled exception:\n%s", "".join(tb))
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


def _migrate_db():
    """既存テーブルに新カラムを追加する（SQLite ALTER TABLE）"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "ai_responses" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("ai_responses")}
        migrations = {
            "input_tokens": "INTEGER",
            "output_tokens": "INTEGER",
            "model_used": "VARCHAR(100)",
        }
        with engine.begin() as conn:
            for col, dtype in migrations.items():
                if col not in existing:
                    conn.execute(text(
                        f"ALTER TABLE ai_responses ADD COLUMN {col} {dtype}"
                    ))
                    logger.info("Added column ai_responses.%s", col)


def _seed_templates():
    """qa_templatesが空の場合、templates_export.jsonから自動投入する"""
    import json

    from app.database import SessionLocal
    from app.models.qa_template import QaTemplate

    db = SessionLocal()
    try:
        if db.query(QaTemplate).count() > 0:
            return

        json_path = Path(__file__).parent.parent / "data" / "templates_export.json"
        if not json_path.exists():
            logger.warning("templates_export.json not found — skipping template seed")
            return

        with open(json_path, encoding="utf-8") as f:
            records = json.load(f)

        for r in records:
            db.add(QaTemplate(
                category_key=r.get("category_key", "other"),
                category=r["category"],
                subcategory=r.get("subcategory"),
                platform=r.get("platform", "common"),
                answer_template=r["answer_template"],
                staff_notes=r.get("staff_notes"),
            ))
        db.commit()
        logger.info("Seeded %d Q&A templates from templates_export.json", len(records))
    finally:
        db.close()


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    _migrate_db()
    _seed_templates()
    start_scheduler()


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()

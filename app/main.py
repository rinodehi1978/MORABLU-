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
PUBLIC_PATHS = {"/login", "/api/auth/login", "/api/health/"}


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


@app.get("/login")
async def login_page():
    return FileResponse(str(static_dir / "login.html"))


@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/templates")
async def templates_page():
    return FileResponse(str(static_dir / "templates.html"))


@app.get("/manual")
async def manual_page():
    return FileResponse(str(static_dir / "manual.html"))


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
    logger.error("Unhandled exception:\n%s", "".join(tb))
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


@app.on_event("startup")
async def startup():
    Base.metadata.create_all(bind=engine)
    start_scheduler()


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()

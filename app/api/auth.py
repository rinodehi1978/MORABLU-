"""ダッシュボードのログイン認証API"""

import hashlib
import hmac

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

TOKEN_MAX_AGE = 60 * 60 * 24 * 7  # 7日間


class LoginRequest(BaseModel):
    password: str


def _make_token() -> str:
    """パスワードとシークレットからセッショントークンを生成"""
    raw = f"{settings.dashboard_password}:{settings.session_secret}"
    return hmac.new(raw.encode(), b"cs-dashboard-session", hashlib.sha256).hexdigest()


def verify_token(token: str) -> bool:
    """クッキーのトークンが正しいか検証"""
    return hmac.compare_digest(token, _make_token())


@router.post("/login")
async def login(body: LoginRequest):
    if body.password != settings.dashboard_password:
        return JSONResponse(
            status_code=401,
            content={"detail": "パスワードが正しくありません"},
        )

    token = _make_token()
    response = JSONResponse(content={"detail": "ログイン成功"})
    response.set_cookie(
        key="cs_session",
        value=token,
        max_age=TOKEN_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout():
    response = JSONResponse(content={"detail": "ログアウトしました"})
    response.delete_cookie("cs_session")
    return response

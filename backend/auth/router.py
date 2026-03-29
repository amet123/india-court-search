import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import asyncpg
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

SECRET_KEY = "bharatlawfinder_secret_change_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    phone: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None,
) -> dict:
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    payload = verify_token(credentials.credentials)
    user_id = int(payload["sub"])
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT u.id, u.email, u.full_name, u.is_admin, u.is_active,
                   u.credits_used, u.credits_reset,
                   p.name AS plan_name, p.display_name AS plan_display,
                   p.credits_monthly, p.searches_daily, p.llm_model, p.features,
                   s.expires_at AS subscription_expires
            FROM users u
            JOIN plans p ON p.id = u.plan_id
            LEFT JOIN subscriptions s ON s.user_id = u.id AND s.status = 'active'
            WHERE u.id = $1 AND u.is_active = TRUE
            """,
            user_id,
        )
    if not user:
        raise HTTPException(401, "User not found")
    return dict(user)

async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(403, "Admin access required")
    return user

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM users WHERE email = $1", req.email)
        if existing:
            raise HTTPException(400, "Email already registered")
        pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
        user = await conn.fetchrow(
            "INSERT INTO users (email, password_hash, full_name, phone, plan_id) VALUES ($1, $2, $3, $4, 1) RETURNING id, email, full_name, is_admin",
            req.email, pw_hash, req.full_name, req.phone,
        )
    token = create_token(user["id"], user["email"])
    return TokenResponse(access_token=token, user={"id": user["id"], "email": user["email"], "full_name": user["full_name"], "is_admin": user["is_admin"], "plan": "free"})

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT u.id, u.email, u.full_name, u.password_hash, u.is_active, u.is_admin, p.name AS plan_name FROM users u JOIN plans p ON p.id = u.plan_id WHERE u.email = $1",
            req.email,
        )
    if not user:
        raise HTTPException(401, "Invalid email or password")
    if not user["is_active"]:
        raise HTTPException(403, "Account deactivated")
    if not bcrypt.checkpw(req.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid email or password")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET last_login = NOW() WHERE id = $1", user["id"])
    token = create_token(user["id"], user["email"])
    return TokenResponse(access_token=token, user={"id": user["id"], "email": user["email"], "full_name": user["full_name"], "is_admin": user["is_admin"], "plan": user["plan_name"]})

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "is_admin": user["is_admin"],
        "plan": {
            "name": user["plan_name"],
            "display": user["plan_display"],
            "credits_monthly": user["credits_monthly"],
            "credits_used": user["credits_used"],
            "credits_remaining": max(0, user["credits_monthly"] - user["credits_used"]),
            "searches_daily": user["searches_daily"],
            "llm_model": user["llm_model"],
            "features": user["features"],
            "expires_at": user["subscription_expires"],
        },
    }

@router.post("/forgot-password")
async def forgot_password(request: Request, email: str):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
    if not user:
        return {"message": "If this email exists, a reset link has been sent."}
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=1)
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO reset_tokens (user_id, token, expires_at) VALUES ($1, $2, $3)", user["id"], token, expires)
    logger.info(f"Reset token: {token}")
    return {"message": "If this email exists, a reset link has been sent."}

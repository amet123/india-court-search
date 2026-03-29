import logging
from datetime import datetime, date
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

async def check_search_limit(user: dict, pool) -> bool:
    daily_limit = user["searches_daily"]
    if daily_limit == -1:
        return True
    async with pool.acquire() as conn:
        today_count = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_logs WHERE user_id = $1 AND action = 'search' AND created_at >= CURRENT_DATE",
            user["id"],
        )
    if today_count >= daily_limit:
        raise HTTPException(429, {
            "error": "daily_limit_reached",
            "message": f"Aapne aaj ke {daily_limit} searches use kar liye.",
            "limit": daily_limit,
            "used": today_count,
            "upgrade_url": "/pricing",
        })
    return True

async def check_ai_credits(user: dict, pool) -> bool:
    plan_name = user["plan_name"]
    if plan_name == "free" or user["llm_model"] == "none":
        raise HTTPException(403, {
            "error": "plan_required",
            "message": "AI answers ke liye paid plan chahiye.",
            "upgrade_url": "/pricing",
        })
    credits_monthly = user["credits_monthly"]
    credits_used = user["credits_used"]
    if credits_used >= credits_monthly:
        raise HTTPException(429, {
            "error": "credits_exhausted",
            "message": f"Is mahine ke saare {credits_monthly} AI credits use ho gaye.",
            "upgrade_url": "/pricing",
        })
    return True

async def deduct_credit(user_id: int, pool, action: str = "ai_answer", model: str = "", query: str = ""):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET credits_used = credits_used + 1 WHERE id = $1", user_id)
        await conn.execute(
            "INSERT INTO usage_logs (user_id, action, model_used, credits, query) VALUES ($1, $2, $3, 1, $4)",
            user_id, action, model, query[:200] if query else "",
        )

async def log_search(user_id: int, pool, query: str = "", ip: str = ""):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO usage_logs (user_id, action, credits, query, ip_address) VALUES ($1, 'search', 0, $2, $3)",
            user_id, query[:200] if query else "", ip,
        )

def get_llm_model(user: dict) -> str:
    model_map = {
        "none": None,
        "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6": "claude-sonnet-4-6",
    }
    return model_map.get(user.get("llm_model", "none"))

def get_plan_features(user: dict) -> dict:
    features = user.get("features", {})
    if isinstance(features, str):
        import json
        features = json.loads(features)
    return {
        "semantic_search": features.get("semantic_search", False),
        "ai_answers": features.get("ai_answers", False),
        "pdf_access": features.get("pdf_access", False),
        "api_access": features.get("api_access", False),
    }

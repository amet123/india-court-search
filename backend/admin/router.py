import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from auth.router import get_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

class UpdateUserPlanRequest(BaseModel):
    plan_id: int

@router.get("/dashboard")
async def admin_dashboard(request: Request, admin: dict = Depends(get_admin_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        active_subs = await conn.fetchval("SELECT COUNT(*) FROM subscriptions WHERE status='active'")
        monthly_revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_paid),0) FROM subscriptions WHERE status='active' AND created_at >= DATE_TRUNC('month', NOW())"
        ) or 0
        searches_today = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_logs WHERE action='search' AND created_at >= CURRENT_DATE"
        )
        ai_answers_today = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_logs WHERE action='ai_answer' AND created_at >= CURRENT_DATE"
        )
        plan_breakdown = await conn.fetch(
            "SELECT p.display_name, COUNT(u.id) AS user_count FROM plans p LEFT JOIN users u ON u.plan_id = p.id GROUP BY p.id, p.display_name ORDER BY p.price_monthly"
        )
        recent_users = await conn.fetch(
            "SELECT u.id, u.email, u.full_name, u.created_at, p.display_name AS plan FROM users u JOIN plans p ON p.id = u.plan_id ORDER BY u.created_at DESC LIMIT 10"
        )
        daily_revenue = await conn.fetch(
            "SELECT DATE(created_at) AS day, COUNT(*) AS subs, SUM(amount_paid) AS revenue FROM subscriptions WHERE created_at >= NOW() - INTERVAL '7 days' GROUP BY DATE(created_at) ORDER BY day DESC"
        )
    return {
        "stats": {
            "total_users": total_users,
            "active_subscriptions": active_subs,
            "monthly_revenue_inr": monthly_revenue / 100,
            "searches_today": searches_today,
            "ai_answers_today": ai_answers_today,
        },
        "plan_breakdown": [dict(p) for p in plan_breakdown],
        "recent_users": [dict(u) for u in recent_users],
        "daily_revenue": [dict(d) for d in daily_revenue],
    }

@router.get("/users")
async def list_users(
    request: Request,
    admin: dict = Depends(get_admin_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
):
    pool = request.app.state.pool
    offset = (page - 1) * limit
    conditions = []
    params = []

    if search:
        params.append(f"%{search}%")
        conditions.append(f"(u.email ILIKE ${len(params)} OR u.full_name ILIKE ${len(params)})")

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        users = await conn.fetch(
            f"""
            SELECT u.id, u.email, u.full_name, u.is_active, u.is_admin,
                   u.credits_used, u.last_login, u.created_at,
                   p.name AS plan_name, p.display_name AS plan_display,
                   p.credits_monthly, s.expires_at, s.status AS sub_status
            FROM users u
            JOIN plans p ON p.id = u.plan_id
            LEFT JOIN subscriptions s ON s.user_id = u.id AND s.status = 'active'
            {where}
            ORDER BY u.created_at DESC
            LIMIT ${len(params)-1} OFFSET ${len(params)}
            """,
            *params,
        )
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM users u JOIN plans p ON p.id = u.plan_id {where}",
            *params[:-2],
        )
    return {"users": [dict(u) for u in users], "total": total, "page": page}

@router.patch("/users/{user_id}/plan")
async def update_user_plan(user_id: int, req: UpdateUserPlanRequest, request: Request, admin: dict = Depends(get_admin_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        plan = await conn.fetchrow("SELECT * FROM plans WHERE id = $1", req.plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        await conn.execute("UPDATE users SET plan_id=$1, credits_used=0 WHERE id=$2", req.plan_id, user_id)
        await conn.execute(
            "INSERT INTO usage_logs (user_id, action, query) VALUES ($1, 'admin_plan_change', $2)",
            user_id, f"Admin changed plan to {plan['name']}",
        )
    return {"message": f"Plan updated to {plan['display_name']}"}

@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, request: Request, admin: dict = Depends(get_admin_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT is_active FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(404, "User not found")
        new_status = not user["is_active"]
        await conn.execute("UPDATE users SET is_active=$1 WHERE id=$2", new_status, user_id)
    return {"message": f"User {'activated' if new_status else 'deactivated'}"}

@router.get("/revenue")
async def revenue_report(request: Request, admin: dict = Depends(get_admin_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        monthly = await conn.fetch(
            "SELECT TO_CHAR(created_at,'YYYY-MM') AS month, COUNT(*) AS subscriptions, SUM(amount_paid)/100.0 AS revenue_inr FROM subscriptions WHERE status IN ('active','cancelled') GROUP BY TO_CHAR(created_at,'YYYY-MM') ORDER BY month DESC LIMIT 12"
        )
        by_plan = await conn.fetch(
            "SELECT p.display_name, COUNT(s.id) AS total_subs, COALESCE(SUM(s.amount_paid),0)/100.0 AS total_revenue_inr FROM subscriptions s JOIN plans p ON p.id = s.plan_id WHERE s.status IN ('active','cancelled') GROUP BY p.display_name"
        )
    return {"monthly": [dict(m) for m in monthly], "by_plan": [dict(b) for b in by_plan]}

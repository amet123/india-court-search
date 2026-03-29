import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth.router import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

class CreateOrderRequest(BaseModel):
    plan_id: int

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_id: int

@router.get("/plans")
async def get_plans(request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        plans = await conn.fetch("SELECT * FROM plans WHERE is_active = TRUE ORDER BY price_monthly")
    return [dict(p) for p in plans]

@router.post("/create-order")
async def create_order(req: CreateOrderRequest, request: Request, user: dict = Depends(get_current_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        plan = await conn.fetchrow("SELECT * FROM plans WHERE id = $1 AND is_active = TRUE", req.plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan["price_monthly"] == 0:
        raise HTTPException(400, "Free plan purchase nahi ho sakta")

    settings = request.app.state.settings
    client = razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))

    order_data = {
        "amount": plan["price_monthly"],
        "currency": "INR",
        "receipt": f"order_user{user['id']}_plan{plan['id']}",
        "notes": {"user_id": str(user["id"]), "user_email": user["email"], "plan_name": plan["name"]},
    }

    try:
        order = client.order.create(data=order_data)
    except Exception as e:
        logger.error(f"Razorpay error: {e}")
        raise HTTPException(500, "Payment gateway error. Dobara try karo.")

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO subscriptions (user_id, plan_id, status, razorpay_order_id, amount_paid) VALUES ($1, $2, 'pending', $3, $4)",
            user["id"], plan["id"], order["id"], plan["price_monthly"],
        )

    return {
        "order_id": order["id"],
        "amount": plan["price_monthly"],
        "currency": "INR",
        "key_id": settings.razorpay_key_id,
        "plan_name": plan["display_name"],
        "user_name": user["full_name"],
        "user_email": user["email"],
    }

@router.post("/verify")
async def verify_payment(req: VerifyPaymentRequest, request: Request, user: dict = Depends(get_current_user)):
    settings = request.app.state.settings
    body = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
    expected = hmac.new(settings.razorpay_key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if expected != req.razorpay_signature:
        raise HTTPException(400, "Invalid payment signature")

    pool = request.app.state.pool
    async with pool.acquire() as conn:
        plan = await conn.fetchrow("SELECT * FROM plans WHERE id = $1", req.plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        expires_at = datetime.utcnow() + timedelta(days=30)
        await conn.execute(
            "UPDATE subscriptions SET status='active', razorpay_payment_id=$1, started_at=NOW(), expires_at=$2 WHERE user_id=$3 AND razorpay_order_id=$4",
            req.razorpay_payment_id, expires_at, user["id"], req.razorpay_order_id,
        )
        await conn.execute(
            "UPDATE subscriptions SET status='cancelled' WHERE user_id=$1 AND status='active' AND razorpay_order_id!=$2",
            user["id"], req.razorpay_order_id,
        )
        await conn.execute(
            "UPDATE users SET plan_id=$1, credits_used=0, credits_reset=NOW() WHERE id=$2",
            plan["id"], user["id"],
        )
        await conn.execute(
            "INSERT INTO usage_logs (user_id, action, query) VALUES ($1, 'subscription', $2)",
            user["id"], f"Subscribed to {plan['display_name']}",
        )

    return {"success": True, "message": f"{plan['display_name']} plan successfully activate ho gaya!", "plan": plan["name"], "expires_at": expires_at.isoformat()}

@router.get("/my-subscriptions")
async def my_subscriptions(request: Request, user: dict = Depends(get_current_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        subs = await conn.fetch(
            "SELECT s.*, p.display_name AS plan_display FROM subscriptions s JOIN plans p ON p.id = s.plan_id WHERE s.user_id = $1 ORDER BY s.created_at DESC",
            user["id"],
        )
    return [dict(s) for s in subs]

@router.post("/cancel")
async def cancel_subscription(request: Request, user: dict = Depends(get_current_user)):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE subscriptions SET status='cancelled', cancelled_at=NOW() WHERE user_id=$1 AND status='active'",
            user["id"],
        )
        await conn.execute("UPDATE users SET plan_id=1 WHERE id=$1", user["id"])
    return {"message": "Subscription cancel ho gaya. Ab aap Free plan pe hain."}

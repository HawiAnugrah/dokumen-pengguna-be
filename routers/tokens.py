from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
import os

import model
import auth
from database import get_db

router = APIRouter(prefix="/api/tokens", tags=["Token Usage"])

@router.get("/usage")
def get_user_token_usage(
    project_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: model.User = Depends(auth.get_current_user)
):
    """Mengambil ringkasan kuota dan riwayat pemakaian token AI global (seluruh akun/server) terpisah per provider dan per hari"""
    
    # Ambil awal hari ini dan awal bulan ini (UTC)
    now = datetime.now(timezone.utc)
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    # 1. Total token & request bulan ini & hari ini (gabungan seluruh akun / server-wide)
    monthly_used = db.query(func.sum(model.AiTokenUsage.total_tokens)).filter(
        model.AiTokenUsage.created_at >= start_of_month
    ).scalar() or 0

    daily_used_total = db.query(func.sum(model.AiTokenUsage.total_tokens)).filter(
        model.AiTokenUsage.created_at >= start_of_day
    ).scalar() or 0

    daily_requests_total = db.query(func.count(model.AiTokenUsage.id)).filter(
        model.AiTokenUsage.created_at >= start_of_day
    ).scalar() or 0

    monthly_requests_total = db.query(func.count(model.AiTokenUsage.id)).filter(
        model.AiTokenUsage.created_at >= start_of_month
    ).scalar() or 0

    # 2. Detail Konfigurasi & Pelacakan RPD (Requests Per Day) Terpisah per Provider AI
    provider_configs = [
        {
            "name": "Google Gemini",
            "provider_key": "gemini",
            "model": os.getenv("GEMINI_MODEL_NAME") or os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            "rpd_limit": int(os.getenv("GEMINI_RPD_LIMIT", "1500")),
            "daily_limit": int(os.getenv("GEMINI_DAILY_LIMIT", "1000000")),
            "monthly_limit": int(os.getenv("GEMINI_MONTHLY_LIMIT", "30000000")),
            "status": "Ready" if os.getenv("GEMINI_API_KEY") else "Not Configured"
        },
        {
            "name": "OpenRouter AI",
            "provider_key": "openrouter",
            "model": os.getenv("OPENROUTER_MODEL_NAME", "meta-llama/llama-3.3-70b-instruct:free"),
            "rpd_limit": int(os.getenv("OPENROUTER_RPD_LIMIT", "200")),
            "daily_limit": int(os.getenv("OPENROUTER_DAILY_LIMIT", "200000")),
            "monthly_limit": int(os.getenv("OPENROUTER_MONTHLY_LIMIT", "5000000")),
            "status": "Ready" if os.getenv("OPENROUTER_API_KEY") else "Not Configured"
        },
        {
            "name": "Groq Cloud LPU",
            "provider_key": "groq",
            "model": os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile"),
            "rpd_limit": int(os.getenv("GROQ_RPD_LIMIT", "1000")),
            "daily_limit": int(os.getenv("GROQ_DAILY_LIMIT", "500000")),
            "monthly_limit": int(os.getenv("GROQ_MONTHLY_LIMIT", "15000000")),
            "status": "Ready" if os.getenv("GROQ_API_KEY") else "Not Configured"
        }
    ]

    total_rpd_limit = sum(cfg["rpd_limit"] for cfg in provider_configs)
    rpd_remaining_total = max(0, total_rpd_limit - daily_requests_total)
    rpd_percentage_total = min(100.0, round((daily_requests_total / total_rpd_limit) * 100, 1)) if total_rpd_limit > 0 else 0.0

    total_monthly_quota = sum(cfg["monthly_limit"] for cfg in provider_configs)
    remaining = max(0, total_monthly_quota - monthly_used)
    percentage = min(100.0, round((monthly_used / total_monthly_quota) * 100, 1)) if total_monthly_quota > 0 else 0.0

    usage_by_provider = {}
    providers_info = []

    for cfg in provider_configs:
        pkey = cfg["provider_key"]
        
        # Penggunaan token hari ini per provider (seluruh akun)
        p_daily_used = db.query(func.sum(model.AiTokenUsage.total_tokens)).filter(
            model.AiTokenUsage.provider == pkey,
            model.AiTokenUsage.created_at >= start_of_day
        ).scalar() or 0

        # Penggunaan token bulan ini per provider (seluruh akun)
        p_monthly_used = db.query(func.sum(model.AiTokenUsage.total_tokens)).filter(
            model.AiTokenUsage.provider == pkey,
            model.AiTokenUsage.created_at >= start_of_month
        ).scalar() or 0

        # Total request (RPD) per provider (seluruh akun)
        p_req_today = db.query(func.count(model.AiTokenUsage.id)).filter(
            model.AiTokenUsage.provider == pkey,
            model.AiTokenUsage.created_at >= start_of_day
        ).scalar() or 0

        p_req_month = db.query(func.count(model.AiTokenUsage.id)).filter(
            model.AiTokenUsage.provider == pkey,
            model.AiTokenUsage.created_at >= start_of_month
        ).scalar() or 0

        usage_by_provider[pkey] = p_monthly_used

        # RPD (Requests Per Day) metrics
        r_limit = cfg["rpd_limit"]
        r_used = p_req_today
        r_rem = max(0, r_limit - r_used)
        r_pct = min(100.0, round((r_used / r_limit) * 100, 1)) if r_limit > 0 else 0.0

        d_limit = cfg["daily_limit"]
        d_rem = max(0, d_limit - p_daily_used)
        d_pct = min(100.0, round((p_daily_used / d_limit) * 100, 2)) if d_limit > 0 else 0.0

        m_limit = cfg["monthly_limit"]
        m_rem = max(0, m_limit - p_monthly_used)
        m_pct = min(100.0, round((p_monthly_used / m_limit) * 100, 2)) if m_limit > 0 else 0.0

        providers_info.append({
            "name": cfg["name"],
            "provider_key": pkey,
            "model": cfg["model"],
            "status": cfg["status"],
            "rpd_limit": r_limit,
            "rpd_used": r_used,
            "rpd_remaining": r_rem,
            "rpd_percentage": r_pct,
            "daily_limit": d_limit,
            "daily_used": p_daily_used,
            "daily_remaining": d_rem,
            "daily_percentage": d_pct,
            "monthly_limit": m_limit,
            "monthly_used": p_monthly_used,
            "monthly_remaining": m_rem,
            "monthly_percentage": m_pct,
            "requests_today": p_req_today,
            "requests_month": p_req_month
        })

    # 3. Breakdown per Fitur (seluruh akun)
    features_raw = db.query(
        model.AiTokenUsage.feature,
        func.sum(model.AiTokenUsage.total_tokens)
    ).group_by(model.AiTokenUsage.feature).all()
    
    usage_by_feature = {f: toks for f, toks in features_raw}

    # 4. Riwayat 15 request terakhir (seluruh akun)
    recent_query = db.query(model.AiTokenUsage)
    if project_id:
        recent_query = recent_query.filter(model.AiTokenUsage.project_id == project_id)
    
    recent_records = recent_query.order_by(model.AiTokenUsage.created_at.desc()).limit(15).all()

    history = [
        {
            "id": r.id,
            "feature": r.feature,
            "provider": r.provider,
            "model_name": r.model_name,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in recent_records
    ]

    return {
        "rpd_total_limit": total_rpd_limit,
        "rpd_total_used": daily_requests_total,
        "rpd_total_remaining": rpd_remaining_total,
        "rpd_total_percentage": rpd_percentage_total,
        "monthly_requests_total": monthly_requests_total,
        "monthly_quota": total_monthly_quota,
        "monthly_used": monthly_used,
        "daily_used": daily_used_total,
        "remaining_tokens": remaining,
        "usage_percentage": percentage,
        "usage_by_provider": usage_by_provider,
        "usage_by_feature": usage_by_feature,
        "providers_info": providers_info,
        "history": history
    }
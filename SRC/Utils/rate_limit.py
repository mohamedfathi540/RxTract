"""
Per-user rate limiting and daily usage quota utilities.

Rate limiter keys by authenticated user (JWT email) with IP fallback.
Quota dependency enforces configurable daily caps per action type.
"""
from datetime import date

import jwt
from fastapi import Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select

from Helpers.Config import get_settings
from Utils.security import get_current_user


# ── Key functions ───────────────────────────────────────────────────

def get_user_key(request: Request) -> str:
    """Extract user identity from JWT for rate limiting; fallback to IP."""
    try:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            s = get_settings()
            payload = jwt.decode(
                auth[7:], s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM]
            )
            email = payload.get("sub")
            if email:
                return f"user:{email}"
    except Exception:
        pass
    return get_remote_address(request)


# Global limiter — defaults to per-user key; auth routes override to IP.
limiter = Limiter(key_func=get_user_key)


def config_limit(setting_name: str):
    """Return a callable for slowapi that reads the limit string from settings."""
    def _resolve():
        return getattr(get_settings(), setting_name)
    return _resolve


# ── Daily usage quota dependency ────────────────────────────────────

def require_quota(action: str):
    """
    Factory returning a FastAPI dependency that enforces daily usage quotas.

    ``action`` must be one of: ``"upload"``, ``"query"``, ``"prescription"``
    """
    _limit_map = {
        "upload": "QUOTA_DAILY_UPLOADS",
        "query": "QUOTA_DAILY_QUERIES",
        "prescription": "QUOTA_DAILY_PRESCRIPTIONS",
    }
    _count_field = f"{action}_count"
    _setting_name = _limit_map[action]

    async def _check_quota(request: Request, user=Depends(get_current_user)):
        from Models.DB_Schemes import UserUsageQuota  # deferred to avoid circular imports

        s = get_settings()
        limit = getattr(s, _setting_name, 0)
        if limit <= 0:
            return user  # 0 or negative means unlimited

        today = date.today()

        async with request.app.db_client() as session:
            result = await session.execute(
                select(UserUsageQuota).where(
                    UserUsageQuota.user_id == user.id,
                    UserUsageQuota.date == today,
                )
            )
            quota = result.scalar_one_or_none()

            if quota is None:
                quota = UserUsageQuota(user_id=user.id, date=today)
                session.add(quota)
                await session.flush()

            current = getattr(quota, _count_field)
            if current >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Daily {action} quota exceeded ({current}/{limit}). "
                        "Resets at midnight UTC."
                    ),
                )

            setattr(quota, _count_field, current + 1)
            await session.commit()

        return user

    return _check_quota


async def get_user_quota_status(request: Request, user) -> dict:
    """Return the current user's daily quota usage and limits."""
    from Models.DB_Schemes import UserUsageQuota

    s = get_settings()
    today = date.today()

    async with request.app.db_client() as session:
        result = await session.execute(
            select(UserUsageQuota).where(
                UserUsageQuota.user_id == user.id,
                UserUsageQuota.date == today,
            )
        )
        quota = result.scalar_one_or_none()

    used_uploads = quota.upload_count if quota else 0
    used_queries = quota.query_count if quota else 0
    used_prescriptions = quota.prescription_count if quota else 0

    return {
        "date": str(today),
        "uploads": {"used": used_uploads, "limit": s.QUOTA_DAILY_UPLOADS},
        "queries": {"used": used_queries, "limit": s.QUOTA_DAILY_QUERIES},
        "prescriptions": {"used": used_prescriptions, "limit": s.QUOTA_DAILY_PRESCRIPTIONS},
    }

"""
SecurityController — Centralises authentication, rate-limiting and
email-verification logic inside the Controllers layer.

All logic is self-contained (no imports from Utils/).
"""

from datetime import date, datetime, timedelta
import logging
from typing import Optional

import bcrypt
import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select

from .BaseController import basecontroller
from Helpers.Config import get_settings

logger = logging.getLogger("uvicorn.error")

# ═══════════════════════════════════════════════════════════════════════
# MODULE-LEVEL OBJECTS (used by decorators / middleware before init)
# ═══════════════════════════════════════════════════════════════════════

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _get_user_key(request: Request) -> str:
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


limiter = Limiter(key_func=_get_user_key)


def config_limit(setting_name: str):
    """Return a callable for slowapi that reads the limit string from settings."""
    def _resolve():
        return getattr(get_settings(), setting_name)
    return _resolve


# ═══════════════════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════════════════

class SecurityController(basecontroller):

    def __init__(self):
        super().__init__()

    # ── Password hashing ────────────────────────────────────────

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )

    @staticmethod
    def get_password_hash(password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    # ── JWT tokens ──────────────────────────────────────────────

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        settings = get_settings()
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta if expires_delta else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    # ── FastAPI dependency: current user from JWT ───────────────

    @staticmethod
    async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)):
        settings = get_settings()

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
            email: str | None = payload.get("sub")
            if email is None:
                raise credentials_exception
        except jwt.PyJWTError:
            raise credentials_exception

        from Models.DB_Schemes import User

        async with request.app.db_client() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()

        if user is None:
            raise credentials_exception

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated",
            )

        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. Please check your inbox.",
            )

        return user

    # ── Daily usage quota dependency ────────────────────────────

    @staticmethod
    def require_quota(action: str):
        _limit_map = {
            "query": "QUOTA_DAILY_QUERIES",
            "prescription": "QUOTA_DAILY_PRESCRIPTIONS",
        }
        _count_field = f"{action}_count"
        _setting_name = _limit_map[action]

        async def _check_quota(request: Request, user=Depends(SecurityController.get_current_user)):
            from Models.DB_Schemes import UserUsageQuota

            s = get_settings()
            limit = getattr(s, _setting_name, 0)
            if limit <= 0:
                return user

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
                            "Resets daily at midnight (server time, UTC)."
                        ),
                    )

                setattr(quota, _count_field, current + 1)
                await session.commit()

            return user

        return _check_quota

    # ── Quota status helper ─────────────────────────────────────

    @staticmethod
    async def get_user_quota_status(request: Request, user) -> dict:
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

        used_queries = quota.query_count if quota else 0
        used_prescriptions = quota.prescription_count if quota else 0

        return {
            "date": str(today),
            "queries": {"used": used_queries, "limit": s.QUOTA_DAILY_QUERIES},
            "prescriptions": {"used": used_prescriptions, "limit": s.QUOTA_DAILY_PRESCRIPTIONS},
        }

    # ── Email verification ──────────────────────────────────────

    @staticmethod
    async def send_verification_email(email: str, token: str) -> None:
        settings = get_settings()
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

        if not settings.BREVO_API_KEY:
            logger.warning(
                "BREVO_API_KEY not configured — printing verification link to console:\n"
                "  → %s",
                verification_link,
            )
            return

        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": settings.BREVO_API_KEY,
            "content-type": "application/json",
        }

        payload = {
            "sender": {"email": settings.SENDER_EMAIL, "name": "RxTract System"},
            "to": [{"email": email}],
            "subject": "Verify Your Email Address",
            "htmlContent": (
                "<html><body>"
                "<h2>Welcome to RxTract!</h2>"
                f"<p>Click <a href='{verification_link}'>here</a> to verify your email address.</p>"
                "<p>If you did not create an account, you can safely ignore this email.</p>"
                "</body></html>"
            ),
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(
                "Brevo API response [%s]: %s", response.status_code, response.text
            )
            response.raise_for_status()

        logger.info("Verification email sent to %s", email)

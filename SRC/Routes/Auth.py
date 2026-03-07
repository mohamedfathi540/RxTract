"""
Authentication routes: register, login, and email verification.
"""
import uuid
import logging
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .Schemes.Auth_Schemes import UserCreate, UserLogin
from Controllers.SecurityController import SecurityController, limiter, config_limit
from slowapi.util import get_remote_address
from Models.DB_Schemes import User

logger = logging.getLogger("uvicorn.error")

auth_router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


# ── Register ────────────────────────────────────────────────────────
@auth_router.post("/register")
@limiter.limit(config_limit("RATE_LIMIT_AUTH"), key_func=get_remote_address)
async def register(request: Request, user_in: UserCreate):
    """Create a new user account and send a verification email."""
    async with request.app.db_client() as session:
        # 1. Check if user already exists
        existing = await session.execute(
            select(User).where(User.email == user_in.email)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        # 2. Hash password & create verification token
        hashed_pw = SecurityController.get_password_hash(user_in.password)
        verification_token = str(uuid.uuid4())

        # 3. Persist user
        db_user = User(
            email=user_in.email,
            hashed_password=hashed_pw,
            verification_token=verification_token,
        )
        session.add(db_user)
        await session.commit()

    # 4. Send verification email (outside the DB session)
    try:
        await SecurityController.send_verification_email(user_in.email, verification_token)
    except Exception as exc:
        logger.error("Failed to send verification email: %s", exc)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "User registered. Please check your email to verify."},
    )


# ── Login ───────────────────────────────────────────────────────────
@auth_router.post("/login")
@limiter.limit(config_limit("RATE_LIMIT_AUTH"), key_func=get_remote_address)
async def login(request: Request, user_in: UserLogin):
    """Authenticate a user and return a JWT access token."""
    async with request.app.db_client() as session:
        result = await session.execute(
            select(User).where(User.email == user_in.email)
        )
        db_user = result.scalar_one_or_none()

    if db_user is None or not SecurityController.verify_password(user_in.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    if not db_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified. Please check your inbox.",
        )

    access_token = SecurityController.create_access_token(data={"sub": db_user.email})
    return {"access_token": access_token, "token_type": "bearer"}


# ── Email verification ──────────────────────────────────────────────
@auth_router.get("/verify")
@limiter.limit(config_limit("RATE_LIMIT_AUTH"), key_func=get_remote_address)
async def verify_email(request: Request, token: str):
    """Verify a user's email address using the token sent via email."""
    async with request.app.db_client() as session:
        result = await session.execute(
            select(User).where(User.verification_token == token)
        )
        db_user = result.scalar_one_or_none()

        if db_user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token.",
            )

        db_user.is_verified = True
        db_user.verification_token = None
        await session.commit()

    return {"message": "Email successfully verified. You can now log in."}


# ── Resend verification email ───────────────────────────────────────
@auth_router.post("/resend-verification")
@limiter.limit("3/minute", key_func=get_remote_address)
async def resend_verification(request: Request, body: dict):
    """Resend the verification email for an unverified account."""
    email = body.get("email", "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address is required.",
        )

    async with request.app.db_client() as session:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        db_user = result.scalar_one_or_none()

        # Always return success to avoid leaking whether an account exists
        if db_user is None or db_user.is_verified:
            return {"message": "If the account exists and is unverified, a new email has been sent."}

        # Generate a fresh token
        new_token = str(uuid.uuid4())
        db_user.verification_token = new_token
        await session.commit()

    # Send the email
    try:
        await SecurityController.send_verification_email(email, new_token)
    except Exception as exc:
        logger.error("Failed to resend verification email: %s", exc)

    return {"message": "If the account exists and is unverified, a new email has been sent."}

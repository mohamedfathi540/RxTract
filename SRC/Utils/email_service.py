"""
Email verification service using the Brevo (Sendinblue) transactional email API.
"""
import logging
import httpx
from Helpers.Config import get_settings

logger = logging.getLogger("uvicorn.error")


async def send_verification_email(email: str, token: str) -> None:
    """
    Send a verification email via Brevo's SMTP API.
    The link points the user to ``{FRONTEND_URL}/verify-email?token=<token>``.

    If ``BREVO_API_KEY`` is not set, the function logs the verification link
    instead (useful during local development).
    """
    settings = get_settings()
    verification_link = f"{settings.FRONTEND_URL}/verify-email?token={token}"

    # ── Dev-mode fallback: just log the link ────────────────────
    if not settings.BREVO_API_KEY:
        logger.warning(
            "BREVO_API_KEY not configured — printing verification link to console:\n"
            "  → %s",
            verification_link,
        )
        return

    # ── Send via Brevo API ──────────────────────────────────────
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "sender": {"email": settings.SENDER_EMAIL, "name": "Tashfeer System"},
        "to": [{"email": email}],
        "subject": "Verify Your Email Address",
        "htmlContent": (
            "<html><body>"
            "<h2>Welcome to Tashfeer!</h2>"
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

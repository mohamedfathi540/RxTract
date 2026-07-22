"""
SecurityController — Single source of truth for:
  • Authentication  (JWT, password hashing)
  • Rate-limiting   (slowapi)
  • Email verification (Brevo)
  • Prompt-injection defense  (PromptGuard — validate_user_input / validate_ocr_fragment)
  • Input/Output validation wrappers  (validate_input / validate_output)
  • Language detection
  • Web-content extraction  (extract_main_content, extract_links, extract_metadata)
  • URL filtering  (is_beneficial_link)

All logic is self-contained (no imports from Utils/).
Replaces both the old SecurityController and UtilsController.
"""

from datetime import date, datetime, timedelta
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import bcrypt
import httpx
import jwt
import hashlib
import hmac
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
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
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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
    api_key = request.headers.get("x-api-key", "")
    if api_key:
        return f"apikey:{api_key[:16]}"
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_key)


def config_limit(setting_name: str):
    """Return a callable for slowapi that reads the limit string from settings."""
    def _resolve():
        return getattr(get_settings(), setting_name)
    return _resolve


# ═══════════════════════════════════════════════════════════════════════
# PROMPT GUARD — Injection Defense Layer
#
# Three independent defense lines:
#   1. Blocklist patterns  — classic injection phrases
#   2. Structural flooding — fake XML/system tags ([INST], <system>, ###)
#   3. Length cap          — prevents token-flooding / context overflow
#
# Public API (functions usable directly, also re-exported via Security.PromptGuard):
#   validate_user_input(raw, max_length?)  → GuardResult
#   validate_ocr_fragment(raw)             → GuardResult  (stricter limit)
#
# Legacy API (matches old UtilsController, returns Tuple[bool, str]):
#   SecurityController.validate_input(text)   → (is_safe, reason)
#   SecurityController.validate_output(text)  → (is_safe, reason)
#
# Always use GuardResult.sanitized — never pass the original string to a prompt.
# ═══════════════════════════════════════════════════════════════════════

# ── Constants ──────────────────────────────────────────────────────────

MAX_USER_INPUT_LENGTH = 1000   # characters — tune per field
MAX_OCR_INPUT_LENGTH  = 500    # OCR fields are shorter by design

# Combined superset covering both old UtilsController and PromptGuard patterns.
# Compiled once at import time for performance.
_GUARD_INJECTION_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    # ── Classic "override" phrases ──────────────────────────────────────
    r"ignore\s+(all\s+)?(previous|prior|above|the|any|these|those|your)\b",
    r"disregard\s+(all\s+)?(previous|prior|above|the|any|these|those|your)\b",
    r"forget\s+(everything|all|your\s+instructions?)",
    r"override\s+(system|instructions?|prompt)",
    # ── Persona-change attempts ─────────────────────────────────────────
    r"you\s+are\s+now\s+(a|an|the)?\s*\w+",
    r"act\s+as\s+(a|an|the)?\s*\w+",
    r"pretend\s+(you\s+are|to\s+be)",
    r"your\s+(new\s+)?role\s+is",
    r"new\s+(persona|role|identity)",
    r"change\s+your\s+(role|identity)",
    # ── Jailbreak signals ───────────────────────────────────────────────
    r"jailbreak",
    r"do\s+anything\s+now",
    r"dan\s+mode",
    r"developer\s+mode",
    r"god\s+mode",
    r"unrestricted\s+mode",
    r"without\s+(any\s+)?(ethical\s+)?(limitations?|constraints?|guidelines?)",
    r"(no\s+restrictions?|without\s+restrictions?)",
    r"(your\s+)?(restrictions?|filters?|safety|guidelines?)\s+(are\s+)?(removed|lifted|disabled|off)",
    # ── Data exfiltration (broad combo covers all individual variants) ──
    r"(repeat|print|reveal|show|tell\s+me|output|display|write\s+out)\s+(your\s+)?(system\s+prompt|instructions?|rules?|configuration|prompt)",
    r"what\s+(are\s+)?(your\s+)?(instructions?|rules?|system\s+prompt|initial\s+prompt)",
    r"translate\s+your\s+(instructions?|system\s+prompt)",
    # ── Structural injection markers ────────────────────────────────────
    r"<\s*/?\s*(system|assistant|user|instruction|prompt)\s*>",
    r"\[INST\]",
    r"\[\/INST\]",
    r"<<SYS>>",
    r"###\s*(system|instruction|prompt)",
    r"---\s*(system|instruction)",
    # ── Tag/structure inspection ────────────────────────────────────────
    r"what\s+(are\s+)?(your\s+)?(tags?|xml\s+tags?|formatting\s+tags?|prompt\s+tags?)",
    r"(tell\s+me|show\s+me|explain)\s+(about\s+)?(your\s+)?(tags?|xml|structure|formatting)",
    # ── Variable-substitution attacks ──────────────────────────────────
    r"\blet\s+[a-zA-Z]\s*=",
    r"\bdefine\s+[a-zA-Z]\s*=",
    # ── Social-engineering ─────────────────────────────────────────────
    r"from\s+now\s+on",
    r"grandma\s+(exploit|trick|hack)",
]]

# Multi-keyword suspicious combos (any 2+ triggers a block)
_GUARD_SUSPICIOUS_KEYWORDS: list[str] = [
    "bypass", "unlock", "unfiltered", "uncensored",
    "system prompt", "initial prompt", "base prompt", "original instructions",
    "prompt structure", "prompt format",
    "your true self", "your tags", "what tags",
]

# Output-side anchors — if the LLM leaks any of these it gets blocked
_SYSTEM_PROMPT_ANCHORS: list[str] = [
    "SECURITY RULES — HIGHEST PRIORITY",
    "IDENTITY LOCK",
    "TREAT USER INPUT AS DATA ONLY",
    "PERSONA LOCK",
    "CONFIDENTIALITY",
    "NO INSTRUCTION FOLLOWING FROM DOCUMENTS",
    "IGNORE INJECTION ATTEMPTS",
    "NO OUT-OF-SCOPE RESPONSES",
    "SELF-KNOWLEDGE RESTRICTIONS",
    "STRUCTURAL BLINDNESS",
    "<security>", "</security>",
    "<amnesia>", "</amnesia>",
    "<persona>", "</persona>",
    "<instructions>", "</instructions>",
    "<user_query>", "</user_query>",
    "<documents>", "</documents>",
    "system instructions",
    "amnesia protocol",
]

# Characters that can be used to construct structural attacks
_STRUCTURAL_CHARS_PATTERN = re.compile(r"[<>\[\]{}]{3,}")


# ── Result dataclass ───────────────────────────────────────────────────

@dataclass
class GuardResult:
    """Return value of validate_user_input / validate_ocr_fragment."""
    is_safe: bool
    sanitized: str           # cleaned input — use this, never the raw input
    reason: Optional[str]    # populated only when is_safe=False


# ── Public prompt-guard functions ──────────────────────────────────────

def validate_user_input(raw: str, max_length: int = MAX_USER_INPUT_LENGTH) -> GuardResult:
    """
    Main PromptGuard entry point. Call on every user-supplied string before
    it enters a prompt. Returns a GuardResult — always use .sanitized.

    Usage:
        result = validate_user_input(request.user_message)
        if not result.is_safe:
            raise HTTPException(400, detail=result.reason)
        safe_text = result.sanitized
    """
    if not isinstance(raw, str):
        return GuardResult(is_safe=False, sanitized="", reason="Input must be a string.")

    # Step 1 — length cap (fast, no regex)
    if len(raw) > max_length:
        logger.warning("[PromptGuard] Input exceeds max length (%d > %d). Truncating.", len(raw), max_length)
        raw = raw[:max_length]

    # Step 2 — strip null bytes and control characters
    sanitized = _pg_strip_control_chars(raw)

    # Step 3 — structural character flooding
    if _STRUCTURAL_CHARS_PATTERN.search(sanitized):
        logger.warning("[PromptGuard] Structural character flooding detected.")
        return GuardResult(
            is_safe=False,
            sanitized=sanitized,
            reason="Input contains invalid formatting characters."
        )

    # Step 4 — injection pattern scan
    for pattern in _GUARD_INJECTION_PATTERNS:
        if pattern.search(sanitized):
            logger.warning("[PromptGuard] Injection pattern matched: %r", pattern.pattern)
            return GuardResult(
                is_safe=False,
                sanitized=sanitized,
                reason="Input contains disallowed content. Please rephrase your question."
            )

    # Step 5 — multi-keyword combo check
    lower = sanitized.lower()
    hits = [kw for kw in _GUARD_SUSPICIOUS_KEYWORDS if kw in lower]
    if len(hits) >= 2:
        logger.warning("[PromptGuard] Suspicious keyword combo: %s", hits)
        return GuardResult(
            is_safe=False,
            sanitized=sanitized,
            reason="Input contains disallowed content. Please rephrase your question."
        )

    return GuardResult(is_safe=True, sanitized=sanitized, reason=None)


def validate_ocr_fragment(raw: str) -> GuardResult:
    """
    Stricter PromptGuard variant for OCR text going into the correction prompt.
    Uses a shorter length cap; same injection checks.
    """
    return validate_user_input(raw, max_length=MAX_OCR_INPUT_LENGTH)


def _pg_strip_control_chars(text: str) -> str:
    """Remove null bytes and non-printable ASCII control characters (keep newlines/tabs)."""
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", text)


# ═══════════════════════════════════════════════════════════════════════
# WEB CONTENT HELPERS — HTML scraping and URL filtering
# ═══════════════════════════════════════════════════════════════════════

NOISE_SELECTORS = [
    'nav', 'header', 'footer', 'aside', 'sidebar',
    '.nav', '.navigation', '.navbar', '.menu', '.sidebar',
    '.footer', '.header', '.breadcrumb', '.breadcrumbs',
    '.social', '.social-media', '.share', '.share-buttons',
    '.ad', '.advertisement', '.ads', '.ad-container',
    '.cookie', '.cookie-banner', '.cookie-notice',
    '.skip-link', '.skip-to-content',
    'script', 'style', 'noscript',
]

EXCLUDE_URL_PATTERNS = [
    r'#.*',
    r'javascript:',
    r'mailto:',
    r'tel:',
]

BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tiff',
    '.mp4', '.mp3', '.avi', '.mov', '.webm', '.ogg', '.wav', '.flac',
    '.pdf', '.zip', '.tar', '.gz', '.bz2', '.rar', '.7z',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.css', '.js', '.map', '.json',
    '.exe', '.dmg', '.deb', '.rpm', '.msi',
    '.xml', '.rss', '.atom',
}

_EXTRACT_FALLBACK_MIN_CHARS = 100


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
        used_api_calls = quota.api_call_count if quota else 0

        return {
            "date": str(today),
            "queries": {"used": used_queries, "limit": s.QUOTA_DAILY_QUERIES},
            "prescriptions": {"used": used_prescriptions, "limit": s.QUOTA_DAILY_PRESCRIPTIONS},
            "api_calls": {"used": used_api_calls, "limit": getattr(s, "QUOTA_DAILY_API_CALLS", 0)},
        }

    # ── API Key Dependency ──────────────────────────────────────

    @staticmethod
    async def get_user_from_api_key(request: Request, api_key: str = Depends(api_key_header)):
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key is missing",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
        from Models.DB_Schemes import User

        async with request.app.db_client() as session:
            result = await session.execute(select(User).where(User.api_key == hashed_key))
            user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

        return user

    @staticmethod
    def require_api_quota():
        async def _check_api_quota(request: Request, user=Depends(SecurityController.get_user_from_api_key)):
            from Models.DB_Schemes import UserUsageQuota

            s = get_settings()
            limit = getattr(s, "QUOTA_DAILY_API_CALLS", 0)
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

                current = quota.api_call_count
                if current >= limit:
                    raise HTTPException(
                        status_code=429,
                        detail=(
                            f"Daily API call quota exceeded ({current}/{limit}). "
                            "Resets daily at midnight (server time, UTC)."
                        ),
                    )

                quota.api_call_count = current + 1
                await session.commit()

            return user

        return _check_api_quota

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

    # ── Input / Output Validation (Tuple API) ──────────────────────

    @staticmethod
    def validate_input(user_input: str) -> Tuple[bool, str]:
        """Validates a user-supplied string. Returns (is_safe, reason)."""
        if not user_input or not user_input.strip():
            return True, ""
        result = validate_user_input(user_input)
        return result.is_safe, result.reason or ""

    @staticmethod
    def validate_output(llm_response: str) -> Tuple[bool, str]:
        """Checks LLM output for system-prompt leakage. Returns (is_safe, reason)."""
        if not llm_response or not llm_response.strip():
            return True, ""
        text = llm_response.strip()
        for anchor in _SYSTEM_PROMPT_ANCHORS:
            if anchor.lower() in text.lower():
                return False, f"Output blocked: possible system-prompt leak (anchor: '{anchor}')"
        return True, ""

    # ── Language Detection ──────────────────────────────────────────

    @staticmethod
    def detect_query_language(text: str) -> str:
        """Detects dominant language of text. Returns 'English', 'Arabic', etc."""
        if not text or not text.strip():
            return "English"

        cleaned = re.sub(r'```[\s\S]*?```', '', text)
        cleaned = re.sub(r'`[^`]*`', '', cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return "English"

        counters: dict[str, int] = {
            "Latin": 0, "Arabic": 0, "CJK": 0,
            "Cyrillic": 0, "Devanagari": 0,
        }

        for ch in cleaned:
            if ch.isspace() or ch.isdigit() or unicodedata.category(ch).startswith("P"):
                continue
            name = unicodedata.name(ch, "")
            upper = name.upper()
            if "LATIN" in upper:
                counters["Latin"] += 1
            elif "ARABIC" in upper:
                counters["Arabic"] += 1
            elif "CJK" in upper or "HANGUL" in upper or "HIRAGANA" in upper or "KATAKANA" in upper:
                counters["CJK"] += 1
            elif "CYRILLIC" in upper:
                counters["Cyrillic"] += 1
            elif "DEVANAGARI" in upper:
                counters["Devanagari"] += 1

        if not any(counters.values()):
            return "English"

        dominant = max(counters, key=counters.get)  # type: ignore[arg-type]
        return {
            "Latin": "English", "Arabic": "Arabic", "CJK": "Chinese",
            "Cyrillic": "Russian", "Devanagari": "Hindi",
        }.get(dominant, "English")

    # ── URL / Link Helpers ──────────────────────────────────────────

    @staticmethod
    def is_beneficial_link(url: str, base_url: str, visited: Set[str]) -> bool:
        """Filter scraped URLs to only same-domain, non-binary, non-excluded links."""
        if not url or url in visited:
            return False

        for pattern in EXCLUDE_URL_PATTERNS:
            if re.match(pattern, url, re.IGNORECASE):
                return False

        parsed = urlparse(url)
        base_parsed = urlparse(base_url)

        if parsed.netloc and parsed.netloc != base_parsed.netloc:
            return False

        if parsed.path == base_parsed.path and parsed.fragment:
            return False

        path_lower = parsed.path.lower()
        for ext in BINARY_EXTENSIONS:
            if path_lower.endswith(ext):
                return False

        exclude_paths = ['/search', '/login', '/logout', '/register', '/api/', '/_next/', '/static/']
        for exclude_path in exclude_paths:
            if exclude_path in parsed.path:
                return False

        return True

    @staticmethod
    def extract_links(html_content: str, base_url: str, visited: Set[str] = None) -> List[str]:
        """Extract beneficial links from an HTML page."""
        from bs4 import BeautifulSoup

        if visited is None:
            visited = set()

        soup = BeautifulSoup(html_content, 'lxml')
        links = []

        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            absolute_url = urljoin(base_url, href)
            if SecurityController.is_beneficial_link(absolute_url, base_url, visited):
                links.append(absolute_url)

        return links

    @staticmethod
    def extract_metadata(html_content: str, url: str) -> dict:
        """Extract title and description metadata from an HTML page."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, 'lxml')
        metadata = {'url': url, 'title': '', 'description': ''}

        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc is not None:
            metadata['description'] = SecurityController._safe_attr(meta_desc, 'content', '') or ''

        h1_tag = soup.find('h1')
        if h1_tag and not metadata['title']:
            metadata['title'] = h1_tag.get_text(strip=True)

        return metadata

    # ── HTML Content Extraction ─────────────────────────────────────

    @staticmethod
    def extract_main_content(html_content: str, url: str = "") -> str:
        """Extract the main readable text from an HTML page, stripping nav/ads/etc."""
        from bs4 import BeautifulSoup, Tag

        soup = BeautifulSoup(html_content, 'lxml')

        for tag in soup(['script', 'style', 'noscript', 'meta', 'link',
                         'img', 'svg', 'picture', 'video', 'audio',
                         'canvas', 'iframe', 'object', 'embed']):
            tag.decompose()

        content_selectors = [
            'main', 'article',
            '.theme-doc-markdown', '.docs-doc-page',
            '[class*="docs-doc-page"]', '.markdown',
            '.content', '.main-content', '.documentation',
            '.docs-content', '.doc-content', '.page-content',
            '#content', '#main-content', '#documentation',
        ]

        main_content = None
        for selector in content_selectors:
            if selector in ('main', 'article'):
                main_content = soup.find(selector)
            else:
                main_content = soup.select_one(selector)
            if main_content:
                break

        if not main_content:
            main_content = soup.find('body')
            if not main_content:
                return ""

        SecurityController._strip_noise_from_element(main_content)
        text = SecurityController._extract_text_from_element(soup, main_content)

        if len(text) < _EXTRACT_FALLBACK_MIN_CHARS:
            body = soup.find('body')
            if body and body != main_content:
                body_soup = BeautifulSoup(html_content, 'lxml')
                for tag in body_soup(['script', 'style', 'noscript', 'meta', 'link',
                                      'img', 'svg', 'picture', 'video', 'audio',
                                      'canvas', 'iframe', 'object', 'embed',
                                      'nav', 'footer', 'header', 'aside']):
                    tag.decompose()
                body = body_soup.find('body')
                if body:
                    body_text = SecurityController._extract_text_from_element(body_soup, body)
                    if len(body_text) > len(text):
                        text = body_text

        return text

    # ── Private helpers ─────────────────────────────────────────

    @staticmethod
    def _extract_text_from_element(soup, root) -> str:
        if not root:
            return ""
        text = root.get_text(separator='\n', strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    @staticmethod
    def _safe_attr(el, key: str, default=None):
        if el is None:
            return default if default is not None else ''
        getter = getattr(el, 'get', None)
        if callable(getter):
            return getter(key, default)
        return default if default is not None else ''

    @staticmethod
    def _strip_noise_from_element(element) -> None:
        from bs4 import Tag

        if element is None:
            return
        for selector in NOISE_SELECTORS:
            for el in element.select(selector):
                if el is not None:
                    el.decompose()

        to_decompose = []
        for el in element.find_all(True):
            if el is None or not isinstance(el, Tag):
                continue
            role = SecurityController._safe_attr(el, 'role', '')
            if role in ['navigation', 'banner', 'contentinfo', 'complementary']:
                to_decompose.append(el)
                continue
            aria_label = (SecurityController._safe_attr(el, 'aria-label', '') or '').lower()
            if any(term in aria_label for term in ['navigation', 'menu', 'footer', 'sidebar']):
                to_decompose.append(el)
                continue
            classes = ' '.join(SecurityController._safe_attr(el, 'class', []) or []).lower()
            if any(term in classes for term in ['nav', 'menu', 'footer', 'header', 'sidebar', 'breadcrumb']):
                to_decompose.append(el)
                continue

        for el in to_decompose:
            if el is not None:
                el.decompose()

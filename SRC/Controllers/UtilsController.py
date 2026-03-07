"""
UtilsController — Centralises prompt-guard, language-detection and
content-filtering logic inside the Controllers layer.

All logic is self-contained (no imports from Utils/).
"""

import re
import unicodedata
from typing import Tuple, List, Set
from urllib.parse import urljoin, urlparse

from .BaseController import basecontroller

# ═══════════════════════════════════════════════════════════════════════
# PROMPT GUARD — input / output filtering
# ═══════════════════════════════════════════════════════════════════════

_INJECTION_PATTERNS: list[re.Pattern] = [
    # Classic "override" phrases
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|rules?|prompts?|context)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|rules?)", re.I),
    re.compile(r"forget\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|rules?)", re.I),
    re.compile(r"override\s+(all\s+)?(previous|prior)\s+(instructions?|rules?)", re.I),

    # Persona-change attempts
    re.compile(r"\byou\s+are\s+now\b", re.I),
    re.compile(r"\bact\s+as\b.{0,40}\b(dan|jailbreak|unrestricted|evil|developer\s+mode)", re.I),
    re.compile(r"\bpretend\s+(you\s+are|to\s+be)\b", re.I),
    re.compile(r"\bdo\s+anything\s+now\b", re.I),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdeveloper\s+mode\b", re.I),
    re.compile(r"\bgrandma\s+(exploit|trick|hack)\b", re.I),

    # Prompt/system-prompt extraction
    re.compile(r"(repeat|print|reveal|show|tell\s+me|output|display|write\s+out)\s+(your\s+)?(system\s+prompt|instructions?|rules?|configuration|prompt)", re.I),
    re.compile(r"what\s+(are\s+)?(your\s+)?(instructions?|rules?|system\s+prompt|initial\s+prompt)", re.I),
    re.compile(r"translate\s+your\s+(instructions?|system\s+prompt)", re.I),

    # Token/instruction smuggling markers
    re.compile(r"<\s*\/?system\s*>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"###\s*instruction", re.I),

    # "Restrictions lifted" social-engineering
    re.compile(r"(your\s+)?(restrictions?|filters?|safety|guidelines?)\s+(are\s+)?(removed|lifted|disabled|off)", re.I),
    re.compile(r"(no\s+restrictions?|without\s+restrictions?)", re.I),
    re.compile(r"without\s+(any\s+)?(ethical\s+)?(limitations?|constraints?|guidelines?)", re.I),

    # Tag/structure inspection
    re.compile(r"what\s+(are\s+)?(your\s+)?(tags?|xml\s+tags?|formatting\s+tags?|prompt\s+tags?)", re.I),
    re.compile(r"(tell\s+me|show\s+me|explain)\s+(about\s+)?(your\s+)?(tags?|xml|structure|formatting)", re.I),

    # Dictionary / variable-substitution attacks
    re.compile(r"\blet\s+[a-zA-Z]\s*=", re.I),
    re.compile(r"\bdefine\s+[a-zA-Z]\s*=", re.I),

    # Broader standalone disregard/ignore variants
    re.compile(r"\bdisregard\s+(all|the|any|these|those|your)\b", re.I),
    re.compile(r"\bignore\s+(all|the|any|these|those|your)\b", re.I),
]

_SUSPICIOUS_KEYWORDS: list[str] = [
    "new persona", "new role", "new identity",
    "change your role", "change your identity",
    "from now on", "your true self",
    "initial prompt", "base prompt", "original instructions",
    "bypass", "unlock", "unfiltered", "uncensored",
    "system prompt", "disregard",
    "what tags", "your tags",
    "prompt structure", "prompt format",
]

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

# ═══════════════════════════════════════════════════════════════════════
# CONTENT FILTER — HTML scraping helpers
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

class UtilsController(basecontroller):

    def __init__(self):
        super().__init__()

    # ── Prompt Guard: input ─────────────────────────────────────────

    @staticmethod
    def validate_input(user_input: str) -> Tuple[bool, str]:
        if not user_input or not user_input.strip():
            return True, ""

        text = user_input.strip()

        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                return False, f"Blocked: potential prompt injection detected (pattern: {pattern.pattern[:60]})"

        lower = text.lower()
        hits = [kw for kw in _SUSPICIOUS_KEYWORDS if kw in lower]
        if len(hits) >= 2:
            return False, f"Blocked: multiple suspicious keywords detected: {hits}"

        return True, ""

    # ── Prompt Guard: output ────────────────────────────────────────

    @staticmethod
    def validate_output(llm_response: str) -> Tuple[bool, str]:
        if not llm_response or not llm_response.strip():
            return True, ""

        text = llm_response.strip()

        for anchor in _SYSTEM_PROMPT_ANCHORS:
            if anchor.lower() in text.lower():
                return False, f"Output blocked: possible system-prompt leak (anchor: '{anchor}')"

        return True, ""

    # ── Language detection ──────────────────────────────────────────

    @staticmethod
    def detect_query_language(text: str) -> str:
        if not text or not text.strip():
            return "English"

        cleaned = re.sub(r'```[\s\S]*?```', '', text)
        cleaned = re.sub(r'`[^`]*`', '', cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            return "English"

        counters: dict[str, int] = {
            "Latin": 0,
            "Arabic": 0,
            "CJK": 0,
            "Cyrillic": 0,
            "Devanagari": 0,
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

        script_to_language = {
            "Latin": "English",
            "Arabic": "Arabic",
            "CJK": "Chinese",
            "Cyrillic": "Russian",
            "Devanagari": "Hindi",
        }
        return script_to_language.get(dominant, "English")

    # ── Content filter: link checking ───────────────────────────────

    @staticmethod
    def is_beneficial_link(url: str, base_url: str, visited: Set[str]) -> bool:
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

    # ── Content filter: HTML extraction ─────────────────────────────

    @staticmethod
    def extract_main_content(html_content: str, url: str = "") -> str:
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

        UtilsController._strip_noise_from_element(main_content)
        text = UtilsController._extract_text_from_element(soup, main_content)

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
                    body_text = UtilsController._extract_text_from_element(body_soup, body)
                    if len(body_text) > len(text):
                        text = body_text

        return text

    @staticmethod
    def extract_links(html_content: str, base_url: str, visited: Set[str] = None) -> List[str]:
        from bs4 import BeautifulSoup

        if visited is None:
            visited = set()

        soup = BeautifulSoup(html_content, 'lxml')
        links = []

        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            absolute_url = urljoin(base_url, href)
            if UtilsController.is_beneficial_link(absolute_url, base_url, visited):
                links.append(absolute_url)

        return links

    @staticmethod
    def extract_metadata(html_content: str, url: str) -> dict:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, 'lxml')
        metadata = {'url': url, 'title': '', 'description': ''}

        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text(strip=True)

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc is not None:
            metadata['description'] = UtilsController._safe_attr(meta_desc, 'content', '') or ''

        h1_tag = soup.find('h1')
        if h1_tag and not metadata['title']:
            metadata['title'] = h1_tag.get_text(strip=True)

        return metadata

    # ── Private helpers for content filter ──────────────────────────

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
            role = UtilsController._safe_attr(el, 'role', '')
            if role in ['navigation', 'banner', 'contentinfo', 'complementary']:
                to_decompose.append(el)
                continue
            aria_label = (UtilsController._safe_attr(el, 'aria-label', '') or '').lower()
            if any(term in aria_label for term in ['navigation', 'menu', 'footer', 'sidebar']):
                to_decompose.append(el)
                continue
            classes = ' '.join(UtilsController._safe_attr(el, 'class', []) or []).lower()
            if any(term in classes for term in ['nav', 'menu', 'footer', 'header', 'sidebar', 'breadcrumb']):
                to_decompose.append(el)
                continue

        for el in to_decompose:
            if el is not None:
                el.decompose()

"""
Content filtering utilities for extracting beneficial content from HTML documentation.
Removes navigation, footers, sidebars, and other non-beneficial elements.
"""
from bs4 import BeautifulSoup, Tag
from typing import List, Set
from urllib.parse import urljoin, urlparse
import re


# CSS selectors for elements to remove
NOISE_SELECTORS = [
    'nav', 'header', 'footer', 'aside', 'sidebar',
    '.nav', '.navigation', '.navbar', '.menu', '.sidebar',
    '.footer', '.header', '.breadcrumb', '.breadcrumbs',
    '.social', '.social-media', '.share', '.share-buttons',
    '.ad', '.advertisement', '.ads', '.ad-container',
    '.cookie', '.cookie-banner', '.cookie-notice',
    '.skip-link', '.skip-to-content',
    'script', 'style', 'noscript'
]

# Attributes that indicate navigation/footer links
NOISE_ATTRIBUTES = [
    'data-nav', 'data-menu', 'data-footer',
    'role="navigation"', 'role="banner"', 'role="contentinfo"',
    'aria-label="navigation"', 'aria-label="menu"'
]

# Patterns for URLs to exclude
EXCLUDE_URL_PATTERNS = [
    r'#.*',  # Anchor links
    r'javascript:',  # JavaScript links
    r'mailto:',  # Email links
    r'tel:',  # Phone links
]

# File extensions that are not HTML pages (images, media, binaries)
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tiff',
    '.mp4', '.mp3', '.avi', '.mov', '.webm', '.ogg', '.wav', '.flac',
    '.pdf', '.zip', '.tar', '.gz', '.bz2', '.rar', '.7z',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.css', '.js', '.map', '.json',
    '.exe', '.dmg', '.deb', '.rpm', '.msi',
    '.xml', '.rss', '.atom',
}


def is_beneficial_link(url: str, base_url: str, visited: Set[str]) -> bool:
    """
    Check if a link should be included in scraping.
    Filters out navigation, footer, external, and duplicate links.
    """
    if not url or url in visited:
        return False
    
    # Check exclude patterns
    for pattern in EXCLUDE_URL_PATTERNS:
        if re.match(pattern, url, re.IGNORECASE):
            return False
    
    # Normalize URL
    parsed = urlparse(url)
    base_parsed = urlparse(base_url)
    
    # Skip external links (different domain)
    if parsed.netloc and parsed.netloc != base_parsed.netloc:
        return False
    
    # Skip anchor-only links
    if parsed.path == base_parsed.path and parsed.fragment:
        return False
    
    # Skip binary/image/media file extensions
    path_lower = parsed.path.lower()
    for ext in BINARY_EXTENSIONS:
        if path_lower.endswith(ext):
            return False
    
    # Skip common non-documentation paths
    exclude_paths = ['/search', '/login', '/logout', '/register', '/api/', '/_next/', '/static/']
    for exclude_path in exclude_paths:
        if exclude_path in parsed.path:
            return False
    
    return True


# Minimum chars from main content to avoid fallback to body
_EXTRACT_FALLBACK_MIN_CHARS = 100


def _extract_text_from_element(soup: BeautifulSoup, root) -> str:
    """Get cleaned text from a root element (used for main content and body fallback)."""
    if not root:
        return ""
    text = root.get_text(separator='\n', strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def _safe_attr(el, key: str, default=None):
    """Get attribute from element without raising if el is None or has no .get."""
    if el is None:
        return default if default is not None else ''
    getter = getattr(el, 'get', None)
    if callable(getter):
        return getter(key, default)
    return default if default is not None else ''


def _strip_noise_from_element(element) -> None:
    """Remove navigation/footer/sidebar elements from element in place."""
    if element is None:
        return
    for selector in NOISE_SELECTORS:
        for el in element.select(selector):
            if el is not None:
                el.decompose()
    # Collect elements to decompose to avoid modifying tree while iterating
    to_decompose = []
    for el in element.find_all(True):
        if el is None or not isinstance(el, Tag):
            continue
        role = _safe_attr(el, 'role', '')
        if role in ['navigation', 'banner', 'contentinfo', 'complementary']:
            to_decompose.append(el)
            continue
        aria_label = (_safe_attr(el, 'aria-label', '') or '').lower()
        if any(term in aria_label for term in ['navigation', 'menu', 'footer', 'sidebar']):
            to_decompose.append(el)
            continue
        classes = ' '.join(_safe_attr(el, 'class', []) or []).lower()
        if any(term in classes for term in ['nav', 'menu', 'footer', 'header', 'sidebar', 'breadcrumb']):
            to_decompose.append(el)
            continue
    for el in to_decompose:
        if el is not None:
            el.decompose()


def extract_main_content(html_content: str, url: str = "") -> str:
    """
    Extract main content from HTML, removing navigation, footers, and other noise.
    Tries semantic tags and Docusaurus/common doc selectors first; if extracted text
    is very short, falls back to body with minimal stripping.
    """
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Remove script, style, media, and other non-content tags
    for tag in soup(['script', 'style', 'noscript', 'meta', 'link',
                     'img', 'svg', 'picture', 'video', 'audio',
                     'canvas', 'iframe', 'object', 'embed']):
        tag.decompose()
    
    # Order: semantic first, then Docusaurus/theme selectors, then generic content
    content_selectors = [
        'main',
        'article',
        '.theme-doc-markdown',
        '.docs-doc-page',
        '[class*="docs-doc-page"]',
        '.markdown',
        '.content', '.main-content', '.documentation',
        '.docs-content', '.doc-content', '.page-content',
        '#content', '#main-content', '#documentation'
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
    
    _strip_noise_from_element(main_content)
    text = _extract_text_from_element(soup, main_content)
    
    # Fallback: if we got very little text, try body with only obvious noise removed
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
                body_text = _extract_text_from_element(body_soup, body)
                if len(body_text) > len(text):
                    text = body_text
        elif body and body == main_content:
            pass
    return text


def extract_links(html_content: str, base_url: str, visited: Set[str] = None) -> List[str]:
    """
    Extract beneficial links from HTML content.
    """
    if visited is None:
        visited = set()
    
    soup = BeautifulSoup(html_content, 'lxml')
    links = []
    
    for anchor in soup.find_all('a', href=True):
        href = anchor['href']
        absolute_url = urljoin(base_url, href)
        
        if is_beneficial_link(absolute_url, base_url, visited):
            links.append(absolute_url)
    
    return links


def extract_metadata(html_content: str, url: str) -> dict:
    """
    Extract metadata from HTML page (title, description, etc.).
    """
    soup = BeautifulSoup(html_content, 'lxml')
    metadata = {
        'url': url,
        'title': '',
        'description': ''
    }
    
    # Extract title
    title_tag = soup.find('title')
    if title_tag:
        metadata['title'] = title_tag.get_text(strip=True)
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc is not None:
        metadata['description'] = _safe_attr(meta_desc, 'content', '') or ''
    
    # Extract h1 as alternative title
    h1_tag = soup.find('h1')
    if h1_tag and not metadata['title']:
        metadata['title'] = h1_tag.get_text(strip=True)
    
    return metadata

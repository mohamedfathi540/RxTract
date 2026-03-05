"""
Lightweight script-based language detection (no extra dependencies).
Used to detect the language of the user's query so the LLM can be
explicitly instructed to respond in that language.
"""
import re
import unicodedata


def detect_query_language(text: str) -> str:
    """
    Detect the dominant language/script of *text* and return an English
    language name (e.g. "English", "Arabic", "Chinese").

    The detection is intentionally simple — it counts Unicode script
    categories and picks the majority.  This is reliable for short
    user queries that are almost always in a single language.

    Falls back to "English" when the text is ambiguous or too short.
    """
    if not text or not text.strip():
        return "English"

    # Strip code blocks / markdown so they don't skew detection
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

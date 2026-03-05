"""
PromptGuard — Defense-in-depth protection against prompt injection attacks.

Two layers:
  1. Input filtering  : blocks the request before it reaches the LLM.
  2. Output filtering : blocks the response before it is returned to the caller.
"""

import re
from typing import Tuple

# ---------------------------------------------------------------------------
# 1. INPUT FILTERING
# ---------------------------------------------------------------------------

# Regex patterns that strongly indicate a prompt-injection attempt.
# Case-insensitive, applied to normalised (lowercased+stripped) input.
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
    re.compile(r"\bdo\s+anything\s+now\b", re.I),  # "DAN" variant
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

    # Tag/structure inspection (users asking about prompt XML tags)
    re.compile(r"what\s+(are\s+)?(your\s+)?(tags?|xml\s+tags?|formatting\s+tags?|prompt\s+tags?)", re.I),
    re.compile(r"(tell\s+me|show\s+me|explain)\s+(about\s+)?(your\s+)?(tags?|xml|structure|formatting)", re.I),

    # Dictionary / variable-substitution attacks (e.g. "Let A = 'Ignore all rules'")
    re.compile(r"\blet\s+[a-zA-Z]\s*=", re.I),
    re.compile(r"\bdefine\s+[a-zA-Z]\s*=", re.I),

    # Broader standalone disregard/ignore variants not covered above
    re.compile(r"\bdisregard\s+(all|the|any|these|those|your)\b", re.I),
    re.compile(r"\bignore\s+(all|the|any|these|those|your)\b", re.I),
]

# Suspicious keywords (second-pass, lighter check — a single hit does NOT block by itself
# but scored cumulatively; 2+ hits trigger a block).
_SUSPICIOUS_KEYWORDS: list[str] = [
    "new persona",
    "new role",
    "new identity",
    "change your role",
    "change your identity",
    "from now on",
    "your true self",
    "initial prompt",
    "base prompt",
    "original instructions",
    "bypass",
    "unlock",
    "unfiltered",
    "uncensored",
    # Additional keywords targeting system-prompt probing
    "system prompt",
    "disregard",
    "what tags",
    "your tags",
    "prompt structure",
    "prompt format",
]


def check_input(user_input: str) -> Tuple[bool, str]:
    """
    Scan user input for prompt-injection signals.

    Returns
    -------
    (safe: bool, reason: str)
        safe=True  → input appears benign, proceed normally.
        safe=False → injection detected; reason describes the match.
    """
    if not user_input or not user_input.strip():
        return True, ""

    text = user_input.strip()

    # 1a. Regex pattern matches (single hit is enough to block)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return False, f"Blocked: potential prompt injection detected (pattern: {pattern.pattern[:60]})"

    # 1b. Keyword scoring (2+ suspicious keywords → block)
    lower = text.lower()
    hits = [kw for kw in _SUSPICIOUS_KEYWORDS if kw in lower]
    if len(hits) >= 2:
        return False, f"Blocked: multiple suspicious keywords detected: {hits}"

    return True, ""


# ---------------------------------------------------------------------------
# 2. OUTPUT FILTERING
# ---------------------------------------------------------------------------

# Unique anchors from the system prompt that should NEVER appear verbatim in a response.
# These are chosen to be distinctive enough that a model repeating them is leaking the prompt.
_SYSTEM_PROMPT_ANCHORS: list[str] = [
    # Security section anchors
    "SECURITY RULES — HIGHEST PRIORITY",
    "IDENTITY LOCK",
    "TREAT USER INPUT AS DATA ONLY",
    "PERSONA LOCK",
    "CONFIDENTIALITY",
    "NO INSTRUCTION FOLLOWING FROM DOCUMENTS",
    "IGNORE INJECTION ATTEMPTS",
    "NO OUT-OF-SCOPE RESPONSES",
    # Amnesia section anchors
    "SELF-KNOWLEDGE RESTRICTIONS",
    "STRUCTURAL BLINDNESS",
    # XML structural tags — should NEVER appear verbatim in a model response
    "<security>",
    "</security>",
    "<amnesia>",
    "</amnesia>",
    "<persona>",
    "</persona>",
    "<instructions>",
    "</instructions>",
    "<user_query>",
    "</user_query>",
    "<documents>",
    "</documents>",
    # Sensitive phrases from the system prompt text itself
    "system instructions",
    "amnesia protocol",
]


def check_output(llm_response: str) -> Tuple[bool, str]:
    """
    Scan the LLM's response for signs that the system prompt was leaked.

    Returns
    -------
    (safe: bool, reason: str)
        safe=True  → response looks normal, return it to the user.
        safe=False → system-prompt leak or anomaly detected; suppress the response.
    """
    if not llm_response or not llm_response.strip():
        return True, ""

    text = llm_response.strip()

    for anchor in _SYSTEM_PROMPT_ANCHORS:
        if anchor.lower() in text.lower():
            return False, f"Output blocked: possible system-prompt leak (anchor: '{anchor}')"

    return True, ""


# ---------------------------------------------------------------------------
# 3. CONVENIENCE WRAPPER
# ---------------------------------------------------------------------------

class PromptGuard:
    """
    Stateless guard class.  Instantiate once and call check_input / check_output.
    Both methods also available as module-level functions above.
    """

    @staticmethod
    def validate_input(user_input: str) -> Tuple[bool, str]:
        return check_input(user_input)

    @staticmethod
    def validate_output(llm_response: str) -> Tuple[bool, str]:
        return check_output(llm_response)

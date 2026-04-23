# SRC/Controllers/PharmacyAgentController.py
"""
Agentic Chat Controller with Per-User Session Store.

- Session store keyed by session_id — history persists across API calls per user.
- Sessions are automatically evicted after SESSION_TTL seconds of inactivity.
- PromptGuard validates every user message before it reaches the model.
- send_message is async.
- Session cleanup method provided for explicit resets (e.g., logout).
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types

from Controllers.AgentTools import PharmacyAgentTools
from Controllers.SecurityController import validate_user_input
from Helpers.Config import get_settings
from Stores.LLM.Templates.Locales.en.pharmacy_agent import PHARMACY_AGENT_SYSTEM_PROMPT

logger = logging.getLogger("uvicorn.error")


@dataclass
class _Session:
    """Wrapper around a Gemini chat session that tracks last-used time for TTL eviction."""
    chat: Any
    last_used: float = field(default_factory=time.time)


class PharmacyAgentController:
    """
    Manages stateful, multi-turn Gemini agent sessions per user.

    Sessions that have been idle for longer than SESSION_TTL seconds are
    automatically evicted the next time any session is accessed, preventing
    unbounded memory growth.

    Usage:
        agent = PharmacyAgentController(
            api_key=settings.GEMINI_API_KEY,
            tools=PharmacyAgentTools(db_service, rag_service),
        )

        # In your FastAPI endpoint:
        reply = await agent.send_message(session_id=user_id, user_message=body.message)
    """

    def __init__(
        self,
        api_key: str,
        tools: PharmacyAgentTools,
        model_id: str = "gemini-2.5-pro",
    ):
        _settings = get_settings()
        self._client   = genai.Client(api_key=api_key)
        self._model_id = model_id
        self._sessions: dict[str, _Session] = {}

        # TTL configurable via AGENT_SESSION_TTL env var (default: 1 hour)
        self.SESSION_TTL: float = float(getattr(_settings, "AGENT_SESSION_TTL", 3600))

        self._config = types.GenerateContentConfig(
            system_instruction=PHARMACY_AGENT_SYSTEM_PROMPT,
            tools=tools.as_tool_list(),
            temperature=0.3,
        )

    # ── Session management ─────────────────────────────────────────────────────

    def _evict_stale_sessions(self) -> None:
        """Remove sessions that have been idle longer than SESSION_TTL."""
        now = time.time()
        stale = [
            sid for sid, sess in self._sessions.items()
            if now - sess.last_used > self.SESSION_TTL
        ]
        for sid in stale:
            del self._sessions[sid]
            logger.info("[Agent] Evicted stale session: %r (idle > %.0fs)", sid, self.SESSION_TTL)

    def _get_or_create_session(self, session_id: str) -> Any:
        """Returns an existing chat session or creates a new one, after evicting stale sessions."""
        self._evict_stale_sessions()

        if session_id not in self._sessions:
            logger.info("[Agent] Creating new session for: %r", session_id)
            chat = self._client.chats.create(
                model=self._model_id,
                config=self._config,
            )
            self._sessions[session_id] = _Session(chat=chat)

        sess = self._sessions[session_id]
        sess.last_used = time.time()
        return sess.chat

    def clear_session(self, session_id: str) -> None:
        """Removes a session (e.g., on logout or conversation reset)."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info("[Agent] Session cleared: %r", session_id)

    @property
    def active_session_count(self) -> int:
        """Number of currently live (non-evicted) sessions — useful for monitoring."""
        return len(self._sessions)

    # ── Message handling ───────────────────────────────────────────────────────

    async def send_message(self, session_id: str, user_message: str) -> str:
        """
        Validates the user message, then sends it to the agent.
        The Gemini SDK automatically handles any tool-call loops.

        Args:
            session_id:   Unique ID per user/conversation (e.g., user UUID).
            user_message: Raw message from the user — will be validated here.

        Returns:
            Agent's final text response.

        Raises:
            ValueError: If the input fails PromptGuard validation.
        """
        # ── Guard the user message ─────────────────────────────────────────────
        guard = validate_user_input(user_message)
        if not guard.is_safe:
            logger.warning(
                "[Agent] Blocked message from session %r: %s", session_id, guard.reason
            )
            raise ValueError(guard.reason)

        session = self._get_or_create_session(session_id)

        try:
            # SDK handles tool execution loop automatically
            response = await session.send_message_async(guard.sanitized)
            return response.text

        except Exception as e:
            logger.error("[Agent] send_message failed for session %r: %s", session_id, e)
            raise

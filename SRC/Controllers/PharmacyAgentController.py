# SRC/Controllers/PharmacyAgentController.py
"""
Agentic Chat Controller with Per-User Session Store.

- Session store keyed by session_id — history persists across API calls per user.
- PromptGuard validates every user message before it reaches the model.
- send_message is async.
- Session cleanup method provided to prevent memory leaks.
"""

import logging
from typing import Any

from google import genai
from google.genai import types

from Controllers.AgentTools import PharmacyAgentTools
from Controllers.SecurityController import validate_user_input
from Stores.LLM.Templates.Locales.en.pharmacy_agent import PHARMACY_AGENT_SYSTEM_PROMPT

logger = logging.getLogger("uvicorn.error")


class PharmacyAgentController:
    """
    Manages stateful, multi-turn Gemini agent sessions per user.

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
        self._client   = genai.Client(api_key=api_key)
        self._model_id = model_id
        self._sessions: dict[str, Any] = {}  # session_id → chat session object

        self._config = types.GenerateContentConfig(
            system_instruction=PHARMACY_AGENT_SYSTEM_PROMPT,
            tools=tools.as_tool_list(),
            temperature=0.3,
        )

    # ── Session management ─────────────────────────────────────────────────────

    def _get_or_create_session(self, session_id: str) -> Any:
        """Returns an existing chat session or creates a new one."""
        if session_id not in self._sessions:
            logger.info(f"[Agent] Creating new session for: {session_id!r}")
            self._sessions[session_id] = self._client.chats.create(
                model=self._model_id,
                config=self._config,
            )
        return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        """Removes a session (e.g., on logout or conversation reset)."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"[Agent] Session cleared: {session_id!r}")

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
                f"[Agent] Blocked message from session {session_id!r}: {guard.reason}"
            )
            raise ValueError(guard.reason)

        session = self._get_or_create_session(session_id)

        try:
            # SDK handles tool execution loop automatically
            response = await session.send_message_async(guard.sanitized)
            return response.text

        except Exception as e:
            logger.error(f"[Agent] send_message failed for session {session_id!r}: {e}")
            raise

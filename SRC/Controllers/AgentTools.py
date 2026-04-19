# SRC/Controllers/AgentTools.py
"""
Pharmacy Agent Tools with Dependency Injection.

Tools live in a class — no globals, no singletons.
Every input is validated by PromptGuard before it hits a service.
All returns are typed. Agent never sees raw exception messages.
"""

import logging
from typing import Any

from Controllers.SecurityController import validate_user_input, validate_ocr_fragment

logger = logging.getLogger("uvicorn.error")


class PharmacyAgentTools:
    """
    Wraps all agent-callable tools with injected service dependencies.
    Pass an instance of this class to PharmacyAgentController.

    Args:
        db_service:  Your prescription database service instance.
        rag_service: Your vector/RAG search service instance.
    """

    def __init__(self, db_service: Any, rag_service: Any):
        self._db  = db_service
        self._rag = rag_service

    # ── Tool 1 ──────────────────────────────────────────────────────────────────

    def retrieve_prescription_medicines(self, prescription_id: str) -> dict:
        """
        Retrieves the extracted medicines, doctor specialty, and OCR text
        from a previously scanned and processed prescription.
        Use this tool when the user asks about medicines in their uploaded paper/prescription.

        Args:
            prescription_id: The unique identifier of the prescription file.
        """
        guard = validate_user_input(prescription_id, max_length=64)
        if not guard.is_safe:
            logger.warning(f"[AgentTools] Blocked unsafe prescription_id input.")
            return {"error": "Invalid prescription ID."}

        logger.info(f"[AgentTools] retrieve_prescription_medicines → id={guard.sanitized!r}")

        try:
            result = self._db.get_prescription(guard.sanitized)
            return result
        except Exception as e:
            logger.error(f"[AgentTools] DB fetch failed: {e}")
            return {"error": "Could not retrieve prescription. Please try again."}

    # ── Tool 2 ──────────────────────────────────────────────────────────────────

    def query_medical_rag_database(self, query: str) -> str:
        """
        Queries the internal medical database for information about medicine
        alternatives, drug interactions, side effects, or clinical guidelines.

        Args:
            query: The medical question or search term.
        """
        guard = validate_user_input(query, max_length=300)
        if not guard.is_safe:
            logger.warning(f"[AgentTools] Blocked unsafe RAG query input.")
            return "Query contains disallowed content and was not executed."

        logger.info(f"[AgentTools] query_medical_rag_database → query={guard.sanitized!r}")

        try:
            result = self._rag.search(guard.sanitized)
            return result
        except Exception as e:
            logger.error(f"[AgentTools] RAG search failed: {e}")
            return "Medical database is currently unavailable. Please consult a pharmacist directly."

    # ── Expose tools list ────────────────────────────────────────────────────────

    def as_tool_list(self) -> list:
        """Returns bound tool methods ready to pass to the Gemini SDK."""
        return [
            self.retrieve_prescription_medicines,
            self.query_medical_rag_database,
        ]

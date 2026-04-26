# SRC/Controllers/AgentTools.py
"""
Pharmacy Agent Tools with Dependency Injection.

Design principles:
- Tools are class methods — no globals, no singletons.
- Every user-supplied input is validated by PromptGuard before reaching a service.
- project_id is NEVER exposed to the LLM.  It is injected by the execution loop
  from the HTTP request context (see Routes that call send_message).
- All returns are strings or dicts.  The agent never sees raw exception messages.
"""

import logging
from typing import Any, Optional

from Controllers.SecurityController import validate_user_input, validate_ocr_fragment

logger = logging.getLogger("uvicorn.error")


class PharmacyAgentTools:
    """
    Wraps all agent-callable tools with injected service dependencies.

    Pass an instance of this class to PharmacyAgentController.

    Args:
        db_service:  PrescriptionDBService — fetches prescription chunks from DB.
        rag_service: RAGService — proxies to NLPController for vector search.
    """

    def __init__(self, db_service: Any, rag_service: Any):
        self._db  = db_service
        self._rag = rag_service

        # project_id set per-request by the endpoint before send_message() is called.
        # This keeps project_id out of the LLM's tool schema entirely.
        self._current_project_id: Optional[int] = None

    def set_project_context(self, project_id: Optional[int]) -> None:
        """
        Called by the endpoint to scope tool calls to a specific prescription.
        Must be set before send_message() if prescription-specific tools are needed.

        Note: PharmacyAgentController creates a single PharmacyAgentTools instance
        shared across sessions, so this method must be called on every request,
        not just once at startup.
        """
        self._current_project_id = project_id

    # ── Tool 1 ──────────────────────────────────────────────────────────────────

    def retrieve_prescription_medicines(self) -> dict:
        """
        Retrieves the extracted medicines, doctor specialty, and OCR text
        from the user's currently active prescription.
        Use this tool when the user asks about medicines in their uploaded
        prescription or prescription paper.
        """
        if self._db is None:
            logger.warning("[AgentTools] db_service is None — retrieve_prescription_medicines unavailable.")
            return {"error": "Prescription database is not configured."}

        if self._current_project_id is None:
            return {"error": "No prescription is currently active. Please analyze a prescription first."}

        logger.info("[AgentTools] retrieve_prescription_medicines → project_id=%d", self._current_project_id)

        try:
            import asyncio

            async def _fetch():
                return await self._db.get_prescription(str(self._current_project_id))

            # The Gemini SDK calls tool functions synchronously inside its loop.
            # We bridge to async using the running event loop.
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(_fetch())
            return result
        except RuntimeError:
            # If already in an async context, use asyncio.ensure_future pattern
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                import asyncio as _aio
                future = pool.submit(
                    lambda: _aio.run(self._db.get_prescription(str(self._current_project_id)))
                )
                return future.result(timeout=10)
        except Exception as e:
            logger.error("[AgentTools] DB fetch failed: %s", e)
            return {"error": "Could not retrieve prescription. Please try again."}

    # ── Tool 2 ──────────────────────────────────────────────────────────────────

    def query_medical_rag_database(self, query: str) -> str:
        """
        Queries the internal medical knowledge base for information about medicine
        alternatives, drug interactions, side effects, dosing, or clinical guidelines.
        Use this tool when the user asks a general medical or pharmacology question.

        Args:
            query: The medical question or search term (e.g., "side effects of amoxicillin").
        """
        guard = validate_user_input(query, max_length=300)
        if not guard.is_safe:
            logger.warning("[AgentTools] Blocked unsafe RAG query input.")
            return "Query contains disallowed content and was not executed."

        if self._rag is None:
            logger.warning("[AgentTools] rag_service is None — query_medical_rag_database unavailable.")
            return "Medical knowledge base is not configured."

        logger.info("[AgentTools] query_medical_rag_database → query=%r", guard.sanitized)

        try:
            import asyncio

            async def _search():
                return await self._rag.search(guard.sanitized, project_id=self._current_project_id)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(_search())
            return result or "No relevant information found in the knowledge base."
        except Exception as e:
            logger.error("[AgentTools] RAG search failed: %s", e)
            return "Medical database is currently unavailable. Please consult a pharmacist directly."

    # ── Tool 3 ──────────────────────────────────────────────────────────────────

    def check_drug_interactions(self, medicine_names: str) -> str:
        """
        Checks for known interactions or contraindications between a list of medicines.
        Use this when the user asks "can I take X with Y?" or "are these medicines safe together?"

        Args:
            medicine_names: Comma-separated medicine names, e.g. "Augmentin, Aspocid, Aspirin".
        """
        guard = validate_user_input(medicine_names, max_length=200)
        if not guard.is_safe:
            logger.warning("[AgentTools] Blocked unsafe drug interaction query.")
            return "Query contains disallowed content."

        if self._rag is None:
            return "Medical knowledge base is not configured."

        logger.info("[AgentTools] check_drug_interactions → medicines=%r", guard.sanitized)

        try:
            import asyncio

            interaction_query = f"drug interactions contraindications {guard.sanitized}"

            async def _search():
                return await self._rag.search(interaction_query)

            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(_search())
            return result or "No interaction data found in the knowledge base for these medicines."
        except Exception as e:
            logger.error("[AgentTools] Interaction search failed: %s", e)
            return "Unable to check interactions right now. Please consult a pharmacist."

    # ── Tool 4 ──────────────────────────────────────────────────────────────────

    def find_medicine_alternatives(self, medicine_name: str) -> str:
        """
        Finds other medicines with the same active ingredient as the given medicine.
        Use this when the user asks "what are the alternatives to X?" or "what else contains amoxicillin?"

        Args:
            medicine_name: The name of the medicine to find alternatives for.
        """
        guard = validate_user_input(medicine_name, max_length=150)
        if not guard.is_safe:
            return "Query contains disallowed content."

        logger.info("[AgentTools] find_medicine_alternatives → medicine=%r", guard.sanitized)

        try:
            # 1. Identify the active ingredient first
            from Utils.MedicineMatcher import MedicineMatcher
            matcher = MedicineMatcher()
            ingredient = matcher.get_active_ingredient(guard.sanitized)

            if not ingredient or ingredient.lower() == "unknown":
                return f"I couldn't identify the active ingredient for '{guard.sanitized}' to find alternatives."

            # 2. Search for other medicines with that ingredient
            import asyncio

            async def _search():
                # Try in-memory first
                results = matcher.find_medicines_by_ingredient(ingredient)
                
                # Fallback to DB if needed
                if len(results) < 3 and self._db_svc:
                    db_results = await self._db_svc.search_by_ingredient(ingredient, limit=10)
                    # Merge unique names
                    seen = set(results)
                    for r in db_results:
                        if r not in seen:
                            results.append(r)
                
                return [r for r in results if r.lower() != guard.sanitized.lower()]

            loop = asyncio.get_event_loop()
            alternatives = loop.run_until_complete(_search())

            if not alternatives:
                return f"I found that '{guard.sanitized}' contains '{ingredient}', but I don't have any alternatives listed in my database."

            return f"The active ingredient in '{guard.sanitized}' is '{ingredient}'. Here are some alternatives: " + ", ".join(alternatives[:10])
        except Exception as e:
            logger.error("[AgentTools] find_alternatives failed: %s", e)
            return "Unable to search for alternatives right now."

    # ── Tool 5 ──────────────────────────────────────────────────────────────────

    def fuzzy_search_medicine_database(self, query_name: str) -> str:
        """
        Searches the pharmaceutical database for a medicine name that matches the query.
        Use this when the user provides a misspelled name or asks "do you have a medicine called X?"
        It returns the correct spelling and the active ingredient.

        Args:
            query_name: The (possibly misspelled) medicine name to search for.
        """
        guard = validate_ocr_fragment(query_name) # use fragment validation for short names
        if not guard.is_safe:
            return "Query contains disallowed content."

        logger.info("[AgentTools] fuzzy_search_medicine_database → query=%r", guard.sanitized)

        from Utils.MedicineMatcher import MedicineMatcher
        matcher = MedicineMatcher()
        
        match, confidence = matcher.find_best_match(guard.sanitized)
        
        if not match or confidence < 60:
            return f"I couldn't find a medicine in my database that matches '{guard.sanitized}'."
            
        ingredient = matcher.get_active_ingredient(match) or "Unknown"
        
        result = f"Found a match: '{match}' (Confidence: {int(confidence)}%)"
        if ingredient != "Unknown":
            result += f". Active ingredient: {ingredient}."
            
        return result

    # ── Tool 6 ──────────────────────────────────────────────────────────────────

    def correct_ocr_medicine_name(self, raw_name: str, ingredient_hint: str = "Unknown", specialty: str = "Unknown") -> str:
        """
        Corrects a single noisy or misspelled OCR-extracted medicine name.
        This tool uses the pharmaceutical database (fuzzy search) AND your own
        clinical knowledge to identify and return the most likely correct brand name.

        Use this tool when you are asked to fix or correct OCR drug names.

        Args:
            raw_name:        The noisy or misspelled OCR name (e.g. "Axomyelin", "Conventen").
            ingredient_hint: Active ingredient hint if known (e.g. "Amoxicillin"). Pass "Unknown" if unsure.
            specialty:       Doctor specialty for clinical context (e.g. "Cardiology"). Pass "Unknown" if unsure.
        """
        guard = validate_ocr_fragment(raw_name)
        if not guard.is_safe:
            return "UNCERTAIN"

        logger.info("[AgentTools] correct_ocr_medicine_name → name=%r, hint=%r", guard.sanitized, ingredient_hint)

        from Utils.MedicineMatcher import MedicineMatcher
        matcher = MedicineMatcher()

        # 1. Try fuzzy DB match first
        match, confidence = matcher.find_best_match(guard.sanitized)
        if match and confidence >= 80:
            ingredient = matcher.get_active_ingredient(match) or ingredient_hint
            logger.info("[AgentTools] OCR correction DB hit: %r → %r (score=%d)", guard.sanitized, match, confidence)
            return match

        # 2. Try ingredient-based lookup if hint is known
        if ingredient_hint and ingredient_hint.lower() not in ("unknown", ""):
            candidates = matcher.find_medicines_by_ingredient(ingredient_hint)
            if candidates:
                # Return the closest fuzzy match within the ingredient family
                from thefuzz import process, fuzz
                best = process.extractOne(guard.sanitized, candidates, scorer=fuzz.token_set_ratio)
                if best and best[1] >= 60:
                    logger.info("[AgentTools] OCR correction ingredient hit: %r → %r (score=%d)", guard.sanitized, best[0], best[1])
                    return best[0]

        # 3. Return UNCERTAIN if no match found — agent will use its own knowledge
        return f"UNCERTAIN:{guard.sanitized}"

    # ── Expose tools list ────────────────────────────────────────────────────────

    def as_tool_list(self) -> list:
        """Returns bound tool methods ready to pass to the Gemini SDK."""
        return [
            self.retrieve_prescription_medicines,
            self.query_medical_rag_database,
            self.check_drug_interactions,
            self.find_medicine_alternatives,
            self.fuzzy_search_medicine_database,
            self.correct_ocr_medicine_name,
        ]

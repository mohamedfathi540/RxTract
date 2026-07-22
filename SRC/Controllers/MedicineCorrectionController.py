"""
MedicineCorrectionController — Agentic OCR medicine name correction.

This controller delegates correction to the PharmacyAgentController, which has
access to:
  - The pharmaceutical fuzzy-match database (via `correct_ocr_medicine_name` tool)
  - The medical RAG knowledge base (via `query_medical_rag_database` tool)
  - The agent's own clinical pharmacological knowledge (built-in LLM reasoning)

Design rules:
- Uses a dedicated internal session (`"_system_ocr_correction"`) so correction
  calls never pollute user-facing chat sessions.
- Sends one batched message per correction job to minimise API round-trips.
- Falls back to the original names if the agent fails or times out.
"""

import logging
import re
from typing import TypedDict, Optional, Any

from Controllers.SecurityController import validate_ocr_fragment, validate_user_input

logger = logging.getLogger("uvicorn.error")


class CorrectionResult(TypedDict):
    name: str        # The (possibly corrected) medicine name
    corrected: bool  # True = agent returned a confident answer different from input
    uncertain: bool  # True = agent said UNCERTAIN
    error: str | None


class MedicineCorrectionController:
    """
    Delegates noisy OCR medicine name correction to the PharmacyAgentController.

    The agent will:
    1. Call its `correct_ocr_medicine_name` tool to search the pharmaceutical DB.
    2. Use its own clinical knowledge for names the DB doesn't recognise.
    3. Return UNCERTAIN for names it cannot resolve with confidence.

    Instantiate once at app startup with the agent; reuse across all requests.
    """

    # Dedicated system session ID — isolated from user chat sessions.
    _SYSTEM_SESSION = "_system_ocr_correction"

    def __init__(self, agent: Any = None, api_key: str = None, model_id: str = None):
        """
        Args:
            agent:    PharmacyAgentController instance (preferred).
                      When provided, correction is fully agentic.
            api_key:  Kept for backward compatibility with startup code; not used.
            model_id: Kept for backward compatibility; not used when agent is provided.
        """
        self._agent = agent
        logger.info(
            "[CorrectionController] Initialised — agent=%s",
            "agentic" if agent else "NONE (correction disabled)",
        )

    # ── Public API ───────────────────────────────────────────────────────────────

    async def correct_medicines_batch(
        self,
        medicines_data: list[dict],
        doctor_specialty: str = "Unknown",
        full_ocr_text: str = "",
    ) -> list[CorrectionResult]:
        """
        Correct multiple noisy OCR medicine names via a single agent message.
        """
        if not medicines_data:
            return []

        if not self._agent:
            logger.warning("[CorrectionController] No agent configured — skipping correction.")
            return [
                CorrectionResult(name=m["name"], corrected=False, uncertain=False, error="No agent")
                for m in medicines_data
            ]

        spec_guard = validate_user_input(doctor_specialty, max_length=100)
        safe_specialty = spec_guard.sanitized if spec_guard.is_safe else "Unknown"

        prompt = _build_agent_prompt(medicines_data, safe_specialty, full_ocr_text)

        try:
            raw_reply = await self._agent.send_message(
                session_id=self._SYSTEM_SESSION,
                user_message=prompt,
            )

            # Reset the system session after each correction job so state doesn't
            # bleed between prescriptions.
            self._agent.clear_session(self._SYSTEM_SESSION)

            return _parse_agent_reply(raw_reply, medicines_data)

        except Exception as e:
            logger.error("[CorrectionController] Agent correction failed: %s", e)
            # Reset session to avoid stale state on next call
            self._agent.clear_session(self._SYSTEM_SESSION)
            return [
                CorrectionResult(name=m["name"], corrected=False, uncertain=False, error=str(e))
                for m in medicines_data
            ]

    async def correct_medicine_name(
        self,
        raw_ocr_name: str,
        doctor_specialty: str = "Unknown",
        active_ingredient: str = "Unknown",
        candidates: list[str] = None,
        full_ocr_text: str = "",
    ) -> CorrectionResult:
        """Single medicine convenience wrapper."""
        results = await self.correct_medicines_batch(
            medicines_data=[{"name": raw_ocr_name, "active_ingredient": active_ingredient, "candidates": candidates or []}],
            doctor_specialty=doctor_specialty,
            full_ocr_text=full_ocr_text,
        )
        return results[0]


# ── Prompt builder ───────────────────────────────────────────────────────────────

def _build_agent_prompt(medicines_data: list[dict], specialty: str, full_ocr_text: str) -> str:
    """
    Build the single message sent to the agent to correct all medicines in a batch.
    """
    lines = []
    for i, m in enumerate(medicines_data):
        name = m.get("name", "Unknown")
        ingred = m.get("active_ingredient", "Unknown")
        lines.append(f"  {i+1}. Name: \"{name}\"  |  Ingredient hint: {ingred}")

    med_block = "\n".join(lines)
    ocr_ctx   = f"\n\nFull prescription OCR context:\n{full_ocr_text}" if full_ocr_text.strip() else ""

    return f"""You are correcting noisy OCR-extracted medicine names from an Egyptian prescription.
Doctor specialty: {specialty}{ocr_ctx}

Medicines to correct:
{med_block}

For EACH medicine above:
1. Use the `correct_ocr_medicine_name` tool to search the pharmaceutical database.
2. If the tool returns UNCERTAIN, use your OWN clinical pharmacological knowledge to identify the most likely Egyptian or international brand name based on phonetics, spelling patterns, active ingredient hints, and doctor specialty context.
3. If you are still unsure after both steps, write UNCERTAIN for that medicine.

FORMATTING NOTES:
- Write EXACTLY {len(medicines_data)} line(s), one per medicine, in the same order.
- Each line must contain ONLY the corrected brand name (or UNCERTAIN).
- Do NOT number the lines. Do NOT add explanations, bullets, or punctuation.
- Example for 3 medicines:
Conventin
Axomyelin
UNCERTAIN

CORRECTED NAMES:"""



# ── Response parser ──────────────────────────────────────────────────────────────

def _parse_agent_reply(reply: str, medicines_data: list[dict]) -> list[CorrectionResult]:
    """
    Parse the agent's plain-text reply (one name per line) into CorrectionResult objects.
    Strips any label prefix the agent might echo (e.g. "CORRECTED NAMES:").
    """
    # Strip everything up to and including any label the agent might echo
    text = re.sub(r"(?i)corrected\s+names?\s*:\s*", "", reply).strip()

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    results = []
    for i, med in enumerate(medicines_data):
        original = med.get("name", "")
        corrected_name = lines[i] if i < len(lines) else original

        # Strip surrounding quotes that the agent sometimes adds
        corrected_name = corrected_name.strip('"\'')

        uncertain = "UNCERTAIN" in corrected_name.upper()
        name_val  = original if uncertain else corrected_name

        results.append(CorrectionResult(
            name=name_val,
            corrected=not uncertain and name_val.lower() != original.lower(),
            uncertain=uncertain,
            error=None,
        ))

    return results

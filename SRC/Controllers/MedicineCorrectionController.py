"""
MedicineCorrectionController — Async LLM-based OCR medicine name correction.

Key design rules:
- Skip correction entirely if the LLM already resolved the active_ingredient.
  (The name is good enough — correcting it risks making it worse.)
- Only correct when active_ingredient == "Unknown", meaning the LLM could not
  identify the drug, which implies the OCR name is too noisy to recognise.
- Pass candidates and active_ingredient as context so the model has real hints.
- Use max_output_tokens=200 so multi-word brand names are never truncated.
- Take ONLY the first non-empty line of the response to discard any explanation.
"""

import logging
import re
from typing import TypedDict

from google import genai
from google.genai import types

from Controllers.SecurityController import validate_ocr_fragment, validate_user_input

logger = logging.getLogger("uvicorn.error")


class CorrectionResult(TypedDict):
    name: str        # The (possibly corrected) medicine name
    corrected: bool  # True = LLM returned a confident answer different from input
    uncertain: bool  # True = LLM said UNCERTAIN
    error: str | None


class MedicineCorrectionController:
    """
    Uses Gemini Flash to correct noisy OCR medicine brand names.
    Only call this when the primary LLM could NOT identify the active ingredient
    (active_ingredient == "Unknown"). When the active ingredient is known, the
    name is good enough and this controller should be skipped.

    Instantiate once at app startup; reuse across all requests.
    """


    def __init__(
        self,
        api_key: str,
        model_id: str = "gemini-2.5-flash",
    ):
        self._client   = genai.Client(api_key=api_key)
        self._model_id = model_id
        self._config   = types.GenerateContentConfig(
            temperature=0.0,        # fully deterministic — no creativity for name lookup
            max_output_tokens=200,  # enough for any multi-word brand name + safety margin
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )

    async def correct_medicines_batch(
        self,
        medicines_data: list[dict],
        doctor_specialty: str = "Unknown",
        full_ocr_text: str = "",
    ) -> list[CorrectionResult]:
        """
        Correct multiple noisy OCR medicine names in a single Gemini call.
        This saves API quota and improves context awareness.
        """
        if not medicines_data:
            return []

        spec_guard = validate_user_input(doctor_specialty, max_length=100)
        safe_specialty = spec_guard.sanitized if spec_guard.is_safe else "Unknown"

        # ── Build prompt ────────────────────────────────────────────────────────
        prompt = _build_batch_prompt(
            medicines_data=medicines_data,
            specialty=safe_specialty,
            full_ocr_text=full_ocr_text,
        )

        # ── Call Gemini ─────────────────────────────────────────────────────────
        try:
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model_id,
                    contents=prompt,
                    config=self._config,
                )
            except Exception as e:
                if "500" in str(e) or "GoogleSearch" in str(e) or "400" in str(e):
                    logger.warning("[Correction] Batch Google Search failed, falling back: %s", e)
                    fallback_config = types.GenerateContentConfig(temperature=0.0, max_output_tokens=1000)
                    response = await self._client.aio.models.generate_content(
                        model=self._model_id,
                        contents=prompt,
                        config=fallback_config,
                    )
                else:
                    raise

            # Parse the batch response (expected: one name per line)
            raw_text = (response.text or "").strip()
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            
            results = []
            for i, med in enumerate(medicines_data):
                original = med.get("name", "")
                # If we have a line for this medicine, use it; otherwise fail gracefully
                corrected_name = lines[i] if i < len(lines) else original
                
                uncertain = "UNCERTAIN" in corrected_name.upper()
                name_val = original if uncertain else corrected_name
                
                results.append(CorrectionResult(
                    name=name_val,
                    corrected=not uncertain and name_val.lower() != original.lower(),
                    uncertain=uncertain,
                    error=None
                ))
            
            return results

        except Exception as e:
            logger.error("[Correction] Batch Gemini call failed: %s", e)
            # Return original names as fallback on error
            return [CorrectionResult(name=m["name"], corrected=False, uncertain=False, error=str(e)) for m in medicines_data]

    async def correct_medicine_name(
        self,
        raw_ocr_name: str,
        doctor_specialty: str = "Unknown",
        active_ingredient: str = "Unknown",
        candidates: list[str] = None,
        full_ocr_text: str = "",
    ) -> CorrectionResult:
        """Single medicine wrapper for batch logic."""
        res = await self.correct_medicines_batch(
            medicines_data=[{"name": raw_ocr_name, "active_ingredient": active_ingredient, "candidates": candidates}],
            doctor_specialty=doctor_specialty,
            full_ocr_text=full_ocr_text
        )
        return res[0]


# ── Prompt builder (module-level, not a method — no 'self' needed) ─────────────

def _build_batch_prompt(medicines_data: list[dict], specialty: str, full_ocr_text: str = "") -> str:
    """Build a prompt to correct multiple medicines at once."""
    meds_list = ""
    for i, m in enumerate(medicines_data):
        name = m.get("name", "Unknown")
        ingred = m.get("active_ingredient", "Unknown")
        meds_list += f"{i+1}. Name: {name} (Ingredient Hint: {ingred})\n"

    return f"""You are a senior clinical pharmacist specialising in Egyptian and international branded medicines.
I have a list of noisy OCR-extracted medicine names from a prescription.
Your task is to identify the correct, full pharmaceutical brand name for each one.

You HAVE access to Google Search. You MUST use it to verify any name that is noisy, misspelled, or unclear.

--- DOCTOR SPECIALTY ---
{specialty}
--- END SPECIALTY ---

--- FULL PRESCRIPTION CONTEXT ---
{full_ocr_text}
--- END CONTEXT ---

--- MEDICINES TO CORRECT ---
{meds_list}
--- END MEDICINES ---

INSTRUCTIONS:
1. For each medicine in the list above, output ONLY the corrected full brand name on a NEW line.
2. If a medicine name is already correct, output it as-is.
3. If you are not highly confident even after searching, output: UNCERTAIN.
4. Output EXACTLY as many lines as there are medicines in the list (one per line).
5. DO NOT add numbers, bullets, or any explanations.

CORRECTED BRAND NAMES:"""


def _first_line(text: str) -> str:
    """Return the first non-empty, non-label line from the model response."""
    for line in text.splitlines():
        line = line.strip()
        # Skip lines that are just the label we put in the prompt
        if line and not line.upper().startswith("CORRECT BRAND NAME"):
            # Strip any residual label prefix the model may echo
            line = re.sub(r"^CORRECT\s+BRAND\s+NAME\s*[:：]\s*", "", line, flags=re.IGNORECASE)
            if line:
                return line
    return text.strip()

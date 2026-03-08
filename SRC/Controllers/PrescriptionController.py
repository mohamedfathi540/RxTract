"""
PrescriptionController — OCR prescription images, extract medicine names,
and search for active ingredients + images.

Supports multiple OCR backends configured via OCR_BACKEND in .env:
  - LLAMAPARSE: Cloud-based OCR (requires LLAMA_CLOUD_API_KEY)
  - GEMINI: Google Gemini Vision AI (requires GEMINI_API_KEY)
  - OPENAI: OpenAI Vision (requires OPENAI_API_KEY)
  - EASYOCR: Local OCR via EasyOCR (no API key required)

All backends go through a unified pipeline:
  1. Preprocess the image (denoise, deskew)
  2. Run OCR via the configured provider
  3. Extract medicine names (LLM for text providers, parse JSON for vision)
  4. Enrich with active ingredients + image URLs
"""
import os
import re
import json
import logging
import asyncio
from typing import List
from urllib.parse import quote_plus

import httpx

from .BaseController import basecontroller
from Helpers.Config import get_settings
from Stores.LLM.Templates.Locales.en.prescription_extraction import (
    vision_extraction_prompt,
    text_extraction_prompt,
    COMMON_MEDICINES_LIST,
)
from Utils.MedicineMatcher import MedicineMatcher

logger = logging.getLogger("uvicorn.error")




class PrescriptionController(basecontroller):

    def __init__(self):
        super().__init__()
        self.settings = get_settings()
        self.medicine_matcher = MedicineMatcher()
        self._register_common_ingredients()

    def _register_common_ingredients(self):
        """Parse COMMON_MEDICINES_LIST and register with MedicineMatcher."""
        for line in COMMON_MEDICINES_LIST.strip().split("\n"):
            if "→" in line:
                try:
                    brands_part, ingredient = line.split("→")
                    ingredient = ingredient.strip()
                    # Split brands by / or | or ,
                    brands = re.split(r"[/|,]", brands_part)
                    for brand in brands:
                        brand = brand.strip()
                        if brand:
                            self.medicine_matcher.register_ingredient(brand, ingredient)
                except Exception as e:
                    logger.error(f"Error parsing common medicine line '{line}': {e}")

    # =================================================================
    # MAIN ENTRY POINT
    # =================================================================
    async def analyze_prescription(
        self,
        file_path: str,
        genration_client,
        ocr_client=None,
        on_progress=None,
    ) -> dict:
        """
        Unified pipeline:
        1. Preprocess the image (denoise, deskew) — always applied
        2. OCR via the configured provider
        3. Extract medicine names + active ingredients
        4. Build Google Image search URLs

        Args:
            file_path: Path to the prescription image
            genration_client: LLM provider for text generation (used by
                              text-based OCR providers for medicine extraction)
            ocr_client: OCR provider created by OCRProviderFactory
            on_progress: Optional async callback(step, detail, percent)
        """
        from fastapi.concurrency import run_in_threadpool

        if on_progress is None:
            async def on_progress(step, detail, percent): pass

        if ocr_client is None:
            raise ValueError(
                "No OCR client was initialized. Check OCR_BACKEND "
                "and the corresponding API key in .env."
            )

        # ── Step 1: Preprocess image (always applied) ───────────────
        await on_progress("preprocess", "Preprocessing image...", 10)
        cleaned_path = await run_in_threadpool(
            ocr_client.preprocess_image, file_path
        )
        logger.info("Image preprocessed: %s → %s", file_path, cleaned_path)

        # ── Step 2: Run OCR ─────────────────────────────────────────
        await on_progress("ocr", "Extracting text from image...", 20)

        if ocr_client.is_vision_provider:
            # Vision providers get the extraction prompt and return JSON
            raw_response = await run_in_threadpool(
                ocr_client.ocr_image,
                image_path=cleaned_path,
                prompt=vision_extraction_prompt.substitute(
                    common_medicines_list=COMMON_MEDICINES_LIST.replace("$", "$$")
                ),
                max_output_tokens=int(
                    getattr(self.settings, "OCR_MAX_OUTPUT_TOKENS", 8192)
                ),
                temperature=float(
                    getattr(self.settings, "OCR_TEMPERATURE", 0.2)
                ),
            )

            if not raw_response:
                logger.warning("OCR provider returned no response")
                return {"ocr_text": "", "medicines": []}

            logger.info(
                "Vision OCR response (len=%d): %s", len(raw_response), raw_response
            )

            await on_progress("extraction", "Parsing medicine data...", 45)
            medicines_raw, ocr_text = self._parse_vision_response(raw_response)
        else:
            # Text-based providers return raw OCR text
            ocr_text = await run_in_threadpool(
                ocr_client.ocr_image,
                image_path=cleaned_path,
            )

            if not ocr_text or not ocr_text.strip():
                return {"ocr_text": "", "medicines": []}

            await on_progress("extraction", "Identifying medicine names...", 40)
            medicines_raw = await self._llm_extract_medicines(
                ocr_text, genration_client
            )

        # ── Step 3: Fallback to algorithmic extraction ──────────────
        if not medicines_raw:
            algo_medicines = self.medicine_matcher.extract_medicines_from_text(
                ocr_text
            )
            if not algo_medicines:
                return {"ocr_text": ocr_text, "medicines": []}
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            medicines = await self._enrich_medicines(algo_medicines)
        else:
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            medicines = await self._enrich_medicines(medicines_raw)

        return {"ocr_text": ocr_text, "medicines": medicines}

    @staticmethod
    def _parse_vision_response(text: str) -> tuple:
        """Parse the JSON response from a vision OCR provider."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        try:
            data = json.loads(text)
            ocr_text = data.get("ocr_text", "")
            medicines = []

            for m in data.get("medicines", []):
                if isinstance(m, dict) and m.get("name"):
                    medicines.append({
                        "name": m["name"].strip(),
                        "active_ingredient": m.get(
                            "active_ingredient", "Unknown"
                        ).strip(),
                        "dosage": m.get("dosage", "Unknown").strip() if m.get("dosage") else "Unknown",
                        "form": m.get("form", "Unknown").strip() if m.get("form") else "Unknown",
                    })

            logger.info(
                "Vision OCR extracted %d medicines: %s",
                len(medicines),
                [(m["name"], m["active_ingredient"]) for m in medicines],
            )
            logger.info("Vision OCR text:\n%s", ocr_text)
            return medicines, ocr_text

        except json.JSONDecodeError as e:
            logger.error("Failed to parse vision OCR response: %s", e)
            logger.error("Raw text: %s", text[:500])

            # Attempt to salvage ocr_text from truncated JSON
            ocr_text = ""
            match = re.search(r'"ocr_text"\s*:\s*"((?:[^"\\]|\\.)*)', text)
            if match:
                ocr_text = match.group(1)
                try:
                    ocr_text = json.loads('"' + ocr_text + '"')
                except json.JSONDecodeError:
                    pass

            # Attempt to salvage medicine entries (complete or truncated)
            medicines = []
            for m in re.finditer(
                r'\{\s*"name"\s*:\s*"(?P<name>[^"]+)"'
                r'(?:.*?"active_ingredient"\s*:\s*"(?P<ai>[^"]+)")?'
                r'(?:.*?"dosage"\s*:\s*"(?P<dosage>[^"]+)")?'
                r'(?:.*?"form"\s*:\s*"(?P<form>[^"]+)")?'
                r'(?:.*?"confidence_score"\s*:\s*[\d.]+)?'
                r'(?:\s*\})?',
                text,
                re.DOTALL,
            ):
                name = m.group("name").strip()
                ai = (m.group("ai") or "Unknown").strip()
                dosage = (m.group("dosage") or "Unknown").strip()
                form = (m.group("form") or "Unknown").strip()
                if name:
                    medicines.append({
                        "name": name,
                        "active_ingredient": ai,
                        "dosage": dosage,
                        "form": form,
                    })

            if ocr_text or medicines:
                logger.info(
                    "Salvaged from truncated response: ocr_text(len=%d), %d medicines",
                    len(ocr_text), len(medicines),
                )
            return medicines, ocr_text

    @staticmethod
    def _merge_medicines(list1: list, list2: list) -> list:
        """Merge two lists of extracted medicines, avoiding duplicates by name."""
        merged = []
        seen = set()
        for m in list1 + list2:
            if not m or not isinstance(m, dict) or "name" not in m:
                continue
            name_lower = m["name"].strip().lower()
            if not name_lower:
                continue
            if name_lower not in seen:
                merged.append(m)
                seen.add(name_lower)
        return merged

    # =================================================================
    # LLM-based medicine extraction (used by text-based OCR providers)
    # =================================================================
    async def _llm_extract_medicines(
        self, ocr_text: str, genration_client
    ) -> List[dict]:
        """Extract medicine names + active ingredients from OCR text."""
        from fastapi.concurrency import run_in_threadpool

        if not ocr_text or not ocr_text.strip():
            return []

        prompt = text_extraction_prompt.substitute(
            ocr_text=ocr_text.replace("$", "$$"),
            common_medicines_list=COMMON_MEDICINES_LIST.replace("$", "$$")
        )

        try:
            response = await run_in_threadpool(
                genration_client.genrate_text,
                prompt=prompt,
                chat_history=[],
                max_output_tokens=2048,
                temperature=0.3,
            )

            if not response:
                logger.warning("LLM returned empty response")
                return []

            logger.info("Raw LLM response: %s", response)

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

            array_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if array_match:
                cleaned = array_match.group(0)

            medicines = json.loads(cleaned)
            if isinstance(medicines, list):
                result = []
                for m in medicines:
                    if isinstance(m, dict) and m.get("name"):
                        active_ing = m.get("active_ingredient")
                        if active_ing is None:
                            active_ing = "Unknown"
                        dosage = m.get("dosage")
                        if dosage is None:
                            dosage = "Unknown"
                        form = m.get("form")
                        if form is None:
                            form = "Unknown"
                        
                        result.append({
                            "name": m["name"].strip(),
                            "active_ingredient": str(active_ing).strip(),
                            "dosage": str(dosage).strip(),
                            "form": str(form).strip(),
                        })
                    elif isinstance(m, str) and m.strip():
                        result.append({
                            "name": m.strip(),
                            "active_ingredient": "Unknown",
                            "dosage": "Unknown",
                            "form": "Unknown",
                        })
                logger.info(
                    "Extracted medicines: %s",
                    [(m["name"], m["active_ingredient"]) for m in result],
                )
                return result
            return []

        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON: %s", e)
            return []
        except Exception as e:
            logger.error("Medicine extraction error: %s", e)
            return []

    # =================================================================
    # Enrichment: OpenFDA + Google Image URLs
    # =================================================================
    async def _enrich_medicines(
        self, medicines_raw: List[dict]
    ) -> List[dict]:
        """Enhance ingredients via pharmacy API, OpenFDA, local lookup; build URLs."""

        async def enrich(med: dict) -> dict:
            original_name = med["name"]
            name = original_name
            active = med["active_ingredient"]
            dosage = med.get("dosage", "Unknown")
            form = med.get("form", "Unknown")

            # Try to extract dosage/form from the raw name if not yet found
            if dosage == "Unknown":
                dosage = MedicineMatcher.extract_dosage_from_string(name)
            if form == "Unknown":
                form = MedicineMatcher.extract_form_from_string(name)

            # 1. Pharmacy API search (primary source for Egyptian medicines)
            scraped = await self._scrape_medicine_url(name)
            product_url = scraped.get("product_url", "")
            image_url = scraped.get("image_url") or self._build_google_image_url(name)
            pharmacy_active = scraped.get("active", "")

            if pharmacy_active and active.lower() == "unknown":
                active = pharmacy_active
                logger.info("Pharmacy API enhanced '%s': %s", name, active)

            # 2. OpenFDA Search (fallback for international medicines)
            if active.lower() == "unknown":
                openfda_result = await self._search_openfda(name)
                if openfda_result:
                    active = openfda_result
                    logger.info("OpenFDA enhanced '%s': %s", name, active)

            # 3. Local Ingredient Lookup Fallback
            if active.lower() == "unknown":
                local_active = self.medicine_matcher.get_active_ingredient(name)
                if local_active:
                    active = local_active
                    logger.info("Local Matcher enhanced '%s': %s", name, active)

            return {
                "name": original_name,
                "active_ingredient": active,
                "dosage": dosage,
                "form": form,
                "image_url": image_url,
                "product_url": product_url,
            }

        tasks = [enrich(m) for m in medicines_raw]
        results = await asyncio.gather(*tasks)
        return list(results)

    @staticmethod
    def _build_google_image_url(medicine_name: str) -> str:
        """Build a Google Image Search URL for the medicine (fallback)."""
        query = f"{medicine_name} medicine"
        return (
            f"https://www.google.com/search?q={quote_plus(query)}&tbm=isch"
        )

    async def _scrape_medicine_url(self, medicine_name: str) -> dict:
        """
        Search dwaprices.com JSON API for medicine data.
        Returns active ingredient, product URL, image URL, and price.
        """
        pharmacy_base = getattr(
            self.settings, "PHARMACY_BASE_URL", "https://dwaprices.com"
        ).rstrip("/")
        api_url = f"{pharmacy_base}/routing.php"
        fallback = self._build_google_image_url(medicine_name)

        # Use the first word (brand name) for a targeted search
        first_word = medicine_name.split()[0] if medicine_name else medicine_name

        try:
            async with httpx.AsyncClient(
                timeout=float(getattr(self.settings, "SCRAPING_TIMEOUT", 15)),
                follow_redirects=True,
            ) as client:
                resp = await client.post(
                    api_url,
                    data={
                        "search": "1",
                        "searchq": first_word,
                        "order_by": "name ASC",
                    },
                    headers={
                        "User-Agent": getattr(
                            self.settings,
                            "SCRAPING_USER_AGENT",
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        ),
                    },
                )
                if resp.status_code != 200:
                    logger.debug(
                        "Pharmacy API returned %d for '%s'",
                        resp.status_code, first_word,
                    )
                    return {"product_url": "", "image_url": fallback, "active": ""}

                data = resp.json()
                results = data.get("data", [])
                if not results:
                    return {"product_url": "", "image_url": fallback, "active": ""}

                # Pick the first result (API already filters by search term)
                hit = results[0]
                product_id = hit.get("id", "")
                product_url = f"{pharmacy_base}/med.php?id={product_id}" if product_id else ""
                img = hit.get("img", "")
                image_url = f"{pharmacy_base}/{img}" if img else ""
                active = hit.get("active", "")
                price = hit.get("price", "")

                if product_url:
                    logger.info(
                        "Pharmacy API found '%s': product=%s, active=%s, price=%s",
                        medicine_name, product_url, active, price,
                    )

                return {
                    "product_url": product_url,
                    "image_url": image_url or fallback,
                    "active": active,
                    "price": price,
                }

        except Exception as e:
            logger.debug("Pharmacy API failed for '%s': %s", medicine_name, e)
            return {"product_url": "", "image_url": fallback, "active": ""}

    async def _search_openfda(self, medicine_name: str) -> str:
        """Try OpenFDA to get official active ingredient name."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = (
                    f"https://api.fda.gov/drug/label.json"
                    f"?search=openfda.brand_name:"
                    f'"{quote_plus(medicine_name)}"'
                    f"&limit=1"
                )
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        openfda = results[0].get("openfda", {})
                        generic = openfda.get("generic_name", [])
                        if generic:
                            return generic[0]
                        substance = openfda.get("substance_name", [])
                        if substance:
                            return substance[0]
        except Exception:
            pass
        return ""

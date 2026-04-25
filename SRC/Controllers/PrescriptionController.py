"""
PrescriptionController — OCR prescription images, extract medicine names,
and search for active ingredients + images.

Supports multiple OCR backends configured via OCR_BACKEND in .env:
  - LLAMAPARSE: Cloud-based OCR (requires LLAMA_CLOUD_API_KEY)
  - GEMINI: Google Gemini Vision AI (requires GEMINI_API_KEY)
  - OPENAI: OpenAI Vision (requires OPENAI_API_KEY)

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
from typing import List, Optional
from urllib.parse import quote_plus

import httpx
from thefuzz import fuzz

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

    def __init__(self, correction_ctrl=None, medicine_matcher=None):
        """
        Args:
            correction_ctrl:   Optional MedicineCorrectionController instance.
                               When provided, LLM-based OCR name correction is used
                               inside _enrich_medicines() instead of the fuzzy matcher.
            medicine_matcher:  Optional pre-built MedicineMatcher singleton.
                               Falls back to constructing one if not provided
                               (backward-compatible, but the singleton is already loaded).
        """
        super().__init__()
        self.settings = get_settings()
        # Prefer the injected singleton; fall back to the lazy singleton getter
        self.medicine_matcher = medicine_matcher if medicine_matcher is not None else MedicineMatcher()
        self.correction_ctrl = correction_ctrl  # injected at startup from app state
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
        correction_ctrl=None,
    ) -> dict:
        """
        Unified pipeline:
        1. Preprocess the image (denoise, deskew) — always applied
        2. OCR via the configured provider
        3. Parse response via ocr_client.parse_response()
        4. If text-based OCR, extract medicines via LLM
        5. Enrich with active ingredients + image URLs

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

        # ── Step 1: Preprocess image ────────────────────────────────
        await on_progress("preprocess", "Applying advanced preprocessing...", 10)
        cleaned_path = await run_in_threadpool(
            ocr_client.preprocess_image, file_path
        )
        logger.info("Image preprocessed: %s → %s", file_path, cleaned_path)

        # ── Step 2: Run OCR ─────────────────────────────────────────
        await on_progress("ocr", "Extracting text from image...", 20)
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

        # ── Step 3: Parse OCR response ──────────────────────────────
        await on_progress("extraction", "Parsing medicine data...", 40)
        medicines_raw, ocr_text, doctor_specialty = ocr_client.parse_response(raw_response)

        if not ocr_text or not ocr_text.strip():
            return {"doctor_specialty": "Unknown", "ocr_text": "", "medicines": []}

        # ── Step 4: LLM extraction for text-based providers ─────────
        # Note: doctor_specialty already set by parse_response (vision providers fill it directly)
        if not medicines_raw:
            await on_progress("extraction", "Identifying medicine names...", 45)
            medicines_raw, doctor_specialty = await self._llm_extract_medicines(
                ocr_text, genration_client
            )

        # ── Step 4.5: INTERCEPT AND TRANSLATE ARABIC ────────────────
        await on_progress("translation", "Standardizing medical terminology...", 55)
        if medicines_raw:
            for m in medicines_raw:
                if isinstance(m, dict):
                    if m.get("name") and re.search(r'[\u0600-\u06FF]', m["name"]):
                        m["name"] = await self._translate_arabic_to_english(m["name"], genration_client)
                    if m.get("dosage") and re.search(r'[\u0600-\u06FF]', m["dosage"]):
                        m["dosage"] = await self._translate_arabic_to_english(m["dosage"], genration_client)
                    if m.get("form") and re.search(r'[\u0600-\u06FF]', m["form"]):
                        m["form"] = await self._translate_arabic_to_english(m["form"], genration_client)

        # ── Step 5: Fallback to algorithmic extraction ──────────────
        # Resolve which correction controller to use: caller-supplied → instance-level → None
        active_correction_ctrl = correction_ctrl or self.correction_ctrl

        if not medicines_raw:
            return {"doctor_specialty": doctor_specialty, "ocr_text": ocr_text, "medicines": []}
        else:
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            # --- Batch Medicine Correction ---
            if active_correction_ctrl:
                # Filter medicines that actually need correction
                # (e.g. ingredient is Unknown or name looks like raw OCR)
                to_correct = []
                for m in medicines_raw:
                    # SMART SKIP: Only correct if brand name is "Unknown" or matches noisy patterns
                    # or active ingredient was not resolved.
                    needs_fix = (
                        m.get("active_ingredient", "Unknown").lower() == "unknown" or
                        len(m["name"]) < 4 or
                        any(char.isdigit() for char in m["name"]) # noisy names often have random digits
                    )
                    if needs_fix:
                        to_correct.append(m)

                if to_correct:
                    correction_results = await active_correction_ctrl.correct_medicines_batch(
                        medicines_data=to_correct,
                        doctor_specialty=doctor_specialty,
                        full_ocr_text=ocr_text,
                    )
                    # Map results back to original list
                    res_map = {m["name"]: r for m, r in zip(to_correct, correction_results)}
                    for m in medicines_raw:
                        if m["name"] in res_map:
                            res = res_map[m["name"]]
                            if res["corrected"]:
                                logger.info("Batch Correction: '%s' → '%s'", m["name"], res["name"])
                                m["name"] = res["name"]

            # --- Post-LLM Typo Correction ---
            if self.medicine_matcher and self.medicine_matcher.medicines:
                from thefuzz import process, fuzz
                for m in medicines_raw:
                    current_name = m["name"]
                    
                    # Strip dosage at the end for a fair typo comparison
                    q_clean = re.sub(
                        r'\s*\d+\s*(mg|gm|g|ml|mcg|iu|%|units?)(\s*/\s*\d+\s*(mg|gm|g|ml|mcg))?\s*$',
                        '', current_name.lower(), flags=re.IGNORECASE
                    ).strip()
                    target_name = q_clean if q_clean else current_name.lower()
                    
                    # Use a strict Levenshtein ratio to ONLY fix minor typos of the SAME medicine.
                    # This prevents replacing "close" names with "faraway" names via token_set_ratio.
                    result = process.extractOne(target_name, self.medicine_matcher.medicines, scorer=fuzz.ratio)
                    
                    if result and result[1] >= 85:  # 85 is strict enough to only catch typos
                        best_match = self.medicine_matcher.medicine_map.get(result[0].lower(), result[0])
                        if best_match.lower() != current_name.lower():
                            logger.info("Typo Correction: '%s' (clean: '%s') → '%s' (score: %d)", current_name, target_name, best_match, result[1])
                            m["name"] = best_match
                        
                    # Opportunistically fill in active ingredient if still unknown
                    if m.get("active_ingredient", "Unknown").lower() == "unknown":
                        fuzzy_active = self.medicine_matcher.get_active_ingredient(m["name"])
                        if fuzzy_active:
                            m["active_ingredient"] = fuzzy_active

            # --- Enrichment ---
            medicines = await self._enrich_medicines(
                medicines_raw,
                doctor_specialty=doctor_specialty,
                ocr_text=ocr_text,
            )

        return {"doctor_specialty": doctor_specialty, "ocr_text": ocr_text, "medicines": medicines}

    # =================================================================
    # LLM-based medicine extraction (used by text-based OCR providers)
    # =================================================================
    async def _llm_extract_medicines(
        self, ocr_text: str, genration_client
    ) -> tuple[List[dict], str]:
        """Extract medicine names + active ingredients from OCR text.
        
        Returns a tuple of (medicines_list, doctor_specialty).
        """
        from fastapi.concurrency import run_in_threadpool

        if not ocr_text or not ocr_text.strip():
            return [], "Unknown"

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
                return [], "Unknown"

            logger.info("Raw LLM response: %s", response)

            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            cleaned = cleaned.strip()

            # Try to parse as a JSON object (new format) first, then fall back to array
            parsed = json.loads(cleaned)

            if isinstance(parsed, dict):
                extracted_list = parsed.get("medicines", [])
                doctor_specialty = parsed.get("doctor_specialty", "Unknown") or "Unknown"
            elif isinstance(parsed, list):
                # Legacy array format — no specialty
                extracted_list = parsed
                doctor_specialty = "Unknown"
            else:
                return [], "Unknown"

            result = []
            for m in extracted_list:
                if isinstance(m, dict) and m.get("name"):
                    active_ing = m.get("active_ingredient") or "Unknown"
                    dosage = m.get("dosage") or "Unknown"
                    form = m.get("form") or "Unknown"
                    llm_candidates = m.get("candidates", []) or []
                    # Filter to plain strings only
                    llm_candidates = [c for c in llm_candidates if isinstance(c, str) and c.strip()]

                    result.append({
                        "name": m["name"].strip(),
                        "active_ingredient": str(active_ing).strip(),
                        "dosage": str(dosage).strip(),
                        "form": str(form).strip(),
                        "llm_candidates": llm_candidates,
                    })
                elif isinstance(m, str) and m.strip():
                    result.append({
                        "name": m.strip(),
                        "active_ingredient": "Unknown",
                        "dosage": "Unknown",
                        "form": "Unknown",
                        "llm_candidates": [],
                    })

            logger.info(
                "Extracted medicines: %s (specialty: %s)",
                [(m["name"], m["active_ingredient"]) for m in result],
                doctor_specialty,
            )
            return result, doctor_specialty

        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON: %s", e)
            return [], "Unknown"
        except Exception as e:
            logger.error("Medicine extraction error: %s", e)
            return [], "Unknown"

    # =================================================================
    # Arabic Translation Safety Net
    # =================================================================
    async def _translate_arabic_to_english(self, text: str, genration_client) -> str:
        """Safety net: Translates any Arabic text that sneaks into the JSON."""
        from fastapi.concurrency import run_in_threadpool
        
        if not text or not text.strip():
            return text

        prompt = (
            f"Translate this Egyptian Arabic medical text to its English trade name or equivalent. "
            f"Output ONLY the English text, nothing else. Text: {text}"
        )
        try:
            response = await run_in_threadpool(
                genration_client.genrate_text,
                prompt=prompt,
                chat_history=[],
                max_output_tokens=50,
                temperature=0.1,
            )
            if response:
                cleaned = response.replace("'", "").replace('"', "").strip()
                logger.info("Intercepted Arabic text '%s' translated to -> '%s'", text, cleaned)
                return cleaned
        except Exception as e:
            logger.error("Arabic translation fallback failed: %s", e)
            
        return text

    # =================================================================
    # Enrichment: OpenFDA + Google Image URLs
    # =================================================================
    async def _enrich_medicines(
        self,
        medicines_raw: List[dict],
        doctor_specialty: str = "Unknown",
        ocr_text: str = "",
    ) -> List[dict]:
        """Enhance ingredients via pharmacy API, OpenFDA, local lookup; build URLs.

        Args:
            medicines_raw:    List of medicine dicts from OCR/LLM extraction.
            doctor_specialty: Specialty string used by the LLM correction prompt.
            correction_ctrl:  Optional MedicineCorrectionController; when present,
                              LLM correction replaces the fuzzy-matcher fallback.
            ocr_text:         Full OCR text context.
        """

        async def enrich(med: dict) -> dict:
            original_name = med["name"]
            name = original_name
            active = med.get("active_ingredient", "Unknown")

            # --- Name Correction is now handled in batch before enrichment ---
            pass

            active = med.get("active_ingredient", "Unknown")
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
            price = scraped.get("price", "Unknown")
            pharmacy_active = scraped.get("active", "")

            if pharmacy_active and active.lower() == "unknown":
                active = pharmacy_active
                logger.info("Pharmacy API enhanced '%s': %s", name, active)

            # --- Search-based Name Correction ---
            # If the pharmacy API found a product and it's highly similar but more 'formal',
            # update the name to the formal version.
            pharmacy_hit_name = scraped.get("hit_name")
            if pharmacy_hit_name and pharmacy_hit_name.lower() != name.lower():
                # Only trust it if it's not a generic result (already validated in _scrape)
                name = pharmacy_hit_name
                logger.info("Pharmacy Search corrected name: '%s' → '%s'", original_name, name)

            # 2. OpenFDA Search (fallback for international medicines)
            if active.lower() == "unknown":
                openfda_result = await self._search_openfda(name)
                if openfda_result:
                    active = openfda_result
                    logger.info("OpenFDA enhanced '%s': %s", name, active)


            # 4. Candidate suggestions
            candidates_data = []
            seen_cands = set()
            llm_candidates = med.get("llm_candidates", []) or []
            for cand_name in llm_candidates:
                if isinstance(cand_name, str) and cand_name.strip() and cand_name.lower() != name.lower() and cand_name.lower() not in seen_cands:
                    seen_cands.add(cand_name.lower())
                    candidates_data.append({
                        "name": cand_name,
                        "product_url": "",
                        "image_url": self._build_google_image_url(cand_name),
                    })

            return {
                "name": name,
                "original_name": original_name,
                "active_ingredient": active,
                "dosage": dosage,
                "form": form,
                "image_url": image_url,
                "product_url": product_url,
                "price": price,
                "candidates": candidates_data,
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
        Search pharmacy API for medicine data if available, else fallback to a search URL.
        Iterates over a comma-separated list of PHARMACY_BASE_URL values to find the
        first pharmacy that stocks the given medicine.
        Returns active ingredient, product URL, image URL, and price.
        """
        from urllib.parse import urlparse
        from urllib.parse import quote_plus

        pharmacy_base_urls = [url.strip() for url in getattr(self.settings, "PHARMACY_BASE_URL", "").split(',') if url.strip()]
        if not pharmacy_base_urls:
            pharmacy_base_urls = ["https://dwaprices.com/"]

        fallback_image = self._build_google_image_url(medicine_name)

        # Build a meaningful search term: take up to 3 non-numeric, non-unit words.
        # A single 2-letter word like "DA" is too ambiguous — use at least 2 words when available.
        _unit_pattern = re.compile(
            r'^\d+(?:\.\d+)?(mg|gm|g|ml|mcg|iu|%|units?)$', re.IGNORECASE
        )
        words_for_search = [
            w for w in medicine_name.split()
            if len(w) >= 2 and not _unit_pattern.match(w)
        ]
        # Use at least 2 words if available, capped at 3
        search_term = " ".join(words_for_search[:3]) if words_for_search else medicine_name
        # Fallback for single-letter start words: use more of the name
        first_word = words_for_search[0] if words_for_search else medicine_name

        # Phrases indicating an empty search result on generic e-commerce platforms
        NO_RESULTS_PHRASES = getattr(
            self.settings, 
            "SCRAPING_NO_RESULTS_PHRASES"
        )

        async with httpx.AsyncClient(
            timeout=float(getattr(self.settings, "SCRAPING_TIMEOUT", 15)),
            follow_redirects=True,
        ) as client:
            headers = {
                "User-Agent": getattr(
                    self.settings,
                    "SCRAPING_USER_AGENT",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                ),
            }

            for pharmacy_base in pharmacy_base_urls:
                pharmacy_base = pharmacy_base.rstrip("/")
                parsed_url = urlparse(pharmacy_base)
                domain = parsed_url.netloc.lower()
                base_path = parsed_url.path.rstrip('/')

                # 1. Dwaprices Native JSON API
                if "dwaprices.com" in domain:
                    api_url = f"{pharmacy_base}/routing.php"
                    try:
                        resp = await client.post(
                            api_url,
                            data={"search": "1", "searchq": search_term, "order_by": "name ASC"},
                            headers=headers,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            results = data.get("data", [])
                            if results:
                                hit = results[0]
                                hit_name = hit.get("name", "")

                                # ── Relevance guard ──────────────────────────────────────
                                # Validate the returned product actually matches what we searched.
                                # Without this, searching "DA" returns "Dabigatran" and its
                                # ingredient gets attributed to unrelated products (e.g. roll-on).
                                query_words = set(w.lower() for w in search_term.split() if len(w) >= 3)
                                hit_words   = set(w.lower() for w in hit_name.split()   if len(w) >= 3)
                                overlap = len(query_words & hit_words)
                                fuzzy_score = fuzz.token_set_ratio(
                                    search_term.lower(), hit_name.lower()
                                ) if hit_name else 0

                                # Accept the hit only if there is at least one shared word
                                # OR the names are fuzzy-similar enough.
                                if overlap == 0 and fuzzy_score < 55:
                                    logger.debug(
                                        "Pharmacy API hit rejected (low relevance): "
                                        "query=%r hit=%r score=%d overlap=%d",
                                        search_term, hit_name, fuzzy_score, overlap,
                                    )
                                    # Don't break — fall through to generic URL construction
                                else:
                                    product_id  = hit.get("id", "")
                                    product_url = f"{pharmacy_base}/med.php?id={product_id}" if product_id else ""
                                    img         = hit.get("img", "")
                                    image_url   = f"{pharmacy_base}/{img}" if img else fallback_image
                                    active      = hit.get("active", "")
                                    price       = hit.get("price", "")

                                    logger.info(
                                        "Pharmacy API found '%s': product=%s (hit=%r, score=%d)",
                                        medicine_name, product_url, hit_name, fuzzy_score,
                                    )
                                    return {
                                        "product_url": product_url,
                                        "image_url": image_url,
                                        "active": active,
                                        "price": price,
                                        "hit_name": hit_name,
                                    }
                    except Exception as e:
                        logger.debug("Pharmacy API failed for '%s' on %s: %s", medicine_name, domain, e)

                    continue  # Move to next URL if dwaprices failed

                # 2. Smart fallback URL construction based on standard e-commerce platforms
                if "chefaa." in domain:
                    generic_search_url = f"{parsed_url.scheme}://{domain}{base_path}/products/search?q={quote_plus(first_word)}"
                elif "seif-online." in domain or "elezaby" in domain:
                    generic_search_url = f"{parsed_url.scheme}://{domain}{base_path}/?s={quote_plus(first_word)}&post_type=product"
                elif "nahdionline." in domain:
                    generic_search_url = f"{parsed_url.scheme}://{domain}{base_path}/catalogsearch/result/?q={quote_plus(first_word)}"
                else:
                    # General fallback (most modern sites use /search?q=)
                    generic_search_url = f"{parsed_url.scheme}://{domain}{base_path}/search?q={quote_plus(first_word)}"

                # 3. Ping the generic pharmacy URL to verify if the product physically exists in stock
                try:
                    resp = await client.get(generic_search_url, headers=headers)
                    if resp.status_code == 200:
                        html_lower = resp.text.lower()
                        # Heuristic Check for "No results" text AND ensure the medicine name is echoed back
                        if first_word.lower() in html_lower and not any(phrase in html_lower for phrase in NO_RESULTS_PHRASES):
                            # Product highly likely exists! Return this URL
                            logger.info(f"Verified '{medicine_name}' exists on {domain} via heuristic.")
                            return {
                                "product_url": generic_search_url,
                                "image_url": fallback_image,
                                "active": "",
                                "price": "",
                            }
                        else:
                            logger.debug(f"Product '{medicine_name}' not found on {domain} (matched negative heuristic or failed positive check)")
                    else:
                        logger.debug(f"Pharmacy {domain} returned HTTP {resp.status_code} for search")
                except Exception as e:
                    logger.debug(f"Pharmacy HTTP verification failed for '{medicine_name}' on {domain}: {e}")

        # 4. Global Fallback if NO pharmacies had the item indexed/found
        logger.info(f"Medicine '{medicine_name}' was not found on any provided pharmacies in .env list.")
        global_fallback_url = f"https://www.google.com/search?q={quote_plus(first_word)}+medicine"
        return {
            "product_url": global_fallback_url,
            "image_url": fallback_image,
            "active": "",
            "price": "",
        }

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

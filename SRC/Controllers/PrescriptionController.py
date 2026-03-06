"""
PrescriptionController — OCR prescription images, extract medicine names,
and search for active ingredients + images.

Supports multiple OCR backends configured via OCR_BACKEND in .env:
  - LLAMAPARSE: Cloud-based OCR (requires LLAMA_CLOUD_API_KEY)
  - GEMINI: Google Gemini Vision AI (requires GEMINI_API_KEY)
  - OPENAI: OpenAI Vision (requires OPENAI_API_KEY)
  - EASYOCR: Local OCR via EasyOCR (no API key required)

Local backends (EASYOCR) extract raw text, then
pass it to the LLM for medicine name extraction.
Vision backends (GEMINI, OPENAI) read the image directly.
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
        Full pipeline:
        1. OCR / vision-read the prescription image (based on OCR_BACKEND)
        2. Extract medicine names + active ingredients
        3. Build Google Image search URLs

        Args:
            file_path: Path to the prescription image
            genration_client: LLM provider for text generation (used by
                              LLAMAPARSE pipeline for medicine extraction)
            ocr_client: OCR provider created by LLMProviderFactory.create_ocr()
                        None if OCR_BACKEND is LLAMAPARSE
            on_progress: Optional async callback(step, detail, percent)
        """
        if on_progress is None:
            async def on_progress(step, detail, percent): pass

        ocr_backend = getattr(
            self.settings, "OCR_BACKEND", "LLAMAPARSE"
        ).upper()
        logger.info("Using OCR backend: %s", ocr_backend)

        if ocr_backend == "LLAMAPARSE":
            # LlamaParse text OCR → LLM extraction
            return await self._pipeline_llamaparse(
                file_path, genration_client, on_progress
            )
        elif ocr_backend == "EASYOCR":
            # Local EasyOCR text OCR → LLM extraction
            return await self._pipeline_easyocr(
                file_path, genration_client, on_progress
            )

        else:
            # Vision-based OCR via the provider's ocr_image method
            if ocr_client is None:
                raise ValueError(
                    f"OCR_BACKEND is set to '{ocr_backend}' but no OCR "
                    f"client was initialized. Check your API key in .env."
                )
            return await self._pipeline_vision(file_path, ocr_client, on_progress)

    # =================================================================
    # PIPELINE A: LlamaParse OCR → HuggingFace LLM extraction
    # =================================================================
    async def _pipeline_llamaparse(
        self, file_path: str, genration_client, on_progress=None
    ) -> dict:
        """LlamaParse text OCR → LLM medicine extraction pipeline."""
        if on_progress is None:
            async def on_progress(step, detail, percent): pass

        await on_progress("ocr", "Extracting text from image (LlamaParse)...", 15)
        ocr_text = await self._ocr_llamaparse(file_path)
        if not ocr_text.strip():
            return {"ocr_text": "", "medicines": []}

        await on_progress("extraction", "Identifying medicine names...", 40)
        medicines_raw = await self._llm_extract_medicines(
            ocr_text, genration_client
        )
        
        # Only use algorithmic fallback if LLM extraction completely fails
        if not medicines_raw:
            algo_medicines = self.medicine_matcher.extract_medicines_from_text(ocr_text)
            if not algo_medicines:
                return {"ocr_text": ocr_text, "medicines": []}
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            medicines = await self._enrich_medicines(algo_medicines)
        else:
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            medicines = await self._enrich_medicines(medicines_raw)
            
        return {"ocr_text": ocr_text, "medicines": medicines}

    # =================================================================
    # PIPELINE C: EasyOCR (Local) → LLM extraction
    # =================================================================
    async def _pipeline_easyocr(
        self, file_path: str, genration_client, on_progress=None
    ) -> dict:
        """EasyOCR text extraction → LLM medicine extraction pipeline."""
        if on_progress is None:
            async def on_progress(step, detail, percent): pass

        await on_progress("ocr", "Extracting text from image (EasyOCR)...", 15)
        ocr_text = await self._ocr_easyocr(file_path)
        if not ocr_text.strip():
            return {"ocr_text": "", "medicines": []}

        await on_progress("extraction", "Identifying medicine names...", 40)
        medicines_raw = await self._llm_extract_medicines(
            ocr_text, genration_client
        )
        
        # Only use algorithmic fallback if LLM extraction completely fails
        if not medicines_raw:
            algo_medicines = self.medicine_matcher.extract_medicines_from_text(ocr_text)
            if not algo_medicines:
                return {"ocr_text": ocr_text, "medicines": []}
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            medicines = await self._enrich_medicines(algo_medicines)
        else:
            await on_progress("enrichment", "Looking up active ingredients...", 65)
            medicines = await self._enrich_medicines(medicines_raw)
            
        return {"ocr_text": ocr_text, "medicines": medicines}



    def _preprocess_image_cv2(self, file_path: str) -> str:
        """Clean image using OpenCV (remove noise, fix rotation)."""
        import cv2
        import numpy as np
        
        img = cv2.imread(file_path, cv2.IMREAD_COLOR)
        if img is None:
            return file_path
            
        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Denoising
        denoised = cv2.fastNlMeansDenoising(gray, h=30)
        
        # Binarization (adaptive thresholding)
        thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # Find coordinates of non-zero pixels to deskew
        coords = np.column_stack(np.where(thresh == 0))
        angle = cv2.minAreaRect(coords)[-1]
        
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
            
        if abs(angle) > 20: 
            angle = 0
            
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        
        output_path = file_path + "_cleaned.png"
        cv2.imwrite(output_path, rotated)
        return output_path



    # =================================================================
    # PIPELINE B: Vision OCR (uses provider.ocr_image)
    # =================================================================
    async def _pipeline_vision(
        self, file_path: str, ocr_client, on_progress=None
    ) -> dict:
        """
        Send image to the OCR provider's ocr_image method.
        Works with any provider that implements LLMInterface.ocr_image.
        """
        from fastapi.concurrency import run_in_threadpool

        if on_progress is None:
            async def on_progress(step, detail, percent): pass

        await on_progress("ocr", "Sending image to vision AI...", 15)

        # Call the provider's ocr_image (synchronous) in a thread pool
        raw_response = await run_in_threadpool(
            ocr_client.ocr_image,
            image_path=file_path,
            prompt=vision_extraction_prompt.substitute(
                common_medicines_list=COMMON_MEDICINES_LIST.replace("$", "$$")
            ),
            max_output_tokens=4096,
            temperature=0.2,
        )

        if not raw_response:
            logger.warning("OCR provider returned no response")
            return {"ocr_text": "", "medicines": []}

        logger.info("Raw Vision OCR Response (len=%d): %s", len(raw_response), raw_response)

        await on_progress("extraction", "Parsing medicine data from response...", 45)

        # Parse the JSON response
        medicines_raw, ocr_text = self._parse_vision_response(raw_response)

        # Only use algorithmic fallback if LLM extraction completely fails
        if not medicines_raw:
            algo_medicines = self.medicine_matcher.extract_medicines_from_text(ocr_text)
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

            # Attempt to salvage complete medicine entries from truncated JSON
            medicines = []
            for m in re.finditer(
                r'\{\s*"name"\s*:\s*"(?P<name>[^"]+)"'
                r'(?:.*?"active_ingredient"\s*:\s*"(?P<ai>[^"]+)")?'
                r'(?:.*?"confidence_score"\s*:\s*[\d.]+)?'
                r'\s*\}',
                text,
                re.DOTALL,
            ):
                name = m.group("name").strip()
                ai = (m.group("ai") or "Unknown").strip()
                if name:
                    medicines.append({"name": name, "active_ingredient": ai})

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
    # LlamaParse OCR
    # =================================================================
    async def _ocr_llamaparse(self, file_path: str) -> str:
        """Use LlamaParse to OCR an image file and return extracted text."""
        from llama_parse import LlamaParse

        api_key = self.settings.LLAMA_CLOUD_API_KEY
        if not api_key or api_key == "llx-REPLACE_WITH_YOUR_KEY":
            raise ValueError(
                "LLAMA_CLOUD_API_KEY is not set in .env — "
                "get a free key from https://cloud.llamaindex.ai/"
            )

        parser = LlamaParse(
            api_key=api_key,
            result_type="text",
            premium_mode=True,
            skip_diagonal_text=False,
            do_not_unroll_columns=True,
            system_prompt=(
                "This is a handwritten medical prescription from a doctor. "
                "Your ONLY job is to extract ALL text from this image as "
                "accurately as possible, especially MEDICINE and DRUG NAMES.\n\n"
                "CRITICAL INSTRUCTIONS:\n"
                "1. Prescriptions have NUMBERED items (1, 2, 3, 4, etc). "
                "Find and extract the text for EVERY numbered item.\n"
                "2. Medicine names are in Latin/English letters even if the "
                "rest is Arabic.\n"
                "3. Common medicine names: Augmentin, Moxclav, Panadol, "
                "Cataflam, Voltaren, Brufen, Antinal, Flagyl, Nexium, "
                "Omeprazole, Phenadon, Phinex, Rhinex, Kongestal, Comtrex, "
                "Ciprocin, Xithrone, Glucophage, Amaryl, Concor, Ventolin, "
                "Symbicort, Prednisolone, Aspocid, Megamox, Hibiotic.\n"
                "4. Even if partially illegible, write your best guess. "
                "Do NOT skip anything.\n"
                "5. Include dosage and instructions — extract EVERYTHING."
            ),
        )

        documents = await parser.aload_data(file_path)
        if not documents:
            return ""

        full_text = "\n".join(doc.text for doc in documents)
        logger.info("LlamaParse OCR extracted %d characters", len(full_text))
        logger.info("OCR text:\n%s", full_text)
        return full_text

    # =================================================================
    # EasyOCR (Local)
    # =================================================================
    async def _ocr_easyocr(self, file_path: str) -> str:
        """Use local EasyOCR to extract text from an image."""
        try:
            import easyocr
            from fastapi.concurrency import run_in_threadpool
        except ImportError:
            raise ImportError(
                "easyocr is not installed. Please install it with: "
                "pip install easyocr"
            )

        logger.info("Starting EasyOCR processing...")
        
        def run_easyocr():
            # Initialize reader for English. Arabic model requires download.
            # GPU=True if available, else False.
            reader = easyocr.Reader(['en'], gpu=True)
            result = reader.readtext(file_path, detail=0, paragraph=True)
            return "\n".join(result)

        full_text = await run_in_threadpool(run_easyocr)
        
        logger.info("EasyOCR extracted %d characters", len(full_text))
        logger.info("OCR text:\n%s", full_text)
        return full_text



    # =================================================================
    # LLM-based medicine extraction (used by LlamaParse pipeline)
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
                        
                        result.append({
                            "name": m["name"].strip(),
                            "active_ingredient": str(active_ing).strip(),
                        })
                    elif isinstance(m, str) and m.strip():
                        result.append({
                            "name": m.strip(),
                            "active_ingredient": "Unknown",
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
        """Enhance ingredients via OpenFDA and build Google search URLs."""

        async def enrich(med: dict) -> dict:
            name = med["name"]
            active = med["active_ingredient"]

            # 1. Fuzzy Match Correction
            corrected_name = self.medicine_matcher.find_best_match(name)
            if corrected_name:
                logger.info(f"Fuzzy corrected '{name}' -> '{corrected_name}'")
                name = corrected_name

            # 2. OpenFDA Search
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

            image_url = self._build_google_image_url(name)

            return {
                "name": name,
                "active_ingredient": active,
                "image_url": image_url,
            }

        tasks = [enrich(m) for m in medicines_raw]
        results = await asyncio.gather(*tasks)
        return list(results)

    @staticmethod
    def _build_google_image_url(medicine_name: str) -> str:
        """Build a Google Image Search URL for the medicine."""
        query = f"{medicine_name} medicine"
        return (
            f"https://www.google.com/search?q={quote_plus(query)}&tbm=isch"
        )

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

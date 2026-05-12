from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import os
import re
import json
import logging
import tempfile
import numpy as np
import cv2
from PIL import Image, ImageEnhance
from .prescription_cropper import extract_prescription

logger = logging.getLogger(__name__)


class OCRInterface(ABC):
    """
    Abstract base class for all OCR providers.
    Mirrors the LLM provider pattern with factory + interface.
    """

    # Indicates whether the provider sends images directly to a vision model
    # (True) or extracts raw text only (False).
    is_vision_provider: bool = False

    @abstractmethod
    def ocr_image(self, image_path: str, prompt: str = None,
                  max_output_tokens: int = None,
                  temperature: float = None) -> Optional[str]:
        """
        Extract text from an image.

        For text-based providers (LlamaParse): returns raw OCR text.
        For vision providers (Gemini, OpenAI): returns the model response
        (typically structured JSON when given an extraction prompt).
        """
        pass

    def parse_response(self, raw_response: str) -> Tuple[List[dict], str, str]:
        """
        Parse the raw OCR output into (medicines_raw, ocr_text, doctor_specialty).

        Text-based providers  → ([], raw_text, 'Unknown')  — LLM extraction needed.
        Vision providers      → (medicines, ocr_text, specialty) parsed from JSON.
        """
        if not raw_response:
            return [], "", "Unknown"
        if not self.is_vision_provider:
            return [], raw_response, "Unknown"
        return self._parse_vision_json(raw_response)

    @staticmethod
    def _parse_vision_json(text: str) -> Tuple[List[dict], str, str]:
        """Parse the JSON response from a vision OCR provider.
        
        Returns (medicines, ocr_text, doctor_specialty).
        """
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        text = text.strip()

        try:
            data = json.loads(text)
            ocr_text = data.get("ocr_text", "")
            doctor_specialty = data.get("doctor_specialty", "Unknown") or "Unknown"
            medicines = []

            for m in data.get("medicines", []):
                if isinstance(m, dict) and m.get("name"):
                    llm_candidates = m.get("candidates", []) or []
                    llm_candidates = [c for c in llm_candidates if isinstance(c, str) and c.strip()]
                    medicines.append({
                        "name": m["name"].strip(),
                        "active_ingredient": m.get(
                            "active_ingredient", "Unknown"
                        ).strip(),
                        "dosage": m.get("dosage", "Unknown").strip() if m.get("dosage") else "Unknown",
                        "form": m.get("form", "Unknown").strip() if m.get("form") else "Unknown",
                        "llm_candidates": llm_candidates,
                    })

            logger.info(
                "Vision OCR extracted %d medicines (specialty: %s): %s",
                len(medicines),
                doctor_specialty,
                [(m["name"], m["active_ingredient"]) for m in medicines],
            )
            logger.info("Vision OCR text:\n%s", ocr_text)
            return medicines, ocr_text, doctor_specialty

        except json.JSONDecodeError as e:
            # --- Plain-text transcription mode (expected after prompt decoupling) ---
            # Vision prompt now returns raw text, not JSON. Treat the entire
            # response as ocr_text and let Step 4 (_llm_extract_medicines)
            # handle extraction and translation.
            logger.info("Vision OCR returned plain text (non-JSON). Passing to text extraction pipeline.")
            logger.info("Raw transcription: %s", text[:500])

            # Attempt to salvage ocr_text from truncated JSON (legacy fallback)
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
                        "llm_candidates": [],
                    })

            if ocr_text or medicines:
                logger.info(
                    "Salvaged from truncated response: ocr_text(len=%d), %d medicines",
                    len(ocr_text), len(medicines),
                )

            # If nothing was salvaged, the entire raw text IS the transcription
            if not ocr_text and not medicines:
                return [], text, "Unknown"

            return medicines, ocr_text, "Unknown"

    def preprocess_image(self, file_path: str, max_width: int = 600) -> str:
        """
        Preprocess image to reduce size, remove background noise, and prepare for OCR.

        Args:
            file_path: Path to the image file
            max_width: Maximum width in pixels (height auto-calculated to maintain ratio)

        Pipeline
        --------
        Step 0 – Border detection & perspective warp (prescription_cropper)
                 Detects the four corners of the prescription document,
                 deskews it, and produces a flat top-down crop.
                 Falls back to the raw file if detection fails.

        Step 1 – Convert to grayscale
        Step 2 – Resize to max_width (maintains aspect ratio)
        Step 3 – Increase brightness to wash out shadows
        Step 4 – Heavily increase contrast → near-binary appearance
        """
        try:
            # ── Step 0: border detection + perspective crop ──────────────────
            # extract_prescription returns a BGR numpy array; we convert it to
            # a PIL Image so the rest of the pipeline stays unchanged.
            # enhance=False here because our PIL steps below do the enhancement.
            try:
                dir_name, file_name = os.path.split(file_path)
                debug_path = os.path.join(dir_name, f"debug_contour_{file_name}")
                
                bgr_cropped = extract_prescription(
                    file_path, 
                    enhance=False, 
                    debug=True, 
                    debug_output_path=debug_path
                )
                # Convert BGR → RGB → PIL
                rgb_cropped = cv2.cvtColor(bgr_cropped, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(rgb_cropped)
                logger.info("Prescription border detected and cropped for: %s", file_path)
            except Exception as crop_err:
                logger.warning(
                    "Border detection skipped (falling back to raw image): %s", crop_err
                )
                image = Image.open(file_path)

            # ── Step 1: grayscale ────────────────────────────────────────────
            gray_image = image.convert('L')

            # ── Step 2: resize if too large ──────────────────────────────────
            if gray_image.width > max_width:
                ratio = max_width / gray_image.width
                new_height = int(gray_image.height * ratio)
                resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
                gray_image = gray_image.resize((max_width, new_height), resample_filter)

            # ── Step 3: brightness (wash out background/shadows) ─────────────
            brightness_enhancer = ImageEnhance.Brightness(gray_image)
            bright_image = brightness_enhancer.enhance(1.4)

            # ── Step 4: contrast (stark black text) ──────────────────────────
            contrast_enhancer = ImageEnhance.Contrast(bright_image)
            final_image = contrast_enhancer.enhance(3.5)

            dir_name, file_name = os.path.split(file_path)
            output_path = os.path.join(dir_name, f"preprocessed_{file_name}")

            final_image.save(output_path)
            logger.info("Image preprocessing complete: %s → %s", file_path, output_path)
            return output_path

        except Exception as e:
            logger.error("Image preprocessing failed: %s", e)
            return file_path

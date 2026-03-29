from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import os
import re
import json
import logging

import cv2
import numpy as np

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
                        "llm_candidates": [],
                    })

            if ocr_text or medicines:
                logger.info(
                    "Salvaged from truncated response: ocr_text(len=%d), %d medicines",
                    len(ocr_text), len(medicines),
                )
            return medicines, ocr_text, "Unknown"

    def preprocess_image(self, file_path: str) -> str:
        """
        Advanced image preprocessing pipeline for OCR.

        Steps:
            1. Read as grayscale
            2. CLAHE contrast enhancement
            3. Bilateral filter (edge-preserving denoise)
            4. Otsu's thresholding (with adaptive fallback)
            5. Morphological cleanup (remove noise specks)
            6. Deskew (angle-clamped to ±15°)

        Returns the path to the cleaned image, or the original on failure.
        """
        try:
            # 1. Read image directly as grayscale
            gray = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                logger.warning("Could not read image: %s", file_path)
                return file_path

            # 2. CLAHE contrast enhancement (adaptive histogram equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)

            # 3. Edge-preserving denoising (bilateral filter)
            denoised = cv2.bilateralFilter(enhanced, d=9, sigmaColor=75, sigmaSpace=75)

            # 4. Binarization — try Otsu's first, fall back to adaptive threshold
            otsu_val, binary = cv2.threshold(
                denoised, 0, 255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
            # If Otsu picks a poor threshold (too low contrast), use adaptive
            if otsu_val < 50 or otsu_val > 230:
                binary = cv2.adaptiveThreshold(
                    denoised, 255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY, 11, 2,
                )

            # 5. Morphological cleanup — remove small noise specks
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

            # 6. Deskew — find skew angle from non-zero pixel coordinates
            coords = np.column_stack(np.where(cleaned == 0))
            if len(coords) > 100:  # need enough points for reliable measurement
                angle = cv2.minAreaRect(coords)[-1]
                if angle < -45:
                    angle = -(90 + angle)
                else:
                    angle = -angle

                # Only correct small angles (likely scan skew, not rotation)
                if abs(angle) <= 15:
                    (h, w) = cleaned.shape[:2]
                    center = (w // 2, h // 2)
                    M = cv2.getRotationMatrix2D(center, angle, 1.0)
                    cleaned = cv2.warpAffine(
                        cleaned, M, (w, h),
                        flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_REPLICATE,
                    )

            dir_name, file_name = os.path.split(file_path)
            output_path = os.path.join(dir_name, f"preprocessed_{file_name}")
            cv2.imwrite(output_path, cleaned)
            logger.info("Advanced preprocessing complete: %s → %s", file_path, output_path)
            return output_path

        except Exception as e:
            logger.error("Image preprocessing failed: %s", e)
            return file_path

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
import re
import json
import logging

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

    def parse_response(self, raw_response: str) -> Tuple[List[dict], str]:
        """
        Parse the raw OCR output into (medicines_raw, ocr_text).

        Text-based providers  → ([], raw_text)  — LLM extraction needed.
        Vision providers      → (medicines, ocr_text) parsed from JSON.
        """
        if not raw_response:
            return [], ""
        if not self.is_vision_provider:
            return [], raw_response
        return self._parse_vision_json(raw_response)

    @staticmethod
    def _parse_vision_json(text: str) -> Tuple[List[dict], str]:
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

    def preprocess_image(self, file_path: str) -> str:
        """
        Preprocess image before OCR: denoise, binarize, deskew.
        Returns the path to the cleaned image (or original if processing fails).
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            logger.warning("opencv-python not installed — skipping image preprocessing")
            return file_path

        img = cv2.imread(file_path, cv2.IMREAD_COLOR)
        if img is None:
            return file_path

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Denoising
        denoised = cv2.fastNlMeansDenoising(gray, h=30)

        # Binarization (adaptive thresholding)
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2,
        )

        # Deskew: find angle from non-zero pixel coordinates
        coords = np.column_stack(np.where(thresh == 0))
        if len(coords) == 0:
            return file_path

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Only correct small angles (likely scan skew, not rotation)
        if abs(angle) > 20:
            angle = 0

        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        output_path = file_path + "_cleaned.png"
        cv2.imwrite(output_path, rotated)
        return output_path

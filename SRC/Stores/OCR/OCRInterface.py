from abc import ABC, abstractmethod
from typing import Optional
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

        For text-based providers (LlamaParse, EasyOCR): returns raw OCR text.
        For vision providers (Gemini, OpenAI): returns the model response
        (typically structured JSON when given an extraction prompt).
        """
        pass

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

from ..OCRInterface import OCRInterface
from typing import Optional
import logging

logger = logging.getLogger("uvicorn.error")


class EasyOCRProvider(OCRInterface):
    """OCR provider using local EasyOCR (no API key required)."""

    is_vision_provider = False

    def __init__(self):
        self._reader = None

    def _get_reader(self):
        """Lazy-initialize the EasyOCR reader (heavy import)."""
        if self._reader is None:
            try:
                import easyocr
            except ImportError:
                raise ImportError(
                    "easyocr is not installed. Please install it with: "
                    "pip install easyocr"
                )
            self._reader = easyocr.Reader(["en"], gpu=True)
        return self._reader

    def ocr_image(self, image_path: str, prompt: str = None,
                  max_output_tokens: int = None,
                  temperature: float = None) -> Optional[str]:
        """Use EasyOCR to extract text from an image."""
        reader = self._get_reader()
        result = reader.readtext(image_path, detail=0, paragraph=True)
        full_text = "\n".join(result)

        logger.info("EasyOCR extracted %d characters", len(full_text))
        logger.info("OCR text:\n%s", full_text)
        return full_text

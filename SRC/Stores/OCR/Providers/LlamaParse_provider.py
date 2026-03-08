from ..OCRInterface import OCRInterface
from typing import Optional
import logging

logger = logging.getLogger("uvicorn.error")


class LlamaParseProvider(OCRInterface):
    """OCR provider using LlamaParse cloud service."""

    is_vision_provider = False

    def __init__(self, api_key: str):
        self.api_key = api_key

    def ocr_image(self, image_path: str, prompt: str = None,
                  max_output_tokens: int = None,
                  temperature: float = None) -> Optional[str]:
        """Use LlamaParse to OCR an image and return extracted text."""
        from llama_parse import LlamaParse

        if not self.api_key or self.api_key == "llx-REPLACE_WITH_YOUR_KEY":
            raise ValueError(
                "LLAMA_CLOUD_API_KEY is not set in .env — "
                "get a free key from https://cloud.llamaindex.ai/"
            )

        parser = LlamaParse(
            api_key=self.api_key,
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

        # LlamaParse has sync load_data
        documents = parser.load_data(image_path)
        if not documents:
            return ""

        full_text = "\n".join(doc.text for doc in documents)
        logger.info("LlamaParse OCR extracted %d characters", len(full_text))
        logger.info("OCR text:\n%s", full_text)
        return full_text

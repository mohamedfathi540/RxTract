from ..OCRInterface import OCRInterface
from typing import Optional
import logging

logger = logging.getLogger("uvicorn.error")


class OpenAIOCRProvider(OCRInterface):
    """OCR provider using OpenAI Vision (GPT-4o, GPT-4-turbo)."""

    is_vision_provider = True

    def __init__(self, api_key: str, base_url: str = None,
                 model_id: str = "gpt-4o"):
        self.api_key = api_key
        self.base_url = base_url
        self.model_id = model_id
        self.client = None

        if self.api_key:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url if self.base_url and len(self.base_url) else None,
            )

    def ocr_image(self, image_path: str, prompt: str = None,
                  max_output_tokens: int = 8192,
                  temperature: float = 0.2) -> Optional[str]:
        """
        Encode the image as base64, send to OpenAI Vision, and return
        the model's text response.
        """
        import base64
        import os

        if not self.client:
            logger.error("OpenAI client is not initialized")
            return None

        if not self.model_id:
            logger.error("OpenAI OCR model is not set")
            return None

        max_output_tokens = max_output_tokens or 8192
        temperature = temperature or 0.2

        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_data}"
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt or "Extract all text from this image.",
                    },
                ],
            }
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                max_tokens=max_output_tokens,
                temperature=temperature,
            )

            if (
                not response
                or not response.choices
                or not response.choices[0].message
            ):
                logger.error("OpenAI OCR returned empty response")
                return None

            return response.choices[0].message.content

        except Exception as e:
            logger.error("OpenAI OCR error: %s", e)
            return None

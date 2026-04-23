from ..OCRInterface import OCRInterface
from typing import Optional
import logging
import time

logger = logging.getLogger("uvicorn.error")


class GeminiOCRProvider(OCRInterface):
    """OCR provider using Google Gemini Vision AI."""

    is_vision_provider = True

    def __init__(self, api_key: str, model_id: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model_id = model_id
        self.client = None

        if self.api_key:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)

    def ocr_image(self, image_path: str, prompt: str = None,
                  max_output_tokens: int = 8192,
                  temperature: float = 0.2) -> Optional[str]:
        """
        Send image to Gemini Vision and return the model's text response.
        Includes retry logic for rate limits and token truncation.
        """
        import os
        from google.genai import types

        if not self.client:
            logger.error("Gemini client is not initialized")
            return None

        if not self.model_id:
            logger.error("Gemini OCR model is not set")
            return None

        max_output_tokens = max_output_tokens or 8192
        temperature = temperature or 0.2

        # Read image bytes
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        # Detect MIME type
        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

        generation_config = types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )

        retries = 3
        for attempt in range(retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_bytes(
                                    data=image_bytes,
                                    mime_type=mime_type,
                                ),
                                types.Part(text=prompt or "Extract all text from this image."),
                            ],
                        )
                    ],
                    config=generation_config,
                )

                if not response or not response.text:
                    if attempt < retries:
                        logger.warning("Gemini OCR empty response, retrying...")
                        continue
                    return None

                # Check if response was truncated
                finish_reason = None
                if response.candidates and response.candidates[0].finish_reason:
                    finish_reason = response.candidates[0].finish_reason
                if finish_reason and str(finish_reason) in (
                    "MAX_TOKENS", "FINISH_REASON_MAX_TOKENS", "2"
                ):
                    logger.warning(
                        "Gemini OCR response truncated (finish_reason=%s, len=%d). "
                        "Retrying with higher token limit...",
                        finish_reason, len(response.text),
                    )
                    if attempt < retries:
                        generation_config = types.GenerateContentConfig(
                            max_output_tokens=max_output_tokens * 2,
                            temperature=temperature,
                        )
                        continue
                    logger.warning("Returning truncated OCR response after %d retries", retries)

                return response.text

            except Exception as e:
                import re as _re
                is_rate_limit = (
                    "429" in str(e)
                    or "RESOURCE_EXHAUSTED" in str(e)
                    or "503" in str(e)
                    or "UNAVAILABLE" in str(e)
                )

                if is_rate_limit and attempt < retries:
                    # If we hit a rate limit or resource exhaustion, try disabling the search tool
                    # for the next attempt to save quota and ensure completion.
                    if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                        logger.warning("Gemini OCR quota hit. Disabling Google Search tool for fallback.")
                        generation_config = types.GenerateContentConfig(
                            max_output_tokens=max_output_tokens,
                            temperature=temperature,
                        )
                    
                    wait_time = 4 * (2 ** attempt)
                    retry_match = _re.search(
                        r"retry in (\d+(?:\.\d+)?)s", str(e), _re.IGNORECASE
                    )
                    if retry_match:
                        try:
                            wait_time = min(float(retry_match.group(1)) + 1, 60)
                        except ValueError:
                            pass
                    logger.warning("Gemini OCR rate limit. Retrying in %.1fs...", wait_time)
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error("Gemini OCR error: %s", e)

                return None

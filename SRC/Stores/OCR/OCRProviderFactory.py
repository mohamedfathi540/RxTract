from .OCREnums import OCREnums
from .Providers import LlamaParseProvider, GeminiOCRProvider, OpenAIOCRProvider


class OCRProviderFactory:
    def __init__(self, config):
        self.config = config

    def create(self, provider: str):
        provider = provider.upper()

        if provider == OCREnums.LLAMAPARSE.value:
            return LlamaParseProvider(
                api_key=getattr(self.config, "LLAMA_CLOUD_API_KEY", None),
            )


        if provider == OCREnums.GEMINI.value:
            return GeminiOCRProvider(
                api_key=getattr(self.config, "GEMINI_API_KEY", None),
                model_id=getattr(self.config, "OCR_MODEL_ID", "gemini-2.0-flash"),
            )

        if provider == OCREnums.OPENAI.value:
            return OpenAIOCRProvider(
                api_key=getattr(self.config, "OPENAI_API_KEY", None),
                base_url=getattr(self.config, "OPENAI_BASE_URL", None),
                model_id=getattr(self.config, "OCR_MODEL_ID", "gpt-4o"),
            )

        return None

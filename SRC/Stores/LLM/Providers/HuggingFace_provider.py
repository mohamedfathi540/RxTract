from ..LLMInterface import LLMInterface
from ..LLMEnums import LLMEnums, HuggingFaceEnum
from huggingface_hub import InferenceClient
import logging
from typing import List, Union

class HuggingFaceProvider(LLMInterface):
    def __init__(self, api_key: str, base_url: str = None,
                 default_input_max_characters: int = 1000,
                 default_genrated_max_output_tokens: int = 1000,
                 default_genration_temperature: float = 0.1):

        self.api_key = api_key
        self.base_url = base_url
        self.default_input_max_characters = default_input_max_characters
        self.default_genrated_max_output_tokens = default_genrated_max_output_tokens
        self.default_genration_temperature = default_genration_temperature

        self.genration_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.client = InferenceClient(token=self.api_key)

        self.enums = HuggingFaceEnum
        self.logger = logging.getLogger(__name__)

    def set_genration_model(self, model_id: str):
        self.genration_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str):
        return text[:self.default_input_max_characters].strip()

    def genrate_text(self, prompt: str, max_output_tokens: int = None, temperature: float = None, chat_history: list = []):
        if not self.client:
            self.logger.error("HuggingFace client is not initialized")
            return None

        if not self.genration_model_id:
            self.logger.error("HuggingFace generation model is not initialized")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_genrated_max_output_tokens
        temperature = temperature if temperature else self.default_genration_temperature

        # Hugging Face Inference API usually takes a simple prompt string for text-generation
        # However, new models support chat templates. We will try to map chat_history to a string or use chat_completion if supported.
        # For simplicity and standard compliance with other providers in this codebase, let's construct a prompt.
        # But the InferenceClient has a chat_completion method now.
        
        # Prepare messages
        messages = chat_history + [{"role": "user", "content": prompt}]

        try:
            response = self.client.chat_completion(
                messages=messages,
                model=self.genration_model_id,
                max_tokens=max_output_tokens,
                temperature=temperature
            )
            
            if not response or not response.choices or len(response.choices) == 0:
                self.logger.error("Error while generating text using HuggingFace")
                return None
                
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Error during HuggingFace generation: {e}")
            return None

    def embed_text(self, text: Union[str, List[str]], document_type: str = None):
        if not self.client:
            self.logger.error("HuggingFace client is not initialized")
            return None

        if isinstance(text, str):
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("HuggingFace embedding model is not initialized")
            return None

        try:
            # feature-extraction task
            response = self.client.feature_extraction(
                text=text,
                model=self.embedding_model_id
            )
            
            # Response is typically a list of lists (embeddings) or a Tensor
            # We need to return a list of embeddings.
            
            # Use tolist() if it's a numpy array, but the client returns lists usually
            if hasattr(response, 'tolist'):
                 return response.tolist()
            return response

        except Exception as e:
            self.logger.error(f"Error while embedding text using HuggingFace: {e}")
            return None

    def construct_prompt(self, prompt: str, role: str):
        return {"role": role, "content": prompt}

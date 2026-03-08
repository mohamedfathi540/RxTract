from ..LLMInterface import LLMInterface
from ..LLMEnums import LLMEnums, CohereEnum , DocumentTypeEnum
import cohere
import logging
from typing import List,Union


class CohereProvider(LLMInterface):
    def __init__(self, api_key: str,
                 default_input_max_characters: int = 1000,
                 default_genrated_max_output_tokens: int = 1000,
                 default_genration_temperature: float = 0.1):

        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_genrated_max_output_tokens = default_genrated_max_output_tokens
        self.default_genration_temperature = default_genration_temperature

        self.genration_model_id = None
        self.client = cohere.Client(api_key=self.api_key) 
    

        self.embedding_model_id = None
        self.embedding_size = None

        self.enums = CohereEnum
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
            self.logger.error("Cohere client is not initialized")
            return None

        if not self.genration_model_id:
            self.logger.error("Cohere genration model is not initialized")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_genrated_max_output_tokens
        temperature = temperature if temperature else self.default_genration_temperature

        try:
            response = self.client.chat(
                model=self.genration_model_id,
                message=self.process_text(current_prompt_text),
                chat_history=chat_history,
                temperature=temperature,
                max_tokens=max_output_tokens
            )
            
            if not response or not response.text:
                self.logger.error("Error while generating text using Cohere")
                return None
                
            return response.text
            
        except Exception as e:
            self.logger.error(f"Exception during Cohere generation: {e}")
            return None

    def embed_text(self, text: Union[str,List[str]], document_type: str = None):
        if not self.client:
            self.logger.error("Cohere client is not initialized")
            return None

        if isinstance(text, str) :
            text = [text]
        if not self.embedding_model_id:
            self.logger.error("Cohere embedding model is not initialized")
            return None

        try:
            input_type = CohereEnum.DOCUMENT
            if document_type == DocumentTypeEnum.QUERY:
                input_type = CohereEnum.QUERY


            # Cohere embed takes a list of texts
            response = self.client.embed(
                texts=[
                    self.process_text(t)
                    for t in text
                    ],
                model=self.embedding_model_id,
                input_type=input_type ,
                embedding_types = ['float']
                # input_type is often required for v3 models, defaulting safe
            )

            if not response or not response.embeddings or not response.embeddings.float:
                self.logger.error("Error while embedding text using Cohere")
                return None

            return [
                f for f in response.embeddings.float
                    ]
            
            
        except Exception as e:
            self.logger.error(f"Exception during Cohere embedding: {e}")
            return None

    def construct_prompt(self, prompt: str, role: str):
        # Cohere expects 'role' and 'message' (or 'text' in some contexts, but 'message' is standard for chat history objects)
        return {"role": role, "text": prompt}

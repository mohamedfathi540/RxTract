from ..LLMInterface import LLMInterface
from ..LLMEnums import LLMEnums, GeminiEnum
from google import genai
from google.genai import types
import logging
import os
import time
from typing import List, Union


class GeminiProvider(LLMInterface):
    def __init__(self, api_key: str,
                 default_input_max_characters: int = 1000,
                 default_genrated_max_output_tokens: int = 8192,
                 default_genration_temperature: float = 0.2):

        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_genrated_max_output_tokens = default_genrated_max_output_tokens
        self.default_genration_temperature = default_genration_temperature

        self.genration_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None
            
        self.enums = GeminiEnum
        self.logger = logging.getLogger('uvicorn')

    def set_genration_model(self, model_id: str):
        self.genration_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def process_text(self, text: str):
        # Removed truncation as requested
        return text.strip()

    def genrate_text(self, prompt: str, max_output_tokens: int = None, temperature: float = None, chat_history: list = []):
        if not self.client:
            self.logger.error("Gemini client is not initialized")
            return None

        if not self.genration_model_id:
            self.logger.error("Gemini generation model is not initialized")
            return None

        max_output_tokens = max_output_tokens if max_output_tokens else self.default_genrated_max_output_tokens
        temperature = temperature if temperature else self.default_genration_temperature

        # Convert chat history to Gemini format and extract system instruction
        gemini_history = []
        system_instruction = None

        for message in chat_history:
            role = message.get("role")
            content = message.get("content")
            
            if role == GeminiEnum.SYSTEM.value:
                system_instruction = content
            elif role == GeminiEnum.USER.value:
                gemini_history.append(types.Content(role="user", parts=[types.Part(text=content)]))
            elif role == GeminiEnum.ASSISTANT.value:
                gemini_history.append(types.Content(role="model", parts=[types.Part(text=content)]))

        # Append the current prompt
        gemini_history.append(types.Content(role="user", parts=[types.Part(text=self.process_text(prompt))]))

        generation_config = types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            system_instruction=system_instruction
        )
        
        retries = 3
        for attempt in range(retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.genration_model_id,
                    contents=gemini_history,
                    config=generation_config
                )
                
                if not response or not response.text:
                    if attempt < retries:
                        self.logger.error("Error while generating text using Gemini: Empty response")
                        return None
                    return None
                    
                return response.text
                
            except Exception as e:
                import re
                is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "503" in str(e) or "UNAVAILABLE" in str(e)
                
                if is_rate_limit:
                    if attempt < retries:
                        # Try to extract wait time from error message
                        wait_time = 4 * (2 ** attempt) # Default backoff
                        
                        # Look for "Please retry in X" pattern
                        retry_match = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e), re.IGNORECASE)
                        if retry_match:
                            try:
                                parsed_wait = float(retry_match.group(1))
                                # Add a small buffer and cap it at 60s to avoid hanging too long
                                wait_time = min(parsed_wait + 1, 60)
                            except ValueError:
                                pass
                        
                        self.logger.warning(f"Gemini rate limit hit. Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        self.logger.error(f"Gemini rate limit exhausted after {retries} retries: {e}")
                else:
                    self.logger.error(f"Error calling Gemini API: {e}")
                
                return None

    def embed_text(self, text: Union[str,List[str]], document_type: str = None):
        if not self.client:
            self.logger.error("Gemini client is not initialized")
            return None

        if isinstance(text, str) :
            text = [text]

        if not self.embedding_model_id:
            self.logger.error("Gemini embedding model is not initialized")
            return None

        retries = 3
        for attempt in range(retries + 1):
            try:
                # Gemini embedding task type
                task_type = "RETRIEVAL_DOCUMENT" if document_type == "document" else "RETRIEVAL_QUERY"
                
                result = self.client.models.embed_content(
                    model=self.embedding_model_id,
                    contents=text,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        title="Embedding" if task_type == "RETRIEVAL_DOCUMENT" else None 
                    )
                )
                
                if not result or not result.embeddings:
                    self.logger.error("Error while embedding text using Gemini")
                    return None
                return [res.values for res in result.embeddings ]
                
                
            except Exception as e:
                import re
                is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "503" in str(e) or "UNAVAILABLE" in str(e)
                
                if is_rate_limit:
                    if attempt < retries:
                        # Try to extract wait time from error message
                        wait_time = 4 * (2 ** attempt) # Default backoff
                        
                        # Look for "Please retry in X" pattern
                        retry_match = re.search(r"retry in (\d+(?:\.\d+)?)s", str(e), re.IGNORECASE)
                        if retry_match:
                            try:
                                parsed_wait = float(retry_match.group(1))
                                # Add a small buffer and cap it at 60s
                                wait_time = min(parsed_wait + 1, 60)
                            except ValueError:
                                pass
                                
                        self.logger.warning(f"Gemini rate limit hit (Embedding). Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        self.logger.error(f"Gemini embedding rate limit exhausted after {retries} retries: {e}")
                else:
                    self.logger.error(f"Error calling Gemini Embedding API: {e}")
                
                return None

    def construct_prompt(self, prompt: str, role: str):
        # This is used by the controller to append to history. 
        return {"role": role, "content": prompt}

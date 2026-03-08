from abc import ABC, abstractmethod


class LLMInterface(ABC):
    
    @abstractmethod
    def set_genration_model(self,model_id : str) :
        pass

    @abstractmethod
    def set_embedding_model(self,model_id : str, embedding_size : int) :
        pass

    @abstractmethod
    def genrate_text(self ,prompt : str , max_output_tokens : int =None ,temperature : float =None , chat_history : list =[]) :
        pass

    @abstractmethod
    def embed_text(self, text : str, document_type :str =None) :
        pass

    @abstractmethod
    def construct_prompt(self, prompt : str ,role : str) :
        pass

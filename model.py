from abc import ABC, abstractmethod

from dotenv import load_dotenv
import os

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
groq_model_name = "llama-3.3-70b-versatile"

gemini_api_key = os.getenv("GEMINI_API_KEY")
gemini_model_name = "gemini-2.5-flash"


class LLMBase(ABC):
    @abstractmethod
    def generate(self, prompt: str):
        pass


class GroqLLM(LLMBase):
    def __init__(self):
        from groq import Groq
        self.client = Groq(api_key=groq_api_key)
        self.model_name = groq_model_name

    def generate(self, prompt: str) -> str:
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model=self.model_name,
        )
        return chat_completion.choices[0].message.content

class GeminiLLM(LLMBase):
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        self.client = genai.GenerativeModel(gemini_model_name)

    def generate(self, prompt: str) -> str:
        response = self.client.generate_content(prompt)
        return response.text

class LLMFactory:

    _providers = {
        "groq": GroqLLM,
        "gemini": GeminiLLM
    }


    @staticmethod
    def get_llm(provider : str) -> LLMBase:
        if provider not in LLMFactory._providers:
            raise ValueError(f"Unknown provider: {provider}")
        return LLMFactory._providers[provider]()
        
def call_llm(prompt: str) -> str:
    try:
        llm = LLMFactory.get_llm("groq")
        return llm.generate(prompt)
    except Exception as groq_err:
        print(f"Warning: Groq failed ({groq_err}). Falling back to Gemini...")
        try:
            llm = LLMFactory.get_llm("gemini")
            return llm.generate(prompt)
        except Exception as gemini_err:
            print(f"Error: Gemini also failed ({gemini_err}). All LLM providers failed.")
            raise Exception("All LLM providers failed.") from gemini_err
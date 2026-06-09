import abc
from typing import Any, Dict, List, Optional
import openai
from pydantic import BaseModel, Field

class ChatMessage(BaseModel):
    role: str # "system", "user", "assistant"
    content: str

class ChatResponse(BaseModel):
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""

class BaseLLMClient(abc.ABC):
    """Abstract interface for multi-provider LLM calls."""
    
    @abc.abstractmethod
    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        pass

    @abc.abstractmethod
    def create_embeddings(self, texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
        pass

class OpenAILLMClient(BaseLLMClient):
    """OpenAI-compatible LLM client wrapping the official openai python package."""
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def chat_completion(
        self,
        messages: List[ChatMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        # Context Window Truncation: Keep System message + last 10 messages to save tokens
        system_msgs = [m for m in messages if m.role == "system"]
        recent_msgs = [m for m in messages if m.role != "system"][-10:]
        optimized_messages = system_msgs + recent_msgs
        
        oai_messages = [{"role": m.role, "content": m.content} for m in optimized_messages]
        
        create_kwargs = {
            "model": model,
            "messages": oai_messages,
            "temperature": temperature,
            **kwargs
        }
        if max_tokens is not None:
            create_kwargs["max_tokens"] = max_tokens
            
        response = self.client.chat.completions.create(**create_kwargs)
        
        choice = response.choices[0].message
        usage = response.usage
        
        return ChatResponse(
            content=choice.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            model=response.model
        )

    def create_embeddings(self, texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
        response = self.client.embeddings.create(input=texts, model=model)
        return [data.embedding for data in response.data]


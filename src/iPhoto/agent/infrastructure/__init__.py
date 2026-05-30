"""Agent infrastructure implementations."""

from .clip_embedding import CLIPEmbeddingService
from .ollama_llm import OllamaLLMService

__all__ = ["CLIPEmbeddingService", "OllamaLLMService"]

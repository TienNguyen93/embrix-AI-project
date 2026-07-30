"""
embrix.llm.base
───────────────
Abstract Base Class for decoupled LLM Providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class LLMResponse:
    """Standardized LLM execution response wrapper."""
    content: str
    model_name: str
    provider_name: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    execution_time_sec: float
    metadata: Dict[str, Any]


class BaseLLMProvider(ABC):
    """Abstract interface for all LLM providers (Gemini Pool, Ollama, llama.cpp)."""

    @abstractmethod
    def generate_sql(self, prompt: str, schema_context: str) -> LLMResponse:
        """Generate SQL query given user prompt and schema context."""
        pass

"""
embrix.llm.factory
──────────────────
LLM Provider Factory with Automatic Failover Circuit (Gemini Pool -> Ollama Local).
"""

import os
import logging
from typing import Optional

from embrix.llm.base import BaseLLMProvider, LLMResponse
from embrix.llm.gemini_pool import GeminiPoolProvider
from embrix.llm.ollama_provider import OllamaProvider

logger = logging.getLogger("embrix.llm.factory")


class ResilientLLMProvider(BaseLLMProvider):
    """
    Unified Resilient Provider that attempts Gemini Pool first,
    and automatically falls back to local Ollama if all cloud Gemini models are rate limited/offline.
    """

    def __init__(self):
        self.gemini_provider = GeminiPoolProvider()
        self.ollama_provider = OllamaProvider()

    def generate_sql(self, prompt: str, schema_context: str, preferred_model: Optional[str] = None) -> LLMResponse:
        """Dispatch query based on preferred_model, falling back through Gemini Pool -> Ollama -> Offline Heuristic."""
        # 1. Check if user explicitly selected local Ollama / Qwen model
        is_ollama_requested = preferred_model and any(kw in preferred_model.lower() for kw in ["ollama", "qwen", "local"])
        if is_ollama_requested:
            try:
                logger.info(f"User explicitly selected local model ({preferred_model}). Dispatching directly to OllamaProvider...")
                return self.ollama_provider.generate_sql(prompt, schema_context)
            except Exception as e:
                logger.warning(f"Requested Ollama Provider failed ({e}). Falling back to Gemini Pool...")

        # 2. Attempt Gemini Pool if API key is configured
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            try:
                return self.gemini_provider.generate_sql(prompt, schema_context, preferred_model=preferred_model)
            except Exception as e:
                logger.warning(f"Gemini Pool Provider failed/exhausted ({e}). Falling back to local Ollama...")



        # Attempt local Ollama
        try:
            return self.ollama_provider.generate_sql(prompt, schema_context)
        except Exception as e:
            logger.warning(f"Local Ollama Provider failed ({e}). Using Offline Heuristic Generator...")
            
            # Extract first table from schema context
            import re
            tables = re.findall(r'Table:\s*([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)', schema_context)
            target_tbl = tables[0] if tables else "core_usage.service_usage_readings"
            
            sql = f"SELECT * FROM {target_tbl} LIMIT 100;"
            return LLMResponse(
                content=sql,
                model_name="Offline-Heuristic",
                provider_name="ResilientLLMProvider (Offline Fallback)",
                input_tokens=100,
                output_tokens=20,
                estimated_cost_usd=0.0,
                execution_time_sec=0.01,
                metadata={"offline_fallback": True}
            )


def get_llm_provider(preference: str = "auto") -> BaseLLMProvider:
    """Factory helper to return appropriate LLM provider instance."""
    if preference == "ollama" or preference == "local":
        return OllamaProvider()
    elif preference == "gemini":
        return GeminiPoolProvider()
    else:
        return ResilientLLMProvider()

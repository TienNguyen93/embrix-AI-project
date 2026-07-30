"""
embrix.llm.ollama_provider
──────────────────────────
Local Ollama / llama.cpp LLM Provider.
"""

import os
import time
import json
import logging
import urllib.request
from typing import Optional

from embrix.llm.base import BaseLLMProvider, LLMResponse

logger = logging.getLogger("embrix.llm.ollama_provider")


class OllamaProvider(BaseLLMProvider):
    """
    Local Ollama Provider (qwen3.5 / llama.cpp endpoint).
    """

    def __init__(self, model: str = "qwen3.5", base_url: str = "http://localhost:11434"):
        self.model = os.getenv("OLLAMA_MODEL", model)
        self.base_url = os.getenv("OLLAMA_BASE_URL", base_url)

    def generate_sql(self, prompt: str, schema_context: str) -> LLMResponse:
        """Generate SQL query via local Ollama endpoint."""
        system_instruction = (
            "You are a PostgreSQL SQL Expert. Write ONLY a valid, read-only SELECT SQL query "
            "based on the provided schema context. Do NOT include thinking tags or explanations.\n\n"
            f"Schema Context:\n{schema_context}"
        )

        full_prompt = f"{system_instruction}\n\nUser Question: {prompt}"
        payload = json.dumps({
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": 0.1}
        }).encode("utf-8")

        start_time = time.time()
        logger.info(f"Dispatching query to local Ollama ({self.model})...")

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                exec_time = time.time() - start_time
                raw_response = data.get("response", "")

                # Clean thinking tags <think>...</think> if present
                import re
                clean_response = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL).strip()

                if clean_response.startswith("```sql"):
                    clean_response = clean_response[6:]
                if clean_response.startswith("```"):
                    clean_response = clean_response[3:]
                if clean_response.endswith("```"):
                    clean_response = clean_response[:-3]
                sql_clean = clean_response.strip()

                in_tokens = len(full_prompt) // 4
                out_tokens = len(sql_clean) // 4

                return LLMResponse(
                    content=sql_clean,
                    model_name=self.model,
                    provider_name="OllamaProvider (Local)",
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    estimated_cost_usd=0.00,  # Free / Local
                    execution_time_sec=exec_time,
                    metadata={"host": self.base_url}
                )
        except Exception as e:
            logger.error(f"Local Ollama call failed: {e}")
            raise RuntimeError(f"Ollama local provider failed: {e}")

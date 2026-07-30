"""
embrix.llm.gemini_pool
──────────────────────
Multi-Model Gemini Rate-Limiter Pool Provider.

Free Gemini Tier Quota Configuration:
1. gemini-3.1-flash-lite (Primary): RPM=15, TPM=250k, RPD=500
2. gemini-3-flash (Secondary): RPM=5, TPM=250k, RPD=20
3. gemini-2.5-flash-lite (Tertiary): RPM=10, TPM=250k, RPD=20

Enforces RPM, TPM, and RPD sliding-window rate limits and automatically fails over on HTTP 429.
"""

import os
import time
import json
import logging
import urllib.request
from typing import List, Dict, Any, Optional

from embrix.llm.base import BaseLLMProvider, LLMResponse
from embrix.llm.rate_limiter import SlidingWindowRateLimiter

logger = logging.getLogger("embrix.llm.gemini_pool")

# Free Tier Model Quotas (RPM, TPM, RPD)
FREE_GEMINI_MODEL_CONFIGS = {
    "gemini-3.1-flash-lite": {"rpm": 15, "tpm": 250000, "rpd": 500},
    "gemini-3-flash": {"rpm": 5, "tpm": 250000, "rpd": 20},
    "gemini-2.5-flash-lite": {"rpm": 10, "tpm": 250000, "rpd": 20},
}

# Rates per 1M tokens for estimated cost (Free tier = $0.00 / Cloud standard rates for tracking)
GEMINI_RATES = {
    "gemini-3.1-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-3-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
}


class GeminiPoolProvider(BaseLLMProvider):
    """
    Multi-model Gemini API Pool with Sliding-Window Rate Limiting (RPM, TPM, RPD) & Failover Circuit.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_pool: Optional[List[str]] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_pool = model_pool or [
            "gemini-3.1-flash-lite",
            "gemini-3-flash",
            "gemini-2.5-flash-lite"
        ]

        self.rate_limiter = SlidingWindowRateLimiter(model_configs=FREE_GEMINI_MODEL_CONFIGS)

    def _call_gemini_api(self, model: str, prompt: str, system_instruction: str) -> str:
        """Execute HTTP request to Google Gemini REST API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_instruction}\n\nUser Question:\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024
            }
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            raise ValueError(f"Invalid API response from {model}")

    def generate_sql(self, prompt: str, schema_context: str, preferred_model: Optional[str] = None) -> LLMResponse:
        """Round-robin failover loop over Gemini model pool enforcing RPM, TPM, and RPD limits."""
        system_instruction = (
            "You are a PostgreSQL SQL Expert. Write ONLY a valid, read-only SELECT SQL query "
            "based on the provided schema context. Do NOT explain or include markdown text outside the query.\n\n"
            f"Schema Context:\n{schema_context}"
        )

        start_time = time.time()
        estimated_input_tokens = len(system_instruction + prompt) // 4
        last_error = None

        # Build dynamic execution pool prioritizing user's selected model first
        active_pool = list(self.model_pool)
        if preferred_model and preferred_model in active_pool:
            active_pool.remove(preferred_model)
            active_pool.insert(0, preferred_model)

        for model in active_pool:

            if not self.rate_limiter.is_allowed(model, estimated_tokens=estimated_input_tokens):
                logger.warning(f"Rate limit (RPM/TPM/RPD) reached for {model}. Trying next pool model...")
                continue

            try:
                logger.info(f"Dispatching query to Gemini Pool Model: {model}...")
                raw_response = self._call_gemini_api(model, prompt, system_instruction)
                exec_time = time.time() - start_time

                # Clean markdown backticks
                sql_clean = raw_response.strip()
                if sql_clean.startswith("```sql"):
                    sql_clean = sql_clean[6:]
                if sql_clean.startswith("```"):
                    sql_clean = sql_clean[3:]
                if sql_clean.endswith("```"):
                    sql_clean = sql_clean[:-3]
                sql_clean = sql_clean.strip()

                in_tokens = estimated_input_tokens
                out_tokens = len(sql_clean) // 4
                rates = GEMINI_RATES.get(model, {"input": 0.075, "output": 0.30})
                cost_usd = ((in_tokens / 1_000_000) * rates["input"]) + ((out_tokens / 1_000_000) * rates["output"])

                return LLMResponse(
                    content=sql_clean,
                    model_name=model,
                    provider_name="GeminiPoolProvider",
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    estimated_cost_usd=cost_usd,
                    execution_time_sec=exec_time,
                    metadata={"rate_limit_status": "OK"}
                )
            except Exception as e:
                logger.error(f"Error calling {model}: {e}")
                last_error = e

        raise RuntimeError(f"All Gemini Pool models failed or rate limited. Last error: {last_error}")

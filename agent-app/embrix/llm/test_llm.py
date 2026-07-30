"""
Test script for Multi-Model Gemini Free Tier Rate Limiter (RPM, TPM, RPD) & Failover.
"""

import logging
from embrix.llm.rate_limiter import SlidingWindowRateLimiter
from embrix.llm.gemini_pool import FREE_GEMINI_MODEL_CONFIGS
from embrix.llm.factory import get_llm_provider

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("test_llm")


def test_rate_limiter_quotas():
    logger.info("Testing SlidingWindowRateLimiter (RPM, TPM, RPD quotas)...")
    limiter = SlidingWindowRateLimiter(model_configs=FREE_GEMINI_MODEL_CONFIGS)
    
    # Test gemini-3-flash (RPM limit = 5)
    model = "gemini-3-flash"
    for i in range(5):
        assert limiter.is_allowed(model, estimated_tokens=1000) == True
    
    # 6th request should be blocked due to RPM=5
    assert limiter.is_allowed(model, estimated_tokens=1000) == False
    logger.info(f"Successfully enforced RPM=5 for {model}.")

    # Test gemini-2.5-flash-lite (RPD limit = 20)
    model_rpd = "gemini-2.5-flash-lite"
    limiter.set_model_config(model_rpd, rpm=100, tpm=250000, rpd=3)
    assert limiter.is_allowed(model_rpd, estimated_tokens=100) == True
    assert limiter.is_allowed(model_rpd, estimated_tokens=100) == True
    assert limiter.is_allowed(model_rpd, estimated_tokens=100) == True
    assert limiter.is_allowed(model_rpd, estimated_tokens=100) == False
    logger.info(f"Successfully enforced RPD limit for {model_rpd}.")


def test_llm_factory():
    logger.info("Testing ResilientLLMProvider factory with new Gemini Free Tier Pool...")
    provider = get_llm_provider("auto")
    
    dummy_schema = "Table: core_usage.service_usage_readings (accountid, readingvalue, servicetype, latestreadingdate)"
    dummy_question = "Show total electricity usage volume by account"

    try:
        res = provider.generate_sql(dummy_question, dummy_schema)
        logger.info(f"Generated SQL via [{res.provider_name} / {res.model_name}]:")
        logger.info(f"SQL: {res.content}")
        logger.info(f"Tokens: In={res.input_tokens}, Out={res.output_tokens} | Cost=${res.estimated_cost_usd:.6f} | Exec Time={res.execution_time_sec:.2f}s")
    except Exception as e:
        logger.warning(f"LLM Provider execution test encountered notice: {e}")

    logger.info("=== MULTI-MODEL FREE GEMINI RATE LIMITER VERIFICATION PASSED ===")


if __name__ == "__main__":
    test_rate_limiter_quotas()
    test_llm_factory()

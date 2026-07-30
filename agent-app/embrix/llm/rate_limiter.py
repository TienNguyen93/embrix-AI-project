"""
embrix.llm.rate_limiter
───────────────────────
Thread-Safe Sliding-Window Rate Limiter enforcing RPM (Requests/Min),
TPM (Tokens/Min), and RPD (Requests/Day) per model to avoid free quota exhaustion.
"""

import time
import threading
from typing import Dict, List, Tuple, Optional


class SlidingWindowRateLimiter:
    """
    Multi-dimensional sliding-window rate limiter.
    Enforces RPM, TPM, and RPD per model key.
    """

    def __init__(self, model_configs: Optional[Dict[str, Dict[str, int]]] = None):
        # Default model limits if not provided
        self.model_configs = model_configs or {
            "gemini-3.1-flash-lite": {"rpm": 15, "tpm": 250000, "rpd": 500},
            "gemini-3-flash": {"rpm": 5, "tpm": 250000, "rpd": 20},
            "gemini-2.5-flash-lite": {"rpm": 10, "tpm": 250000, "rpd": 20},
        }
        self.window_sec = 60.0
        self.day_sec = 86400.0

        # Storage per model:
        # _minute_requests: model -> list of (timestamp, token_count)
        # _daily_requests: model -> list of timestamp
        self._minute_requests: Dict[str, List[Tuple[float, int]]] = {}
        self._daily_requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def set_model_config(self, model_key: str, rpm: int, tpm: int, rpd: int):
        """Configure specific RPM, TPM, and RPD limits for a model key."""
        with self._lock:
            self.model_configs[model_key] = {"rpm": rpm, "tpm": tpm, "rpd": rpd}

    def is_allowed(self, model_key: str, estimated_tokens: int = 1000) -> bool:
        """
        Check if a request with estimated_tokens is allowed under RPM, TPM, and RPD limits.
        If allowed, records the request timestamp and tokens atomically.
        """
        with self._lock:
            now = time.time()
            config = self.model_configs.get(model_key, {"rpm": 15, "tpm": 250000, "rpd": 500})
            
            rpm_limit = config.get("rpm", 15)
            tpm_limit = config.get("tpm", 250000)
            rpd_limit = config.get("rpd", 500)

            # Prune 60-second window requests
            if model_key not in self._minute_requests:
                self._minute_requests[model_key] = []
            self._minute_requests[model_key] = [
                (t, tokens) for (t, tokens) in self._minute_requests[model_key] if now - t < self.window_sec
            ]

            # Prune 24-hour window requests
            if model_key not in self._daily_requests:
                self._daily_requests[model_key] = []
            self._daily_requests[model_key] = [
                t for t in self._daily_requests[model_key] if now - t < self.day_sec
            ]

            current_rpm = len(self._minute_requests[model_key])
            current_tpm = sum(tokens for (_, tokens) in self._minute_requests[model_key])
            current_rpd = len(self._daily_requests[model_key])

            # Check quota constraints
            if current_rpm >= rpm_limit:
                return False
            if current_tpm + estimated_tokens > tpm_limit:
                return False
            if current_rpd >= rpd_limit:
                return False

            # Record allowed request
            self._minute_requests[model_key].append((now, estimated_tokens))
            self._daily_requests[model_key].append(now)
            return True

    def time_until_available(self, model_key: str) -> float:
        """Return wait time in seconds until next available minute window slot."""
        with self._lock:
            now = time.time()
            if model_key not in self._minute_requests or not self._minute_requests[model_key]:
                return 0.0

            oldest = self._minute_requests[model_key][0][0]
            remaining = self.window_sec - (now - oldest)
            return max(0.0, remaining)

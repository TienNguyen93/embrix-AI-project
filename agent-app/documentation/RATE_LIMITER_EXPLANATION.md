# 🧠 Embrix AI Agent — Detailed Rate Limiter Mechanics & Architecture

This document provides a deep-dive technical explanation of how the multi-dimensional rate limiter function works in [`agent-app/embrix/llm/rate_limiter.py`](../embrix/llm/rate_limiter.py).

---

## 1. High-Level Algorithm Overview

The rate limiter uses a **Multi-Dimensional Sliding Window Log Algorithm**. It continuously tracks and prunes API request timestamps in real-time to enforce **RPM** (Requests Per Minute), **TPM** (Tokens Per Minute), and **RPD** (Requests Per Day) constraints per LLM model.

Unlike Fixed Window algorithms (which reset at fixed 1-minute clock intervals and are prone to double-spike rate limit errors at boundary edges), the **Sliding Window Log** algorithm maintains a continuously rolling time window relative to the exact current timestamp `now = time.time()`.

---

## 2. Internal Data Structures

Inside `SlidingWindowRateLimiter.__init__()`, the rate limiter sets up multi-dimensional quota limits and storage dictionaries per model key:

```python
self.model_configs = {
    "gemini-3.1-flash-lite": {"rpm": 15, "tpm": 250000, "rpd": 500},
    "gemini-3-flash":       {"rpm": 5,  "tpm": 250000, "rpd": 20},
    "gemini-2.5-flash-lite": {"rpm": 10, "tpm": 250000, "rpd": 20},
}

self.window_sec = 60.0        # 1-minute sliding window
self.day_sec = 86400.0        # 24-hour sliding window

self._minute_requests = {}    # Stores list of (timestamp, token_count) for last 60s
self._daily_requests = {}     # Stores list of timestamps for last 24h
self._lock = threading.Lock() # Thread lock for safety in concurrent web servers
```

---

## 3. Step-by-Step Mechanics of `is_allowed()`

Whenever a query needs an LLM completion (e.g. before calling `gemini-3.1-flash-lite`), the system calls:
`rate_limiter.is_allowed(model_key="gemini-3.1-flash-lite", estimated_tokens=1200)`

Here is what happens line-by-line:

### Step A: Thread Safety (`with self._lock:`)
Multiple users or web server threads might request LLM completion at the exact same millisecond. The `self._lock` prevents race conditions so counter checks are 100% atomic and thread-safe.

### Step B: Dynamic Timestamp Pruning
Instead of resetting counters at fixed clock minutes, the algorithm looks back from the exact current timestamp `now = time.time()`:

```python
# 1. Keep only entries from the LAST 60 SECONDS
self._minute_requests[model_key] = [
    (t, tokens) for (t, tokens) in self._minute_requests[model_key] 
    if now - t < 60.0
]

# 2. Keep only entries from the LAST 24 HOURS (86,400s)
self._daily_requests[model_key] = [
    t for t in self._daily_requests[model_key] 
    if now - t < 86400.0
]
```
Any call older than 60 seconds (or 24 hours) is instantly purged from memory.

### Step C: Multi-Quota Evaluation
Next, it calculates current usage across all 3 metrics:

```python
current_rpm = len(self._minute_requests[model_key])           # Request count in last 60s
current_tpm = sum(tokens for (_, tokens) in _minute_requests) # Token count in last 60s
current_rpd = len(self._daily_requests[model_key])            # Request count in last 24h

# Check constraints:
if current_rpm >= rpm_limit:
    return False  # RPM exceeded!

if current_tpm + estimated_tokens > tpm_limit:
    return False  # TPM exceeded!

if current_rpd >= rpd_limit:
    return False  # RPD daily limit exceeded!
```

### Step D: Recording Allowed Requests
If **all 3 checks pass**, the request timestamp and estimated token count are recorded atomically in the sliding log, and `is_allowed()` returns `True`:

```python
self._minute_requests[model_key].append((now, estimated_tokens))
self._daily_requests[model_key].append(now)
return True
```

---

## 4. How Failover Integration Works (`gemini_pool.py`)

In [`agent-app/embrix/llm/gemini_pool.py`](../embrix/llm/gemini_pool.py), `GeminiPoolProvider` uses `is_allowed()` to loop through models seamlessly:

```python
for model in ["gemini-3.1-flash-lite", "gemini-3-flash", "gemini-2.5-flash-lite"]:
    if not self.rate_limiter.is_allowed(model, estimated_tokens=in_tokens):
        # Model is rate-limited! Rotate to next model in pool.
        continue

    try:
        # Call Gemini API
        return response
    except Exception as e: # e.g. HTTP 429 Too Many Requests
        continue
```

If `gemini-3.1-flash-lite` hits 15 RPM or 500 RPD, `is_allowed()` immediately returns `False`, causing the system to automatically rotate to `gemini-3-flash` $\rightarrow$ `gemini-2.5-flash-lite` $\rightarrow$ local Ollama (`qwen3.5`) without failing the user's request.

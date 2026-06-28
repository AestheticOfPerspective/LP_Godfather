"""
utils/ratelimit.py — Token-Bucket Rate Limiter + Circuit Breaker
"""
import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            deficit = tokens - self.tokens
            wait = deficit / self.rate
            return wait

    async def wait_and_acquire(self, tokens: float = 1.0) -> None:
        wait = await self.acquire(tokens)
        if wait > 0:
            logger.debug("Rate limit: waiting %.2fs", wait)
            await asyncio.sleep(wait)


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_time: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure = 0.0
        self._open = False
        self._lock = asyncio.Lock()

    async def call(self, coro_factory):
        async with self._lock:
            if self._open:
                if time.monotonic() - self.last_failure >= self.recovery_time:
                    self._open = False
                    self.failures = 0
                    logger.info("Circuit breaker: half-open, retrying")
                else:
                    logger.warning("Circuit breaker: open, rejecting call")
                    raise RuntimeError("Circuit breaker is open")

        try:
            result = await coro_factory()
        except Exception as e:
            async with self._lock:
                self.failures += 1
                self.last_failure = time.monotonic()
                if self.failures >= self.failure_threshold:
                    self._open = True
                    logger.warning("Circuit breaker: tripped (failures=%d)", self.failures)
            raise e

        async with self._lock:
            self.failures = 0
        return result


class RateLimiter:
    """
    Token-bucket rate limiter with per-command and global limits.
    Used by all runtimes; accepts optional per-command config.
    """

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._user_buckets: dict[str, TokenBucket] = {}
        self._cb: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    def _get_bucket(self, key: str, rate: float, burst: int) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(rate, burst)
        return self._buckets[key]

    def _get_user_bucket(self, user_key: str) -> TokenBucket:
        if user_key not in self._user_buckets:
            self._user_buckets[user_key] = TokenBucket(1.0, 3)
        return self._user_buckets[user_key]

    def get_circuit_breaker(self, name: str, threshold: int = 5, recovery: float = 30.0) -> CircuitBreaker:
        if name not in self._cb:
            self._cb[name] = CircuitBreaker(threshold, recovery)
        return self._cb[name]

    async def check_command(self, command: str, user: str) -> float:
        wait = 0.0

        global_bucket = self._get_bucket("_global", rate=0.67, burst=20)
        wait = max(wait, await global_bucket.acquire())

        cmd_rates = {
            "ask": (0.1, 1),
            "prompt": (0.1, 1),
            "vibe": (0.03, 1),
            "nowplaying": (0.03, 1),
            "songid": (0.03, 1),
        }
        rate, burst = cmd_rates.get(command, (0.33, 3))
        cmd_bucket = self._get_bucket(f"cmd:{command}", rate, burst)
        wait = max(wait, await cmd_bucket.acquire())

        user_bucket = self._get_user_bucket(f"user:{user}")
        wait = max(wait, await user_bucket.acquire())

        return wait

    async def wait_and_check(self, command: str, user: str) -> None:
        remaining = await self.check_command(command, user)
        if remaining > 0:
            logger.debug("Rate limit: %s %s waiting %.2fs", command, user, remaining)
            await asyncio.sleep(remaining)


rate_limiter = RateLimiter()

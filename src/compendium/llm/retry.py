"""Retry wrapper with exponential backoff for LLM API calls."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")
logger = logging.getLogger(__name__)

RATE_LIMIT_TERMS = (
    "rate_limit",
    "rate limit",
    "429",
    "too many requests",
    "overloaded",
    "capacity",
)


def is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception is a rate limit error."""
    msg = str(exc).lower()
    return any(term in msg for term in RATE_LIMIT_TERMS)


async def with_retry[T](
    fn: Callable[..., Awaitable[T]],
    *args: object,
    max_retries: int = 3,
    base_delay: float = 2.0,
    backoff_factor: float = 4.0,
    **kwargs: object,
) -> T:
    """Call fn with exponential backoff retry on rate limit errors."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if not is_rate_limit_error(e) or attempt == max_retries:
                raise
            delay = base_delay * (backoff_factor**attempt)
            logger.warning(
                "Rate limited (attempt %d/%d), retrying in %.1fs...",
                attempt + 1,
                max_retries + 1,
                delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]

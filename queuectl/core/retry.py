"""
Exponential backoff retry scheduling module.
Calculates retry delays using formula: delay = base ^ attempts.
"""

from datetime import datetime, timedelta, timezone


def calculate_backoff_delay(attempts: int, base: float = 2.0) -> float:
    """
    Calculates backoff delay in seconds for a given attempt number.
    Formula: delay = base ^ attempts
    
    Example with base = 2:
    - Attempt 1: 2^1 = 2 seconds
    - Attempt 2: 2^2 = 4 seconds
    - Attempt 3: 2^3 = 8 seconds
    """
    if attempts <= 0:
        return 0.0
    return float(base ** attempts)


def get_next_retry_timestamp(attempts: int, base: float = 2.0) -> str:
    """Returns ISO 8601 UTC timestamp string for when the job should be retried next."""
    delay = calculate_backoff_delay(attempts, base)
    next_time = datetime.now(timezone.utc) + timedelta(seconds=delay)
    return next_time.isoformat()

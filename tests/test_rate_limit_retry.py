from __future__ import annotations

import asyncio
import logging

import pytest

from dialectical_framework.brain import Brain
from dialectical_framework.utils.use_brain import use_brain


class SimpleAIConsumer:
    """Simple class to test use_brain decorator with rate limiting."""

    def __init__(self, brain: Brain):
        self.brain = brain

    @use_brain()
    async def simple_prompt(self) -> str:
        """Simple prompt that triggers LLM call."""
        return "What is 2+2?"


class RetryDetector(logging.Handler):
    """Custom logging handler to detect retry attempts."""

    def __init__(self):
        super().__init__()
        self.retry_detected = False
        self.retry_message = None

    def emit(self, record):
        if "Retrying" in record.getMessage():
            self.retry_detected = True
            self.retry_message = record.getMessage()


@pytest.mark.asyncio
@pytest.mark.parametrize("model,quota", [
    ("bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0", 7),  # Low quota model
])
async def test_retry_logic(model: str, quota: int):
    """
    Fast test to verify retry logic works.

    Args:
        model: The model to test (should have low quota)
        quota: Expected requests per minute quota

    This test:
    1. Fires (quota * 2) concurrent requests to trigger rate limit
    2. Detects if retry happens (via logging)
    3. Exits as soon as retry is detected (no need to wait for success)
    """
    print(f"\n=== Testing Retry Logic ===")
    print(f"Model: {model}")
    print(f"Expected quota: {quota} RPM")

    # Set up retry detector
    retry_detector = RetryDetector()
    retry_detector.setLevel(logging.WARNING)
    logger = logging.getLogger("dialectical_framework.utils.use_brain")
    logger.addHandler(retry_detector)

    brain = Brain(ai_model=model, ai_provider=None)

    # Fire (quota * 2) requests to definitely trigger rate limit
    num_requests = quota * 2
    print(f"Firing {num_requests} concurrent requests...")

    consumers = [SimpleAIConsumer(brain) for _ in range(num_requests)]

    # Create actual tasks (not coroutines)
    tasks = [asyncio.create_task(consumer.simple_prompt()) for consumer in consumers]

    # Start tasks but don't wait for all to complete
    # We just need to detect one retry
    results = []
    for task in asyncio.as_completed(tasks):
        try:
            result = await task
            results.append(result)
        except Exception as e:
            results.append(e)

        # Exit early if we detected a retry
        if retry_detector.retry_detected:
            print(f"\n✓ Retry detected!")
            print(f"  Message: {retry_detector.retry_message[:150]}")

            # Cancel remaining tasks
            for t in tasks:
                if not t.done():
                    t.cancel()

            # Wait briefly for cancellations
            await asyncio.gather(*tasks, return_exceptions=True)
            break

    # Clean up
    logger.removeHandler(retry_detector)

    # Assert retry was detected
    assert retry_detector.retry_detected, (
        "No retry detected! This means use_brain retry logic is broken. "
        f"Completed {len(results)}/{num_requests} requests."
    )

    print(f"\n✓ Retry logic is working correctly")

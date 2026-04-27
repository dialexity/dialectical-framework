"""
Test for use_brain retry logic using mock client.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest
from litellm import RateLimitError
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from dialectical_framework.brain import Brain
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.utils.use_brain import use_brain


class MockOpenAIClient(AsyncOpenAI):
    """Mock OpenAI client that raises RateLimitError on first 2 calls."""

    def __init__(self, *args: Any, **kwargs: Any):
        # Don't call super().__init__() to avoid needing real API key
        self.call_count = 0

    @property
    def chat(self) -> Any:
        return self

    @property
    def completions(self) -> Any:
        return self

    async def create(self, *args: Any, **kwargs: Any) -> ChatCompletion:
        """Mock create method that fails twice, then succeeds."""
        self.call_count += 1

        if self.call_count <= 2:
            # Raise rate limit error on first 2 calls
            raise RateLimitError(
                message="Too many requests, please wait before trying again.",
                response=None,
                body=None,
            )

        # Success on 3rd call
        return ChatCompletion(
            id="mock-completion-id",
            object="chat.completion",
            created=1234567890,
            model="gpt-4",
            choices=[
                Choice(
                    index=0,
                    message=ChatCompletionMessage(
                        role="assistant",
                        content="Test response",
                    ),
                    finish_reason="stop",
                )
            ],
        )


@pytest.mark.asyncio
async def test_retry_logic():
    """
    Test that use_brain retries on rate limit errors.

    Uses a mock client that fails twice, then succeeds.
    Verifies retry logic works via logging and call count.
    """
    print("\n=== Testing use_brain Retry Logic (Mock) ===")

    # Setup logging detector
    class RetryDetector(logging.Handler):
        def __init__(self):
            super().__init__()
            self.retry_count = 0

        def emit(self, record):
            if "Retrying" in record.getMessage():
                self.retry_count += 1

    detector = RetryDetector()
    detector.setLevel(logging.WARNING)
    logger = logging.getLogger("dialectical_framework.utils.use_brain")
    logger.addHandler(detector)

    # Create mock client
    mock_client = MockOpenAIClient()

    # Create brain with OpenAI provider (so we can use custom client)
    brain = Brain(ai_model="gpt-4", ai_provider="openai")

    class Consumer(HasBrain):
        def __init__(self, brain_instance: Brain):
            self._brain = brain_instance

        @property
        def brain(self) -> Brain:
            return self._brain

        @use_brain(client=mock_client)
        async def call(self) -> str:
            return "Test"

    consumer = Consumer(brain)
    result = await consumer.call()

    logger.removeHandler(detector)

    # Verify
    print(f"✓ Call count: {mock_client.call_count}")
    print(f"✓ Retry count: {detector.retry_count}")
    print(f"✓ Result: {result}")

    assert mock_client.call_count == 3, f"Expected 3 calls (2 failures + 1 success), got {mock_client.call_count}"
    assert detector.retry_count == 2, f"Expected 2 retries, got {detector.retry_count}"
    assert result is not None

    print("✅ Retry logic works!")

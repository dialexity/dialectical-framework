"""
Test for API quota limits and retry logic.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

import pytest

from dialectical_framework.brain import Brain
from dialectical_framework.utils.use_brain import use_brain


@pytest.mark.asyncio
@pytest.mark.parametrize("model,expected_rpm", [
    ("bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0", 7),  # Cross-region Haiku 4.5
    # ("bedrock/global.anthropic.claude-haiku-4-5-20251001-v1:0", 13),  # Global Haiku 4.5
    # ("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0", 200),  # Global Sonnet 4.5
    # ("bedrock/global.anthropic.claude-sonnet-4-5-20250929-v1:0", 200),  # Global Sonnet 4.5
])
async def test_requests_per_minute_quota(model: str, expected_rpm: int):
    """
    Test that use_brain respects rate limit quotas.

    Fires concurrent requests to trigger rate limits, validates we hit the quota,
    and captures timestamps for diagnostics.

    Args:
        model: The AI model to test
        expected_rpm: Expected requests per minute quota for this model
    """
    print(f"\n=== Testing Requests Per Minute Quota ===")
    print(f"Model: {model}")
    print(f"Expected RPM: {expected_rpm}")

    # Capture rate limit errors with timestamps (no retries with retry_max=1)
    rate_limit_errors = []

    # Use model with specified quota
    brain = Brain(ai_model=model, ai_provider=None)

    class Consumer:
        def __init__(self, brain: Brain):
            self.brain = brain

        @use_brain(retry_max=1)
        async def call(self) -> str:
            return "Test"

    # Fire concurrent requests (more than quota to trigger rate limit)
    num_requests = expected_rpm * 2
    print(f"Firing {num_requests} concurrent requests...")
    consumers = [Consumer(brain) for _ in range(num_requests)]
    tasks = [asyncio.create_task(c.call()) for c in consumers]

    # Gather results and capture errors
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Analyze results
    successes = 0
    failures = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failures += 1
            error_msg = str(result)
            if "rate" in error_msg.lower() or "too many" in error_msg.lower():
                rate_limit_errors.append({
                    "timestamp": datetime.now().isoformat(),
                    "request_number": i + 1,
                    "error": error_msg,
                })
        else:
            successes += 1

    print(f"\n✓ Results: {successes} successes, {failures} failures")
    print(f"✓ Rate limit errors: {len(rate_limit_errors)}")

    # Validate quota
    # Success count should be close to expected_rpm (within ±2 tolerance)
    quota_min = max(1, expected_rpm - 2)
    quota_max = expected_rpm + 2

    if quota_min <= successes <= quota_max:
        print(f"✅ Quota validation passed: {successes} successes within expected range [{quota_min}, {quota_max}]")
        quota_valid = True
    else:
        print(f"⚠️  Quota validation issue: {successes} successes outside expected range [{quota_min}, {quota_max}]")
        print(f"   This might indicate quota was increased or changed")
        quota_valid = False

    # Save diagnostic info for AWS Support if needed
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    diagnostic_file = os.path.join(reports_dir, "aws_rate_limit_diagnostics.txt")
    with open(diagnostic_file, "w") as f:
        f.write("="*80 + "\n")
        f.write("AWS BEDROCK RATE LIMIT DIAGNOSTIC REPORT\n")
        f.write("="*80 + "\n\n")
        f.write(f"Model: {model}\n")
        f.write(f"Expected RPM Quota: {expected_rpm}\n")
        f.write(f"Test Time: {datetime.now().isoformat()}\n\n")
        f.write(f"Total Requests: {len(results)}\n")
        f.write(f"Successful: {successes}\n")
        f.write(f"Failed: {failures}\n")
        f.write(f"Rate Limit Errors: {len(rate_limit_errors)}\n")
        f.write(f"Quota Valid: {quota_valid}\n\n")

        if not quota_valid:
            f.write("⚠️  WARNING: Quota validation failed!\n")
            f.write(f"   Expected {quota_min}-{quota_max} successes, got {successes}\n")
            f.write("   This might indicate:\n")
            f.write("   - Quota was increased by AWS Support\n")
            f.write("   - Quota settings changed\n")
            f.write("   - Model routing changed\n\n")

        if rate_limit_errors:
            f.write("RATE LIMIT ERRORS WITH TIMESTAMPS:\n")
            f.write("-"*80 + "\n\n")

            for error in rate_limit_errors:
                f.write(f"Request #{error['request_number']}:\n")
                f.write(f"  Timestamp: {error['timestamp']}\n")
                f.write(f"  Error: {error['error']}\n\n")
        else:
            f.write("No rate limit errors encountered.\n")
            f.write("All requests succeeded - quota may have been increased.\n")

    print(f"✓ Diagnostic report saved to: {diagnostic_file}")

    # Assert we got some rate limit errors (otherwise quota might have been increased)
    assert len(rate_limit_errors) > 0, (
        f"No rate limit errors encountered. Expected to hit quota of {expected_rpm} RPM, "
        f"but all {successes} requests succeeded. Quota may have been increased."
    )

    print("✅ Rate limit test complete!")
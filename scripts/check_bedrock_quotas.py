#!/usr/bin/env python3
"""Check Bedrock quotas for the configured model and suggest concurrency settings.

Reads DIALEXITY_DEFAULT_MODEL from .env, determines the region from AWS config,
and queries Service Quotas for invocations/minute and tokens/minute limits.

Usage:
    python scripts/check_bedrock_quotas.py
    python scripts/check_bedrock_quotas.py --region us-west-2
    python scripts/check_bedrock_quotas.py --profile my-profile
"""
from __future__ import annotations

import argparse
import os
import re
import sys

from dotenv import load_dotenv


# Map model ID patterns to how they appear in quota names.
# Order matters — first match wins.
MODEL_PATTERNS: list[tuple[str, list[str]]] = [
    # Global cross-region models (global.anthropic.*)
    ("global.anthropic.claude-haiku-4-5", ["Global", "Haiku 4.5"]),
    ("global.anthropic.claude-opus-4-6", ["Global", "Opus 4.6"]),
    ("global.anthropic.claude-opus-4-5", ["Global", "Opus 4.5"]),
    ("global.anthropic.claude-sonnet-4-6", ["Global", "Sonnet 4.6"]),
    ("global.anthropic.claude-sonnet-4-5", ["Global", "Sonnet 4.5"]),
    ("global.anthropic.claude-sonnet-4", ["Global", "Sonnet 4 V1"]),
    # US cross-region models (us.anthropic.*)
    ("us.anthropic.claude-haiku-4-5", ["Cross-region", "Haiku 4.5"]),
    ("us.anthropic.claude-opus-4-6", ["Cross-region", "Opus 4.6"]),
    ("us.anthropic.claude-opus-4-5", ["Cross-region", "Opus 4.5"]),
    ("us.anthropic.claude-sonnet-4-6", ["Cross-region", "Sonnet 4.6"]),
    ("us.anthropic.claude-sonnet-4-5", ["Cross-region", "Sonnet 4.5"]),
    ("us.anthropic.claude-sonnet-4", ["Cross-region", "Sonnet 4 V1"]),
    ("us.anthropic.claude-3-7-sonnet", ["Cross-region", "3.7 Sonnet"]),
    ("us.anthropic.claude-3-5-sonnet", ["Cross-Region", "3.5 Sonnet V2"]),
    ("us.anthropic.claude-3-5-haiku", ["Cross-Region", "3.5 Haiku"]),
    # On-demand models (anthropic.claude-*)
    ("anthropic.claude-3-5-haiku", ["On-demand", "3.5 Haiku"]),
    ("anthropic.claude-3-5-sonnet", ["On-demand", "3.5 Sonnet"]),
    ("anthropic.claude-3-haiku", ["On-demand", "3 Haiku"]),
    ("anthropic.claude-3-opus", ["On-demand", "3 Opus"]),
    ("anthropic.claude-3-sonnet", ["On-demand", "3 Sonnet"]),
]


def _detect_model_keywords(model_id: str) -> list[str] | None:
    """Match model ID to quota name keywords."""
    model_lower = model_id.lower()
    for pattern, keywords in MODEL_PATTERNS:
        if pattern in model_lower:
            return keywords
    return None


def _quota_matches(name: str, keywords: list[str]) -> bool:
    """Check if all keywords appear in a quota name (case-insensitive)."""
    name_lower = name.lower()
    return all(kw.lower() in name_lower for kw in keywords)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Check Bedrock quotas")
    parser.add_argument("--region", help="AWS region (default: from AWS_DEFAULT_REGION or boto3 session)")
    parser.add_argument("--profile", help="AWS profile name (default: from AWS_PROFILE env var)")
    args = parser.parse_args()

    model = os.getenv("DIALEXITY_DEFAULT_MODEL", "")
    if not model:
        print("ERROR: DIALEXITY_DEFAULT_MODEL not set in .env")
        sys.exit(1)

    # Strip bedrock/ prefix to get the model identifier
    model_id = model.removeprefix("bedrock/")
    print(f"Model: {model_id}")

    keywords = _detect_model_keywords(model_id)
    if keywords:
        print(f"Matching quotas containing: {keywords}")
    else:
        print("WARNING: Could not map model to quota keywords, will show all Claude quotas")

    try:
        import boto3
    except ImportError:
        print("ERROR: boto3 not installed. Run: pip install boto3")
        sys.exit(1)

    session = boto3.Session(region_name=args.region, profile_name=args.profile)
    region = session.region_name
    print(f"Region: {region}")
    print()

    client = session.client("service-quotas")

    # Fetch all Bedrock quotas
    quotas = []
    paginator = client.get_paginator("list_service_quotas")
    for page in paginator.paginate(ServiceCode="bedrock"):
        quotas.extend(page["Quotas"])

    # Filter to Claude-related quotas
    claude_quotas = [
        q for q in quotas
        if "claude" in q["QuotaName"].lower() or "anthropic" in q["QuotaName"].lower()
    ]

    if not claude_quotas:
        print("No Claude/Anthropic quotas found. Available Bedrock quotas:")
        for q in sorted(quotas, key=lambda x: x["QuotaName"]):
            print(f"  {q['QuotaName']}: {q['Value']}")
        return

    # Categorize quotas
    rpm_quotas: list[tuple[str, float, bool]] = []
    tpm_quotas: list[tuple[str, float, bool]] = []

    for q in sorted(claude_quotas, key=lambda x: x["QuotaName"]):
        name = q["QuotaName"]
        value = q["Value"]
        is_ours = _quota_matches(name, keywords) if keywords else False

        is_rpm = ("request" in name.lower() and "per minute" in name.lower()) or \
                 ("invocation" in name.lower() and "per minute" in name.lower())
        is_tpm = "token" in name.lower() and "per minute" in name.lower()

        if is_rpm:
            rpm_quotas.append((name, value, is_ours))
        elif is_tpm:
            tpm_quotas.append((name, value, is_ours))

    # Display RPM
    if rpm_quotas:
        print("=== Requests per minute (RPM) ===")
        our_rpm_value = None
        for name, value, ours in rpm_quotas:
            if ours:
                print(f"  >>> {name}: {value:,.0f} <<<")
                if our_rpm_value is None or "1M Context" not in name:
                    our_rpm_value = value
            # Only show non-matching if no keywords detected
            elif not keywords:
                print(f"      {name}: {value:,.0f}")
        # Show nearby models for context
        if keywords:
            print()
            print("  (Other models for comparison):")
            for name, value, ours in rpm_quotas:
                if not ours and value > 0:
                    print(f"      {name}: {value:,.0f}")
        print()
    else:
        our_rpm_value = None

    # Display TPM
    if tpm_quotas:
        print("=== Tokens per minute (TPM) ===")
        our_tpm_value = None
        for name, value, ours in tpm_quotas:
            if ours:
                print(f"  >>> {name}: {value:,.0f} <<<")
                if our_tpm_value is None or "1M Context" not in name:
                    our_tpm_value = value
            elif not keywords:
                print(f"      {name}: {value:,.0f}")
        if keywords:
            print()
            print("  (Other models for comparison):")
            for name, value, ours in tpm_quotas:
                if not ours and value > 0:
                    print(f"      {name}: {value:,.0f}")
        print()
    else:
        our_tpm_value = None

    # Suggestion
    print("=" * 50)
    print("RECOMMENDATION")
    print("=" * 50)
    if our_rpm_value:
        suggested = max(8, int(our_rpm_value / 3))
        print(f"  Your RPM limit: {our_rpm_value:,.0f}")
        print(f"  Your TPM limit: {our_tpm_value:,.0f}" if our_tpm_value else "")
        print()
        print(f"  Suggested DIALEXITY_MAX_CONCURRENT_LLM_CALLS = {suggested}")
        print(f"    (RPM / 3, assuming ~20s avg response time)")
        print()
        if our_rpm_value >= 5000:
            print(f"  Your RPM is very high ({our_rpm_value:,.0f}). The semaphore at 40")
            print(f"  is purely for runaway protection — you won't hit RPM limits.")
            print(f"  TPM ({our_tpm_value:,.0f}) is more likely to be your binding constraint" if our_tpm_value else "")
            print(f"  under heavy parallel load. Rate-limit retry handles this dynamically.")
    else:
        print("  Could not determine your model's RPM limit.")
        print("  Look at the quotas above and divide RPM by 3.")


if __name__ == "__main__":
    main()

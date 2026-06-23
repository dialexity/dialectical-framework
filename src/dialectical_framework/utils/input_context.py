"""
Utility for building input context from digests for downstream LLM concerns.

Follows the same <Input id="..."> tagging pattern as CompositeInputResolver.resolve_all(),
but prefers digest over full content resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.protocols.input_resolver import InputResolver


async def input_context(
    inputs: list[Input],
    input_resolver: InputResolver,
) -> str:
    """
    Get labeled digests from inputs for injection into LLM prompts.

    Each input's digest (or fallback full content) is wrapped in <Input id="...">
    tags so the LLM knows which source it came from and can use read_input(hash)
    to pull full content if needed.

    Args:
        inputs: List of Input nodes to get digests from
        input_resolver: Resolver for fallback when digest is not yet available

    Returns:
        Combined text with each input wrapped in <Input> tags.
        Empty string if no inputs or all inputs have no content.
    """
    if not inputs:
        return ""

    parts = []
    for input_node in inputs:
        if input_node.digest:
            text = input_node.digest
        else:
            text = await input_resolver.resolve(input_node)

        if not text:
            continue

        parts.append(f'<Input id="{input_node.hash}">\n{text}\n</Input>')

    return "\n\n".join(parts)

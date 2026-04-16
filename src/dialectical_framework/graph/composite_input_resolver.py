"""
CompositeInputResolver that orchestrates delegation based on URI scheme.

This is the main InputResolver that gets injected via DI. It delegates to
scheme-specific resolvers based on the content format:
- dx://  -> DialexityInputResolver (internal graph references)
- data:  -> VerbatimInputResolver (data URIs)
- (else) -> VerbatimInputResolver (plain text)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Union

from dialectical_framework.graph.dialexity_input_resolver import DialexityInputResolver
from dialectical_framework.graph.verbatim_input_resolver import VerbatimInputResolver
from dialectical_framework.protocols.input_resolver import InputResolver

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.nodes.input import Input


class CompositeInputResolver(InputResolver):
    """
    Orchestrates input resolution by delegating to scheme-specific resolvers.

    Delegation rules:
    - dx://  -> DialexityInputResolver (internal graph node references)
    - data:  -> VerbatimInputResolver (base64/URL-encoded data)
    - (else) -> VerbatimInputResolver (plain text)

    This is the resolver that gets wired into DI as the default InputResolver.
    Apps can still override with their own resolver if needed.

    Example:
        # Plain text - handled by VerbatimInputResolver
        input1 = Input(content="My plain text content")

        # data: URI - handled by VerbatimInputResolver
        input2 = Input(content="data:text/plain,Hello%20World")

        # dx:// URI - handled by DialexityInputResolver
        input3 = Input(content="dx://scope-123/abc1234def...")

        resolver = CompositeInputResolver(
            verbatim_resolver=VerbatimInputResolver(),
            dialexity_resolver=DialexityInputResolver()
        )
        text = await resolver.resolve(input3)  # Fetches content from graph node
    """

    def __init__(
        self,
        verbatim_resolver: VerbatimInputResolver,
        dialexity_resolver: DialexityInputResolver,
    ) -> None:
        """
        Initialize with scheme-specific resolvers.

        Args:
            verbatim_resolver: Handles plain text and data: URIs
            dialexity_resolver: Handles dx:// URIs (internal graph references)
        """
        self._verbatim = verbatim_resolver
        self._dialexity = dialexity_resolver

    async def resolve(self, input_node: Input) -> str:
        """
        Resolve an Input node's content by delegating to the appropriate resolver.

        Args:
            input_node: Input node with content to resolve

        Returns:
            Resolved text content

        Raises:
            Various resolver-specific exceptions based on the content scheme
        """
        content = input_node.content
        if not content:
            return ""

        if content.startswith("dx://"):
            return await self._dialexity.resolve(content)

        # VerbatimInputResolver handles plain text and data: URIs
        return await self._verbatim.resolve(input_node)

    async def resolve_all(self, source: Union[Case, list[Input]]) -> str:
        """
        Resolve multiple inputs to combined text content.

        Combines all input contents with XML-style delineation:
        <Input id="...">resolved text</Input>

        Args:
            source: Either a Case node (resolves all connected Inputs)
                   or a list of Input nodes to resolve

        Returns:
            Combined text content with each input wrapped in <Input> tags

        Raises:
            ValueError: If no inputs provided
        """
        from dialectical_framework.graph.nodes.case import Case

        # Get inputs list
        if isinstance(source, Case):
            inputs = [inp for inp, _ in source.inputs.all()]
        else:
            inputs = source

        if not inputs:
            raise ValueError("No inputs provided to resolve")

        # Combine all inputs with delineation (skip inputs with no content)
        parts = []
        for input_node in inputs:
            if not input_node.content:
                continue  # Skip inputs with None/empty content
            resolved_text = await self.resolve(input_node)
            parts.append(f'<Input id="{input_node.hash}">\n{resolved_text}\n</Input>')

        return "\n\n".join(parts)

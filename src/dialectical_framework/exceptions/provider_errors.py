"""
Provider verdicts that are not transport faults.

`ModelRefusal` is raised when the model stops with ``stop_reason: "refusal"``
(the provider's policy classifiers intervened). It is deliberately its own
type: before it existed a refusal reached the framework as an empty or cut-off
reply, so a structured call re-asked it as a ParseError (ten times) and a
conversational turn fell through to a second, structured call that was refused
again. A refusal is the provider's answer to THIS request, so nothing retries
it; the caller decides — a concern fails soft as on any error, a host shows the
person something and lets them rephrase.
"""

from __future__ import annotations

from typing import Optional


class ModelRefusal(RuntimeError):
    """The model declined the request (``stop_reason: "refusal"``).

    ``category`` and ``explanation`` are the provider's ``stop_details`` when it
    sends them (``"cyber"``, ``"bio"``, or None for an unnamed category); a
    streamed round does not carry them and leaves both None. The explanation
    text is not guaranteed stable by the provider — show it, never branch on it.
    """

    def __init__(
        self,
        model: str,
        *,
        category: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> None:
        self.model = model
        self.category = category
        self.explanation = explanation
        detail = f" ({category})" if category else ""
        super().__init__(
            f"Model {model} refused the request{detail}"
            + (f": {explanation}" if explanation else "")
        )

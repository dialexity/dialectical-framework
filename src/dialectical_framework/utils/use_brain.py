from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import litellm
from mirascope import llm
from tenacity import retry, stop_after_attempt, wait_exponential

from dialectical_framework.brain import Brain
from dialectical_framework.protocols.has_brain import HasBrain

T = TypeVar("T")

def use_brain(brain: Optional[Brain] = None, **llm_call_kwargs):
    """
    Decorator factory for Mirascope that creates an LLM call using the brain's AI provider and model.

    Args:
        brain: Optional Brain instance to use. If not provided, will expect 'self' to implement HasBrain protocol
        **llm_call_kwargs: All keyword arguments to pass to @llm.call, including response_model

    Returns:
        A decorator that wraps methods to make LLM calls
    """

    def decorator(method: Callable[..., Any]) -> Callable[..., T]:
        @wraps(method)
        async def wrapper(*args, **kwargs) -> T:
            target_brain = None
            if brain is not None:
                target_brain = brain
            else:
                # Expect first argument to be self with HasBrain protocol
                if not args:
                    raise TypeError(
                        "No arguments provided, no brain specified in decorator, and no brain available from DI container"
                    )

                first_arg = args[0]
                if isinstance(first_arg, HasBrain) and target_brain is None:
                    target_brain = first_arg.brain
                else:
                    raise TypeError(
                        f"{first_arg.__class__.__name__} must implement {HasBrain.__name__} protocol, "
                        "pass brain parameter to decorator, or have Brain available in DI container"
                    )

            overridden_ai_provider, overridden_ai_model = target_brain.specification()
            if overridden_ai_provider == "bedrock":
                # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
                # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
                overridden_ai_provider, overridden_ai_model = (
                    target_brain.modified_specification(ai_provider="litellm")
                )

            if overridden_ai_provider == "litellm":
                # We use LiteLLM just for convenience, the real framework is Mirascope.
                # So anything related to litellm can be suppressed
                litellm.turn_off_message_logging = True

            # Merge brain specification with all parameters
            call_params = {
                "provider": overridden_ai_provider,
                "model": overridden_ai_model,
                **llm_call_kwargs,  # All parameters including response_model
            }

            # https://mirascope.com/docs/mirascope/learn/retries
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=4, max=10),
            )
            @llm.call(**call_params)
            async def _llm_call():
                return await method(*args, **kwargs)

            return await _llm_call()

        return wrapper

    return decorator

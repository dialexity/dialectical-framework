from abc import ABC, abstractmethod
from typing import TypeVar, Callable, Any, Protocol, runtime_checkable, Optional
from functools import wraps

from mirascope import llm

from dialectical_framework.brain import Brain

T = TypeVar('T')

@runtime_checkable
class HasBrain(Protocol):
    @property
    @abstractmethod
    def brain(self) -> Brain: ...

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
            # Determine the brain to use
            if brain is not None:
                target_brain = brain
            else:
                # Expect first argument to be self with HasBrain protocol
                if not args:
                    raise TypeError("No arguments provided and no brain specified in decorator")
                
                first_arg = args[0]
                if isinstance(first_arg, HasBrain):
                    target_brain = first_arg.brain
                else:
                    raise TypeError(
                        f"{first_arg.__class__.__name__} must implement {HasBrain.__name__} protocol "
                        "or pass brain parameter to decorator"
                    )

            overridden_ai_provider, overridden_ai_model = target_brain.specification()
            if overridden_ai_provider == "bedrock":
                # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
                # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
                overridden_ai_provider, overridden_ai_model = target_brain.modified_specification(ai_provider="litellm")

            # Merge brain specification with all parameters
            call_params = {
                "provider": overridden_ai_provider,
                "model": overridden_ai_model,
                **llm_call_kwargs  # All parameters including response_model
            }

            @llm.call(**call_params)
            async def _llm_call():
                return await method(*args, **kwargs)

            return await _llm_call()
        return wrapper
    return decorator
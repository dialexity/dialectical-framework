from abc import ABC, abstractmethod
from typing import TypeVar, Callable, Any, Protocol, runtime_checkable
from functools import wraps

from mirascope import llm

from dialectical_framework.brain import Brain

T = TypeVar('T')

@runtime_checkable
class HasBrain(Protocol):
    @property
    @abstractmethod
    def brain(self) -> Brain: ...

def use_brain(**llm_call_kwargs):
    """
    Decorator factory for Mirascope that creates an LLM call using the brain's AI provider and model.
    
    Args:
        **llm_call_kwargs: All keyword arguments to pass to @llm.call, including response_model
        
    Returns:
        A decorator that wraps methods to make LLM calls
    """
    def decorator(method: Callable[..., Any]) -> Callable[..., T]:
        @wraps(method)
        async def wrapper(self, *args, **kwargs) -> T:
            if isinstance(self, HasBrain):
                brain = self.brain
            else:
                raise TypeError(
                    f"{self.__class__.__name__} must implement {HasBrain.__class__.__name__} protocol"
                )

            overridden_ai_provider, overridden_ai_model = brain.specification()
            if overridden_ai_provider == "bedrock":
                # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
                # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
                overridden_ai_provider, overridden_ai_model = brain.modified_specification(ai_provider="litellm")

            # Merge brain specification with all parameters
            call_params = {
                "provider": overridden_ai_provider,
                "model": overridden_ai_model,
                **llm_call_kwargs  # All parameters including response_model
            }

            @llm.call(**call_params)
            async def _llm_call():  # Make this async
                return await method(self, *args, **kwargs)  # Add await here

            return await _llm_call()  # Add await here
        return wrapper
    return decorator
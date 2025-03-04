from typing import cast

from dotenv import load_dotenv
from mirascope import llm
from pydantic import BaseModel

# Load environment variables
load_dotenv()


class LLMResponse(BaseModel):
    message: str


def dynamic_llm_call(provider: str, model: str, prompt: str) -> LLMResponse:
    """
    Dynamically call the LLM with the given provider, model, and prompt.
    """

    @llm.call(provider=provider, model=model, response_model=LLMResponse)
    def dynamic_ping() -> str:
        return prompt

    # Call the dynamically created function
    return cast(LLMResponse, dynamic_ping())


def test_llm_model_connection():
    provider_models = {
        "litellm": ["azure/gpt-4o", "anthropic/claude-3-5-haiku-latest"],
        "anthropic": ["claude-3-5-haiku-latest"],
    }
    for provider, models in provider_models.items():
        for model in models:
            response = dynamic_llm_call(
                provider, model, f"Say 'Hello, this is a test from {provider} {model}'."
            )
            assert response is not None
            print(f"\n{response.message}")

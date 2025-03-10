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
    response = dynamic_ping()
    assert isinstance(response, LLMResponse)
    return response


def test_llm_model_connection():
    provider_models = {
        "litellm": [
            "azure/gpt-4o",
            "anthropic/claude-3-5-haiku-latest",
            "bedrock/us.anthropic.claude-3-5-sonnet-20241022-v2:0"
        ],
        "anthropic": ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"],
        "bedrock": ["us.anthropic.claude-3-5-sonnet-20241022-v2:0"],
        # "bedrock": ["us.anthropic.claude-3-7-sonnet-20250219-v1:0"],
    }
    for provider, models in provider_models.items():
        for model in models:
            response = dynamic_llm_call(
                provider, model, f"Say 'Hello, this is a test from {provider} {model}'."
            )
            print(f"\n{response.message}")

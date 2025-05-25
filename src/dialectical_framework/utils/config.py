import os

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    # Default settings
    MODEL = os.getenv("DIALEXITY_DEFAULT_MODEL", None)
    PROVIDER = os.getenv("DIALEXITY_DEFAULT_MODEL_PROVIDER", None)

    @classmethod
    def validate(cls):
        missing = []
        if not cls.MODEL:
            missing.append('DIALEXITY_DEFAULT_MODEL')
        if not cls.PROVIDER:
            if "/" not in cls.MODEL:
                missing.append('DIALEXITY_DEFAULT_MODEL_PROVIDER')
            else:
                # We will give litellm a chance to derive the provider from the model
                pass
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    # Default settings
    PROVIDER = os.getenv("DEFAULT_MODEL_PROVIDER", None)
    MODEL = os.getenv("DEFAULT_MODEL", None)

if __name__ == "__main__":
    print(f"You are using: provider={Config.PROVIDER}, model={Config.MODEL}")

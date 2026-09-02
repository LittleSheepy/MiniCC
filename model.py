#!/usr/bin/env python3
import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv("D:/00sheepy/.env")

if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ["MODEL_ID"]
# FALLBACK_MODEL = os.getenv("FALLBACK_MODEL_ID")
FALLBACK_MODEL = os.getenv("MODEL_ID")
PRIMARY_MODEL = MODEL

if __name__ == "__main__":
    response = client.messages.create(model=MODEL, messages=[{"role": "user", "content": "你好"}], max_tokens=8000)
    print(response)
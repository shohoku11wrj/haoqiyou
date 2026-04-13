"""Utility helpers for interacting with the Google Gemini API."""

from __future__ import annotations

import time
from typing import Any, Dict

import google.generativeai as genai


DEFAULT_MODEL = "gemini-pro"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF = 1.5

SYSTEM_PROMPT = (
    "You are a browsing assistant that can fetch live webpages when requested. "
    "When presenting results, follow the user's requested response format exactly."
)


class GeminiClientError(RuntimeError):
    """Raised when the Gemini API request fails."""


def call_gemini_api(
    api_key: str,
    prompt_request: str,
    prompt_response: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF,
) -> str:
    """Call the Gemini API and return the assistant's content string."""

    if not api_key:
        raise ValueError("api_key must be provided")

    genai.configure(api_key=api_key)

    generation_config = {
        "temperature": temperature,
    }

    model = genai.GenerativeModel(
        model_name=model,
        generation_config=generation_config,
        system_instruction=SYSTEM_PROMPT,
    )

    prompt_parts = [
        f"{prompt_request.strip()} {prompt_response.strip()}",
    ]

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = model.generate_content(prompt_parts, request_options={"timeout": timeout})
            return response.text
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                raise GeminiClientError(
                    "Timed out while calling the Gemini API. "
                    "This could indicate an invalid API key, network issues, or that the API is "
                    "experiencing high latency. Please check your API key, network connection, "
                    "and try again in a moment."
                ) from exc
            sleep_seconds = backoff_factor * (attempt + 1)
            time.sleep(sleep_seconds)

    raise GeminiClientError(
        "Unable to contact the Gemini API due to repeated network errors."
    ) from last_error

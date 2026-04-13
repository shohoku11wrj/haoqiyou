"""Utility helpers for interacting with the OpenAI GPT chat completions API."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests
from requests import exceptions as requests_exceptions


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT = 60
DEFAULT_RETRIES = 2
DEFAULT_BACKOFF = 1.5

SYSTEM_PROMPT = (
    "You are a browsing assistant that can fetch live webpages when requested. "
    "When presenting results, follow the user's requested response format exactly."
)


class GPTClientError(RuntimeError):
    """Raised when the GPT API request fails."""


def call_gpt_api(
    api_key: str,
    prompt_request: str,
    prompt_response: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    stream: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    backoff_factor: float = DEFAULT_BACKOFF,
) -> str:
    """Call the OpenAI GPT API and return the assistant's content string."""

    if not api_key:
        raise ValueError("api_key must be provided")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{prompt_request.strip()} {prompt_response.strip()}",
        },
    ]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": stream,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response: Optional[requests.Response] = None
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                OPENAI_CHAT_COMPLETIONS_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            break
        except (requests_exceptions.Timeout, requests_exceptions.ConnectionError) as exc:
            last_error = exc
            if attempt >= retries:
                raise GPTClientError(
                    "Timed out while calling the GPT API. Please try again in a moment."
                ) from exc
            sleep_seconds = backoff_factor * (attempt + 1)
            time.sleep(sleep_seconds)
        except requests_exceptions.RequestException as exc:
            raise GPTClientError(f"Error calling the GPT API: {exc}") from exc
    else:  # pragma: no cover - defensive, should not reach
        raise GPTClientError(
            "Unable to contact the GPT API due to repeated network errors."
        ) from last_error

    if response is None:
        raise GPTClientError("No response received from the GPT API.")

    if response.status_code != 200:
        raise GPTClientError(
            f"GPT API request failed with status {response.status_code}: {response.text}"
        )

    data = response.json()
    choices = data.get("choices")
    if not choices:
        raise GPTClientError("GPT API response does not contain choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise GPTClientError("GPT API response choice is missing content")

    return content


from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from typing import Any

from enablement_studio.call import generate_call
from enablement_studio.critic import generate_critic
from enablement_studio.guards import apply_llm_guards
from enablement_studio.models import (
    EngineName,
    Product,
    ProductOutput,
    call_from_dict,
    critic_from_dict,
    role_from_dict,
)
from enablement_studio.prompts import system_prompt
from enablement_studio.role import generate_role

LLM_KEY_ENV = "ENABLEMENT_LLM_API_KEY"
LLM_BASE_ENV = "ENABLEMENT_LLM_BASE_URL"
LLM_MODEL_ENV = "ENABLEMENT_LLM_MODEL"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
LLM_TIMEOUT_SECONDS = 20


def llm_configured() -> bool:
    return bool(os.environ.get(LLM_KEY_ENV) or os.environ.get("OPENAI_API_KEY"))


def llm_endpoint() -> str:
    base = os.environ.get(LLM_BASE_ENV, DEFAULT_BASE_URL).rstrip("/")
    return f"{base}/chat/completions"


def llm_chat_body(product: Product, text: str) -> dict[str, Any]:
    model = os.environ.get(LLM_MODEL_ENV, DEFAULT_MODEL)
    return {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt(product)},
            {"role": "user", "content": f"product={product.value}\n\n{text}"},
        ],
    }


def generate(product: Product, text: str) -> tuple[ProductOutput, EngineName]:
    offline = _offline(product, text)
    if not llm_configured():
        return offline, EngineName.OFFLINE
    try:
        payload = _llm_json(product, text)
        output = _from_llm(product, payload)
        guarded = apply_llm_guards(product, output, text)
        if guarded is None:
            return offline, EngineName.OFFLINE
        return guarded, EngineName.LLM
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        urllib.error.URLError,
        json.JSONDecodeError,
        TimeoutError,
        http.client.IncompleteRead,
    ):
        return offline, EngineName.OFFLINE


def _offline(product: Product, text: str) -> ProductOutput:
    match product:
        case Product.ROLE:
            return generate_role(text)
        case Product.CALL:
            return generate_call(text)
        case Product.CRITIC:
            return generate_critic(text)
        case _:
            never: Product = product
            raise ValueError(f"unsupported product: {never}")


def _llm_json(product: Product, text: str) -> dict[str, Any]:
    api_key = os.environ.get(LLM_KEY_ENV) or os.environ.get("OPENAI_API_KEY") or ""
    body = json.dumps(llm_chat_body(product, text)).encode("utf-8")
    request = urllib.request.Request(
        llm_endpoint(),
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
        raw = json.loads(response.read().decode("utf-8"))
    choices = raw.get("choices") or []
    if not choices:
        raise ValueError("LLM response had no choices")
    content = choices[0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not an object")
    return parsed


def _from_llm(product: Product, payload: dict[str, Any]) -> ProductOutput:
    match product:
        case Product.ROLE:
            return role_from_dict(payload)
        case Product.CALL:
            return call_from_dict(payload)
        case Product.CRITIC:
            return critic_from_dict(payload)
        case _:
            never: Product = product
            raise ValueError(f"unsupported product: {never}")

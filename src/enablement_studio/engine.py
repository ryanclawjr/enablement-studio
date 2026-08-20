from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from enablement_studio.call import generate_call
from enablement_studio.critic import generate_critic
from enablement_studio.models import (
    EngineName,
    Product,
    ProductOutput,
    RoleEnablement,
    call_from_dict,
    critic_from_dict,
    role_from_dict,
)
from enablement_studio.role import apply_title_swap_validity, generate_role

LLM_KEY_ENV = "ENABLEMENT_LLM_API_KEY"
LLM_BASE_ENV = "ENABLEMENT_LLM_BASE_URL"
LLM_MODEL_ENV = "ENABLEMENT_LLM_MODEL"


def llm_configured() -> bool:
    return bool(os.environ.get(LLM_KEY_ENV) or os.environ.get("OPENAI_API_KEY"))


def generate(product: Product, text: str) -> tuple[ProductOutput, EngineName]:
    offline = _offline(product, text)
    if not llm_configured():
        return offline, EngineName.OFFLINE
    try:
        payload = _llm_json(product, text)
        output = _from_llm(product, payload)
        if isinstance(output, RoleEnablement):
            output = apply_title_swap_validity(output, text)
        return output, EngineName.LLM
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        urllib.error.URLError,
        json.JSONDecodeError,
        TimeoutError,
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
    base = os.environ.get(LLM_BASE_ENV, "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get(LLM_MODEL_ENV, "gpt-4.1-mini")
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only JSON for an instructional-design specialist. "
                        "Do not invent live employer metrics. Mark example_data true "
                        "if the source is labeled example or fictional. "
                        "For product=role, extract skills from this source. "
                        "Enablement, L&D, or coaching jobs are not seller modules."
                    ),
                },
                {
                    "role": "user",
                    "content": f"product={product.value}\n\n{text}",
                },
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = json.loads(response.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
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

"""
LLM inference client for the Octopus builtin agent.

Calls any OpenAI-compatible /chat/completions endpoint using the profile
bound to the `octopus_builtin` agent (via existing AgentApiBinding mechanism).

Falls back gracefully when no profile or API key is configured.
"""
from __future__ import annotations

from typing import Any

import httpx

from .api_profiles import resolve_profile_for_agent

OCTOPUS_BUILTIN_AGENT_ID = "octopus_builtin"

_NOT_CONFIGURED_MSG = (
    "章鱼 AI 尚未激活大语言模型。"
    "请前往「设置 → 模型」添加 API Profile 并绑定到章鱼 AI，即可开启真实推理。"
)


def get_octopus_profile():
    """Resolve the API profile bound to the built-in Octopus agent."""
    return resolve_profile_for_agent(OCTOPUS_BUILTIN_AGENT_ID)


def is_llm_configured() -> bool:
    """Return True if a profile with an API key is bound to octopus_builtin."""
    p = get_octopus_profile()
    return bool(p and p.api_key)


def call_llm(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 2048,
    temperature: float = 0.7,
) -> str:
    """
    Call the LLM using the profile bound to octopus_builtin.

    Returns the reply text.
    Raises RuntimeError with a user-readable message on failure.
    Raises LLMNotConfiguredError when no profile/key is available.
    """
    profile = get_octopus_profile()
    if not profile or not profile.api_key:
        raise LLMNotConfiguredError(_NOT_CONFIGURED_MSG)

    url = f"{profile.base_url}/chat/completions"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {profile.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": profile.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"LLM API 返回错误 {e.response.status_code}：{e.response.text[:400]}"
        ) from e
    except LLMNotConfiguredError:
        raise
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败：{e}") from e


class LLMNotConfiguredError(Exception):
    """Raised when no API profile / key is configured for octopus_builtin."""

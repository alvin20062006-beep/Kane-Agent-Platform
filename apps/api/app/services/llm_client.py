"""
LLM inference client for the Octopus builtin agent.

Calls any OpenAI-compatible /chat/completions endpoint using the profile
bound to the `octopus_builtin` agent (via existing AgentApiBinding mechanism).

Falls back gracefully when no profile or API key is configured.

Compatibility: many providers require ``temperature: 1`` for certain models;
others expect ``max_completion_tokens`` instead of ``max_tokens``. This module
uses a small ordered fallback chain so a fresh install works without manual
tuning.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..models import AgentApiProfile
from ..settings_env import get_llm_max_tokens
from .api_profiles import resolve_profile_for_agent

OCTOPUS_BUILTIN_AGENT_ID = "octopus_builtin"

# Must stay 1.0 for models that reject any other value (incl. many
# reasoning-style / vendor-proxied endpoints).
OCTOPUS_LLM_TEMPERATURE = 1.0

_NOT_CONFIGURED_MSG = (
    "章鱼 AI 尚未激活大语言模型。"
    "请前往「设置 → 模型」添加 API Profile 并绑定到章鱼 AI，即可开启真实推理。"
)


def get_octopus_profile():
    """Resolve the API profile bound to the built-in Octopus agent."""
    return resolve_profile_for_agent(OCTOPUS_BUILTIN_AGENT_ID)


def is_llm_configured() -> bool:
    """True if env or bound profile provides an API key for octopus_builtin."""
    if (os.getenv("OCTOPUS_LLM_API_KEY") or "").strip() or (os.getenv("LLM_API_KEY") or "").strip():
        return True
    p = get_octopus_profile()
    return bool(p and p.api_key and str(p.api_key).strip())


def resolve_llm_api_key(profile: AgentApiProfile | None) -> str | None:
    """
    Prefer environment (no disk); profile.api_key is legacy local fallback only.
    Never log or expose in API responses.
    """
    for name in ("OCTOPUS_LLM_API_KEY", "LLM_API_KEY"):
        v = os.getenv(name)
        if v and str(v).strip():
            return str(v).strip()
    if profile and profile.api_key and str(profile.api_key).strip():
        return str(profile.api_key).strip()
    return None


def _payload_variants(model: str, messages: list[dict[str, str]], max_tokens: int | None) -> list[dict[str, Any]]:
    """Bodies to try in order when the upstream returns a parameter-related 4xx."""
    core: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": OCTOPUS_LLM_TEMPERATURE,
    }
    if max_tokens is None:
        return [core]
    return [
        {**core, "max_tokens": max_tokens},
        {**core, "max_completion_tokens": max_tokens},
        core,
    ]


def _extract_message_content(data: dict[str, Any]) -> str:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        snippet = repr(data)[:500]
        raise RuntimeError(f"LLM 响应格式异常：{snippet}") from e


def call_llm(
    messages: list[dict[str, str]],
    *,
    max_tokens: int | None = None,
) -> str:
    """
    Call the LLM using the profile bound to octopus_builtin.

    API key: OCTOPUS_LLM_API_KEY / LLM_API_KEY first; else profile.api_key (local fallback).
    Output token cap: only if LLM_MAX_TOKENS / OCTOPUS_LLM_MAX_TOKENS set to a positive int;
    otherwise omit max_tokens (provider default).

    Temperature is fixed at 1.0 for provider compatibility; when capped, variants map
    ``max_tokens`` → ``max_completion_tokens`` → omit.

    Returns the reply text.
    Raises RuntimeError with a user-readable message on failure.
    Raises LLMNotConfiguredError when no profile/key is available.
    """
    profile = get_octopus_profile()
    api_key = resolve_llm_api_key(profile)
    if not api_key:
        raise LLMNotConfiguredError(_NOT_CONFIGURED_MSG)
    if not profile:
        raise LLMNotConfiguredError(
            "请在「设置 → 模型」绑定 API Profile（base_url / model）。"
            "API Key 建议使用环境变量 OCTOPUS_LLM_API_KEY 或 LLM_API_KEY。"
        )

    url = f"{profile.base_url}/chat/completions"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    mt = max_tokens if max_tokens is not None else get_llm_max_tokens()
    variants = _payload_variants(profile.model, messages, mt)
    last: httpx.Response | None = None

    try:
        with httpx.Client(timeout=90.0) as client:
            for payload in variants:
                r = client.post(url, json=payload, headers=headers)
                last = r
                if r.is_success:
                    return _extract_message_content(r.json())
                # Do not chain on auth / missing resource / rate limit.
                if r.status_code in (401, 403, 404, 429):
                    r.raise_for_status()
                if r.status_code >= 500:
                    r.raise_for_status()
                # 400 / 422: try next payload shape (token key, optional params).
                if r.status_code not in (400, 422):
                    r.raise_for_status()
            if last is not None:
                last.raise_for_status()
            raise RuntimeError("LLM 调用失败：无响应")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(
            f"LLM API 返回错误 {e.response.status_code}：{e.response.text[:400]}"
        ) from e
    except LLMNotConfiguredError:
        raise
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"LLM 调用失败：{e}") from e


class LLMNotConfiguredError(Exception):
    """Raised when no API profile / key is configured for octopus_builtin."""


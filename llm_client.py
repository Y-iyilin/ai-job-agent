import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

from prompts import SYSTEM_PROMPT


class LLMConfigError(RuntimeError):
    """Raised when required AI API configuration is missing."""


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise LLMConfigError(f"缺少环境变量 `{name}`。请在 `.env` 文件中配置后再运行。")
    return value


def load_ai_config() -> dict[str, str]:
    load_dotenv()
    return {
        "api_key": _get_required_env("AI_API_KEY"),
        "base_url": _get_required_env("AI_BASE_URL").rstrip("/"),
        "model": _get_required_env("AI_MODEL"),
        "fallback_models": os.getenv("AI_FALLBACK_MODELS", "").strip(),
        "timeout": os.getenv("AI_TIMEOUT_SECONDS", "120").strip(),
        "max_retries": os.getenv("AI_MAX_RETRIES", "2").strip(),
    }


def _extract_content(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"AI 接口返回格式异常：{data}") from exc

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("AI 接口返回了空内容。")
    return content.strip()


def _build_model_list(config: dict[str, str]) -> list[str]:
    models = [config["model"]]
    fallback_models = [
        item.strip()
        for item in config.get("fallback_models", "").split(",")
        if item.strip()
    ]
    for model in fallback_models:
        if model not in models:
            models.append(model)
    return models


def _as_positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def call_job_agent(user_prompt: str, config_override: dict[str, str] | None = None) -> str:
    config = config_override or load_ai_config()
    endpoint = f"{config['base_url']}/chat/completions"
    timeout = _as_positive_int(config.get("timeout", "120"), 120)
    max_retries = _as_positive_int(config.get("max_retries", "2"), 2)

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    errors = []
    for model in _build_model_list(config):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        }

        for attempt in range(1, max_retries + 1):
            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
                if response.status_code >= 400:
                    errors.append(f"{model} 第 {attempt} 次：HTTP {response.status_code}，{response.text[:300]}")
                    break
                return _extract_content(response.json())
            except requests.Timeout:
                errors.append(f"{model} 第 {attempt} 次：请求超时，超过 {timeout} 秒未返回")
            except requests.RequestException as exc:
                errors.append(f"{model} 第 {attempt} 次：网络请求异常，{exc}")

            if attempt < max_retries:
                time.sleep(1)

    raise RuntimeError("AI 接口调用失败，已尝试重试/备用模型：\n" + "\n".join(errors[-8:]))

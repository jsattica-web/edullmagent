"""select_model.py

OpenAI, vLLM, Ollama 세 플랫폼을 같은 인터페이스로 로드한다.

load_model(model_name, platform, **kwargs)는 create_agent에 그대로 넣을 수 있는
LangChain chat model(BaseChatModel)을 반환한다. 반환 타입이 세 플랫폼에서 동일하므로,
플랫폼을 바꿔도 create_agent, 미들웨어, MCP 코드는 손대지 않는다.

MCP 실습부터 이 모듈로 플랫폼을 고른다.
- 전반부(LLM API부터 MCP 심화까지)는 platform="openai".
- 오픈 모델 전환 실습 이후는 platform="vllm" 또는 "ollama"로 같은 코드를 재사용한다.

사용 예시
    from select_model import load_model

    # OpenAI (추가 인자는 모델 생성자로 그대로 전달된다)
    llm = load_model("gpt-5.2", platform="openai", reasoning_effort="low")

    # vLLM (모델명 생략 시 서버가 올린 모델을 자동 감지)
    llm = load_model(platform="vllm", base_url="http://localhost:8000/v1")

    # Ollama (128k 컨텍스트)
    llm = load_model("qwen3.6:latest", platform="ollama")

    from langchain.agents import create_agent
    agent = create_agent(llm, tools=tools)

API 키와 엔드포인트는 환경 파일(.env, env, environment 순으로 탐색)에서 읽는다.
필요한 키: OPENAI_API_KEY (openai). vLLM/Ollama 엔드포인트는 아래 환경 변수 또는
인자로 넘길 수 있으며, 없으면 로컬 기본값을 쓴다.
    VLLM_BASE_URL   (기본 http://localhost:8000/v1)
    VLLM_API_KEY    (기본 token-abc123, vLLM은 임의 문자열 허용)
    OLLAMA_BASE_URL (기본 http://localhost:11434)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# 환경 파일 탐색: 기존 노트북과 동일하게 .env를 우선한다.
for _candidate in (".env", "env", "environment"):
    if os.path.exists(_candidate):
        load_dotenv(_candidate, override=True)
        break

# vLLM과 Ollama는 128k 컨텍스트로 운영한다.
# vLLM은 serve 시 --max-model-len 131072, Ollama는 클라이언트의 num_ctx로 맞춘다.
CONTEXT_128K = 131072

DEFAULTS = {
    "openai": {"model": "gpt-5.2"},
    "vllm": {"base_url": "http://localhost:8000/v1", "api_key": "token-abc123"},
    "ollama": {"base_url": "http://localhost:11434", "num_ctx": CONTEXT_128K},
}


def load_model(model_name: str | None = None, platform: str = "openai", **kwargs):
    """플랫폼을 골라 LangChain chat model을 반환한다.

    Args:
        model_name: 모델 이름. vLLM은 생략 시 서버가 올린 첫 모델을 자동 감지한다.
        platform: "openai", "vllm", "ollama" 중 하나.
        **kwargs: 해당 chat model 생성자에 그대로 전달된다
            (temperature, max_tokens, base_url, api_key 등).

    Returns:
        BaseChatModel: create_agent에 그대로 넣을 수 있는 모델 객체.
    """
    platform = platform.lower()
    if platform in ("openai", "gpt"):
        return _load_openai(model_name, **kwargs)
    if platform == "vllm":
        return _load_vllm(model_name, **kwargs)
    if platform == "ollama":
        return _load_ollama(model_name, **kwargs)
    raise ValueError(
        f"지원하지 않는 platform: {platform!r} (openai, vllm, ollama 중 선택)"
    )


def _load_openai(model_name: str | None = None, **kwargs):
    from langchain.chat_models import init_chat_model

    model_name = model_name or DEFAULTS["openai"]["model"]
    return init_chat_model(model_name, model_provider="openai", **kwargs)


def _load_vllm(
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    enable_thinking: bool = False,
    **kwargs,
):
    base_url = base_url or os.environ.get("VLLM_BASE_URL", DEFAULTS["vllm"]["base_url"])
    api_key = api_key or os.environ.get("VLLM_API_KEY", DEFAULTS["vllm"]["api_key"])
    model_name = model_name or _first_served_model(base_url, api_key)

    # vLLM의 --reasoning-parser qwen3는 thinking을 reasoning 필드로 분리한다.
    # 이 필드를 살리려면 ChatOpenAIWithReasoning을 쓰고, 없으면 표준 ChatOpenAI로 폴백한다.
    try:
        from chat_openai_with_reasoning import ChatOpenAIWithReasoning

        return ChatOpenAIWithReasoning(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            enable_thinking=enable_thinking,
            **kwargs,
        )
    except ImportError:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(base_url=base_url, api_key=api_key, model=model_name, **kwargs)


def _load_ollama(
    model_name: str | None = None,
    base_url: str | None = None,
    num_ctx: int | None = None,
    **kwargs,
):
    from langchain_ollama import ChatOllama

    if not model_name:
        raise ValueError("ollama는 model_name이 필요하다 (예: 'qwen3.6:latest').")
    base_url = base_url or os.environ.get(
        "OLLAMA_BASE_URL", DEFAULTS["ollama"]["base_url"]
    )
    num_ctx = num_ctx or DEFAULTS["ollama"]["num_ctx"]
    return ChatOllama(model=model_name, base_url=base_url, num_ctx=num_ctx, **kwargs)


def _first_served_model(base_url: str, api_key: str) -> str:
    """vLLM 서버가 올린 첫 모델 id를 반환한다."""
    from openai import OpenAI

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client.models.list().data[0].id

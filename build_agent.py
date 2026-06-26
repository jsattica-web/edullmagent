"""build_agent.py

에이전트를 한 곳에서 조립하는 팩토리입니다. 모델은 select_model로 고르고,
표준 도구(tools.py)에 MCP 서버 도구를 더해 에이전트를 만듭니다. 

MCP 도구는 await로 처리해야 하므로 build_agent는 async 함수로 정의합니다. 
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from select_model import load_model
from tools import DEFAULT_TOOLS

DEFAULT_SYSTEM_PROMPT = (
    '당신은 유용한 AI 어시스턴트입니다. '
    '필요하면 도구를 사용하고, 도구를 실행하기 전 중간 과정을 간략히 설명하세요.'
)

# build_agent가 직접 연결하는 MCP 서버. 서버가 실행 중이어야 도구가 로드됩니다.
MCP_SERVERS = {
    'demo': {'transport': 'streamable_http', 'url': 'http://localhost:8090/mcp'},
}


async def load_mcp_tools(servers=None):
    """MCP 서버에서 도구를 받아옵니다. 연결에 실패하면 빈 목록을 돌려줍니다."""
    servers = MCP_SERVERS if servers is None else servers
    if not servers:
        return []
    try:
        client = MultiServerMCPClient(servers)
        return await client.get_tools()
    except Exception as e:
        print(f'[build_agent] MCP 도구 로드 실패, 표준 도구만 사용합니다: {e}')
        return []


async def build_agent(
    model_name=None,
    platform='openai',
    model=None,
    tools=None,
    system_prompt=None,
    checkpointer=None,
    mcp_servers=None,
    **model_kwargs,
):
    """현재까지 구성된 에이전트를 만들어 반환합니다.

    Args:
        model_name: 모델 이름. select_model.load_model로 전달됩니다.
        platform: 'openai' | 'vllm' | 'ollama'. load_model로 전달됩니다.
        model: 이미 만든 chat model. 주면 model_name/platform을 무시합니다.
        tools: 도구 목록. 생략 시 tools.py의 DEFAULT_TOOLS을 사용합니다.
        system_prompt: 시스템 프롬프트. 생략 시 기본값을 씁니다.
        checkpointer: 멀티턴 대화를 위한 체크포인터.
        mcp_servers: 연결할 MCP 서버 설정. 기본값은 MCP_SERVERS, {}면 MCP를 사용하지 않습니다.
        **model_kwargs: load_model로 전달되는 추가 인자 (reasoning_effort 등).
    """
    if model is None:
        model = load_model(model_name, platform=platform, **model_kwargs)
    base_tools = list(DEFAULT_TOOLS) if tools is None else list(tools)
    mcp_tools = await load_mcp_tools(mcp_servers)
    if system_prompt is None:
        system_prompt = DEFAULT_SYSTEM_PROMPT
    return create_agent(
        model,
        tools=base_tools + mcp_tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )

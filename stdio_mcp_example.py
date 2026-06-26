"""
MCP STDIO 클라이언트 (langchain_mcp_adapters 기반)

weather_server.py에 STDIO 방식으로 연결하여
에이전트를 구성하고 도구를 호출합니다.
"""

import asyncio
import sys
import os

from dotenv import load_dotenv

load_dotenv(".env", override=True)

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from select_model import load_model

PLATFORM = "openai"

# .venv의 python 경로 (Windows에서는 Scripts\\python.exe, macOS/Linux에서는 bin/python)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.platform == "win32":
    PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
else:
    PYTHON = os.path.join(BASE_DIR, ".venv", "bin", "python")

async def main():
    # STDIO 방식으로 MCP 서버 연결
    client = MultiServerMCPClient(
        {
            "weather": {
                "command": PYTHON,
                "args": [os.path.join(BASE_DIR, "weather_server.py")],
                "transport": "stdio",
            },
        }
    )

    # MCP 도구 로드
    tools = await client.get_tools()
    print(f"로드된 도구 수: {len(tools)}")
    for t in tools:
        print(f"  - {t.name}: {t.description}")

    # 에이전트 생성
    model = load_model("gpt-5.2" if PLATFORM == "openai" else None, platform=PLATFORM)
    agent = create_agent(
        model,
        tools=tools,
        system_prompt="중간 과정을 매번 간략히 설명하세요.",
    )


    # Weather 도구 테스트
    print("\n--- Weather 도구 테스트 ---")
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "캘리포니아(CA)의 현재 기상 경보를 확인해줘."}]}
    )
    print(result["messages"][-1].text)


if __name__ == "__main__":
    asyncio.run(main())

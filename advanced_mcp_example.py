"""
Playwright MCP를 stateful 세션으로 사용하는 예제.
- client.session() 컨텍스트로 모든 도구가 동일한 ClientSession을 공유
- 이렇게 하면 navigate -> snapshot 사이에 브라우저 상태가 유지됨
"""

import asyncio
import sys
import os

from dotenv import load_dotenv
from stream_utils import stream_print

load_dotenv(".env", override=True)

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools   # ← 추가
from langchain.agents import create_agent

# .venv의 python 경로 (Windows에서는 Scripts\\python.exe, macOS/Linux에서는 bin/python)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.platform == "win32":
    PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
else:
    PYTHON = os.path.join(BASE_DIR, ".venv", "bin", "python")


async def main():
    # STDIO 방식으로 MCP 서버 연결
    client = MultiServerMCPClient({
        "playwright": {
            "transport": "stdio",
            "command": "npx",
            "args": ["@playwright/mcp@latest", "--headless"],
            # headless : 실제 브라우저 창을 열지 않음
        }
    })

    # 명시적 세션 컨텍스트.
    # 기본 client.get_tools()는 호출마다 새 세션을 만들어 stateful 서버에서 상태가 유실
    # 아래 패턴은 한 세션을 열고 그 안에서 도구를 로드 -> 모든 도구 호출이 같은 세션을 공유
    async with client.session("playwright") as session:
        # 같은 세션에 바인딩된 도구 로드
        tools = await load_mcp_tools(session)

        print(f"로드된 도구 수: {len(tools)}")
        for t in tools:
            print(f"  - {t.name}: {t.description}")

        agent = create_agent(
            "gpt-5.2",
            tools=tools,
            system_prompt="도구를 사용할 때마다, 중간 과정을 매번 간략히 설명하세요.",
        )

        question = "https://sudoremove.com/news/ 에 접속해서, 가장 최신 날짜 뉴스 내용 설명해줘"


        result = await stream_print(agent, question)


if __name__ == "__main__":
    asyncio.run(main())

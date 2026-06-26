"""LangGraph 에이전트/워크플로우 스트리밍 유틸리티.

astream_events(v2) 기반으로 안정적인 진행 상황 스트리밍을 제공합니다.

용도별 헬퍼:
    - stream_print / stream_with_markdown : create_agent 류의 messages-기반 에이전트
    - stream_workflow                     : 임의 state schema의 StateGraph 워크플로우

사용법:
    from stream_utils import stream_print, stream_with_markdown, stream_workflow

    # Agent (messages 입력)
    await stream_print(agent, "서울 날씨 알려줘")
    await stream_with_markdown(agent, "서울과 부산 날씨 비교해줘")

    # Workflow (도메인 state 입력)
    await stream_workflow(router_graph, {"query": "..."})
    await stream_workflow(mapreduce_graph, {"topic": "..."}, show_tokens=True)
"""

import os

# aiohttp가 Windows 인증서 저장소를 참조하지 않아 SSL 오류가 발생하는 문제 우회
if not os.environ.get("SSL_CERT_FILE"):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass

from langchain_core.messages import HumanMessage

try:
    # HITL 노트북에서 graph 재개 시 사용. 미설치 환경(예: 02 노트북 직후)에서도
    # import 실패로 모듈 자체가 깨지지 않도록 가드한다.
    from langgraph.types import Command as _LGCommand
except ImportError:  # pragma: no cover
    _LGCommand = None


def _normalize_input(user_message):
    """str / HumanMessage / 메시지 리스트 / Command 를 에이전트 입력 형태로 정규화합니다."""
    if _LGCommand is not None and isinstance(user_message, _LGCommand):
        # Command(resume=...) 등은 그래프가 직접 해석하므로 그대로 통과.
        return user_message
    if isinstance(user_message, str):
        return {"messages": [{"role": "user", "content": user_message}]}
    if isinstance(user_message, HumanMessage):
        return {"messages": [user_message]}
    if isinstance(user_message, list):
        return {"messages": user_message}
    if isinstance(user_message, dict) and "messages" in user_message:
        return user_message
    if isinstance(user_message, dict) and "role" in user_message and "content" in user_message:
        return {"messages": [user_message]}
    raise TypeError(
        f"지원하지 않는 입력 타입: {type(user_message)}. "
        "str, HumanMessage, 메시지 리스트, dict, 또는 Command 를 사용하세요."
    )


def _chunk_text(content):
    """AIMessageChunk.content를 표시용 텍스트로 정규화한다.

    OpenAI Responses API의 native 도구(image_generation 등)를 bind_tools 한 모델은
    chunk.content 가 멀티블록 list 형태로 들어온다 (예: [{"type":"image_generation_call",
    "result":"<base64>"}]). 토큰 스트림에는 'text' 블록만 노출하고 비텍스트 블록은 무시한다.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return "".join(parts)
    return ""


def _extract_interrupt(event):
    """on_chain_stream / on_chain_end 이벤트에서 __interrupt__ 페이로드를 추출.

    LangGraph 는 노드가 interrupt() 를 호출하면 chunk 또는 output dict 안에
    `__interrupt__` 키로 Interrupt 객체 튜플을 실어 보낸다. 토큰 스트림과 별개
    이벤트라서 on_chat_model_stream 핸들러에는 잡히지 않는다.
    """
    data = event.get("data") or {}
    for slot in ("chunk", "output"):
        payload = data.get(slot)
        if isinstance(payload, dict) and "__interrupt__" in payload:
            return payload["__interrupt__"]
    return None


def _tool_args(event):
    """on_tool_start 이벤트에서 표시용 도구 인자만 추린다.

    create_agent가 도구에 주입하는 runtime 같은 내부 인자는 출력에서 제외한다.
    """
    data = event.get("data") or {}
    args = data.get("input", data) if isinstance(data, dict) else data
    if isinstance(args, dict):
        return {k: v for k, v in args.items() if k != "runtime"}
    return args


def _tool_result_text(event):
    """on_tool_end 이벤트에서 도구 결과 텍스트를 추출한다.

    data는 {"output": ToolMessage} 형태이고, MCP 도구의 content는 텍스트 블록
    리스트일 수 있으므로 텍스트만 정규화한다.
    """
    data = event.get("data") or {}
    output = data.get("output", data) if isinstance(data, dict) else data
    content = output.content if hasattr(output, "content") else output
    if isinstance(content, (str, list)):
        text = _chunk_text(content)
        if text:
            return text
    return content if isinstance(content, str) else str(content)


async def stream_print(agent, user_message, *, max_tool_result=200, verbose=False, **kwargs):
    """에이전트 응답을 토큰 단위로 print 출력합니다.

    Args:
        max_tool_result: Tool 결과 출력 최대 글자수 (기본 200). verbose=True이면 무시됨.
        verbose: True이면 Tool 결과를 잘라내지 않고 전체 출력.

    Returns:
        str: 수집된 LLM 응답 텍스트
    """
    agent_input = _normalize_input(user_message)
    collected = ""

    async for event in agent.astream_events(agent_input, version="v2", **kwargs):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            content = _chunk_text(event["data"]["chunk"].content)
            if content:
                collected += content
                print(content, end="", flush=True)

        elif kind == "on_tool_start":
            print(f"\n🔧 Tool 호출: {event['name']}  {_tool_args(event)}")

        elif kind == "on_tool_end":
            result = _tool_result_text(event)
            print(f"✅ Tool 결과: {result if verbose else result[:max_tool_result]}")

        elif kind in ("on_chain_stream", "on_chain_end"):
            interrupts = _extract_interrupt(event)
            if interrupts:
                for intr in interrupts:
                    val = getattr(intr, "value", intr)
                    print(f"\n⏸️  INTERRUPT: {val}")

    print()
    return collected


async def stream_with_markdown(agent, user_message, *, max_tool_result=200, verbose=False, **kwargs):
    """에이전트 응답을 Jupyter에서 마크다운으로 실시간 렌더링합니다.

    clear_output + display(Markdown(...))로 ChatGPT/Claude 웹과 유사한 UX를 구현합니다.

    Args:
        max_tool_result: Tool 결과 출력 최대 글자수 (기본 200). verbose=True이면 무시됨.
        verbose: True이면 Tool 결과를 잘라내지 않고 전체 출력.

    Returns:
        str: 수집된 LLM 응답 텍스트
    """
    from IPython.display import display, Markdown, clear_output

    agent_input = _normalize_input(user_message)
    all_text = ""     # 반환용 전체 텍스트
    collected = ""    # 현재 LLM 구간의 텍스트 (도구 호출 시 리셋)
    tool_logs = ""    # 누적 로그 (이전 텍스트 + 도구 로그가 시간순으로 쌓임)

    async for event in agent.astream_events(agent_input, version="v2", **kwargs):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = _chunk_text(event["data"]["chunk"].content)
            if chunk:
                collected += chunk
                all_text += chunk
                clear_output(wait=True)
                if tool_logs:
                    display(Markdown(tool_logs + "\n---\n" + collected))
                else:
                    display(Markdown(collected))

        elif kind == "on_tool_start":
            # 도구 호출 전까지의 텍스트를 로그에 합류시켜 순서를 보존
            if collected:
                tool_logs += collected + "\n\n"
                collected = ""
            tool_logs += f"🔧 Tool 호출: `{event['name']}` (인자: `{_tool_args(event)}`)\n\n"
            clear_output(wait=True)
            display(Markdown(tool_logs + "\n도구 실행 중..."))

        elif kind == "on_tool_end":
            result = _tool_result_text(event)
            display_result = result if verbose else result[:max_tool_result]
            tool_logs += f"✅ 결과: {display_result}\n\n"

        elif kind in ("on_chain_stream", "on_chain_end"):
            interrupts = _extract_interrupt(event)
            if interrupts:
                # 진행 중이던 토큰 텍스트를 먼저 로그로 합류시켜 시간순 보존
                if collected:
                    tool_logs += collected + "\n\n"
                    collected = ""
                for intr in interrupts:
                    val = getattr(intr, "value", intr)
                    tool_logs += f"⏸️ INTERRUPT: `{val}`\n\n"
                clear_output(wait=True)
                display(Markdown(tool_logs + "\n사람의 응답 대기 중입니다. `Command(resume=...)` 으로 재개하세요."))

    return all_text


def _short_value(v, limit=80):
    """state 값의 짧은 미리보기 문자열을 반환합니다."""
    if isinstance(v, str):
        s = v.replace("\n", " ")
        return f'"{s[:limit]}..."' if len(s) > limit else f'"{s}"'
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"dict({list(v)})"
    cls = type(v).__name__
    label = getattr(v, "title", None) or getattr(v, "name", None)
    return f"<{cls}{f' {label}' if label else ''}>"


async def stream_workflow(graph, state, *, show_tokens=False, max_tool_result=200, **kwargs):
    """LangGraph StateGraph 워크플로우의 노드 단위 진행 상황을 스트리밍 출력합니다.

    Agent용 stream_print/stream_with_markdown과 달리 messages 형태를 강제하지 않고,
    그래프의 state schema에 맞는 dict를 그대로 받습니다 (예: {"topic": "..."}).

    출력 형식:
        ▶ [노드명]            노드 시작
           ↳ key=value, ...   노드가 반환한 state 갱신분
        🔧 / ✅                도구 호출/결과 (있을 때만)
        (옵션) LLM 토큰 흐름   show_tokens=True일 때

    Args:
        graph: 컴파일된 StateGraph
        state: 그래프 입력 dict (예: {"query": "..."}, {"topic": "..."}, {"messages": [...]})
        show_tokens: True면 노드 내부 LLM 토큰을 실시간 출력 (Fan-out에서는 인터리브 주의)
        max_tool_result: 도구 결과 출력 최대 글자수
        **kwargs: astream_events 추가 인자 (예: config={"callbacks": [langfuse_handler]})

    Returns:
        dict | None: 최상위 그래프의 최종 state
    """
    node_names = set(graph.get_graph().nodes) - {"__start__", "__end__"}
    final_state = None

    async for ev in graph.astream_events(state, version="v2", **kwargs):
        kind = ev["event"]
        name = ev.get("name", "")

        # 최상위 그래프 종료 시 최종 state 캡처
        if kind == "on_chain_end" and not ev.get("parent_ids"):
            final_state = ev["data"].get("output")

        if kind == "on_chain_start" and name in node_names:
            print(f"\n▶ [{name}]")

        elif kind == "on_chain_end" and name in node_names:
            out = ev["data"].get("output")
            if isinstance(out, dict) and out:
                preview = ", ".join(f"{k}={_short_value(v)}" for k, v in out.items())
                print(f"   ↳ {preview}")

        elif kind == "on_chat_model_stream" and show_tokens:
            chunk = _chunk_text(ev["data"]["chunk"].content)
            if chunk:
                print(chunk, end="", flush=True)

        elif kind == "on_tool_start":
            print(f"\n  🔧 {ev['name']}({ev['data']})")

        elif kind == "on_tool_end":
            result = ev["data"]
            text = result.content if hasattr(result, "content") else str(result)
            print(f"\n  ✅ {text[:max_tool_result]}")

        elif kind in ("on_chain_stream", "on_chain_end"):
            interrupts = _extract_interrupt(ev)
            if interrupts:
                for intr in interrupts:
                    val = getattr(intr, "value", intr)
                    print(f"\n  ⏸️  INTERRUPT: {val}")

    return final_state

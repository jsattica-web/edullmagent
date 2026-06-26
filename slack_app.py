"""slack_app.py

build_agent로 만든 에이전트를 Slack에 올리는 배포 하네스입니다.
채널에서 봇을 @멘션하면 스레드를 열어 응답하고, 그 스레드 안에서는 멘션 없이도
대화가 이어집니다(멘션 없는 일반 채널 대화는 무시). 응답은 astream_events로 토큰과
도구 호출을 스레드에 점진 게시하고, generate_image로 만든 그림은 파일로 첨부합니다.
스레드 대화는 SQLite 체크포인터에 저장되어 봇을 껐다 켜도 이어집니다.

모델, 표준 도구, MCP 도구는 build_agent가 조립합니다. 이 파일은 그것들을 직접
알지 않으므로, build_agent.py가 갱신되면 이 봇도 같은 에이전트를 그대로 씁니다.

전제 조건:
  MCP 서버 설정은 mcp_servers.json에서 읽습니다. stateless 서버(tavily, slack,
  image)는 build_agent가 로드하고, stateful 서버(Playwright)는 이 봇이 세션으로
  유지합니다. 서버가 떠 있지 않으면 그 도구만 빠지고 나머지로 동작합니다.
  Playwright는 stdio로 npx가 자체 실행하며, 브라우저(Chrome)가 있어야 합니다.

Slack 설정 (slack_setup.md 참고):
  Event Subscriptions에 message.channels(스레드 메시지 수신)와 app_mention을 구독하고,
  봇 스코프에 files:write(이미지 첨부)를 추가하세요.

필요한 환경변수 (.env):
  OPENAI_API_KEY
  SLACK_BOT_TOKEN   (xoxb-...)  Bot User OAuth Token
  SLACK_APP_TOKEN   (xapp-...)  App-Level Token (Socket Mode 활성화 필요)

추가 설치:
  pip install slack_bolt

실행:
  python slack_app.py             # = --mode compact (기본)
  python slack_app.py --mode 1    # AI 텍스트만
  python slack_app.py --mode 3    # 전체 풀 출력
"""

import argparse
import asyncio
import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env", override=True)

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from build_agent import build_agent
from mcp_config import load_servers

# 스레드 대화를 파일에 저장해 봇을 껐다 켜도 이어집니다. thread_id = slack_{thread_ts}.
CHECKPOINT_DB = "slack_threads.db"

# 승인 게이트(HITL)를 걸 도구. 키 = 도구 이름, 값 = True(approve/edit/reject 모두 허용).
# 외부로 나가거나 비가역적인 도구를 여기에 추가하세요. 봇이 그 도구를 호출하려 하면
# 실행 전에 멈추고 스레드에 [승인][거부] 버튼을 띄웁니다. 빈 dict면 게이트 없음.
#   예) "post_message": True   # Slack 게시(외부 발신) 전 승인
#       "delete_file": True    # 파일 삭제 전 승인
# 기본값은 항상 존재하는 save_note로 두어 데모가 바로 동작하게 합니다.
INTERRUPT_ON = {
    "save_note": True,
}


SLACK_SYSTEM_PROMPT = """당신은 Slack에서 동작하는 AI 어시스턴트입니다.

규칙:
  1) 항상 한국어로 응답하며, 도구를 사용할 때는 사용하기 전 중간 과정을 간략히 설명합니다.
  2) Slack 관련 도구를 호출할 때는 사용자 입력 앞에 주어진 [현재 Slack 컨텍스트]의
     채널 ID와 스레드 ts를 그대로 사용하세요. 채널을 추측해서 보내지 마세요.
  3) 도구를 여러 개 조합해도 됩니다. 검색 결과만으로 부족하면 브라우저 도구로 페이지를 열어 확인하세요.
  4) generate_image로 만든 그림은 시스템이 자동으로 이 스레드에 파일로 첨부합니다.
     사용자에게 직접 올리라고 안내하지 말고, 그림을 첨부했다고 자연스럽게 답하세요.
"""

# ─── 출력 모드 파싱 ─────────────────────────────────────────

MODE_ALIASES = {"1": "final", "2": "compact", "3": "verbose"}
VALID_MODES = ("final", "compact", "verbose")


def parse_args() -> str:
    p = argparse.ArgumentParser(
        prog="slack_app",
        description="build_agent 에이전트를 Slack에 올리는 봇 (스트리밍 응답)",
    )
    p.add_argument(
        "--mode", "-m",
        default="compact",
        choices=list(MODE_ALIASES.keys()) + list(VALID_MODES),
        help="출력 모드. 1/final = AI 텍스트만, 2/compact = AI + 도구 한 줄 요약 (기본), "
             "3/verbose = 전체 풀 출력",
    )
    args = p.parse_args()
    return MODE_ALIASES.get(args.mode, args.mode)


# ─── Slack 스트리밍 헬퍼 ─────────────────────────────────────

def _format_args_full(data, limit: int = 400) -> str:
    """on_tool_start의 event['data']를 코드블록 친화적으로 직렬화 (verbose)."""
    try:
        s = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        s = str(data)
    return s if len(s) <= limit else s[:limit] + "  …(생략)"


def _compact_args(data, limit: int = 120) -> str:
    """on_tool_start의 event['data']에서 args를 한 줄 key=value 요약 (compact)."""
    inp = data.get("input", data) if isinstance(data, dict) else data
    if isinstance(inp, dict):
        parts = []
        for k, v in inp.items():
            sv = repr(v) if isinstance(v, str) else str(v)
            sv = sv.replace("\n", " ")
            if len(sv) > 40:
                sv = sv[:40] + "…"
            parts.append(f"{k}={sv}")
        s = ", ".join(parts)
    else:
        s = str(inp).replace("\n", " ")
    return s if len(s) <= limit else s[:limit] + "…"


def _stringify_content(content) -> str:
    """ToolMessage.content가 str / content-block list / 그 외 형태로 와도 str로 정규화한다."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for blk in content:
            if isinstance(blk, dict):
                parts.append(blk.get("text") or blk.get("content") or json.dumps(blk, ensure_ascii=False, default=str))
            else:
                parts.append(str(blk))
        return "\n".join(parts)
    return str(content)


def _extract_tool_result(data) -> str:
    """on_tool_end의 event['data']에서 결과 텍스트만 추출 (항상 str 반환)."""
    if isinstance(data, dict) and "output" in data:
        out = data["output"]
        content = out.content if hasattr(out, "content") else out
    elif hasattr(data, "content"):
        content = data.content
    else:
        content = data
    return _stringify_content(content)


def _compact_result(text: str, limit: int = 140) -> str:
    """도구 결과를 한 줄로 압축 (compact)."""
    s = text.replace("\n", " ").strip()
    return s if len(s) <= limit else s[:limit] + "…"


# ─── 이미지 파일 업로드 ─────────────────────────────────────

_IMG_PATH_RE = re.compile(r"([^\s\"']+\.(?:png|jpg|jpeg|webp|gif))", re.IGNORECASE)


def _parse_image_path(result_text: str):
    """generate_image 결과 문자열에서 저장된 이미지 경로를 뽑습니다."""
    m = _IMG_PATH_RE.search(result_text or "")
    return m.group(1) if m else None


async def _upload_image(client, channel: str, thread_ts: str, path: str) -> bool:
    """생성된 이미지를 스레드에 파일로 첨부합니다. (files:write 스코프 필요)"""
    p = Path(path)
    if not p.exists():
        return False
    await client.files_upload_v2(
        channel=channel, thread_ts=thread_ts, file=str(p), title=p.name,
    )
    return True


class SlackStreamer:
    """astream_events 이벤트를 Slack 메시지로 점진 게시하는 헬퍼.

    하나의 활성 메시지 슬롯만 갱신한다. AI 토큰이 오면 그 메시지를 chat.update로
    토큰 단위 갱신(throttle 적용)하고, 도구 호출이 오면 진행 중 메시지를 확정한 뒤
    도구 메시지를 새로 게시한다. 다음 AI 토큰은 새 메시지를 시작해 시간순을 보존한다.

    출력 모드:
      - 'final'   : 도구 호출/결과 메시지를 Slack에 게시하지 않음.
      - 'compact' : 도구 호출/결과를 한 줄로 압축해서 게시 (기본).
      - 'verbose' : 도구 args/결과를 코드블록으로 풀 출력.
    """

    def __init__(self, web_client, channel: str, thread_ts: str, *,
                 mode: str = "compact",
                 min_update_interval: float = 1.0,
                 max_tool_result: int = 600):
        self.client = web_client
        self.channel = channel
        self.thread_ts = thread_ts
        self.mode = mode
        self.min_update_interval = min_update_interval
        self.max_tool_result = max_tool_result
        self._active_ts = None
        self._active_kind = None  # "placeholder" | "ai" | None
        self._active_text = ""
        self._last_update = 0.0

    async def _post(self, text: str) -> str:
        resp = await self.client.chat_postMessage(
            channel=self.channel, thread_ts=self.thread_ts,
            text=text or "_(빈 메시지)_",
        )
        return resp["ts"]

    async def _update(self, ts: str, text: str) -> None:
        try:
            await self.client.chat_update(
                channel=self.channel, ts=ts, text=text or "_(빈 메시지)_",
            )
        except Exception:
            # 레이트리밋/일시 오류: 다음 갱신이 따라잡으므로 조용히 무시.
            pass

    async def post_placeholder(self) -> None:
        self._active_ts = await self._post("_생각 중..._")
        self._active_kind = "placeholder"
        self._active_text = ""
        self._last_update = 0.0

    async def append_token(self, chunk: str) -> None:
        if self._active_kind == "ai":
            self._active_text += chunk
            now = time.monotonic()
            if now - self._last_update >= self.min_update_interval:
                await self._update(self._active_ts, self._active_text)
                self._last_update = now
            return

        # placeholder거나 활성 슬롯이 비어있음 → 새 AI 세그먼트 시작.
        self._active_text = chunk
        if self._active_ts is None:
            self._active_ts = await self._post(self._active_text)
        else:
            await self._update(self._active_ts, self._active_text)
        self._active_kind = "ai"
        self._last_update = time.monotonic()

    async def _finalize_active(self) -> None:
        """진행 중이던 메시지를 마지막 텍스트로 강제 동기화하고 슬롯을 비운다."""
        if self._active_ts and self._active_kind == "ai" and self._active_text:
            await self._update(self._active_ts, self._active_text)
        elif self._active_ts and self._active_kind == "placeholder":
            await self._update(self._active_ts, "_(응답 없음)_")
        self._active_ts = None
        self._active_kind = None
        self._active_text = ""

    def _format_tool_call(self, name: str, data) -> str:
        if self.mode == "verbose":
            return f"🔧 *Tool 호출*: `{name}`\n```\n{_format_args_full(data)}\n```"
        return f"🔧 `{name}` 호출 _({_compact_args(data)})_"

    def _format_tool_result(self, result_text: str) -> str:
        if self.mode == "verbose":
            truncated = (result_text if len(result_text) <= self.max_tool_result
                         else result_text[:self.max_tool_result] + "  …(생략)")
            return f"✅ *결과*\n```\n{truncated}\n```"
        return f"✅ _{_compact_result(result_text)}_"

    async def post_tool_call(self, name: str, data) -> None:
        if self.mode == "final":
            if self._active_kind == "ai":
                await self._finalize_active()
            return

        text = self._format_tool_call(name, data)
        if self._active_kind == "placeholder":
            await self._update(self._active_ts, text)
            self._active_ts = None
            self._active_kind = None
            self._active_text = ""
        else:
            await self._finalize_active()
            await self._post(text)

    async def post_tool_result(self, result_text: str) -> None:
        if self.mode == "final":
            return
        await self._post(self._format_tool_result(result_text))

    async def post_error(self, err_text: str) -> None:
        await self._finalize_active()
        await self._post(f"❌ 오류:\n```\n{err_text}\n```")

    async def close(self) -> None:
        """모든 이벤트 처리가 끝난 뒤 호출. 마지막 토큰까지 동기화 보장."""
        await self._finalize_active()


# ─── 봇 메인 ──────────────────────────────────────────────

async def main(mode: str):
    required = ["OPENAI_API_KEY", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        print(f"환경변수가 설정되지 않았습니다: {', '.join(missing)}")
        print("  .env 파일을 확인하세요.")
        sys.exit(1)

    stack = contextlib.AsyncExitStack()

    # 스레드 대화를 SQLite에 저장한다. 봇을 껐다 켜도 같은 스레드면 이어진다.
    checkpointer = await stack.enter_async_context(
        AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB)
    )
    await checkpointer.setup()

    # stateful MCP 서버(예: Playwright)는 봇 lifetime 동안 세션을 열어 유지하고,
    # 그 도구를 build_agent에 extra_tools로 넘긴다. 세션은 stack에 넣어 종료 시 닫는다.
    # 설정은 mcp_servers.json의 stateful 항목에서 읽고, 연결에 실패한 서버는 건너뛴다.
    extra_tools = []
    stateful_servers = load_servers(stateful=True)
    if stateful_servers:
        sclient = MultiServerMCPClient(stateful_servers)
        for name in stateful_servers:
            try:
                session = await stack.enter_async_context(sclient.session(name))
                tools = await load_mcp_tools(session)
                extra_tools += tools
                print(f"{name} 도구 {len(tools)}개 로드 (stateful 세션)")
            except Exception as e:
                print(f"{name} 연결 실패({type(e).__name__}: {e}). 건너뜁니다.")

    print(f"에이전트 빌드 중... (출력 모드: {mode})")
    hitl_middleware = (
        [HumanInTheLoopMiddleware(interrupt_on=INTERRUPT_ON)] if INTERRUPT_ON else []
    )
    agent = await build_agent(
        system_prompt=SLACK_SYSTEM_PROMPT,
        checkpointer=checkpointer,
        extra_tools=extra_tools,
        middleware=hitl_middleware,
    )

    app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])

    # 봇 자신의 user id. 멘션 판정과 루프 방지(봇 메시지 무시)에 쓴다.
    bot_user_id = (await app.client.auth_test())["user_id"]

    async def thread_is_active(thread_ts: str) -> bool:
        # 그 스레드에 이미 대화 기록(체크포인트)이 있으면 봇이 참여 중인 스레드다.
        cfg = {"configurable": {"thread_id": f"slack_{thread_ts}"}}
        return (await checkpointer.aget_tuple(cfg)) is not None

    # 스레드별 "이 세션 항상 승인" 도구 allow-list. 봇 실행 동안만 메모리에 유지된다
    # (봇을 재시작하면 비워져 다시 묻습니다). thread_ts -> {도구이름, ...}
    session_approvals: dict[str, set] = {}

    def _pending_tools(hitl_request):
        """HITL interrupt 값에서 (승인 대기 도구 이름 목록, 결정 개수)를 뽑는다."""
        reqs = hitl_request.get("action_requests", []) if isinstance(hitl_request, dict) else []
        return [r.get("name") for r in reqs], (len(reqs) or 1)

    @app.event("app_mention")
    async def absorb_app_mention(event):
        # 멘션은 message 이벤트로도 들어와 handle_message가 처리한다.
        # 여기서는 app_mention을 흡수만 해 중복 처리와 "Unhandled request" 경고를 막는다.
        pass

    async def run_agent_stream(client, channel, thread_ts, stream_input):
        """에이전트 실행을 Slack에 점진 게시하고, 끝나면 HITL 승인 대기 여부를 확인한다.

        stream_input 이 {"messages": [...]} 면 최초 실행, Command(resume=...) 면 승인 후 재개다.
        스트림이 끝났는데 그래프가 interrupt로 멈춰 있으면(=승인 대기) 승인 버튼을 게시한다.
        """
        config = {"configurable": {"thread_id": f"slack_{thread_ts}"}}
        streamer = SlackStreamer(client, channel, thread_ts, mode=mode)
        await streamer.post_placeholder()

        try:
            async for ev in agent.astream_events(
                stream_input, version="v2", config=config,
            ):
                kind = ev["event"]

                if kind == "on_chat_model_stream":
                    chunk = ev["data"]["chunk"].content
                    if chunk:
                        await streamer.append_token(chunk)

                elif kind == "on_tool_start":
                    await streamer.post_tool_call(ev["name"], ev["data"])

                elif kind == "on_tool_end":
                    result = _extract_tool_result(ev["data"])
                    await streamer.post_tool_result(result)
                    # generate_image 결과면 저장된 그림을 스레드에 파일로 첨부한다.
                    if ev["name"] == "generate_image":
                        path = _parse_image_path(result)
                        if path:
                            try:
                                await _upload_image(client, channel, thread_ts, path)
                            except Exception as e:
                                await streamer.post_error(
                                    f"이미지 업로드 실패: {type(e).__name__}: {e}"
                                )
        except Exception as e:
            await streamer.post_error(f"{type(e).__name__}: {e}")
            return
        finally:
            await streamer.close()

        # 스트림이 끝났는데 그래프가 멈춰 있으면 = HITL 승인 대기.
        snapshot = await agent.aget_state(config)
        pending = [i for t in snapshot.tasks for i in (getattr(t, "interrupts", None) or [])]
        if not pending:
            return
        hitl_request = pending[0].value
        tool_names, n = _pending_tools(hitl_request)

        # 이 세션에서 '항상 승인'한 도구만 호출되면 버튼 없이 자동 승인하고 이어간다.
        approved = session_approvals.get(thread_ts, set())
        if tool_names and all(name in approved for name in tool_names):
            with contextlib.suppress(Exception):
                await client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text="⏩ 이 세션 자동 승인: " + ", ".join(f"`{t}`" for t in tool_names),
                )
            await run_agent_stream(
                client, channel, thread_ts,
                Command(resume={"decisions": [{"type": "approve"} for _ in range(n)]}),
            )
            return

        await post_approval(client, channel, thread_ts, hitl_request)

    async def post_approval(client, channel, thread_ts, hitl_request):
        """HITL interrupt 정보를 [이번만 승인][이 세션 항상 승인][거절] 버튼과 함께 게시한다."""
        tool_names, n = _pending_tools(hitl_request)
        reqs = hitl_request.get("action_requests", []) if isinstance(hitl_request, dict) else []
        lines = []
        for r in reqs:
            args = json.dumps(r.get("args", {}), ensure_ascii=False)
            if len(args) > 300:
                args = args[:300] + "…"
            lines.append(f"• `{r.get('name')}` 인자: `{args}`")
        summary = "\n".join(lines) or "(상세 정보 없음)"
        # 버튼 클릭 시 어느 스레드를 재개할지 + 결정 개수(n) + 도구 이름을 value(JSON)로 넘긴다.
        value = json.dumps({"thread_ts": thread_ts, "n": n, "tools": tool_names})
        await client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text="도구 실행 승인이 필요합니다",
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": f"*⏸️ 도구 실행 승인이 필요합니다*\n{summary}"}},
                {"type": "actions", "block_id": "hitl_actions", "elements": [
                    {"type": "button", "action_id": "hitl_approve_once", "style": "primary",
                     "text": {"type": "plain_text", "text": "✅ 이번만 승인"}, "value": value},
                    {"type": "button", "action_id": "hitl_approve_session",
                     "text": {"type": "plain_text", "text": "♾️ 이 세션 항상 승인"}, "value": value},
                    {"type": "button", "action_id": "hitl_reject", "style": "danger",
                     "text": {"type": "plain_text", "text": "❌ 거절"}, "value": value},
                ]},
            ],
        )

    async def resume_from_button(body, client, *, kind):
        """버튼 클릭(once/session/reject)을 받아 같은 스레드의 그래프를 재개한다."""
        data = json.loads(body["actions"][0]["value"])
        thread_ts = data["thread_ts"]
        n = int(data.get("n", 1)) or 1
        tool_names = data.get("tools", []) or []
        channel = body["channel"]["id"]

        if kind == "session":
            # 이 스레드에서 해당 도구는 다음부터 묻지 않는다(자동 승인 등록).
            session_approvals.setdefault(thread_ts, set()).update(t for t in tool_names if t)
            tlist = ", ".join(f"`{t}`" for t in tool_names) or "이 도구"
            decided = f"♾️ 이 세션 항상 승인됨 ({tlist}) — 다음부터 묻지 않습니다."
            approve = True
        elif kind == "once":
            decided = "✅ 이번만 승인됨 — 실행을 계속합니다."
            approve = True
        else:  # reject
            decided = "❌ 거절됨 — 실행을 취소합니다."
            approve = False

        # 버튼 메시지를 결정 결과로 교체해 중복 클릭을 막는다.
        with contextlib.suppress(Exception):
            await client.chat_update(
                channel=channel, ts=body["message"]["ts"], text=decided,
                blocks=[{"type": "section",
                         "text": {"type": "mrkdwn", "text": f"*{decided}*"}}],
            )

        # 미들웨어는 중단된 도구 호출 수만큼 decisions를 요구한다(개수 불일치 시 에러).
        if approve:
            decisions = [{"type": "approve"} for _ in range(n)]
        else:
            decisions = [{"type": "reject", "message": "사용자가 도구 실행을 거절했습니다."}
                         for _ in range(n)]
        await run_agent_stream(
            client, channel, thread_ts, Command(resume={"decisions": decisions})
        )

    @app.action("hitl_approve_once")
    async def on_hitl_approve_once(ack, body, client):
        await ack()
        await resume_from_button(body, client, kind="once")

    @app.action("hitl_approve_session")
    async def on_hitl_approve_session(ack, body, client):
        await ack()
        await resume_from_button(body, client, kind="session")

    @app.action("hitl_reject")
    async def on_hitl_reject(ack, body, client):
        await ack()
        await resume_from_button(body, client, kind="reject")

    @app.event("message")
    async def handle_message(event, client):
        # 루프 방지: 봇 자신/다른 봇/서브타입(편집·파일첨부·입퇴장) 메시지는 무시한다.
        if event.get("bot_id") or event.get("subtype") or event.get("user") == bot_user_id:
            return

        text = event.get("text", "") or ""
        channel = event["channel"]
        thread_ts = event.get("thread_ts", event["ts"])

        # 멘션이면 스레드를 연다. 멘션이 없어도 봇이 이미 참여 중인 스레드면 이어간다.
        # 둘 다 아니면(멘션 없는 일반 채널 대화) 무시한다.
        mentioned = f"<@{bot_user_id}>" in text
        if not (mentioned or await thread_is_active(thread_ts)):
            return

        body = text.replace(f"<@{bot_user_id}>", "").strip()
        if not body:
            await client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text="무엇을 도와드릴까요?"
            )
            return

        # 이 스레드가 승인 대기 중이면, 새 입력 대신 버튼으로만 진행하도록 안내한다.
        config = {"configurable": {"thread_id": f"slack_{thread_ts}"}}
        snapshot = await agent.aget_state(config)
        if any(getattr(t, "interrupts", None) for t in snapshot.tasks):
            await client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text="위 승인 요청의 *승인* 또는 *거부* 버튼을 눌러 진행해주세요.",
            )
            return

        # 봇이 아는 채널/스레드 정보를 LLM 입력 앞에 붙여, Slack 도구 호출 시
        # 정확한 channel_id, thread_ts를 채우게 한다.
        context_block = (
            "[현재 Slack 컨텍스트]\n"
            f"채널 ID: {channel}\n"
            f"스레드 ts: {thread_ts}\n"
            "Slack 관련 도구를 호출할 때 이 값을 그대로 사용하세요.\n\n"
            "사용자 요청:\n"
            f"{body}"
        )

        await run_agent_stream(
            client, channel, thread_ts,
            {"messages": [{"role": "user", "content": context_block}]},
        )

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("Slack App 시작 (Ctrl+C 로 종료)")
    try:
        await handler.start_async()
    finally:
        await stack.aclose()
        print("\n봇을 종료합니다...")


if __name__ == "__main__":
    mode = parse_args()
    try:
        asyncio.run(main(mode))
    except KeyboardInterrupt:
        pass
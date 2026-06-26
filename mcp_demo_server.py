from fastmcp import FastMCP

# 1. MCP 서버 인스턴스 생성
mcp = FastMCP(
    name="demo",
    instructions="간단한 계산과 인사말을 제공하는 MCP 서버입니다.",
)

# 2. Resource 정의 (클라이언트가 URI로 접근하는 읽기 전용 데이터)
@mcp.resource("info://about")
def get_about() -> str:
    """서버 정보를 반환합니다."""
    return "데모 MCP 서버입니다."

# 2-1. 고정값 Resource: 이 서버의 계산 정책
@mcp.resource("config://limits")
def get_limits() -> dict:
    """이 서버의 계산 정책(지원 연산, 입력 한도)을 반환합니다."""
    return {
        "supported_ops": ["add", "multiply"],
        "max_operand": 10_000_000,
        "note": "정수 연산만 지원합니다.",
    }

# 2-2. Resource Template: URI에 인자를 전달하는 동적 Resource
@mcp.resource("const://{name}")
def get_constant(name: str) -> str:
    """이름으로 상수 값을 조회합니다. (pi, e, golden)"""
    table = {
        "pi": "3.141592653589793",
        "e": "2.718281828459045",
        "golden": "1.618033988749895",
    }
    return table.get(name, f"알 수 없는 상수: {name}")

# 3. Tool 정의 (모델이 호출하는 함수)
@mcp.tool()
def add(a: int, b: int) -> str:
    """두 정수를 더합니다."""
    return f"{a} + {b} = {a + b}"

@mcp.tool()
def multiply(a: int, b: int) -> str:
    """두 정수를 곱합니다."""
    return f"{a} x {b} = {a * b}"

@mcp.tool()
def get_greeting(name: str, style: str = "formal") -> str:
    """인사말을 생성합니다."""
    if style == "casual":
        return f"안녕 {name}! 반가워~"
    return f"안녕하세요, {name}님."

# 4. Prompt 정의 (서버가 배포하는 프롬프트 템플릿)
@mcp.prompt()
def explain_calculation(expression: str) -> str:
    """주어진 수식을 단계별로 풀이해 설명하도록 지시하는 프롬프트."""
    return (
        f"다음 수식을 초등학생도 이해할 수 있게 한 단계씩 풀이해 주세요.\n\n"
        f"수식: {expression}\n\n"
        f"각 단계에서 무엇을 왜 계산하는지 한 줄로 설명하고, 마지막 줄에 최종 답을 적어 주세요."
    )

# 5. 서버 실행
if __name__ == "__main__":
    mcp.run(transport="streamable-http", port=8090)

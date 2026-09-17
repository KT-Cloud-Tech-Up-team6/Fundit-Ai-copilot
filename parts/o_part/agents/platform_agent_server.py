"""Platform Agent A2A 서버 — Product Agent 서버(현서)와 동일 구조.

실행: python -m parts.o_part.agents.platform_agent_server
Agent Card: http://127.0.0.1:9998/.well-known/agent-card.json
JSON-RPC:   http://127.0.0.1:9998/a2a/platform
"""
import os

from dotenv import load_dotenv

# 인수인계 STEP4: API 키·모델 설정을 .env 에서 읽는다 (api/webtest 와 동일)
load_dotenv()

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette

from parts.o_part.agents.platform_agent_executor import PlatformAgentExecutor

HOST = os.getenv("PLATFORM_AGENT_HOST", "127.0.0.1")
PORT = int(os.getenv("PLATFORM_AGENT_PORT", "9998"))
PUBLIC_URL = os.getenv("PLATFORM_AGENT_PUBLIC_URL", f"http://127.0.0.1:{PORT}")
RPC_PATH = "/a2a/platform"

platform_question_skill = AgentSkill(
    id="platform_question_answering",
    name="Platform Question Answering",
    description=(
        "플랫폼·펀딩 운영 질문(방송·펀딩 방식·결제·배송·환불·리워드·계정·쿠폰)을 "
        "Platform Copilot으로 처리하고 검증된 FAQ 원문 + 실시간 값 치환 답변을 반환합니다."
    ),
    tags=["platform", "funding", "live-commerce", "faq"],
    input_modes=["text/plain"],
    output_modes=["application/json"],
    examples=["펀딩 언제 끝나요?", "지금 바로 결제되나요?", "중간에 취소할 수 있나요?"],
)

agent_card = AgentCard(
    name="Live Commerce Platform Agent",
    description=(
        "라이브커머스 플랫폼·펀딩 질문을 처리하는 Platform Agent입니다. "
        "검증된 플랫폼 FAQ만 근거로 사용하며 답변 본문을 생성하지 않습니다 "
        "(환각 구조 차단). 상품 자체 질문은 Product Agent가 담당합니다."
    ),
    supported_interfaces=[
        AgentInterface(protocol_binding="JSONRPC", url=f"{PUBLIC_URL}{RPC_PATH}")
    ],
    version="0.1.0",
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["application/json"],
    skills=[platform_question_skill],
)

request_handler = DefaultRequestHandler(
    agent_executor=PlatformAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)

routes = []
routes.extend(create_agent_card_routes(agent_card))
routes.extend(create_jsonrpc_routes(request_handler, rpc_url=RPC_PATH))

app = Starlette(routes=routes)

if __name__ == "__main__":
    print()
    print(f"Platform Agent Server: {PUBLIC_URL}")
    print(f"Agent Card: {PUBLIC_URL}/.well-known/agent-card.json")
    print(f"A2A JSON-RPC: {PUBLIC_URL}{RPC_PATH}")
    print()
    uvicorn.run(app, host=HOST, port=PORT)

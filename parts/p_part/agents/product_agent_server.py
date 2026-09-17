import os

import uvicorn

from a2a.server.request_handlers import (
    DefaultRequestHandler,
)
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import (
    InMemoryTaskStore,
)
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from starlette.applications import Starlette

from parts.p_part.agents.product_agent_executor import (
    ProductAgentExecutor,
)


# =========================================================
# Server Config
# =========================================================

HOST = os.getenv(
    "PRODUCT_AGENT_HOST",
    "127.0.0.1",
)

PORT = int(
    os.getenv(
        "PRODUCT_AGENT_PORT",
        "9999",
    )
)

PUBLIC_URL = os.getenv(
    "PRODUCT_AGENT_PUBLIC_URL",
    f"http://127.0.0.1:{PORT}",
)

RPC_PATH = "/a2a/product"


# =========================================================
# Agent Skill
# =========================================================

product_question_skill = AgentSkill(
    id="product_question_answering",

    name="Product Question Answering",

    description=(
        "상품 관련 고객 질문을 Product Copilot으로 처리하고 "
        "Product KB Grounding 결과와 답변을 반환합니다."
    ),

    tags=[
        "product",
        "live-commerce",
        "rag",
        "grounding",
    ],

    input_modes=[
        "text/plain",
    ],

    output_modes=[
        "application/json",
    ],

    examples=[
        "건조 시간은 몇 분인가요?",
        "흡입력은 얼마인가요?",
        "180도로 눕혀서 청소 가능한가요?",
    ],
)


# =========================================================
# Agent Card
# =========================================================

agent_card = AgentCard(
    name="Live Commerce Product Agent",

    description=(
        "라이브커머스 상품 질문을 처리하는 Product Agent입니다. "
        "Product KB를 기반으로 Grounding된 답변을 생성하며 "
        "상품 질문이 이미 Product 영역으로 전달되었다고 가정합니다."
    ),

    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url=f"{PUBLIC_URL}{RPC_PATH}",
        )
    ],

    version="0.1.0",

    capabilities=AgentCapabilities(
        streaming=False,
    ),

    default_input_modes=[
        "text/plain",
    ],

    default_output_modes=[
        "application/json",
    ],

    skills=[
        product_question_skill,
    ],
)


# =========================================================
# Executor / Request Handler
# =========================================================

executor = ProductAgentExecutor()

request_handler = DefaultRequestHandler(
    agent_executor=executor,
    task_store=InMemoryTaskStore(),
    agent_card=agent_card,
)


# =========================================================
# A2A Routes
# =========================================================

routes = []

# Agent Discovery
# /.well-known/agent-card.json
routes.extend(
    create_agent_card_routes(
        agent_card
    )
)

# JSON-RPC A2A endpoint
# /a2a/product
routes.extend(
    create_jsonrpc_routes(
        request_handler,
        rpc_url=RPC_PATH,
    )
)


# =========================================================
# Starlette App
# =========================================================

app = Starlette(
    routes=routes
)


# =========================================================
# Local Server
# =========================================================

if __name__ == "__main__":

    print()
    print(
        f"Product Agent Server: "
        f"{PUBLIC_URL}"
    )

    print(
        f"Agent Card: "
        f"{PUBLIC_URL}/.well-known/agent-card.json"
    )

    print(
        f"A2A JSON-RPC: "
        f"{PUBLIC_URL}{RPC_PATH}"
    )

    print()

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
    )

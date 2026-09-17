from mcp import Client

from parts.p_part.mcp_servers.product_knowledge_server import mcp


async def register_seller_answer(
    live_id: str,
    question: str,
    answer: str,
) -> dict:
    """
    판매자가 미답변 고객 질문에 직접 답변한 내용을
    MCP Live Knowledge에 등록한다.

    실제 서비스에서는
    판매자 화면 -> BE -> 이 기능
    형태로 연결할 수 있다.

    현재 AI 개발 단계에서는
    터미널 입력을 통해 테스트한다.
    """

    live_id = live_id.strip()
    question = question.strip()
    answer = answer.strip()

    if not live_id:
        raise ValueError(
            "live_id는 비어 있을 수 없습니다."
        )

    if not question:
        raise ValueError(
            "question은 비어 있을 수 없습니다."
        )

    if not answer:
        raise ValueError(
            "answer는 비어 있을 수 없습니다."
        )

    async with Client(
        mcp,
        raise_exceptions=True,
    ) as client:

        result = await client.call_tool(
            "add_live_product_fact",
            {
                "live_id": live_id,
                "question": question,
                "answer": answer,
            },
        )

    data = (
        result.structured_content
        or {}
    )

    return {
        "live_id": live_id,
        "question": question,
        "answer": answer,
        "mcp_result": data,
    }

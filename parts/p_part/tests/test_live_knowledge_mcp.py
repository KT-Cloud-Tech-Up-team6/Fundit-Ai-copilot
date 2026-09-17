from uuid import uuid4

import anyio
from mcp import Client

from parts.p_part.mcp_servers.product_knowledge_server import mcp


async def main():

    live_id = (
        "test_live_"
        + uuid4().hex[:8]
    )

    async with Client(
        mcp,
        raise_exceptions=True
    ) as client:

        print("=" * 70)
        print("LIVE KNOWLEDGE MCP TEST")
        print("=" * 70)

        print(
            "live_id:",
            live_id
        )


        # =================================================
        # 1. 기존 상태
        # =================================================

        print(
            "\n[1] 등록 전 질문"
        )

        before = await client.call_tool(
            "search_product_context",
            {
                "live_id":
                    live_id,

                "question":
                    "앱으로 원격 조작 가능한가요?",

                "top_k":
                    3
            }
        )

        print(
            before.structured_content
        )


        # =================================================
        # 2. 판매자 답변 등록
        # =================================================

        print(
            "\n[2] 판매자 답변 등록"
        )

        added = await client.call_tool(
            "add_live_product_fact",
            {
                "live_id":
                    live_id,

                "question":
                    "앱으로 원격 조작 가능한가요?",

                "answer":
                    "앱 원격 조작은 지원하지 않습니다."
            }
        )

        print(
            added.structured_content
        )


        # =================================================
        # 3. 동일 질문 재검색
        # =================================================

        print(
            "\n[3] 동일 질문 재검색"
        )

        same_question = await client.call_tool(
            "search_live_product_fact",
            {
                "live_id":
                    live_id,

                "question":
                    "앱으로 원격 조작 가능한가요?",

                "top_k":
                    3
            }
        )

        same_data = (
            same_question
            .structured_content
        )

        print(
            same_data
        )

        assert (
            same_data["count"]
            >= 1
        )


        # =================================================
        # 4. 유사 질문 검색
        # =================================================

        print(
            "\n[4] 유사 질문 검색"
        )

        similar_question = (
            await client.call_tool(
                "search_live_product_fact",
                {
                    "live_id":
                        live_id,

                    "question":
                        "앱 원격 조작 돼요?",

                    "top_k":
                        3
                }
            )
        )

        similar_data = (
            similar_question
            .structured_content
        )

        print(
            similar_data
        )

        assert (
            similar_data["count"]
            >= 1
        )


        # =================================================
        # 5. 통합 Context 검색
        # =================================================

        print(
            "\n[5] 공식 KB + Live Knowledge 통합 검색"
        )

        context = await client.call_tool(
            "search_product_context",
            {
                "live_id":
                    live_id,

                "question":
                    "앱 원격 조작 돼요?",

                "top_k":
                    3
            }
        )

        context_data = (
            context
            .structured_content
        )

        print(
            context_data
        )

        assert (
            context_data["live_count"]
            >= 1
        )


        # =================================================
        # 6. 기존 공식 KB도 정상인지 확인
        # =================================================

        print(
            "\n[6] 공식 KB 회귀 테스트"
        )

        official = await client.call_tool(
            "search_product_context",
            {
                "live_id":
                    live_id,

                "question":
                    "흡입력 몇 파스칼이에요?",

                "top_k":
                    3
            }
        )

        official_data = (
            official
            .structured_content
        )

        print(
            official_data
        )

        assert (
            official_data[
                "official_count"
            ]
            >= 1
        )


        print(
            "\n"
            + "=" * 70
        )

        print(
            "LIVE KNOWLEDGE MCP TEST SUCCESS"
        )

        print(
            "=" * 70
        )


if __name__ == "__main__":

    anyio.run(
        main
    )
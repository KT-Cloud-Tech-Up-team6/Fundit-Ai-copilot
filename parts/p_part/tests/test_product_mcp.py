import anyio
from mcp import Client

from parts.p_part.mcp_servers.product_knowledge_server import mcp


async def main():

    async with Client(
        mcp,
        raise_exceptions=True
    ) as client:

        # =================================================
        # 1. MCP Server 연결 확인
        # =================================================

        print("=" * 70)
        print("MCP SERVER")
        print("=" * 70)

        print(
            "Server:",
            client.server_info
        )

        print(
            "Protocol:",
            client.protocol_version
        )


        # =================================================
        # 2. 등록 Tool 확인
        # =================================================

        print("\n" + "=" * 70)
        print("등록된 MCP TOOLS")
        print("=" * 70)

        tools_result = (
            await client.list_tools()
        )

        for tool in tools_result.tools:

            print(
                "-",
                tool.name
            )


        # =================================================
        # 3. 상품 지식 검색
        # =================================================

        print("\n" + "=" * 70)
        print("상품 KB 검색 테스트")
        print("=" * 70)

        search_result = (
            await client.call_tool(
                "search_product_knowledge",
                {
                    "question":
                        "흡입력 몇 파스칼이에요?",

                    "top_k":
                        3
                }
            )
        )

        print(
            search_result
            .structured_content
        )


        # =================================================
        # 4. 특정 Chunk 조회
        # =================================================

        print("\n" + "=" * 70)
        print("Chunk 조회 테스트")
        print("=" * 70)

        chunk_result = (
            await client.call_tool(
                "get_product_chunk",
                {
                    "chunk_id":
                        "kb_p_005"
                }
            )
        )

        print(
            chunk_result
            .structured_content
        )


        # =================================================
        # 5. 미지원 상품 질문
        # =================================================

        print("\n" + "=" * 70)
        print("근거 없는 질문 테스트")
        print("=" * 70)

        no_result = (
            await client.call_tool(
                "search_product_knowledge",
                {
                    "question":
                        "앱으로 원격 조작 가능한가요?",

                    "top_k":
                        3
                }
            )
        )

        print(
            no_result
            .structured_content
        )


if __name__ == "__main__":

    anyio.run(
        main
    )
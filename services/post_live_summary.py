from typing import Any

from mcp import Client

from core.interest_tracker import InterestTracker
from mcp_servers.product_knowledge_server import mcp


async def build_post_live_summary(
    live_id: str,
    tracker: InterestTracker,
    top_n: int = 2,
) -> dict:
    """
    방송 종료 후 구매자용 AI 라이브 Q&A 요약을 생성한다.

    처리 흐름
    1. 방송 전체 미답변 관심사 순위 조회
    2. Topic별 실제 대표 시청자 질문 선정
    3. MCP를 통해 공식 상품 KB + Live Knowledge 검색
    4. 근거가 존재하는 질문만 Q&A로 구성
    5. 최대 top_n개 반환

    현재 우선순위
    - 판매자가 방송 중 등록한 Live Knowledge
    - 공식 상품 KB

    근거가 없는 답변은 생성하지 않는다.
    """

    live_id = live_id.strip()

    if not live_id:
        raise ValueError(
            "live_id는 비어 있을 수 없습니다."
        )

    if top_n < 1:
        raise ValueError(
            "top_n은 1 이상이어야 합니다."
        )

    # -----------------------------------------------------
    # 1. 전체 방송 미답변 Topic 순위
    # -----------------------------------------------------

    ranked_topics = tracker.get_ranked_topics(
        top_n=100
    )

    summary_items: list[dict[str, Any]] = []

    # -----------------------------------------------------
    # 2. MCP 연결
    # -----------------------------------------------------

    async with Client(
        mcp,
        raise_exceptions=True,
    ) as client:

        for row in ranked_topics:

            question = row.get(
                "representative_question",
                "",
            )

            if (
                not question
                or question == "-"
            ):
                continue

            # -------------------------------------------------
            # 3. 공식 KB + Live Knowledge 통합 검색
            # -------------------------------------------------

            result = await client.call_tool(
                "search_product_context",
                {
                    "live_id": live_id,
                    "question": question,
                    "top_k": 3,
                },
            )

            context = (
                result.structured_content
                or {}
            )

            live_matches = context.get(
                "live_matches",
                [],
            )

            official_matches = context.get(
                "official_matches",
                [],
            )

            answer = None
            answer_source = None
            evidence = None

            # -------------------------------------------------
            # 4-A. 판매자 Live Knowledge 우선
            # -------------------------------------------------

            if live_matches:

                best_match = live_matches[0]

                fact = best_match.get(
                    "fact",
                    {},
                )

                seller_answer = fact.get(
                    "answer",
                    "",
                ).strip()

                if seller_answer:

                    answer = seller_answer
                    answer_source = (
                        "LIVE_KNOWLEDGE"
                    )

                    evidence = {
                        "fact_id":
                            fact.get(
                                "fact_id"
                            ),

                        "source":
                            fact.get(
                                "source"
                            ),
                    }

            # -------------------------------------------------
            # 4-B. 공식 상품 KB
            # -------------------------------------------------


            # -------------------------------------------------
            # 5. 근거 없는 질문은 구매자 요약에 넣지 않음
            # -------------------------------------------------

            if not answer:
                continue

            summary_items.append(
                {
                    "rank":
                        len(summary_items) + 1,

                    "category":
                        row.get(
                            "category"
                        ),

                    "category_name":
                        row.get(
                            "category_name"
                        ),

                    "topic_key":
                        row.get(
                            "topic_key"
                        ),

                    "topic_name":
                        row.get(
                            "topic_name"
                        ),

                    "interest_count":
                        row.get(
                            "count",
                            0,
                        ),

                    "question":
                        question,

                    "question_count":
                        row.get(
                            "representative_question_count",
                            0,
                        ),

                    "answer":
                        answer,

                    "answer_source":
                        answer_source,

                    "evidence":
                        evidence,
                }
            )

            if (
                len(summary_items)
                >= top_n
            ):
                break

    # -----------------------------------------------------
    # 6. 최종 반환
    # -----------------------------------------------------

    return {
        "live_id": live_id,
        "summary_type":
            "POST_LIVE_TOP_QA",

        "requested_count":
            top_n,

        "generated_count":
            len(summary_items),

        "top_questions":
            summary_items,
    }

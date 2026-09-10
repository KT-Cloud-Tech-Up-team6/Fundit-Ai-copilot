from core.interest_tracker import InterestTracker
from services.seller_feedback import register_seller_answer


async def collect_post_live_seller_feedback(
    live_id: str,
    tracker: InterestTracker,
    top_n: int = 2,
) -> list[dict]:
    """
    방송 종료 후 전체 미답변 관심사 TOP 질문을 판매자에게 보여주고,
    판매자는 답변만 입력한다.

    live_id와 질문은 시스템 내부에서 전달한다.
    판매자가 직접 입력하는 값은 answer뿐이다.

    입력된 답변은 MCP Live Knowledge에 등록한다.
    """

    # -----------------------------------------------------
    # 1. 방송 전체 TOP 질문 선정
    # -----------------------------------------------------

    top_questions = tracker.get_ranked_topics(
        top_n=top_n
    )

    if not top_questions:
        print()
        print("방송 전체 미답변 질문이 없습니다.")
        return []

    print()
    print("=" * 68)
    print("방송 종료 - 판매자 답변 입력")
    print("=" * 68)

    registered = []

    # -----------------------------------------------------
    # 2. TOP 질문을 자동으로 보여주고
    #    판매자는 답변만 입력
    # -----------------------------------------------------

    for rank, item in enumerate(
        top_questions,
        start=1,
    ):

        question = item[
            "representative_question"
        ]

        print()
        print(
            f"{rank}. "
            f"{item['topic_name']} "
            f"| {item['count']}건"
        )

        print(
            "Q.",
            question
        )

        answer = input(
            "판매자 답변 > "
        ).strip()

        # 답변하지 않은 질문은 건너뜀
        if not answer:
            print(
                "답변이 입력되지 않아 건너뜁니다."
            )
            continue

        # -------------------------------------------------
        # 3. MCP Live Knowledge 등록
        # -------------------------------------------------

        result = await register_seller_answer(
            live_id=live_id,
            question=question,
            answer=answer,
        )

        registered.append(
            {
                "rank": rank,
                "topic_key":
                    item["topic_key"],

                "topic_name":
                    item["topic_name"],

                "interest_count":
                    item["count"],

                "question":
                    question,

                "answer":
                    answer,

                "mcp_result":
                    result["mcp_result"],
            }
        )

        print(
            "→ Live Knowledge 등록 완료"
        )

    print()
    print("=" * 68)
    print(
        f"총 {len(registered)}개 답변 등록 완료"
    )
    print("=" * 68)

    return registered

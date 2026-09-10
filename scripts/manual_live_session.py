import anyio

from services.live_product_copilot import LiveProductCopilot


async def main():

    copilot = LiveProductCopilot()

    print()
    print("=" * 68)
    print("LIVE PRODUCT COPILOT - MANUAL E2E")
    print("=" * 68)

    print(
        "시청자 질문을 직접 입력하세요."
    )

    print(
        "명령어: /dashboard | /end"
    )

    print("=" * 68)

    while True:

        comment = input(
            "\n시청자 > "
        ).strip()

        if not comment:
            continue

        # -------------------------------------------------
        # 현재 관심사 확인
        # -------------------------------------------------

        if comment == "/dashboard":

            copilot.print_dashboard()

            continue

        # -------------------------------------------------
        # 방송 종료
        # -------------------------------------------------

        if comment == "/end":

            result = await copilot.end_live(
                top_n=2
            )

            summary = result.get(
                "summary"
            )

            print()
            print("=" * 68)
            print("구매자용 AI 라이브 요약")
            print("=" * 68)

            if (
                not summary
                or not summary.get(
                    "top_questions"
                )
            ):

                print(
                    "생성된 Q&A 요약이 없습니다."
                )

            else:

                for item in summary[
                    "top_questions"
                ]:

                    print()

                    print(
                        f"{item['rank']}. "
                        f"{item['topic_name']} "
                        f"| 관심 {item['interest_count']}건"
                    )

                    print(
                        "Q.",
                        item["question"]
                    )

                    print(
                        "A.",
                        item["answer"]
                    )

                    print(
                        "출처:",
                        item["answer_source"]
                    )

            print()
            print("=" * 68)

            break

        # -------------------------------------------------
        # 실제 P파트 질문 처리
        # -------------------------------------------------

        try:

            result = (
                copilot.process_comment(
                    comment
                )
            )

            print(
                "Grounding:",
                result["grounding_status"]
            )

            print(
                "Answer:",
                result["answer"]
            )

            if result[
                "needs_seller_attention"
            ]:

                print(
                    "→ 미답변 관심사에 누적됨"
                )

        except Exception as e:

            print(
                "처리 오류:",
                e
            )


if __name__ == "__main__":

    anyio.run(
        main
    )


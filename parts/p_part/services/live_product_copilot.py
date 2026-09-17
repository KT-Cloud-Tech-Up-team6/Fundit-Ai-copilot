from uuid import uuid4

from parts.p_part.interest_tracker import InterestTracker
from parts.p_part.services.product_copilot import process_product_question
from parts.p_part.services.post_live_feedback import (
    collect_post_live_seller_feedback,
)
from parts.p_part.services.post_live_summary import (
    build_post_live_summary,
)


class LiveProductCopilot:
    """
    라이브 방송 세션용 P파트 Copilot.

    역할
    - 고객 질문 처리
    - 미답변 관심사 누적
    - 판매자 관심사 대시보드 조회
    - 방송 종료 후 TOP 질문 선정
    - 판매자 답변 수집
    - 구매자용 Post-Live Q&A Summary 생성
    """

    def __init__(
        self,
        live_id: str | None = None,
    ):
        # 실제 서비스에서는 BE가 live_id를 전달한다.
        # 로컬 개발에서는 자동 생성한다.
        self.live_id = (
            live_id
            if live_id
            else "local_live_" + uuid4().hex[:8]
        )

        self.tracker = InterestTracker()
        self.tracker.reset()

    def process_comment(
        self,
        question: str,
    ) -> dict:
        """
        고객 질문 1건 처리.

        PARTIAL / NO인 경우
        미답변 관심사가 자동 누적된다.
        """

        return process_product_question(
            question=question,
            tracker=self.tracker,
        )

    def print_dashboard(
        self,
        top_n: int = 5,
    ):
        """
        판매자용 미답변 관심사 대시보드.
        """

        self.tracker.print_dashboard(
            top_n=top_n
        )

    def get_post_live_top_questions(
        self,
        top_n: int = 2,
    ):
        """
        방송 전체 기준 TOP 질문 반환.
        """

        return self.tracker.get_ranked_topics(
            top_n=top_n
        )

    async def end_live(
        self,
        top_n: int = 2,
    ) -> dict:
        """
        방송 종료 처리.

        1. 전체 미답변 관심사 TOP N 선정
        2. 판매자에게 질문 표시
        3. 판매자는 답변만 입력
        4. 답변을 MCP Live Knowledge에 등록
        5. 구매자용 Post-Live Q&A Summary 생성
        """

        print()
        print("=" * 68)
        print("라이브 방송 종료")
        print("=" * 68)

        top_questions = (
            self.get_post_live_top_questions(
                top_n=top_n
            )
        )

        if not top_questions:
            print(
                "방송 중 집계된 미답변 질문이 없습니다."
            )

            return {
                "live_id": self.live_id,
                "top_questions": [],
                "seller_feedback": [],
                "summary": None,
            }

        print()
        print("전체 방송 관심사 TOP 질문")

        for rank, item in enumerate(
            top_questions,
            start=1,
        ):
            print(
                f"{rank}. "
                f"{item['topic_name']} "
                f"| {item['count']}건"
            )

            print(
                "   Q.",
                item["representative_question"],
            )

        # -------------------------------------------------
        # 판매자는 답변만 입력
        # -------------------------------------------------

        seller_feedback = (
            await collect_post_live_seller_feedback(
                live_id=self.live_id,
                tracker=self.tracker,
                top_n=top_n,
            )
        )

        # -------------------------------------------------
        # 구매자용 Q&A 요약 생성
        # -------------------------------------------------

        summary = await build_post_live_summary(
            live_id=self.live_id,
            tracker=self.tracker,
            top_n=top_n,
        )

        return {
            "live_id":
                self.live_id,

            "top_questions":
                top_questions,

            "seller_feedback":
                seller_feedback,

            "summary":
                summary,
        }

    def reset(self):
        """
        새로운 방송 세션 시작 시 초기화.
        """

        self.live_id = (
            "local_live_"
            + uuid4().hex[:8]
        )

        self.tracker.reset()
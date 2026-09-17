import asyncio
import json
import logging

from a2a.helpers import (
    get_message_text,
    new_text_message,
)
from a2a.server.agent_execution import (
    AgentExecutor,
    RequestContext,
)
from a2a.server.events import EventQueue


logger = logging.getLogger(__name__)


def run_product_copilot(question: str) -> dict:
    """
    실제 Product Copilot 호출.

    import를 함수 내부에서 수행하는 이유:
    A2A 서버 시작 자체가 Vertex AI / ADC 상태에
    의존하지 않도록 하기 위함이다.

    따라서 GCP 연결이 없어도
    Agent Card와 A2A 서버는 실행할 수 있다.
    """

    from services.product_copilot import (
        process_product_question,
    )

    return process_product_question(question)


class ProductAgentExecutor(AgentExecutor):
    """
    Product Copilot을 A2A Agent로 노출하는 Executor.

    역할:
    1. A2A Message에서 상품 질문 추출
    2. 기존 process_product_question() 호출
    3. 기존 Product Copilot 결과를 JSON 형태로 반환

    Product RAG 로직 자체는 여기서 다시 구현하지 않는다.
    """

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

        # -------------------------------------------------
        # 1. 사용자 메시지 확인
        # -------------------------------------------------

        message = context.message

        if message is None:

            response = {
                "error": "EMPTY_MESSAGE",
                "message": "A2A 요청에 메시지가 없습니다.",
            }

            await event_queue.enqueue_event(
                new_text_message(
                    json.dumps(
                        response,
                        ensure_ascii=False,
                    ),
                    media_type="application/json",
                )
            )

            return

        # -------------------------------------------------
        # 2. Text 추출
        # -------------------------------------------------

        question = get_message_text(
            message
        ).strip()

        if not question:

            response = {
                "error": "EMPTY_QUESTION",
                "message": "상품 질문이 비어 있습니다.",
            }

            await event_queue.enqueue_event(
                new_text_message(
                    json.dumps(
                        response,
                        ensure_ascii=False,
                    ),
                    media_type="application/json",
                )
            )

            return

        # -------------------------------------------------
        # 3. Product Copilot 호출
        #
        # process_product_question()은 동기 함수이므로
        # asyncio event loop를 막지 않도록
        # 별도 thread에서 실행한다.
        # -------------------------------------------------

        try:

            result = await asyncio.to_thread(
                run_product_copilot,
                question,
            )

        except Exception:

            logger.exception(
                "Product Agent 처리 중 오류 발생"
            )

            response = {
                "error": "PRODUCT_AGENT_EXECUTION_FAILED",
                "message": (
                    "상품 질문 처리 중 오류가 발생했습니다."
                ),
            }

            await event_queue.enqueue_event(
                new_text_message(
                    json.dumps(
                        response,
                        ensure_ascii=False,
                    ),
                    media_type="application/json",
                )
            )

            return

        # -------------------------------------------------
        # 4. A2A Response
        #
        # 기존 Product Copilot의 반환 구조를
        # 그대로 유지한다.
        # -------------------------------------------------

        response_text = json.dumps(
            result,
            ensure_ascii=False,
        )

        # v1 A2A Message-only 패턴:
        # 정확히 하나의 Message만 enqueue한다.
        await event_queue.enqueue_event(
            new_text_message(
                response_text,
                media_type="application/json",
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:

        # 현재 Product Agent는
        # 단발성 질문 → 응답 구조이므로
        # 장기 실행 Task cancellation은 지원하지 않는다.
        raise NotImplementedError(
            "Product Agent는 Task cancellation을 지원하지 않습니다."
        )

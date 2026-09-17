"""Platform Copilot 을 A2A Agent 로 노출하는 Executor.

P파트 ProductAgentExecutor 와 동일 패턴 — 로직 재구현 없이
process_platform_question() 을 호출하는 Wrapper 다.
"""
import asyncio
import json
import logging

from a2a.helpers import get_message_text, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

logger = logging.getLogger(__name__)


def run_platform_copilot(question: str) -> dict:
    # import 를 함수 내부에서 수행: A2A 서버 시작이 LLM 인증 상태에 의존하지 않게 함
    from parts.o_part.services.platform_copilot import process_platform_question
    return process_platform_question(question)


class PlatformAgentExecutor(AgentExecutor):

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        if message is None:
            await self._reply(event_queue, {"error": "EMPTY_MESSAGE",
                                            "message": "A2A 요청에 메시지가 없습니다."})
            return

        question = get_message_text(message).strip()
        if not question:
            await self._reply(event_queue, {"error": "EMPTY_QUESTION",
                                            "message": "플랫폼 질문이 비어 있습니다."})
            return

        try:
            result = await asyncio.to_thread(run_platform_copilot, question)
        except Exception:
            logger.exception("Platform Agent 처리 중 오류 발생")
            await self._reply(event_queue, {"error": "PLATFORM_AGENT_EXECUTION_FAILED",
                                            "message": "플랫폼 질문 처리 중 오류가 발생했습니다."})
            return

        await self._reply(event_queue, result)

    @staticmethod
    async def _reply(event_queue: EventQueue, payload: dict) -> None:
        # v1 A2A Message-only 패턴: 정확히 하나의 Message 만 enqueue
        await event_queue.enqueue_event(
            new_text_message(json.dumps(payload, ensure_ascii=False),
                             media_type="application/json"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Platform Agent는 Task cancellation을 지원하지 않습니다.")

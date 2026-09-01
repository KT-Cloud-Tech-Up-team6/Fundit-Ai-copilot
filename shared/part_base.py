"""모든 상담 파트가 구현해야 하는 인터페이스.

새 파트(P파트 등)를 붙이는 방법:
  1. parts/<part_id>/ 폴더를 만들고 CopilotPart 를 구현한다.
  2. api/main.py (또는 orchestrator 초기화 지점)에서 register 한다.
  3. 끝. 오케스트레이터가 manifest 를 읽어 라우팅에 자동 반영한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from shared.schemas import Comment, LiveContext, PartAnswer, PartManifest, RouteMatch


class CopilotPart(ABC):
    part_id: str = "base"

    @abstractmethod
    def manifest(self) -> PartManifest:
        """라우팅용 명세(담당 범위·라벨·FAQ 색인)를 반환한다."""

    @abstractmethod
    def handle(self, comment: Comment, match: RouteMatch, context: LiveContext) -> PartAnswer:
        """라우팅된 댓글에 대한 최종 답변을 만든다.

        규칙:
        - strict 근거는 원문 그대로 반환해야 한다 (수치·날짜 변형 금지).
        - 근거가 없으면 반드시 decision=UNANSWERABLE 로 반환한다 (생성 금지).
        """

"""파트 간 공통 계약 스키마.

O파트·P파트 등 모든 상담 파트와 오케스트레이터가 이 모델만으로 통신한다.
여기를 바꾸면 모든 파트에 영향이 가므로, 변경 시 팀 합의 필요.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Decision(str, Enum):
    """댓글 하나에 대한 최종 처리 결정."""

    ANSWER = "ANSWER"                # 파트가 답변 생성
    IGNORE = "IGNORE"                # 응대 제외 (스몰톡, 개인 문의 등)
    UNANSWERABLE = "UNANSWERABLE"    # 근거 없음 → 고정 폴백 멘트


class IgnoredReason(str, Enum):
    SMALLTALK = "SMALLTALK"
    NOT_QUESTION = "NOT_QUESTION"
    PERSONAL_INQUIRY = "PERSONAL_INQUIRY"


class Comment(BaseModel):
    """라이브 채팅 댓글 1건 (파트 입력)."""

    comment_id: Optional[str] = None
    user_id: Optional[str] = None
    text: str


class LiveContext(BaseModel):
    """방송·펀딩 실시간 컨텍스트. PUT /lives/{live_id}/context 로 갱신된다."""

    live_id: str
    project_id: Optional[str] = None
    broadcast: dict = Field(default_factory=dict)   # start_at, end_at, vod_enabled
    funding: dict = Field(default_factory=dict)     # deadline, achieved_rate, target_amount
    extra_slots: dict = Field(default_factory=dict)  # early_bird_left 등 파트 공용 동적 슬롯


class RouteMatch(BaseModel):
    """오케스트레이터 분류기의 출력 → 파트 handle() 입력."""

    decision: Decision
    part_id: Optional[str] = None          # "o_part" | "p_part" | ...
    label: Optional[str] = None            # BROADCAST_INFO 등 카테고리
    faq_id: Optional[str] = None           # FAQ 단위까지 매칭된 경우
    ignored_reason: Optional[IgnoredReason] = None
    confidence: float = 0.0


class PartAnswer(BaseModel):
    """파트 handle() 의 출력 (최종 응답 단위)."""

    decision: Decision
    part_id: Optional[str] = None
    label: Optional[str] = None
    faq_id: Optional[str] = None
    ignored_reason: Optional[IgnoredReason] = None
    answer_text: Optional[str] = None      # decision == ANSWER 일 때만
    strict: bool = False                   # True면 정책 원문 그대로 (리라이트 금지)
    source: Optional[str] = None           # 근거 (정책 조항 등)
    meta: dict = Field(default_factory=dict)


class PartManifest(BaseModel):
    """파트가 오케스트레이터에 자신을 등록할 때 내는 라우팅 명세.

    분류 프롬프트는 등록된 모든 파트의 manifest 를 합쳐서 만들어진다.
    """

    part_id: str
    description: str                       # 이 파트가 담당하는 질문 범위 설명
    labels: list[str] = Field(default_factory=list)
    # faq_index: 분류기가 faq_id 단위까지 매칭해 주길 원하는 파트만 채운다 (O파트).
    # 항목: {"faq_id", "label", "question_variants": [...]}
    faq_index: list[dict] = Field(default_factory=list)

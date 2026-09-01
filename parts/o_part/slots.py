"""동적 슬롯 값 계산.

기본값(data/slots.json) 위에 LiveContext(PUT /lives/{live_id}/context)로
들어온 실시간 값을 덮어쓴다.
"""
from __future__ import annotations

from datetime import datetime

from shared.schemas import LiveContext
from parts.o_part import kb


def _fmt_time(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    return f"{dt.hour}시 {dt.minute:02d}분"


def _fmt_datetime(iso: str) -> str:
    dt = datetime.fromisoformat(iso)
    return f"{dt.year}년 {dt.month}월 {dt.day}일 {dt.hour}시 {dt.minute:02d}분"


def _fmt_amount(won: int) -> str:
    man = won // 10_000
    return f"{man:,}만 원"


def resolve(context: LiveContext) -> dict:
    slots = dict(kb.load_default_slots())

    bc, fd = context.broadcast, context.funding
    if bc.get("end_at"):
        slots["end_time"] = _fmt_time(bc["end_at"])
    if fd.get("deadline"):
        slots["deadline"] = _fmt_datetime(fd["deadline"])
    if fd.get("achieved_rate") is not None:
        slots["achieved_rate"] = fd["achieved_rate"]
    if fd.get("target_amount") is not None:
        slots["target_amount"] = _fmt_amount(fd["target_amount"])
    if fd.get("current_amount") is not None:
        slots["current_amount"] = _fmt_amount(fd["current_amount"])

    slots.update(context.extra_slots)  # early_bird_left 등 수시 갱신 값
    return slots


def fill(answer_text: str, slots: dict) -> str:
    for key, value in slots.items():
        answer_text = answer_text.replace("{" + key + "}", str(value))
    return answer_text

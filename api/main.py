"""FastAPI 엔트리포인트.

실행: uvicorn api.main:app --reload  (프로젝트 루트에서)
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel

from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from parts.p_part.part import PPart
from shared.schemas import Comment, LiveContext, PartAnswer

app = FastAPI(title="LiveFunding Copilot", version="0.1.0")

# 파트 등록 지점 — 새 파트는 여기 리스트에 추가하면 끝.
service = CopilotService(parts=[OPart(), PPart()])


class ContextBody(BaseModel):
    project_id: str | None = None
    broadcast: dict = {}
    funding: dict = {}
    extra_slots: dict = {}


@app.put("/lives/{live_id}/context")
def put_context(live_id: str, body: ContextBody):
    service.put_context(LiveContext(live_id=live_id, **body.model_dump()))
    return {"ok": True, "live_id": live_id}


@app.get("/lives/{live_id}/context")
def get_context(live_id: str) -> LiveContext:
    return service.get_context(live_id)


class CommentBody(BaseModel):
    comment_id: str | None = None
    user_id: str | None = None
    text: str


@app.post("/lives/{live_id}/comments")
def post_comment(live_id: str, body: CommentBody) -> PartAnswer:
    return service.process(live_id, Comment(**body.model_dump()))


@app.get("/health")
def health():
    return {"ok": True}

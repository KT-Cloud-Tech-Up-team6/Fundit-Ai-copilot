"""Fundit AI Copilot — BE 연동 API (v1).

Base Path: /api/v1/funding-ai
인증: env API_TOKEN 설정 시 Authorization: Bearer {token} 필수 (미설정이면 개발 모드로 통과)

기능 A. 라이브 자동 답변
  POST /lives/{live_id}/prepare    LIVE 전 상품정보 색인 (미색인 상태 comments 호출 → 409)
  PUT  /lives/{live_id}/context    방송·펀딩 실시간 값 (동적 슬롯)
  POST /lives/{live_id}/comments   댓글 배치 분석 + 자동 답변 (3초 배치 권장)

기능 B. 자주 나오는 질문 요약 (Seller Copilot)
  GET  /lives/{live_id}/insights   관심사 카테고리 랭킹 + 대표 질문(고객 원문)
  GET  /lives/{live_id}/unanswered 반복 미답변 질문 목록

실행: uvicorn api.main:app --port 8080
문서: /docs (Swagger UI), /openapi.json — 상세 가이드는 api/API_GUIDE.md
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from parts.p_part.part import PPart
from shared.schemas import Comment, Decision, LiveContext

BASE = "/api/v1/funding-ai"
RUNTIME_DIR = Path(os.getenv("RUNTIME_DIR", Path(__file__).parent / "runtime"))
MAX_BATCH = 50

app = FastAPI(
    title="Fundit AI Copilot API",
    version="1.0.0",
    description="라이브 채팅 AI 자동 응대 — 기능 A(자동 답변) / 기능 B(자주 나오는 질문 요약)",
)

service = CopilotService(parts=[OPart(), PPart()])

# live_id 별 런타임 상태 (MVP: 인메모리 — 운영 전환 시 KV/DB 교체 지점)
_lives: dict[str, dict] = {}


def _auth(authorization: str | None = Header(default=None)) -> None:
    token = os.getenv("API_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED"})


def _live(live_id: str) -> dict:
    if live_id not in _lives:
        _lives[live_id] = {
            "prepared": False, "product": None, "qseq": 0,
            "tracker": None, "unanswered": {},
        }
    return _lives[live_id]


def _tracker(live_id: str):
    """P파트 관심사 집계기 (심현서 interest_tracker) — live 단위 파일."""
    st = _live(live_id)
    if st["tracker"] is None:
        from parts.p_part.interest_tracker import InterestTracker
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        st["tracker"] = InterestTracker(path=str(RUNTIME_DIR / f"interest_{live_id}.json"))
    return st["tracker"]


# =========================================================
# 기능 A-1. 상품정보 색인 (LIVE 전)
# =========================================================

class KnowledgeChunk(BaseModel):
    chunk_id: str
    category: str
    text: str
    strict: bool = False
    source: str | None = None


class PrepareBody(BaseModel):
    product_name: str = "상품"
    product_category: str
    knowledge: list[KnowledgeChunk] = Field(min_length=1)


def _knowledge_to_md(body: PrepareBody) -> str:
    """prepare 입력을 P파트 retriever 가 읽는 MD KB 형식으로 변환.

    chunk_id 는 retriever 파서 규격(kb_p_###)으로 정규화하고
    원본 id 는 source 에 병기해 추적 가능하게 남긴다.
    """
    lines = [f"# {body.product_name}", "",
             f"- product_category: {body.product_category}", "", "---", ""]
    for i, c in enumerate(body.knowledge, start=1):
        cid = f"kb_p_{i:03d}"
        src = (c.source or "판매자 입력").strip()
        if c.chunk_id and c.chunk_id != cid:
            src += f" (원본 id: {c.chunk_id})"
        lines += [f"## {cid} | {c.category.strip()}", "", c.text.strip(), "",
                  f"- strict: {'true' if c.strict else 'false'}",
                  f"- source: {src}", "", "---", ""]
    return "\n".join(lines)


@app.post(BASE + "/lives/{live_id}/prepare", dependencies=[Depends(_auth)], tags=["A. 라이브 자동 답변"])
def prepare(live_id: str, body: PrepareBody):
    """판매자 상품정보를 색인해 **활성 상품 KB 로 교체**한다.

    이후 상품 질문은 여기서 전달된 knowledge 를 근거로 답변한다 (동적 KB —
    상품이 바뀌면 이 API 만 다시 호출하면 됨). 색인 전 comments 호출은 409.
    MVP 한계: 활성 KB 는 프로세스 전역 1개 — 동시에 여러 live 를 서로 다른
    상품으로 돌리려면 프로세스 분리 또는 다음 페이즈의 per-live KB 필요.
    """
    from parts.p_part import rag_retriever

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    md_path = RUNTIME_DIR / f"product_{live_id}.md"
    md_path.write_text(_knowledge_to_md(body), encoding="utf-8")
    rag_retriever.set_product_md(md_path)

    st = _live(live_id)
    st["product"] = {"product_name": body.product_name,
                     "product_category": body.product_category,
                     "chunks": len(body.knowledge)}
    st["prepared"] = True
    return {"status": "ready", "live_id": live_id,
            "product_name": body.product_name, "chunks": len(body.knowledge)}


# =========================================================
# 기능 A-2. 방송·펀딩 실시간 값 (동적 슬롯)
# =========================================================

class ContextBody(BaseModel):
    project_id: str | None = None
    broadcast: dict = {}
    funding: dict = {}
    extra_slots: dict = {}


@app.put(BASE + "/lives/{live_id}/context", dependencies=[Depends(_auth)], tags=["A. 라이브 자동 답변"])
def put_context(live_id: str, body: ContextBody):
    service.put_context(LiveContext(live_id=live_id, **body.model_dump()))
    return {"status": "ok", "live_id": live_id}


# =========================================================
# 기능 A-3. 댓글 배치 분석 + 자동 답변 (LIVE 중)
# =========================================================

class CommentIn(BaseModel):
    comment_id: str
    text: str = Field(min_length=1, max_length=300)
    at_ms: int = 0


class CommentsBody(BaseModel):
    comments: list[CommentIn] = Field(min_length=1, max_length=MAX_BATCH)


def _handled_by(ans) -> str:
    if ans.decision == Decision.UNANSWERABLE:
        return "UNANSWERABLE"
    return {"p_part": "PRODUCT", "o_part": "PLATFORM"}.get(ans.part_id or "", "PLATFORM")


def _track_unanswered(live_id: str, text: str, ans) -> list[dict]:
    """P파트 미해결 토픽(파트가 이미 분석해 meta 로 전달)을 관심사 집계에 반영."""
    topics: list[dict] = []
    unresolved = ans.meta.get("unresolved_topics") or []
    if ans.part_id == "p_part" and unresolved:
        try:
            from types import SimpleNamespace

            from parts.p_part.interest_tracker import CATEGORY_NAMES, TOPIC_NAMES
            _tracker(live_id).add_topics(
                topics=[SimpleNamespace(**t) for t in unresolved],
                original_question=text,
            )
            topics = [
                {"category": CATEGORY_NAMES.get(t["category"], t["category"]),
                 "topic": TOPIC_NAMES.get(t["topic_key"], t["topic_key"])}
                for t in unresolved
            ]
        except Exception:
            pass  # 집계 실패는 답변 흐름에 영향 없음

    # 반복 미답변 목록 (unanswered) 병합 집계 — 완전 미답변만
    if ans.decision == Decision.UNANSWERABLE:
        key = "".join(ch for ch in text if ch.isalnum())
        st = _live(live_id)
        rec = st["unanswered"].setdefault(key, {
            "representative_text": text, "count": 0, "examples": [], "topics": topics,
        })
        rec["count"] += 1
        if text not in rec["examples"]:
            rec["examples"] = (rec["examples"] + [text])[-5:]
        if len(text) < len(rec["representative_text"]):
            rec["representative_text"] = text
        rec["last_ts"] = time.time()
        if topics and not rec["topics"]:
            rec["topics"] = topics
    return topics


@app.post(BASE + "/lives/{live_id}/comments", dependencies=[Depends(_auth)], tags=["A. 라이브 자동 답변"])
def analyze_comments(live_id: str, body: CommentsBody):
    """댓글 배치(3초 단위 권장, 최대 50건)를 분류하고 자동 답변을 생성한다.

    - answer 가 있으면 시청자 채팅에 그대로 노출 (strict=true 는 문구 가공 금지)
    - answer 가 null(UNANSWERABLE)이면 시청자 화면 무노출 — 기능 B 로 집계됨
    - ignored 는 잡담·개인문의 (판매자 화면·집계 제외)
    """
    st = _live(live_id)
    if not st["prepared"]:
        return JSONResponse(status_code=409, content={
            "status": "error", "code": "NOT_PREPARED",
            "message": "상품정보 색인 전입니다. POST /prepare 를 먼저 호출하세요.",
        })

    questions, ignored, errors = [], [], []
    for c in body.comments:
        try:
            ans = service.process(live_id, Comment(comment_id=c.comment_id, text=c.text))
        except Exception as e:
            errors.append({"comment_id": c.comment_id, "code": "EVIDENCE_UNAVAILABLE",
                           "message": str(e)[:200]})
            continue

        if ans.decision == Decision.IGNORE:
            ignored.append({
                "comment_id": c.comment_id,
                "reason": ans.ignored_reason.value if ans.ignored_reason else "NOT_QUESTION",
            })
            continue

        st["qseq"] += 1
        q: dict = {
            "question_id": f"q_{st['qseq']:04d}",
            "comment_id": c.comment_id,
            "text": c.text,
            "handled_by": _handled_by(ans),
            "category": ans.label,
            "at_ms": c.at_ms,
            "answer": None,
        }
        if ans.decision == Decision.ANSWER and ans.answer_text:
            q["answer"] = {
                "text": ans.answer_text,
                "grounding": ans.meta.get("grounding", "GROUNDED"),
                "strict": ans.strict,
                "source": ans.source,
            }
            if ans.meta.get("grounding") == "PARTIAL_GROUNDED":
                q["unresolved_topics"] = _track_unanswered(live_id, c.text, ans)
        else:  # UNANSWERABLE — 시청자 무노출, 기능 B 집계
            q["topics"] = _track_unanswered(live_id, c.text, ans)
        questions.append(q)

    out = {"status": "ok", "questions": questions, "ignored": ignored}
    if errors:
        out["errors"] = errors
    return out


# =========================================================
# 기능 B-1. 관심사 요약 (Seller Copilot)
# =========================================================

@app.get(BASE + "/lives/{live_id}/insights", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def insights(live_id: str, top_n: int = 5):
    """미답변 질문의 관심사 랭킹. 대표 질문은 AI 생성이 아닌 실제 고객 원문."""
    rows = _tracker(live_id).get_ranked_categories(top_n=top_n)
    categories = [
        {"category": r["category_name"], "count": r["count"],
         "top_topic": r["top_topic_name"], "top_topic_count": r["topic_count"]}
        for r in rows
    ]
    top_questions = [
        {"representative_text": r["representative_question"],
         "count": r["representative_question_count"],
         "category": r["category_name"], "topic": r["top_topic_name"]}
        for r in rows if r["representative_question"] != "-"
    ]
    return {"status": "ok", "live_id": live_id,
            "categories": categories, "top_questions": top_questions}


# =========================================================
# 기능 B-2. 반복 미답변 질문 목록
# =========================================================

@app.get(BASE + "/lives/{live_id}/unanswered", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def unanswered(live_id: str, top_n: int = 10):
    """AI가 답하지 못한 질문을 병합 집계한 목록 — 판매자가 방송에서 직접 답변."""
    rows = sorted(_live(live_id)["unanswered"].values(),
                  key=lambda r: r["count"], reverse=True)[:top_n]
    return {"status": "ok", "live_id": live_id, "unanswered": [
        {"representative_text": r["representative_text"], "count": r["count"],
         "examples": r["examples"], "topics": r["topics"]}
        for r in rows
    ]}


# =========================================================
# 공통
# =========================================================

@app.get(BASE + "/health", tags=["공통"])
def health():
    return {"status": "ok", "model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            "auth": bool(os.getenv("API_TOKEN"))}


@app.post(BASE + "/lives/{live_id}/reset", dependencies=[Depends(_auth)], tags=["공통"])
def reset(live_id: str):
    """테스트용: 해당 live 의 색인·집계 상태 초기화."""
    if live_id in _lives:
        try:
            _tracker(live_id).reset()
        except Exception:
            pass
        del _lives[live_id]
    return {"status": "ok"}

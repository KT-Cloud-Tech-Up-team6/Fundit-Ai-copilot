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

from orchestrator import llm
from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from parts.p_part.part import PPart
from shared.schemas import Comment, Decision, LiveContext

BASE = "/api/v1/funding-ai"
RUNTIME_DIR = Path(os.getenv("RUNTIME_DIR", Path(__file__).parent / "runtime"))
MAX_BATCH = 50
WINDOW_MS = 3 * 60 * 1000  # 자주 나오는 질문 집계 윈도우 = 3분

# O파트 라벨 → 판매자 화면용 한글 카테고리 (P 카테고리는 이미 한글)
O_LABEL_NAMES = {
    "BROADCAST_INFO": "방송", "FUNDING_PROCESS": "펀딩", "PAYMENT": "결제",
    "DELIVERY_POLICY": "배송", "REFUND_CANCEL": "취소·환불", "REWARD_OPTION": "리워드",
    "ACCOUNT_APP": "계정·앱", "EVENT_COUPON": "쿠폰·이벤트",
}

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
            "tracker": None,
            # 질문 집계 저장소 — 답변된 질문 + 미답변 + 판매자 답변 전부 누적
            "faq": {}, "faq_seq": 0, "last_win": 0,
        }
    return _lives[live_id]


def _qkey(text: str) -> str:
    """유사 표현 병합용 정규화 키 (공백·문장부호 무시)."""
    return "".join(ch for ch in text if ch.isalnum())


def _qwords(text: str):
    import re
    return set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", text.lower()))


def _faq_lookup(st: dict, text: str, topics: list | None = None):
    """유사 질문 병합 탐색 — ① 정규화 키 일치 ② 단어 자카드 ≥0.6 ③ 관심 토픽 일치.

    한 번 병합된 표현은 alias 로 등록되어 이후 즉시 같은 그룹으로 붙는다.
    """
    key = _qkey(text)
    main = st.setdefault("faq_alias", {}).get(key, key)
    if main in st["faq"]:
        return main, st["faq"][main]

    tw = _qwords(text)
    if tw:
        best_key, best_j = None, 0.0
        for k, e in st["faq"].items():
            ew = _qwords(e["representative_text"])
            if not ew:
                continue
            j = len(tw & ew) / (len(tw | ew) or 1)
            if j > best_j:
                best_key, best_j = k, j
        if best_key and best_j >= 0.6:
            st["faq_alias"][key] = best_key
            return best_key, st["faq"][best_key]

    if topics:
        tset = {(t.get("category"), t.get("topic")) for t in topics}
        for k, e in st["faq"].items():
            if e["handled_by"] == "UNANSWERABLE" and e["topics"]:
                eset = {(t.get("category"), t.get("topic")) for t in e["topics"]}
                if tset & eset:
                    st["faq_alias"][key] = k
                    return k, e
    return key, None


def _promote_windows(st: dict) -> None:
    """완료된 3분 윈도우마다 TOP3 신규 질문을 '공통 질문'으로 승격한다.

    이미 승격된 그룹은 다음 윈도우에서 다시 수집하지 않는다 — 카운트만 누적.
    (현재 진행 중인 윈도우는 아직 승격하지 않는다)
    """
    done = st.setdefault("promoted_upto", -1)
    for w in range(done + 1, st["last_win"]):  # last_win = 진행 중 윈도우
        candidates = [e for e in st["faq"].values()
                      if not e.get("promoted") and e["windows"].get(w, 0) > 0]
        candidates.sort(key=lambda e: (-e["windows"].get(w, 0), -e["count"]))
        for e in candidates[:3]:
            e["promoted"] = True
            e["promoted_win"] = w
        st["promoted_upto"] = w


def _record_question(st: dict, text: str, at_ms: int, *,
                     handled_by: str, category: str | None,
                     ai_answer: str | None = None,
                     topics: list | None = None,
                     comment_id: str | None = None) -> dict:
    """질문 1건을 누적 집계에 반영하고 해당 항목을 돌려준다.

    - 순위 기준: AI 답변·판매자 답변·미답변 구분 없이 **합산 누적 횟수**
    - 3분 윈도우(win)별 카운트를 함께 유지 → 윈도우 TOP3 선정에 사용
    - 대표 질문은 실제 고객 원문 중 가장 짧은 문장
    """
    key, e = _faq_lookup(st, text, topics)   # 유사 질문 3단 병합
    win = max(0, at_ms) // WINDOW_MS
    if e is None:
        st["faq_seq"] += 1
        e = st["faq"][key] = {
            "qid": f"fq_{st['faq_seq']:04d}",
            "representative_text": text, "count": 0, "examples": [],
            "category": category, "handled_by": handled_by,
            "ai_answer": None, "ai_answer_at": None,
            "seller_answer": None, "seller_answer_at": None, "draft": None,
            "topics": topics or [], "windows": {}, "last_ts": time.time(),
            "promoted": False, "promoted_win": None,
            # 병합된 원본 채팅 전체 (FE '질문 전체 보기' — 누적 횟수 클릭 시 노출)
            "originals": [],
        }
    e["count"] += 1
    e["windows"][win] = e["windows"].get(win, 0) + 1
    st["last_win"] = max(st["last_win"], win)
    e["originals"] = (e["originals"] + [
        {"comment_id": comment_id, "text": text, "at_ms": at_ms}
    ])[-200:]
    if text not in e["examples"]:
        e["examples"] = (e["examples"] + [text])[-5:]
    if len(text) < len(e["representative_text"]):
        e["representative_text"] = text
    if ai_answer and not e["ai_answer"]:
        e["ai_answer"] = ai_answer
        e["ai_answer_at"] = time.time()
    if category and not e["category"]:
        e["category"] = category
    if topics and not e["topics"]:
        e["topics"] = topics
    e["last_ts"] = time.time()
    return e


def _answered_by(e: dict) -> str:
    if e["seller_answer"]:
        return "SELLER"
    if e["ai_answer"]:
        return "AI"
    return "NONE"


def _faq_row(e: dict, win: int | None = None) -> dict:
    by = _answered_by(e)
    row = {
        "qid": e["qid"], "representative_text": e["representative_text"],
        "count": e["count"], "category": e["category"] or "기타",
        "handled_by": e["handled_by"],
        "answered_by": by,                                   # SELLER | AI | NONE
        "answered_by_label": {"SELLER": "판매자", "AI": "AI 라이브 매니저"}.get(by),
        "answer": e["seller_answer"] or e["ai_answer"],
        "answered_at": e["seller_answer_at"] or e["ai_answer_at"],  # epoch — FE 'n분 전'
        "promoted": e.get("promoted", False),
        "examples": e["examples"], "topics": e["topics"],
    }
    if win is not None:
        row["window_count"] = e["windows"].get(win, 0)
    return row


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
        # ── 판매자 확정 답변 우선 ──
        # 같은 질문(정규화 병합)에 판매자가 이미 [답변하기]로 대표 답변을 달았으면
        # LLM 을 거치지 않고 즉시 그 답변으로 응답한다 (방송 중 실시간 학습 효과)
        _, cached = _faq_lookup(st, c.text)
        if cached is not None and cached["seller_answer"]:
            _record_question(st, c.text, c.at_ms, handled_by=cached["handled_by"],
                             category=cached["category"], comment_id=c.comment_id)
            st["qseq"] += 1
            questions.append({
                "question_id": f"q_{st['qseq']:04d}", "comment_id": c.comment_id,
                "text": c.text, "handled_by": cached["handled_by"],
                "category": cached["category"], "at_ms": c.at_ms,
                "qid": cached["qid"],
                "answer": {"text": cached["seller_answer"],
                           "grounding": "SELLER_CONFIRMED", "strict": False,
                           "source": "판매자 확인 답변"},
            })
            continue

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
            unresolved: list = []
            if ans.meta.get("grounding") == "PARTIAL_GROUNDED":
                unresolved = _track_unanswered(live_id, c.text, ans)
                q["unresolved_topics"] = unresolved
            category = (q["category"] if q["handled_by"] == "PRODUCT"
                        else O_LABEL_NAMES.get(q["category"], q["category"]))
            rec = _record_question(st, c.text, c.at_ms, handled_by=q["handled_by"],
                                   category=category, ai_answer=ans.answer_text,
                                   topics=unresolved, comment_id=c.comment_id)
        else:  # UNANSWERABLE — 시청자 무노출, 미답변 창·집계로
            topics = _track_unanswered(live_id, c.text, ans)
            q["topics"] = topics
            category = (topics[0]["category"] if topics
                        else O_LABEL_NAMES.get(q["category"], q["category"]) or "기타")
            rec = _record_question(st, c.text, c.at_ms, handled_by="UNANSWERABLE",
                                   category=category, topics=topics, comment_id=c.comment_id)
        q["qid"] = rec["qid"]
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
# 기능 B-2. 집계된 Q&A — 판매자 화면·시청자 Q&A 버튼 공용
# =========================================================

@app.get(BASE + "/lives/{live_id}/faq", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def faq(live_id: str, top_n: int = 10):
    """자주 나오는 질문 누적 목록 (답변 포함).

    - 순위: AI 답변 + 판매자 답변 + 미답변 **합산 누적 횟수**
    - 각 항목: 대표질문·건수·답변·답변자(판매자/AI 라이브 매니저)·답변시각
    - 3분 윈도우가 끝날 때마다 그 윈도우 TOP3 신규 질문이 '공통 질문'으로 승격되고,
      이미 승격된 질문은 다음 윈도우에서 다시 수집되지 않는다 (카운트만 누적)
    """
    st = _live(live_id)
    _promote_windows(st)
    entries = sorted(st["faq"].values(), key=lambda e: (-e["count"], -e["last_ts"]))
    cur = st["last_win"]
    cur_top3 = sorted([e for e in st["faq"].values() if e["windows"].get(cur, 0) > 0],
                      key=lambda e: -e["windows"].get(cur, 0))[:3]
    return {
        "status": "ok", "live_id": live_id,
        "window_sec": WINDOW_MS // 1000,
        "qna": [_faq_row(e) for e in entries[:top_n]],
        "current_window": {"window_id": cur, "starts_at_ms": cur * WINDOW_MS,
                           "top3": [_faq_row(e, win=cur) for e in cur_top3]},
    }


@app.get(BASE + "/lives/{live_id}/faq/{qid}/comments", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def faq_comments(live_id: str, qid: str):
    """누적 건수 클릭 → 병합된 원본 채팅 전체 보기."""
    e = _find_by_qid(live_id, qid)
    return {"status": "ok", "qid": qid,
            "representative_text": e["representative_text"], "count": e["count"],
            "comments": e["originals"]}


# =========================================================
# 기능 B-3. 미답변 질문 창 (질문 요약) + 답변하기 플로우
# =========================================================

def _find_by_qid(live_id: str, qid: str) -> dict:
    for e in _live(live_id)["faq"].values():
        if e["qid"] == qid:
            return e
    raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})


@app.get(BASE + "/lives/{live_id}/unanswered", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def unanswered(live_id: str, top_n: int = 10):
    """미답변 질문 창 목록 — 'AI가 자동답변하지 않은 질문 중 상위 누적' + 답변 완료 구분."""
    st = _live(live_id)
    _promote_windows(st)
    rows = [e for e in st["faq"].values() if not e["ai_answer"]]
    rows.sort(key=lambda e: (-e["count"], -e["last_ts"]))
    pending = [e for e in rows if not e["seller_answer"]][:top_n]
    done = [e for e in rows if e["seller_answer"]][:top_n]
    return {"status": "ok", "live_id": live_id,
            "pending": [_faq_row(e) for e in pending],
            "answered": [_faq_row(e) for e in done]}


@app.get(BASE + "/lives/{live_id}/unanswered/{qid}", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def unanswered_detail(live_id: str, qid: str):
    """미답변 질문 클릭 → 상단: 참고 정보(관련 KB·이미지 자리) / 하단: 상담사 말투 답변 초안."""
    e = _find_by_qid(live_id, qid)

    # 참고 정보: 활성 상품 KB 에서 부분 관련 청크 검색 (근거가 아니라 판매자 참고용)
    from parts.p_part.rag_retriever import retrieve
    try:
        ref_chunks = [{"chunk_id": c["chunk_id"], "category": c["category"],
                       "text": c["text"], "source": c.get("source")}
                      for c in retrieve(e["representative_text"], top_k=3)]
    except Exception:
        ref_chunks = []

    # 답변 초안 (상담사 말투) — 1회 생성 후 캐시. 사실 미확인 부분은 표기.
    if not e["draft"]:
        from parts.p_part.rag_answer import build_style_text, retrieve_style_frames
        style = build_style_text(retrieve_style_frames(e["representative_text"]))
        ref_text = "\n".join(f"- {c['text']}" for c in ref_chunks) or "(관련 상품정보 없음)"
        prompt = (
            "라이브커머스 판매자가 방송에서 그대로 읽을 답변 초안을 1~2문장으로 작성하세요.\n"
            "규칙: 아래 참고 정보에 있는 사실만 사용하고, 확인되지 않는 내용은 문장에 넣지 말고 "
            "'[판매자 확인 필요: ...]' 로 비워 두세요. 새로운 수치·조건을 만들지 마세요.\n"
            f"상담사 말투 참고:\n{style}\n\n"
            f"고객 질문: {e['representative_text']}\n"
            f"참고 상품정보:\n{ref_text}\n"
        )
        import re as _re
        for attempt in range(3):
            try:
                draft = llm.generate_text(prompt)
                # 스타일 태그([INFORMATION] 등)가 출력에 섞이면 제거 (FE 노출용)
                e["draft"] = _re.sub(r"^\s*\[[A-Z_]+\]\s*", "", draft).strip()
                break
            except Exception as err:
                if attempt < 2 and ("429" in str(err) or "RESOURCE_EXHAUSTED" in str(err)):
                    time.sleep(15)  # 무료 등급 분당 한도 — 대기 후 재시도
                    continue
                e["draft"] = None
                e["draft_error"] = f"{type(err).__name__}: {err}"[:300]
                break
    return {"status": "ok", "qid": qid,
            "question": e["representative_text"], "count": e["count"],
            "examples": e["examples"], "topics": e["topics"],
            "reference": {"chunks": ref_chunks,
                          "images": []},   # 상품 이미지 URL — BE 연결 자리
            "draft": e["draft"],
            "draft_error": e.get("draft_error"),
            "seller_answer": e["seller_answer"]}


class SellerAnswerBody(BaseModel):
    answer_text: str = Field(min_length=1, max_length=1000)


@app.post(BASE + "/lives/{live_id}/unanswered/{qid}/answer", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def seller_answer(live_id: str, qid: str, body: SellerAnswerBody):
    """[답변하기] — 판매자 대표 답변 등록.

    ① 이 질문 그룹에 대표 답변이 달리고 (집계된 Q&A 에 '판매자' 답변으로 노출)
    ② 이후 같은/유사 질문은 LLM 없이 이 답변으로 즉시 응답되며
    ③ Live Knowledge(MCP) 에도 등록되어 상품 지식으로 축적된다
    """
    e = _find_by_qid(live_id, qid)
    e["seller_answer"] = body.answer_text.strip()
    e["seller_answer_at"] = time.time()

    lk = False
    try:
        from parts.p_part.mcp_servers.product_knowledge_server import add_live_product_fact
        fn = getattr(add_live_product_fact, "fn", add_live_product_fact)
        fn(live_id=live_id, question=e["representative_text"], answer=e["seller_answer"])
        lk = True
    except Exception:
        pass  # Live Knowledge 등록 실패해도 대표 답변 자체는 유효
    return {"status": "ok", "qid": qid, "live_knowledge_registered": lk}


# =========================================================
# 기능 B-4. 방송 종료 후 요약 — 전체 TOP15 + 카테고리별 정리
# =========================================================

@app.get(BASE + "/lives/{live_id}/summary", dependencies=[Depends(_auth)], tags=["B. 자주 나오는 질문 요약"])
def summary(live_id: str, top_n: int = 15):
    """방송 전체에서 많이 나온 질문 순위 + 카테고리별 그룹 (펀딩/결제/배송/상품 성능 등)."""
    st = _live(live_id)
    _promote_windows(st)
    entries = sorted(st["faq"].values(), key=lambda e: -e["count"])
    top = [_faq_row(e) for e in entries[:top_n]]

    by_cat: dict[str, list] = {}
    for e in entries:
        by_cat.setdefault(e["category"] or "기타", []).append(_faq_row(e))
    by_category = dict(sorted(by_cat.items(),
                              key=lambda kv: -sum(r["count"] for r in kv[1])))
    return {"status": "ok", "live_id": live_id,
            "total_questions": sum(e["count"] for e in entries),
            "unique_questions": len(entries),
            "top_questions": top,
            "by_category": by_category}


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

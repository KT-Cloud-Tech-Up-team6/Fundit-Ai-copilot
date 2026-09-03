"""라이브 목방송 테스트 서버.

목영상 + 실시간 채팅 화면을 띄우고, 팀원들의 채팅을 코파일럿 파이프라인에
그대로 통과시켜 실제 라이브 환경에서의 동작을 검증한다.

- 입장: 공유 비밀번호(SITE_PASSWORD) + 닉네임
- 방송: 진행자가 "방송 시작"을 누르면 모든 참가자의 영상이 같은 시점으로 동기화
- 채팅: 댓글 1건 = 분류 1회. ANSWER/UNANSWERABLE 만 봇이 채팅으로 답하고
  IGNORE 는 조용히 로그만 남긴다 (실서비스 동작과 동일)
- 로그: 전 댓글의 판정·라벨·faq_id·지연이 기록됨 → GET /api/export
  → `python -m webtest.report <url> <password>` 로 리포트 생성

로컬 실행: uvicorn webtest.app:app --reload
Vercel 배포: vercel.json 참고 (환경변수 GEMINI_API_KEY, SITE_PASSWORD, VIDEO_URL,
Upstash KV 연동 필요)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from orchestrator.service import CopilotService
from parts.o_part.part import OPart
from parts.p_part.part import PPart
from shared.schemas import Comment, Decision, LiveContext
from webtest import store

LIVE_ID = "9401"

app = FastAPI(title="LiveFunding Copilot — Live Test", version="0.1.0")

service = CopilotService(parts=[OPart(), PPart()])
# 평가와 동일한 목데이터 컨텍스트 (로보락 F25 ACE, 달성률 142%)
service.put_context(LiveContext(
    live_id=LIVE_ID,
    project_id="8812",
    broadcast={
        "start_at": "2026-09-01T20:00:00+09:00",
        "end_at": "2026-09-01T20:10:00+09:00",
        "vod_enabled": True,
    },
    funding={
        "deadline": "2026-09-15T23:59:59+09:00",
        "achieved_rate": 142,
        "target_amount": 30_000_000,
    },
    extra_slots={"early_bird_left": 6},
))


def _password() -> str:
    return os.getenv("SITE_PASSWORD", "team-only")


def _auth(password: str) -> None:
    if password != _password():
        raise HTTPException(status_code=401, detail="비밀번호가 다릅니다")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


class JoinBody(BaseModel):
    nickname: str
    password: str


@app.post("/api/join")
def join(body: JoinBody):
    _auth(body.password)
    nick = body.nickname.strip()[:20]
    if not nick:
        raise HTTPException(status_code=400, detail="닉네임을 입력하세요")
    return {
        "ok": True,
        "nickname": nick,
        "video_url": _video_url(),
        "backend": store.backend(),
    }


def _video_url() -> str:
    """진행자가 설정한 URL(state) > 환경변수 VIDEO_URL 순."""
    return store.get_state().get("video_url") or os.getenv("VIDEO_URL", "")


class ChatBody(BaseModel):
    nickname: str
    password: str
    text: str


@app.post("/api/chat")
def chat(body: ChatBody):
    _auth(body.password)
    text = body.text.strip()[:300]
    if not text:
        raise HTTPException(status_code=400, detail="빈 메시지")

    now = time.time()
    user_seq = store.append({
        "type": "user", "nick": body.nickname[:20], "text": text, "ts": now,
    })

    # 코파일럿 처리 (429 버스트는 1회 재시도로 완화)
    t0 = time.perf_counter()
    ans, error = None, None
    for attempt in range(2):
        try:
            ans = service.process(LIVE_ID, Comment(text=text, user_id=body.nickname))
            break
        except Exception as e:
            if attempt == 0 and ("429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)):
                time.sleep(1.2)
                continue
            error = str(e)[:300]
    latency_ms = round((time.perf_counter() - t0) * 1000)

    result = {
        "type": "result", "for_seq": user_seq, "nick": body.nickname[:20],
        "text": text, "ts": now, "latency_ms": latency_ms,
    }
    if error:
        result["error"] = error
    elif ans:
        result.update(
            decision=ans.decision.value, label=ans.label, faq_id=ans.faq_id,
            strict=ans.strict,
            ignored_reason=ans.ignored_reason.value if ans.ignored_reason else None,
        )
    store.append(result)

    # ANSWER → 채팅으로 답변 / UNANSWERABLE → 판매자 알림 (채팅 폴백 없음) / IGNORE → 침묵
    if ans is not None and ans.decision == Decision.UNANSWERABLE:
        store.append({
            "type": "alert", "ts": time.time(),
            "nick": body.nickname[:20], "text": text,
        })
    elif ans is not None and ans.answer_text:
        store.append({
            "type": "bot", "text": ans.answer_text, "ts": time.time(),
            "reply_nick": body.nickname[:20], "reply_text": text,
            "decision": ans.decision.value, "label": ans.label,
            "faq_id": ans.faq_id, "latency_ms": latency_ms,
        })

    return {
        "ok": error is None,
        "decision": ans.decision.value if ans else None,
        "error": error,
    }


@app.get("/api/state")
def state(password: str, since: int = 0):
    _auth(password)
    records = store.read(since)
    st = store.get_state()
    return {
        "now": time.time(),
        "started_at": st.get("started_at"),
        "video_url": st.get("video_url") or os.getenv("VIDEO_URL", ""),
        "seq": since + len(records),
        "messages": records,
    }


class PwBody(BaseModel):
    password: str


@app.post("/api/start")
def start(body: PwBody):
    _auth(body.password)
    st = store.get_state()
    if not st.get("started_at"):
        st["started_at"] = time.time()
        store.set_state(st)
        store.append({"type": "system", "text": "방송이 시작됐습니다", "ts": time.time()})
    return {"ok": True, "started_at": st["started_at"]}


@app.post("/api/reset")
def reset(body: PwBody):
    _auth(body.password)
    store.reset()
    return {"ok": True}


class VideoBody(BaseModel):
    password: str
    url: str


@app.post("/api/set-video")
def set_video(body: VideoBody):
    """영상 URL 직접 지정 (유튜브 비공개 링크 또는 mp4 주소)."""
    _auth(body.password)
    st = store.get_state()
    st["video_url"] = body.url.strip()
    store.set_state(st)
    return {"ok": True, "video_url": st["video_url"]}


UPLOAD_DIR = Path(__file__).parent / "uploads"


@app.post("/api/upload")
async def upload(password: str, file: UploadFile):
    """로컬 실행용 영상 업로드 (서버 디스크 저장).

    Vercel 서버리스는 요청 4.5MB 제한 + 디스크 휘발이라 이 경로를 쓰지 못한다
    → 프런트가 Blob 업로드 또는 URL 입력으로 우회한다.
    """
    _auth(password)
    UPLOAD_DIR.mkdir(exist_ok=True)
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    dest = UPLOAD_DIR / f"video{ext}"
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    url = f"/media/{dest.name}"
    st = store.get_state()
    st["video_url"] = url
    store.set_state(st)
    return {"ok": True, "video_url": url}


_MEDIA_TYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}


@app.get("/media/{name}")
def media(name: str, range: str | None = Header(default=None)):
    """업로드 영상 서빙. 시킹·라이브 동기화를 위해 Range 요청을 지원한다."""
    path = UPLOAD_DIR / Path(name).name
    if not path.exists():
        raise HTTPException(status_code=404)
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    size = path.stat().st_size

    def _iter(start: int, end: int, chunk: int = 1024 * 1024):
        with path.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    if range and range.startswith("bytes="):
        start_s, _, end_s = range[6:].partition("-")
        start = int(start_s or 0)
        end = min(int(end_s), size - 1) if end_s else size - 1  # 개방형 범위는 끝까지 스트리밍
        return StreamingResponse(_iter(start, end), status_code=206, media_type=media_type, headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
            "Accept-Ranges": "bytes",
        })
    return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})


@app.post("/api/blob-token")
def blob_token(body: PwBody):
    """Vercel Blob 클라이언트 업로드용 토큰. 비밀번호 확인 후에만 내준다."""
    _auth(body.password)
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise HTTPException(status_code=404, detail="BLOB_READ_WRITE_TOKEN 미설정 — 영상 URL 입력을 사용하세요")
    return {"token": token}


@app.get("/api/export")
def export(password: str):
    _auth(password)
    return {
        "exported_at": time.time(),
        "state": store.get_state(),
        "backend": store.backend(),
        "records": store.read(0),
    }


@app.get("/health")
def health():
    return {"ok": True, "backend": store.backend()}

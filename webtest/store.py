"""라이브 테스트 채팅 로그 저장소.

Vercel KV / Upstash Redis (REST) 가 설정돼 있으면 그걸 쓰고,
없으면 프로세스 메모리로 동작한다 (로컬 개발용 — 서버리스에서는 휘발됨).
"""
from __future__ import annotations

import json
import os

import httpx

KEY_LOG = "livetest:log"
KEY_STATE = "livetest:state"

_mem_log: list[str] = []
_mem_state: dict = {}


def _kv() -> tuple[str | None, str | None]:
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    return url, token


def backend() -> str:
    url, token = _kv()
    return "kv" if url and token else "memory"


def _redis(*cmd):
    url, token = _kv()
    r = httpx.post(url, json=list(cmd),
                   headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()["result"]


def append(record: dict) -> int:
    """레코드를 로그에 추가하고 새 로그 길이(=seq)를 돌려준다."""
    data = json.dumps(record, ensure_ascii=False)
    if backend() == "kv":
        return int(_redis("RPUSH", KEY_LOG, data))
    _mem_log.append(data)
    return len(_mem_log)


def read(since: int = 0) -> list[dict]:
    """since 인덱스부터의 레코드 목록."""
    if backend() == "kv":
        rows = _redis("LRANGE", KEY_LOG, since, -1) or []
    else:
        rows = _mem_log[since:]
    return [json.loads(r) for r in rows]


def get_state() -> dict:
    if backend() == "kv":
        raw = _redis("GET", KEY_STATE)
        return json.loads(raw) if raw else {}
    return dict(_mem_state)


def set_state(state: dict) -> None:
    if backend() == "kv":
        _redis("SET", KEY_STATE, json.dumps(state, ensure_ascii=False))
    else:
        _mem_state.clear()
        _mem_state.update(state)


def reset() -> None:
    if backend() == "kv":
        _redis("DEL", KEY_LOG, KEY_STATE)
    else:
        _mem_log.clear()
        _mem_state.clear()

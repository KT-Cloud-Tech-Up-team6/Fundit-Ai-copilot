"""Gemini 호출 래퍼. 모델명은 환경변수 GEMINI_MODEL 로 교체 가능."""
from __future__ import annotations

import os

from google import genai
from google.genai import types

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# 평가(V10 비용 산정)용 누적 사용량. reset_usage() 후 호출들을 돌리고 읽는다.
usage = {"calls": 0, "prompt_tokens": 0, "output_tokens": 0}


def reset_usage() -> None:
    usage.update(calls=0, prompt_tokens=0, output_tokens=0)


def _track(resp) -> None:
    usage["calls"] += 1
    um = getattr(resp, "usage_metadata", None)
    if um is not None:
        usage["prompt_tokens"] += um.prompt_token_count or 0
        usage["output_tokens"] += um.candidates_token_count or 0


_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true"):
            # GCP Vertex AI 경로 (gcloud auth application-default login 필요)
            _client = genai.Client(
                vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
            )
        else:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY 환경변수가 필요합니다 (.env 참고)")
            _client = genai.Client(api_key=api_key)
    return _client


def generate_json(prompt: str, response_schema, model: str | None = None):
    """구조화 출력(JSON mode)으로 1회 호출. response_schema 는 pydantic 모델."""
    resp = client().models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=response_schema,
        ),
    )
    _track(resp)
    return resp.parsed


def generate_text(prompt: str, model: str | None = None, temperature: float = 0.3) -> str:
    resp = client().models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=temperature),
    )
    _track(resp)
    return (resp.text or "").strip()

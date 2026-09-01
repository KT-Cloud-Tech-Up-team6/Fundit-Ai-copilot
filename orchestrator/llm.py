"""Gemini 호출 래퍼. 모델명은 환경변수 GEMINI_MODEL 로 교체 가능."""
from __future__ import annotations

import os

from google import genai
from google.genai import types

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
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
    return resp.parsed


def generate_text(prompt: str, model: str | None = None, temperature: float = 0.3) -> str:
    resp = client().models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=temperature),
    )
    return (resp.text or "").strip()

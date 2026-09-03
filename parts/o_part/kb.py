"""O파트 FAQ 지식베이스 로더."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


@lru_cache(maxsize=1)
def load_faq() -> dict[str, dict]:
    """faq_id → FAQ 항목 dict."""
    raw = json.loads((DATA_DIR / "platform_faq.json").read_text(encoding="utf-8"))
    return {f["faq_id"]: f for f in raw["platform_faq"]}


@lru_cache(maxsize=1)
def load_default_slots() -> dict:
    return json.loads((DATA_DIR / "slots.json").read_text(encoding="utf-8"))

from __future__ import annotations

import hashlib
import json
import logging


logger = logging.getLogger("uvicorn.error")


def question_hash(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()[:16]


def trace(event: str, **fields) -> None:
    payload = {
        "event": event,
        **fields,
    }

    logger.info(
        "COPILOT_TRACE %s",
        json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        ),
    )

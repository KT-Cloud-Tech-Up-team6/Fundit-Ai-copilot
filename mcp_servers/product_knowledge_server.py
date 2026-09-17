from pathlib import Path
from typing import Annotated, Literal
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

import json
import sys

from mcp.server import MCPServer
from pydantic import BaseModel, Field


# =========================================================
# 0. 프로젝트 경로
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT)
    )


# =========================================================
# 1. 기존 Retriever
# =========================================================

from core import rag_retriever


# =========================================================
# 2. Live Knowledge 저장 위치
# =========================================================

LIVE_KNOWLEDGE_FILE = (
    PROJECT_ROOT
    / "data"
    / "live_knowledge.json"
)

LIVE_KNOWLEDGE_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

FILE_LOCK = Lock()


# =========================================================
# 3. 출력 모델
# =========================================================

class ProductChunk(BaseModel):
    chunk_id: str
    category: str
    text: str
    strict: bool
    source: str


class SearchProductKnowledgeResult(BaseModel):
    question: str
    count: int
    matches: list[ProductChunk]


class GetProductChunkResult(BaseModel):
    found: bool
    chunk: ProductChunk | None = None


class LiveKnowledgeFact(BaseModel):
    fact_id: str
    live_id: str
    question: str
    answer: str
    source: str
    created_at: str
    updated_at: str


class AddLiveKnowledgeResult(BaseModel):
    action: Literal[
        "created",
        "updated",
    ]

    fact: LiveKnowledgeFact


class LiveKnowledgeMatch(BaseModel):
    score: float
    fact: LiveKnowledgeFact


class SearchLiveKnowledgeResult(BaseModel):
    question: str
    live_id: str
    count: int
    matches: list[LiveKnowledgeMatch]


class SearchProductContextResult(BaseModel):
    question: str
    live_id: str

    official_count: int
    official_matches: list[ProductChunk]

    live_count: int
    live_matches: list[LiveKnowledgeMatch]


# =========================================================
# 4. Live Knowledge 파일 처리
# =========================================================

def _load_live_facts() -> list[dict]:

    if not LIVE_KNOWLEDGE_FILE.exists():
        return []

    try:

        raw = LIVE_KNOWLEDGE_FILE.read_text(
            encoding="utf-8"
        )

        if not raw.strip():
            return []

        data = json.loads(raw)

        facts = data.get(
            "facts",
            []
        )

        if not isinstance(
            facts,
            list
        ):
            return []

        return facts

    except (
        json.JSONDecodeError,
        OSError,
    ):
        return []


def _save_live_facts(
    facts: list[dict]
) -> None:

    data = {
        "facts": facts
    }

    temp_file = (
        LIVE_KNOWLEDGE_FILE
        .with_suffix(".tmp")
    )

    temp_file.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    temp_file.replace(
        LIVE_KNOWLEDGE_FILE
    )


# =========================================================
# 5. 내부 공식 KB 검색
# =========================================================

def _search_official_knowledge(
    question: str,
    top_k: int
) -> list[ProductChunk]:

    results = rag_retriever.retrieve(
        question=question,
        top_k=top_k
    )

    return [
        ProductChunk(
            chunk_id=item["chunk_id"],
            category=item["category"],
            text=item["text"],
            strict=item["strict"],
            source=item["source"]
        )
        for item in results
    ]


# =========================================================
# 6. Live Knowledge 등록
# =========================================================

def _upsert_live_fact(
    live_id: str,
    question: str,
    answer: str,
    source: str
) -> AddLiveKnowledgeResult:

    normalized_question = (
        rag_retriever.normalize(
            question
        )
    )

    now = datetime.now(
        timezone.utc
    ).isoformat()

    with FILE_LOCK:

        facts = _load_live_facts()

        # -------------------------------------------------
        # 같은 방송 + 같은 질문이면 UPDATE
        # -------------------------------------------------

        for item in facts:

            if (
                item.get("live_id")
                != live_id
            ):
                continue

            stored_question = (
                item.get(
                    "question",
                    ""
                )
            )

            if (
                rag_retriever.normalize(
                    stored_question
                )
                == normalized_question
            ):

                item["answer"] = answer
                item["source"] = source
                item["updated_at"] = now

                _save_live_facts(
                    facts
                )

                return AddLiveKnowledgeResult(
                    action="updated",
                    fact=LiveKnowledgeFact(
                        **item
                    )
                )

        # -------------------------------------------------
        # 새로운 Fact 생성
        # -------------------------------------------------

        new_fact = {
            "fact_id":
                "live_fact_"
                + uuid4().hex[:12],

            "live_id":
                live_id,

            "question":
                question,

            "answer":
                answer,

            "source":
                source,

            "created_at":
                now,

            "updated_at":
                now,
        }

        facts.append(
            new_fact
        )

        _save_live_facts(
            facts
        )

    return AddLiveKnowledgeResult(
        action="created",
        fact=LiveKnowledgeFact(
            **new_fact
        )
    )


# =========================================================
# 7. Live Knowledge 검색
# =========================================================

def _search_live_knowledge(
    live_id: str,
    question: str,
    top_k: int
) -> list[LiveKnowledgeMatch]:

    with FILE_LOCK:
        facts = _load_live_facts()

    normalized_question = (
        rag_retriever.normalize(
            question
        )
    )

    question_words = set(
        rag_retriever.extract_words(
            question
        )
    )

    question_specs = set(
        rag_retriever.extract_spec_tokens(
            question
        )
    )

    scored = []


    for item in facts:

        if (
            item.get("live_id")
            != live_id
        ):
            continue

        stored_question = item.get(
            "question",
            ""
        )

        normalized_stored = (
            rag_retriever.normalize(
                stored_question
            )
        )

        score = 0.0


        # -------------------------------------------------
        # A. 질문 완전 일치
        # -------------------------------------------------

        if (
            normalized_question
            == normalized_stored
        ):
            score += 100


        # -------------------------------------------------
        # B. 한 질문이 다른 질문을 포함
        # -------------------------------------------------

        elif (
            normalized_question
            in normalized_stored
            or normalized_stored
            in normalized_question
        ):
            score += 40


        # -------------------------------------------------
        # C. 단어 중복
        # -------------------------------------------------

        stored_words = set(
            rag_retriever.extract_words(
                stored_question
            )
        )

        common_words = (
            question_words
            & stored_words
        )

        if len(common_words) >= 2:
            score += (
                len(common_words)
                * 5
            )


        # -------------------------------------------------
        # D. 숫자 + 단위 일치
        # -------------------------------------------------

        stored_specs = set(
            rag_retriever.extract_spec_tokens(
                stored_question
            )
        )

        common_specs = (
            question_specs
            & stored_specs
        )

        if common_specs:
            score += (
                len(common_specs)
                * 20
            )


        # -------------------------------------------------
        # 너무 약한 검색 결과 제거
        # -------------------------------------------------

        if score < 10:
            continue


        scored.append(
            (
                score,
                item
            )
        )


    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )


    results = []

    for score, item in scored[:top_k]:

        results.append(
            LiveKnowledgeMatch(
                score=score,
                fact=LiveKnowledgeFact(
                    **item
                )
            )
        )

    return results


# =========================================================
# 8. MCP Server
# =========================================================

mcp = MCPServer(
    "Product Knowledge MCP",
    instructions=(
        "라이브커머스 Product Agent가 "
        "공식 상품 KB 및 방송 중 판매자가 추가한 "
        "Live Knowledge를 조회할 수 있도록 한다. "
        "Live Knowledge는 방송 세션별로 관리한다."
    )
)


# =========================================================
# Tool 1
# 공식 상품 KB 검색
# =========================================================

@mcp.tool(
    title="상품 지식 검색"
)
def search_product_knowledge(
    question: Annotated[
        str,
        Field(
            description=
                "고객의 상품 관련 질문"
        )
    ],
    top_k: Annotated[
        int,
        Field(
            ge=1,
            le=10,
            description=
                "반환할 최대 KB Chunk 수"
        )
    ] = 3
) -> SearchProductKnowledgeResult:

    matches = (
        _search_official_knowledge(
            question=question,
            top_k=top_k
        )
    )

    return SearchProductKnowledgeResult(
        question=question,
        count=len(matches),
        matches=matches
    )


# =========================================================
# Tool 2
# 특정 공식 KB Chunk 조회
# =========================================================

@mcp.tool(
    title="상품 근거 Chunk 조회"
)
def get_product_chunk(
    chunk_id: Annotated[
        str,
        Field(
            description=
                "조회할 상품 KB Chunk ID"
        )
    ]
) -> GetProductChunkResult:

    chunks = (
        rag_retriever.load_chunks()
    )

    for item in chunks:

        if (
            item["chunk_id"]
            == chunk_id
        ):

            return GetProductChunkResult(
                found=True,
                chunk=ProductChunk(
                    chunk_id=
                        item["chunk_id"],

                    category=
                        item["category"],

                    text=
                        item["text"],

                    strict=
                        item["strict"],

                    source=
                        item["source"]
                )
            )

    return GetProductChunkResult(
        found=False,
        chunk=None
    )


# =========================================================
# Tool 3
# 판매자 답변 → Live Knowledge 등록
# =========================================================

@mcp.tool(
    title="Live Knowledge 등록"
)
def add_live_product_fact(
    live_id: Annotated[
        str,
        Field(
            description=
                "현재 라이브 방송 ID"
        )
    ],

    question: Annotated[
        str,
        Field(
            description=
                "AI가 해결하지 못했던 고객 질문"
        )
    ],

    answer: Annotated[
        str,
        Field(
            description=
                "판매자가 직접 제공한 답변"
        )
    ]
) -> AddLiveKnowledgeResult:

    live_id = live_id.strip()
    question = question.strip()
    answer = answer.strip()

    if not live_id:
        raise ValueError(
            "live_id는 비어 있을 수 없습니다."
        )

    if not question:
        raise ValueError(
            "question은 비어 있을 수 없습니다."
        )

    if not answer:
        raise ValueError(
            "answer는 비어 있을 수 없습니다."
        )

    return _upsert_live_fact(
        live_id=live_id,
        question=question,
        answer=answer,
        source="seller"
    )


# =========================================================
# Tool 4
# Live Knowledge 검색
# =========================================================

@mcp.tool(
    title="Live Knowledge 검색"
)
def search_live_product_fact(
    live_id: Annotated[
        str,
        Field(
            description=
                "현재 라이브 방송 ID"
        )
    ],

    question: Annotated[
        str,
        Field(
            description=
                "고객 상품 질문"
        )
    ],

    top_k: Annotated[
        int,
        Field(
            ge=1,
            le=10,
            description=
                "최대 검색 결과 수"
        )
    ] = 3

) -> SearchLiveKnowledgeResult:

    matches = _search_live_knowledge(
        live_id=live_id,
        question=question,
        top_k=top_k
    )

    return SearchLiveKnowledgeResult(
        question=question,
        live_id=live_id,
        count=len(matches),
        matches=matches
    )


# =========================================================
# Tool 5
# 공식 KB + Live Knowledge 통합 검색
# =========================================================

@mcp.tool(
    title="상품 Context 통합 검색"
)
def search_product_context(
    live_id: Annotated[
        str,
        Field(
            description=
                "현재 라이브 방송 ID"
        )
    ],

    question: Annotated[
        str,
        Field(
            description=
                "고객 상품 질문"
        )
    ],

    top_k: Annotated[
        int,
        Field(
            ge=1,
            le=10
        )
    ] = 3

) -> SearchProductContextResult:

    official_matches = (
        _search_official_knowledge(
            question=question,
            top_k=top_k
        )
    )

    live_matches = (
        _search_live_knowledge(
            live_id=live_id,
            question=question,
            top_k=top_k
        )
    )

    return SearchProductContextResult(
        question=question,
        live_id=live_id,

        official_count=
            len(official_matches),

        official_matches=
            official_matches,

        live_count=
            len(live_matches),

        live_matches=
            live_matches
    )


# =========================================================
# 직접 실행
# =========================================================

if __name__ == "__main__":
    mcp.run()
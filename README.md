# Live Commerce MCP + A2A Copilot

라이브커머스 방송 중 발생하는 고객 질문을 상품 정보에 근거해 답변하고,  
답변하지 못한 관심사를 판매자에게 전달하며, 판매자가 확인한 정보를 다시 활용할 수 있도록 설계한 AI Copilot 프로젝트입니다.

현재 Phase 3에서는 기존 Product RAG PoC를 기반으로 다음 기능을 구현했습니다.

- Product KB 기반 Grounded Answer
- `GROUNDED / PARTIAL_GROUNDED / NO_GROUNDED_INFO` 판정
- 미답변 세부 주제 분석 및 관심사 집계
- K쇼핑 상담 데이터 기반 Counselor Style RAG
- MCP 기반 Product Knowledge / Live Knowledge 연결
- Seller Feedback 및 Post-live Summary
- A2A 기반 Product Agent
- Product Agent A2A End-to-End 검증

> 현재 Product Agent 구현은 완료되었으며, Platform Agent의 A2A 인터페이스가 준비되면 Agent 간 연동을 진행할 예정입니다.

---

## 1. 프로젝트 목표

라이브커머스에서는 짧은 시간 안에 많은 고객 질문이 발생합니다.

단순 LLM 답변만 사용할 경우 다음 문제가 발생할 수 있습니다.

- 상품정보에 없는 내용을 추측해 답변
- 정확한 수치나 조건을 잘못 생성
- 복합 질문의 일부만 답변하고도 전체 답변으로 처리
- 반복적으로 발생하는 미답변 관심사를 판매자가 놓침
- AI 답변이 지나치게 기계적인 문장으로 출력
- 방송 중 판매자가 확인한 새로운 정보를 다시 활용하기 어려움

이 프로젝트는 이를 해결하기 위해 **상품 사실**, **상담 표현**, **실시간 학습 정보**, **Agent 간 통신**을 분리해서 설계했습니다.

---

## 2. 전체 구조

```text
Customer Question
        │
        ▼
   Product Agent
        │
        ├── Product KB Retrieval
        ├── Counselor Style Retrieval
        │
        ▼
      Gemini
        │
        ├── Grounding 판단
        ├── 상품 답변 생성
        └── 상담 말투 적용
        │
        ▼
Grounding Result
   │       │       │
   │       │       └── NO_GROUNDED_INFO
   │       └────────── PARTIAL_GROUNDED
   └────────────────── GROUNDED
                    │
                    ▼
          Unanswered Analyzer
                    │
                    ▼
            Interest Tracker
                    │
                    ▼
            Seller Attention
```

핵심 원칙은 다음과 같습니다.

```text
Product KB
= 상품 사실의 근거

K쇼핑 Counselor Style RAG
= 상담 말투와 표현 참고
```

K쇼핑 상담 데이터는 상품 사실의 근거로 사용하지 않습니다.

---

## 3. Product RAG

현재 테스트 상품은 KT알파 쇼핑 단일 상품을 기준으로 구성했습니다.

- Product ID: `5454434`
- Product: Roborock F25
- KB Format: JSON / Markdown
- Vector DB 사용 없음
- Embedding 사용 없음

관련 파일:

```text
data/
├── product_5454434.json
└── product_5454434.md
```

`core/rag_retriever.py`에서 키워드, 숫자, 단위, 카테고리 등을 이용해 관련 Product KB chunk를 검색합니다.

예시:

```text
건조 몇 분 걸려?
→ kb_p_018
→ 약 5분
```

---

## 4. Grounding

`core/rag_answer.py`

상품 답변은 다음 세 상태 중 하나로 반환합니다.

### GROUNDED

KB만으로 질문 전체에 답할 수 있는 경우

```text
Q. 건조 몇 분 걸려?

A. 빠른 건조 시간은 약 5분으로 확인됩니다.
```

### PARTIAL_GROUNDED

질문의 일부만 KB에서 확인되는 경우

```text
Q. 흡입력은 몇이고 앱으로 원격 조종도 가능해?

A. 최대 흡입력은 20,000Pa로 확인됩니다.
   앱 원격 조종 기능에 대해서는 현재 확인이 어렵습니다.
```

### NO_GROUNDED_INFO

질문에 필요한 정보가 KB에 없는 경우

```text
Q. 앱으로 원격 조종 가능해?

A. 문의주신 내용은 현재 제공된 상품정보에서 확인이 어렵습니다.
```

주요 Grounding 원칙:

- KB에 없는 내용 추론 금지
- 정확한 숫자는 KB에 직접 명시된 경우만 사용
- 서로 다른 기능의 숫자를 혼용하지 않음
- 하나의 옵션이 있다고 다른 옵션이 없다고 추론하지 않음
- 가능 여부 질문은 직접 근거가 있을 때만 확정
- 실제 답변에 사용한 chunk만 `source_chunk_ids`에 포함

---

## 5. Counselor Style RAG

상품 사실과 상담 말투를 분리하기 위해 K쇼핑 상담 데이터를 기반으로 Shared Counselor Style RAG를 구축했습니다.

```text
Product KB
→ WHAT TO SAY

Counselor Style RAG
→ HOW TO SAY
```

### 데이터 구축 결과

```text
전체 원본 레코드            1,005,233
전체 대화                      29,489
정제 Counselor Corpus           3,131
Runtime Style Frame                47
실제 Runtime 사용 Frame            40
```

관련 파일:

```text
data/kshopping_style/rag/
├── counselor_style_corpus.json
├── counselor_style_corpus_stats.json
├── counselor_style_search.json
└── counselor_style_search_stats.json
```

원본 K쇼핑 데이터는 Git에 포함하지 않습니다.

```text
data/kshopping_style/raw/
```

해당 경로는 `.gitignore`에 포함되어 있습니다.

### Runtime Style

현재 Runtime에서는 다음 유형을 사용합니다.

```text
CONFIRMATION
INFORMATION
GUIDANCE
POSITIVE
NEGATIVE
NO_INFORMATION
APOLOGY
```

예시:

```text
[INFORMATION]
{안내 정보}로 확인됩니다.

[CONFIRMATION]
{확인된 정보}로 확인됩니다.

[POSITIVE]
{문의 내용}은 가능합니다.

[NO_INFORMATION]
문의주신 내용은 현재 확인이 어렵습니다.
```

Style Frame은 `STYLE_ONLY`로 사용하며 상품 사실의 근거로 사용하지 않습니다.

또한 별도의 Gemini Rewrite 호출을 추가하지 않고, 기존 Answer Generation 호출에 Product KB와 Style Frame을 함께 전달합니다.

---

## 6. Unanswered Analyzer / Interest Tracker

`core/unanswered_analyzer.py`  
`core/interest_tracker.py`

`PARTIAL_GROUNDED` 또는 `NO_GROUNDED_INFO`일 경우 해결되지 않은 세부 질문을 분석합니다.

예시:

```json
{
  "category": "APP_REMOTE",
  "topic_key": "SMART_CONNECTIVITY",
  "representative_question": "앱으로 원격 조종할 수 있나요?"
}
```

이를 Interest Tracker에서 집계해 판매자가 반복적으로 발생하는 미답변 관심사를 확인할 수 있도록 합니다.

현재 호출 구조:

```text
GROUNDED
→ Gemini 1회

PARTIAL / NO
→ Answer Generation 1회
→ Unanswered Analyzer 1회
→ 최대 Gemini 2회
```

Grounding과 미답변 분석 품질을 유지하기 위해 현재는 2-step 구조를 사용합니다.

---

## 7. Product Copilot

`services/product_copilot.py`

P(Product) 질문 처리의 단일 진입점입니다.

```python
process_product_question(question)
```

처리 흐름:

```text
Product Question
      │
      ▼
Product RAG
      │
      ▼
Grounding Status
      │
      ├── GROUNDED
      │      └── Answer
      │
      └── PARTIAL / NO
             │
             ▼
       Unanswered Analyzer
             │
             ▼
        Interest Tracker
```

반환 예시:

```json
{
  "question": "흡입력은 몇이고 앱으로 원격 조종도 가능해?",
  "grounding_status": "PARTIAL_GROUNDED",
  "answer": "최대 흡입력은 20,000Pa로 확인됩니다. 앱 원격 조종 기능에 대해서는 현재 확인이 어렵습니다.",
  "source_chunk_ids": [
    "kb_p_005"
  ],
  "unresolved_topics": [
    {
      "category": "APP_REMOTE",
      "topic_key": "SMART_CONNECTIVITY",
      "representative_question": "앱이나 와이파이로 원격 조작할 수 있나요?"
    }
  ],
  "needs_seller_attention": true
}
```

> 현재 Product Copilot은 입력이 이미 Product 질문이라고 가정합니다.  
> 전체 P/O/DROP 라우팅은 Product Agent 범위에 포함하지 않습니다.

---

## 8. MCP / Live Knowledge

`mcp_servers/product_knowledge_server.py`

MCP는 Agent와 Product Knowledge / Live Knowledge를 연결합니다.

현재 주요 Tool:

```text
search_product_knowledge
get_product_chunk
add_live_product_fact
search_live_product_fact
search_product_context
```

방송 중 판매자가 직접 확인한 정보는 Live Knowledge로 저장할 수 있습니다.

```text
Seller Feedback
      │
      ▼
MCP Product Knowledge Server
      │
      ▼
Live Knowledge
      │
      ▼
Post-live Summary
```

관련 서비스:

```text
services/
├── seller_feedback.py
├── post_live_feedback.py
└── post_live_summary.py
```

---

## 9. A2A Product Agent

Product Copilot은 현재 A2A Product Agent로 구현되어 있습니다.

관련 파일:

```text
agents/
├── __init__.py
├── product_agent_executor.py
└── product_agent_server.py
```

구조:

```text
A2A Client
    │
    ▼
Agent Card Discovery
    │
    ▼
Product Agent Server
    │
    ▼
ProductAgentExecutor
    │
    ▼
process_product_question()
    │
    ▼
Product RAG / Style RAG
    │
    ▼
Gemini
    │
    ▼
A2A Response
```

기존 Product Copilot을 다시 구현하지 않고 `ProductAgentExecutor`가 `process_product_question()`을 호출하는 Wrapper 형태로 구성했습니다.

### Agent Card

```text
GET /.well-known/agent-card.json
```

로컬 기준:

```text
http://127.0.0.1:9999/.well-known/agent-card.json
```

### A2A JSON-RPC Endpoint

```text
/a2a/product
```

로컬 기준:

```text
http://127.0.0.1:9999/a2a/product
```

Agent Skill:

```text
product_question_answering
```

---

## 10. A2A End-to-End 검증

다음 세 Grounding 상태에 대해 실제 A2A E2E 테스트를 완료했습니다.

### GROUNDED

```text
건조 몇 분 걸려?
```

```json
{
  "question": "건조 몇 분 걸려?",
  "grounding_status": "GROUNDED",
  "answer": "빠른 건조 시간은 약 5분으로 확인됩니다.",
  "source_chunk_ids": [
    "kb_p_018"
  ],
  "unresolved_topics": [],
  "needs_seller_attention": false
}
```

### NO_GROUNDED_INFO

```text
앱으로 원격 조종 가능해?
```

```json
{
  "question": "앱으로 원격 조종 가능해?",
  "grounding_status": "NO_GROUNDED_INFO",
  "answer": "문의주신 내용은 현재 제공된 상품정보에서 확인이 어렵습니다.",
  "source_chunk_ids": [],
  "unresolved_topics": [
    {
      "category": "APP_REMOTE",
      "topic_key": "SMART_CONNECTIVITY",
      "representative_question": "앱으로 원격 조종할 수 있나요?"
    }
  ],
  "needs_seller_attention": true
}
```

### PARTIAL_GROUNDED

```text
흡입력은 몇이고 앱으로 원격 조종도 가능해?
```

```json
{
  "question": "흡입력은 몇이고 앱으로 원격 조종도 가능해?",
  "grounding_status": "PARTIAL_GROUNDED",
  "answer": "최대 흡입력은 20,000Pa로 확인됩니다. 앱 원격 조종 기능에 대해서는 현재 확인이 어렵습니다.",
  "source_chunk_ids": [
    "kb_p_005"
  ],
  "unresolved_topics": [
    {
      "category": "APP_REMOTE",
      "topic_key": "SMART_CONNECTIVITY",
      "representative_question": "앱이나 와이파이로 원격 조작할 수 있나요?"
    }
  ],
  "needs_seller_attention": true
}
```

A2A를 통해 호출한 경우에도 다음 데이터가 정상적으로 유지되는 것을 확인했습니다.

```text
grounding_status
answer
source_chunk_ids
unresolved_topics
needs_seller_attention
```

---

## 11. 프로젝트 구조

```text
.
├── agents/
│   ├── product_agent_executor.py
│   └── product_agent_server.py
│
├── core/
│   ├── counselor_style_retriever.py
│   ├── interest_tracker.py
│   ├── rag_answer.py
│   ├── rag_retriever.py
│   └── unanswered_analyzer.py
│
├── data/
│   ├── product_5454434.json
│   ├── product_5454434.md
│   └── kshopping_style/
│       └── rag/
│
├── mcp_servers/
│   └── product_knowledge_server.py
│
├── scripts/
│   ├── build_counselor_style_corpus.py
│   ├── build_counselor_style_search.py
│   ├── clean_counselor_data.py
│   ├── filter_shared_counselor_style.py
│   └── split_counselor_style_pipeline.py
│
├── services/
│   ├── live_product_copilot.py
│   ├── post_live_feedback.py
│   ├── post_live_summary.py
│   ├── product_copilot.py
│   └── seller_feedback.py
│
├── tests/
├── .gitignore
├── README.md
└── requirements.txt
```

---

# Live Commerce MCP + A2A Copilot

라이브커머스 방송 중 발생하는 고객 질문을 분석하고, 상품 정보에 근거한 답변을 제공하며, AI가 해결하지 못한 질문을 판매자 관심사로 집계하는 **AI Seller Copilot** 프로젝트입니다.

기존 Product RAG PoC를 기반으로 **MCP(Model Context Protocol)** 기반 Live Knowledge 구조를 추가했으며, 향후 Product Agent와 Platform Agent 간 **A2A(Agent-to-Agent)** 협업 구조로 확장하는 것을 목표로 합니다.

---

## 1. Project Overview

라이브커머스에서는 짧은 시간 동안 많은 댓글과 질문이 동시에 발생합니다.

```text
고객 질문
   ↓
Product RAG
   ↓
상품 KB Retrieval
   ↓
Gemini Grounding
   ↓
GROUNDED            → 근거 기반 답변
PARTIAL_GROUNDED    → 미해결 부분 분석
NO_GROUNDED_INFO    → 미답변 관심사 집계
```

AI가 해결하지 못한 질문은 Category와 Topic 단위로 집계해 판매자가 고객 관심사를 확인할 수 있도록 합니다.

방송 종료 후에는 전체 미답변 관심사에서 TOP 2 질문을 선정하고, 판매자가 직접 제공한 답변을 MCP Live Knowledge에 저장해 구매자용 Post-Live Q&A로 활용합니다.

---

## 2. Core Features

### Product RAG

상품 상세정보를 Knowledge Base로 구성하고 고객 질문과 관련된 Chunk를 검색합니다.

현재 Retrieval은 Vector DB나 Embedding 대신 다음 정보를 활용합니다.

- Keyword
- Rule
- 숫자
- 단위
- 상품 사양 표현

예시:

```text
Q. 흡입력 몇 파스칼이에요?

↓ Retrieval

kb_p_005
최대 흡입력은 20,000Pa입니다.
```

### Grounding

Gemini를 활용해 검색된 상품 정보만을 기반으로 답변 가능 여부를 판단합니다.

```text
GROUNDED
PARTIAL_GROUNDED
NO_GROUNDED_INFO
```

상품 KB에 존재하지 않는 정보는 임의로 생성하지 않는 것을 기본 원칙으로 합니다.

### Unanswered Interest Tracking

```text
PARTIAL / NO
      ↓
Unanswered Analyzer
      ↓
Category / Topic
      ↓
Interest Tracker
```

대표 질문은 AI가 새로 만들지 않고 실제 시청자 질문 중 가장 많이 등장한 문장을 사용합니다.

예시:

```text
앱으로 원격 조작 가능한가요?
앱으로 원격 조작 가능한가요?
앱 원격 조작 돼요?

↓

앱·원격 연결 | 3건
대표 질문: 앱으로 원격 조작 가능한가요?
```

---

## 3. MCP Product Knowledge Server

현재 구현된 MCP Tools:

```text
search_product_knowledge
get_product_chunk
add_live_product_fact
search_live_product_fact
search_product_context
```

기본 구조:

```text
MCP Client
     ↓
Product Knowledge MCP Server
     ↓
rag_retriever
     ↓
Product KB
```

---

## 4. MCP Live Knowledge

MCP를 단순 상품 조회 Wrapper로만 사용하지 않고, **판매자가 제공한 답변을 동적으로 갱신되는 Knowledge로 활용**합니다.

```text
AI가 답변하지 못함
        ↓
미답변 관심사 집계
        ↓
판매자 답변
        ↓
MCP
        ↓
Live Knowledge 등록
        ↓
다른 AI 기능에서 재사용
```

이를 통해 Product Agent와 동적으로 변경되는 Knowledge를 분리하여 연결할 수 있습니다.

---

## 5. Post-Live Q&A

방송 종료 후 전체 미답변 관심사를 Topic 기준으로 집계합니다.

```text
전체 방송 미답변 질문
        ↓
Topic별 누적
        ↓
TOP 2 선정
        ↓
실제 대표 고객 질문
        ↓
판매자 답변
        ↓
MCP Live Knowledge
        ↓
구매자용 Post-Live Q&A
```

판매자는 시스템이 선정한 질문에 대한 **답변만 입력**합니다.

예시:

```text
1. 앱·원격 연결 | 관심 5건

Q. 앱으로 원격 조작 가능한가요?
판매자 답변 > 앱을 통한 원격 조작 기능은 지원하지 않습니다.
```

---

## 6. Knowledge Feedback Loop

```text
Viewer Question
      ↓
Product RAG
      ↓
Grounding
      ↓
답변 불가능
      ↓
Unanswered Interest
      ↓
Seller Feedback
      ↓
MCP Live Knowledge
      ↓
Knowledge Reuse
      ↓
Post-Live Q&A
```

기존에는 미답변 질문을 판매자에게 전달하는 데서 끝났다면, 현재 구조에서는 판매자의 피드백을 다시 AI가 활용할 수 있는 Knowledge로 연결합니다.

---

## 7. Project Structure

```text
.
├── core/
│   ├── interest_tracker.py
│   ├── rag_answer.py
│   ├── rag_retriever.py
│   └── unanswered_analyzer.py
│
├── data/
│   ├── product_5454434.json
│   └── product_5454434.md
│
├── mcp_servers/
│   └── product_knowledge_server.py
│
├── services/
│   ├── product_copilot.py
│   ├── live_product_copilot.py
│   ├── seller_feedback.py
│   ├── post_live_feedback.py
│   └── post_live_summary.py
│
├── scripts/
│   └── manual_live_session.py
│
├── tests/
│   ├── test_product_mcp.py
│   ├── test_live_knowledge_mcp.py
│   ├── test_post_live_interest.py
│   └── test_live_product_copilot.py
│
├── requirements.txt
└── README.md
```

---

## 8. Tech Stack

- Python
- Google Vertex AI
- Gemini 3.5 Flash-Lite
- MCP Python SDK
- Pydantic
- JSON
- Markdown Knowledge Base

---

## 9. Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 10. Tests

```bash
python3 -m tests.test_product_mcp
python3 -m tests.test_live_knowledge_mcp
python3 -m tests.test_post_live_interest
python3 -m tests.test_live_product_copilot
```

수동 E2E 테스트:

```bash
python3 -m scripts.manual_live_session
```

주요 명령어:

```text
/dashboard
/end
```

---

## 11. Development Status

### Completed

- Product RAG
- Rule / Keyword / Numeric Retrieval
- Gemini Grounding
- GROUNDED / PARTIAL_GROUNDED / NO_GROUNDED_INFO 처리
- Unanswered Topic Analysis
- Interest Tracking
- 실제 시청자 대표 질문 선정
- 방송 전체 관심사 TOP 2 선정
- MCP Product Knowledge Server
- MCP Live Knowledge
- Seller Feedback 등록
- Post-Live Q&A
- Manual E2E Test

### Next

- Seller Answer Guardrail
- Automated E2E Test
- Comment Filter / Router
- Product Agent 구조화
- Platform Agent 연동
- A2A Agent Handoff
- Agent Trace / Evaluation

---

## 12. Planned A2A Architecture

A2A는 현재 구현 예정 단계입니다.

```text
                     Coordinator
                    /           \
                  A2A           A2A
                   ↓             ↓
           Product Agent    Platform Agent
                   │             │
                  MCP        Platform Data
                   │
          Product Knowledge
```

MCP는 **Agent와 Knowledge / Tool의 연결**, A2A는 **Agent와 Agent 간 역할 분담 및 협업**을 담당하도록 설계할 예정입니다.

---

## Goal

본 프로젝트의 목표는 단순한 라이브커머스 Q&A 챗봇이 아니라,

**상품 정보 Grounding, 실시간 고객 관심사 분석, Human-in-the-loop Knowledge Update, MCP 기반 Knowledge 연결, A2A 기반 Agent 협업을 결합한 Live Commerce AI Copilot을 구축하는 것**입니다.

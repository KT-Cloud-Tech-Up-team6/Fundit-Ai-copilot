# A2A·MCP 통합 작업 인수인계

**작성일** 2026-09-17
**대상 저장소** `KT-Cloud-Tech-Up-team6/Fundit-Ai-copilot`
**현재 상태** 원격 `main` = `a88fd64` (통합 전으로 원복 완료)

---

## 0. 지금 상태 먼저 확인

| 항목 | 상태 |
|---|---|
| 원격 `main` | `a88fd64` 로 원복됨 — 통합 작업 전과 동일 |
| `live-commerce-mcp-a2a-copilot` (현서님 원본) | 무사. 손대지 않음 |
| `Funddit-Ai-highlight` (하이라이트 원본) | 무사. 손대지 않음 |
| `feat/a2a-agent`, `feat/highlight` 브랜치 | **원격에 남아 있음** — 삭제 권한이 막혀 못 지움 |
| 로컬 백업 브랜치 | `backup/before-revert-20260917` 에 전체 작업 보존 |

### 먼저 해야 할 일

**하이라이트 브랜치 삭제** — 코파일럿 레포에 하이라이트가 섞이면 안 되므로.

```bash
git push origin --delete feat/highlight
```

`Funddit-Ai-highlight` 레포에 원본이 온전히 있으므로 지워도 아무것도 유실되지 않는다.

`feat/a2a-agent` 는 현서님 원본(`live-commerce-mcp-a2a-copilot`)을 그대로 가져온 것이라
남겨둬도 무방하다. 정리하려면 같은 방식으로 삭제.

---

## 1. 무엇을 하는 작업인가

현서님이 별도 저장소(`live-commerce-mcp-a2a-copilot`)에서 만든 **A2A Agent · MCP 서버 ·
상담 문체 RAG** 를 `Fundit-Ai-copilot` 에 합쳐 **하나의 코파일럿**으로 만드는 작업.

합치기 전에는 이렇게 나뉘어 있었다.

| | `Fundit-Ai-copilot` | `live-commerce-mcp-a2a-copilot` |
|---|---|---|
| 채팅 분류(라우터) | 있음 | 없음 |
| 플랫폼·펀딩 답변 | 있음 (`parts/o_part/`) | 없음 |
| 상품 답변 | 구버전 (`parts/p_part/`) | 신버전 (`core/`) |
| 상담 문체 | 없음 | 있음 |
| 미답변 관심사 집계 | 구버전 | 신버전 |
| A2A · MCP | 없음 | 있음 |

**현서님 코드는 라우터 앞단이 비어 있다.** 의도적이다.
`services/product_copilot.py` 주석: *"P/O/DROP 라우팅은 현재 범위에 포함하지 않는다"*
Agent Card: *"상품 질문이 이미 Product 영역으로 전달되었다고 가정합니다"*

즉 **두 저장소는 서로의 빈칸을 채우는 관계**다. 합치면 완성된다.

---

## 2. 작업 순서

### STEP 1 — 원격 추가 후 머지

```bash
cd <Fundit-Ai-copilot 작업 폴더>
git checkout main

git remote add a2a https://github.com/KT-Cloud-Tech-Up-team6/live-commerce-mcp-a2a-copilot.git
git fetch a2a --no-tags

git merge a2a/main --allow-unrelated-histories --no-commit
```

> `--allow-unrelated-histories` 가 필요한 이유: 두 저장소는 공통 조상이 없다.

**결과: 충돌 3건. 전부 코드가 아니다.**

```
CONFLICT (add/add): .gitignore
CONFLICT (add/add): README.md
CONFLICT (add/add): requirements.txt
```

파이썬 코드는 경로가 겹치지 않아 전부 자동 머지된다
(`agents/`, `core/`, `mcp_servers/`, `services/`, `scripts/`, `data/`, `tests/` 신규 추가).

### STEP 2 — 충돌 3건 해소

**`requirements.txt`** — 양쪽 합집합

```
# 공용
google-genai>=2.20
pydantic>=2.13
python-dotenv>=1.0
httpx>=0.27

# API 서버 (BE 연동 · webtest)
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9

# A2A Agent · MCP
a2a-sdk[http-server]>=1.1.2
mcp>=1.2
```

**`.gitignore`** — 양쪽 합집합. A2A 쪽에서 추가로 필요한 항목:

```
test_post_live_interest.json
data/live_knowledge.json
data/kshopping_style/raw/
```

**`README.md`** — 통합 구조로 재작성 (5장 참고)

### STEP 3 — 인증 통일 (필수)

**이걸 안 하면 통합 후 상품 답변이 전부 죽는다.**

현서님 코드는 **Vertex AI 전용**이고, 모듈 최상단에서 클라이언트를 즉시 만든다.
`Fundit-Ai-copilot` 은 `GEMINI_API_KEY` 로 동작하므로 그대로 합치면 import 만 해도 터진다.

대상 2곳:

**① `core/rag_answer.py`**

```python
# 삭제
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "live-copliot")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-3.5-flash-lite")
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# 교체
MODEL_ID = os.getenv(
    "GEMINI_MODEL_ID",
    os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
)


def client():
    """orchestrator/llm.py 가 GEMINI_API_KEY / Vertex AI 양쪽을 처리한다."""
    return llm.client()
```

import 추가: `from orchestrator import llm`
호출부 수정: `client.models.generate_content(` → `client().models.generate_content(`

**② `core/unanswered_analyzer.py`** — 동일하게 처리

```python
# 삭제
PROJECT_ID = "live-copliot"
LOCATION = "global"
MODEL = "gemini-3.5-flash-lite"
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# 교체
import os
from orchestrator import llm

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def client():
    return llm.client()
```

호출부: `client.models.generate_content(` → `client().models.generate_content(`

> **`live-copliot`** 은 현서님 개인 GCP 프로젝트 ID 가 코드에 박힌 것이다(오타 포함).
> 본인 주석에 *"새 프로젝트 Billing 활성화 전까지 fallback / 나중에는 환경변수만 바꾸면 전환 가능"*
> 이라고 되어 있다. 위 수정이 그 의도대로 만드는 것이다.
> 나중에 GCP 로 가려면 `.env` 에 `GOOGLE_GENAI_USE_VERTEXAI=1` 만 넣으면 된다.

부수 효과로 **모듈 최상단 즉시 생성 → 지연 생성**이 되어, import 만으로 인증을 타던 문제도 사라진다.

### STEP 4 — A2A Agent 서버 `.env` 로드 (버그 수정)

**이것도 안 하면 A2A 로 들어온 상품 질문이 전부 실패한다.**

`agents/product_agent_server.py` 에 `load_dotenv()` 가 없다.
`api/main.py`, `webtest/app.py` 에는 있는데 Agent 서버만 빠져 있다.
그래서 `GEMINI_API_KEY` 를 못 읽고 모든 요청이 `PRODUCT_AGENT_EXECUTION_FAILED` 로 떨어진다.

```python
import os

import uvicorn
from dotenv import load_dotenv

# API 키·모델 설정을 .env 에서 읽는다 (api/main.py, webtest/app.py 와 동일).
load_dotenv()
```

### STEP 5 — 상품 RAG 정본을 `core/` 로 일원화

통합 직후에는 **두 벌의 상품 RAG 가 공존**한다.

| | 상담 문체 | 크기 |
|---|---|---|
| `core/rag_answer.py` (현서님 신버전) | **있음** | 751줄 |
| `parts/p_part/rag_answer.py` (구버전) | 없음 | 422줄 |

그런데 서빙(`api/main.py`, `webtest/app.py`)은 **구버전을 본다.**
같은 질문에 답이 달라진다.

```
"머리카락 엉킴 방지 되나요?"
  parts/p_part → UNANSWERABLE  (못 찾음)
  core/        → GROUNDED      (JawScrapers 구조 설명)
```

**import 경로만 바꾸면 된다.** API 가 완전히 호환된다(함수 시그니처·반환 구조 동일 확인).

대상 파일: `api/main.py`, `webtest/app.py`, `parts/p_part/part.py`,
`eval/o_part/run_eval.py`, `eval/o_part/smoke_offline.py`,
`eval/p_part/evaluate_rag.py`, `eval/p_part/mvp_live_test.py`, `eval/p_part/mvp_replay_test.py`

```bash
sed -i \
  -e 's/from parts\.p_part\.rag_answer import/from core.rag_answer import/' \
  -e 's/from parts\.p_part\.rag_retriever import/from core.rag_retriever import/' \
  -e 's/from parts\.p_part\.interest_tracker import/from core.interest_tracker import/' \
  -e 's/from parts\.p_part\.unanswered_analyzer import/from core.unanswered_analyzer import/' \
  <파일들>
```

이후 구버전 중복 모듈 제거 (2,391줄):

```bash
git rm parts/p_part/rag_answer.py parts/p_part/rag_retriever.py \
       parts/p_part/interest_tracker.py parts/p_part/unanswered_analyzer.py
git rm -r parts/p_part/data          # data/ 의 KB 와 내용 동일 (md5 확인함)
```

`parts/p_part/part.py` 는 **남긴다.** `CopilotPart` 계약 어댑터 역할.
단, KB 경로를 `data/` 로 바꿔야 한다.

```python
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
```

---

## 3. 검증

```bash
pip install -r requirements.txt

# ① 오프라인 구조 검증 (LLM 없이)
python -m eval.o_part.smoke_offline
#   기대: SMOKE OK — 구조·KB·슬롯 치환 정상

# ② A2A Agent 서버 기동 (별도 터미널)
python -m agents.product_agent_server
#   기대: http://127.0.0.1:9999

# ③ Agent Card 확인
curl http://127.0.0.1:9999/.well-known/agent-card.json
#   기대: name = "Live Commerce Product Agent"

# ④ 라이브 테스트 화면
uvicorn webtest.app:app --port 8000
```

### 실측 결과 (통합 후 확인한 값)

| 항목 | 결과 |
|---|---|
| 라우팅 (잡담/플랫폼/상품) | 5/5 정확 |
| 플랫폼 답변 | 정상 — FAQ 원문 + 날짜 슬롯 치환 |
| 상품 답변 Grounding | 정상 — GROUNDED / NO_GROUNDED_INFO |
| 상담 문체 적용 | 정상 |
| 미답변 관심사 집계 | 정상 |
| A2A 엔드투엔드 | 6/6 |

실제 응답 예시:

```
Q: 흡입력이 얼마인가요?    → GROUNDED  최대 흡입력은 20,000Pa로 확인됩니다.  [kb_p_005]
Q: 무게가 얼마나 되나요?   → GROUNDED  본체 4.2kg, 도크 포함 5.7kg으로 확인됩니다.  [kb_p_003]
Q: 카펫에도 쓸 수 있나요?  → NO_GROUNDED_INFO  (미답변: CARPET_RUG_USE)
```

**상담 문체가 실제로 적용된다.** 코퍼스 프레임이 `INFORMATION: {안내 정보}로 확인됩니다` 인데
답변이 `"20,000Pa로 확인됩니다"` 로 나온다. KB 원문 그대로가 아니라 말투가 입혀진 것이다.

**관심사 집계도 동작한다.** "카펫에도 쓸 수 있나요 / 러그 위에서도 되나요 / 카펫 모드 있어요?"
3건을 전부 `CARPET_RUG_USE` 하나로 묶어 count 3 으로 판매자 화면에 올린다.

### A2A 테스트 스크립트

`a2a-sdk` 1.x 는 protobuf 기반이라 손으로 JSON-RPC 를 만들면 잘 안 된다.
SDK 클라이언트를 쓰는 게 맞고, 아래 두 가지를 주의한다.

- `SendMessageRequest(message=...)` — `request=` 가 아니다
- 응답은 `ev.message.parts[].text` 에 있다

```python
import asyncio, json, httpx
from a2a.client import A2ACardResolver, ClientFactory, ClientConfig
from a2a.helpers import new_text_message
from a2a.types import SendMessageRequest

async def main():
    async with httpx.AsyncClient(timeout=180) as hx:
        card = await A2ACardResolver(hx, "http://127.0.0.1:9999").get_agent_card()
        cli = ClientFactory(ClientConfig(httpx_client=hx, streaming=False)).create(card)
        req = SendMessageRequest(message=new_text_message("흡입력이 얼마인가요?"))
        async for ev in cli.send_message(req):
            m = getattr(ev, "message", None)
            if not m:
                continue
            for p in m.parts:
                if p.text:
                    print(json.loads(p.text))

asyncio.run(main())
```

---

## 4. 통합 후 남는 문제 (미해결 — 반드시 읽을 것)

### 상품이 로보락 1개로 고정되어 있다

실제 서비스는 판매자가 상품을 등록하면 앞단에서 상품정보가 넘어오는 구조인데,
현재 코드는 **파일명이 하드코딩**되어 있다.

```python
# core/rag_retriever.py:8
MD_FILE = PROJECT_ROOT / "data" / "product_5454434.md"     ← 고정

# core/rag_retriever.py:730
def retrieve(question, top_k=3):                           ← product_id 없음
    chunks = load_chunks()                                 ← 매 호출 파일 재파싱
```

**실제로 오염된다.** 확인한 결과:

```
"이 옷 사이즈 어떻게 나와요?"  →  kb_p_002 (로보락 청소기 크기 262×221×1100mm)
```

최종 답변은 LLM Grounding 이 막았지만(`NO_GROUNDED_INFO`), **검색 자체가 틀린 상품을 가져온다.**
비슷한 상품끼리(청소기 A vs 청소기 B)면 Grounding 도 못 걸러낸다.

### 검색룰이 로보락 전용이다 — 이쪽이 더 크다

```python
# core/rag_retriever.py:96  RETRIEVAL_RULES — 20개 규칙
"흡입력": {
    "query_keywords": ["흡입력", "파스칼", "2만 파스칼", "20000pa", ...],
    "target_words":   ["흡입력", "20,000pa", "20000pa"]      ← 로보락 스펙
},
"머리카락": { ... "jawscrapers" ... },                        ← 로보락 기술명
```

20개 중 7개에 로보락 고유 수치·모델명이 박혀 있다.
**상품이 1만 개면 규칙을 1만 벌 쓸 수 없다.**

실제로 노트북·화장품 질문에는 검색 결과가 **0건**이다. 해당 규칙이 없어서다.
KB 주입을 고쳐도 이 문제는 그대로 남는다.

### 참고 — 앞단 입력 스키마와 KB 크기

`Fundit-AI-Funding-Story` 의 `ProjectInput` / `ExportResult` 가 실제 입력원이다.

```
ProjectInput   title(200) category(200) product_description(20,000)
               rewards[]{name(100) description(3,000)} × 3
               information{budget schedule team policy risks}

ExportResult   project_summary{summary storyline} information{...} images[]
```

`max_length` 로 계산한 **최악 상한 29,700자 ≈ 14,850 토큰**.
로보락 실측(2,501자 ≈ 1,250토큰)의 **12배**다.
따라서 "KB 를 통째로 프롬프트에 넣는" 방식은 쓸 수 없다. 검색 단계가 반드시 필요하다.

### 참고 — 실시간 갱신 경로는 이미 있다

MCP 에 판매자가 방송 중 정보를 넣는 경로가 구현되어 있다. 실측으로 확인했다.

```
① 등록 전     live=0
② 판매자 등록  7ms
③ 등록 후     live=1  "카펫 모드가 있어 러그·카펫에도 사용 가능합니다."
④ 정보 정정    live=1  "죄송합니다. 카펫은 권장하지 않습니다."   ← 덮어쓰기, 중복 아님
```

`search_product_context` 가 공식 KB(official) 와 라이브 지식(live) 2층으로 조회하며,
라이브 지식이 우선이다.

> MCP tool 파라미터명 주의: `query` 가 아니라 **`question`**.

### 성능 참고

```
load_chunks()       0.4 ms   (파일 재파싱, 캐시 없음)
retrieve()          0.7 ms
answer_question() 2079.1 ms   (Gemini 호출 포함)
→ 지연의 100% 가 LLM 호출
```

**검색은 병목이 아니다.** 실시간 속도를 걱정해 검색 방식을 바꿀 이유는 없다.

### 이 문제들을 어떻게 할 것인가

`core/rag_retriever.py` 는 현서님 담당 영역이다.
상품별 KB 주입과 룰 생성 방식은 **현서님과 합의 후 진행**하는 것이 맞다.

방향만 적어 두면,

1. `retrieve(question, product_id)` 로 상품 스코핑 — 상품 간 오염 차단
2. 방송 전 KB·룰 사전 구축 (실시간 조회 없음 → 응답 속도 유지)
3. `RETRIEVAL_RULES` 를 상품마다 생성 (코드 생성 또는 LLM 생성)
4. **상담 문체 코퍼스는 전 상품 공통으로 고정** — 여기는 건드리지 않는다

4번이 중요하다. 현서님이 설계에서 이미 분리해 둔 축이다.
*"Product KB = 상품 사실의 근거 / Counselor Style RAG = 상담 말투"*
상품은 매번 바뀌지만 상담사 말투는 그대로 재사용된다.

> 1~3 의 초안을 만들어 봤으나 **검증이 불충분해 폐기했다.**
> 노트북 상품으로 테스트했을 때 4개 질문 중 1개만 검색됐다.
> 카테고리 단위로만 키워드를 뽑는 방식이라 "무게", "배터리" 같은 질문이 안 잡혔다.
> 실제 상품 데이터를 여러 건 확보한 뒤 설계하는 것을 권한다.

---

## 5. README 반영 내용

통합 후 README 에 들어가야 할 핵심.

**기능 영역 표** — 하나의 코파일럿을 구성하는 영역

| 영역 | 역할 | 구현 |
|---|---|---|
| 분류 | 채팅을 잡담/플랫폼/상품으로 라우팅 | `orchestrator/router.py` |
| 답변 — 플랫폼·펀딩 | FAQ 원문 + 실시간 값 치환 | `parts/o_part/` |
| 답변 — 상품 | Product KB 검색 → Grounding 3단 판정 | `core/rag_answer.py`, `core/rag_retriever.py` |
| 상담 문체 | 답변에 상담사 말투 적용 | `core/counselor_style_retriever.py` |
| 질문 요약 | 미답변 분석 → 관심사 집계 → 방송후 Q&A | `core/unanswered_analyzer.py`, `core/interest_tracker.py`, `services/post_live_summary.py` |

**폴더 구조**

```
shared/          파트 간 계약 (schemas + CopilotPart)
orchestrator/    라우터(LLM 분류 전용) · 서비스 · 공용 LLM 클라이언트
parts/
├── o_part/      플랫폼·펀딩 FAQ 응대 + data/
└── p_part/      상품 상담 어댑터 (CopilotPart 계약 → core/)
core/            상품 RAG · 상담 문체 검색 · 미답변 분석 · 관심사 집계
                 ※ 서빙(api·webtest)과 A2A Agent 가 동일하게 사용하는 정본
services/        상품 질문 처리 · 라이브 코파일럿 · 방송후 요약 · 판매자 피드백
agents/          A2A Product Agent (실행기 · 서버)
mcp_servers/     Product Knowledge MCP 서버 (공식 KB + 라이브 지식)
scripts/         상담 문체 코퍼스 구축 파이프라인
api/             FastAPI — BE 연동 API
data/
├── product_5454434.*            상품 KB (Roborock F25)
└── kshopping_style/rag/         K쇼핑 상담 문체 학습 코퍼스
eval/            평가 하네스
tests/           MCP · A2A 연동 테스트
webtest/         라이브 목방송 테스트 환경
```

**상담 문체 코퍼스 통계** (현서님 구축분)

| 단계 | 건수 |
|---|---|
| 원본 상담 | 18,440 |
| 정제 후 코퍼스 | 3,131 |
| 제외 | 7,056 (업무처리 6,568 · 과길이 252 · 내부절차 110 · 개인정보 64 등) |
| 최종 문체 프레임 | 47 |

스타일 10종: CONFIRMATION · INFORMATION · GUIDANCE · POSITIVE · NEGATIVE ·
NO_INFORMATION · APOLOGY · CLOSING · WAIT · GREETING

**MCP tool 5종**

```
search_product_knowledge   공식 KB 검색
get_product_chunk          chunk 조회
add_live_product_fact      방송 중 판매자 확인 정보 등록
search_live_product_fact   라이브 지식 검색
search_product_context     공식 KB + 라이브 지식 통합
```

**담당 구성** — 현서님 영역이 넓어졌으므로 갱신 필요

| 영역 | 담당 |
|---|---|
| 상품 답변 · 상담 문체 · 질문 요약 · A2A·MCP | 심현서 |
| 플랫폼·펀딩 답변 | 박금별 |
| 공용 구조·통합 | 공동 |

---

## 6. 주의사항

- **`.env` 는 절대 커밋하지 않는다.** `GEMINI_API_KEY` 가 들어 있다.
- **현서님 커밋 이력은 보존한다.** 리베이스·스쿼시 없이 그대로 가져오면
  `5d7e84f` → `92cf40b` → `cb93697` 3개가 저자·메시지까지 유지된다.
- **하이라이트(타임라인·쇼츠) 코드는 이 저장소에 넣지 않는다.**
  `Funddit-Ai-highlight` 에 별도로 둔다.
- `core/rag_retriever.py` 등 P파트 영역 수정은 현서님과 합의 후 진행한다.

---

## 7. 참고 — 작업 결과물 위치

전체 통합 작업이 로컬 백업 브랜치에 보존되어 있다.

```bash
git branch                       # backup/before-revert-20260917
git diff a88fd64 backup/before-revert-20260917 --stat
#   47 files changed, 61623 insertions(+), 482 deletions(-)
```

STEP 1~5 를 그대로 적용한 결과이므로, 막히는 부분이 있으면 이 브랜치와 비교하면 된다.

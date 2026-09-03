# Live Commerce Copilot MVP

라이브커머스 방송 중 발생하는 고객 질문을 분석하여  
상품 정보로 답변 가능한 질문과 추가 확인이 필요한 질문을 구분하고,  
판매자가 실시간으로 확인해야 할 **미답변 고객 관심사**를 정리하는 Seller Copilot MVP입니다.

본 저장소는 전체 Live Commerce Copilot 중 **P(Product) 영역**을 담당합니다.

---

## 1. 프로젝트 목표

라이브커머스에서는 짧은 시간 동안 비슷한 고객 질문이 반복적으로 발생합니다.

본 MVP는 고객 질문을 상품 Knowledge Base와 비교하여 다음과 같이 처리합니다.

- 상품 정보만으로 답변 가능한 질문 식별
- 일부만 답변 가능한 질문의 미답변 부분 추출
- 상품 정보에 존재하지 않는 질문 식별
- 미답변 질문을 관심 유형별로 그룹화
- 반복적으로 발생하는 관심사를 판매자에게 제공
- 실제 시청자 질문 중 가장 많이 등장한 질문을 대표 질문으로 선정

최종적으로 판매자가 방송 중

> "지금 시청자들이 어떤 정보를 가장 궁금해하고 있는가?"

를 빠르게 확인할 수 있도록 하는 것이 목적입니다.

---

## 2. 전체 처리 흐름

```text
고객 질문
    ↓
상품 Knowledge Base Retrieval
    ↓
Grounding 판정
    │
    ├─ GROUNDED
    │    └─ 상품 정보로 처리 가능
    │
    ├─ PARTIAL_GROUNDED
    │    └─ 해결되지 않은 세부 질문 추출
    │
    └─ NO_GROUNDED_INFO
         └─ 미답변 질문 추출
                    ↓
              관심 유형 분류
                    ↓
             동일 Topic 그룹화
                    ↓
              발생 횟수 집계
                    ↓
          대표 관심 / 대표 질문 선정
                    ↓
             Seller Copilot 화면
```

`GROUNDED` 질문은 상품 Knowledge Base로 처리할 수 있으므로  
미답변 관심사 화면에는 포함하지 않습니다.

`PARTIAL_GROUNDED` 질문은 전체 질문이 아니라  
**상품 정보로 해결하지 못한 부분만 관심사 집계에 반영합니다.**

---

## 3. Grounding 상태

고객 질문은 상품 Knowledge Base 기준으로 세 가지 상태로 구분합니다.

### `GROUNDED`

상품 정보만으로 질문 전체에 답변할 수 있는 경우

```text
Q. 흡입력이 정확히 몇 Pa예요?

→ GROUNDED
→ 최대 흡입력은 20,000Pa입니다.
```

### `PARTIAL_GROUNDED`

질문의 일부는 상품 정보로 답변할 수 있지만  
일부 내용은 확인할 수 없는 경우

```text
Q. 흡입력은 몇이고 앱으로 조작도 가능한가요?

→ PARTIAL_GROUNDED

확인 가능
- 최대 흡입력 20,000Pa

확인 불가
- 앱 조작 지원 여부
```

### `NO_GROUNDED_INFO`

상품 Knowledge Base에서 질문에 필요한 정보를 확인할 수 없는 경우

```text
Q. 완충하면 몇 분 사용할 수 있나요?

→ NO_GROUNDED_INFO
```

상품 정보에 존재하지 않는 수치, 기능, 조건은 임의로 생성하지 않습니다.

---

## 4. 상품 Knowledge Base

현재 MVP 대상 상품은 **로보락 F25**입니다.

상품 상세 정보를 JSON으로 구조화한 뒤 Markdown Knowledge Base로 변환하여 사용합니다.

```text
product_5454434.json
        ↓
make_product_md.py
        ↓
product_5454434.md
```

현재 Knowledge Base에는 다음과 같은 상품 정보가 포함되어 있습니다.

- 흡입력
- 제품 크기 및 무게
- 배터리 사양
- 물통 용량
- 소음
- 머리카락 엉킴 관련 구조
- 청소 압력
- 헤드 회전각
- FlatReach 기능
- 모서리 청소
- 롤러 회전 속도
- 오염 감지
- 청소 모드
- 세척 및 건조
- 전용 클리너
- A/S 및 보증 정보

---

## 5. Retrieval

현재 MVP에서는 Vector DB와 Embedding을 사용하지 않습니다.

단일 상품의 소규모 Knowledge Base를 대상으로  
**규칙 기반 Retrieval + 키워드/수치/단위 매칭 방식**을 사용합니다.

예를 들어 다음과 같은 표현을 동일한 상품 정보로 연결합니다.

```text
"본체를 180도로 눕힐 수 있나요?"
→ FlatReach 관련 Chunk

"롤러가 분당 450번 도나요?"
→ 450RPM 관련 Chunk

"바닥 누르는 힘은 어느 정도예요?"
→ 20N 청소 압력 관련 Chunk

"청소 헤드는 몇 도까지 회전해요?"
→ 최대 70도 회전 관련 Chunk
```

숫자와 단위가 명확하게 일치하는 상품 사양도 Retrieval 신호로 활용합니다.

상품과 관계없는 입력은 관련 Knowledge Base를 반환하지 않도록 처리합니다.

---

## 6. 미답변 고객 관심사 분석

상품 Knowledge Base로 해결되지 않은 질문은  
고정된 관심 유형과 Topic으로 분류합니다.

예시:

```text
FLOOR_COMPATIBILITY
├─ HARD_FLOOR_USE
└─ CARPET_RUG_USE

APP_REMOTE
└─ SMART_CONNECTIVITY

WASH_DRY
├─ AUTO_WASH
├─ WASH_TEMPERATURE
├─ DRYING_ODOR
└─ STERILIZATION
```

서로 표현이 다른 질문도 의미가 같으면 동일한 Topic으로 묶습니다.

예:

```text
대리석에도 사용해도 되나요?
장판에도 써도 돼요?
강화마루에서 사용 가능한가요?
원목마루에도 괜찮나요?
```

↓

```text
FLOOR_COMPATIBILITY
└─ HARD_FLOOR_USE : 4건
```

---

## 7. 대표 관심 및 대표 질문 선정

각 카테고리에서 가장 많이 발생한 Topic을  
**대표 관심**으로 선정합니다.

대표 질문은 AI가 새로 생성하지 않습니다.

해당 Topic에 포함된 **실제 시청자 질문 중 가장 많이 등장한 질문**을 대표 질문으로 사용합니다.

동일한 질문 횟수가 같을 경우에는 더 짧은 실제 질문을 선택합니다.

예:

```text
앱으로 원격 조작 가능한가요?   4회
와이파이 연결 지원하나요?      2회
음성 명령도 지원해요?          1회
```

↓

```text
대표 관심: 앱·원격 연결
대표 질문: 앱으로 원격 조작 가능한가요?
```

---

## 8. Seller Copilot 출력 예시

```text
실시간 미답변 고객 관심사

1. 세척·건조 | 8건
   대표 관심: 세척 온도 (3건)
   대표 질문: 롤러 세척 온도는 정확히 몇 도예요?

2. 청소 성능 | 7건
   대표 관심: 생활 오염 청소 (3건)
   대표 질문: 끈적한 바닥도 물걸레질 가능한가요?

3. 바닥재·호환성 | 7건
   대표 관심: 일반 바닥재 사용 (4건)
   대표 질문: 장판에도 써도 돼요?
```

판매자 화면에서는 AI 추천 답변을 표시하지 않고,  
**현재 상품 정보만으로 해결되지 않은 고객 관심사와 실제 질문을 중심으로 제공합니다.**

---

## 9. 사용 모델

Grounding 및 미답변 질문 분석에는 Vertex AI 기반의

```text
Gemini 3.5 Flash-Lite
```

를 사용합니다.

모델은 상품 Knowledge Base에 제공된 정보를 기준으로 답변 가능 여부를 판단하며,  
상품 정보에 없는 사실을 임의로 생성하지 않도록 제한합니다.

---

## 10. 프로젝트 구조

```text
.
├── product_5454434.json
├── product_5454434.md
├── make_product_md.py
│
├── rag_retriever.py
├── rag_answer.py
├── unanswered_analyzer.py
├── interest_tracker.py
│
├── mvp_live_test.py
├── mvp_replay_test.py
│
├── p_rag_eval_50.json
├── evaluate_rag.py
├── p_video_expected_questions_100.json
│
├── requirements.txt
├── .gitignore
└── README.md
```

### 주요 파일

| 파일 | 역할 |
|---|---|
| `product_5454434.json` | 상품 원본 Knowledge Base |
| `product_5454434.md` | Retrieval용 Markdown Knowledge Base |
| `make_product_md.py` | JSON → Markdown 변환 |
| `rag_retriever.py` | 질문과 관련된 상품 정보 검색 |
| `rag_answer.py` | Grounding 판정 및 상품 정보 기반 답변 |
| `unanswered_analyzer.py` | 해결되지 않은 질문의 관심 유형 분석 |
| `interest_tracker.py` | 관심사별 질문 누적 및 대표 질문 선정 |
| `mvp_live_test.py` | 단일 질문 기반 MVP 테스트 |
| `mvp_replay_test.py` | 100개 예상 질문 자동 Replay |
| `evaluate_rag.py` | RAG 평가 실행 |
| `p_rag_eval_50.json` | 개발용 RAG 평가 데이터 |
| `p_video_expected_questions_100.json` | 방송 기반 예상 질문 100건 |

---

## 11. 실행 환경

Python 가상환경 사용을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

필요한 패키지를 설치합니다.

```bash
pip install -r requirements.txt
```

Vertex AI 사용을 위해 Google Cloud 인증 환경이 필요합니다.

---

## 12. Retrieval 단독 테스트

```bash
python3 rag_retriever.py
```

실행 후 질문을 입력합니다.

```text
고객 질문: 롤러가 분당 450번 도는 건가요?
```

예상 검색 결과:

```text
chunk_id: kb_p_022
category: 제품 성능 및 사양
text: 롤러 회전 속도는 450RPM입니다.
```

---

## 13. RAG 평가

개발 단계에서 구성한 50건의 평가 데이터로  
상품 Retrieval 및 Grounding 기능을 테스트할 수 있습니다.

```bash
python3 evaluate_rag.py
```

평가 결과 JSON 파일은 실행 시 생성되며 Git 저장소에서는 제외합니다.

---

## 14. MVP Replay 테스트

방송 상황을 가정하여 구성한 예상 고객 질문 100건을 자동으로 실행할 수 있습니다.

```bash
python3 mvp_replay_test.py
```

Replay 과정에서는 다음 항목을 확인합니다.

- 질문별 Grounding 상태
- Knowledge Base 검색 결과
- 미답변 질문 추출
- 관심 Topic 분류
- Topic별 질문 발생 횟수
- 대표 관심
- 실제 시청자 대표 질문

---

## 15. 현재 MVP 테스트 결과

100개 예상 고객 질문 Replay 기준 결과입니다.

| 항목 | 결과 |
|---|---:|
| 전체 질문 | 100건 |
| GROUNDED | 47건 |
| PARTIAL_GROUNDED | 10건 |
| NO_GROUNDED_INFO | 43건 |
| Grounding 상태 일치 | 85건 |
| Grounding 상태 정확도 | 85% |
| 평균 처리 시간 | 약 1.53초 |
| 실행 오류 | 0건 |

Retrieval 규칙 개선을 통해  
자연어로 표현된 상품 사양 질문에 대한 검색 성능을 보완했습니다.

현재 평가는 MVP 개발 및 기능 검증을 위한 결과이며,  
일부 평가 문항의 Grounding 기준은 추가 검수가 필요한 상태입니다.

따라서 해당 수치는 최종 운영 성능이 아닌 **현재 MVP 기준 검증 결과**로 사용합니다.

---

## 16. 현재 범위

본 저장소는 Live Commerce Seller Copilot의 **P(Product) 영역**을 대상으로 합니다.

### 포함

- 상품 질문 분석
- 상품 Knowledge Base Retrieval
- Grounding
- 상품 정보 기반 답변 가능 여부 판단
- 미답변 상품 질문 분석
- 고객 관심사 집계
- 대표 관심 및 대표 질문 선정

### 제외

다음과 같은 플랫폼 운영 영역은 본 저장소의 범위에 포함하지 않습니다.

- 주문
- 결제
- 배송
- 취소
- 교환
- 환불
- 쿠폰
- 프로모션
- 실시간 재고
- 개인 주문 조회

해당 영역은 별도의 O(Operational) 파이프라인에서 처리하는 것을 전제로 합니다.

---

## 17. 향후 개선 방향

현재 MVP 이후에는 다음 항목을 확장할 수 있습니다.

- 실제 라이브 댓글 스트림 연동
- Seller Copilot 화면 연동
- 새로운 상품에 대한 Knowledge Base 자동 생성
- Retrieval 범용화
- Grounding 판정 기준 개선
- 새로운 Hold-out 평가셋 구축
- P/O 통합 파이프라인 연결

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


# =========================================================
# 제거 규칙
# =========================================================

# 개인정보 / 인증정보 요청
SENSITIVE_PATTERNS = {
    "PERSONAL_INFO": [
        r"성함",
        r"성명",
        r"이름.*말씀",
        r"전화\s*번호",
        r"휴대폰\s*번호",
        r"연락처.*말씀",
        r"생년월일",
        r"주민\s*번호",
        r"주소.*말씀",
        r"상세\s*주소",
    ],
    "PAYMENT_AUTH": [
        r"카드\s*번호",
        r"카드.*유효\s*기간",
        r"비밀\s*번호",
        r"계좌\s*번호",
        r"예금주",
        r"본인.*카드",
        r"카드.*본인",
    ],
    "PHONE_ONLY_PROCESS": [
        r"에이알에스",
        r"\bARS\b",
        r"자동응답",
        r"통화\s*가능",
        r"전화.*연결",
    ],
}


# 실제 시스템 처리처럼 오인될 가능성이 큰 표현
ACTION_PATTERNS = [
    r"결제.*(?:변경|취소).*해\s*드리",
    r"환불.*(?:처리|진행|접수).*하겠",
    r"환불.*해\s*드리",
    r"주문.*(?:접수|진행).*하겠",
    r"주문.*해\s*드리",
    r"교환.*(?:접수|처리).*하겠",
    r"교환.*해\s*드리",
    r"반품.*(?:접수|처리).*하겠",
    r"반품.*해\s*드리",
    r"배송지.*변경.*해\s*드리",
    r"카드.*삭제.*해\s*드리",
]


# 너무 짧거나 스타일 데이터로 가치가 거의 없는 발화
LOW_VALUE_EXACT = {
    "네",
    "예",
    "네.",
    "예.",
    "알겠습니다.",
    "네 알겠습니다.",
    "예 알겠습니다.",
    "맞습니다.",
    "네 맞습니다.",
    "감사합니다.",
}


# =========================================================
# 스타일 분류 규칙
# =========================================================

STYLE_RULES = [
    (
        "APOLOGY",
        [
            r"죄송",
            r"불편.*드려",
            r"양해",
            r"안타깝",
        ],
    ),
    (
        "WAIT",
        [
            r"잠시만",
            r"기다려",
            r"기다려주셔서",
        ],
    ),
    (
        "CONFIRMATION",
        [
            r"확인.*감사",
            r"확인됩니다",
            r"확인되",
            r"확인해\s*드리",
            r"확인 후",
            r"확인 결과",
        ],
    ),
    (
        "GUIDANCE",
        [
            r"안내.*드리",
            r"말씀.*드리",
            r"도움.*드리",
            r"참고.*부탁",
        ],
    ),
    (
        "CLOSING",
        [
            r"더 문의",
            r"추가.*문의",
            r"궁금.*사항",
            r"감사합니다.*이었습니다",
        ],
    ),
    (
        "GREETING",
        [
            r"안녕하십니까",
            r"안녕하세요",
            r"반갑습니다",
            r"무엇을 도와",
        ],
    ),
    (
        "INFORMATION",
        [
            r"입니다",
            r"됩니다",
            r"가능합니다",
            r"어렵습니다",
            r"지원",
            r"소요",
            r"구성",
        ],
    ),
]


def normalize_text(text: str) -> str:
    """비교와 중복 제거를 위한 최소 정규화."""
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_for_dedup(text: str) -> str:
    """문장부호와 공백 차이를 어느 정도 무시한 중복키."""
    text = normalize_text(text).lower()
    text = re.sub(r"[,.!?~]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_records(data: Any) -> list[dict]:
    """
    통합 JSON 구조가 단순 리스트가 아니어도
    '화자' 필드가 있는 레코드를 재귀적으로 찾아낸다.
    """
    records = []

    def walk(obj: Any):
        if isinstance(obj, list):
            for item in obj:
                walk(item)

        elif isinstance(obj, dict):
            if "화자" in obj:
                records.append(obj)
                return

            for value in obj.values():
                walk(value)

    walk(data)
    return records


def get_counselor_utterances(record: dict) -> list[dict]:
    """
    상담사질문(요청), 상담사답변 둘 다 확인한다.
    """
    if str(record.get("화자", "")).strip() != "상담사":
        return []

    result = []

    fields = [
        "상담사질문(요청)",
        "상담사답변",
    ]

    for field in fields:
        text = normalize_text(str(record.get(field, "") or ""))

        if not text:
            continue

        result.append(
            {
                "conversation_id": str(
                    record.get("대화셋일련번호", "")
                ).strip(),
                "sentence_no": str(record.get("문장번호", "")).strip(),
                "category": str(record.get("카테고리", "")).strip(),
                "counselor_intent": str(
                    record.get("상담사의도", "")
                ).strip(),
                "source_field": field,
                "text": text,
                "knowledge_base": str(
                    record.get("지식베이스", "")
                ).strip(),
                "entities": str(
                    record.get("개체명 ", record.get("개체명", ""))
                ).strip(),
            }
        )

    return result


def detect_rejection_reason(text: str) -> str | None:
    normalized = normalize_text(text)

    if normalized in LOW_VALUE_EXACT:
        return "LOW_VALUE"

    if len(normalized) < 5:
        return "TOO_SHORT"

    for reason, patterns in SENSITIVE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return reason

    for pattern in ACTION_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return "SYSTEM_ACTION"

    return None


def classify_style(text: str) -> str:
    for style_type, patterns in STYLE_RULES:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return style_type

    return "GENERAL"


def needs_generalization(item: dict) -> bool:
    """
    특정 상품/가격/날짜/수치 등이 포함됐을 가능성이 있는 문장은
    삭제하지 않고 일반화 필요 표시만 한다.

    이 문장을 나중에 그대로 RAG에 넣으면 안 된다.
    """

    text = item["text"]

    # 원본 데이터에서 지식베이스나 개체명이 존재하면
    # 구체적 사실이 포함됐을 가능성이 높음.
    if item.get("knowledge_base"):
        return True

    # 가격 / 수량 / 단위 / 날짜 등
    numeric_patterns = [
        r"\d",
        r"[일이삼사오육칠팔구십백천만억]+\s*원",
        r"[일이삼사오육칠팔구십]+\s*개",
        r"[일이삼사오육칠팔구십]+\s*종",
        r"[일이삼사오육칠팔구십]+\s*개월",
        r"[일이삼사오육칠팔구십]+\s*일",
    ]

    return any(re.search(pattern, text) for pattern in numeric_patterns)


def main():
    parser = argparse.ArgumentParser(
        description="K쇼핑 상담 데이터에서 공통 상담사 스타일 발화를 정제합니다."
    )

    parser.add_argument(
        "--input",
        default="data/kshopping_style/raw/K쇼핑_데이터.json",
        help="통합 K쇼핑 JSON 경로",
    )

    parser.add_argument(
        "--output-dir",
        default="data/kshopping_style/processed",
        help="정제 결과 저장 폴더",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        raise FileNotFoundError(
            f"입력 파일을 찾을 수 없습니다: {input_path}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[LOAD] {input_path}")

    with input_path.open("r", encoding="utf-8-sig") as f:
        raw_data = json.load(f)

    records = load_records(raw_data)

    print(f"[INFO] 전체 레코드 수: {len(records):,}")

    # -----------------------------------------------------
    # 1. 상담사 발화 전체 추출
    # -----------------------------------------------------

    counselor_utterances = []

    for record in records:
        counselor_utterances.extend(
            get_counselor_utterances(record)
        )

    print(
        f"[INFO] 상담사 발화 수: "
        f"{len(counselor_utterances):,}"
    )

    # -----------------------------------------------------
    # 2. 필터링
    # -----------------------------------------------------

    clean = []
    rejected = []

    for item in counselor_utterances:
        reason = detect_rejection_reason(item["text"])

        if reason:
            rejected_item = dict(item)
            rejected_item["reject_reason"] = reason
            rejected.append(rejected_item)
            continue

        candidate = dict(item)

        candidate["style_type"] = classify_style(
            candidate["text"]
        )

        candidate["needs_generalization"] = (
            needs_generalization(candidate)
        )

        clean.append(candidate)

    # -----------------------------------------------------
    # 3. 완전/준완전 동일 문장 중복 제거
    # -----------------------------------------------------

    grouped = {}

    for item in clean:
        dedup_key = normalize_for_dedup(item["text"])

        if dedup_key not in grouped:
            grouped[dedup_key] = {
                **item,
                "duplicate_count": 1,
                "source_examples": [
                    {
                        "conversation_id": item["conversation_id"],
                        "sentence_no": item["sentence_no"],
                        "category": item["category"],
                    }
                ],
            }

        else:
            grouped[dedup_key]["duplicate_count"] += 1

            if len(grouped[dedup_key]["source_examples"]) < 5:
                grouped[dedup_key]["source_examples"].append(
                    {
                        "conversation_id": item["conversation_id"],
                        "sentence_no": item["sentence_no"],
                        "category": item["category"],
                    }
                )

    clean_deduped = list(grouped.values())

    # 많이 등장한 상담 표현부터 확인할 수 있게 정렬
    clean_deduped.sort(
        key=lambda x: (-x["duplicate_count"], x["text"])
    )

    # -----------------------------------------------------
    # 4. 저장
    # -----------------------------------------------------

    utterance_path = (
        output_dir / "counselor_utterances.json"
    )
    clean_path = (
        output_dir / "counselor_style_clean.json"
    )
    rejected_path = (
        output_dir / "counselor_style_rejected.json"
    )

    with utterance_path.open("w", encoding="utf-8") as f:
        json.dump(
            counselor_utterances,
            f,
            ensure_ascii=False,
            indent=2,
        )

    with clean_path.open("w", encoding="utf-8") as f:
        json.dump(
            clean_deduped,
            f,
            ensure_ascii=False,
            indent=2,
        )

    with rejected_path.open("w", encoding="utf-8") as f:
        json.dump(
            rejected,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # -----------------------------------------------------
    # 5. 통계
    # -----------------------------------------------------

    rejection_counter = Counter(
        item["reject_reason"] for item in rejected
    )

    style_counter = Counter(
        item["style_type"] for item in clean_deduped
    )

    generalization_count = sum(
        1
        for item in clean_deduped
        if item["needs_generalization"]
    )

    print()
    print("=" * 60)
    print("K쇼핑 상담사 데이터 정제 결과")
    print("=" * 60)

    print(
        f"전체 원본 레코드       : {len(records):,}"
    )
    print(
        f"상담사 발화           : {len(counselor_utterances):,}"
    )
    print(
        f"필터 통과             : {len(clean):,}"
    )
    print(
        f"중복 제거 후          : {len(clean_deduped):,}"
    )
    print(
        f"제거 발화             : {len(rejected):,}"
    )
    print(
        f"일반화 필요           : {generalization_count:,}"
    )

    print("\n[제거 사유]")
    for key, value in rejection_counter.most_common():
        print(f"- {key}: {value:,}")

    print("\n[스타일 유형]")
    for key, value in style_counter.most_common():
        print(f"- {key}: {value:,}")

    print("\n[SAVED]")
    print(f"- {utterance_path}")
    print(f"- {clean_path}")
    print(f"- {rejected_path}")


if __name__ == "__main__":
    main()
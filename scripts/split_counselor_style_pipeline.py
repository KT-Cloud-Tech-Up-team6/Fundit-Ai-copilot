import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


# =========================================================
# 기본 설정
# =========================================================

TRAINING_STYLES = {
    "CONFIRMATION",
    "INFORMATION",
    "GUIDANCE",
    "POSITIVE",
    "NEGATIVE",
    "NO_INFORMATION",
    "APOLOGY",
    "CLOSING",
    "WAIT",
    "GREETING",
    "GENERAL",
}

# RAG에서는 실시간 답변에서 자주 쓸 핵심 스타일 위주
RAG_CORE_STYLES = {
    "CONFIRMATION",
    "INFORMATION",
    "GUIDANCE",
    "POSITIVE",
    "NEGATIVE",
    "NO_INFORMATION",
    "APOLOGY",
    "CLOSING",
}

# WAIT / GREETING은 아예 버리지는 않고 별도 보관
RAG_AUX_STYLES = {
    "WAIT",
    "GREETING",
}


def normalize_text(text: str) -> str:
    return " ".join(
        str(text or "")
        .replace("\r", " ")
        .replace("\n", " ")
        .split()
    )


def load_records(data: Any) -> list[dict]:
    """
    통합 JSON 구조가 리스트가 아니더라도
    '화자'가 있는 레코드를 재귀적으로 탐색한다.
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


def get_customer_text(record: dict) -> str:
    """
    고객 발화는 고객질문(요청) 또는 고객답변에 들어갈 수 있음.
    """
    question = normalize_text(
        record.get("고객질문(요청)", "")
    )

    answer = normalize_text(
        record.get("고객답변", "")
    )

    if question:
        return question

    if answer:
        return answer

    return ""


def build_conversation_index(
    records: list[dict],
) -> dict[str, list[dict]]:
    """
    대화셋일련번호 기준으로 대화를 묶고 문장번호 순으로 정렬.
    """
    conversations = defaultdict(list)

    for record in records:
        conversation_id = str(
            record.get("대화셋일련번호", "")
        ).strip()

        if not conversation_id:
            continue

        conversations[conversation_id].append(
            record
        )

    def sentence_number(record: dict) -> int:
        raw = str(
            record.get("문장번호", "0")
        ).strip()

        try:
            return int(raw)
        except ValueError:
            return 0

    for conversation_id in conversations:
        conversations[conversation_id].sort(
            key=sentence_number
        )

    return dict(conversations)


def find_previous_customer_context(
    conversation: list[dict],
    counselor_sentence_no: int,
    max_customer_turns: int = 2,
) -> list[str]:
    """
    상담사 발화 직전의 고객 발화를 최대 N개까지 복원한다.

    단순히 바로 이전 문장 하나만 보는 게 아니라,
    짧은 고객 응답("네", "맞아요") 이전의 실제 질문까지
    포함할 수 있도록 최근 고객 발화 N개를 가져온다.
    """
    previous_customer_turns = []

    for record in reversed(conversation):
        try:
            sentence_no = int(
                str(
                    record.get(
                        "문장번호",
                        "0",
                    )
                ).strip()
            )
        except ValueError:
            continue

        if sentence_no >= counselor_sentence_no:
            continue

        if str(
            record.get("화자", "")
        ).strip() != "고객":
            continue

        text = get_customer_text(record)

        if not text:
            continue

        previous_customer_turns.append(text)

        if (
            len(previous_customer_turns)
            >= max_customer_turns
        ):
            break

    return list(
        reversed(previous_customer_turns)
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Shared Counselor Style 후보를 "
            "Fine-tuning 후보와 RAG 후보로 분리합니다."
        )
    )

    parser.add_argument(
        "--raw",
        default=(
            "data/kshopping_style/raw/"
            "K쇼핑_데이터.json"
        ),
    )

    parser.add_argument(
        "--candidates",
        default=(
            "data/kshopping_style/processed/"
            "shared_counselor_style_candidates.json"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=(
            "data/kshopping_style/pipeline"
        ),
    )

    parser.add_argument(
        "--rag-min-score",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--rag-max-per-style",
        type=int,
        default=3000,
    )

    args = parser.parse_args()

    raw_path = Path(args.raw)
    candidates_path = Path(args.candidates)
    output_dir = Path(args.output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not raw_path.exists():
        raise FileNotFoundError(
            f"원본 파일 없음: {raw_path}"
        )

    if not candidates_path.exists():
        raise FileNotFoundError(
            f"후보 파일 없음: {candidates_path}"
        )

    # =====================================================
    # LOAD
    # =====================================================

    print(f"[LOAD RAW] {raw_path}")

    with raw_path.open(
        "r",
        encoding="utf-8-sig",
    ) as f:
        raw_data = json.load(f)

    records = load_records(raw_data)

    print(
        f"[INFO] 전체 원본 레코드: "
        f"{len(records):,}"
    )

    conversations = build_conversation_index(
        records
    )

    print(
        f"[INFO] 전체 대화 수: "
        f"{len(conversations):,}"
    )

    print(
        f"[LOAD CANDIDATES] "
        f"{candidates_path}"
    )

    with candidates_path.open(
        "r",
        encoding="utf-8-sig",
    ) as f:
        candidates = json.load(f)

    print(
        f"[INFO] Shared 후보: "
        f"{len(candidates):,}"
    )

    # =====================================================
    # 1. TRAINING 후보
    # =====================================================

    training_candidates = []

    missing_context_count = 0

    for item in candidates:
        styles = set(
            item.get(
                "shared_styles",
                [],
            )
        )

        if not styles & TRAINING_STYLES:
            continue

        conversation_id = str(
            item.get(
                "conversation_id",
                "",
            )
        ).strip()

        try:
            sentence_no = int(
                str(
                    item.get(
                        "sentence_no",
                        "0",
                    )
                )
            )
        except ValueError:
            sentence_no = 0

        conversation = conversations.get(
            conversation_id,
            [],
        )

        customer_context = (
            find_previous_customer_context(
                conversation=conversation,
                counselor_sentence_no=sentence_no,
                max_customer_turns=2,
            )
        )

        if not customer_context:
            missing_context_count += 1

        training_candidates.append(
            {
                "conversation_id":
                    conversation_id,
                "sentence_no":
                    sentence_no,
                "category":
                    item.get(
                        "category",
                        "",
                    ),
                "customer_context":
                    customer_context,
                "counselor_response":
                    item.get(
                        "text",
                        "",
                    ),
                "styles":
                    item.get(
                        "shared_styles",
                        [],
                    ),
                "shared_score":
                    item.get(
                        "shared_score",
                        0,
                    ),
                "duplicate_count":
                    item.get(
                        "duplicate_count",
                        1,
                    ),
                "needs_generalization":
                    item.get(
                        "needs_generalization",
                        False,
                    ),

                # 아직 Fine-tuning에 바로 사용하면 안 됨.
                # 다음 단계에서 Gemini가
                # neutral/raw answer를 생성하고
                # 사실정보를 제거/일반화할 예정.
                "training_ready": False,
            }
        )

    # =====================================================
    # 2. RAG 후보
    # =====================================================

    rag_by_style = defaultdict(list)

    rag_aux = []

    for item in candidates:
        score = int(
            item.get(
                "shared_score",
                0,
            )
        )

        if score < args.rag_min_score:
            continue

        styles = item.get(
            "shared_styles",
            [],
        )

        core_styles = [
            style
            for style in styles
            if style in RAG_CORE_STYLES
        ]

        aux_styles = [
            style
            for style in styles
            if style in RAG_AUX_STYLES
        ]

        if core_styles:
            for style in core_styles:
                rag_by_style[style].append(
                    item
                )

        elif aux_styles:
            rag_aux.append(item)

    # 스타일별 과도한 쏠림 방지
    rag_candidates = []

    for style, items in rag_by_style.items():
        items.sort(
            key=lambda x: (
                -int(
                    x.get(
                        "shared_score",
                        0,
                    )
                ),
                -int(
                    x.get(
                        "duplicate_count",
                        1,
                    )
                ),
                len(
                    x.get(
                        "text",
                        "",
                    )
                ),
            )
        )

        selected = items[
            : args.rag_max_per_style
        ]

        for item in selected:
            rag_candidates.append(
                {
                    "primary_style": style,
                    "text": item.get(
                        "text",
                        "",
                    ),
                    "shared_styles":
                        item.get(
                            "shared_styles",
                            [],
                        ),
                    "shared_score":
                        item.get(
                            "shared_score",
                            0,
                        ),
                    "duplicate_count":
                        item.get(
                            "duplicate_count",
                            1,
                        ),
                    "needs_generalization":
                        item.get(
                            "needs_generalization",
                            False,
                        ),
                    "conversation_id":
                        item.get(
                            "conversation_id",
                            "",
                        ),
                    "sentence_no":
                        item.get(
                            "sentence_no",
                            "",
                        ),
                    "category":
                        item.get(
                            "category",
                            "",
                        ),
                }
            )

    # =====================================================
    # 3. WAIT / GREETING 별도
    # =====================================================

    rag_aux.sort(
        key=lambda x: (
            -int(
                x.get(
                    "shared_score",
                    0,
                )
            ),
            -int(
                x.get(
                    "duplicate_count",
                    1,
                )
            ),
        )
    )

    rag_aux = rag_aux[:3000]

    # =====================================================
    # 4. 저장
    # =====================================================

    training_path = (
        output_dir
        / "training_candidates.jsonl"
    )

    rag_path = (
        output_dir
        / "rag_candidates.json"
    )

    rag_aux_path = (
        output_dir
        / "rag_auxiliary.json"
    )

    with training_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        for item in training_candidates:
            f.write(
                json.dumps(
                    item,
                    ensure_ascii=False,
                )
                + "\n"
            )

    with rag_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            rag_candidates,
            f,
            ensure_ascii=False,
            indent=2,
        )

    with rag_aux_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            rag_aux,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # =====================================================
    # 5. 통계
    # =====================================================

    training_style_counter = Counter()

    for item in training_candidates:
        for style in item["styles"]:
            training_style_counter[
                style
            ] += 1

    rag_style_counter = Counter(
        item["primary_style"]
        for item in rag_candidates
    )

    training_generalization = sum(
        1
        for item in training_candidates
        if item["needs_generalization"]
    )

    rag_generalization = sum(
        1
        for item in rag_candidates
        if item["needs_generalization"]
    )

    print()
    print("=" * 68)
    print(
        "Shared Counselor Pipeline 분리 결과"
    )
    print("=" * 68)

    print(
        f"Shared 원본 후보       : "
        f"{len(candidates):,}"
    )

    print()
    print("[Fine-tuning 후보]")

    print(
        f"- 전체                : "
        f"{len(training_candidates):,}"
    )

    print(
        f"- 고객 문맥 없음       : "
        f"{missing_context_count:,}"
    )

    print(
        f"- 일반화 필요          : "
        f"{training_generalization:,}"
    )

    print("\n스타일 분포")

    for key, value in (
        training_style_counter
        .most_common()
    ):
        print(
            f"- {key}: {value:,}"
        )

    print()
    print("[RAG 후보]")

    print(
        f"- 핵심 후보            : "
        f"{len(rag_candidates):,}"
    )

    print(
        f"- 일반화 필요          : "
        f"{rag_generalization:,}"
    )

    print(
        f"- WAIT/GREETING 별도   : "
        f"{len(rag_aux):,}"
    )

    print("\n스타일 분포")

    for key, value in (
        rag_style_counter
        .most_common()
    ):
        print(
            f"- {key}: {value:,}"
        )

    print()
    print("[SAVED]")

    print(
        f"- {training_path}"
    )

    print(
        f"- {rag_path}"
    )

    print(
        f"- {rag_aux_path}"
    )

    print()
    print(
        "주의: training_candidates.jsonl은 "
        "아직 Fine-tuning에 바로 사용하면 안 됩니다."
    )

    print(
        "다음 단계에서 고객 문맥 + 상담사 답변을 "
        "안전한 style-transfer 학습쌍으로 변환합니다."
    )


if __name__ == "__main__":
    main()
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


STYLE_ORDER = [
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
]


# =========================================================
# Utility
# =========================================================

def normalize_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_key(text: str) -> str:
    text = normalize_text(text).lower()

    text = re.sub(
        r"[.!?~·…\"'“”‘’]+",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def has_placeholder(text: str) -> bool:
    return bool(
        re.search(
            r"\{[^{}]+\}",
            text,
        )
    )


def split_clauses(text: str) -> list[str]:
    """
    상담사 발화가 여러 문장으로 구성되어 있을 경우
    짧은 문장 단위로 분리한다.
    """

    text = normalize_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    results = []

    for part in parts:
        part = normalize_text(part)

        if not part:
            continue

        # 너무 긴 문장은 연결어를 기준으로 한 번 더 분리
        if len(part) > 90:

            subparts = re.split(
                r"\s+(?:그리고|그런데|다만|그래서)\s+",
                part,
            )

            for sub in subparts:

                sub = normalize_text(sub)

                if sub:
                    results.append(sub)

        else:
            results.append(part)

    return results


# =========================================================
# 문장 공통 특징
# =========================================================

def starts_positive_response(text: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:네|예)[,.]?\s*",
            text,
        )
    )


def contains_apology(text: str) -> bool:
    return bool(
        re.search(
            r"죄송|불편|양해|안타깝",
            text,
        )
    )


def contains_inquiry_prefix(text: str) -> bool:
    return bool(
        re.search(
            r"문의\s*주신|문의주신|문의하신",
            text,
        )
    )


# =========================================================
# CONFIRMATION
# =========================================================

def extract_confirmation_frames(
    text: str,
) -> list[str]:

    frames = []

    # 확인 + 감사
    if re.search(
        r"확인해\s*주셔서\s*감사",
        text,
    ):

        if starts_positive_response(text):
            frames.append(
                "네, 확인해 주셔서 감사합니다."
            )
        else:
            frames.append(
                "확인해 주셔서 감사합니다."
            )

    if re.search(
        r"확인\s*감사",
        text,
    ):

        if re.search(
            r"감사드립|감사\s*드립",
            text,
        ):
            frames.append(
                "확인 감사드립니다."
            )
        else:
            frames.append(
                "확인 감사합니다."
            )

    # ~로 확인됩니다
    if re.search(
        r"확인됩|확인\s*됩",
        text,
    ):

        if contains_inquiry_prefix(text):

            frames.append(
                "문의주신 내용은 "
                "{확인된 정보}로 확인됩니다."
            )

        elif re.search(
            r"확인해\s*보니|확인해보니",
            text,
        ):

            frames.append(
                "확인해보니 "
                "{확인된 정보}로 확인됩니다."
            )

        elif re.search(
            r"말씀.*대로",
            text,
        ):

            frames.append(
                "말씀하신 내용대로 "
                "{확인된 정보}로 확인됩니다."
            )

        elif starts_positive_response(text):

            frames.append(
                "네, {확인된 정보}로 확인됩니다."
            )

        else:

            frames.append(
                "{확인된 정보}로 확인됩니다."
            )

    return frames


# =========================================================
# INFORMATION
# =========================================================

def extract_information_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"안내\s*드리겠습니다|안내드리겠습니다",
        text,
    ):

        if contains_inquiry_prefix(text):

            frames.append(
                "문의주신 내용에 대해 안내드리겠습니다."
            )

        else:

            frames.append(
                "확인된 내용을 안내드리겠습니다."
            )

    if re.search(
        r"말씀\s*드리겠습니다|말씀드리겠습니다",
        text,
    ):

        frames.append(
            "확인된 내용을 말씀드리겠습니다."
        )

    # 특정 정보 문장을 내용만 제거
    if re.search(
        r"입니다[.!]?$",
        text,
    ):

        if contains_inquiry_prefix(text):

            frames.append(
                "문의주신 내용은 {안내 정보}입니다."
            )

        elif starts_positive_response(text):

            frames.append(
                "네, {안내 정보}입니다."
            )

        else:

            frames.append(
                "{안내 정보}입니다."
            )

    if re.search(
        r"로\s*확인됩니다|으로\s*확인됩니다",
        text,
    ):

        frames.append(
            "{안내 정보}로 확인됩니다."
        )

    return frames


# =========================================================
# GUIDANCE
# =========================================================

def extract_guidance_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"안내.*드리",
        text,
    ):

        frames.append(
            "문의주신 내용에 대해 안내드리겠습니다."
        )

    if re.search(
        r"참고.*부탁",
        text,
    ):

        frames.append(
            "안내드린 내용을 참고 부탁드립니다."
        )

    if re.search(
        r"확인.*부탁",
        text,
    ):

        frames.append(
            "{확인할 내용}을 확인 부탁드립니다."
        )

    if re.search(
        r"말씀.*부탁",
        text,
    ):

        frames.append(
            "{필요한 내용}을 말씀해 주세요."
        )

    return frames


# =========================================================
# POSITIVE
# =========================================================

def extract_positive_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"맞습니다",
        text,
    ):

        if starts_positive_response(text):
            frames.append(
                "네, 맞습니다."
            )
        else:
            frames.append(
                "맞습니다."
            )

    if re.search(
        r"가능합니다|가능하십니다|가능해요|가능하세요",
        text,
    ):

        if starts_positive_response(text):

            frames.append(
                "네, 가능합니다."
            )

        else:

            frames.append(
                "{문의 내용}은 가능합니다."
            )

    if re.search(
        r"이용.*가능",
        text,
    ):
        frames.append(
            "{문의 내용}은 이용 가능합니다."
        )

    if re.search(
        r"사용.*가능",
        text,
    ):
        frames.append(
            "{문의 내용}은 사용 가능합니다."
        )

    return frames


# =========================================================
# NEGATIVE
# =========================================================

def extract_negative_frames(
    text: str,
) -> list[str]:

    frames = []

    apology = contains_apology(
        text
    )

    if re.search(
        r"지원되지|지원하지\s*않",
        text,
    ):

        if apology:
            frames.append(
                "죄송하지만 {문의 내용}은 "
                "지원되지 않습니다."
            )
        else:
            frames.append(
                "{문의 내용}은 지원되지 않습니다."
            )

    if re.search(
        r"불가능",
        text,
    ):

        if apology:
            frames.append(
                "죄송하지만 {문의 내용}은 어렵습니다."
            )
        else:
            frames.append(
                "{문의 내용}은 어렵습니다."
            )

    if re.search(
        r"어렵습니다|어려운\s*부분|어려운\s*점",
        text,
    ):

        if apology:
            frames.append(
                "죄송하지만 {문의 내용}은 "
                "어려운 것으로 확인됩니다."
            )
        else:
            frames.append(
                "{문의 내용}은 어려운 것으로 확인됩니다."
            )

    if re.search(
        r"할\s*수\s*없",
        text,
    ):

        frames.append(
            "{문의 내용}은 이용이 어렵습니다."
        )

    return frames


# =========================================================
# NO_INFORMATION
# =========================================================

def extract_no_information_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"확인이\s*어렵|확인하기\s*어렵",
        text,
    ):

        if contains_apology(text):

            frames.append(
                "죄송하지만 문의주신 내용은 "
                "현재 확인이 어렵습니다."
            )

        else:

            frames.append(
                "문의주신 내용은 현재 확인이 어렵습니다."
            )

    if re.search(
        r"확인되지\s*않",
        text,
    ):

        frames.append(
            "현재 제공된 정보에서는 "
            "확인되지 않습니다."
        )

    if re.search(
        r"정보가\s*없|정보에서는\s*확인",
        text,
    ):

        frames.append(
            "현재 제공된 정보에서는 "
            "확인이 어렵습니다."
        )

    if re.search(
        r"안내가\s*어렵",
        text,
    ):

        frames.append(
            "현재 확인 가능한 정보가 없어 "
            "안내가 어렵습니다."
        )

    if contains_apology(text):

        frames.append(
            "정확한 안내가 어려운 점 "
            "양해 부탁드립니다."
        )

    return frames


# =========================================================
# APOLOGY
# =========================================================

def extract_apology_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"불편.*죄송",
        text,
    ):

        frames.append(
            "불편을 드려 죄송합니다."
        )

    if re.search(
        r"죄송합니다|죄송하지만|죄송한",
        text,
    ):

        frames.append(
            "죄송합니다."
        )

    if re.search(
        r"양해.*부탁",
        text,
    ):

        frames.append(
            "양해 부탁드립니다."
        )

    if re.search(
        r"안타깝",
        text,
    ):

        frames.append(
            "안타깝게도 {문의 내용}은 "
            "어려운 것으로 확인됩니다."
        )

    return frames


# =========================================================
# CLOSING
# =========================================================

def extract_closing_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"추가.*문의|더.*문의",
        text,
    ):

        frames.append(
            "추가로 궁금하신 사항이 있으시면 "
            "말씀해 주세요."
        )

    if re.search(
        r"궁금.*사항|궁금.*점",
        text,
    ):

        frames.append(
            "궁금하신 사항이 있으시면 "
            "말씀해 주세요."
        )

    return frames


# =========================================================
# WAIT
# =========================================================

def extract_wait_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"잠시만.*기다려",
        text,
    ):

        frames.append(
            "잠시만 기다려 주세요."
        )

    if re.search(
        r"기다려.*감사",
        text,
    ):

        frames.append(
            "기다려 주셔서 감사합니다."
        )

    return frames


# =========================================================
# GREETING
# =========================================================

def extract_greeting_frames(
    text: str,
) -> list[str]:

    frames = []

    if re.search(
        r"안녕하세요",
        text,
    ):
        frames.append(
            "안녕하세요."
        )

    if re.search(
        r"안녕하십니까",
        text,
    ):
        frames.append(
            "안녕하십니까."
        )

    if re.search(
        r"반갑습니다",
        text,
    ):
        frames.append(
            "반갑습니다."
        )

    return frames


# =========================================================
# Style별 Frame Extractor
# =========================================================

FRAME_EXTRACTORS = {
    "CONFIRMATION":
        extract_confirmation_frames,

    "INFORMATION":
        extract_information_frames,

    "GUIDANCE":
        extract_guidance_frames,

    "POSITIVE":
        extract_positive_frames,

    "NEGATIVE":
        extract_negative_frames,

    "NO_INFORMATION":
        extract_no_information_frames,

    "APOLOGY":
        extract_apology_frames,

    "CLOSING":
        extract_closing_frames,

    "WAIT":
        extract_wait_frames,

    "GREETING":
        extract_greeting_frames,
}


# =========================================================
# 이미 안전하게 일반화되어 있는 Corpus Template
# =========================================================

def normalize_existing_template(
    text: str,
) -> str:

    text = normalize_text(
        text
    )

    if not has_placeholder(
        text
    ):
        return ""

    # 숫자가 들어간 Template은 사용하지 않음
    if re.search(
        r"\d",
        text,
    ):
        return ""

    return text


# =========================================================
# Main
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "전체 상담 Corpus에서 "
            "사실 내용을 제거하고 "
            "상담 표현 Frame RAG Dataset을 구축합니다."
        )
    )

    parser.add_argument(
        "--input",
        default=(
            "data/kshopping_style/"
            "rag/counselor_style_corpus.json"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "data/kshopping_style/"
            "rag/counselor_style_search.json"
        ),
    )

    parser.add_argument(
        "--stats-output",
        default=(
            "data/kshopping_style/"
            "rag/counselor_style_search_stats.json"
        ),
    )

    args = parser.parse_args()

    input_path = Path(
        args.input
    )

    output_path = Path(
        args.output
    )

    stats_path = Path(
        args.stats_output
    )

    if not input_path.exists():

        raise FileNotFoundError(
            f"Corpus 파일 없음: "
            f"{input_path}"
        )

    with input_path.open(
        "r",
        encoding="utf-8",
    ) as f:

        payload = json.load(
            f
        )

    corpus = payload.get(
        "styles",
        [],
    )

    print(
        f"[INFO] 입력 Corpus: "
        f"{len(corpus):,}"
    )

    # =====================================================
    # Frame 집계
    # =====================================================

    groups = {}

    stats = defaultdict(
        int
    )

    for entry in corpus:

        text = normalize_text(
            entry.get(
                "retrieval_text",
                "",
            )
        )

        style = str(
            entry.get(
                "style_type",
                "",
            )
        ).upper()

        pattern_type = str(
            entry.get(
                "pattern_type",
                "",
            )
        )

        source_count = int(
            entry.get(
                "source_count",
                1,
            )
            or 1
        )

        if not text:
            stats["EMPTY"] += 1
            continue

        if style not in STYLE_ORDER:
            stats["UNKNOWN_STYLE"] += 1
            continue

        # =================================================
        # 기존 일반화 Template은 그대로 활용
        # =================================================

        if (
            pattern_type
            == "GENERALIZED_TEMPLATE"
            or has_placeholder(text)
        ):

            template = (
                normalize_existing_template(
                    text
                )
            )

            if template:

                key = (
                    style,
                    normalize_key(
                        template
                    ),
                )

                if key not in groups:

                    groups[key] = {
                        "style_type":
                            style,

                        "retrieval_text":
                            template,

                        "pattern_type":
                            "CORPUS_TEMPLATE",

                        "evidence_count":
                            0,

                        "source_entry_count":
                            0,
                    }

                groups[
                    key
                ][
                    "evidence_count"
                ] += source_count

                groups[
                    key
                ][
                    "source_entry_count"
                ] += 1

                stats[
                    "CORPUS_TEMPLATE"
                ] += 1

            continue

        # =================================================
        # 실제 상담사 발화 → Frame 추출
        # =================================================

        clauses = split_clauses(
            text
        )

        extractor = FRAME_EXTRACTORS.get(
            style
        )

        if extractor is None:
            continue

        found_any = False

        for clause in clauses:

            frames = extractor(
                clause
            )

            for frame in frames:

                frame = normalize_text(
                    frame
                )

                if not frame:
                    continue

                key = (
                    style,
                    normalize_key(
                        frame
                    ),
                )

                if key not in groups:

                    groups[key] = {
                        "style_type":
                            style,

                        "retrieval_text":
                            frame,

                        "pattern_type":
                            "EXTRACTED_FRAME",

                        "evidence_count":
                            0,

                        "source_entry_count":
                            0,
                    }

                groups[
                    key
                ][
                    "evidence_count"
                ] += source_count

                groups[
                    key
                ][
                    "source_entry_count"
                ] += 1

                found_any = True

        if found_any:

            stats[
                "FRAME_EXTRACTED"
            ] += 1

        else:

            stats[
                "NO_SAFE_FRAME"
            ] += 1

    # =====================================================
    # 결과 변환
    # =====================================================

    results = list(
        groups.values()
    )

    # 너무 희귀한 Frame은 제거
    #
    # 단, Corpus Template은 유지
    filtered_results = []

    for item in results:

        if (
            item[
                "pattern_type"
            ]
            == "CORPUS_TEMPLATE"
        ):

            filtered_results.append(
                item
            )

            continue

        if (
            item[
                "source_entry_count"
            ] >= 2
            or item[
                "evidence_count"
            ] >= 3
        ):

            filtered_results.append(
                item
            )

    results = filtered_results

    # =====================================================
    # 정렬
    # =====================================================

    results.sort(
        key=lambda x: (
            STYLE_ORDER.index(
                x["style_type"]
            ),
            -x[
                "evidence_count"
            ],
            -x[
                "source_entry_count"
            ],
            x[
                "retrieval_text"
            ],
        )
    )

    style_stats = defaultdict(
        int
    )

    pattern_stats = defaultdict(
        int
    )

    for index, item in enumerate(
        results,
        start=1,
    ):

        item[
            "style_id"
        ] = (
            f"style_frame_"
            f"{index:04d}"
        )

        item[
            "knowledge_role"
        ] = "STYLE_ONLY"

        item[
            "can_be_used_as_fact"
        ] = False

        style_stats[
            item["style_type"]
        ] += 1

        pattern_stats[
            item["pattern_type"]
        ] += 1

    # =====================================================
    # 저장
    # =====================================================

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "metadata": {
                    "name":
                        (
                            "Counselor Style "
                            "Runtime Frame RAG"
                        ),

                    "source":
                        (
                            "counselor_style_"
                            "corpus.json"
                        ),

                    "input_corpus_entries":
                        len(corpus),

                    "entry_count":
                        len(results),

                    "knowledge_role":
                        "STYLE_ONLY",

                    "fact_source":
                        False,

                    "retrieval_field":
                        "retrieval_text",

                    "rule":
                        (
                            "Frames are derived from "
                            "K-Shopping counselor data "
                            "and must only be used as "
                            "response style references."
                        ),
                },

                "styles":
                    results,
            },

            f,

            ensure_ascii=False,
            indent=2,
        )

    stats_payload = {
        "input_corpus_entries":
            len(corpus),

        "output_frame_entries":
            len(results),

        "style_distribution":
            dict(
                style_stats
            ),

        "pattern_distribution":
            dict(
                pattern_stats
            ),

        "processing":
            dict(
                stats
            ),
    }

    with stats_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            stats_payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

    # =====================================================
    # 출력
    # =====================================================

    print()
    print(
        "=" * 70
    )

    print(
        "Counselor Style Frame RAG Dataset"
    )

    print(
        "=" * 70
    )

    print(
        f"입력 Corpus             : "
        f"{len(corpus):,}"
    )

    print(
        f"최종 Frame Entry        : "
        f"{len(results):,}"
    )

    print(
        "\n[Pattern Type]"
    )

    for key, value in (
        pattern_stats.items()
    ):

        print(
            f"- {key}: "
            f"{value:,}"
        )

    print(
        "\n[Style별]"
    )

    for style in STYLE_ORDER:

        print(
            f"- {style}: "
            f"{style_stats.get(style, 0):,}"
        )

    print(
        "\n[처리 결과]"
    )

    for key, value in sorted(
        stats.items(),
        key=lambda x: -x[1],
    ):

        print(
            f"- {key}: "
            f"{value:,}"
        )

    print(
        "\n[Frame 예시]"
    )

    for item in results[:50]:

        print(
            f"- "
            f"[{item['style_type']}] "
            f"{item['retrieval_text']} "
            f"("
            f"{item['pattern_type']}, "
            f"evidence="
            f"{item['evidence_count']}, "
            f"sources="
            f"{item['source_entry_count']}"
            f")"
        )

    print()
    print(
        "[SAVED]"
    )

    print(
        f"- {output_path}"
    )

    print(
        f"- {stats_path}"
    )


if __name__ == "__main__":
    main()
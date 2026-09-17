import argparse
import json
import re
from pathlib import Path
from typing import Optional


# =========================================================
# Runtime에서 실제 답변 생성에 사용할 Style
# =========================================================

RUNTIME_STYLES = [
    "CONFIRMATION",
    "INFORMATION",
    "GUIDANCE",
    "POSITIVE",
    "NEGATIVE",
    "NO_INFORMATION",
    "APOLOGY",
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


def normalize_status(
    status: Optional[str],
) -> str:
    return str(
        status or ""
    ).strip().upper()


def contains_pattern(
    text: str,
    patterns: list[str],
) -> bool:

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


# =========================================================
# Grounded Answer → 필요한 Style 결정
# =========================================================

def determine_styles(
    raw_answer: str,
    grounding_status: Optional[str],
) -> list[str]:

    answer = normalize_text(
        raw_answer
    )

    status = normalize_status(
        grounding_status
    )

    # -----------------------------------------------------
    # Grounding 정보 없음
    # -----------------------------------------------------

    if status in {
        "NO_GROUNDED_INFO",
        "NO_INFORMATION",
    }:

        return [
            "NO_INFORMATION",
            "APOLOGY",
        ]

    # -----------------------------------------------------
    # 일부만 Grounding
    # -----------------------------------------------------

    if status in {
        "PARTIAL_GROUNDED",
        "PARTIAL",
    }:

        return [
            "INFORMATION",
            "NO_INFORMATION",
        ]

    # -----------------------------------------------------
    # Grounded - 부정형
    # -----------------------------------------------------

    negative_patterns = [
        r"지원되지",
        r"지원하지 않",
        r"불가능",
        r"할 수 없",
        r"어렵습니다",
    ]

    if contains_pattern(
        answer,
        negative_patterns,
    ):

        return [
            "NEGATIVE",
            "INFORMATION",
        ]

    # -----------------------------------------------------
    # Grounded - 긍정형
    # -----------------------------------------------------

    positive_patterns = [
        r"가능합니다",
        r"가능해요",
        r"할 수 있습니다",
        r"지원합니다",
        r"맞습니다",
    ]

    if contains_pattern(
        answer,
        positive_patterns,
    ):

        return [
            "POSITIVE",
            "INFORMATION",
        ]

    # -----------------------------------------------------
    # 일반 정보형
    # -----------------------------------------------------

    return [
        "INFORMATION",
        "CONFIRMATION",
    ]


# =========================================================
# Retriever
# =========================================================

class CounselorStyleRetriever:

    def __init__(
        self,
        search_path: Optional[str] = None,
    ):

        if search_path is None:

            project_root = (
                Path(__file__)
                .resolve()
                .parents[1]
            )

            search_path = (
                project_root
                / "data"
                / "kshopping_style"
                / "rag"
                / "counselor_style_search.json"
            )

        self.search_path = Path(
            search_path
        )

        if not self.search_path.exists():

            raise FileNotFoundError(
                "Counselor Style Search Dataset 없음: "
                f"{self.search_path}"
            )

        self.entries = (
            self._load_entries()
        )

        self.by_style = (
            self._group_by_style()
        )

    # =====================================================
    # Load
    # =====================================================

    def _load_entries(
        self,
    ) -> list[dict]:

        with self.search_path.open(
            "r",
            encoding="utf-8",
        ) as f:

            payload = json.load(
                f
            )

        entries = payload.get(
            "styles",
            [],
        )

        valid = []

        for entry in entries:

            if (
                entry.get(
                    "knowledge_role"
                )
                != "STYLE_ONLY"
            ):
                continue

            if (
                entry.get(
                    "can_be_used_as_fact"
                )
                is not False
            ):
                continue

            style = str(
                entry.get(
                    "style_type",
                    "",
                )
            ).upper()

            text = normalize_text(
                entry.get(
                    "retrieval_text",
                    "",
                )
            )

            if (
                style
                not in RUNTIME_STYLES
            ):
                continue

            if not text:
                continue

            copied = dict(
                entry
            )

            copied[
                "style_type"
            ] = style

            copied[
                "retrieval_text"
            ] = text

            valid.append(
                copied
            )

        return valid

    # =====================================================
    # Style별 그룹
    # =====================================================

    def _group_by_style(
        self,
    ) -> dict[str, list[dict]]:

        grouped = {
            style: []
            for style in RUNTIME_STYLES
        }

        for entry in self.entries:

            grouped[
                entry["style_type"]
            ].append(
                entry
            )

        # 실제 상담 데이터에서
        # 많이 관찰된 Frame 우선
        for style in grouped:

            grouped[
                style
            ].sort(
                key=lambda x: (
                    -int(
                        x.get(
                            "evidence_count",
                            0,
                        )
                        or 0
                    ),
                    -int(
                        x.get(
                            "source_entry_count",
                            0,
                        )
                        or 0
                    ),
                )
            )

        return grouped

    # =====================================================
    # Retrieval
    # =========================================================

    def retrieve(
        self,
        raw_answer: str,
        grounding_status: Optional[str],
        top_k: int = 3,
    ) -> list[dict]:

        target_styles = (
            determine_styles(
                raw_answer=raw_answer,
                grounding_status=(
                    grounding_status
                ),
            )
        )

        selected = []
        used_texts = set()

        # -------------------------------------------------
        # 1차:
        # 각 Style에서 가장 근거가 많은 Frame 하나씩
        # -------------------------------------------------

        for style in target_styles:

            entries = self.by_style.get(
                style,
                [],
            )

            for entry in entries:

                text = entry[
                    "retrieval_text"
                ]

                if text in used_texts:
                    continue

                used_texts.add(
                    text
                )

                selected.append(
                    entry
                )

                break

            if len(
                selected
            ) >= top_k:
                break

        # -------------------------------------------------
        # 2차:
        # top_k가 부족하면 target style 내에서 추가
        # -------------------------------------------------

        if len(selected) < top_k:

            for style in target_styles:

                entries = self.by_style.get(
                    style,
                    [],
                )

                for entry in entries:

                    text = entry[
                        "retrieval_text"
                    ]

                    if text in used_texts:
                        continue

                    used_texts.add(
                        text
                    )

                    selected.append(
                        entry
                    )

                    if len(
                        selected
                    ) >= top_k:
                        break

                if len(
                    selected
                ) >= top_k:
                    break

        # -------------------------------------------------
        # Output
        # -------------------------------------------------

        return [
            {
                "style_id":
                    entry.get(
                        "style_id"
                    ),

                "style_type":
                    entry[
                        "style_type"
                    ],

                "retrieval_text":
                    entry[
                        "retrieval_text"
                    ],

                "pattern_type":
                    entry.get(
                        "pattern_type"
                    ),

                "evidence_count":
                    entry.get(
                        "evidence_count",
                        0,
                    ),

                "source_entry_count":
                    entry.get(
                        "source_entry_count",
                        0,
                    ),

                "knowledge_role":
                    "STYLE_ONLY",

                "can_be_used_as_fact":
                    False,
            }
            for entry in selected
        ]

    # =====================================================
    # Stats
    # =====================================================

    def stats(
        self,
    ) -> dict:

        return {
            "search_path":
                str(
                    self.search_path
                ),

            "total_runtime_frames":
                len(
                    self.entries
                ),

            "style_distribution": {
                style: len(
                    self.by_style.get(
                        style,
                        [],
                    )
                )
                for style in RUNTIME_STYLES
            },
        }


# =========================================================
# CLI 테스트
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Counselor Style Frame Retriever"
        )
    )

    parser.add_argument(
        "--answer",
        required=True,
        help=(
            "Domain Copilot의 "
            "Grounded Raw Answer"
        ),
    )

    parser.add_argument(
        "--status",
        required=True,
        help=(
            "GROUNDED / "
            "PARTIAL_GROUNDED / "
            "NO_GROUNDED_INFO"
        ),
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--stats",
        action="store_true",
    )

    args = parser.parse_args()

    retriever = (
        CounselorStyleRetriever()
    )

    if args.stats:

        print(
            json.dumps(
                retriever.stats(),
                ensure_ascii=False,
                indent=2,
            )
        )

        print()

    results = retriever.retrieve(
        raw_answer=args.answer,
        grounding_status=args.status,
        top_k=args.top_k,
    )

    print(
        "=" * 70
    )

    print(
        "Counselor Style Frame Retrieval"
    )

    print(
        "=" * 70
    )

    print(
        f"원답변 : {args.answer}"
    )

    print(
        f"상태   : {args.status}"
    )

    print()

    for index, result in enumerate(
        results,
        start=1,
    ):

        print(
            f"[{index}] "
            f"{result['style_type']}"
        )

        print(
            f"    "
            f"{result['retrieval_text']}"
        )

        print(
            f"    evidence="
            f"{result['evidence_count']}"
        )

        print()


if __name__ == "__main__":
    main()
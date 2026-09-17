import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


# =========================================================
# Shared Counselor Style RAG
#
# 목적:
# - K쇼핑 전체 상담 데이터에서 추출한 상담사 표현을
#   가능한 한 많이 보존한다.
# - 상품/정책/개인정보/실제 업무처리 정보는 제거한다.
# - 의미 유사 문장을 과도하게 병합하지 않는다.
# - 실제 RAG 검색에서는 retrieval_text만 사용한다.
#
# 중요:
# 이 데이터는 STYLE_ONLY이며 사실 근거가 아니다.
# =========================================================


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
# 개인정보 / 민감정보
# =========================================================

PERSONAL_INFO_PATTERNS = [
    r"전화\s*번호",
    r"전화번호",
    r"휴대폰",
    r"연락처",
    r"생년월일",
    r"주민\s*번호",
    r"주민번호",
    r"카드\s*번호",
    r"카드번호",
    r"계좌\s*번호",
    r"계좌번호",
    r"비밀\s*번호",
    r"비밀번호",
    r"유효\s*기간",
    r"유효기간",
    r"성함",
    r"성명",
    r"예금주",
]


# =========================================================
# 실제 업무 수행 표현
#
# Copilot이 실제로 수행하지 않는 행동을
# 했다고 말하게 만들 수 있으므로 제거
# =========================================================

BUSINESS_ACTION_PATTERNS = [
    r"접수\s*(?:해|도와|하겠|완료)",
    r"처리\s*(?:해|도와|진행|하겠|완료)",
    r"변경\s*(?:해|도와|하겠|완료)",
    r"등록\s*(?:해|도와|하겠|완료)",
    r"삭제\s*(?:해|도와|하겠|완료)",

    r"주문\s*(?:접수|처리|진행|도와)",
    r"결제\s*(?:변경|취소|처리|진행)",
    r"환불\s*(?:접수|처리|진행)",
    r"반품\s*(?:접수|처리|진행)",
    r"교환\s*(?:접수|처리|진행)",

    r"회수\s*(?:접수|처리|진행)",
    r"수거\s*(?:접수|처리|진행)",

    r"도움\s*드리겠습니다",
    r"도와\s*드리겠습니다",

    r"연락\s*드리겠습니다",
    r"전화\s*드리겠습니다",

    r"정보\s*확인\s*후",
    r"고객\s*정보\s*확인",
    r"회원\s*정보\s*확인",

    r"전산\s*처리",
    r"시스템\s*처리",
]


# =========================================================
# 콜센터에만 적합한 표현
# =========================================================

CALL_CENTER_PATTERNS = [
    r"\bARS\b",
    r"에이알에스",
    r"자동응답",
    r"상담원\s*연결",
    r"전화\s*연결",
    r"통화\s*연결",
]


# =========================================================
# 내부 업무 / 특정 회사 프로세스
# =========================================================

INTERNAL_PROCESS_PATTERNS = [
    r"업체\s*측",
    r"업체측",
    r"협력사",
    r"담당\s*부서",
    r"상담\s*부서",
    r"일반\s*상담",
    r"출하\s*지시",
    r"내부\s*확인",
]


# =========================================================
# 구체적인 사실/정책 문장 가능성이 높은 패턴
#
# 이런 정보를 Style RAG가 사실처럼 전달하면 안 됨.
# =========================================================

FACT_PATTERNS = [
    # 숫자
    r"\d",

    # 금액
    r"[일이삼사오육칠팔구십백천만억]+\s*원",

    # 기간
    r"[일이삼사오육칠팔구십백천]+\s*일",
    r"[일이삼사오육칠팔구십백천]+\s*개월",
    r"[일이삼사오육칠팔구십백천]+\s*시간",

    # 수량
    r"[일이삼사오육칠팔구십백천]+\s*개",
    r"[일이삼사오육칠팔구십백천]+\s*종",

    # 단위
    r"\bkg\b",
    r"\bg\b",
    r"\bml\b",
    r"\bl\b",
    r"\bmm\b",
    r"\bcm\b",
    r"\bpa\b",
    r"\bmah\b",
    r"\bdb\b",
    r"\brpm\b",

    # 정책 조건
    r"경우에만",
    r"이후에만",
    r"이전까지만",
    r"가장\s*(?:작은|큰|빠른|늦은)",

    # 특정 시점
    r"추석",
    r"설\s*연휴",
    r"연휴\s*이후",

    # 특정 사실 관계
    r"제품\s*하자",
    r"상품\s*하자",
    r"제품\s*불량",
    r"상품\s*불량",
]


# =========================================================
# 도메인 단어
#
# 도메인 단어가 있다고 무조건 버리지는 않는다.
# 순수 말투 문장이라면 안전한 Template으로 일반화한다.
# =========================================================

DOMAIN_TERMS = [
    "배송",
    "출고",
    "택배",
    "운송장",
    "송장",

    "주문",
    "결제",

    "교환",
    "반품",
    "환불",
    "회수",
    "수거",

    "쿠폰",
    "적립금",
    "적립",
    "할인",

    "사이즈",
    "색상",

    "상품",
    "제품",
]


# =========================================================
# 직접 상담 Style Signal
# =========================================================

STYLE_PATTERNS = {
    "CONFIRMATION": [
        r"확인",
        r"확인해\s*주셔서",
    ],

    "INFORMATION": [
        r"안내",
        r"입니다",
        r"됩니다",
        r"말씀드리",
        r"말씀\s*드리",
    ],

    "GUIDANCE": [
        r"안내.*드리",
        r"참고.*부탁",
        r"말씀.*부탁",
    ],

    "POSITIVE": [
        r"가능합니다",
        r"가능하십니다",
        r"가능해",
        r"맞습니다",
    ],

    "NEGATIVE": [
        r"지원되지",
        r"제공되지",
        r"불가능",
        r"이용.*어렵",
        r"사용.*어렵",
        r"어려운",
    ],

    "NO_INFORMATION": [
        r"확인이\s*어렵",
        r"확인하기\s*어렵",
        r"확인할\s*수\s*없",
        r"정보가\s*없",
        r"안내가\s*어렵",
        r"확인되지\s*않",
    ],

    "APOLOGY": [
        r"죄송",
        r"불편",
        r"양해",
        r"안타깝",
    ],

    "CLOSING": [
        r"추가.*문의",
        r"더\s*문의",
        r"궁금.*사항",
        r"문의하실\s*사항",
    ],

    "WAIT": [
        r"기다려",
        r"잠시만",
    ],

    "GREETING": [
        r"안녕하세요",
        r"안녕하십니까",
        r"반갑습니다",
        r"무엇을\s*도와",
    ],
}


# =========================================================
# 도메인 문장을 일반화할 때 사용하는 Template
# =========================================================

GENERALIZED_TEMPLATES = {
    "CONFIRMATION": [
        "문의주신 내용은 {확인된 정보}로 확인됩니다.",
        "{확인된 정보}로 확인됩니다.",
    ],

    "INFORMATION": [
        "문의주신 내용은 {안내 정보}입니다.",
        "{안내 정보}로 확인됩니다.",
    ],

    "GUIDANCE": [
        "문의주신 내용에 대해 안내드리겠습니다.",
        "{안내 내용}을 안내드립니다.",
    ],

    "POSITIVE": [
        "네, 가능합니다.",
        "{문의 내용}은 가능합니다.",
    ],

    "NEGATIVE": [
        "{문의 내용}은 어려운 것으로 확인됩니다.",
        "{문의 내용}은 지원되지 않습니다.",
    ],

    "NO_INFORMATION": [
        "현재 제공된 정보에서는 확인이 어렵습니다.",
        "문의주신 내용은 현재 확인이 어려운 점 양해 부탁드립니다.",
    ],

    "APOLOGY": [
        "불편을 드려 죄송합니다.",
        "{어려운 사항}에 대해 양해 부탁드립니다.",
    ],

    "CLOSING": [
        "추가로 궁금하신 사항이 있으시면 말씀해 주세요.",
    ],

    "WAIT": [
        "잠시만 기다려 주세요.",
        "기다려 주셔서 감사합니다.",
    ],

    "GREETING": [
        "무엇을 도와드릴까요?",
    ],
}


# =========================================================
# Utility
# =========================================================

def normalize_text(text: str) -> str:
    text = str(text or "")

    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_key(text: str) -> str:
    text = normalize_text(
        text
    ).lower()

    text = re.sub(
        r"[,.!?~·…\"'“”‘’]",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


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


def contains_domain_term(
    text: str,
) -> bool:

    lowered = text.lower()

    return any(
        term.lower() in lowered
        for term in DOMAIN_TERMS
    )


# =========================================================
# Style 탐지
# =========================================================

def detect_styles(
    text: str,
) -> list[str]:

    detected = []

    for style, patterns in (
        STYLE_PATTERNS.items()
    ):

        if contains_pattern(
            text,
            patterns,
        ):
            detected.append(
                style
            )

    return detected


def get_source_styles(
    item: dict,
) -> list[str]:

    styles = item.get(
        "shared_styles",
        [],
    )

    if isinstance(
        styles,
        str,
    ):
        styles = [
            styles
        ]

    if not styles:

        primary = item.get(
            "primary_style",
            "",
        )

        if primary:
            styles = [
                primary
            ]

    return [
        style
        for style in styles
        if style in STYLE_ORDER
    ]


# =========================================================
# Style 후보인지 판정
# =========================================================

def has_counselor_style_signal(
    text: str,
) -> bool:

    common_signals = [
        r"고객님",
        r"문의",
        r"확인",
        r"안내",
        r"말씀",
        r"부탁",
        r"감사",
        r"죄송",
        r"양해",
        r"가능",
        r"어렵",
        r"기다려",
        r"궁금",
    ]

    return contains_pattern(
        text,
        common_signals,
    )


# =========================================================
# 일반화
# =========================================================

def generalize_text(
    text: str,
    styles: list[str],
) -> list[tuple[str, str]]:

    """
    특정 도메인/상품 사실이 섞인 문장은
    원문을 검색 대상으로 사용하지 않고
    안전한 Style Template으로 변환한다.

    반환:
    [
        (style, generalized_text),
        ...
    ]
    """

    results = []

    for style in styles:

        templates = (
            GENERALIZED_TEMPLATES
            .get(
                style,
                [],
            )
        )

        for template in templates:

            results.append(
                (
                    style,
                    template,
                )
            )

    return results


# =========================================================
# 원문을 그대로 Corpus에 써도 되는지
# =========================================================

def validate_source_text(
    text: str,
) -> tuple[bool, str]:

    if not text:
        return False, "EMPTY"

    if len(text) < 5:
        return False, "TOO_SHORT"

    if len(text) > 120:
        return False, "TOO_LONG"

    if contains_pattern(
        text,
        PERSONAL_INFO_PATTERNS,
    ):
        return False, "PERSONAL_INFO"

    if contains_pattern(
        text,
        BUSINESS_ACTION_PATTERNS,
    ):
        return False, "BUSINESS_ACTION"

    if contains_pattern(
        text,
        CALL_CENTER_PATTERNS,
    ):
        return False, "CALL_CENTER_ONLY"

    if contains_pattern(
        text,
        INTERNAL_PROCESS_PATTERNS,
    ):
        return False, "INTERNAL_PROCESS"

    if not has_counselor_style_signal(
        text
    ):
        return False, "NO_STYLE_SIGNAL"

    return True, "PASS"


# =========================================================
# 입력 Loader
# =========================================================

def load_items(
    path: Path,
) -> list[dict]:

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:

        payload = json.load(
            f
        )

    if isinstance(
        payload,
        list,
    ):
        return payload

    if isinstance(
        payload,
        dict,
    ):

        for key in [
            "items",
            "styles",
            "data",
            "candidates",
        ]:

            value = payload.get(
                key
            )

            if isinstance(
                value,
                list,
            ):
                return value

    raise ValueError(
        f"지원하지 않는 JSON 구조: {path}"
    )


# =========================================================
# Main
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "K쇼핑 상담 데이터를 기반으로 "
            "Shared Counselor Style RAG 전체 Corpus 구축"
        )
    )

    parser.add_argument(
        "--input",
        default=(
            "data/kshopping_style/"
            "pipeline/rag_candidates.json"
        ),
    )

    parser.add_argument(
        "--aux",
        default=(
            "data/kshopping_style/"
            "pipeline/rag_auxiliary.json"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default=(
            "data/kshopping_style/rag"
        ),
    )

    args = parser.parse_args()

    input_path = Path(
        args.input
    )

    aux_path = Path(
        args.aux
    )

    output_dir = Path(
        args.output_dir
    )

    if not input_path.exists():
        raise FileNotFoundError(
            f"입력 파일 없음: {input_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates = load_items(
        input_path
    )

    auxiliary = []

    if aux_path.exists():

        auxiliary = load_items(
            aux_path
        )

    all_items = (
        candidates
        + auxiliary
    )

    print(
        f"[INFO] RAG 후보: "
        f"{len(candidates):,}"
    )

    print(
        f"[INFO] Auxiliary: "
        f"{len(auxiliary):,}"
    )

    print(
        f"[INFO] 전체 입력: "
        f"{len(all_items):,}"
    )

    # =====================================================
    # Corpus 집계
    # =====================================================

    corpus_groups = {}

    rejected = []

    reject_stats = defaultdict(
        int
    )

    generalized_source_count = 0
    raw_source_count = 0

    for item in all_items:

        text = normalize_text(
            item.get(
                "text",
                "",
            )
        )

        ok, reason = (
            validate_source_text(
                text
            )
        )

        if not ok:

            reject_stats[
                reason
            ] += 1

            rejected.append(
                {
                    "text": text,
                    "reason": reason,
                }
            )

            continue

        source_styles = (
            get_source_styles(
                item
            )
        )

        detected_styles = (
            detect_styles(
                text
            )
        )

        # 직접 탐지된 Style 우선
        styles = [
            style
            for style in detected_styles
            if style in STYLE_ORDER
        ]

        # 직접 스타일 탐지는 안 됐지만
        # 기존 정제 단계에서 Style label이 있다면 사용
        if not styles:
            styles = source_styles

        if not styles:

            reject_stats[
                "NO_STYLE"
            ] += 1

            rejected.append(
                {
                    "text": text,
                    "reason": "NO_STYLE",
                }
            )

            continue

        duplicate_count = int(
            item.get(
                "duplicate_count",
                1,
            )
            or 1
        )

        shared_score = float(
            item.get(
                "shared_score",
                0,
            )
            or 0
        )

        category = str(
            item.get(
                "category",
                "",
            )
            or ""
        ).strip()

        needs_generalization = bool(
            item.get(
                "needs_generalization",
                False,
            )
        )

        # =================================================
        # 구체 사실정보가 있으면 그대로 사용하지 않음
        # =================================================

        has_fact = contains_pattern(
            text,
            FACT_PATTERNS,
        )

        has_domain = contains_domain_term(
            text
        )

        should_generalize = (
            has_fact
            or needs_generalization
            or has_domain
        )

        # =================================================
        # 일반화 문장
        # =================================================

        if should_generalize:

            generalized = generalize_text(
                text,
                styles,
            )

            if not generalized:

                reject_stats[
                    "GENERALIZATION_FAILED"
                ] += 1

                rejected.append(
                    {
                        "text": text,
                        "reason":
                            "GENERALIZATION_FAILED",
                    }
                )

                continue

            generalized_source_count += 1

            for (
                style,
                retrieval_text,
            ) in generalized:

                key = (
                    style,
                    normalize_key(
                        retrieval_text
                    ),
                )

                if key not in corpus_groups:

                    corpus_groups[
                        key
                    ] = {
                        "style_type":
                            style,

                        "retrieval_text":
                            retrieval_text,

                        "pattern_type":
                            "GENERALIZED_TEMPLATE",

                        "source_count":
                            0,

                        "scores":
                            [],

                        "categories":
                            set(),

                        "source_examples":
                            [],
                    }

                group = corpus_groups[
                    key
                ]

                group[
                    "source_count"
                ] += duplicate_count

                group[
                    "scores"
                ].append(
                    shared_score
                )

                if category:

                    group[
                        "categories"
                    ].add(
                        category
                    )

                if (
                    len(
                        group[
                            "source_examples"
                        ]
                    )
                    < 3
                ):

                    group[
                        "source_examples"
                    ].append(
                        text
                    )

        # =================================================
        # 안전한 원문 표현
        # =================================================

        else:

            raw_source_count += 1

            for style in styles:

                key = (
                    style,
                    normalize_key(
                        text
                    ),
                )

                if key not in corpus_groups:

                    corpus_groups[
                        key
                    ] = {
                        "style_type":
                            style,

                        "retrieval_text":
                            text,

                        "pattern_type":
                            "SOURCE_EXPRESSION",

                        "source_count":
                            0,

                        "scores":
                            [],

                        "categories":
                            set(),

                        "source_examples":
                            [],
                    }

                group = corpus_groups[
                    key
                ]

                group[
                    "source_count"
                ] += duplicate_count

                group[
                    "scores"
                ].append(
                    shared_score
                )

                if category:

                    group[
                        "categories"
                    ].add(
                        category
                    )

                if (
                    len(
                        group[
                            "source_examples"
                        ]
                    )
                    < 3
                ):

                    group[
                        "source_examples"
                    ].append(
                        text
                    )

    # =====================================================
    # 최종 Corpus 변환
    # =====================================================

    corpus = []

    style_stats = defaultdict(
        int
    )

    for group in corpus_groups.values():

        avg_score = (
            sum(
                group["scores"]
            )
            / len(
                group["scores"]
            )
            if group["scores"]
            else 0
        )

        corpus.append(
            {
                "style_type":
                    group[
                        "style_type"
                    ],

                "retrieval_text":
                    group[
                        "retrieval_text"
                    ],

                "pattern_type":
                    group[
                        "pattern_type"
                    ],

                "source_count":
                    group[
                        "source_count"
                    ],

                "avg_score":
                    round(
                        avg_score,
                        2,
                    ),

                "source_categories":
                    sorted(
                        group[
                            "categories"
                        ]
                    ),

                # 감사용 데이터.
                # 실제 Retriever에서는 사용하지 않는 것을 권장.
                "source_examples":
                    group[
                        "source_examples"
                    ],

                "knowledge_role":
                    "STYLE_ONLY",

                "can_be_used_as_fact":
                    False,
            }
        )

    # 자주 등장한 표현 우선
    corpus.sort(
        key=lambda x: (
            STYLE_ORDER.index(
                x["style_type"]
            )
            if x["style_type"]
            in STYLE_ORDER
            else 999,
            -x["source_count"],
            -x["avg_score"],
        )
    )

    # ID 부여
    for index, entry in enumerate(
        corpus,
        start=1,
    ):

        entry[
            "style_id"
        ] = (
            f"style_corpus_"
            f"{index:05d}"
        )

        style_stats[
            entry["style_type"]
        ] += 1

    # =====================================================
    # 저장
    # =====================================================

    corpus_path = (
        output_dir
        / "counselor_style_corpus.json"
    )

    rejected_path = (
        output_dir
        / "counselor_style_corpus_rejected.json"
    )

    stats_path = (
        output_dir
        / "counselor_style_corpus_stats.json"
    )

    with corpus_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "metadata": {
                    "name":
                        "Shared Counselor Style RAG Corpus",

                    "source":
                        "K-Shopping counselor dialogue",

                    "knowledge_role":
                        "STYLE_ONLY",

                    "fact_source":
                        False,

                    "retrieval_field":
                        "retrieval_text",

                    "entry_count":
                        len(corpus),

                    "rule":
                        (
                            "This corpus is used only "
                            "for response tone/style. "
                            "Never use as factual evidence."
                        ),
                },

                "styles":
                    corpus,
            },

            f,

            ensure_ascii=False,
            indent=2,
        )

    with rejected_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            rejected,
            f,
            ensure_ascii=False,
            indent=2,
        )

    stats_payload = {
        "input_candidates":
            len(candidates),

        "input_auxiliary":
            len(auxiliary),

        "input_total":
            len(all_items),

        "raw_source_items":
            raw_source_count,

        "generalized_source_items":
            generalized_source_count,

        "final_corpus_entries":
            len(corpus),

        "rejected":
            len(rejected),

        "style_distribution":
            dict(
                style_stats
            ),

        "reject_distribution":
            dict(
                sorted(
                    reject_stats.items(),
                    key=lambda x: -x[1],
                )
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
    # 결과
    # =====================================================

    print()
    print(
        "=" * 70
    )

    print(
        "Shared Counselor Style RAG Corpus 구축 결과"
    )

    print(
        "=" * 70
    )

    print(
        f"전체 입력             : "
        f"{len(all_items):,}"
    )

    print(
        f"안전한 원문 사용      : "
        f"{raw_source_count:,}"
    )

    print(
        f"일반화 처리           : "
        f"{generalized_source_count:,}"
    )

    print(
        f"Rejected              : "
        f"{len(rejected):,}"
    )

    print(
        f"최종 Corpus Entry     : "
        f"{len(corpus):,}"
    )

    print(
        "\n[Style별 Corpus]"
    )

    for style in STYLE_ORDER:

        print(
            f"- {style}: "
            f"{style_stats.get(style, 0):,}"
        )

    print(
        "\n[제거 사유]"
    )

    for reason, count in sorted(
        reject_stats.items(),
        key=lambda x: -x[1],
    ):

        print(
            f"- {reason}: "
            f"{count:,}"
        )

    print(
        "\n[Corpus 예시]"
    )

    for entry in corpus[:30]:

        print(
            f"- [{entry['style_type']}] "
            f"{entry['retrieval_text']} "
            f"(count={entry['source_count']})"
        )

    print()
    print(
        "[SAVED]"
    )

    print(
        f"- {corpus_path}"
    )

    print(
        f"- {stats_path}"
    )

    print(
        f"- {rejected_path}"
    )


if __name__ == "__main__":
    main()
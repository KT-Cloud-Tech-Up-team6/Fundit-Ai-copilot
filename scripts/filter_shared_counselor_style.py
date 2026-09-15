import argparse
import json
import re
from collections import Counter
from pathlib import Path


# =========================================================
# 공통 Copilot에서 사용하면 위험한 업무 수행 표현
# =========================================================

DOMAIN_ACTION_PATTERNS = [
    # 주문 / 결제 실제 처리
    r"주문.*(?:접수|완료|진행|변경|취소).*드렸",
    r"주문.*(?:접수|완료|진행|변경|취소).*하겠",
    r"결제.*(?:변경|취소|완료|진행).*드렸",
    r"결제.*(?:변경|취소|완료|진행).*하겠",

    # 환불 / 반품 / 교환 실제 처리
    r"환불.*(?:접수|처리|진행|완료).*드렸",
    r"환불.*(?:접수|처리|진행|완료).*하겠",
    r"반품.*(?:접수|처리|진행|완료).*드렸",
    r"반품.*(?:접수|처리|진행|완료).*하겠",
    r"교환.*(?:접수|처리|진행|완료).*드렸",
    r"교환.*(?:접수|처리|진행|완료).*하겠",

    # 배송 / 회수 실제 처리
    r"배송지.*(?:변경|등록).*드렸",
    r"배송지.*(?:변경|등록).*하겠",
    r"회수.*(?:접수|진행).*드렸",
    r"회수.*(?:접수|진행).*하겠",

    # 개인정보/회원정보 실제 변경
    r"주소.*변경.*드렸",
    r"정보.*등록.*드렸",
    r"카드.*삭제.*드렸",
]


# =========================================================
# 특정 전화상담 절차
# =========================================================

CALL_CENTER_ONLY_PATTERNS = [
    r"성함.*말씀",
    r"전화\s*번호.*말씀",
    r"휴대폰\s*번호.*말씀",
    r"생년월일.*말씀",
    r"주소.*말씀",
    r"계좌\s*번호.*말씀",
    r"카드\s*번호.*말씀",
    r"유효\s*기간.*말씀",
    r"비밀\s*번호",
    r"주민\s*번호",
    r"예금주",
    r"에이알에스",
    r"\bARS\b",
    r"자동응답",
]


# =========================================================
# 너무 업무 종속적인 표현
# =========================================================

DOMAIN_SPECIFIC_PATTERNS = [
    r"택배\s*기사",
    r"회수지",
    r"수거\s*기사",
    r"인수증",
    r"가상\s*계좌",
    r"무통장",
    r"청구\s*할인",
    r"무이자",
    r"할부",
    r"입금\s*계좌",
]


# =========================================================
# 공통 상담사 표현 탐지
# =========================================================

SHARED_STYLE_RULES = {
    "APOLOGY": [
        r"죄송",
        r"불편.*드려",
        r"양해.*부탁",
        r"안타깝",
    ],

    "CONFIRMATION": [
        r"확인.*감사",
        r"확인됩니다",
        r"확인되었",
        r"확인해.*보",
        r"확인.*드리",
        r"확인 결과",
        r"확인 후",
    ],

    "GUIDANCE": [
        r"안내.*드리",
        r"말씀.*드리",
        r"참고.*부탁",
        r"도움.*드리",
    ],

    "NO_INFORMATION": [
        r"확인이 어렵",
        r"확인하기 어렵",
        r"확인할 수 없",
        r"정보가 없",
        r"안내가 어렵",
        r"정확한.*확인.*어렵",
    ],

    "POSITIVE": [
        r"가능합니다",
        r"가능하십니다",
        r"이용.*가능",
        r"사용.*가능",
        r"네.*맞습니다",
    ],

    "NEGATIVE": [
        r"불가능",
        r"어렵습니다",
        r"지원되지 않",
        r"제공되지 않",
        r"이용.*어렵",
        r"사용.*어렵",
    ],

    "INFORMATION": [
        r"확인됩니다",
        r"구성됩니다",
        r"포함되어",
        r"소요됩니다",
        r"예정입니다",
        r"가능합니다",
        r"제공됩니다",
        r"진행됩니다",
    ],

    "WAIT": [
        r"잠시만 기다려",
        r"기다려주시",
        r"기다려주셔서 감사",
    ],

    "CLOSING": [
        r"추가.*문의",
        r"더 문의",
        r"궁금.*사항",
        r"문의하실 사항",
    ],

    "GREETING": [
        r"무엇을 도와드릴까요",
        r"무엇을 도와 드릴까요",
        r"안녕하십니까",
        r"반갑습니다",
    ],
}


# =========================================================
# 라이브 Copilot에서 자연스러운 핵심 표현
# =========================================================

STYLE_BONUS_PATTERNS = [
    r"고객님",
    r"문의",
    r"확인",
    r"안내",
    r"가능",
    r"어렵",
    r"죄송",
    r"양해",
    r"감사",
    r"참고",
    r"도움",
]


# =========================================================
# 상품 고유 사실/수치 가능성 탐지
# =========================================================

FACT_PATTERNS = [
    # 숫자
    r"\d",

    # 한글 수량 / 금액
    r"[일이삼사오육칠팔구십백천만억]+\s*원",
    r"[일이삼사오육칠팔구십백천]+\s*개",
    r"[일이삼사오육칠팔구십백천]+\s*종",
    r"[일이삼사오육칠팔구십백천]+\s*개월",

    # 색상
    r"블랙",
    r"화이트",
    r"그레이",
    r"베이지",
    r"핑크",
    r"레드",
    r"블루",

    # 흔한 단위
    r"\bkg\b",
    r"\bml\b",
    r"\bmm\b",
    r"\bcm\b",
    r"\bpa\b",
    r"\bmah\b",
    r"\bdb\b",
    r"\brpm\b",
]


def normalize_text(text: str) -> str:
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def matches_any(text: str, patterns: list[str]) -> bool:
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in patterns
    )


def detect_shared_style(text: str) -> list[str]:
    """
    하나의 문장이 여러 상담 스타일을 가질 수 있으므로
    multi-label로 반환한다.
    """
    detected = []

    for style_type, patterns in SHARED_STYLE_RULES.items():
        if matches_any(text, patterns):
            detected.append(style_type)

    return detected


def calculate_reusability_score(
    text: str,
    styles: list[str],
    duplicate_count: int,
) -> int:
    """
    높을수록 여러 Copilot에서 재사용하기 좋은 상담 표현.
    """

    score = 0

    # 명확한 상담 스타일이 있으면 가점
    score += min(len(styles) * 2, 6)

    # 상담사 공통 어휘
    for pattern in STYLE_BONUS_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += 1

    # 실제 데이터에서 반복 출현한 표현
    if duplicate_count >= 100:
        score += 4
    elif duplicate_count >= 30:
        score += 3
    elif duplicate_count >= 10:
        score += 2
    elif duplicate_count >= 3:
        score += 1

    # 너무 긴 문장은 특정 업무 설명일 가능성이 큼
    if len(text) > 150:
        score -= 3
    elif len(text) > 100:
        score -= 2

    # 아주 짧으면 맥락 의존성이 큼
    if len(text) < 8:
        score -= 2

    return score


def detect_reject_reason(text: str) -> str | None:
    """
    확실히 공통 Style Layer에 부적합한 문장만 제거한다.
    애매하면 살려두고 나중에 Gemini에서 판단한다.
    """

    if len(text) < 5:
        return "TOO_SHORT"

    if matches_any(text, CALL_CENTER_ONLY_PATTERNS):
        return "CALL_CENTER_ONLY"

    if matches_any(text, DOMAIN_ACTION_PATTERNS):
        return "DOMAIN_ACTION"

    # 지나치게 긴 문장 + 업무 종속 표현
    if len(text) > 180 and matches_any(
        text,
        DOMAIN_SPECIFIC_PATTERNS,
    ):
        return "DOMAIN_SPECIFIC"

    return None


def detect_generalization_need(
    item: dict,
    text: str,
) -> bool:
    """
    상품명/가격/수량 등 사실정보가 포함됐을 가능성이 있으면
    삭제하지 않고 일반화 대상으로 표시한다.
    """

    if item.get("needs_generalization"):
        return True

    if item.get("knowledge_base"):
        return True

    if item.get("entities"):
        # 모든 entity 때문에 true로 만들지는 않고
        # 실제 특정 사실 패턴이 존재하는 경우에만 사용
        if matches_any(text, FACT_PATTERNS):
            return True

    return matches_any(text, FACT_PATTERNS)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "K쇼핑 상담사 발화 중 모든 Copilot에서 "
            "공통으로 활용할 Style 후보를 선별합니다."
        )
    )

    parser.add_argument(
        "--input",
        default=(
            "data/kshopping_style/processed/"
            "counselor_style_clean.json"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="data/kshopping_style/processed",
    )

    parser.add_argument(
        "--min-score",
        type=int,
        default=3,
        help="공통 Style 후보 최소 점수",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        raise FileNotFoundError(
            f"입력 파일이 없습니다: {input_path}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[LOAD] {input_path}")

    with input_path.open(
        "r",
        encoding="utf-8-sig",
    ) as f:
        data = json.load(f)

    print(f"[INFO] 1차 정제 데이터: {len(data):,}")

    candidates = []
    rejected = []

    for item in data:
        text = normalize_text(
            str(item.get("text", "") or "")
        )

        if not text:
            continue

        # -------------------------------------------------
        # 확실한 부적합 문장 제거
        # -------------------------------------------------

        reject_reason = detect_reject_reason(text)

        if reject_reason:
            rejected.append(
                {
                    **item,
                    "shared_reject_reason": reject_reason,
                }
            )
            continue

        # -------------------------------------------------
        # 상담 스타일 탐지
        # -------------------------------------------------

        styles = detect_shared_style(text)

        duplicate_count = int(
            item.get("duplicate_count", 1) or 1
        )

        score = calculate_reusability_score(
            text=text,
            styles=styles,
            duplicate_count=duplicate_count,
        )

        # -------------------------------------------------
        # GENERAL인데 상담 표현 점수까지 낮으면 제외
        # -------------------------------------------------

        if not styles and score < args.min_score:
            rejected.append(
                {
                    **item,
                    "shared_reject_reason":
                        "LOW_SHARED_STYLE_VALUE",
                    "shared_score": score,
                }
            )
            continue

        # 스타일이 있더라도 너무 낮은 점수면 제거
        if score < args.min_score:
            rejected.append(
                {
                    **item,
                    "shared_reject_reason":
                        "LOW_REUSABILITY_SCORE",
                    "shared_score": score,
                }
            )
            continue

        needs_generalization = (
            detect_generalization_need(
                item,
                text,
            )
        )

        candidate = {
            **item,
            "text": text,
            "shared_styles": (
                styles if styles else ["GENERAL"]
            ),
            "shared_score": score,
            "needs_generalization":
                needs_generalization,
        }

        candidates.append(candidate)

    # -----------------------------------------------------
    # 점수 → 실제 빈도 → 짧은 문장 순 정렬
    # -----------------------------------------------------

    candidates.sort(
        key=lambda x: (
            -x["shared_score"],
            -int(x.get("duplicate_count", 1)),
            len(x["text"]),
        )
    )

    # -----------------------------------------------------
    # 저장
    # -----------------------------------------------------

    candidate_path = (
        output_dir
        / "shared_counselor_style_candidates.json"
    )

    rejected_path = (
        output_dir
        / "shared_counselor_style_rejected.json"
    )

    preview_path = (
        output_dir
        / "shared_counselor_style_preview.txt"
    )

    with candidate_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            candidates,
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

    # 상위 300개를 사람이 바로 확인할 수 있게 preview 생성
    with preview_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        for i, item in enumerate(
            candidates[:300],
            start=1,
        ):
            f.write(
                f"[{i}] "
                f"score={item['shared_score']} | "
                f"count={item.get('duplicate_count', 1)} | "
                f"styles={','.join(item['shared_styles'])} | "
                f"generalize="
                f"{item['needs_generalization']}\n"
            )

            f.write(
                f"{item['text']}\n\n"
            )

    # -----------------------------------------------------
    # 통계
    # -----------------------------------------------------

    style_counter = Counter()

    for item in candidates:
        for style in item["shared_styles"]:
            style_counter[style] += 1

    reject_counter = Counter(
        item["shared_reject_reason"]
        for item in rejected
    )

    generalization_count = sum(
        1
        for item in candidates
        if item["needs_generalization"]
    )

    print()
    print("=" * 65)
    print("K쇼핑 Shared Counselor Style 2차 정제")
    print("=" * 65)

    print(
        f"입력 데이터            : {len(data):,}"
    )

    print(
        f"공통 Style 후보        : {len(candidates):,}"
    )

    print(
        f"2차 제거               : {len(rejected):,}"
    )

    print(
        f"일반화 필요 후보       : "
        f"{generalization_count:,}"
    )

    print("\n[후보 Style 분포]")

    for key, value in style_counter.most_common():
        print(
            f"- {key}: {value:,}"
        )

    print("\n[2차 제거 사유]")

    for key, value in reject_counter.most_common():
        print(
            f"- {key}: {value:,}"
        )

    print("\n[상위 후보 예시]")

    for i, item in enumerate(
        candidates[:20],
        start=1,
    ):
        print(
            f"{i:02d}. "
            f"[{','.join(item['shared_styles'])}] "
            f"(score={item['shared_score']}, "
            f"count={item.get('duplicate_count', 1)})"
        )

        print(
            f"    {item['text']}"
        )

    print("\n[SAVED]")

    print(
        f"- {candidate_path}"
    )

    print(
        f"- {rejected_path}"
    )

    print(
        f"- {preview_path}"
    )


if __name__ == "__main__":
    main()
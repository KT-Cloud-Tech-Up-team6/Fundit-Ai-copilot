import json
from pathlib import Path


CATEGORY_NAMES = {
    "CLEANING_POWER": "청소 성능",
    "WASH_DRY": "세척·건조",
    "HAIR_TANGLE": "머리카락·엉킴",
    "EDGE_REACH": "조작성·틈새",
    "WATER_TANK": "물통",
    "CLEANING_MODE": "청소 모드",
    "BATTERY": "배터리",
    "APP_REMOTE": "앱·원격제어",
    "MAINTENANCE": "관리·소모품",
    "PRODUCT_SPEC": "제품 제원",
    "FLOOR_COMPATIBILITY": "바닥재·호환성",
    "PRODUCT_COMPARE": "제품 비교",
    "OTHER_PRODUCT": "기타 상품질문",
}


TOPIC_NAMES = {
    "SUCTION_PERFORMANCE": "흡입 성능",
    "REAL_WORLD_MESS_CLEANING": "생활 오염 청소",
    "VACUUM_REPLACEMENT": "일반 청소기 대체",
    "AFTER_CLEANING_MOISTURE": "청소 후 바닥 물기",

    "AUTO_WASH": "자동 세척",
    "WASH_TEMPERATURE": "세척 온도",
    "DRYING_ODOR": "건조 후 냄새",
    "STERILIZATION": "살균",

    "HAIR_TANGLE_PREVENTION": "머리카락 엉킴 방지",
    "PET_HAIR": "반려동물 털",

    "LOW_SPACE_REACH": "낮은 공간 청소",
    "EDGE_CLEANING": "모서리·벽면 청소",
    "MANEUVERABILITY": "헤드 조작성",
    "LAY_FLAT_LEAK": "눕힘 사용 시 누수",

    "COVERAGE_PER_TANK": "물통 1회 청소 범위",
    "TANK_EMPTYING": "오수통 비우기",
    "TANK_STRUCTURE": "물통 구조",

    "MODE_DIFFERENCE": "청소 모드 차이",
    "MODE_BEHAVIOR": "청소 모드 동작",

    "BATTERY_RUNTIME": "배터리 사용시간",
    "BATTERY_CHARGING": "충전 시간",
    "BATTERY_REPLACEMENT": "배터리 교체",

    "SMART_CONNECTIVITY": "앱·원격 연결",

    "CONSUMABLE_REPLACEMENT": "소모품 교체",
    "DETERGENT_USE": "세제·클리너 사용",
    "WASTEWATER_MAINTENANCE": "오수 관리",
    "INCLUDED_ACCESSORIES": "기본 구성품",

    "COLOR_OPTIONS": "색상 옵션",
    "WEIGHT_USABILITY": "체감 무게",
    "NOISE_USABILITY": "소음 체감",
    "CERTIFICATION": "시험·인증",
    "LIGHTING": "LED 조명",

    "HARD_FLOOR_USE": "일반 바닥재 사용",
    "CARPET_RUG_USE": "카펫·러그 사용",

    "PRODUCT_COMPARISON": "제품 비교",
    "OTHER_PRODUCT_QUESTION": "기타 상품 질문",
}


class InterestTracker:
    def __init__(
        self,
        path: str = "unanswered_interest.json",
    ):
        self.path = Path(path)
        self.data = self._load()

    @staticmethod
    def _empty():
        return {
            "categories": {}
        }

    def _load(self):
        if not self.path.exists():
            return self._empty()

        try:
            data = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )

            if "categories" not in data:
                return self._empty()

            return data

        except Exception:
            return self._empty()

    def _save(self):
        self.path.write_text(
            json.dumps(
                self.data,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def reset(self):
        self.data = self._empty()
        self._save()

    def add_topics(
        self,
        topics,
        original_question: str,
    ):
        """
        미답변 질문을 category + topic_key 기준으로 묶는다.

        대표 질문은 AI가 생성하지 않고
        실제 입력된 시청자 질문을 저장해 선정한다.
        """

        original_question = original_question.strip()

        for topic in topics:
            category = topic.category
            topic_key = topic.topic_key

            category_data = (
                self.data["categories"].setdefault(
                    category,
                    {
                        "count": 0,
                        "topics": {},
                    },
                )
            )

            category_data["count"] += 1

            topic_data = (
                category_data["topics"].setdefault(
                    topic_key,
                    {
                        "count": 0,
                        "topic_name": TOPIC_NAMES.get(
                            topic_key,
                            topic_key,
                        ),
                        "viewer_questions": {},
                    },
                )
            )

            topic_data["count"] += 1

            # 실제 시청자 질문 문장을 그대로 저장
            if original_question:
                question_counts = (
                    topic_data["viewer_questions"]
                )

                question_counts[
                    original_question
                ] = (
                    question_counts.get(
                        original_question,
                        0,
                    )
                    + 1
                )

        self._save()

    @staticmethod
    def _select_representative_question(
        viewer_questions: dict,
    ):
        """
        실제 시청자 질문 중 대표 질문 선정.

        기준
        1. 가장 많이 등장한 질문
        2. 등장 횟수가 같으면 더 짧은 질문
        """

        if not viewer_questions:
            return "-", 0

        sorted_questions = sorted(
            viewer_questions.items(),
            key=lambda item: (
                -item[1],
                len(item[0]),
            ),
        )

        question, count = sorted_questions[0]

        return question, count

    def get_ranked_categories(
        self,
        top_n: int = 5,
    ):
        rows = []

        for (
            category,
            category_data,
        ) in self.data["categories"].items():

            topics = category_data.get(
                "topics",
                {},
            )

            top_topic_key = None
            top_topic = None

            if topics:
                (
                    top_topic_key,
                    top_topic,
                ) = max(
                    topics.items(),
                    key=lambda item:
                        item[1]["count"],
                )

            if top_topic:
                (
                    representative_question,
                    representative_question_count,
                ) = self._select_representative_question(
                    top_topic.get(
                        "viewer_questions",
                        {},
                    )
                )

            else:
                representative_question = "-"
                representative_question_count = 0

            rows.append(
                {
                    "category":
                        category,

                    "category_name":
                        CATEGORY_NAMES.get(
                            category,
                            category,
                        ),

                    "count":
                        category_data.get(
                            "count",
                            0,
                        ),

                    "top_topic_key":
                        top_topic_key,

                    "top_topic_name":
                        (
                            top_topic.get(
                                "topic_name",
                                top_topic_key,
                            )
                            if top_topic
                            else "-"
                        ),

                    "topic_count":
                        (
                            top_topic.get(
                                "count",
                                0,
                            )
                            if top_topic
                            else 0
                        ),

                    "representative_question":
                        representative_question,

                    "representative_question_count":
                        representative_question_count,
                }
            )

        rows.sort(
            key=lambda item:
                item["count"],
            reverse=True,
        )

        return rows[:top_n]

    def print_dashboard(
        self,
        top_n: int = 5,
    ):
        top_n = min(
            top_n,
            5,
        )

        rows = self.get_ranked_categories(
            top_n=top_n,
        )

        print()
        print("=" * 68)
        print("실시간 미답변 고객 관심사")
        print("=" * 68)

        if not rows:
            print(
                "집계된 미답변 상품 질문이 없습니다."
            )
            print("=" * 68)
            return

        for rank, row in enumerate(
            rows,
            start=1,
        ):
            print(
                f"{rank}. "
                f"{row['category_name']} "
                f"| {row['count']}건"
            )

            print(
                f"   대표 관심: "
                f"{row['top_topic_name']} "
                f"({row['topic_count']}건)"
            )

            print(
                f"   대표 질문: "
                f"{row['representative_question']} "
                f"({row['representative_question_count']}건)"
            )

            print("-" * 68)

        print("=" * 68)
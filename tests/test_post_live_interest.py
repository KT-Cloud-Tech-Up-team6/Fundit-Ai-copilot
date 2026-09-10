from types import SimpleNamespace

from core.interest_tracker import InterestTracker


def make_topic(
    category,
    topic_key,
):
    return SimpleNamespace(
        category=category,
        topic_key=topic_key,
    )


def main():

    tracker = InterestTracker(
        path="test_post_live_interest.json"
    )

    tracker.reset()


    # =====================================================
    # 앱·원격 연결 5건
    # =====================================================

    app_topic = make_topic(
        "APP_REMOTE",
        "SMART_CONNECTIVITY",
    )

    for _ in range(3):

        tracker.add_topics(
            topics=[app_topic],
            original_question=
                "앱으로 원격 조작 가능한가요?",
        )

    for _ in range(2):

        tracker.add_topics(
            topics=[app_topic],
            original_question=
                "앱 원격 조작 돼요?",
        )


    # =====================================================
    # 카펫·러그 3건
    # =====================================================

    carpet_topic = make_topic(
        "FLOOR_COMPATIBILITY",
        "CARPET_RUG_USE",
    )

    for _ in range(2):

        tracker.add_topics(
            topics=[carpet_topic],
            original_question=
                "카펫에서도 사용할 수 있나요?",
        )

    tracker.add_topics(
        topics=[carpet_topic],
        original_question=
            "러그에서도 써도 돼요?",
    )


    # =====================================================
    # 세제 1건
    # =====================================================

    detergent_topic = make_topic(
        "MAINTENANCE",
        "DETERGENT_USE",
    )

    tracker.add_topics(
        topics=[detergent_topic],
        original_question=
            "일반 세제 써도 되나요?",
    )


    # =====================================================
    # TOP 2
    # =====================================================

    rows = tracker.get_ranked_topics(
        top_n=2
    )

    print()
    print("=" * 68)
    print("POST LIVE TOP 2 TEST")
    print("=" * 68)

    for rank, row in enumerate(
        rows,
        start=1,
    ):

        print(
            f"{rank}. "
            f"{row['topic_name']} "
            f"| {row['count']}건"
        )

        print(
            "대표 질문:",
            row["representative_question"]
        )

        print("-" * 68)


    assert len(rows) == 2

    assert (
        rows[0]["topic_key"]
        == "SMART_CONNECTIVITY"
    )

    assert (
        rows[0]["count"]
        == 5
    )

    assert (
        rows[0]["representative_question"]
        == "앱으로 원격 조작 가능한가요?"
    )

    assert (
        rows[1]["topic_key"]
        == "CARPET_RUG_USE"
    )

    assert (
        rows[1]["count"]
        == 3
    )


    print(
        "POST LIVE INTEREST TEST SUCCESS"
    )


if __name__ == "__main__":
    main()
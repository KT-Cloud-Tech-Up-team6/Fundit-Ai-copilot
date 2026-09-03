import argparse
import json
import time
from collections import Counter
from pathlib import Path

from parts.p_part.interest_tracker import InterestTracker
from parts.p_part.rag_answer import answer_question
from parts.p_part.unanswered_analyzer import analyze_unanswered


DEFAULT_DATASET = str(Path(__file__).parent / "data" / "p_video_expected_questions_100.json")

RESULT_PATH = "mvp_replay_results.json"
SUMMARY_PATH = "mvp_replay_summary.json"
INTEREST_PATH = "replay_unanswered_interest.json"


def to_dict(result):
    if hasattr(result, "model_dump"):
        return result.model_dump()

    if isinstance(result, dict):
        return result

    raise TypeError(
        f"지원하지 않는 RAG 결과 타입입니다: "
        f"{type(result)}"
    )


def load_questions(path: str):
    data = json.loads(
        Path(path).read_text(
            encoding="utf-8"
        )
    )

    if isinstance(data, list):
        rows = data

    elif isinstance(data, dict):
        rows = data.get(
            "questions",
            [],
        )

    else:
        raise ValueError(
            "평가 데이터는 list 또는 "
            "{'questions': [...]} 구조여야 합니다."
        )

    questions = []

    for row in rows:
        if isinstance(row, str):
            questions.append(
                {
                    "question": row
                }
            )
            continue

        if not isinstance(
            row,
            dict,
        ):
            continue

        question = str(
            row.get(
                "question",
                "",
            )
        ).strip()

        if not question:
            continue

        questions.append(row)

    return questions


def save_json(
    path: str,
    data,
):
    Path(path).write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def count_unanswered_topics(
    tracker: InterestTracker,
):
    total = 0

    for category_data in (
        tracker.data
        .get(
            "categories",
            {}
        )
        .values()
    ):
        total += category_data.get(
            "count",
            0,
        )

    return total


def run_replay(
    dataset_path: str,
    limit: int | None,
    delay: float,
    dashboard_every: int,
):
    questions = load_questions(
        dataset_path
    )

    if limit is not None:
        questions = questions[:limit]

    if not questions:
        raise ValueError(
            "처리할 질문이 없습니다."
        )

    tracker = InterestTracker(
        path=INTEREST_PATH
    )

    # 매 실행마다 집계 초기화
    tracker.reset()

    results = []
    status_counter = Counter()

    error_count = 0

    print("=" * 72)
    print(
        "로보락 F25 Seller Copilot "
        "- P파트 자동 Replay Test"
    )
    print("=" * 72)

    print(
        f"입력 데이터 : "
        f"{dataset_path}"
    )

    print(
        f"처리 질문 수: "
        f"{len(questions)}"
    )

    print("=" * 72)

    total_start = time.time()

    for index, row in enumerate(
        questions,
        start=1,
    ):
        question = str(
            row.get(
                "question",
                "",
            )
        ).strip()

        started = time.time()

        result_row = {
            "index":
                index,

            "question":
                question,

            "expected_grounding":
                row.get(
                    "expected_grounding"
                ),

            "category":
                row.get(
                    "category"
                ),

            "tone":
                row.get(
                    "tone"
                ),

            "grounding_status":
                None,

            "answer":
                None,

            "source_chunk_ids":
                [],

            "unanswered_topics":
                [],

            "latency_sec":
                None,

            "error":
                None,
        }

        print()

        print(
            f"[{index:03d}/"
            f"{len(questions):03d}] "
            f"{question}"
        )

        try:
            rag_result = to_dict(
                answer_question(
                    question
                )
            )

            status = rag_result.get(
                "grounding_status",
                "",
            )

            answer = rag_result.get(
                "answer",
                "",
            )

            source_chunk_ids = (
                rag_result.get(
                    "source_chunk_ids",
                    [],
                )
                or []
            )

            result_row[
                "grounding_status"
            ] = status

            result_row[
                "answer"
            ] = answer

            result_row[
                "source_chunk_ids"
            ] = source_chunk_ids

            status_counter[
                status
            ] += 1

            if status == "GROUNDED":
                print(
                    "→ 상품 KB에서 처리 가능"
                )

            elif status in {
                "PARTIAL_GROUNDED",
                "NO_GROUNDED_INFO",
            }:
                analysis = analyze_unanswered(
                    question=question,
                    grounding_status=status,
                    rag_answer=answer,
                )

                topics = [
                    topic.model_dump()
                    for topic
                    in analysis.topics
                ]

                result_row[
                    "unanswered_topics"
                ] = topics

                if analysis.topics:
                    # 실제 질문 원문도 함께 전달
                    tracker.add_topics(
                        topics=analysis.topics,
                        original_question=question,
                    )

                    print(
                        "→ 미답변 관심사 반영: "
                        + ", ".join(
                            topic.category
                            for topic
                            in analysis.topics
                        )
                    )

                else:
                    print(
                        "→ 집계할 미답변 "
                        "상품 질문 없음"
                    )

            else:
                print(
                    "→ 알 수 없는 "
                    f"Grounding 상태: "
                    f"{status}"
                )

        except Exception as exc:
            error_count += 1

            result_row[
                "error"
            ] = str(exc)

            print(
                f"→ 오류: {exc}"
            )

        result_row[
            "latency_sec"
        ] = round(
            time.time()
            - started,
            3,
        )

        results.append(
            result_row
        )

        # 중간 결과 저장
        save_json(
            RESULT_PATH,
            results,
        )

        if (
            dashboard_every > 0
            and index
            % dashboard_every
            == 0
        ):
            tracker.print_dashboard()

        if delay > 0:
            time.sleep(
                delay
            )

    total_elapsed = (
        time.time()
        - total_start
    )

    ranked_categories = (
        tracker.get_ranked_categories(
            top_n=20
        )
    )

    total_unanswered = (
        count_unanswered_topics(
            tracker
        )
    )

    summary = {
        "dataset":
            dataset_path,

        "total_questions":
            len(questions),

        "status_counts":
            dict(
                status_counter
            ),

        "errors":
            error_count,

        "total_latency_sec":
            round(
                total_elapsed,
                3,
            ),

        "average_latency_sec":
            round(
                total_elapsed
                / len(questions),
                3,
            ),

        "total_unanswered_topics":
            total_unanswered,

        "ranked_unanswered_categories":
            ranked_categories,
    }

    comparable = [
        row
        for row in results
        if (
            row.get(
                "expected_grounding"
            )
            and row.get(
                "grounding_status"
            )
        )
    ]

    if comparable:
        correct = sum(
            1
            for row in comparable
            if (
                row[
                    "expected_grounding"
                ]
                ==
                row[
                    "grounding_status"
                ]
            )
        )

        summary[
            "grounding_status_accuracy"
        ] = round(
            correct
            / len(comparable),
            4,
        )

        summary[
            "grounding_status_correct"
        ] = correct

        summary[
            "grounding_status_total"
        ] = len(
            comparable
        )

    save_json(
        SUMMARY_PATH,
        summary,
    )

    print()
    print()
    print("=" * 72)
    print("Replay 완료")
    print("=" * 72)

    print(
        f"총 질문         : "
        f"{len(questions)}건"
    )

    print(
        f"Grounding 분포  : "
        f"{dict(status_counter)}"
    )

    print(
        f"미답변 질문 수  : "
        f"{total_unanswered}건"
    )

    print(
        f"평균 처리시간   : "
        f"{summary['average_latency_sec']}초"
    )

    if (
        "grounding_status_accuracy"
        in summary
    ):
        print(
            "Grounding 상태 정확도: "
            f"{summary['grounding_status_accuracy'] * 100:.2f}%"
        )

    print(
        f"상세 결과       : "
        f"{RESULT_PATH}"
    )

    print(
        f"요약 결과       : "
        f"{SUMMARY_PATH}"
    )

    tracker.print_dashboard(
        top_n=5
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=0,
    )

    parser.add_argument(
        "--dashboard-every",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    run_replay(
        dataset_path=args.dataset,
        limit=args.limit,
        delay=args.delay,
        dashboard_every=args.dashboard_every,
    )


if __name__ == "__main__":
    main()
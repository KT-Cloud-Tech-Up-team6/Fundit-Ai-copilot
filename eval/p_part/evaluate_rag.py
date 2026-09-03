import json
import time
from pathlib import Path
from collections import defaultdict

from parts.p_part.rag_retriever import retrieve
from parts.p_part.rag_answer import answer_question


# 통합 재배치: 입력은 eval/p_part/data/, 결과는 eval/results/ 공용 (경로만 수정)
INPUT_FILE = Path(__file__).parent / "data" / "p_rag_eval_50.json"
RESULT_FILE = Path(__file__).parent.parent / "results" / "p_rag_eval_results.json"
SUMMARY_FILE = Path(__file__).parent.parent / "results" / "p_rag_eval_summary.json"

TOP_K = 2


def contains_keyword(answer: str, keyword: str) -> bool:
    """
    답변에 expected keyword가 포함되는지 확인.
    공백 차이 정도는 무시.
    """
    answer_normalized = answer.lower().replace(" ", "")
    keyword_normalized = keyword.lower().replace(" ", "")

    return keyword_normalized in answer_normalized


def evaluate_case(case):
    question = case["question"]
    expected_status = case["expected_status"]
    expected_chunk_ids = case.get("expected_chunk_ids", [])
    expected_keywords = case.get("expected_answer_keywords", [])

    # --------------------------------
    # 1. Retrieval 평가
    # --------------------------------

    retrieved_chunks = retrieve(
        question,
        top_k=TOP_K
    )

    retrieved_chunk_ids = [
        chunk["chunk_id"]
        for chunk in retrieved_chunks
    ]

    # 정답 chunk가 있는 질문
    if expected_chunk_ids:
        retrieval_hit = any(
            chunk_id in retrieved_chunk_ids
            for chunk_id in expected_chunk_ids
        )

    # 정답 chunk가 없어야 하는 질문
    else:
        retrieval_hit = len(retrieved_chunk_ids) == 0

    # --------------------------------
    # 2. Grounding + 답변 생성
    # --------------------------------

    start_time = time.perf_counter()

    result = answer_question(question)

    elapsed = time.perf_counter() - start_time

    predicted_status = result["grounding_status"]
    predicted_chunk_ids = result.get(
        "source_chunk_ids",
        []
    )
    answer = result.get("answer", "")

    # --------------------------------
    # 3. Grounding Status 평가
    # --------------------------------

    status_correct = (
        predicted_status == expected_status
    )

    # --------------------------------
    # 4. 실제 사용한 source chunk 평가
    # --------------------------------

    if expected_chunk_ids:
        source_chunk_hit = any(
            chunk_id in predicted_chunk_ids
            for chunk_id in expected_chunk_ids
        )

    else:
        source_chunk_hit = (
            len(predicted_chunk_ids) == 0
        )

    # --------------------------------
    # 5. 답변 핵심값 평가
    # --------------------------------

    if expected_keywords:

        keyword_results = [
            contains_keyword(
                answer,
                keyword
            )
            for keyword in expected_keywords
        ]

        # expected keyword가 모두 포함돼야 성공
        answer_keyword_correct = all(
            keyword_results
        )

    else:
        # NO_GROUNDED_INFO는 핵심값 평가 대상 제외
        answer_keyword_correct = None

    return {
        "id": case["id"],
        "question": question,

        "expected_status": expected_status,
        "predicted_status": predicted_status,

        "expected_chunk_ids": expected_chunk_ids,
        "retrieved_chunk_ids": retrieved_chunk_ids,
        "source_chunk_ids": predicted_chunk_ids,

        "expected_answer_keywords": expected_keywords,
        "answer": answer,

        "status_correct": status_correct,
        "retrieval_hit": retrieval_hit,
        "source_chunk_hit": source_chunk_hit,
        "answer_keyword_correct": answer_keyword_correct,

        "latency_sec": round(
            elapsed,
            3
        )
    }


def calculate_summary(results):

    total = len(results)

    # -------------------------------
    # 전체 정확도
    # -------------------------------

    status_correct_count = sum(
        r["status_correct"]
        for r in results
    )

    retrieval_hit_count = sum(
        r["retrieval_hit"]
        for r in results
    )

    source_chunk_hit_count = sum(
        r["source_chunk_hit"]
        for r in results
    )

    # keyword 평가 가능한 데이터만 계산
    keyword_cases = [
        r for r in results
        if r["answer_keyword_correct"] is not None
    ]

    keyword_correct_count = sum(
        r["answer_keyword_correct"]
        for r in keyword_cases
    )

    # -------------------------------
    # 상태별 정확도
    # -------------------------------

    status_stats = defaultdict(
        lambda: {
            "total": 0,
            "correct": 0
        }
    )

    for result in results:

        expected = result["expected_status"]

        status_stats[expected]["total"] += 1

        if result["status_correct"]:
            status_stats[expected]["correct"] += 1

    status_accuracy = {}

    for status, stat in status_stats.items():

        accuracy = (
            stat["correct"]
            / stat["total"]
            * 100
        )

        status_accuracy[status] = {
            "total": stat["total"],
            "correct": stat["correct"],
            "accuracy_percent": round(
                accuracy,
                2
            )
        }

    # -------------------------------
    # Confusion Matrix
    # -------------------------------

    confusion_matrix = defaultdict(
        lambda: defaultdict(int)
    )

    for result in results:

        expected = result["expected_status"]
        predicted = result["predicted_status"]

        confusion_matrix[expected][predicted] += 1

    confusion_matrix = {
        expected: dict(predictions)
        for expected, predictions
        in confusion_matrix.items()
    }

    # -------------------------------
    # 평균 응답 시간
    # -------------------------------

    avg_latency = (
        sum(
            r["latency_sec"]
            for r in results
        )
        / total
    )

    summary = {

        "total_cases": total,

        "grounding_status_accuracy_percent": round(
            status_correct_count
            / total
            * 100,
            2
        ),

        "retrieval_hit_rate_percent": round(
            retrieval_hit_count
            / total
            * 100,
            2
        ),

        "source_chunk_hit_rate_percent": round(
            source_chunk_hit_count
            / total
            * 100,
            2
        ),

        "answer_keyword_accuracy_percent": round(
            keyword_correct_count
            / len(keyword_cases)
            * 100,
            2
        ) if keyword_cases else None,

        "average_latency_sec": round(
            avg_latency,
            3
        ),

        "status_accuracy": status_accuracy,

        "confusion_matrix": confusion_matrix
    }

    return summary


def main():

    # 평가 데이터 로드
    cases = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8"
        )
    )

    results = []

    print(
        f"\n총 {len(cases)}건 RAG 평가 시작\n"
    )

    for index, case in enumerate(
        cases,
        start=1
    ):

        print(
            f"[{index}/{len(cases)}] "
            f"{case['question']}"
        )

        try:

            result = evaluate_case(case)

            results.append(result)

            mark = (
                "✅"
                if result["status_correct"]
                else "❌"
            )

            print(
                f"  {mark} "
                f"{result['expected_status']} "
                f"→ {result['predicted_status']}"
            )

            print(
                f"  Retrieval: "
                f"{result['retrieved_chunk_ids']}"
            )

            print(
                f"  Source: "
                f"{result['source_chunk_ids']}"
            )

            print(
                f"  Latency: "
                f"{result['latency_sec']} sec"
            )

        except Exception as e:

            print(
                f"  ❌ ERROR: {e}"
            )

            results.append({
                "id": case["id"],
                "question": case["question"],
                "error": str(e),

                "expected_status":
                    case["expected_status"],

                "predicted_status":
                    "ERROR",

                "expected_chunk_ids":
                    case.get(
                        "expected_chunk_ids",
                        []
                    ),

                "retrieved_chunk_ids": [],
                "source_chunk_ids": [],

                "expected_answer_keywords":
                    case.get(
                        "expected_answer_keywords",
                        []
                    ),

                "answer": "",

                "status_correct": False,
                "retrieval_hit": False,
                "source_chunk_hit": False,
                "answer_keyword_correct": False,

                "latency_sec": 0
            })

        # 중간에 중단돼도 결과가 남도록 매번 저장
        RESULT_FILE.write_text(
            json.dumps(
                results,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        print()

    # --------------------------------
    # 최종 Summary
    # --------------------------------

    summary = calculate_summary(
        results
    )

    SUMMARY_FILE.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("=" * 60)
    print("RAG 평가 완료")
    print("=" * 60)

    print(
        f"총 평가 데이터: "
        f"{summary['total_cases']}건"
    )

    print(
        f"Grounding Status 정확도: "
        f"{summary['grounding_status_accuracy_percent']}%"
    )

    print(
        f"Retrieval Hit Rate: "
        f"{summary['retrieval_hit_rate_percent']}%"
    )

    print(
        f"Source Chunk Hit Rate: "
        f"{summary['source_chunk_hit_rate_percent']}%"
    )

    print(
        f"답변 핵심값 정확도: "
        f"{summary['answer_keyword_accuracy_percent']}%"
    )

    print(
        f"평균 응답시간: "
        f"{summary['average_latency_sec']}초"
    )

    print("\n상태별 정확도")

    for status, stat in summary[
        "status_accuracy"
    ].items():

        print(
            f"- {status}: "
            f"{stat['correct']}/{stat['total']} "
            f"({stat['accuracy_percent']}%)"
        )

    print(
        f"\n상세 결과: {RESULT_FILE}"
    )

    print(
        f"요약 결과: {SUMMARY_FILE}"
    )


if __name__ == "__main__":
    main()
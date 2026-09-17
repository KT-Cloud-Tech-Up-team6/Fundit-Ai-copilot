from services.live_product_copilot import LiveProductCopilot


def main():
    copilot = LiveProductCopilot()

    questions = [
        "흡입력 몇 파스칼이에요?",
        "앱으로 원격 조작 가능한가요?",
        "앱으로 원격 조작 가능한가요?",
        "건조는 몇 분 걸려요?",
    ]

    for question in questions:
        print()
        print(f"질문: {question}")

        result = copilot.process_comment(
            question
        )

        print(
            "Grounding:",
            result["grounding_status"],
        )

        print(
            "Answer:",
            result["answer"],
        )

    print()
    print("=" * 70)
    print("최종 관심사")
    print("=" * 70)

    copilot.print_dashboard()


if __name__ == "__main__":
    main()
from amath_bot.assignments.weekly import PaperQuestion, six_day_plan


def test_six_day_plan_is_shuffled_balanced_and_complete() -> None:
    marks = (7, 6, 5, 9, 5, 4, 6, 9, 5, 8, 8, 10, 10)
    questions = tuple(
        PaperQuestion(id=index, number=str(index), marks=mark)
        for index, mark in enumerate(marks, start=1)
    )

    plan = six_day_plan(questions, seed="SPS|2025|1")

    assert sorted(item for day in plan for item in day) == list(range(1, 14))
    assert sorted(map(len, plan)) == [2, 2, 2, 2, 2, 3]
    assert tuple(item for day in plan for item in day) != tuple(range(1, 14))
    totals = [sum(marks[item - 1] for item in day) for day in plan]
    assert max(totals) - min(totals) <= 6
    assert plan == six_day_plan(questions, seed="SPS|2025|1")

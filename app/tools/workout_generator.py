from collections.abc import Iterable

from app.schemas.workout import WorkoutDay, WorkoutExercise, WorkoutPlanData


def _rotate_days(days_per_week: int) -> Iterable[str]:
    templates = [
        "Upper Body",
        "Lower Body",
        "Push",
        "Pull",
        "Legs",
        "Conditioning",
    ]
    for i in range(days_per_week):
        yield f"Day {i + 1}: {templates[i % len(templates)]}"


def generate_workout_plan(goal: str, days_per_week: int = 4) -> WorkoutPlanData:
    safe_days = max(2, min(days_per_week, 6))

    week: list[WorkoutDay] = []
    for title in _rotate_days(safe_days):
        week.append(
            WorkoutDay(
                title=title,
                focus=goal,
                exercises=[
                    WorkoutExercise(name="Compound Lift", sets=4, reps="6-8"),
                    WorkoutExercise(name="Accessory Lift", sets=3, reps="10-12"),
                    WorkoutExercise(name="Core Finisher", sets=3, reps="12-15"),
                ],
            )
        )

    return WorkoutPlanData(
        goal=goal,
        days_per_week=safe_days,
        weekly_plan=week,
        notes="Progressive overload: add reps first, then increase load by 2.5-5%.",
    )

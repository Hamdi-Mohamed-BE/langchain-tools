from sqlalchemy.orm import Session

from app.repositories.workout_repo import WorkoutRepository
from app.schemas.workout import WorkoutExercise, WorkoutPlanData, WorkoutProgressEntry


def save_workout_plan(db: Session, user_id: int, week_start, plan: WorkoutPlanData):
    repo = WorkoutRepository(db)
    return repo.create(user_id=user_id, week_start=week_start, plan_json=plan.model_dump())


def get_latest_workout_plan_data(db: Session, user_id: int) -> WorkoutPlanData | None:
    repo = WorkoutRepository(db)
    record = repo.get_latest_for_user(user_id)
    if not record:
        return None
    return WorkoutPlanData.model_validate(record.plan_json)


def update_workout_progress(
    db: Session,
    user_id: int,
    day_title: str,
    completed_exercises: list[str] | None = None,
    notes: str | None = None,
) -> WorkoutPlanData | None:
    repo = WorkoutRepository(db)
    record = repo.get_latest_for_user(user_id)
    if not record:
        return None

    plan = WorkoutPlanData.model_validate(record.plan_json)
    clean_exercises = completed_exercises or []

    entry_index = next(
        (i for i, e in enumerate(plan.progress.entries) if e.day_title.casefold() == day_title.casefold()),
        -1,
    )

    new_entry = WorkoutProgressEntry(
        day_title=day_title,
        completed=True,
        completed_exercises=clean_exercises,
        notes=notes,
    )

    if entry_index >= 0:
        plan.progress.entries[entry_index] = new_entry
    else:
        plan.progress.entries.append(new_entry)

    repo.update_plan_json(record, plan.model_dump(mode="json"))
    return plan


def replace_exercise_in_latest_workout_plan(
    db: Session,
    user_id: int,
    current_exercise_name: str,
    replacement_exercise_name: str,
    day_title: str | None = None,
    replacement_video_url: str | None = None,
    replacement_sets: int | None = None,
    replacement_reps: str | None = None,
) -> WorkoutPlanData | None:
    def normalize(value: str) -> str:
        return value.casefold().strip()

    def matches_name(candidate: str, requested: str) -> bool:
        c = normalize(candidate)
        r = normalize(requested)
        return c == r or r in c or c in r

    def matches_day(candidate: str, requested: str) -> bool:
        c = normalize(candidate)
        r = normalize(requested)
        return c == r or r in c

    repo = WorkoutRepository(db)
    record = repo.get_latest_for_user(user_id)
    if not record:
        return None

    plan = WorkoutPlanData.model_validate(record.plan_json)
    day_key = day_title.strip() if day_title else None

    for day in plan.weekly_plan:
        if day_key and not matches_day(day.title, day_key):
            continue
        for idx, exercise in enumerate(day.exercises):
            if not matches_name(exercise.name, current_exercise_name):
                continue

            day.exercises[idx] = WorkoutExercise(
                name=replacement_exercise_name,
                sets=replacement_sets or exercise.sets,
                reps=replacement_reps or exercise.reps,
                video_url=replacement_video_url,
            )
            repo.update_plan_json(record, plan.model_dump(mode="json"))
            return plan

    return None


def build_compact_workout_snapshot(db: Session, user_id: int) -> str:
    """Builds a small context payload for the LLM with no URL-heavy data."""
    plan = get_latest_workout_plan_data(db, user_id)
    if not plan:
        return "No saved workout plan yet."

    completed_days = len(plan.progress.entries)
    total_days = len(plan.weekly_plan)
    next_day = next((day.title for day in plan.weekly_plan if day.title not in {e.day_title for e in plan.progress.entries}), "none")

    return (
        f"WorkoutState(goal={plan.goal}, days_per_week={plan.days_per_week}, "
        f"completed_days={completed_days}/{total_days}, next_day={next_day})"
    )


def delete_latest_workout_plan(db: Session, user_id: int) -> bool:
    repo = WorkoutRepository(db)
    return repo.delete_latest_for_user(user_id)

def delete_all_workout_plans(db: Session, user_id: int) -> int:
    repo = WorkoutRepository(db)
    return repo.delete_all_for_user(user_id)

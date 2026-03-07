from datetime import date

from sqlalchemy.orm import Session

from app.repositories.workout_repo import WorkoutRepository
from app.schemas.workout import WorkoutPlanData, WorkoutPlanResponse
from app.tools.workout_generator import generate_workout_plan


class WorkoutService:
    def __init__(self, db: Session) -> None:
        self.repo = WorkoutRepository(db)

    def generate_and_save_plan(self, user_id: int, goal: str, days_per_week: int) -> WorkoutPlanResponse:
        plan = generate_workout_plan(goal=goal, days_per_week=days_per_week)
        record = self.repo.create(user_id=user_id, week_start=date.today(), plan_json=plan.model_dump())
        return WorkoutPlanResponse(
            id=record.id,
            user_id=record.user_id,
            week_start=record.week_start,
            plan=plan,
            created_at=record.created_at,
        )

    def get_latest_plan(self, user_id: int) -> WorkoutPlanResponse | None:
        plan = self.repo.get_latest_for_user(user_id)
        if not plan:
            return None
        typed_plan = WorkoutPlanData.model_validate(plan.plan_json)
        return WorkoutPlanResponse(
            id=plan.id,
            user_id=plan.user_id,
            week_start=plan.week_start,
            plan=typed_plan,
            created_at=plan.created_at,
        )

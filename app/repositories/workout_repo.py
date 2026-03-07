from datetime import date

from sqlalchemy.orm import Session

from app.models.workout_plan import WorkoutPlan


class WorkoutRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, week_start: date, plan_json: dict) -> WorkoutPlan:
        plan = WorkoutPlan(user_id=user_id, week_start=week_start, plan_json=plan_json)
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def get_latest_for_user(self, user_id: int) -> WorkoutPlan | None:
        return (
            self.db.query(WorkoutPlan)
            .filter(WorkoutPlan.user_id == user_id)
            .order_by(WorkoutPlan.created_at.desc())
            .first()
        )

    def update_plan_json(self, plan: WorkoutPlan, plan_json: dict) -> WorkoutPlan:
        plan.plan_json = plan_json
        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)
        return plan

    def delete_latest_for_user(self, user_id: int) -> bool:
        latest = self.get_latest_for_user(user_id)
        if latest is None:
            return False
        self.db.delete(latest)
        self.db.commit()
        return True
    
    def delete_all_for_user(self, user_id: int) -> int:
        plans = self.db.query(WorkoutPlan).filter(WorkoutPlan.user_id == user_id).all()
        count = len(plans)
        for plan in plans:
            self.db.delete(plan)
        self.db.commit()
        return count

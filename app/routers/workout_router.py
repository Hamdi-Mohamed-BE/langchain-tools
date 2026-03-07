from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.workout import GenerateWorkoutRequest, UpdateWorkoutProgressRequest, WorkoutPlanResponse
from app.services.workout_service import WorkoutService
from app.tools.db_tools import update_workout_progress


router = APIRouter()


@router.post("/generate", response_model=WorkoutPlanResponse)
def generate(payload: GenerateWorkoutRequest, db: Session = Depends(get_db)) -> WorkoutPlanResponse:
    service = WorkoutService(db)
    return service.generate_and_save_plan(
        user_id=payload.user_id,
        goal=payload.goal,
        days_per_week=payload.days_per_week,
    )


@router.get("/latest", response_model=WorkoutPlanResponse)
def latest(user_id: int = Query(...), db: Session = Depends(get_db)) -> WorkoutPlanResponse:
    service = WorkoutService(db)
    plan = service.get_latest_plan(user_id)
    if not plan:
        raise HTTPException(status_code=404, detail="No workout plan found for this user")
    return plan


@router.post("/progress", response_model=WorkoutPlanResponse)
def update_progress(payload: UpdateWorkoutProgressRequest, db: Session = Depends(get_db)) -> WorkoutPlanResponse:
    service = WorkoutService(db)
    current = service.get_latest_plan(payload.user_id)
    if not current:
        raise HTTPException(status_code=404, detail="No workout plan found for this user")

    updated = update_workout_progress(
        db=db,
        user_id=payload.user_id,
        day_title=payload.day_title,
        completed_exercises=payload.completed_exercises,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="No workout plan found for this user")

    refreshed = service.get_latest_plan(payload.user_id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Progress was updated but plan could not be reloaded")
    return refreshed

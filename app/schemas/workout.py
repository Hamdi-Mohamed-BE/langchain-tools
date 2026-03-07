from datetime import date, datetime

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class GenerateWorkoutRequest(BaseModel):
    user_id: int
    goal: str
    days_per_week: int = 4


class WorkoutExercise(BaseModel):
    name: str
    sets: int = Field(ge=1)
    reps: str
    video_url: str | None = None


class WorkoutDay(BaseModel):
    title: str
    focus: str
    exercises: list[WorkoutExercise]


class WorkoutProgressEntry(BaseModel):
    day_title: str
    completed: bool = True
    completed_exercises: list[str] = Field(default_factory=list)
    notes: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkoutProgressData(BaseModel):
    entries: list[WorkoutProgressEntry] = Field(default_factory=list)


class WorkoutPlanData(BaseModel):
    goal: str
    days_per_week: int = Field(ge=2, le=6)
    weekly_plan: list[WorkoutDay]
    notes: str
    progress: WorkoutProgressData = Field(default_factory=WorkoutProgressData)


class UpdateWorkoutProgressRequest(BaseModel):
    user_id: int
    day_title: str
    completed_exercises: list[str] = Field(default_factory=list)
    notes: str | None = None


class WorkoutPlanResponse(BaseModel):
    id: int
    user_id: int
    week_start: date
    plan: WorkoutPlanData
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

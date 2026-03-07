from pydantic import BaseModel, HttpUrl


class ExerciseData(BaseModel):
    name: str
    muscle_group: str
    equipment: str | None = None
    video_url: HttpUrl | None = None

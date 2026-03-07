from app.tools.youtube_shorts_tool import YouTubeShortsAdapter
from app.schemas.exercise import ExerciseData


class ExerciseService:
    def __init__(self) -> None:
        self.youtube = YouTubeShortsAdapter()

    def get_exercises(self, muscle_group: str, limit: int = 6) -> list[ExerciseData]:
        return self.youtube.get_exercises(muscle_group, limit=limit)

    def get_exercises_by_names(
        self,
        exercise_names: list[str],
        default_muscle_group: str = "general",
    ) -> list[ExerciseData]:
        return self.youtube.get_exercises_by_names(
            exercise_names=exercise_names,
            default_muscle_group=default_muscle_group,
        )

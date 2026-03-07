from datetime import date
import logging
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.schemas.workout import WorkoutDay, WorkoutExercise, WorkoutPlanData, WorkoutProgressData
from app.services.exercise_service import ExerciseService
from app.tools.db_tools import (
    build_compact_workout_snapshot,
    delete_latest_workout_plan,
    get_latest_workout_plan_data,
    replace_exercise_in_latest_workout_plan,
    save_workout_plan,
    update_workout_progress,
    delete_all_workout_plans,
)


logger = logging.getLogger(__name__)


class GeneratePlanInput(BaseModel):
    goal: str = Field(description="Workout goal, e.g. muscle gain, fat loss, strength")
    days_per_week: int = Field(default=4, ge=2, le=6, description="Training days per week")


class ExerciseLookupInput(BaseModel):
    exercise_names: list[str] = Field(
        default_factory=list,
        description="Exercise names to fetch matching YouTube Shorts videos for",
    )
    default_muscle_group: str = Field(default="general", description="Fallback muscle tag for metadata")
    limit: int = Field(default=6, ge=1, le=20, description="Maximum exercises to return")

    @model_validator(mode="after")
    def validate_lookup_mode(self) -> "ExerciseLookupInput":
        has_names = any(name.strip() for name in self.exercise_names)
        if not has_names:
            raise ValueError("Provide at least one exercise name.")
        return self


class UpdateProgressInput(BaseModel):
    day_title: str = Field(description="Workout day title, e.g. Day 1 or Push Day")
    completed_exercises: list[str] = Field(default_factory=list, description="Exercise names completed")
    notes: str | None = Field(default=None, description="Optional short session notes")


class ModifyWorkoutPlanInput(BaseModel):
    current_exercise_name: str = Field(description="Existing exercise name to replace")
    new_exercise_name: str = Field(description="New exercise name that should replace the old one")
    day_title: str | None = Field(
        default=None,
        description="Optional day title to target, e.g. Day 2: Back + Biceps",
    )
    replacement_sets: int | None = Field(default=None, ge=1, le=8, description="Optional set override")
    replacement_reps: str | None = Field(default=None, description="Optional reps override, e.g. 8-12")


class AgentToolsBuilder:
    """Builder for constructing context-aware LangChain tools.

    Uses a fluent builder style and returns @tool-decorated tools from build().
    """

    def __init__(self) -> None:
        self._db: Session | None = None
        self._user_id: int | None = None
        self._exercise_service: ExerciseService | None = None
        self._tool_logger: Callable[[str, str], None] | None = None

    def with_db(self, db: Session) -> "AgentToolsBuilder":
        self._db = db
        return self

    def with_user(self, user_id: int) -> "AgentToolsBuilder":
        self._user_id = user_id
        return self

    def with_exercise_service(self, exercise_service: ExerciseService) -> "AgentToolsBuilder":
        self._exercise_service = exercise_service
        return self

    def with_tool_logger(self, tool_logger: Callable[[str, str], None] | None) -> "AgentToolsBuilder":
        self._tool_logger = tool_logger
        return self

    def _require(self) -> tuple[Session, int, ExerciseService]:
        if self._db is None:
            raise ValueError("AgentToolsBuilder requires db via with_db(...)")
        if self._user_id is None:
            raise ValueError("AgentToolsBuilder requires user_id via with_user(...)")
        if self._exercise_service is None:
            raise ValueError("AgentToolsBuilder requires exercise_service via with_exercise_service(...)")
        return self._db, self._user_id, self._exercise_service

    def _log_tool(self, tool_name: str, message: str) -> None:
        logger.info("Tool used: %s", tool_name)
        if self._tool_logger:
            self._tool_logger(tool_name, message)

    def _context(self) -> tuple[Session, int, ExerciseService]:
        return self._require()

    @staticmethod
    def _resolve_muscle_targets(days_per_week: int) -> list[tuple[str, str]]:
        split = [
            ("Day 1: Chest + Triceps", "chest"),
            ("Day 2: Back + Biceps", "back"),
            ("Day 3: Legs", "legs"),
            ("Day 4: Shoulders + Core", "shoulders"),
            ("Day 5: Upper Body Volume", "chest"),
            ("Day 6: Pull Volume", "back"),
        ]
        return split[: max(2, min(days_per_week, 6))]

    @staticmethod
    def _reps_for_goal(goal: str) -> str:
        lowered = goal.lower()
        if "strength" in lowered:
            return "4-6"
        if "fat" in lowered or "cut" in lowered:
            return "10-15"
        return "6-12"

    @staticmethod
    def _prefers_machine_isolation(goal: str) -> bool:
        lowered = goal.casefold()
        return (
            "machine" in lowered
            or "isolation" in lowered
            or "cable" in lowered
        )

    @staticmethod
    def _exercise_name_pool(muscle: str, machine_isolation: bool) -> list[str]:
        machine_pool: dict[str, list[str]] = {
            "chest": [
                "Machine Chest Press",
                "Incline Machine Press",
                "Cable Fly",
                "Pec Deck Fly",
                "Single-Arm Cable Press",
            ],
            "back": [
                "Lat Pulldown",
                "Seated Cable Row",
                "Machine High Row",
                "Straight-Arm Pulldown",
                "Single-Arm Cable Row",
            ],
            "legs": [
                "Hack Squat Machine",
                "Leg Press",
                "Leg Extension",
                "Seated Leg Curl",
                "Glute Drive Machine",
            ],
            "shoulders": [
                "Machine Shoulder Press",
                "Cable Lateral Raise",
                "Reverse Pec Deck",
                "Cable Front Raise",
                "Cable Y Raise",
            ],
        }
        standard_pool: dict[str, list[str]] = {
            "chest": [
                "Barbell Bench Press",
                "Incline Dumbbell Press",
                "Chest Dip",
                "Cable Fly",
                "Push-Up",
            ],
            "back": [
                "Pull-Up",
                "Barbell Row",
                "Lat Pulldown",
                "Seated Cable Row",
                "Dumbbell Row",
            ],
            "legs": [
                "Back Squat",
                "Romanian Deadlift",
                "Leg Press",
                "Walking Lunge",
                "Leg Curl",
            ],
            "shoulders": [
                "Overhead Press",
                "Dumbbell Lateral Raise",
                "Rear Delt Fly",
                "Arnold Press",
                "Upright Row",
            ],
        }
        pool = machine_pool if machine_isolation else standard_pool
        return pool.get(muscle, ["Compound Lift", "Accessory Lift", "Isolation Lift", "Core Finisher"])

    @classmethod
    def _select_day_exercise_names(
        cls,
        muscle: str,
        goal: str,
        count: int,
        variant_index: int,
    ) -> list[str]:
        pool = cls._exercise_name_pool(muscle=muscle, machine_isolation=cls._prefers_machine_isolation(goal))
        if not pool:
            return []

        safe_count = max(1, count)
        start = variant_index % len(pool)
        ordered = pool[start:] + pool[:start]
        unique: list[str] = []
        for name in ordered:
            if name in unique:
                continue
            unique.append(name)
            if len(unique) >= safe_count:
                break
        return unique

    def _build_real_data_plan(self, goal: str, days_per_week: int, exercise_service: ExerciseService) -> WorkoutPlanData:
        rep_range = self._reps_for_goal(goal)
        weekly_days: list[WorkoutDay] = []

        for day_idx, (day_title, muscle) in enumerate(self._resolve_muscle_targets(days_per_week)):
            chosen_names = self._select_day_exercise_names(
                muscle=muscle,
                goal=goal,
                count=4,
                variant_index=day_idx,
            )

            day_exercises: list[WorkoutExercise] = []
            for idx, selected_name in enumerate(chosen_names):
                match = self._fetch_video_for_name(
                    exercise_service=exercise_service,
                    exercise_name=selected_name,
                    default_muscle_group=muscle,
                )
                day_exercises.append(
                    WorkoutExercise(
                        name=selected_name,
                        sets=4 if idx == 0 else 3,
                        reps=rep_range,
                        video_url=self._safe_video_url(str(match.video_url)) if (match and match.video_url) else None,
                    )
                )

            weekly_days.append(
                WorkoutDay(
                    title=day_title,
                    focus=f"{goal} ({muscle})",
                    exercises=day_exercises,
                )
            )

        return WorkoutPlanData(
            goal=goal,
            days_per_week=max(2, min(days_per_week, 6)),
            weekly_plan=weekly_days,
            notes=(
                "Built from YouTube Shorts exercise search data when available. "
                "Progressive overload: add reps first, then load by 2.5-5%."
            ),
            progress=WorkoutProgressData(),
        )

    def _fetch_video_for_name(
        self,
        exercise_service: ExerciseService,
        exercise_name: str,
        default_muscle_group: str,
    ):
        enriched = exercise_service.get_exercises_by_names(
            exercise_names=[exercise_name],
            default_muscle_group=default_muscle_group,
        )
        return enriched[0] if enriched else None

    @staticmethod
    def _is_youtube_url(url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except ValueError:
            return False
        return host in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "www.youtube-nocookie.com",
        }

    @classmethod
    def _extract_youtube_id(cls, url: str) -> str | None:
        if not cls._is_youtube_url(url):
            return None

        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path_parts = [p for p in parsed.path.split("/") if p]

        if host == "youtu.be" and path_parts:
            return path_parts[0]

        if path_parts and path_parts[0] in {"shorts", "embed"} and len(path_parts) > 1:
            return path_parts[1]

        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            values = query.get("v")
            if values:
                return values[0]

        return None

    @classmethod
    def _safe_video_url(cls, url: str | None) -> str | None:
        if not url:
            return None
        cleaned = url.strip()
        if not cleaned:
            return None
        video_id = cls._extract_youtube_id(cleaned)
        if not video_id:
            return None
        return f"https://www.youtube.com/shorts/{video_id}"

    def _get_workout_state_action(self) -> str:
        db, user_id, _exercise_service = self._context()
        self._log_tool("get_workout_state", "Fetched compact workout state")
        return build_compact_workout_snapshot(db, user_id)

    def _generate_and_save_workout_plan_action(self, goal: str, days_per_week: int = 4) -> dict:
        db, user_id, exercise_service = self._context()
        self._log_tool(
            "generate_and_save_workout_plan",
            f"Generating plan for goal='{goal}', days={days_per_week}",
        )
        plan = self._build_real_data_plan(goal=goal, days_per_week=days_per_week, exercise_service=exercise_service)
        save_workout_plan(db=db, user_id=user_id, week_start=date.today(), plan=plan)
        self._log_tool("generate_and_save_workout_plan", "Saved generated workout plan")
        return {
            "status": "saved",
            "source": "youtube_shorts_api_or_fallback",
            "goal": plan.goal,
            "days_per_week": plan.days_per_week,
            "day_titles": [day.title for day in plan.weekly_plan],
        }

    def _lookup_youtube_shorts_exercises_action(
        self,
        exercise_names: list[str],
        default_muscle_group: str = "general",
        limit: int = 6,
    ) -> list[dict]:
        _db, _user_id, exercise_service = self._context()
        safe_names = [name.strip() for name in exercise_names if isinstance(name, str) and name.strip()][:limit]
        self._log_tool(
            "lookup_youtube_shorts_exercises",
            f"Fetching YouTube Shorts by exercise names count={len(safe_names)}, limit={limit}",
        )
        exercises = exercise_service.get_exercises_by_names(
            exercise_names=safe_names,
            default_muscle_group=default_muscle_group,
        )

        return [
            {
                "name": exercise.name,
                "muscle_group": exercise.muscle_group,
                "equipment": exercise.equipment,
                "video_url": str(exercise.video_url) if exercise.video_url else None,
            }
            for exercise in exercises[:limit]
        ]

    def _update_user_workout_progress_action(
        self,
        day_title: str,
        completed_exercises: list[str] | None = None,
        notes: str | None = None,
    ) -> dict:
        db, user_id, _exercise_service = self._context()
        self._log_tool("update_user_workout_progress", f"Updating progress for day='{day_title}'")
        updated = update_workout_progress(
            db=db,
            user_id=user_id,
            day_title=day_title,
            completed_exercises=completed_exercises or [],
            notes=notes,
        )
        if not updated:
            return {"status": "no_plan", "message": "No saved workout plan for current user."}

        return {
            "status": "updated",
            "day_title": day_title,
            "completed_days": len(updated.progress.entries),
            "total_days": len(updated.weekly_plan),
        }

    def _delete_latest_workout_plan_action(self) -> dict:
        db, user_id, _exercise_service = self._context()
        self._log_tool("delete_latest_workout_plan", "Deleting latest workout plan")
        deleted = delete_latest_workout_plan(db=db, user_id=user_id)
        if not deleted:
            return {"status": "no_plan", "message": "No workout plan found to delete."}
        return {"status": "deleted", "message": "Latest workout plan deleted."}

    def _delete_all_workout_plans_action(self) -> dict:
        db, user_id, _exercise_service = self._context()
        self._log_tool("delete_all_workout_plans", "Deleting all workout plans for user")
        count = delete_all_workout_plans(db=db, user_id=user_id)
        if count == 0:
            return {"status": "no_plan", "message": "No workout plans found to delete."}
        return {"status": "deleted", "message": f"Deleted {count} workout plan(s)."}

    def _modify_user_workout_plan_action(
        self,
        current_exercise_name: str,
        new_exercise_name: str,
        day_title: str | None = None,
        replacement_sets: int | None = None,
        replacement_reps: str | None = None,
    ) -> dict:
        db, user_id, exercise_service = self._context()

        enriched_new = self._fetch_video_for_name(
            exercise_service=exercise_service,
            exercise_name=new_exercise_name,
            default_muscle_group="general",
        )
        chosen_name = new_exercise_name
        chosen_video_url = self._safe_video_url(str(enriched_new.video_url)) if (enriched_new and enriched_new.video_url) else None
        effective_day_title = day_title

        self._log_tool(
            "modify_user_workout_plan",
            (
                f"Replacing '{current_exercise_name}' with '{chosen_name}'"
                + (f" on '{effective_day_title}'" if effective_day_title else "")
            ),
        )

        updated = replace_exercise_in_latest_workout_plan(
            db=db,
            user_id=user_id,
            current_exercise_name=current_exercise_name,
            replacement_exercise_name=chosen_name,
            day_title=effective_day_title,
            replacement_video_url=chosen_video_url,
            replacement_sets=replacement_sets,
            replacement_reps=replacement_reps,
        )
        if not updated:
            return {
                "status": "not_found",
                "message": "Could not find matching workout plan/day/exercise to modify.",
            }

        return {
            "status": "updated",
            "message": f"Replaced '{current_exercise_name}' with '{chosen_name}'.",
            "day_title": effective_day_title,
            "total_days": len(updated.weekly_plan),
        }

    def build(self) -> list[BaseTool]:
        self._require()

        get_workout_state = tool(
            "get_workout_state",
            description="Get the user's latest saved workout plan and progress summary.",
        )(self._get_workout_state_action)
        
        generate_and_save_workout_plan = tool(
            "generate_and_save_workout_plan",
            description=(
                "Generate a personalized weekly workout plan using goals, level, and available days, "
                "then save it for the current user."
            ),
            args_schema=GeneratePlanInput,
        )(self._generate_and_save_workout_plan_action)

        lookup_youtube_shorts_exercises = tool(
            "lookup_youtube_shorts_exercises",
            description=(
                "Search YouTube Shorts exercise videos by explicit exercise names or by target muscle group, "
                "and return structured exercise options."
            ),
            args_schema=ExerciseLookupInput,
        )(self._lookup_youtube_shorts_exercises_action)
        
        update_user_workout_progress = tool(
            "update_user_workout_progress",
            description="Update completion status and notes for a workout day in the latest saved plan.",
            args_schema=UpdateProgressInput,
        )(self._update_user_workout_progress_action)
        
        delete_latest_workout_plan_tool = tool(
            "delete_latest_workout_plan",
            description="Delete the most recently saved workout plan for the current user.",
        )(self._delete_latest_workout_plan_action)
        
        delete_all_workout_plans_tool = tool(
            "delete_all_workout_plans",
            description="Delete all saved workout plans for the current user.",
        )(self._delete_all_workout_plans_action)

        modify_user_workout_plan = tool(
            "modify_user_workout_plan",
            description=(
                "Modify the latest saved workout plan using old exercise name + day, then new exercise name. "
                "System fetches the new exercise video automatically by name and saves both name and video."
            ),
            args_schema=ModifyWorkoutPlanInput,
        )(self._modify_user_workout_plan_action)
        
        return [
            get_workout_state,
            generate_and_save_workout_plan,
            lookup_youtube_shorts_exercises,
            update_user_workout_progress,
            delete_latest_workout_plan_tool,
            delete_all_workout_plans_tool,
            modify_user_workout_plan,
        ]


def build_agent_tools(
    db: Session,
    user_id: int,
    exercise_service: ExerciseService,
    tool_logger: Callable[[str, str], None] | None = None,
) -> list[BaseTool]:
    """Compatibility wrapper around AgentToolsBuilder for existing call sites."""
    return (
        AgentToolsBuilder()
        .with_db(db)
        .with_user(user_id)
        .with_exercise_service(exercise_service)
        .with_tool_logger(tool_logger)
        .build()
    )

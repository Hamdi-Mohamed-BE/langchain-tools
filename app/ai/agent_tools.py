from datetime import date
import logging
from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.schemas.workout import WorkoutDay, WorkoutExercise, WorkoutPlanData, WorkoutProgressData
from app.ai.llm_client import LLMClient
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

    def _build_real_data_plan(self, goal: str, days_per_week: int, exercise_service: ExerciseService) -> WorkoutPlanData:
        db, user_id, _ = self._context()
        llm = LLMClient()
        context_snapshot = build_compact_workout_snapshot(db, user_id)

        # Step 1: force the LLM to produce workout structure via strict schema.
        draft = llm.generate_structured_workout_plan(
            goal=goal,
            days_per_week=max(2, min(days_per_week, 6)),
            context=context_snapshot,
        )

        # Step 2: enrich each generated exercise with a YouTube video when available.
        weekly_days: list[WorkoutDay] = []
        for day in draft.weekly_plan:
            generated_names = [exercise.name for exercise in day.exercises]
            enriched = exercise_service.get_exercises_by_names(
                exercise_names=generated_names,
                default_muscle_group=day.focus,
            )
            video_by_name = {
                item.name.casefold().strip(): self._safe_video_url(str(item.video_url)) if item.video_url else None
                for item in enriched
            }

            day_exercises: list[WorkoutExercise] = []
            for exercise in day.exercises:
                key = exercise.name.casefold().strip()
                day_exercises.append(
                    WorkoutExercise(
                        name=exercise.name,
                        sets=exercise.sets,
                        reps=exercise.reps,
                        video_url=video_by_name.get(key),
                    )
                )

            weekly_days.append(
                WorkoutDay(
                    title=day.title,
                    focus=day.focus,
                    exercises=day_exercises,
                )
            )

        return WorkoutPlanData(
            goal=draft.goal,
            days_per_week=draft.days_per_week,
            weekly_plan=weekly_days,
            notes=draft.notes or "Plan generated by AI and enriched with YouTube videos.",
            progress=WorkoutProgressData(),
        )

    def _fill_missing_video_urls(self, plan: WorkoutPlanData, exercise_service: ExerciseService) -> WorkoutPlanData:
        for day in plan.weekly_plan:
            for exercise in day.exercises:
                if exercise.video_url:
                    continue
                match = self._fetch_video_for_name(
                    exercise_service=exercise_service,
                    exercise_name=exercise.name,
                    default_muscle_group=day.focus,
                )
                if match and match.video_url:
                    exercise.video_url = self._safe_video_url(str(match.video_url))
        return plan

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
        plan = self._fill_missing_video_urls(plan=plan, exercise_service=exercise_service)
        save_workout_plan(db=db, user_id=user_id, week_start=date.today(), plan=plan)
        self._log_tool("generate_and_save_workout_plan", "Saved generated workout plan")
        return {
            "status": "saved",
            "source": "youtube_shorts_api",
            "goal": plan.goal,
            "days_per_week": plan.days_per_week,
            "day_titles": [day.title for day in plan.weekly_plan],
        }

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

    def _refresh_exercise_videos_action(self) -> dict:
        """Re-fetch YouTube videos for every exercise in the latest saved plan."""
        db, user_id, exercise_service = self._context()
        self._log_tool("refresh_exercise_videos", "Re-fetching YouTube videos for all exercises")
        plan = get_latest_workout_plan_data(db=db, user_id=user_id)
        if not plan:
            return {"status": "no_plan", "message": "No saved workout plan found to refresh."}

        refreshed_count = 0
        for day in plan.weekly_plan:
            names = [ex.name for ex in day.exercises]
            enriched = exercise_service.get_exercises_by_names(
                exercise_names=names,
                default_muscle_group=day.focus,
            )
            video_by_name = {
                item.name.casefold().strip(): self._safe_video_url(str(item.video_url)) if item.video_url else None
                for item in enriched
            }
            for exercise in day.exercises:
                key = exercise.name.casefold().strip()
                new_url = video_by_name.get(key)
                if new_url:
                    exercise.video_url = new_url
                    refreshed_count += 1

        save_workout_plan(db=db, user_id=user_id, week_start=date.today(), plan=plan)
        self._log_tool("refresh_exercise_videos", f"Refreshed {refreshed_count} video URLs")
        return {
            "status": "refreshed",
            "message": f"Re-fetched YouTube videos for {refreshed_count} exercises across {len(plan.weekly_plan)} days.",
            "refreshed_count": refreshed_count,
        }

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

        refresh_exercise_videos = tool(
            "refresh_exercise_videos",
            description=(
                "Re-fetch YouTube video URLs for every exercise in the user's latest saved workout plan. "
                "Use this when the user asks to refresh, update, or fix exercise videos."
            ),
        )(self._refresh_exercise_videos_action)

        return [
            get_workout_state,
            generate_and_save_workout_plan,
            update_user_workout_progress,
            delete_latest_workout_plan_tool,
            delete_all_workout_plans_tool,
            modify_user_workout_plan,
            refresh_exercise_videos,
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

import logging
import time
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.schemas.exercise import ExerciseData


logger = logging.getLogger(__name__)


class YouTubeShortsAdapter:
    """Exercise lookup adapter backed by YouTube Data API (Shorts-first search)."""

    _VIDEO_CACHE_TTL_SECONDS = 60 * 60 * 24
    _QUOTA_COOLDOWN_SECONDS = 60 * 15
    _video_cache: dict[str, tuple[float, str | None]] = {}
    _quota_pause_until: float = 0.0

    _seed = {
        "chest": [
            {"name": "Push-Up Variations", "muscle_group": "chest", "equipment": "bodyweight", "video_url": None},
            {"name": "Incline Press Technique", "muscle_group": "chest", "equipment": "dumbbell", "video_url": None},
        ],
        "back": [
            {"name": "Lat Pulldown Form", "muscle_group": "back", "equipment": "cable", "video_url": None},
            {"name": "Row Mechanics", "muscle_group": "back", "equipment": "dumbbell", "video_url": None},
        ],
        "legs": [
            {"name": "Squat Form Cues", "muscle_group": "legs", "equipment": "barbell", "video_url": None},
            {"name": "Romanian Deadlift Form", "muscle_group": "legs", "equipment": "barbell", "video_url": None},
        ],
        "shoulders": [
            {"name": "Overhead Press Setup", "muscle_group": "shoulders", "equipment": "dumbbell", "video_url": None},
            {"name": "Lateral Raise Technique", "muscle_group": "shoulders", "equipment": "dumbbell", "video_url": None},
        ],
    }

    def __init__(self) -> None:
        self.base_url = settings.youtube_api_base_url.rstrip("/")
        self.api_key = settings.youtube_api_key.strip()

    def get_exercises(self, muscle_group: str, limit: int = 6) -> list[ExerciseData]:
        safe_limit = max(1, min(limit, 20))

        if self.api_key:
            try:
                fetched = self._get_exercises_from_api(muscle_group=muscle_group, limit=safe_limit)
                if fetched:
                    return fetched
            except httpx.HTTPError:
                pass

        payloads = self._seed.get(muscle_group.lower(), [])
        return [ExerciseData.model_validate(item) for item in payloads[:safe_limit]]

    def get_exercises_by_names(
        self,
        exercise_names: list[str],
        default_muscle_group: str = "general",
    ) -> list[ExerciseData]:
        """Resolve a list of exercise names to YouTube Shorts video URLs.

        This supports name-first planning where the AI picks exercise names first,
        then the adapter enriches each name with a matching shorts video.
        """
        clean_names = [name.strip() for name in exercise_names if isinstance(name, str) and name.strip()]
        unique_names: list[str] = []
        seen: set[str] = set()
        for name in clean_names:
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            unique_names.append(name)

        results: list[ExerciseData] = []
        for name in unique_names:
            video_url = None
            if self.api_key and not self._is_quota_paused():
                video_url = self._find_video_for_exercise_name(name)
            results.append(
                ExerciseData(
                    name=name,
                    muscle_group=default_muscle_group,
                    equipment=self._infer_equipment(name),
                    video_url=video_url,
                )
            )

        return results

    @classmethod
    def _is_quota_paused(cls) -> bool:
        return time.time() < cls._quota_pause_until

    @classmethod
    def _set_quota_pause(cls) -> None:
        cls._quota_pause_until = time.time() + cls._QUOTA_COOLDOWN_SECONDS
        logger.warning("YouTube quota cooldown enabled for %s seconds", cls._QUOTA_COOLDOWN_SECONDS)

    @classmethod
    def _cache_get(cls, key: str) -> str | None | object:
        cached = cls._video_cache.get(key)
        if not cached:
            return _CACHE_MISS
        expires_at, value = cached
        if time.time() >= expires_at:
            cls._video_cache.pop(key, None)
            return _CACHE_MISS
        return value

    @classmethod
    def _cache_set(cls, key: str, value: str | None) -> None:
        cls._video_cache[key] = (time.time() + cls._VIDEO_CACHE_TTL_SECONDS, value)

    def _find_video_for_exercise_name(self, exercise_name: str) -> str | None:
        cache_key = exercise_name.casefold().strip()
        cached = self._cache_get(cache_key)
        if cached is not _CACHE_MISS:
            return cached  # type: ignore[return-value]

        if self._is_quota_paused():
            self._cache_set(cache_key, None)
            return None

        query = f"{exercise_name} exercise tutorial shorts"
        params = {
            "part": "snippet",
            "type": "video",
            "videoDuration": "short",
            "maxResults": 8,
            "q": query,
            "key": self.api_key,
            "safeSearch": "strict",
            "regionCode": settings.youtube_region_code,
            "fields": "items(id/videoId,snippet/title)",
        }

        try:
            with httpx.Client(base_url=self.base_url, timeout=12.0) as client:
                response = client.get("/search", params=params)

            if response.status_code == 403 and self._is_quota_exceeded_response(response):
                self._set_quota_pause()
                self._cache_set(cache_key, None)
                return None

            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError:
            self._cache_set(cache_key, None)
            return None

        items = payload.get("items", []) if isinstance(payload, dict) else []
        requested_key = exercise_name.casefold().strip()

        for item in items:
            if not isinstance(item, dict):
                continue
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            id_payload = item.get("id") if isinstance(item.get("id"), dict) else {}
            video_id = id_payload.get("videoId")
            title = snippet.get("title") if isinstance(snippet.get("title"), str) else ""
            if not isinstance(video_id, str) or not video_id.strip():
                continue

            normalized_title = self._normalize_exercise_name(title).casefold().strip()
            if requested_key in normalized_title or normalized_title in requested_key:
                selected = f"https://www.youtube.com/shorts/{video_id.strip()}"
                self._cache_set(cache_key, selected)
                return selected

        first_valid = next(
            (
                item
                for item in items
                if isinstance(item, dict)
                and isinstance(item.get("id"), dict)
                and isinstance(item.get("id", {}).get("videoId"), str)
                and item.get("id", {}).get("videoId", "").strip()
            ),
            None,
        )
        if first_valid:
            first_id = first_valid["id"]["videoId"].strip()
            selected = f"https://www.youtube.com/shorts/{first_id}"
            self._cache_set(cache_key, selected)
            return selected

        self._cache_set(cache_key, None)
        return None

    @staticmethod
    def _is_quota_exceeded_response(response: httpx.Response) -> bool:
        try:
            payload = response.json()
        except ValueError:
            return False

        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return False

        errors = error.get("errors")
        if isinstance(errors, list):
            for entry in errors:
                if isinstance(entry, dict) and entry.get("reason") == "quotaExceeded":
                    return True

        message = error.get("message")
        return isinstance(message, str) and "quota" in message.casefold()

    def _get_exercises_from_api(self, muscle_group: str, limit: int) -> list[ExerciseData]:
        query = f"{muscle_group} workout exercise tutorial shorts"
        params = {
            "part": "snippet",
            "type": "video",
            "videoDuration": "short",
            "maxResults": min(50, max(10, limit * 4)),
            "q": query,
            "key": self.api_key,
            "safeSearch": "strict",
            "regionCode": settings.youtube_region_code,
        }

        with httpx.Client(base_url=self.base_url, timeout=15.0) as client:
            response = client.get("/search", params=params)
            response.raise_for_status()
            payload = response.json()

        items = payload.get("items", []) if isinstance(payload, dict) else []
        exercises: list[ExerciseData] = []
        seen_names: set[str] = set()

        for item in items:
            if not isinstance(item, dict):
                continue

            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            id_payload = item.get("id") if isinstance(item.get("id"), dict) else {}
            video_id = id_payload.get("videoId")
            if not isinstance(video_id, str) or not video_id.strip():
                continue

            title = snippet.get("title") if isinstance(snippet.get("title"), str) else ""
            name = self._normalize_exercise_name(title)
            name_key = name.casefold().strip()
            if not name_key or name_key in seen_names:
                continue
            seen_names.add(name_key)

            video_url = f"https://www.youtube.com/shorts/{video_id.strip()}"
            exercises.append(
                ExerciseData(
                    name=name,
                    muscle_group=muscle_group,
                    equipment=self._infer_equipment(title),
                    video_url=video_url,
                )
            )
            if len(exercises) >= limit:
                break

        return exercises[:limit]

    @staticmethod
    def _normalize_exercise_name(title: str) -> str:
        cleaned = title.strip()
        if "|" in cleaned:
            cleaned = cleaned.split("|", 1)[0].strip()
        if "-" in cleaned and len(cleaned) > 40:
            cleaned = cleaned.split("-", 1)[0].strip()
        return cleaned or "Exercise"

    @staticmethod
    def _infer_equipment(title: str) -> str | None:
        lowered = title.casefold()
        if "barbell" in lowered:
            return "barbell"
        if "dumbbell" in lowered:
            return "dumbbell"
        if "cable" in lowered:
            return "cable"
        if "machine" in lowered:
            return "machine"
        if "bodyweight" in lowered or "calisthenics" in lowered:
            return "bodyweight"
        return None

    @staticmethod
    def is_youtube_url(url: str) -> bool:
        try:
            host = urlparse(url).netloc.lower()
        except ValueError:
            return False
        return host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}


_CACHE_MISS = object()

import logging
import time
from urllib.parse import urlparse

from youtube_search import YoutubeSearch

from app.schemas.exercise import ExerciseData


logger = logging.getLogger(__name__)


class YouTubeShortsAdapter:
    """Exercise lookup adapter using youtube-search (no API key required)."""

    _VIDEO_CACHE_TTL_SECONDS = 60 * 60 * 24
    _video_cache: dict[str, tuple[float, str | None]] = {}

    def get_exercises(self, muscle_group: str, limit: int = 6) -> list[ExerciseData]:
        safe_limit = max(1, min(limit, 20))
        try:
            return self._search_exercises(
                query=f"{muscle_group} workout exercise short",
                muscle_group=muscle_group,
                limit=safe_limit,
            )
        except Exception:
            logger.exception("youtube-search lookup failed for muscle_group='%s'", muscle_group)
            return []

    def get_exercises_by_names(
        self,
        exercise_names: list[str],
        default_muscle_group: str = "general",
    ) -> list[ExerciseData]:
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

        query = f"{exercise_name} exercise tutorial short"
        try:
            results = YoutubeSearch(query, max_results=5).to_dict()
        except Exception:
            logger.exception("youtube-search failed for exercise '%s'", exercise_name)
            self._cache_set(cache_key, None)
            return None

        if not results:
            self._cache_set(cache_key, None)
            return None

        # Prefer short-duration videos (<= 60s) when available.
        for item in results:
            duration = item.get("duration", "")
            video_id = item.get("id", "")
            if video_id and self._is_short_duration(duration):
                url = f"https://www.youtube.com/shorts/{video_id}"
                self._cache_set(cache_key, url)
                return url

        # Fallback to first result as a regular watch link.
        first_id = results[0].get("id", "")
        if first_id:
            url = f"https://www.youtube.com/watch?v={first_id}"
            self._cache_set(cache_key, url)
            return url

        self._cache_set(cache_key, None)
        return None

    def _search_exercises(self, query: str, muscle_group: str, limit: int) -> list[ExerciseData]:
        try:
            results = YoutubeSearch(query, max_results=min(50, limit * 4)).to_dict()
        except Exception:
            logger.exception("youtube-search lookup failed for query='%s'", query)
            return []

        exercises: list[ExerciseData] = []
        seen_names: set[str] = set()

        for item in results:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id", "")
            title = item.get("title", "")
            if not video_id or not title:
                continue

            name = self._normalize_exercise_name(title)
            name_key = name.casefold().strip()
            if not name_key or name_key in seen_names:
                continue
            seen_names.add(name_key)

            duration = item.get("duration", "")
            if self._is_short_duration(duration):
                video_url = f"https://www.youtube.com/shorts/{video_id}"
            else:
                video_url = f"https://www.youtube.com/watch?v={video_id}"

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
    def _is_short_duration(duration: str) -> bool:
        """Check if a duration string like '0:45' or '1:10' is <= 60 seconds."""
        if not duration:
            return False
        parts = duration.strip().split(":")
        try:
            if len(parts) == 2:
                minutes, seconds = int(parts[0]), int(parts[1])
                return minutes == 0 or (minutes == 1 and seconds == 0)
            if len(parts) == 1:
                return int(parts[0]) <= 60
        except ValueError:
            return False
        return False

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

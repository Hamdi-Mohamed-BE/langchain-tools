# Implementation Progress Log

This file tracks implementation work step by step.

## 2026-03-07

1. Reviewed provided technical plan and workspace baseline.
2. Scaffolded project directories under `app/` and `static/`.
3. Added initial backend core:
   - `app/main.py`
   - `app/core/config.py`
   - `app/core/database.py`
4. Added SQLAlchemy models:
   - users
   - workout_plans
   - exercises
   - chat_messages
5. Added repositories for user, workout, and chat persistence.
6. Added services for auth, chat, workout, exercise, and image placeholder logic.
7. Added LangChain Gemini client in `app/ai/llm_client.py`.
8. Added chat streaming endpoint with SSE (`/chat/stream`).
9. Added auth and workout endpoints.
10. Added temporary frontend files:
    - `static/index.html`
    - `static/styles.css`
    - `static/app.js`
11. Added `pyproject.toml` to use **uv** as package manager source of truth.
12. Added `.env.example` with Gemini and backend keys.
13. Updated plan document for LangChain + Gemini and uv.
14. Refactored data flow to use Pydantic models where needed:
    - `ExerciseData`
    - `WorkoutExercise`
    - `WorkoutDay`
    - `WorkoutPlanData`
    - `WorkoutPlanResponse`
    - `ChatContextMessage`
15. Replaced several dict-based internal payloads with typed models in services/tools/context manager.
16. Added `README.md` with uv-first setup and run commands.
17. Extended `.gitignore` for uv/Python runtime artifacts.
18. Updated `.env` with canonical `GEMINI_MODEL` and backend defaults while keeping existing keys.
19. Kept `requirements.txt` as compatibility export and marked `pyproject.toml` as canonical source.
20. Ran VS Code error validation: no errors found.
21. Added `run_server.sh` to automate Python/uv installation and run the FastAPI server from a single bash command.
22. Updated `README.md` with one-file startup instructions.
23. Rewrote `README.md` with full codebase documentation, architecture, setup paths, API examples, and direct code references.
24. Patched `run_server.sh` to auto-relaunch under bash when invoked with `sh`, fixing `pipefail` startup error.
25. Expanded `README.md` with dedicated LangChain integration documentation and LangChain tools catalog, flow, and extension guide.
26. Integrated real MuscleWiki API in `app/tools/musclewiki_tool.py` using `X-API-Key` auth and `/exercises` + `/exercises/{id}` endpoints.
27. Added MuscleWiki env settings in `app/core/config.py` and `.env.example`.
28. Updated README docs for MuscleWiki API configuration and fallback behavior.
29. Implemented LangChain-native tool calling flow (`bind_tools` + tool-call loop) in `app/ai/llm_client.py`.
30. Added context-aware agent tool factory in `app/ai/agent_tools.py` for state lookup, plan generation/saving, exercise lookup, and progress updates.
31. Refactored `app/services/chat_service.py` to delegate actions to tools instead of keyword-only hardcoded operations.
32. Fixed `ChatService._build_optimized_context` signature mismatch that caused SSE stream runtime crash.
33. Renamed setup workflow by adding `setup_server.sh` (install/bootstrap + run).
34. Converted `run_server.sh` to run-only mode (no reinstall/re-sync).
35. Updated README startup instructions to use `setup_server.sh` once and `run_server.sh` for normal runs.
36. Fixed Gemini tool-calling compatibility in `app/ai/llm_client.py` by invoking tools with full tool-call payload and appending `ToolMessage` outputs directly.
37. Refactored `app/ai/llm_client.py` to LangChain `create_agent(...)` flow for tool-enabled requests, replacing manual `bind_tools` loop.
38. Switched from unavailable `create_agent` import to version-compatible `create_tool_calling_agent` + `AgentExecutor` flow in `app/ai/llm_client.py`.
39. Upgraded dependency constraints to LangChain 1.x line in `pyproject.toml` and `requirements.txt`.
40. Re-aligned `app/ai/llm_client.py` to docs-style `create_agent(...)` usage for tool-enabled flows.
41. Enhanced `generate_and_save_workout_plan` tool to build plans from live MuscleWiki exercise lookups per training day, with typed Pydantic plan output and fallback behavior.
42. Renamed exercise lookup tool to `lookup_musclewiki_exercises`, propagated explicit limit support through `ExerciseService`, and reinforced chat tool policy to use MuscleWiki tool first for exercise/workout requests.
43. Added backend tool-usage logging hooks in `app/ai/agent_tools.py` and streamed tool events through chat SSE.
44. Updated frontend chat UI to display tool events and workout panel to render exercise video links when available.
45. Extended workout exercise schema with optional `video_url` and ensured live-data plan generation persists it.
46. Improved chat message formatting and switched workout video links to authenticated backend proxy endpoint (`/chat/musclewiki/video`).
47. Restyled tool log messages in green for clear visibility of which tool was used.
48. Refactored `app/ai/agent_tools.py` to use LangChain `@tool(...)` decorators with custom names and Pydantic args schemas instead of `StructuredTool.from_function`.
49. Refactored tool factory into Builder pattern via `AgentToolsBuilder` with fluent setup methods and `.build()` output, while keeping `build_agent_tools(...)` as a compatibility wrapper.
50. Added `delete_latest_workout_plan` capability across repository/db tools and registered `@tool("delete_latest_workout_plan")` in `AgentToolsBuilder`.
51. Removed nested functions from `AgentToolsBuilder.build()` by moving tool actions into dedicated class methods and keeping `build()` as registration-only orchestration.
52. Added dark-mode friendly Tailwind UI with persisted theme toggle (`light`/`dark`) and dark-safe chat/workout rendering styles.
53. Added streaming usage telemetry: backend now extracts LLM token usage metadata, emits SSE `usage` events, and frontend displays cumulative estimated session cost in USD.
54. Increased large-screen UI scale (wider max width, larger titles, taller content panes) for better fullscreen usage.
55. Added chat history preload by user ID via new backend endpoint `GET /chat/history` and frontend `Load Chats` control with auto-load on user change.
56. Fixed video handling for non-MuscleWiki links by allowing YouTube passthrough in `/chat/musclewiki/video` and rendering YouTube videos as iframe embeds in the frontend.
57. Added persisted usage tracking table (`chat_usage`) and backend `GET /chat/usage/summary` endpoint so UI cost reflects all chats in the system instead of only the current stream session.
58. Added `modify_user_workout_plan` AI tool with typed args to swap exercises in the latest saved plan, including optional MuscleWiki-based replacement auto-pick.
59. Improved assistant text formatting in chat UI (clean paragraphs/lists/bold/code rendering) and added robust YouTube embed support including Shorts URLs.
60. Reduced YouTube video usage in workout data by filtering YouTube URLs from MuscleWiki adapter outputs and fallback seed data.
61. Hardened workout modification flow with fuzzy matching for day/exercise names, inferred day/muscle context, and fallback replacement selection when requested exercise is not found.
62. Replaced MuscleWiki integration with YouTube Shorts adapter (`app/tools/youtube_shorts_tool.py`) and switched exercise sourcing to YouTube Data API search.
63. Removed MuscleWiki proxy route/config references, updated tool names to `lookup_youtube_shorts_exercises`, and refreshed `.env.example`, `.env`, and README documentation for YouTube API setup.
64. Fixed startup config validation failure by setting Pydantic settings `extra="ignore"`, allowing non-app env keys like `UV_VENV_CLEAR` in `.env`.
65. Updated `YouTubeShortsAdapter` to support name-first lookup (`get_exercises_by_names`) so AI can choose exercise names first and fetch matching Shorts videos by name.
66. Updated `lookup_youtube_shorts_exercises` agent tool to accept `exercise_names` directly (with validation), while keeping `muscle_group` as fallback mode.
67. Simplified agent flow: plan generation now loops each chosen exercise name to fetch/save video URLs, and workout update now follows strict old-name + day + new-name with automatic new-video fetch.
68. Added automatic frontend data refresh after each AI response completion (refresh usage summary + latest workout plan without manual reload).
69. Fixed repeated exercise generation by replacing generic fallback names with muscle-specific name pools and per-day rotation before Shorts video enrichment.
70. Optimized YouTube Shorts lookup with per-name caching and quota cooldown handling to prevent repeated 403 quotaExceeded calls and reduce API usage.

## Pending

1. Install dependencies with uv and run the backend.
2. Validate all endpoints with quick smoke tests.
3. Add real external exercise API integration.
4. Add Gemini vision integration for image analysis.
5. Add Alembic migrations for production DB workflows.

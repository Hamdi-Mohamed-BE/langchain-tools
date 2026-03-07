# AI Gym Coach Chatbot

FastAPI + LangChain + Gemini scaffold for an AI gym coaching chatbot.

This project currently provides:
- auth endpoints (register/login)
- chat endpoints (normal + streaming SSE)
- workout plan generation and persistence
- YouTube Shorts exercise sourcing (API + fallback seed)
- temporary web UI for chat and workout view

## Architecture

Runtime flow:

1. Browser sends requests to FastAPI.
2. Routers call service layer.
3. Services use repositories/tools.
4. Chat service calls LangChain Gemini client.
5. SQLAlchemy stores users/chat/workouts.

Main code entrypoints:
- App bootstrap: `app/main.py`
- Settings/env: `app/core/config.py`
- DB engine/session: `app/core/database.py`
- Gemini client: `app/ai/llm_client.py`
- Chat orchestration: `app/services/chat_service.py`

## Project Structure

```text
app/
	main.py
	core/
		config.py
		database.py
	routers/
		auth_router.py
		chat_router.py
		workout_router.py
	services/
		auth_service.py
		chat_service.py
		workout_service.py
		exercise_service.py
		image_service.py
	repositories/
		user_repo.py
		chat_repo.py
		workout_repo.py
	tools/
		workout_generator.py
		youtube_shorts_tool.py
		db_tools.py
	schemas/
		auth.py
		chat.py
		workout.py
		exercise.py
	models/
		user.py
		chat_message.py
		workout_plan.py
		exercise.py
static/
	index.html
	styles.css
	app.js
run_server.sh
setup_server.sh
pyproject.toml
.env.example
IMPLEMENTATION_PROGRESS.md
```

## Prerequisites

- Python 3.11+
- `uv` package manager

You can let the script install prerequisites automatically (see quick start below).

## Quick Start

First-time setup (installs Python/uv if needed, creates venv, syncs deps, then runs server):

```bash
bash setup_server.sh
```

What `setup_server.sh` does:
1. Installs Python if missing.
2. Installs `uv` if missing.
3. Creates `.env` from `.env.example` (if `.env` does not exist).
4. Runs `uv venv`, `uv sync`, and starts the server.

Daily run (no install, no re-sync):

```bash
bash run_server.sh
```

What `run_server.sh` does:
1. Verifies `uv` exists.
2. Verifies `.venv` exists.
3. Starts the FastAPI server only.

## Manual Setup (uv)

```bash
uv venv
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:
- API docs: `http://127.0.0.1:8000/docs`
- Temp UI: `http://127.0.0.1:8000/static/index.html`
- Root health-ish endpoint: `http://127.0.0.1:8000/`

## Environment Variables

Copy `.env.example` to `.env` and set values.

Required:

```dotenv
GOOGLE_API_KEY=
```

Required for live exercise video sourcing (otherwise local fallback seed is used):

```dotenv
YOUTUBE_API_KEY=
```

Model selection:

```dotenv
GEMINI_MODEL=gemini-2.5-flash
```

Backward-compatible fallback (legacy typo key also supported):

```dotenv
GEMENI_MODEL=
```

Other useful settings:

```dotenv
DATABASE_URL=sqlite:///./ai_gym.db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=ANYTHING_RANDOM_AND_SECRET
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
YOUTUBE_API_KEY=
YOUTUBE_API_BASE_URL=https://www.googleapis.com/youtube/v3
YOUTUBE_REGION_CODE=US
```

Env parsing code:
- `app/core/config.py`

## LangChain Documentation (Project-Specific)

This section explains exactly how LangChain is used in this codebase.

### LangChain Components Used

- Chat model wrapper: `ChatGoogleGenerativeAI`
- Message primitives: `SystemMessage`, `HumanMessage`
- Async invocation patterns: `.ainvoke(...)` and `.astream(...)`

Code reference:
- `app/ai/llm_client.py`

### How Request -> LangChain -> Response Works

1. Router receives request in `app/routers/chat_router.py`.
2. Router calls `ChatService` in `app/services/chat_service.py`.
3. `ChatService` builds context and calls `LLMClient`.
4. `LLMClient` builds LangChain messages (`SystemMessage`, `HumanMessage`).
5. LangChain calls Gemini and returns text.
6. Service stores assistant response in DB.

### Non-Streaming LangChain Call

Implemented in `LLMClient.generate_response` (`app/ai/llm_client.py`):

```python
messages = [
		SystemMessage(content="..."),
		HumanMessage(content=f"Context: {context}\n\nUser: {user_message}"),
]
response = await self.llm.ainvoke(messages)
return str(response.content)
```

### Streaming LangChain Call

Implemented in `LLMClient.stream_response` (`app/ai/llm_client.py`):

```python
async for chunk in self.llm.astream(messages):
		text = chunk.content if isinstance(chunk.content, str) else ""
		if text:
				yield text
```

The router converts these chunks to SSE events in `app/routers/chat_router.py`.

### LangChain Model Configuration

Configured in:
- `app/ai/llm_client.py`
- `app/core/config.py`

Current fields used:
- `google_api_key`
- `resolved_gemini_model` (supports `GEMINI_MODEL` and fallback `GEMENI_MODEL`)

## LangChain Tools Documentation

In this project, "tools" are deterministic backend functions/services that the chat layer can call before or alongside LLM generation.

Current tool code lives in:
- `app/tools/workout_generator.py`
- `app/tools/youtube_shorts_tool.py`
- `app/tools/db_tools.py`

### Tool Catalog

`generate_workout_plan`
- Location: `app/tools/workout_generator.py`
- Purpose: Build a typed weekly workout plan (`WorkoutPlanData`) from goal and training days.
- Input: `goal: str`, `days_per_week: int`
- Output: `WorkoutPlanData`
- Used by:
	- `app/services/workout_service.py`
	- `app/services/chat_service.py`

`YouTubeShortsAdapter.get_exercises`
- Location: `app/tools/youtube_shorts_tool.py`
- Purpose: Return typed exercise list (`ExerciseData`) by muscle group.
- Input: `muscle_group: str`
- Output: `list[ExerciseData]`
- API integration: calls YouTube Data API `GET /search` with shorts-focused query and `videoDuration=short`.
- Fallback behavior: if API key is missing or request fails, uses local seed data.
- Used by:
	- `app/services/exercise_service.py`
	- `app/services/chat_service.py`

`save_workout_plan`
- Location: `app/tools/db_tools.py`
- Purpose: Persist a typed workout plan via repository helper.
- Input: SQLAlchemy session, `user_id`, `week_start`, `WorkoutPlanData`
- Output: persisted workout row

### How Tools Are Triggered in Chat

Tool orchestration currently happens in `app/services/chat_service.py`.

Current behavior:
- LangChain agent tools are built in `app/ai/agent_tools.py` and passed to `LLMClient`.
- The model decides tool calls, guided by the tool policy injected by `ChatService`.
- Primary exercise lookup tool is `lookup_youtube_shorts_exercises`.
- Workout edits use `modify_user_workout_plan` to swap exercises without regenerating the whole plan.

### Tooling Extension Guide

To add a new tool:

1. Implement deterministic logic in `app/tools/<new_tool>.py`.
2. Use Pydantic models for input/output where possible.
3. Add service wrapper if needed in `app/services/`.
4. Call it from `ChatService` and append structured output to context.
5. Add endpoint docs and example in this README.

### Tool Safety and Reliability Notes

- Keep tool outputs structured and typed (Pydantic).
- Keep external API calls behind adapter classes.
- Keep LLM focused on reasoning/text generation while tools provide deterministic data.
- Validate boundaries at schema level (`app/schemas/`).

## API Reference (With Examples)

All routes are mounted in `app/main.py`.

### Auth

Route code:
- `app/routers/auth_router.py`

Register:

```bash
curl -X POST "http://127.0.0.1:8000/auth/register" \
	-H "Content-Type: application/json" \
	-d '{"email":"user@example.com","password":"strongpass123"}'
```

Login:

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
	-H "Content-Type: application/json" \
	-d '{"email":"user@example.com","password":"strongpass123"}'
```

### Chat (Non-Streaming)

Route code:
- `app/routers/chat_router.py`

```bash
curl -X POST "http://127.0.0.1:8000/chat/message" \
	-H "Content-Type: application/json" \
	-d '{"user_id":1,"message":"Build me a 4-day hypertrophy plan"}'
```

### Chat (Streaming SSE)

SSE route:
- `GET /chat/stream`
- implementation: `app/routers/chat_router.py`

Browser example:

```javascript
const source = new EventSource(
	"/chat/stream?user_id=1&message=" + encodeURIComponent("Give me a push day workout")
);

source.onmessage = (event) => {
	const payload = JSON.parse(event.data);
	console.log(payload);
};
```

SSE payload types currently emitted:
- `{"type":"status","text":"Thinking..."}`
- `{"type":"tool","tool":"...","text":"..."}`
- `{"type":"usage","model":"...","input_tokens":123,"output_tokens":45,"estimated_cost_usd":0.000123}`
- `{"type":"token","text":"..."}`
- `{"type":"done"}`

### Workout Plans

Route code:
- `app/routers/workout_router.py`

Generate and save plan:

```bash
curl -X POST "http://127.0.0.1:8000/workouts/generate" \
	-H "Content-Type: application/json" \
	-d '{"user_id":1,"goal":"muscle gain","days_per_week":4}'
```

Get latest saved plan:

```bash
curl "http://127.0.0.1:8000/workouts/latest?user_id=1"
```

Schema definitions:
- `app/schemas/workout.py`

## Data and Typing

This codebase uses Pydantic classes for API and internal payloads:
- chat schemas: `app/schemas/chat.py`
- workout schemas: `app/schemas/workout.py`
- exercise schema: `app/schemas/exercise.py`

Workout generator returns typed plan objects:
- `app/tools/workout_generator.py`

Exercise tool returns typed exercise objects:
- `app/tools/youtube_shorts_tool.py`

## Frontend (Temporary)

Files:
- `static/index.html`
- `static/styles.css`
- `static/app.js`

What it supports now:
- send streaming chat message
- fetch latest workout plan

## Database

Current default DB:
- SQLite file at `ai_gym.db`

Model definitions:
- `app/models/user.py`
- `app/models/chat_message.py`
- `app/models/workout_plan.py`
- `app/models/exercise.py`

DB table creation currently happens at app startup in:
- `app/main.py`

## Troubleshooting

`uv` command not found after installation:
- open a new terminal and run again
- or add `~/.local/bin` to PATH

Gemini auth/model errors:
- verify `.env` contains valid `GOOGLE_API_KEY`
- ensure model name is valid in `GEMINI_MODEL` or `GEMENI_MODEL`

YouTube exercise lookup not returning videos:
- verify `.env` contains valid `YOUTUBE_API_KEY`
- confirm `YOUTUBE_API_BASE_URL` is `https://www.googleapis.com/youtube/v3`
- if key is missing/invalid, fallback exercise list will be used

No workout found on `/workouts/latest`:
- call `/workouts/generate` first for that `user_id`

## Dev Notes

- Implementation tracking file: `IMPLEMENTATION_PROGRESS.md`
- Technical plan: `ai_gym_chatbot_plan.md`

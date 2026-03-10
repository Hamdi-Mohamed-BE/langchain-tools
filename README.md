# AI Gym Coach Chatbot

An AI-powered gym coaching chatbot that generates personalized weekly workout plans, sources exercise demo videos from YouTube Shorts, and provides real-time conversational coaching — all driven by Google Gemini via LangChain tool-calling agents.

## App Preview

<video src="videos/ai_gym.mp4" width="100%" controls></video>

> If the video doesn't render, [click here to watch](videos/ai_gym.mp4)
---

## Features

- **AI Workout Generation** — Gemini builds fully personalized multi-day training plans based on user goals (no hardcoded exercise databases)
- **YouTube Shorts Exercise Videos** — Each exercise is automatically enriched with a short-form demo video via YouTube Data API
- **Real-Time Streaming Chat** — Token-by-token responses over SSE and WebSocket with tool event visibility
- **Plan Modification** — Ask the AI to swap exercises, change days, or regenerate parts of your plan conversationally
- **Usage Tracking** — Token consumption and estimated cost per chat session
- **Chat History** — Persistent message history with preload on reconnect
- **Dark Mode** — Tailwind-based web UI with persisted light/dark theme toggle
- **Mobile App** — Expo + React Native client with WebSocket chat, auth, and embedded YouTube Shorts player
- **Auth System** — Email/password registration and JWT-based login

---

## Architecture

```
┌──────────────────┐     ┌──────────────────┐
│  Web UI (HTML/JS)│     │ Mobile (Expo/RN)  │
│  static/         │     │ mobile/           │
└────────┬─────────┘     └────────┬──────────┘
         │  HTTP / SSE            │  WebSocket
         └──────────┬─────────────┘
                    ▼
          ┌─────────────────┐
          │  FastAPI Server  │
          │  app/main.py     │
          └────────┬─────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
 Routers       Services      AI Layer
 /auth         auth_service   llm_client.py
 /chat         chat_service   agent_tools.py
 /workouts     workout_svc    context_manager.py
               exercise_svc
               image_svc
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
 Repositories    Tools         External APIs
 user_repo     workout_gen    Google Gemini
 chat_repo     youtube_shorts YouTube Data API
 workout_repo  db_tools
                   │
                   ▼
              SQLAlchemy
            (SQLite / PostgreSQL)
```

### Request Flow

1. Client sends a message (HTTP, SSE, or WebSocket).
2. Router delegates to `ChatService`.
3. `ChatService` builds optimized context (trimmed history + current workout state + tool policy).
4. `LLMClient` invokes Gemini with LangChain agent tools bound.
5. Gemini decides which tools to call (workout generation, exercise lookup, plan modification, etc.).
6. Tool results feed back into the agent loop until a final text response is produced.
7. Response tokens stream to the client; usage metadata and assistant reply are persisted.

---

## Project Structure

```text
├── app/
│   ├── main.py                  # FastAPI app, CORS, router mounting, DB init
│   ├── ai/
│   │   ├── agent_tools.py       # LangChain @tool definitions (AgentToolsBuilder)
│   │   ├── context_manager.py   # Conversation history trimming
│   │   └── llm_client.py        # Gemini chat model wrapper
│   ├── core/
│   │   ├── config.py            # Pydantic Settings (env parsing)
│   │   └── database.py          # SQLAlchemy engine & session
│   ├── models/
│   │   ├── user.py              # User table
│   │   ├── chat_message.py      # Chat history table
│   │   ├── chat_usage.py        # Token usage tracking table
│   │   ├── workout_plan.py      # Workout plan table
│   │   └── exercise.py          # Exercise table
│   ├── repositories/
│   │   ├── user_repo.py         # User CRUD
│   │   ├── chat_repo.py         # Message persistence
│   │   └── workout_repo.py      # Workout plan CRUD
│   ├── routers/
│   │   ├── auth_router.py       # POST /auth/register, /auth/login
│   │   ├── chat_router.py       # POST /chat/message, GET /chat/stream, WS /chat/ws, GET /chat/history, GET /chat/usage/summary
│   │   └── workout_router.py    # POST /workouts/generate, GET /workouts/latest
│   ├── schemas/
│   │   ├── auth.py              # Auth request/response models
│   │   ├── chat.py              # Chat message schemas
│   │   ├── workout.py           # Workout plan schemas
│   │   └── exercise.py          # Exercise data schemas
│   ├── services/
│   │   ├── auth_service.py      # JWT + password hashing
│   │   ├── chat_service.py      # Chat orchestration, tool policy, sanitization
│   │   ├── workout_service.py   # Workout generation orchestration
│   │   ├── exercise_service.py  # Exercise lookup service
│   │   └── image_service.py     # Image analysis (placeholder)
│   └── tools/
│       ├── workout_generator.py # Deterministic plan builder
│       ├── youtube_shorts_tool.py # YouTube Shorts exercise adapter
│       └── db_tools.py          # DB persistence helpers
├── static/
│   ├── index.html               # Web UI (dark mode, Tailwind)
│   ├── styles.css
│   └── app.js
├── mobile/
│   ├── App.tsx                  # Expo/RN entry (auth + chat + workout views)
│   ├── src/
│   │   ├── components/          # MessageBubble, YouTubeShort
│   │   ├── config/              # API base URL config
│   │   ├── services/            # authApi, chatSocket
│   │   ├── types/               # TypeScript types
│   │   └── utils/               # YouTube URL helpers
│   ├── package.json
│   └── app.json
├── videos/                      # App preview videos (add here)
├── setup_server.sh              # One-time server bootstrap
├── run_server.sh                # Daily server start
├── setup_mobile.bat             # One-time mobile bootstrap (Windows)
├── run_mobile.bat               # Daily mobile start (Windows)
├── pyproject.toml               # Python dependencies (uv)
└── .env.example                 # Environment variable template
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI, SQLAlchemy, Pydantic, Uvicorn |
| **AI/LLM** | Google Gemini (via `langchain-google-genai`), LangChain tool-calling agents |
| **Database** | SQLite (default) / PostgreSQL |
| **Web Frontend** | HTML, Tailwind CSS, Vanilla JS, SSE |
| **Mobile** | Expo SDK 54, React Native, TypeScript, WebSocket |
| **Package Mgmt** | `uv` (Python), `yarn` (mobile) |
| **External APIs** | YouTube Data API v3 (Shorts exercise videos) |

---

## Prerequisites

### Backend
- Python 3.11+
- `uv` package manager (auto-installed by setup script)

### Mobile
- Node.js 20.19+
- Yarn (enabled via Corepack)
- Expo Go app on your phone (or Android/iOS emulator)

---

## Quick Start

### Backend Server

**First-time setup** (installs Python/uv if needed, creates venv, syncs deps, bootstraps `.env`):

```bash
bash setup_server.sh
```

**Daily run** (no reinstall, no re-sync):

```bash
bash run_server.sh
```

The server starts on `http://0.0.0.0:8000` with `--reload` enabled.

**Manual setup** (if you prefer):

```bash
uv venv
uv sync
cp .env.example .env   # then edit .env with your keys
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Access points:**

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000/docs` | Swagger API docs |
| `http://127.0.0.1:8000/static/index.html` | Web UI |
| `http://127.0.0.1:8000/` | Health check |

### Mobile App

**First-time setup** (Windows — installs Node.js/Yarn if needed, syncs deps):

```bat
setup_mobile.bat
```

**Daily run** (Windows):

```bat
run_mobile.bat
```

**Manual setup:**

```bash
cd mobile
yarn install
yarn start
```

Then press `a` for Android, `i` for iOS, or scan the QR code with Expo Go.

> **Tip:** For physical devices, set `EXPO_PUBLIC_API_BASE_URL` in `mobile/.env` to your machine's LAN IP (e.g., `http://192.168.1.100:8000`). For Android emulator use `http://10.0.2.2:8000`.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in values.

### Required

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google AI API key for Gemini |

### Recommended

| Variable | Description |
|----------|-------------|
| `YOUTUBE_API_KEY` | YouTube Data API key for exercise video lookup (falls back to seed data if missing) |
| `JWT_SECRET_KEY` | Secret for signing JWT tokens |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `DATABASE_URL` | `sqlite:///./ai_gym.db` | SQLAlchemy connection string |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_MINUTES` | `1440` | Token expiry (24h) |
| `YOUTUBE_API_BASE_URL` | `https://www.googleapis.com/youtube/v3` | YouTube API base |
| `YOUTUBE_REGION_CODE` | `US` | YouTube search region |
| `CORS_ALLOW_ORIGINS` | `*` | Allowed CORS origins |

### Mobile (`mobile/.env`)

| Variable | Description |
|----------|-------------|
| `EXPO_PUBLIC_API_BASE_URL` | Backend URL (e.g., `http://10.0.2.2:8000` for Android emulator) |

---

## AI Agent Tools

The LLM has access to the following tools via LangChain's tool-calling agent flow. The model autonomously decides which tools to invoke based on the user's message.

| Tool | Description |
|------|-------------|
| `get_workout_state` | Fetches the user's latest workout plan and progress summary |
| `generate_and_save_workout_plan` | Generates a personalized multi-day plan based on goals, enriches exercises with YouTube Shorts videos, and saves to DB |
| `lookup_youtube_shorts_exercises` | Searches YouTube Shorts for exercise demo videos by muscle group or exercise name |
| `modify_user_workout_plan` | Swaps a specific exercise in the plan with a new one (auto-fetches replacement video) |
| `update_user_workout_progress` | Marks exercises as completed for a day with optional notes |
| `refresh_exercise_videos` | Re-fetches YouTube video URLs for all exercises in the current plan |
| `delete_latest_workout_plan` | Removes the most recent workout plan |
| `delete_all_workout_plans` | Clears all workout plans for the user |

Tool source: `app/ai/agent_tools.py` (uses `AgentToolsBuilder` pattern with `@tool` decorators)

### Tool Flow in Chat

1. `ChatService` injects a **tool policy** into the system prompt, guiding Gemini on when to use each tool.
2. Gemini analyzes the user message and calls tools as needed (e.g., generating a plan, looking up exercises).
3. Tool results feed back into the agent loop until Gemini produces a final text response.
4. Tool events are streamed to the client in real time (`{"type":"tool","tool":"...","text":"..."}`).

### Adding a New Tool

1. Implement logic in `app/tools/<new_tool>.py`.
2. Use Pydantic models for typed input/output.
3. Add a service wrapper in `app/services/` if needed.
4. Register the tool in `AgentToolsBuilder` (`app/ai/agent_tools.py`).
5. Update tool policy in `ChatService` if the LLM needs guidance on when to use it.

---

## API Reference

All routes are mounted in `app/main.py`.

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create a new user account |
| POST | `/auth/login` | Login and receive JWT token |

```bash
# Register
curl -X POST "http://127.0.0.1:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"strongpass123"}'

# Login
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"strongpass123"}'
```

Response:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user_id": 1
}
```

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat/message` | Send a message, get a single response |
| GET | `/chat/stream` | SSE streaming chat (token-by-token) |
| WS | `/chat/ws` | WebSocket streaming chat |
| GET | `/chat/history` | Load previous messages for a user |
| GET | `/chat/usage/summary` | Token usage and cost summary |

**SSE streaming example:**

```javascript
const source = new EventSource(
  "/chat/stream?user_id=1&message=" + encodeURIComponent("Build me a 4-day hypertrophy plan")
);

source.onmessage = (event) => {
  const payload = JSON.parse(event.data);
  // payload.type: "status" | "tool" | "token" | "usage" | "done"
  console.log(payload);
};
```

**WebSocket example:**

```javascript
const ws = new WebSocket("ws://127.0.0.1:8000/chat/ws");
ws.onopen = () => {
  ws.send(JSON.stringify({ user_id: 1, message: "Give me a push day workout" }));
};
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // data.type: "status" | "tool" | "token" | "usage" | "done" | "error"
};
```

**SSE/WebSocket event types:**

| Type | Description |
|------|-------------|
| `status` | Status update (e.g., "Thinking...") |
| `tool` | Tool invocation event with tool name and result text |
| `token` | Single text token from the LLM response |
| `usage` | Token counts, model name, and estimated cost in USD |
| `done` | Stream complete |
| `error` | Error message (WebSocket only) |

### Workout Plans

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/workouts/generate` | Generate and save a workout plan |
| GET | `/workouts/latest` | Get the latest saved plan for a user |

```bash
# Generate plan
curl -X POST "http://127.0.0.1:8000/workouts/generate" \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"goal":"muscle gain","days_per_week":4}'

# Get latest plan
curl "http://127.0.0.1:8000/workouts/latest?user_id=1"
```

---

## Database

- **Default:** SQLite (`ai_gym.db` in project root)
- **Production:** Set `DATABASE_URL` to a PostgreSQL connection string
- **Table creation:** Automatic on app startup via `Base.metadata.create_all()`

### Tables

| Table | Model | Description |
|-------|-------|-------------|
| `users` | `app/models/user.py` | User accounts (email, password hash) |
| `chat_messages` | `app/models/chat_message.py` | Chat history per user |
| `chat_usage` | `app/models/chat_usage.py` | Token usage and cost tracking per request |
| `workout_plans` | `app/models/workout_plan.py` | Saved workout plans (JSON) |
| `exercises` | `app/models/exercise.py` | Exercise metadata |

---

## Web Frontend

A temporary Tailwind-based UI served from `static/`.

- **Chat interface** with real-time SSE streaming and tool event display
- **Workout panel** showing the latest plan with exercise video links
- **Dark mode** toggle with persistent theme preference
- **Usage display** showing cumulative token count and estimated cost
- **Chat history** preload by user ID

---

## Mobile App

A React Native app built with Expo SDK 54 and TypeScript.

### Features

- Email/password signup and login with session persistence (AsyncStorage)
- Real-time WebSocket chat with token-by-token streaming
- Tool event rendering in chat
- Usage stats display
- Workout plan viewer with embedded YouTube Shorts player
- Configurable backend URL for physical device testing

### Mobile Tech

| Package | Purpose |
|---------|---------|
| `expo` (SDK 54) | React Native framework |
| `react-native-youtube-iframe` | Embedded YouTube player |
| `@react-native-async-storage/async-storage` | Auth session persistence |
| `react-native-webview` | WebView for video rendering |

See `mobile/MOBILE_APP.md` for detailed mobile documentation.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `uv` command not found | Open a new terminal, or add `~/.local/bin` to PATH |
| Gemini auth/model errors | Verify `GOOGLE_API_KEY` in `.env`; ensure `GEMINI_MODEL` is a valid model name |
| YouTube videos not loading | Verify `YOUTUBE_API_KEY` in `.env`; if missing, fallback seed data is used |
| No workout on `/workouts/latest` | Generate a plan first via chat or `/workouts/generate` |
| Mobile can't connect to backend | Set `EXPO_PUBLIC_API_BASE_URL` to your LAN IP; ensure backend runs on `0.0.0.0` |
| WSL + Android emulator issues | Use Expo Go QR code on a physical device, or set `ANDROID_HOME` in your shell |
| `npm install` deprecation warnings | These are transitive dependencies from React Native / Expo toolchain — safe to ignore |

---

## Dev Notes

- Implementation log: `IMPLEMENTATION_PROGRESS.md`
- Technical plan: `ai_gym_chatbot_plan.md`
- Mobile docs: `mobile/MOBILE_APP.md`

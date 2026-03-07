
# AI Gym Coach Chatbot – Technical Implementation Plan

## 1. Objective
Build an AI-powered chatbot that generates weekly gym training sessions and interacts with users via a chat interface.  
The system will:
- Generate structured weekly workout plans
- Retrieve exercises from external APIs (e.g., YouTube Shorts API)
- Persist user workout data
- Analyze uploaded images
- Stream AI responses with reasoning steps
- Optimize token usage and context management

Backend: **FastAPI**  
Frontend: **Simple HTML/CSS/JS** (temporary UI)  
LLM: Gemini via LangChain (`langchain-google-genai`)
Package Manager: **uv**

---

# 2. System Architecture

```
Browser (HTML/JS)
      │
      ▼
FastAPI Backend
      │
      ├── Auth Service
      ├── Chat Service
      ├── Workout Service
      ├── Exercise Service
      ├── Image Analysis Service
      │
      ▼
Database (PostgreSQL)
```

LLM interaction:

```
User Message
     │
     ▼
Chat Orchestrator
     │
     ├─ tool: get_user_profile
     ├─ tool: generate_workout_plan
     ├─ tool: get_exercises
     ├─ tool: save_workout_plan
     └─ tool: update_workout_progress
```

---

# 3. Tech Stack

## Backend
- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis (context + caching)
- LangChain

## AI
- Gemini model (tool calling + vision) via `langchain-google-genai`
- Streaming responses

## Frontend
- HTML
- CSS
- Vanilla JS
- SSE or WebSockets

---

# 4. Database Schema

## Users

```
users
-----
id
email
password_hash
created_at
```

## Workout Plans

```
workout_plans
-------------
id
user_id
week_start
plan_json
created_at
```

## Exercises

```
exercises
---------
id
name
muscle_group
equipment
video_url
```

## Chat Messages

```
chat_messages
-------------
id
user_id
role
content
created_at
```

---

# 5. Design Patterns

## Service Layer Pattern

Separates business logic from API layer.

```
routers/
services/
repositories/
models/
schemas/
```

Example:

```
ChatRouter → ChatService → LLMClient
```

## Repository Pattern

Handles database operations.

Example:

```
UserRepository
WorkoutRepository
ExerciseRepository
```

## Tool Adapter Pattern

Wraps external APIs as callable tools.

Example:

```
YouTubeShortsAdapter
```

---

# 6. Backend Structure

```
app/
 ├── main.py
 ├── routers/
 │     ├── auth_router.py
 │     ├── chat_router.py
 │     └── workout_router.py
 │
 ├── services/
 │     ├── chat_service.py
 │     ├── workout_service.py
 │     ├── exercise_service.py
 │     └── image_service.py
 │
 ├── repositories/
 │     ├── user_repo.py
 │     ├── workout_repo.py
 │     └── chat_repo.py
 │
 ├── tools/
 │     ├── workout_generator.py
 │     ├── youtube_shorts_tool.py
 │     └── db_tools.py
 │
 ├── ai/
 │     ├── llm_client.py
 │     └── context_manager.py
```

---

# 7. Chat System

The chat service orchestrates tool usage.

Flow:

```
User message
      │
      ▼
ChatService
      │
      ▼
LLM Agent
      │
      ├─ tool: get_exercises
      ├─ tool: generate_plan
      ├─ tool: save_plan
      └─ tool: update_progress
```

---

# 8. Streaming Responses

Use **Server Sent Events (SSE)**.

FastAPI example:

```
/chat/stream
```

The server streams tokens as they are generated.

Output example:

```
Thinking...
Selecting exercises...
Generating program...
```

Implementation note:
- FastAPI endpoint streams SSE chunks from LangChain async token stream (`ChatGoogleGenerativeAI.astream`).

---

# 9. Image Understanding

Users can upload images in chat.

Examples:
- gym equipment
- progress photos
- exercise form

Flow:

```
Image upload
     │
     ▼
Vision model
     │
     ▼
Result injected into chat context
```

Example response:

```
The image appears to show a barbell bench press setup.
You can perform these exercises.
```

---

# 10. Token Optimization Strategy

## Context Window Control

Only include:

- last 5 messages
- summary of older messages

## Conversation Summaries

Use background summarization:

```
old_messages → summary
```

Store summary in Redis.

## Tool-first Strategy

Avoid asking LLM for data when a tool can provide it.

Example:

```
exercise database → tool
```

---

# 11. Frontend Layout

Simple split screen.

```
+--------------------+--------------------+
| Chat Panel         | Workout Viewer     |
|                    |                    |
| user messages      | Day 1 exercises    |
| AI responses       | Day 2 exercises    |
| image uploads      | videos             |
+--------------------+--------------------+
```

---

# 12. Frontend Structure

```
/static
   index.html
   styles.css
   app.js
```

## Chat panel
- message input
- image upload
- streaming response

## Workout viewer
- weekly plan
- exercise videos
- progress tracking

---

# 13. Authentication

Simple email/password login.

Endpoints:

```
POST /auth/register
POST /auth/login
```

JWT token returned.

Frontend stores token.

---

# 14. MVP Implementation Steps

### Phase 1
- FastAPI project
- auth system
- database models
- uv-based dependency setup (`pyproject.toml`)

### Phase 2
- chat API
- streaming responses
- LangChain + Gemini client

### Phase 3
- workout generator tool
- exercise API integration

### Phase 4
- image understanding

### Phase 5
- frontend UI

---

# 15. Future Improvements

- personalized progression
- adaptive programs
- injury detection
- form analysis
- wearable integrations

---

# Conclusion

This architecture keeps the AI agent lightweight while moving deterministic logic to backend services.  
It ensures scalability, lower token costs, and maintainable code structure.

---

# 16. Environment Variables (LangChain + Gemini)

Required:

```dotenv
GOOGLE_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

Backward compatibility:

```dotenv
# Supported as a fallback because some setups use this typo key.
GEMENI_MODEL=
```

Additional backend keys:

```dotenv
DATABASE_URL=sqlite:///./ai_gym.db
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=change-me
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

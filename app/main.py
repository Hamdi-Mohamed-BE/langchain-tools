from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, engine
from app.routers.auth_router import router as auth_router
from app.routers.chat_router import router as chat_router
from app.routers.workout_router import router as workout_router


app = FastAPI(title=settings.app_name, debug=settings.debug)

Base.metadata.create_all(bind=engine)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(workout_router, prefix="/workouts", tags=["workouts"])

app.mount("/static", StaticFiles(directory="static", html=True), name="static")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "AI Gym Coach Chatbot is running", "ui": "/static/index.html"}

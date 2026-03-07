from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.services.auth_service import AuthService


router = APIRouter()


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    service = AuthService(db)
    try:
        user_id, token = service.register(payload.email, payload.password)
        return AuthResponse(access_token=token, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    service = AuthService(db)
    try:
        user_id, token = service.login(payload.email, payload.password)
        return AuthResponse(access_token=token, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

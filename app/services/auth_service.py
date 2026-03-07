from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.user_repo import UserRepository


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, db: Session) -> None:
        self.repo = UserRepository(db)

    def register(self, email: str, password: str) -> tuple[int, str]:
        existing = self.repo.get_by_email(email)
        if existing:
            raise ValueError("Email already exists")

        password_hash = pwd_context.hash(password)
        user = self.repo.create(email=email, password_hash=password_hash)
        token = self.create_access_token({"sub": str(user.id), "email": user.email})
        return user.id, token

    def login(self, email: str, password: str) -> tuple[int, str]:
        user = self.repo.get_by_email(email)
        if not user or not pwd_context.verify(password, user.password_hash):
            raise ValueError("Invalid credentials")

        token = self.create_access_token({"sub": str(user.id), "email": user.email})
        return user.id, token

    def create_access_token(self, data: dict) -> str:
        to_encode = data.copy()
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def decode_token(token: str) -> dict | None:
        try:
            return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        except JWTError:
            return None

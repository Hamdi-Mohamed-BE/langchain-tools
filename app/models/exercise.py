from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    muscle_group: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    equipment: Mapped[str] = mapped_column(String(100), nullable=True)
    video_url: Mapped[str] = mapped_column(String(500), nullable=True)

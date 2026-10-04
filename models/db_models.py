from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from core.database import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC default (``datetime.utcnow`` is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(320), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    interviews = relationship(
        "InterviewSessionModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class InterviewSessionModel(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True, nullable=False)
    # Ownership is required: an interview with no owner cannot be access-checked.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # No resume_name: it was the uploaded filename and was displayed nowhere.
    # Kept on the Redis session for the report header only.
    job_role = Column(String(128))
    # The band the score was earned under. Without it a stored score is not
    # comparable across sessions — a 72 on "easy" and a 72 on "hard" are not the
    # same result, and the live session that knows which is which expires after
    # six hours.
    difficulty = Column(String(16), default="medium", nullable=False)
    status = Column(String(32), default="in_progress", nullable=False)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # No report_data: the full report lives in Redis for the session's 6-hour
    # TTL and is not persisted. An interview always finishes well inside that
    # window, so the report is served from the live session; once the TTL
    # lapses, the score and status below are what remains of it.
    user = relationship("User", back_populates="interviews")

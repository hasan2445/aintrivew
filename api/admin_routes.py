from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core import auth
from core.database import get_db
from models import db_models

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def get_all_users(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_admin: db_models.User = Depends(auth.get_current_admin),
):
    users = (
        db.query(db_models.User)
        .order_by(db_models.User.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "is_admin": u.is_admin,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.get("/interviews")
def get_all_interviews(
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_admin: db_models.User = Depends(auth.get_current_admin),
):
    # Single joined query; the previous version issued one user lookup per
    # interview row (N+1).
    rows = (
        db.query(db_models.InterviewSessionModel, db_models.User.username)
        .outerjoin(db_models.User, db_models.User.id == db_models.InterviewSessionModel.user_id)
        .order_by(db_models.InterviewSessionModel.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": interview.id,
            "session_id": interview.session_id,
            "username": username or "Unknown",
            "job_role": interview.job_role,
            "status": interview.status,
            "score": interview.score,
            "created_at": interview.created_at,
        }
        for interview, username in rows
    ]

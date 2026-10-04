import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from core import config
from core.database import get_db
from models import db_models

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

# bcrypt silently truncates (or, in newer releases, rejects) anything past 72
# bytes. Normalise here so hashing and verification agree on the same input.
_BCRYPT_MAX_BYTES = 72


def _prepare_password(password: str) -> bytes:
    if not isinstance(password, str):
        password = str(password)
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            _prepare_password(plain_password),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Malformed stored hash: treat as a failed login rather than a 500.
        logger.warning("Password verification failed due to a malformed stored hash.")
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt()).decode("utf-8")


class TokenIdentity:
    """Who the caller is, taken from the token alone.

    ``get_current_user`` costs one ``users`` row read per request, and at one
    webcam frame every three seconds that was the single largest source of
    database traffic in the app — hundreds of identical primary-key lookups per
    interview, none of which read anything the token could not carry.

    This carries the two fields the hot paths actually use: the id, for rate
    limit keys and ownership comparisons, and the username. It deliberately does
    NOT carry ``is_admin``. Privilege is still read from the database wherever it
    matters, so revoking an admin still takes effect on the next request rather
    than whenever their token happens to expire.
    """

    __slots__ = ("id", "username")

    def __init__(self, user_id: int, username: str):
        self.id = user_id
        self.username = username


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> db_models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(db_models.User).filter(db_models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


def get_token_identity(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> TokenIdentity:
    """Resolve the caller from the token, without touching the database.

    Falls back to a lookup for tokens minted before ``uid`` was a claim, so a
    candidate mid-interview at deploy time is not logged out. Those tokens age
    out within ``ACCESS_TOKEN_EXPIRE_MINUTES``.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
    except JWTError:
        raise credentials_exception

    username = payload.get("sub")
    if not username:
        raise credentials_exception

    uid = payload.get("uid")
    if isinstance(uid, int):
        return TokenIdentity(uid, username)

    user = db.query(db_models.User).filter(db_models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return TokenIdentity(user.id, user.username)


def get_current_admin(
    current_user: db_models.User = Depends(get_current_user),
) -> db_models.User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not enough privileges")
    return current_user

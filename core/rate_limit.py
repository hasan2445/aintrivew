"""Fixed-window rate limiting for the endpoints that cost money or CPU.

There was previously nothing in this codebase between a caller and unlimited
login attempts, YOLO inference or ElevenLabs billing. Every
ML endpoint required a valid token but had no session binding and no ceiling, so
one authenticated account could saturate the box for free.

Counters live in Redis when it is available so they hold across workers, and
fall back to a process-local dict otherwise — the same trade the session store
makes, except here a per-worker counter is merely a weaker limit rather than
lost data, so it does not need to fail the boot.
"""

import logging
import threading
import time
from typing import Dict, Tuple

from fastapi import Depends, HTTPException, Request

from core import auth
from core.settings import settings

logger = logging.getLogger(__name__)

_local_lock = threading.Lock()
_local_counters: Dict[str, Tuple[int, float]] = {}

_redis_client = None
_redis_checked = False


def _get_redis():
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        import redis

        client = redis.StrictRedis.from_url(
            settings.redis_url or "redis://localhost:6379/0",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _redis_client = client
    except Exception as exc:
        logger.warning("Rate limiter falling back to in-process counters: %s", exc)
        _redis_client = None
    return _redis_client


def _hit(key: str, limit: int, window_seconds: int) -> bool:
    """Record one request. Returns True when the caller is over the limit."""
    client = _get_redis()
    bucket = int(time.time() // window_seconds)
    full_key = f"ratelimit:{key}:{bucket}"

    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.incr(full_key)
            pipe.expire(full_key, window_seconds + 1)
            count = pipe.execute()[0]
            return int(count) > limit
        except Exception as exc:
            logger.warning("Rate limiter Redis error, allowing request: %s", exc)
            return False

    now = time.time()
    with _local_lock:
        # Opportunistic sweep so an abandoned process does not grow the dict
        # without bound.
        if len(_local_counters) > 4096:
            for k, (_, expiry) in list(_local_counters.items()):
                if expiry < now:
                    _local_counters.pop(k, None)
        count, expiry = _local_counters.get(full_key, (0, now + window_seconds))
        count += 1
        _local_counters[full_key] = (count, expiry)
    return count > limit


class RateLimiter:
    """FastAPI dependency enforcing ``limit`` requests per ``window_seconds``.

    Authenticated callers are keyed by user id, so one account cannot spread its
    quota across many IPs. Anonymous callers (login, signup) are keyed by client
    IP, which is the only identity available before a token exists.
    """

    def __init__(self, name: str, limit: int, window_seconds: int, per_user: bool = True):
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds
        self.per_user = per_user

    def _identity(self, request: Request, user) -> str:
        if self.per_user and user is not None:
            return f"user:{user.id}"
        client = request.client
        return f"ip:{client.host if client else 'unknown'}"

    def __call__(self, request: Request, user=None):
        key = f"{self.name}:{self._identity(request, user)}"
        if _hit(key, self.limit, self.window_seconds):
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Try again in {self.window_seconds} seconds.",
                headers={"Retry-After": str(self.window_seconds)},
            )


def authenticated_limiter(name: str, limit: int, window_seconds: int):
    """Build a dependency that rate-limits an authenticated endpoint by user id.

    Identity comes from the token rather than a ``users`` row: the limiter needs
    the id and nothing else, and this dependency sits in front of the webcam
    frame endpoint, which fires every three seconds for the length of an
    interview. Reading a row to learn an id the token already carries was the
    largest single source of database traffic in the app.
    """
    limiter = RateLimiter(name, limit, window_seconds, per_user=True)

    def dependency(
        request: Request,
        identity: auth.TokenIdentity = Depends(auth.get_token_identity),
    ) -> auth.TokenIdentity:
        limiter(request, identity)
        return identity

    return dependency


def anonymous_limiter(name: str, limit: int, window_seconds: int):
    """Build a dependency that rate-limits an unauthenticated endpoint by IP."""
    limiter = RateLimiter(name, limit, window_seconds, per_user=False)

    def dependency(request: Request) -> None:
        limiter(request, None)

    return dependency


# One frame every 3s per candidate is 20/min; 40/min leaves headroom for a
# retry storm without allowing a scripted flood.
frame_rate_limit = authenticated_limiter("frame", limit=40, window_seconds=60)
# ElevenLabs is billed per character.
tts_rate_limit = authenticated_limiter("tts", limit=20, window_seconds=60)
# Each upload is a multi-second LLM generation call.
upload_rate_limit = authenticated_limiter("upload", limit=6, window_seconds=300)
# Two sequential LLM calls per submission.
answer_rate_limit = authenticated_limiter("answer", limit=40, window_seconds=60)
# Credential stuffing: 10 attempts per IP per 5 minutes.
login_rate_limit = anonymous_limiter("login", limit=10, window_seconds=300)
signup_rate_limit = anonymous_limiter("signup", limit=5, window_seconds=3600)

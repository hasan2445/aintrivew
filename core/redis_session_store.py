import logging
from typing import Dict, Optional

import redis
from pydantic import ValidationError

from core.settings import settings
from models.schemas import InterviewSession

logger = logging.getLogger(__name__)


class RedisUnavailableError(RuntimeError):
    """Raised when production is configured but Redis cannot be reached."""


class RedisSessionStore:
    """Thin wrapper around Redis for persisting InterviewSession objects.

    Sessions are serialized to JSON under keys prefixed with
    ``interview_session:`` and expire after ``settings.session_ttl_seconds`` so
    abandoned interviews do not accumulate forever.

    Outside production an unreachable Redis degrades to a process-local dict so
    the repo runs with no Redis installed. In production that fallback is a
    multi-worker data-loss bug wearing a developer-convenience hat — each worker
    would get its own dict and a candidate's answer would land on a worker that
    has never seen their session — so the boot fails instead, matching the
    fail-fast pattern ``core/settings.py`` already applies to the JWT secret.
    """

    def __init__(self, url: Optional[str] = None, ttl_seconds: Optional[int] = None):
        self.prefix = "interview_session:"
        self.proctoring_prefix = "interview_proctoring:"
        self.ttl_seconds = ttl_seconds or settings.session_ttl_seconds
        # Always present so callers never hit AttributeError on the fallback path.
        self._memory_store: Dict[str, str] = {}
        self._memory_proctoring: Dict[str, Dict[str, int]] = {}
        self.client = None
        try:
            client = redis.StrictRedis.from_url(
                url or settings.redis_url or "redis://localhost:6379/0",
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            client.ping()
            self.client = client
        except Exception as exc:
            if settings.is_production:
                raise RedisUnavailableError(
                    "Redis is unreachable and ENVIRONMENT=production. The in-memory "
                    "session fallback is single-worker only and silently loses "
                    "interviews across workers; refusing to start. Set REDIS_URL to a "
                    "reachable instance."
                ) from exc
            logger.warning(
                "Redis connection failed (%s); using in-memory session store. "
                "Sessions will not be shared across workers or survive a restart.",
                exc,
            )

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def _proctoring_key(self, session_id: str) -> str:
        return f"{self.proctoring_prefix}{session_id}"

    def set(self, session_id: str, session: InterviewSession) -> None:
        data = session.model_dump_json()
        if self.client:
            try:
                self.client.set(self._key(session_id), data, ex=self.ttl_seconds)
                return
            except redis.RedisError as exc:
                logger.error("Redis SET failed for %s: %s", session_id, exc)
                raise
        self._memory_store[self._key(session_id)] = data

    def get(self, session_id: str) -> Optional[InterviewSession]:
        if self.client:
            try:
                raw = self.client.get(self._key(session_id))
            except redis.RedisError as exc:
                logger.error("Redis GET failed for %s: %s", session_id, exc)
                return None
        else:
            raw = self._memory_store.get(self._key(session_id))

        if raw is None:
            return None
        try:
            return InterviewSession.model_validate_json(raw)
        except ValidationError as exc:
            # A stored session written by an older schema version should not take
            # the whole request down.
            logger.error("Discarding unreadable session %s: %s", session_id, exc)
            return None

    def delete(self, session_id: str) -> None:
        if self.client:
            try:
                self.client.delete(self._key(session_id), self._proctoring_key(session_id))
                return
            except redis.RedisError as exc:
                logger.error("Redis DELETE failed for %s: %s", session_id, exc)
                return
        self._memory_store.pop(self._key(session_id), None)
        self._memory_proctoring.pop(self._proctoring_key(session_id), None)

    def increment_proctoring(self, session_id: str, fields: Dict[str, int]) -> None:
        """Atomically bump proctoring counters for a session.

        Kept in its own hash rather than on the session blob on purpose: frames
        arrive every 3 seconds while an answer submission is doing a
        read-modify-write of the whole session, and folding counters into that
        blob would make every frame a chance to clobber an answer. HINCRBY is
        atomic and touches nothing else.
        """
        fields = {k: int(v) for k, v in fields.items() if v}
        if not fields:
            return

        key = self._proctoring_key(session_id)
        if self.client:
            try:
                pipe = self.client.pipeline()
                for field, amount in fields.items():
                    pipe.hincrby(key, field, amount)
                pipe.expire(key, self.ttl_seconds)
                pipe.execute()
                return
            except redis.RedisError as exc:
                logger.error("Redis HINCRBY failed for %s: %s", session_id, exc)
                return

        bucket = self._memory_proctoring.setdefault(key, {})
        for field, amount in fields.items():
            bucket[field] = bucket.get(field, 0) + amount

    def set_proctoring(self, session_id: str, fields: Dict[str, int]) -> None:
        """Overwrite specific proctoring fields with absolute values.

        Used for the browser-reported attention counters, which arrive as
        running totals rather than deltas. HINCRBY would double-count them on
        every resend; HSET is idempotent, so a retry or an overlapping report
        settles on the same value instead of inflating it.
        """
        fields = {k: int(v) for k, v in fields.items()}
        if not fields:
            return

        key = self._proctoring_key(session_id)
        if self.client:
            try:
                pipe = self.client.pipeline()
                pipe.hset(key, mapping=fields)
                pipe.expire(key, self.ttl_seconds)
                pipe.execute()
                return
            except redis.RedisError as exc:
                logger.error("Redis HSET failed for %s: %s", session_id, exc)
                return

        bucket = self._memory_proctoring.setdefault(key, {})
        bucket.update(fields)

    def get_proctoring(self, session_id: str) -> Dict[str, int]:
        """Read the proctoring counters, defaulting to zeros."""
        key = self._proctoring_key(session_id)
        if self.client:
            try:
                raw = self.client.hgetall(key) or {}
            except redis.RedisError as exc:
                logger.error("Redis HGETALL failed for %s: %s", session_id, exc)
                return {}
        else:
            raw = self._memory_proctoring.get(key, {})

        out: Dict[str, int] = {}
        for field, value in raw.items():
            try:
                out[str(field)] = int(value)
            except (TypeError, ValueError):
                continue
        return out

    def all(self) -> Dict[str, InterviewSession]:
        sessions: Dict[str, InterviewSession] = {}
        if self.client:
            try:
                iterator = list(self.client.scan_iter(f"{self.prefix}*"))
            except redis.RedisError as exc:
                logger.error("Redis SCAN failed: %s", exc)
                return sessions
        else:
            iterator = [k for k in self._memory_store if k.startswith(self.prefix)]

        for key in iterator:
            sid = key.split(":", 1)[1]
            session = self.get(sid)
            # Skip entries that expired or failed to parse mid-scan rather than
            # returning None values the caller would have to guard against.
            if session is not None:
                sessions[sid] = session
        return sessions

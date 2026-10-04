"""Derived constants. Everything configurable lives in core/settings.py.

Removed here, because nothing read them: OPENAI_API_KEY / OPENAI_MODEL /
OPENAI_TEMPERATURE (this app only ever used langchain-groq),
QUESTIONS_PER_SKILL and its three siblings (from the deleted static question
bank), MAX_SESSION_DURATION_HOURS (superseded by the Redis TTL) and
UPLOAD_FOLDER (resumes are parsed in memory and discarded, so the directory was
created at boot and never written to).
"""

import os

from .settings import settings


# Cap primary questions used in a live session (generation prompt asks for 8-12).
MAX_PRIMARY_QUESTIONS = 12

# Bound on a single submitted answer, to keep LLM prompts (and cost) sane.
MAX_ANSWER_CHARS = 20000
# Bound on resume text forwarded to the LLM.
MAX_RESUME_CHARS = 40000
# Bound on text accepted by the TTS endpoint.
MAX_TTS_CHARS = 5000


MAX_UPLOAD_SIZE_MB = settings.max_upload_size_mb
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx"}


# Wired into ChatGroq's constructor in services/question_generator.py. These
# were defined and never imported, so the client ran on langchain-groq's
# defaults and an unbounded call could pin a threadpool worker.
LLM_MAX_RETRIES = 3
LLM_TIMEOUT_SECONDS = 60


GROQ_MODEL = settings.groq_model
GROQ_MAX_TOKENS = settings.groq_max_tokens

DATABASE_URL = settings.database_url


SECRET_KEY = settings.jwt_secret_key.get_secret_value()
ALGORITHM = settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes

ENVIRONMENT = settings.environment
IS_PRODUCTION = settings.is_production
DEBUG = settings.debug

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

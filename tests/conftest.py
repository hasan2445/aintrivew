"""Test configuration.

The seams this suite pushes through already existed: the LLM lives behind
``InterviewSessionManager.generator``, the store behind ``RedisSessionStore``,
and the heavy CV models behind lazy loaders so importing the app does not drag
in torch. Nothing had ever been pushed through them.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Settings validate at import and require these. Values are throwaway.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GROQ_API_KEY", "test-key-not-used")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("SKIP_MODEL_WARMUP", "1")

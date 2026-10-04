"""Recover a JSON object from a chat model's free-text response.

Three call sites in ``question_generator`` used to carry their own copy of the
same fence-stripping + brace-slicing logic. The brace slice took first ``{`` to
last ``}``, which produces invalid JSON the moment the model emits two objects
or appends a trailing note containing a brace. ``json.JSONDecoder.raw_decode``
parses the first complete object instead and reports where it stopped, so the
common failure modes stop being failures.
"""

import json
from typing import Any, Dict

_DECODER = json.JSONDecoder()


class LLMJSONError(ValueError):
    """Raised when no complete JSON object can be recovered from a response."""


def _strip_code_fences(text: str) -> str:
    """Return the body of a ```/```json fenced block, or the text unchanged."""
    if "```json" in text:
        after = text.split("```json", 1)[1]
        return after.split("```", 1)[0]
    if "```" in text:
        parts = text.split("```")
        # parts[0] is the preamble, parts[1] the first fenced body.
        if len(parts) > 1:
            return parts[1]
    return text


def extract_json_object(raw: Any) -> Dict[str, Any]:
    """Parse the first complete JSON object in ``raw``.

    Tolerates code fences, a chatty preamble ("Here's the JSON:"), a trailing
    remark, and a second object appended after the first.
    """
    if raw is None:
        raise LLMJSONError("Empty model response")

    text = _strip_code_fences(str(raw)).strip()
    if not text:
        raise LLMJSONError("Empty model response")

    start = text.find("{")
    while start != -1:
        try:
            value, _end = _DECODER.raw_decode(text, start)
        except ValueError:
            # Not a valid object at this brace; try the next one. Handles a
            # preamble that itself contains a stray "{".
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)

    raise LLMJSONError("No valid JSON object found in response")

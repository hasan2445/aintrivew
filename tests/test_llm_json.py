"""Parser tests.

Every case here has explicit handling in the production code, which is a good
sign each one was hit by hand at some point and then left unpinned.
"""

import pytest

from services.llm_json import LLMJSONError, extract_json_object


def test_plain_object():
    assert extract_json_object('{"rating": "good"}') == {"rating": "good"}


def test_json_code_fence():
    raw = 'Sure!\n```json\n{"rating": "fair", "score": 6}\n```\n'
    assert extract_json_object(raw)["rating"] == "fair"


def test_bare_code_fence():
    assert extract_json_object('```\n{"a": 1}\n```')["a"] == 1


def test_chatty_preamble_and_trailing_remark():
    raw = 'Here is the JSON you asked for:\n{"a": 1}\nHope that helps!'
    assert extract_json_object(raw) == {"a": 1}


def test_two_objects_returns_the_first():
    # The old first-{ to last-} slice produced '{"a": 1}\n{"b": 2}', which is
    # not valid JSON, so this whole class of response used to fail outright.
    assert extract_json_object('{"a": 1}\n{"b": 2}') == {"a": 1}


def test_trailing_prose_containing_a_brace():
    raw = '{"a": 1}\nNote: use {placeholders} carefully.'
    assert extract_json_object(raw) == {"a": 1}


def test_nested_objects_survive():
    raw = '{"questions": [{"id": 1, "name": "Python"}]}'
    assert extract_json_object(raw)["questions"][0]["id"] == 1


def test_truncated_response_raises():
    with pytest.raises(LLMJSONError):
        extract_json_object('{"a": 1')


def test_no_object_raises():
    with pytest.raises(LLMJSONError):
        extract_json_object("I could not answer that.")


def test_empty_raises():
    with pytest.raises(LLMJSONError):
        extract_json_object("")

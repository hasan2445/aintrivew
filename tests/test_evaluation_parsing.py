"""Table-driven tests for evaluate_answer's normalisation layer.

The three defensive layers (strip fences, recover the object, normalise every
field) exist because the model really does return an unknown category, a 0-100
score where the schema says 1-10, and a chatty preamble. None of that was
pinned by a test.
"""

import pytest

from models.schemas import RatingEnum
from services.question_generator import InterviewQuestionGenerator


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeModel:
    """Stands in for ChatGroq. Returns a scripted reply per invoke()."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply)


def build(replies):
    generator = InterviewQuestionGenerator.__new__(InterviewQuestionGenerator)
    generator.api_key = "test"
    generator.model = FakeModel(replies)
    return generator


def test_well_formed_evaluation():
    generator = build(['{"rating": "excellent", "score": 9.5, "strengths": ["clear"], '
                       '"improvements": [], "missing_concepts": [], '
                       '"follow_up_direction": "probe deeper"}'])
    result = generator.evaluate_answer("Q", "A")
    assert result.rating == RatingEnum.EXCELLENT
    assert result.score == 9.5
    assert result.unscored is False


def test_score_on_a_0_to_100_scale_is_rescaled():
    generator = build(['{"rating": "good", "score": 85, "strengths": [], '
                       '"improvements": [], "follow_up_direction": ""}'])
    assert generator.evaluate_answer("Q", "A").score == pytest.approx(8.5)


def test_score_is_clamped_into_range():
    generator = build(['{"rating": "poor", "score": -4, "strengths": [], '
                       '"improvements": [], "follow_up_direction": ""}'])
    assert generator.evaluate_answer("Q", "A").score == 1.0


def test_unknown_rating_falls_back_to_fair():
    generator = build(['{"rating": "outstanding", "strengths": [], '
                       '"improvements": [], "follow_up_direction": ""}'])
    assert generator.evaluate_answer("Q", "A").rating == RatingEnum.FAIR


def test_non_numeric_score_falls_back_to_the_rating():
    generator = build(['{"rating": "good", "score": "high", "strengths": [], '
                       '"improvements": [], "follow_up_direction": ""}'])
    assert generator.evaluate_answer("Q", "A").score == 8.0


def test_fenced_response_with_preamble():
    generator = build(['Sure.\n```json\n{"rating": "fair", "score": 6, '
                       '"strengths": [], "improvements": [], '
                       '"follow_up_direction": ""}\n```'])
    assert generator.evaluate_answer("Q", "A").rating == RatingEnum.FAIR


def test_unparseable_response_is_marked_unscored():
    # The fallback still rates "good" so a hiccup does not escalate into three
    # more probes — but it is now tagged so the score can exclude it.
    generator = build(["I'm not able to evaluate that."])
    result = generator.evaluate_answer("Q", "A")
    assert result.rating == RatingEnum.GOOD
    assert result.unscored is True


def test_transport_error_is_marked_unscored():
    generator = build([RuntimeError("connection reset")])
    assert generator.evaluate_answer("Q", "A").unscored is True

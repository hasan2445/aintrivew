"""Characterization tests for the follow-up state machine.

``submit_answer`` is pure logic over a session object once the generator is
stubbed, which is what makes a scripted sequence of ratings enough to assert
every transition. These are the tests that would have caught the mispaired
follow-up records and the duplicated report rows.
"""

import pytest

from models.schemas import (
    AnswerEvaluation,
    InterviewQuestion,
    InterviewSession,
    RatingEnum,
)
from services.question_generator import (
    SCORE_WEIGHTS,
    InterviewSessionManager,
    StaleTurnError,
)


class MemoryStore:
    """The RedisSessionStore surface submit_answer actually uses."""

    def __init__(self):
        self.sessions = {}
        self.proctoring = {}

    def set(self, session_id, session):
        self.sessions[session_id] = session.model_copy(deep=True)

    def get(self, session_id):
        session = self.sessions.get(session_id)
        return session.model_copy(deep=True) if session else None

    def delete(self, session_id):
        self.sessions.pop(session_id, None)

    def increment_proctoring(self, session_id, fields):
        bucket = self.proctoring.setdefault(session_id, {})
        for key, value in fields.items():
            bucket[key] = bucket.get(key, 0) + value

    def set_proctoring(self, session_id, fields):
        # Absolute write, mirroring HSET: the browser reports cumulative totals,
        # so incrementing would double-count every resend.
        self.proctoring.setdefault(session_id, {}).update(fields)

    def get_proctoring(self, session_id):
        return dict(self.proctoring.get(session_id, {}))


class ScriptedGenerator:
    """Returns ratings from a script; records follow-up calls."""

    def __init__(self, ratings, followup_error=None):
        self.ratings = list(ratings)
        self.followup_error = followup_error
        self.followup_calls = 0
        self.follow_up_direction = "go deeper"

    def evaluate_answer(self, question, candidate_answer):
        rating = self.ratings.pop(0) if self.ratings else "good"
        return AnswerEvaluation(
            rating=rating,
            score={"poor": 4.0, "fair": 6.0, "good": 8.0, "excellent": 9.5}[rating],
            strengths=[],
            improvements=[],
            missing_concepts=[],
            follow_up_direction=self.follow_up_direction,
        )

    def generate_followup(self, **kwargs):
        self.followup_calls += 1
        if self.followup_error:
            raise self.followup_error
        return f"Generated follow-up #{self.followup_calls}"


def make_manager(ratings, question_count=2, followup_error=None):
    manager = InterviewSessionManager.__new__(InterviewSessionManager)
    manager.session_store = MemoryStore()
    manager.generator = ScriptedGenerator(ratings, followup_error)

    questions = [
        InterviewQuestion(
            id=i + 1,
            category="skill",
            name=f"Topic {i + 1}",
            primary_question=f"Primary question {i + 1}?",
            context="context",
            difficulty_level="intermediate",
        )
        for i in range(question_count)
    ]
    session = InterviewSession(
        session_id="s1", resume_name="cv.pdf", job_role="Backend", questions=questions
    )
    manager.session_store.set("s1", session)
    return manager


# --- Branching -------------------------------------------------------------


def test_first_answer_always_gets_a_follow_up_even_when_excellent():
    manager = make_manager(["excellent"])
    result = manager.submit_answer("s1", "A strong answer.")
    assert result["action"] == "follow_up"
    assert result["followup_depth"] == 1


def test_excellent_on_a_follow_up_closes_the_thread():
    manager = make_manager(["good", "excellent"])
    manager.submit_answer("s1", "first")
    result = manager.submit_answer("s1", "second")
    assert result["action"] == "next_question"
    assert result["next_question_available"] is True


def test_depth_cap_stops_the_thread_at_three():
    manager = make_manager(["good"] * 5)
    assert manager.submit_answer("s1", "a1")["followup_depth"] == 1
    assert manager.submit_answer("s1", "a2")["followup_depth"] == 2
    assert manager.submit_answer("s1", "a3")["followup_depth"] == 3
    # Depth 3 is max_followup_depth, so the fourth answer closes the thread.
    assert manager.submit_answer("s1", "a4")["action"] == "next_question"


def test_two_consecutive_poor_ratings_end_the_thread():
    # Previously only "excellent" or the depth cap could stop the loop, so the
    # candidate who plainly did not know the topic got the longest interrogation
    # on it.
    manager = make_manager(["poor", "poor"])
    manager.submit_answer("s1", "a1")
    result = manager.submit_answer("s1", "a2")
    assert result["action"] == "next_question"


def test_a_single_poor_still_probes():
    manager = make_manager(["poor", "good"])
    manager.submit_answer("s1", "a1")
    assert manager.submit_answer("s1", "a2")["action"] == "follow_up"


def test_consecutive_poor_resets_on_a_better_answer():
    manager = make_manager(["poor", "good", "poor", "good"], question_count=3)
    manager.submit_answer("s1", "a1")   # depth 1
    manager.submit_answer("s1", "a2")   # good -> counter resets, depth 2
    result = manager.submit_answer("s1", "a3")  # one poor only
    assert result["action"] == "follow_up"


def test_interview_completes_after_the_last_question():
    manager = make_manager(["excellent", "excellent"], question_count=1)
    manager.submit_answer("s1", "a1")
    result = manager.submit_answer("s1", "a2")
    assert result["interview_complete"] is True
    assert manager.get_session("s1").status == "completed"


# --- Record integrity ------------------------------------------------------


def test_stored_question_always_matches_its_answer():
    # The probing branch used to store the *next* question alongside the
    # previous answer, mispairing every record but the last in each thread.
    manager = make_manager(["good", "good", "excellent"])
    manager.submit_answer("s1", "answer one")
    manager.submit_answer("s1", "answer two")
    manager.submit_answer("s1", "answer three")

    records = manager.get_session("s1").follow_ups
    assert records[0].question == "Primary question 1?"
    assert records[0].candidate_answer == "answer one"
    assert records[0].next_question == "Generated follow-up #1"
    assert records[1].question == "Generated follow-up #1"
    assert records[1].candidate_answer == "answer two"
    assert records[2].question == "Generated follow-up #2"
    assert records[2].candidate_answer == "answer three"


def test_one_record_per_answer():
    manager = make_manager(["good", "good", "excellent"])
    for text in ("a1", "a2", "a3"):
        manager.submit_answer("s1", text)
    session = manager.get_session("s1")
    assert len(session.follow_ups) == len(session.answers) == 3


def test_depth_is_the_depth_the_answer_was_given_at():
    manager = make_manager(["good", "good", "excellent"])
    for text in ("a1", "a2", "a3"):
        manager.submit_answer("s1", text)
    assert [f.depth for f in manager.get_session("s1").follow_ups] == [0, 1, 2]


def test_report_emits_one_row_per_primary_question():
    # Four answers on one question used to produce four identical qa_pairs, each
    # carrying the whole follow-up list.
    manager = make_manager(["good", "good", "good", "excellent"], question_count=1)
    for text in ("a1", "a2", "a3", "a4"):
        manager.submit_answer("s1", text)

    report = manager.get_interview_report("s1")
    assert len(report["qa_pairs"]) == 1
    assert report["qa_pairs"][0]["answer"] == "a1"
    assert len(report["qa_pairs"][0]["follow_ups"]) == 3


def test_history_is_wiped_between_primary_questions():
    manager = make_manager(["excellent", "excellent"])
    manager.submit_answer("s1", "a1")
    manager.submit_answer("s1", "a2")
    session = manager.get_session("s1")
    assert session.conversation_history == ""
    assert session.current_question_index == 1


# --- Failure handling ------------------------------------------------------


def test_follow_up_failure_still_keeps_the_answer():
    # The whole request used to unwind here, so the answer was lost and the
    # candidate had to retype it. There is no pre-generated seed question to
    # fall back on any more, so the turn is completed with the generic prompt.
    manager = make_manager(["good"], followup_error=RuntimeError("groq down"))
    result = manager.submit_answer("s1", "an answer worth keeping")

    assert result["action"] == "follow_up"
    assert result["follow_up_question"] == (
        "Could you walk me through a concrete example of that?"
    )
    session = manager.get_session("s1")
    assert session.answers[0].answer == "an answer worth keeping"
    assert len(session.follow_ups) == 1


def test_follow_up_failure_reuses_a_direction_already_phrased_as_a_question():
    # follow_up_direction is written for the interviewer, so it is only asked
    # verbatim when the model happened to address the candidate directly.
    manager = make_manager(["good"], followup_error=RuntimeError("groq down"))
    manager.generator.follow_up_direction = "Which index did you add, and why?"
    result = manager.submit_answer("s1", "an answer worth keeping")

    assert result["follow_up_question"] == "Which index did you add, and why?"


def test_unscored_evaluations_are_excluded_from_the_score():
    manager = make_manager(["good", "excellent"])
    manager.submit_answer("s1", "a1")
    manager.submit_answer("s1", "a2")

    session = manager.session_store.sessions["s1"]
    session.follow_ups[0].evaluation.unscored = True
    session.follow_ups[0].evaluation.score = 8.0

    scores = manager.calculate_interview_score("s1")
    assert scores["unscored_evaluations"] == 1
    # Only the 9.5 remains, so technical is 95, not the average with the 8.0.
    assert scores["technical_score"] == pytest.approx(95.0)


# --- Proctoring and attention ----------------------------------------------


def _scored(**proctoring):
    manager = make_manager(["good", "excellent"], question_count=1)
    manager.submit_answer("s1", "a1")
    manager.submit_answer("s1", "a2")
    if proctoring:
        manager.session_store.increment_proctoring("s1", proctoring)
    return manager


def test_integrity_penalty_uses_only_server_verified_signals():
    # Phone and extra-person are YOLO's verdicts on frames the server decoded.
    # Attention is browser-reported and must never reach this number.
    scores = _scored(
        frames_analysed=100, phone_frames=3, multiple_person_frames=2
    ).calculate_interview_score("s1")
    assert scores["integrity_penalty"] == 25.0
    assert scores["proctoring"]["phone_frames"] == 3
    assert scores["proctoring"]["multiple_person_frames"] == 2


def test_no_frames_means_no_penalty():
    scores = _scored().calculate_interview_score("s1")
    assert scores["integrity_penalty"] == 0.0
    assert scores["proctoring"]["frames_analysed"] == 0


def test_attention_is_reported_but_never_scored():
    manager = _scored(frames_analysed=100)
    manager.session_store.set_proctoring(
        "s1",
        {
            "attention_samples": 1000,
            "attentive_samples": 850,
            "look_away_events": 12,
            "look_away_seconds": 47,
            "no_face_events": 2,
        },
    )
    scores = manager.calculate_interview_score("s1")

    assert scores["attention"]["reported"] is True
    assert scores["attention"]["on_screen_percentage"] == pytest.approx(85.0)
    assert scores["attention"]["look_away_events"] == 12
    assert scores["attention"]["look_away_seconds"] == 47
    # The whole point: it is feedback, not a graded component.
    assert "eye_contact_score" not in scores
    assert "eye_contact_score" not in scores["score_basis"]["components"]
    assert scores["integrity_penalty"] == 0.0


def test_attention_absent_is_reported_honestly_not_defaulted():
    scores = _scored(frames_analysed=100).calculate_interview_score("s1")
    assert scores["attention"]["reported"] is False
    assert scores["attention"]["on_screen_percentage"] is None


def test_attentive_samples_cannot_exceed_total_samples():
    manager = _scored()
    manager.session_store.set_proctoring(
        "s1", {"attention_samples": 100, "attentive_samples": 900}
    )
    scores = manager.calculate_interview_score("s1")
    assert scores["attention"]["on_screen_percentage"] == pytest.approx(100.0)


def test_overall_is_a_weighted_percentage_of_the_scored_components():
    earned, weights = InterviewSessionManager._overall_percentage(
        {
            "technical_score": 80.0,
            "communication_score": 70.0,
            "confidence_score": 60.0,
            "resume_alignment_score": 90.0,
        }
    )
    expected = (80 * 0.35 + 70 * 0.20 + 60 * 0.15 + 90 * 0.15) / 0.85
    assert earned == pytest.approx(expected)
    assert sum(weights.values()) == pytest.approx(1.0)
    assert len(weights) == 4




def test_a_perfect_candidate_scores_100():
    full = {name: 100.0 for name in SCORE_WEIGHTS}
    assert InterviewSessionManager._overall_percentage(full)[0] == pytest.approx(100.0)


def test_score_basis_names_the_four_scored_components():
    scores = _scored().calculate_interview_score("s1")
    basis = scores["score_basis"]
    assert len(basis["components"]) == 4
    assert sum(basis["weights"].values()) == pytest.approx(1.0, abs=1e-3)


def test_no_measurable_component_yields_zero_not_a_crash():
    earned, weights = InterviewSessionManager._overall_percentage(
        {name: None for name in SCORE_WEIGHTS}
    )
    assert earned == 0.0
    assert weights == {}


# --- Idempotency -----------------------------------------------------------


def test_turn_increments_on_every_accepted_submission():
    manager = make_manager(["good", "good"])
    assert manager.submit_answer("s1", "a1", turn=0)["turn"] == 1
    assert manager.submit_answer("s1", "a2", turn=1)["turn"] == 2


def test_replaying_a_consumed_turn_is_rejected():
    manager = make_manager(["good", "good"])
    manager.submit_answer("s1", "a1", turn=0)
    with pytest.raises(StaleTurnError):
        manager.submit_answer("s1", "a1 again", turn=0)
    # And nothing was written for the rejected attempt.
    assert len(manager.get_session("s1").answers) == 1


def test_omitting_the_turn_keeps_the_legacy_behaviour():
    manager = make_manager(["good", "good"])
    manager.submit_answer("s1", "a1")
    manager.submit_answer("s1", "a2")
    assert len(manager.get_session("s1").answers) == 2


def test_empty_answer_is_rejected():
    manager = make_manager(["good"])
    with pytest.raises(ValueError):
        manager.submit_answer("s1", "   ")

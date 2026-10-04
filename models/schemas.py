"""
Data Models for Interview System
"""

from pydantic import BaseModel, Field
from typing import Any, List, Optional
from datetime import datetime, timezone
from enum import Enum


def _utcnow() -> datetime:
    """Timezone-aware UTC default (``datetime.utcnow`` is deprecated in 3.12+)."""
    return datetime.now(timezone.utc)


class CategoryEnum(str, Enum):
    SKILL = "skill"
    GENERIC_SKILL = "generic_skill"
    PROJECT = "project"
    EXPERIENCE = "experience"
    ACHIEVEMENT = "achievement"
    SCENARIO = "scenario"
    BEHAVIORAL = "behavioral"


class DifficultyLevel(str, Enum):
    EASY = "easy"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class RatingEnum(str, Enum):
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"


class InterviewQuestion(BaseModel):
    id: int
    category: CategoryEnum
    name: str
    primary_question: str
    context: str
    difficulty_level: DifficultyLevel
    # No follow-up field: follow-ups are written mid-interview by
    # generate_followup(), after the candidate's answer has been read. A
    # question generated before the answer exists cannot respond to it.
    # Sessions serialized before this change still load — pydantic ignores the
    # extra key.

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "category": "skill",
                "name": "Python",
                "primary_question": "Describe a production issue you solved using Python.",
                "context": "Understanding real-world debugging and optimization",
                "difficulty_level": "advanced",
            }
        }


class CandidateAnswer(BaseModel):
    question_id: int
    answer: str
    is_followup: bool = False
    followup_depth: int = 0
    timestamp: datetime = Field(default_factory=_utcnow)


class AnswerEvaluation(BaseModel):
    rating: RatingEnum
    score: float = 6.0
    strengths: List[str]
    improvements: List[str]
    missing_concepts: List[str] = []
    follow_up_direction: str
    # True when the model's reply could not be parsed and the values below are a
    # flow-control placeholder rather than a judgement. Scoring excludes these so
    # a run of parse failures cannot inflate (or deflate) the final number.
    unscored: bool = False


class FollowUpQuestion(BaseModel):
    """One evaluated turn in a follow-up thread.

    ``question`` is always the question that ``candidate_answer`` answers. It
    previously held the *next* question in the probing branch, which mispaired
    every record except the last one in each thread.
    """

    original_question_id: int
    depth: int
    question: str
    candidate_answer: str = ""
    evaluation: AnswerEvaluation
    # The question generated after this turn, when the thread continued. Kept
    # separate so it can never be mistaken for the question that was answered.
    next_question: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)


class ProctoringStats(BaseModel):
    """Server-observed proctoring counters for one interview.

    Incremented by ``/api/analyze-frame`` from the server's own YOLO verdicts and
    never accepted from the client. These are the only integrity signals that
    remain server-verified, and the only ones the score penalises.
    """

    frames_analysed: int = 0
    phone_frames: int = 0
    multiple_person_frames: int = 0


class AttentionReport(BaseModel):
    """Attention counters measured in the browser and reported by it.

    Deliberately client-sourced. The browser runs MediaPipe FaceMesh on every
    frame at camera rate and derives gaze from iris position between the eye
    corners — a finer measurement than anything recoverable from one 320x240
    JPEG every three seconds, and it already tracks duration, which frame counts
    cannot. Since nothing in this product acts on the number adversarially, the
    better measurement is worth more than the weaker attestation.

    Consequently these values are reported as feedback and never feed the
    integrity penalty. Totals are cumulative, not deltas.
    """

    samples: int = Field(0, ge=0, description="Frames the browser analysed")
    attentive_samples: int = Field(0, ge=0, description="Frames with gaze on screen")
    look_away_events: int = Field(0, ge=0)
    look_away_seconds: int = Field(0, ge=0)
    no_face_events: int = Field(0, ge=0)


class InterviewSession(BaseModel):
    session_id: str
    # Who owns this interview. Present so a live-session request can be
    # authorised from the blob it was about to read anyway, instead of a
    # separate `interviews` row lookup on every webcam frame. Optional so
    # sessions written before this field existed still load; those fall back to
    # the database check.
    user_id: Optional[int] = None
    resume_name: str
    job_role: str
    # Candidate-chosen difficulty band, applied as a ceiling override in the
    # generation prompt. Was previously a UI-only setting that reached nothing.
    difficulty: str = "medium"
    questions: List[InterviewQuestion]
    current_question_index: int = 0

    is_followup_mode: bool = False
    current_followup_depth: int = 0
    max_followup_depth: int = 3
    current_followup_question: str = ""
    # Consecutive "poor" ratings in the current thread. Two in a row ends the
    # thread, so the loop terminates on certainty in either direction rather
    # than only on success.
    consecutive_poor: int = 0

    answers: List[CandidateAnswer] = []
    follow_ups: List[FollowUpQuestion] = []

    # Plain-text history (JSON-safe). Replaces ConversationBufferMemory.
    conversation_history: str = ""
    # Legacy field kept for older serialized sessions; unused.
    memory: Any = None

    # Monotonic turn counter. The client echoes it back on submit so a duplicate
    # or replayed submission is rejected before any LLM call, instead of two
    # concurrent read-modify-writes silently losing one answer.
    turn: int = 0

    created_at: datetime = Field(default_factory=_utcnow)
    status: str = "in_progress"

    class Config:
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "session_id": "session_123",
                "resume_name": "john_doe.pdf",
                "job_role": "Senior Backend Engineer",
                "questions": [],
                "current_question_index": 0,
                "answers": [],
                "follow_ups": [],
                "status": "in_progress"
            }
        }


class ResumeUploadRequest(BaseModel):
    job_role: str


class QuestionResponse(BaseModel):
    session_id: str
    question_number: int
    total_questions: int
    category: CategoryEnum
    name: str
    primary_question: str
    context: str
    difficulty_level: DifficultyLevel


class AnswerSubmissionRequest(BaseModel):
    # Bounded so a hostile or runaway client cannot push an unbounded prompt
    # into the LLM call. 20k chars is far above any realistic spoken answer.
    answer: str = Field(..., min_length=1, max_length=20000)
    # Which turn this answer is for. Omitted by older clients, in which case the
    # idempotency check is skipped and the previous last-write-wins behaviour
    # applies; the bundled frontend always sends it.
    turn: Optional[int] = None


class FollowUpResponse(BaseModel):
    follow_up_question: str
    evaluation: AnswerEvaluation


class InterviewProgressResponse(BaseModel):
    session_id: str
    total_questions: int
    current_question: int
    completed_percentage: float
    status: str


class CommunicationAnalysis(BaseModel):
    """Analysis of candidate's communication skills"""
    speaking_speed_wpm: float
    filler_word_count: int
    average_pause_seconds: float
    confidence_score: float
    clarity_score: float

    class Config:
        json_schema_extra = {
            "example": {
                "speaking_speed_wpm": 140,
                "filler_word_count": 8,
                "average_pause_seconds": 2.5,
                "confidence_score": 82,
                "clarity_score": 85
            }
        }


class FaceAnalysis(BaseModel):
    """Analysis of face and eye contact during interview"""
    eye_contact_percentage: float
    face_detected_percentage: float
    head_position: str
    emotion: str
    looking_away_incidents: int
    face_missing_incidents: int

    class Config:
        json_schema_extra = {
            "example": {
                "eye_contact_percentage": 87,
                "face_detected_percentage": 95,
                "head_position": "centered",
                "emotion": "neutral",
                "looking_away_incidents": 2,
                "face_missing_incidents": 0
            }
        }


class CheatingDetectionResult(BaseModel):
    """Cheating detection analysis"""
    phone_detected: bool
    multiple_faces_detected: bool
    suspicious_behavior_detected: bool
    cheating_score: float
    flags: List[str] = []

    class Config:
        json_schema_extra = {
            "example": {
                "phone_detected": False,
                "multiple_faces_detected": False,
                "suspicious_behavior_detected": False,
                "cheating_score": 5,
                "flags": []
            }
        }


class InterviewMetrics(BaseModel):
    """Complete interview metrics and scoring"""
    technical_score: float
    communication_score: float
    confidence_score: float
    eye_contact_score: float
    resume_alignment_score: float
    problem_solving_score: float
    overall_score: float

    class Config:
        json_schema_extra = {
            "example": {
                "technical_score": 85,
                "communication_score": 78,
                "confidence_score": 82,
                "eye_contact_score": 87,
                "resume_alignment_score": 88,
                "problem_solving_score": 75,
                "overall_score": 82
            }
        }


class ImprovementPlan(BaseModel):
    """Personalized improvement recommendations"""
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    focus_areas: List[str]
    resources: List[str] = []

    class Config:
        json_schema_extra = {
            "example": {
                "strengths": [
                    "Strong Python knowledge",
                    "Good project explanation",
                    "Clear communication"
                ],
                "weaknesses": [
                    "Poor SQL understanding",
                    "Limited database design knowledge",
                    "Too many filler words"
                ],
                "recommendations": [
                    "Practice DBMS concepts",
                    "Study database design patterns",
                    "Practice speaking without filler words"
                ],
                "focus_areas": [
                    "Database fundamentals",
                    "Communication clarity",
                    "System design"
                ],
                "resources": [
                    "LeetCode Database Problems",
                    "System Design Primer"
                ]
            }
        }


class InterviewReport(BaseModel):
    """Complete interview report"""
    session_id: str
    resume_name: str
    job_role: str
    questions_answered: int
    total_questions: int

    metrics: InterviewMetrics
    communication_analysis: CommunicationAnalysis
    face_analysis: FaceAnalysis
    cheating_detection: CheatingDetectionResult

    q_and_a: List[dict]

    improvement_plan: ImprovementPlan

    created_at: datetime = Field(default_factory=_utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_123",
                "resume_name": "john_doe.pdf",
                "job_role": "Senior Backend Engineer",
                "questions_answered": 5,
                "total_questions": 10,
                "metrics": {},
                "communication_analysis": {},
                "face_analysis": {},
                "cheating_detection": {},
                "q_and_a": [],
                "improvement_plan": {}
            }
        }

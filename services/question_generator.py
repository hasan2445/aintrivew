"""
Question Generation and Interview Logic
"""

import json
import logging
import os
import re
import sys
from typing import List, Optional, Tuple
import uuid
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq


load_dotenv()

logger = logging.getLogger(__name__)


sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml'))

from models.schemas import (
    InterviewQuestion,
    InterviewSession,
    CandidateAnswer,
    FollowUpQuestion,
    AnswerEvaluation,
    RatingEnum,
)
from services.prompts import (
    QUESTION_GENERATION_PROMPT,
    FOLLOWUP_QUESTION_PROMPT,
    ANSWER_EVALUATION_PROMPT,
    DIFFICULTY_DIRECTIVES,
)
from services.llm_json import extract_json_object
from core.redis_session_store import RedisSessionStore
from core.config import (
    GROQ_MAX_TOKENS,
    GROQ_MODEL,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    MAX_ANSWER_CHARS,
    MAX_PRIMARY_QUESTIONS,
)


class QuestionGenerationError(RuntimeError):
    """Raised when the LLM cannot produce usable interview questions."""


class StaleTurnError(ValueError):
    """Raised when a submission targets a turn that has already been consumed."""


RATING_TO_SCORE = {
    "poor": 40.0,
    "fair": 60.0,
    "good": 80.0,
    "excellent": 95.0,
}

# Frontend uses a 0–10 scale; LLM score is expected on 1–10.
RATING_TO_SCORE_10 = {
    "poor": 4.0,
    "fair": 6.0,
    "good": 8.0,
    "excellent": 9.5,
}

# Minimum viable observability for the silent-fallback path: without a counter,
# a production run of unparseable evaluations is invisible from the outside.
# Surfaced by /api/health.
EVALUATION_PARSE_FAILURES = {"count": 0}

# Weights for the overall percentage. They sum to 1.0 when every component is
# available; when one cannot be measured its weight is redistributed across the
# remainder in proportion, so the overall is always a percentage of the criteria
# that were actually assessed rather than a mean over a varying number of terms.
#
# problem_solving_score is deliberately absent: it is a pure rescaling of the
# technical score, so including it would count the same signal twice.
#
# eye_contact_score is absent too, and that is the substantive change. Attention
# is now measured in the browser and reported by it, which makes it feedback
# rather than evidence — so it is shown to the candidate but does not grade
# them. Weights are renormalised over whatever is present, so removing it simply
# redistributes its share across the four that remain.
SCORE_WEIGHTS = {
    "technical_score": 0.35,
    "communication_score": 0.20,
    "confidence_score": 0.15,
    "resume_alignment_score": 0.15,
}


# Placeholder names a prompt template may legitimately contain. Anything else
# left over after substitution is a typo, not JSON.
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


def _fill_prompt(template: str, **kwargs) -> str:
    """Replace {placeholders} without interpreting JSON example braces via str.format.

    ``str.format`` cannot be used: these templates embed the JSON schema the
    model must emit, so every example brace would be read as a replacement
    field. Doubling the braces makes the prompts unreadable and breaks silently
    for whoever edits them next.

    The blind ``.replace`` that this used to be had no error when a key was
    misspelled — a typo shipped a literal ``{resume_text}`` to the model and
    nothing detected it. Leftovers are now logged.
    """
    out = template
    for key, value in kwargs.items():
        out = out.replace("{" + key + "}", str(value))

    leftover = {
        name for name in _PLACEHOLDER_RE.findall(out) if name not in kwargs
    }
    if leftover:
        logger.error(
            "Prompt placeholders were never filled: %s. Check the template and "
            "the caller's kwargs agree.",
            ", ".join(sorted(leftover)),
        )
    return out


# Asked only when the follow-up model call fails. Deliberately generic: it is
# always grammatical and always answerable, which a salvaged fragment of
# interviewer-facing prose is not.
_GENERIC_FOLLOW_UP = "Could you walk me through a concrete example of that?"


def _fallback_follow_up(direction: str) -> str:
    """Turn an evaluation's follow-up direction into something askable.

    ``follow_up_direction`` is written for the interviewer — "probe how they
    chose the index" — so asking it verbatim reads as a stage instruction, not
    a question. It is used only when the model already phrased it as a question
    to the candidate; otherwise the generic prompt is asked instead. This path
    used to reach for the seed follow-up written at generation time, which no
    longer exists.
    """
    text = (direction or "").strip()
    if text.endswith("?"):
        return text
    return _GENERIC_FOLLOW_UP


def _rating_value(rating) -> str:
    if hasattr(rating, "value"):
        return str(rating.value).lower()
    return str(rating).lower()


def _category_label(category) -> str:
    if hasattr(category, "value"):
        return str(category.value)
    return str(category)


def _evaluation_dict(evaluation) -> dict:
    if hasattr(evaluation, "model_dump"):
        return evaluation.model_dump(mode="json")
    data = evaluation.dict()
    if hasattr(data.get("rating"), "value"):
        data["rating"] = data["rating"].value
    return data


class InterviewQuestionGenerator:
    """Generate interview questions from resume using Llama3 LLM"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with GROQ API key"""
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ API key not found. Set GROQ_API_KEY environment variable.")

        self.model = ChatGroq(
            groq_api_key=self.api_key,
            model=GROQ_MODEL,
            temperature=0.2,
            max_tokens=GROQ_MAX_TOKENS,
            # Previously unset, so an unbounded call inside a threadpool worker
            # could hold a request thread until the upstream gave up. These two
            # constants had been sitting in core/config.py unread.
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )

    def generate_questions(
        self,
        resume_text: str,
        job_role: str = "Software Engineer",
        difficulty: str = "medium",
    ) -> List[InterviewQuestion]:
        """Generate interview questions from resume text, steered by job role."""

        directive = DIFFICULTY_DIRECTIVES.get(
            str(difficulty or "medium").lower(), DIFFICULTY_DIRECTIVES["medium"]
        )
        prompt = _fill_prompt(
            QUESTION_GENERATION_PROMPT,
            resume_text=resume_text,
            job_role=job_role or "Software Engineer",
            difficulty_directive=directive,
        )

        try:
            response = self.model.invoke([
                SystemMessage(content="You are an expert technical interviewer. Generate only valid JSON output."),
                HumanMessage(content=prompt)
            ])

            data = extract_json_object(response.content)

            category_map = {
                "skills": "skill",
                "skill": "skill",
                "generic_skill": "generic_skill",
                "generic": "generic_skill",
                "generic technical": "generic_skill",
                "projects": "project",
                "project": "project",
                "experience": "experience",
                "experiences": "experience",
                "achievements": "achievement",
                "achievement": "achievement",
                "scenario": "scenario",
                "scenarios": "scenario",
                "engineering scenario": "scenario",
                "behavioral": "behavioral",
                "behavioural": "behavioral",
            }

            questions = []
            valid_difficulties = {"easy", "intermediate", "advanced", "expert"}
            for idx, q in enumerate(data.get("questions", []), 1):
                category = str(q.get("category", "skill")).lower().strip()
                category = category_map.get(category, "skill")

                diff = str(q.get("difficulty_level", "intermediate")).lower().strip()
                if diff not in valid_difficulties:
                    diff = "intermediate"

                question = InterviewQuestion(
                    id=idx,
                    category=category,
                    name=q.get("name", ""),
                    primary_question=q.get("primary_question", ""),
                    context=q.get("context", ""),
                    difficulty_level=diff,
                )
                questions.append(question)

            # Hard cap so live interviews stay practical even if the model over-generates.
            questions = questions[:MAX_PRIMARY_QUESTIONS]

            # `extracted_profile` and `candidate_level` are in the response
            # schema but deliberately not parsed. They exist to make the model
            # commit to a band and enumerate the resume's skills and projects
            # *before* it writes the questions — tokens are emitted in order, so
            # the questions are generated after that read rather than instead of
            # it. Nothing downstream consumed the profile: it was stored, shipped
            # to the browser and assigned to three variables no render function
            # ever read.
            return questions

        except Exception as e:
            logger.exception("Question generation failed: %s: %s", type(e).__name__, e)
            raise QuestionGenerationError(f"Error generating questions: {e}") from e

    def generate_followup(
        self,
        primary_question: str,
        candidate_answer: str,
        difficulty_level: str,
        context: str,
        conversation_history_text: str = "",
        current_depth: int = 1,
        max_depth: int = 3,
        follow_up_direction: str = "",
    ) -> str:
        """Generate a follow-up from the answer that was just given.

        There is no seed question to fall back on by design: the generation
        prompt no longer writes one. A follow-up guessed before the answer
        exists cannot respond to what was actually said, so the only inputs
        here are the primary question, the answer, the thread so far, and the
        direction the evaluation asked for.
        """

        history_text = conversation_history_text if conversation_history_text else "[No prior follow-ups yet]"

        prompt = _fill_prompt(
            FOLLOWUP_QUESTION_PROMPT,
            primary_question=primary_question,
            difficulty_level=difficulty_level,
            context=context,
            candidate_answer=candidate_answer,
            conversation_history=history_text,
            current_depth=current_depth,
            max_depth=max_depth,
            follow_up_direction=follow_up_direction or "Ask for a concrete example, at a depth appropriate to the candidate's level.",
        )

        try:
            response = self.model.invoke([
                SystemMessage(content="You are an expert technical interviewer. Generate only the follow-up question, nothing else."),
                HumanMessage(content=prompt)
            ])

            return response.content.strip()

        except Exception as e:
            raise RuntimeError(f"GROQ follow-up generation failed: {e}") from e

    def evaluate_answer(
        self,
        question: str,
        candidate_answer: str
    ) -> AnswerEvaluation:
        """Evaluate candidate answer against the question that was actually asked."""

        prompt = _fill_prompt(
            ANSWER_EVALUATION_PROMPT,
            question=question,
            answer=candidate_answer,
        )

        try:
            response = self.model.invoke([
                SystemMessage(content="You are an expert technical interviewer. Return only valid JSON."),
                HumanMessage(content=prompt)
            ])

            data = extract_json_object(response.content)

            rating_raw = str(data.get("rating", "fair")).lower().strip()
            if rating_raw not in RATING_TO_SCORE_10:
                rating_raw = "fair"

            score_raw = data.get("score", RATING_TO_SCORE_10[rating_raw])
            try:
                score_val = float(score_raw)
            except (TypeError, ValueError):
                score_val = RATING_TO_SCORE_10[rating_raw]

            # Normalize accidental 0–100 scores to 0–10.
            if score_val > 10:
                score_val = score_val / 10.0
            score_val = max(1.0, min(10.0, score_val))

            return AnswerEvaluation(
                rating=rating_raw,
                score=score_val,
                strengths=data.get("strengths", []) or [],
                improvements=data.get("improvements", []) or [],
                missing_concepts=data.get("missing_concepts", []) or [],
                follow_up_direction=data.get("follow_up_direction", "") or "",
            )

        except Exception as e:
            # `except (json.JSONDecodeError, Exception)` was redundant - the second
            # arm already caught everything, including the first.
            #
            # The rating still defaults to "good" (not "fair") because it feeds
            # the follow-up decision, and "fair" would escalate an LLM hiccup
            # into three more probes on a topic the system knows nothing about.
            # `unscored=True` keeps that flow-control choice while excluding the
            # placeholder 8.0 from the score, which used to silently inflate the
            # final number and was indistinguishable from a real evaluation
            # downstream.
            EVALUATION_PARSE_FAILURES["count"] += 1
            logger.warning(
                "evaluate_answer parse failed (total=%d): %s",
                EVALUATION_PARSE_FAILURES["count"],
                e,
            )
            return AnswerEvaluation(
                rating=RatingEnum.GOOD,
                score=RATING_TO_SCORE_10["good"],
                strengths=["Answer provided"],
                improvements=["Could not fully parse automated evaluation; review manually if needed"],
                missing_concepts=[],
                follow_up_direction="Ask for one concrete example or implementation detail",
                unscored=True,
            )


class InterviewSessionManager:
    """Manage interview sessions"""

    def __init__(self):
        self.session_store = RedisSessionStore()
        self.generator = InterviewQuestionGenerator()

    def _save_session(self, session: InterviewSession) -> None:
        """Persist session after every mutation."""
        self.session_store.set(session.session_id, session)

    def _append_history(self, session: InterviewSession, question: str, answer: str, kind: str) -> None:
        block = f"[{kind}_QUESTION] {question}\n[{kind}_ANSWER] {answer}"
        if session.conversation_history:
            session.conversation_history = f"{session.conversation_history}\n\n{block}"
        else:
            session.conversation_history = block

    def create_session(
        self,
        resume_text: str,
        job_role: str,
        resume_name: str,
        difficulty: str = "medium",
        user_id: Optional[int] = None,
    ) -> InterviewSession:
        """Create a new interview session"""

        difficulty = str(difficulty or "medium").lower()
        if difficulty not in DIFFICULTY_DIRECTIVES:
            difficulty = "medium"

        questions = self.generator.generate_questions(
            resume_text, job_role=job_role, difficulty=difficulty
        )

        session_id = str(uuid.uuid4())
        session = InterviewSession(
            session_id=session_id,
            user_id=user_id,
            resume_name=resume_name,
            job_role=job_role,
            difficulty=difficulty,
            questions=questions,
            conversation_history="",
            memory=None,
        )

        self.session_store.set(session_id, session)
        return session

    def get_session(self, session_id: str) -> Optional[InterviewSession]:
        """Retrieve a session"""
        return self.session_store.get(session_id)

    def get_current_question(self, session_id: str) -> Optional[InterviewQuestion]:
        """Get current question in the session"""
        session = self.get_session(session_id)
        if not session:
            return None

        if session.current_question_index < len(session.questions):
            return session.questions[session.current_question_index]
        return None

    def submit_answer(self, session_id: str, answer: str, turn: Optional[int] = None) -> dict:
        """
        Submit answer to current question or follow-up.

        Returns:
        {
            "action": "follow_up" | "next_question",
            "evaluation": AnswerEvaluation dict,
            "follow_up_question": str (if action="follow_up", else null),
            "next_question": InterviewQuestion dict (if action="next_question", else null),
            "next_question_available": bool,
            "followup_depth": int,
            "turn": int
        }
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Idempotency, not locking. The whole session is a read-modify-write with
        # no compare-and-set, so two concurrent submits (a double-Enter, an
        # impatient double-click) both read the same state and the second SET
        # wins, losing an answer and its evaluation. A lock would have to be held
        # across two sequential LLM calls; rejecting a stale turn is a cheap 409
        # *before* any LLM call and has no lifetime to get wrong.
        if turn is not None and int(turn) != session.turn:
            raise StaleTurnError(
                f"Turn {turn} has already been submitted for this session"
            )

        if not answer or not str(answer).strip():
            raise ValueError("Answer cannot be empty")

        # Truncate rather than reject, so a long dictation is still usable while
        # the prompt sent to the LLM stays bounded.
        answer = str(answer).strip()[:MAX_ANSWER_CHARS]

        if session.current_question_index >= len(session.questions):
            raise ValueError(f"No current question in session {session_id}")

        current_question = session.questions[session.current_question_index]

        # Evaluate against the question that was actually asked.
        if session.is_followup_mode:
            question_asked = (
                session.current_followup_question
                or (session.follow_ups[-1].question if session.follow_ups else current_question.primary_question)
            )
            history_kind = "FOLLOWUP"
        else:
            question_asked = current_question.primary_question
            history_kind = "PRIMARY"

        self._append_history(session, question_asked, answer, history_kind)

        candidate_answer = CandidateAnswer(
            question_id=current_question.id,
            answer=answer,
            is_followup=session.is_followup_mode,
            followup_depth=session.current_followup_depth
        )
        session.answers.append(candidate_answer)

        evaluation = self.generator.evaluate_answer(
            question=question_asked,
            candidate_answer=answer
        )

        rating_key = _rating_value(evaluation.rating)
        session.consecutive_poor = (
            session.consecutive_poor + 1 if rating_key == "poor" else 0
        )

        # Depth at which this answer was given, before any increment below. The
        # stored record must be tagged with the turn it belongs to, not the next.
        answered_depth = session.current_followup_depth

        should_ask_followup = False
        action = "next_question"

        if not session.is_followup_mode:
            # Unconditional on the first answer: a real interviewer never accepts
            # an opening answer and moves on. The claim is made here; the
            # follow-up is what tests whether it is real.
            should_ask_followup = True
            session.is_followup_mode = True
            session.current_followup_depth = 1
        else:
            keeps_probing = evaluation.rating in [
                RatingEnum.POOR,
                RatingEnum.FAIR,
                RatingEnum.GOOD,
            ]
            # Two consecutive "poor" ratings end the thread as well as
            # "excellent". Previously only success or the depth cap could stop
            # it, so a candidate who plainly did not know the topic got the
            # longest possible interrogation on it.
            struggling = session.consecutive_poor >= 2
            if (
                session.current_followup_depth < session.max_followup_depth
                and keeps_probing
                and not struggling
            ):
                session.current_followup_depth += 1
                should_ask_followup = True
            else:
                should_ask_followup = False

        follow_up_question = None
        if should_ask_followup:
            action = "follow_up"
            difficulty = (
                current_question.difficulty_level.value
                if hasattr(current_question.difficulty_level, "value")
                else str(current_question.difficulty_level)
            )
            try:
                follow_up_q = self.generator.generate_followup(
                    primary_question=current_question.primary_question,
                    candidate_answer=answer,
                    difficulty_level=difficulty,
                    context=current_question.context,
                    conversation_history_text=session.conversation_history,
                    current_depth=session.current_followup_depth,
                    max_depth=session.max_followup_depth,
                    follow_up_direction=evaluation.follow_up_direction,
                )
            except Exception as exc:
                # The evaluation call already succeeded. Unwinding the whole
                # request here would throw the answer away and make the
                # candidate retype it, so the turn is completed with the best
                # question available without a second model call.
                #
                # There is no pre-generated seed to fall back on any more. The
                # evaluation's follow_up_direction is written for an interviewer
                # ("probe how they chose the index"), not addressed to the
                # candidate, so it is phrased into a question rather than asked
                # verbatim.
                logger.warning(
                    "Follow-up generation failed for %s, falling back to the "
                    "evaluation's direction: %s",
                    session_id,
                    exc,
                )
                follow_up_q = _fallback_follow_up(evaluation.follow_up_direction)

            follow_up_question = follow_up_q
            session.current_followup_question = follow_up_q

        # One record per submitted answer, in both branches, with `question`
        # always meaning "the question this answer answers". The probing branch
        # used to store the *next* question here, which mispaired every record
        # except the last in each thread — data that is wrong at rest rather
        # than merely duplicated.
        session.follow_ups.append(FollowUpQuestion(
            original_question_id=current_question.id,
            depth=answered_depth,
            question=question_asked,
            candidate_answer=answer,
            evaluation=evaluation,
            next_question=follow_up_question or "",
        ))

        if not should_ask_followup:
            action = "next_question"
            session.is_followup_mode = False
            session.current_followup_depth = 0
            session.current_followup_question = ""
            session.conversation_history = ""
            session.consecutive_poor = 0

        try:
            eval_dict = evaluation.model_dump(mode="json")
        except AttributeError:
            eval_dict = evaluation.dict()
            if "rating" in eval_dict and hasattr(eval_dict["rating"], "value"):
                eval_dict["rating"] = eval_dict["rating"].value

        session.turn += 1

        result = {
            "action": action,
            "evaluation": eval_dict,
            "follow_up_question": follow_up_question,
            "followup_depth": session.current_followup_depth,
            "next_question": None,
            "next_question_available": False,
            "turn": session.turn,
        }

        if action == "next_question":
            has_next = session.current_question_index < len(session.questions) - 1
            result["next_question_available"] = has_next

            if has_next:
                session.current_question_index += 1
                next_q = session.questions[session.current_question_index]
                result["next_question"] = {
                    "question_number": session.current_question_index + 1,
                    "total_questions": len(session.questions),
                    "category": _category_label(next_q.category),
                    "name": next_q.name,
                    "primary_question": next_q.primary_question,
                    "context": next_q.context,
                    "difficulty_level": (
                        next_q.difficulty_level.value
                        if hasattr(next_q.difficulty_level, "value")
                        else next_q.difficulty_level
                    ),
                }
            else:
                session.status = "completed"

        # Returned from the object already in hand. The route used to do a third
        # Redis GET purely to re-read this flag.
        result["interview_complete"] = session.status == "completed"

        self._save_session(session)
        return result

    def proceed_to_next_question(self, session_id: str) -> bool:
        """
        Deprecated - progression now happens in submit_answer().
        Kept for backward compatibility only.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.current_question_index < len(session.questions) - 1:
            session.current_question_index += 1
            session.is_followup_mode = False
            session.current_followup_depth = 0
            session.current_followup_question = ""
            session.conversation_history = ""
            self._save_session(session)
            return True

        session.status = "completed"
        self._save_session(session)
        return False

    def get_interview_progress(self, session_id: str) -> dict:
        """Get interview progress"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        total = len(session.questions)
        current = session.current_question_index + 1
        percentage = (current / total * 100) if total > 0 else 0

        return {
            "session_id": session_id,
            "total_questions": total,
            "current_question": current,
            "completed_percentage": round(percentage, 2),
            "status": session.status
        }

    def get_interview_report(self, session_id: str) -> dict:
        """Generate interview report"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        report = {
            "session_id": session_id,
            "resume": session.resume_name,
            "job_role": session.job_role,
            "total_questions": len(session.questions),
            "answers_submitted": len(session.answers),
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "qa_pairs": []
        }

        # Only primary answers open a qa_pair. Every answer in a thread —
        # including follow-up answers — carries the primary question's id, so
        # iterating all of them emitted the same question once per follow-up,
        # each row repeating the identical follow-up list. `is_followup` was
        # already being written correctly at submit time and simply never read.
        for answer in session.answers:
            if answer.is_followup:
                continue

            question = next(
                (q for q in session.questions if q.id == answer.question_id),
                None
            )
            if not question:
                continue

            # depth 0 is the primary turn itself; its evaluation belongs to the
            # qa_pair, not to the nested follow-up thread.
            thread = [
                f for f in session.follow_ups
                if f.original_question_id == answer.question_id
            ]
            primary_eval = next((f for f in thread if f.depth == 0), None)

            qa_pair = {
                "question": question.primary_question,
                "category": _category_label(question.category),
                "answer": answer.answer,
                "evaluation": _evaluation_dict(primary_eval.evaluation) if primary_eval else None,
                "follow_ups": [
                    {
                        "depth": f.depth,
                        "question": f.question,
                        "candidate_answer": f.candidate_answer,
                        "evaluation": _evaluation_dict(f.evaluation),
                    }
                    for f in thread
                    if f.depth > 0
                ],
            }
            report["qa_pairs"].append(qa_pair)

        return report

    def generate_improvement_plan(self, session_id: str) -> dict:
        """Generate personalized improvement plan based on interview performance"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        try:
            all_evaluations = [follow_up.evaluation for follow_up in session.follow_ups]

            strengths = []
            improvements = []
            missing = []
            for ev in all_evaluations:
                strengths.extend(ev.strengths or [])
                improvements.extend(ev.improvements or [])
                missing.extend(getattr(ev, "missing_concepts", None) or [])

            context = f"""
Based on this interview for role: {session.job_role}

Candidate's Performance:
- Total Questions: {len(session.questions)}
- Answers Submitted: {len(session.answers)}
- Evaluations Recorded: {len(all_evaluations)}

Observed strengths (from evaluations):
{json.dumps(strengths[:12], indent=2)}

Observed improvements (from evaluations):
{json.dumps(improvements[:12], indent=2)}

Missing concepts:
{json.dumps(missing[:12], indent=2)}

Question Categories:
"""
            for q in session.questions[:8]:
                context += f"\n- {_category_label(q.category)}: {q.name}"

            context += """

Return ONLY valid JSON with this shape:
{
  "strengths": ["...", "...", "..."],
  "weaknesses": ["...", "...", "..."],
  "recommendations": ["...", "...", "..."],
  "focus_areas": ["...", "...", "..."]
}
"""

            response = self.generator.model.invoke([
                SystemMessage(content="You are a career coach. Generate only valid JSON improvement plan."),
                HumanMessage(content=context)
            ])

            data = extract_json_object(response.content)

            return {
                "strengths": data.get("strengths", []) or strengths[:3] or ["Participated in interview"],
                "weaknesses": data.get("weaknesses", []) or improvements[:3] or ["Area for growth"],
                "recommendations": data.get("recommendations", []) or ["Practice more interview questions"],
                "focus_areas": data.get("focus_areas", []) or ["Technical depth", "Communication"],
            }

        except Exception as e:
            logger.warning("Failed to generate improvement plan: %s", e)
            return {
                "strengths": ["Participated in interview"],
                "weaknesses": ["Area for growth"],
                "recommendations": ["Practice more interview questions"],
                "focus_areas": ["Technical depth", "Communication"]
            }

    def calculate_interview_score(self, session_id: str) -> dict:
        """Calculate comprehensive interview scores from recorded evaluations.

        This is the only score that is written to the database. The browser
        renders it; it no longer computes its own and POSTs the result back.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        technical_scores = []
        unscored_count = 0
        for follow_up in session.follow_ups:
            evaluation = follow_up.evaluation
            # A parse-failure placeholder is not a judgement. Counting its 8.0
            # as a real score inflated the average and was indistinguishable
            # from a genuine evaluation downstream.
            if getattr(evaluation, "unscored", False):
                unscored_count += 1
                continue

            rating_key = _rating_value(evaluation.rating)
            # `is not None` rather than truthiness: a legitimate 0.0 score would
            # otherwise silently fall through to the rating-based default.
            if getattr(evaluation, "score", None) is not None:
                # evaluation.score is 1–10; convert to 0–100 for report metrics.
                technical_scores.append(float(evaluation.score) * 10.0)
            else:
                technical_scores.append(RATING_TO_SCORE.get(rating_key, 60.0))

        # Also fold in answers that somehow lack follow-up records.
        if not technical_scores and session.answers:
            technical_scores = [60.0]

        avg_technical = sum(technical_scores) / len(technical_scores) if technical_scores else 0.0

        answer_lengths = [len((a.answer or "").split()) for a in session.answers]
        avg_words = (sum(answer_lengths) / len(answer_lengths)) if answer_lengths else 0.0
        length_factor = min(1.0, avg_words / 80.0) if avg_words else 0.7

        communication = round(max(40.0, min(95.0, avg_technical * (0.85 + 0.15 * length_factor))), 1)
        confidence = round(max(40.0, min(95.0, avg_technical * (0.88 + 0.10 * length_factor))), 1)
        resume_alignment = round(max(40.0, min(95.0, avg_technical * 0.93)), 1)
        problem_solving = round(avg_technical * 0.9, 1)

        # Integrity comes only from what the server itself observed: YOLO's
        # phone and extra-person verdicts on frames it decoded. Attention is
        # browser-reported (see below) and deliberately does not grade anyone.
        proctoring = self.session_store.get_proctoring(session_id)
        frames = proctoring.get("frames_analysed", 0)
        integrity_penalty = self._integrity_penalty(proctoring)

        # Attention is feedback, not a component of the score. It used to be
        # `eye_contact_score`, computed server-side from a nose-in-bounding-box
        # approximation on one frame every three seconds, and weighted at 0.15
        # of the result. The browser measures the same thing far better — iris
        # position between the eye corners, every frame — and it already tracks
        # duration, which frame counts cannot. Since nothing here acts on the
        # number adversarially, the better measurement is worth more than the
        # weaker attestation; the price is that it can no longer grade.
        attention = self._attention_summary(proctoring)

        component_scores = {
            "technical_score": avg_technical,
            "communication_score": communication,
            "confidence_score": confidence,
            "resume_alignment_score": resume_alignment,
        }
        earned, applied_weights = self._overall_percentage(component_scores)
        overall = round(max(0.0, min(100.0, earned - integrity_penalty)), 1)

        return {
            "technical_score": round(avg_technical, 1),
            "communication_score": communication,
            "confidence_score": confidence,
            "resume_alignment_score": resume_alignment,
            "problem_solving_score": problem_solving,
            "overall_score": overall,
            "integrity_penalty": integrity_penalty,
            "unscored_evaluations": unscored_count,
            "proctoring": {
                "frames_analysed": frames,
                "phone_frames": proctoring.get("phone_frames", 0),
                "multiple_person_frames": proctoring.get("multiple_person_frames", 0),
            },
            # Browser-measured, shown as feedback, excluded from the score.
            "attention": attention,
            # What the percentage was actually taken over, so the number can be
            # explained rather than just displayed.
            "score_basis": {
                "components": sorted(applied_weights),
                "weights": {k: round(v, 4) for k, v in sorted(applied_weights.items())},
            },
        }

    @staticmethod
    def _overall_percentage(component_scores: dict) -> Tuple[float, dict]:
        """Weighted percentage over the components that were measured.

        The overall used to be a plain mean of whatever components happened to
        exist. That is not comparable across candidates: a session with no
        camera averaged four numbers and a session with a camera averaged five,
        so the two results sat on subtly different scales and nothing said so.

        This computes an explicit percentage instead. Each component carries a
        fixed weight; when one could not be measured, its weight is
        redistributed across the rest **in proportion**, so the weights always
        sum to 1.0 and the result is always "percentage of the criteria that
        could actually be assessed". Two candidates are then comparable by
        construction — the basis is reported alongside the number so a missing
        component is visible rather than silently absorbed.
        """
        available = {
            name: float(score)
            for name, score in component_scores.items()
            if score is not None and name in SCORE_WEIGHTS
        }
        if not available:
            return 0.0, {}

        total_weight = sum(SCORE_WEIGHTS[name] for name in available)
        if total_weight <= 0:
            return 0.0, {}

        applied = {name: SCORE_WEIGHTS[name] / total_weight for name in available}
        earned = sum(available[name] * applied[name] for name in available)
        return earned, applied

    @staticmethod
    def _attention_summary(proctoring: dict) -> dict:
        """Browser-reported attention, presented as feedback.

        Returns None values when the browser never reported — no camera, or an
        older client — rather than a plausible-looking default. Nothing here
        feeds the score; it sits alongside filler words and speaking rate, which
        are also browser-measured and which nobody expects to be attested.
        """
        samples = proctoring.get("attention_samples", 0)
        if samples <= 0:
            return {
                "reported": False,
                "on_screen_percentage": None,
                "look_away_events": 0,
                "look_away_seconds": 0,
                "no_face_events": 0,
            }

        attentive = min(proctoring.get("attentive_samples", 0), samples)
        return {
            "reported": True,
            "on_screen_percentage": round((attentive / samples) * 100.0, 1),
            "look_away_events": proctoring.get("look_away_events", 0),
            "look_away_seconds": proctoring.get("look_away_seconds", 0),
            "no_face_events": proctoring.get("no_face_events", 0),
        }

    @staticmethod
    def _integrity_penalty(proctoring: dict) -> float:
        """Penalty in points, computed from server-observed frames only.

        The client used to compute this from browser-tracked counters and POST
        the finished number, which made the scoring policy editable in devtools.
        """
        frames = proctoring.get("frames_analysed", 0)
        if frames <= 0:
            return 0.0

        # Only YOLO's verdicts. The look-away term that used to live here was
        # sourced from the server's own coarse gaze estimate; attention is now
        # browser-reported and does not penalise, so it is gone rather than
        # silently reading a field the client supplies.
        penalty = 0.0
        if proctoring.get("phone_frames", 0) > 0:
            penalty += 15.0
        if proctoring.get("multiple_person_frames", 0) > 0:
            penalty += 10.0
        return round(min(30.0, penalty), 1)

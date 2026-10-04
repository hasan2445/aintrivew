import logging
import os

# Quieten native TF/glog chatter before those libraries are imported.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GLOG_minloglevel", "2")

import base64
import io
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

import dotenv
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

dotenv.load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "ml"))

from core import auth, config, database, rate_limit
from core.settings import settings
from api import admin_routes, auth_routes
from ml.extract_text import extract_text_from_file
from models import db_models
from models.schemas import AnswerSubmissionRequest, AttentionReport
from services.prompts import DIFFICULTY_DIRECTIVES
from services.question_generator import (
    EVALUATION_PARSE_FAILURES,
    InterviewSessionManager,
    StaleTurnError,
)

logging.basicConfig(
    level=getattr(logging, str(config.LOG_LEVEL).upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("interviewai")

import cv2

# ---------------------------------------------------------------------------
# Heavy ML models
#
# These were previously constructed at import time, which made the process take
# tens of seconds to boot, allocated GPU/CPU memory in every worker regardless of
# use, and made the module impossible to import in a test or CI environment.
# They are now built on first use and cached.
# ---------------------------------------------------------------------------

# No server-side FaceMesh.
#
# It existed as a backstop: the browser loads its MediaPipe WASM from a CDN and
# can fail to initialise, and a proctoring system that silently stops proctoring
# is worse than one that has none. But YOLO already fills that role and fills it
# from a different failure mode — it counts people, so an empty frame and a
# second person are both caught without it, and the frontend already consults
# its person count when browser tracking goes quiet.
#
# What the second FaceMesh actually contributed was a coarser duplicate of a
# measurement the browser makes better: gaze from nose-in-bounding-box on one
# 320x240 frame every three seconds, against iris position between the eye
# corners on every frame. Its verdicts were recorded and then read by nothing —
# the integrity penalty has only ever come from YOLO. It cost a native
# dependency, a per-request lock, and an inference pass, for counters no one
# looked at.
#
# Face presence is now measured in the browser and corroborated by YOLO's person
# count.


@lru_cache(maxsize=1)
def get_yolo_model():
    import torch
    from ultralytics import YOLO

    weights = BASE_DIR / "ml" / "yolov8n.pt"
    model_path = str(weights) if weights.exists() else "yolov8n.pt"

    # Ultralytics checkpoints are pickles that torch>=2.6 refuses to load under
    # the default weights_only=True. Patch only for the duration of this load
    # instead of disabling the protection process-wide, as the previous code did.
    original_load = torch.load

    def _load_trusted_checkpoint(*args, **kwargs):
        kwargs["weights_only"] = False
        return original_load(*args, **kwargs)

    torch.load = _load_trusted_checkpoint
    try:
        return YOLO(model_path)
    finally:
        torch.load = original_load


@lru_cache(maxsize=1)
def get_elevenlabs_client():
    """Return a configured ElevenLabs client, or None when no key is set.

    There is deliberately no fallback API key: an unset key disables TTS rather
    than silently billing someone else's account.
    """
    if not settings.elevenlabs_api_key:
        return None
    from elevenlabs.client import ElevenLabs

    return ElevenLabs(api_key=settings.elevenlabs_api_key.get_secret_value())


database.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="InterviewAI",
    version="1.0.0",
    debug=settings.debug,
    # Interactive API docs are useful in development but expose the full surface
    # area (and every schema) publicly in production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)

_allowed_origins = settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    # A wildcard origin is incompatible with credentialed requests; browsers
    # reject the combination outright. Only send credentials for a real allowlist.
    allow_credentials="*" not in _allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


session_manager = InterviewSessionManager()


@app.on_event("startup")
async def _warm_models() -> None:
    """Load YOLO in the background so the first frame does not pay for it.

    The loaders stay lazy — that is what keeps ``app.py`` importable in a test
    without the whole ML stack — but nothing warmed them, so the first candidate
    to submit a frame ate the weights read on their request thread while the
    frontend's 3-second timer kept firing. The hook is what is eager here, not
    the functions.

    Only the CV models are warmed. The ElevenLabs client is an HTTP client, not
    a model, and there is nothing else left to load: transcription is done by
    the browser's Web Speech API, so no speech model is resident server-side.
    """
    if os.getenv("SKIP_MODEL_WARMUP", "").lower() in {"1", "true", "yes"}:
        return

    def _load() -> None:
        for name, loader in (("YOLO", get_yolo_model),):
            try:
                loader()
                logger.info("Warmed %s", name)
            except Exception as exc:
                # A missing model must not stop the API from serving.
                logger.warning("Could not warm %s: %s", name, exc)

    threading.Thread(target=_load, name="model-warmup", daemon=True).start()


templates = Jinja2Templates(directory=str(BASE_DIR / "frontend"))
app.mount("/css", StaticFiles(directory=str(BASE_DIR / "frontend" / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(BASE_DIR / "frontend" / "js")), name="js")
app.mount("/pages", StaticFiles(directory=str(BASE_DIR / "frontend" / "pages")), name="pages")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _fail(status_code: int, public_detail: str, exc: Exception, context: str) -> HTTPException:
    """Log the real error, return a message safe to show a client.

    The previous handlers interpolated ``str(e)`` straight into the response,
    which leaked stack-level detail (SQL fragments, file paths, API errors) to
    anyone who could trigger a failure.
    """
    logger.exception("%s failed: %s", context, exc)
    return HTTPException(status_code=status_code, detail=public_detail)


def get_owned_interview(
    session_id: str,
    current_user: db_models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
) -> db_models.InterviewSessionModel:
    """Resolve an interview and confirm the caller owns it.

    Session IDs are UUIDs but were previously the only thing guarding an
    interview's transcript, evaluations and scores. Admins may read any session.
    """
    interview = (
        db.query(db_models.InterviewSessionModel)
        .filter(db_models.InterviewSessionModel.session_id == session_id)
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if interview.user_id != current_user.id and not current_user.is_admin:
        # 404 rather than 403 so the endpoint does not confirm that an
        # unknown-to-this-user session ID exists.
        raise HTTPException(status_code=404, detail="Session not found")
    return interview


def get_live_session(
    session_id: str,
    identity: auth.TokenIdentity = Depends(auth.get_token_identity),
    db: Session = Depends(database.get_db),
):
    """Authorise a live-session request and return the session, from Redis.

    Replaces ``get_owned_interview`` + ``_load_live_session`` on every route
    that was going to read the session anyway. Those two together cost a
    ``users`` row, an ``interviews`` row and a Redis GET per request; at one
    webcam frame every three seconds that was ~800 queries an interview to
    re-answer a question the session blob can answer itself.

    Sessions written before ``user_id`` existed have none, so those fall back to
    the database check rather than being refused. Both paths return 404 for an
    interview that is not the caller's, so the endpoint never confirms that an
    unknown-to-this-user session id exists.

    Note the admin bypass is not carried over. Admin tooling reads finished
    interviews through /api/admin/*, which does read privilege from the
    database; nothing needs an admin to reach into a live session mid-answer.
    """
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Interview session has expired or is no longer available",
        )

    owner_id = getattr(session, "user_id", None)
    if owner_id is None:
        # Legacy session blob: fall back to the interviews row.
        row = (
            db.query(db_models.InterviewSessionModel)
            .filter(db_models.InterviewSessionModel.session_id == session_id)
            .first()
        )
        owner_id = row.user_id if row else None

    if owner_id != identity.id:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


def _load_live_session(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Interview session has expired or is no longer available",
        )
    return session


def _question_payload(question, question_number: int, total_questions: int) -> dict:
    return {
        "question_number": question_number,
        "total_questions": total_questions,
        "category": getattr(question.category, "value", question.category),
        "name": question.name,
        "primary_question": question.primary_question,
        "context": question.context,
        "difficulty_level": getattr(
            question.difficulty_level, "value", question.difficulty_level
        ),
    }


@app.get("/")
async def root(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "InterviewAI - Home"},
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Interview lifecycle
# ---------------------------------------------------------------------------


async def _read_resume_upload(resume: UploadFile) -> bytes:
    """Read an upload while enforcing the extension and size limits."""
    filename = (resume.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    suffix = Path(filename).suffix.lower()
    if suffix not in config.ALLOWED_RESUME_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_RESUME_EXTENSIONS))
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type. Allowed: {allowed}"
        )

    # Read in chunks and abort as soon as the cap is passed, so an oversized
    # upload is never fully buffered in memory.
    limit = config.MAX_UPLOAD_SIZE_BYTES
    chunks: list[bytes] = []
    total = 0
    while chunk := await resume.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {config.MAX_UPLOAD_SIZE_MB} MB.",
            )
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    await resume.seek(0)
    return b"".join(chunks)


@app.post("/api/upload-resume", status_code=201)
async def upload_resume(
    resume: UploadFile = File(...),
    job_role: str = Form(...),
    resume_text: Optional[str] = Form(None),
    difficulty: str = Form("medium"),
    current_user: db_models.User = Depends(rate_limit.upload_rate_limit),
    db: Session = Depends(database.get_db),
):
    """Upload a resume and start an interview session."""
    job_role = (job_role or "").strip()
    if not job_role:
        raise HTTPException(status_code=400, detail="Job role is required")
    if len(job_role) > 128:
        raise HTTPException(status_code=400, detail="Job role is too long")

    difficulty = (difficulty or "medium").strip().lower()
    if difficulty not in DIFFICULTY_DIRECTIVES:
        difficulty = "medium"

    raw = await _read_resume_upload(resume)

    # Client-extracted text is only trusted for PDFs, which is the only format
    # the browser's pdf.js can actually read. handleFileUpload used to run
    # pdf.js over every file: for a .docx it threw, the catch wrote a
    # "Resume PDF: <filename>" placeholder, and that non-empty string was sent
    # and preferred — so the whole interview was generated from a filename while
    # ml/extract_text.py's DOCX path (which walks tables, where resumes keep
    # skills and contact details) was unreachable through the UI.
    suffix = Path(resume.filename or "").suffix.lower()
    client_text_allowed = suffix == ".pdf"

    if client_text_allowed and resume_text and resume_text.strip():
        text_to_use = resume_text.strip()
    else:
        try:
            text_to_use = await run_in_threadpool(
                extract_text_from_file, io.BytesIO(raw), resume.filename
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise _fail(
                400,
                "Could not read that resume. Please upload a text-based PDF or DOCX.",
                exc,
                "Resume text extraction",
            )

    if not text_to_use or not text_to_use.strip():
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from the resume. If it is a scanned "
            "document, please upload a text-based PDF instead.",
        )

    # Bound the prompt sent to the LLM.
    text_to_use = text_to_use[: config.MAX_RESUME_CHARS]

    try:
        session = await run_in_threadpool(
            session_manager.create_session,
            resume_text=text_to_use,
            job_role=job_role,
            resume_name=resume.filename,
            difficulty=difficulty,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise _fail(
            502,
            "Could not generate interview questions right now. Please try again.",
            exc,
            "Question generation",
        )

    if not session.questions:
        session_manager.session_store.delete(session.session_id)
        raise HTTPException(
            status_code=502,
            detail="No interview questions could be generated from this resume.",
        )

    db_interview = db_models.InterviewSessionModel(
        session_id=session.session_id,
        user_id=current_user.id,
        job_role=job_role,
        difficulty=difficulty,
        status="in_progress",
    )
    db.add(db_interview)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        # Fail now rather than twenty minutes from now. Authorisation no longer
        # depends on this row — get_live_session reads user_id off the session
        # blob — so the interview would run to completion without it, and then
        # 404 at the end: /comprehensive-report and /end both key their UPDATE
        # on a row that was never written. Deleting the session makes the
        # failure immediate and visible instead of silent until the report.
        session_manager.session_store.delete(session.session_id)
        raise _fail(500, "Could not start the interview session.", exc, "Interview persistence")

    total = len(session.questions)
    questions = [_question_payload(q, i + 1, total) for i, q in enumerate(session.questions)]
    first_question = session_manager.get_current_question(session.session_id)

    return JSONResponse(
        {
            "status": "success",
            "session_id": session.session_id,
            "total_questions": total,
            "job_role": job_role,
            "difficulty": difficulty,
            "questions": questions,
            "turn": session.turn,
            "first_question": _question_payload(first_question, 1, total)
            if first_question
            else None,
        },
        status_code=201,
    )


@app.get("/api/session/{session_id}/question")
async def get_current_question(
    session_id: str,
    session=Depends(get_live_session),
):
    """Get the current question for a session."""
    current_question = session_manager.get_current_question(session_id)
    if not current_question:
        raise HTTPException(status_code=400, detail="Interview already completed")

    return JSONResponse(
        {
            "status": "success",
            "question": _question_payload(
                current_question,
                session.current_question_index + 1,
                len(session.questions),
            ),
        }
    )


@app.post("/api/session/{session_id}/answer")
async def submit_answer(
    session_id: str,
    request: AnswerSubmissionRequest,
    session=Depends(get_live_session),
    identity: auth.TokenIdentity = Depends(rate_limit.answer_rate_limit),
):
    """Submit an answer to the current question or follow-up."""

    try:
        result = await run_in_threadpool(
            session_manager.submit_answer, session_id, request.answer, request.turn
        )
    except StaleTurnError as exc:
        # A duplicate or replayed submission, rejected before either LLM call.
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise _fail(
            502,
            "Could not evaluate that answer right now. Please try again.",
            exc,
            "Answer submission",
        )

    return JSONResponse(
        {
            "status": "success",
            "action": result["action"],
            "evaluation": result["evaluation"],
            "follow_up_question": result.get("follow_up_question"),
            "followup_depth": result.get("followup_depth", 0),
            "next_question": result.get("next_question"),
            "next_question_available": result.get("next_question_available", False),
            # Read off the session object submit_answer already had in hand; this
            # used to cost a third Redis GET per answer.
            "interview_complete": result.get("interview_complete", False),
            "turn": result.get("turn", 0),
        }
    )


@app.post("/api/session/{session_id}/next-question")
async def next_question(
    session_id: str,
    session=Depends(get_live_session),
):
    """Skip remaining follow-ups and move to the next primary question."""

    try:
        has_next = await run_in_threadpool(
            session_manager.proceed_to_next_question, session_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise _fail(500, "Could not advance the interview.", exc, "Next question")

    if not has_next:
        return JSONResponse(
            {"status": "success", "interview_complete": True, "next_question": None}
        )

    next_q = session_manager.get_current_question(session_id)
    updated = session_manager.get_session(session_id) or session
    if next_q is None:
        return JSONResponse(
            {"status": "success", "interview_complete": True, "next_question": None}
        )

    return JSONResponse(
        {
            "status": "success",
            "interview_complete": False,
            "next_question": _question_payload(
                next_q, updated.current_question_index + 1, len(updated.questions)
            ),
        }
    )


@app.get("/api/session/{session_id}/progress")
async def get_progress(
    session_id: str,
    session=Depends(get_live_session),
):
    """Get interview progress."""
    try:
        progress = session_manager.get_interview_progress(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as exc:
        raise _fail(500, "Could not load interview progress.", exc, "Progress")

    return JSONResponse({"status": "success", "progress": progress})


@app.get("/api/session/{session_id}/report")
async def get_report(
    session_id: str,
    session=Depends(get_live_session),
):
    """Get the complete interview report."""
    try:
        report = session_manager.get_interview_report(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as exc:
        raise _fail(500, "Could not build the interview report.", exc, "Report")

    return JSONResponse({"status": "success", "report": report})


@app.get("/api/health")
async def health_check():
    """Health check endpoint.

    Exposes the evaluation parse-failure counter. That fallback path (a silent
    hardcoded "good" rating when the model returns unparseable JSON) previously
    produced one ``logger.warning`` and nothing else — there was no way to know
    from outside the process that it was firing at all.
    """
    return JSONResponse(
        {
            "status": "healthy",
            "service": "InterviewAI",
            "session_store": "redis" if session_manager.session_store.client else "memory",
            "evaluation_parse_failures": EVALUATION_PARSE_FAILURES["count"],
        }
    )


@app.get("/api/session/{session_id}/scores")
async def get_interview_scores(
    session_id: str,
    session=Depends(get_live_session),
):
    """Get interview scores and metrics."""
    try:
        scores = session_manager.calculate_interview_score(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as exc:
        raise _fail(500, "Could not calculate interview scores.", exc, "Scores")

    return JSONResponse({"status": "success", "scores": scores})


@app.get("/api/session/{session_id}/improvement-plan")
async def get_improvement_plan(
    session_id: str,
    session=Depends(get_live_session),
):
    """Get a personalised improvement plan based on interview performance."""
    try:
        plan = await run_in_threadpool(
            session_manager.generate_improvement_plan, session_id
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as exc:
        raise _fail(500, "Could not build an improvement plan.", exc, "Improvement plan")

    return JSONResponse({"status": "success", "improvement_plan": plan})


@app.get("/api/session/{session_id}/comprehensive-report")
async def get_comprehensive_report(
    session_id: str,
    interview: db_models.InterviewSessionModel = Depends(get_owned_interview),
    db: Session = Depends(database.get_db),
):
    """Get the full interview report with scores, analysis and improvements.

    Built from the live Redis session every time. The report is not persisted:
    an interview always finishes inside the session's 6-hour TTL, so the window
    in which a candidate reads their report is the same window in which the
    session is still alive. After the TTL this returns 404 and the durable
    record is the score and status on the interview row.

    The cost of not caching it is one improvement-plan LLM call per view, and a
    plan that is re-written (and so worded differently) on every refresh.
    """
    session = _load_live_session(session_id)

    try:
        report = session_manager.get_interview_report(session_id)
        scores = session_manager.calculate_interview_score(session_id)
        improvement_plan = await run_in_threadpool(
            session_manager.generate_improvement_plan, session_id
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found")
    except Exception as exc:
        raise _fail(500, "Could not build the interview report.", exc, "Comprehensive report")

    comprehensive_report = {
        "session_id": session_id,
        "resume_name": session.resume_name,
        "job_role": session.job_role,
        "questions_answered": len(session.answers),
        "total_questions": len(session.questions),
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "metrics": scores,
        "qa_pairs": report.get("qa_pairs", []),
        "improvement_plan": improvement_plan,
    }

    try:
        interview.status = "completed"
        interview.score = scores.get("overall_score", 0.0)
        db.commit()
    except SQLAlchemyError as exc:
        # Report generation succeeded; persisting the score is best-effort.
        db.rollback()
        logger.warning("Could not persist score for %s: %s", session_id, exc)

    return JSONResponse({"status": "success", "comprehensive_report": comprehensive_report})


@app.post("/api/session/{session_id}/attention")
async def report_attention(
    session_id: str,
    report: AttentionReport,
    session=Depends(get_live_session),
    identity: auth.TokenIdentity = Depends(rate_limit.answer_rate_limit),
):
    """Record the browser's attention measurements for this interview.

    Deliberately client-reported. The browser runs MediaPipe FaceMesh on every
    frame at camera rate and computes gaze from iris position between the eye
    corners; the server previously ran a second, coarser estimate (nose position
    within the face bounding box) on one 320x240 frame every three seconds,
    purely so the number would be server-attested. Nothing in this product acts
    on that number adversarially, so the better measurement is worth more than
    the weaker attestation.

    These values are presented as feedback and never touch the integrity
    penalty, which stays sourced from the server's own YOLO verdicts.

    Totals are cumulative, so they are written with HSET rather than HINCRBY —
    a resend settles on the same value instead of inflating it.
    """
    try:
        session_manager.session_store.set_proctoring(
            session_id,
            {
                "attention_samples": report.samples,
                "attentive_samples": min(report.attentive_samples, report.samples),
                "look_away_events": report.look_away_events,
                "look_away_seconds": report.look_away_seconds,
                "no_face_events": report.no_face_events,
            },
        )
    except Exception as exc:
        # Feedback data is supplementary; never fail the request over it.
        logger.warning("Could not record attention for %s: %s", session_id, exc)
        return JSONResponse({"status": "error"}, status_code=202)

    return JSONResponse({"status": "success"})


@app.post("/api/session/{session_id}/end")
async def end_session(
    session_id: str,
    identity: auth.TokenIdentity = Depends(auth.get_token_identity),
    db: Session = Depends(database.get_db),
):
    """Mark an interview completed and store the server's own final score.

    This endpoint used to take ``{"score": <float 0-100>}`` from the browser and
    write it straight to ``interviews.score``, overwriting the number
    ``/comprehensive-report`` had just computed from the real evaluations. The
    range check (ge=0, le=100) validated the shape of a value that should never
    have crossed the trust boundary at all — anyone could POST a 100. The score
    is now computed here, from evaluations and server-observed proctoring only.

    It reads no rows. Ownership used to cost a ``users`` lookup and an
    ``interviews`` lookup before a write that changed, in the normal flow,
    nothing at all — the report endpoint runs first and has already stored the
    identical status and score, so SQLAlchemy emitted no UPDATE. Scoping the
    UPDATE to ``user_id`` makes the write its own authorisation check: a row
    that is not the caller's is not matched, and a zero row count is the 404.

    Consequence: an admin can no longer end another user's interview. Nothing
    does that — admin tooling reads finished interviews through /api/admin/*.
    """
    session = session_manager.get_session(session_id)

    final_score = None
    if session:
        session.status = "completed"
        session_manager.session_store.set(session_id, session)
        try:
            scores = session_manager.calculate_interview_score(session_id)
            final_score = scores.get("overall_score")
        except Exception as exc:
            logger.warning("Could not compute final score for %s: %s", session_id, exc)

    # Leave `score` alone when there is no live session to compute one from,
    # rather than overwriting a stored number with a guess.
    values = {"status": "completed"}
    if final_score is not None:
        values["score"] = final_score

    try:
        updated = (
            db.query(db_models.InterviewSessionModel)
            .filter(
                db_models.InterviewSessionModel.session_id == session_id,
                db_models.InterviewSessionModel.user_id == identity.id,
            )
            .update(values, synchronize_session=False)
        )
        if not updated:
            db.rollback()
            # 404 rather than 403, matching every other session route: the
            # endpoint does not confirm that an unknown-to-this-user id exists.
            raise HTTPException(status_code=404, detail="Session not found")
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _fail(500, "Could not end the interview session.", exc, "End session")

    return {"status": "success", "score": final_score}


# ---------------------------------------------------------------------------
# Proctoring / media
# ---------------------------------------------------------------------------

_EMPTY_FRAME_RESPONSE = {
    "status": "error",
    "object_analysis": {"person_count": 1, "phone_detected": False, "warnings": []},
    "cheating_detected": False,
    "warnings": [],
}

_MAX_FRAME_BYTES = 8 * 1024 * 1024


async def _read_bounded(upload: UploadFile, limit: int, label: str) -> bytes:
    data = await upload.read()
    if len(data) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"{label} exceeds the {limit // (1024 * 1024)} MB limit",
        )
    return data


def _decode_frame(frame_bytes: bytes):
    nparr = np.frombuffer(frame_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        return None
    return cv2.flip(img, 1)


_SUSPICIOUS_CLASSES = {
    "cell phone",
}


def _analyse_objects(frame_img, min_confidence: float = 0.45) -> dict:
    result = {
        "person_count": 1,
        "phone_detected": False,
        "prohibited_objects": [],
        "status": "success",
        "warnings": [],
    }
    try:
        model = get_yolo_model()
        yolo_results = model(frame_img, verbose=False, conf=min_confidence)

        person_count = 0
        phone_detected = False
        prohibited: list[str] = []
        warnings: list[str] = []

        for detection in yolo_results or []:
            if detection.boxes is None:
                continue
            for box in detection.boxes:
                if float(box.conf[0]) < min_confidence:
                    continue
                cls = int(box.cls[0])
                class_name = str(model.names.get(cls, "unknown")).lower()

                if "person" in class_name:
                    person_count += 1
                elif class_name in _SUSPICIOUS_CLASSES or "phone" in class_name:
                    if "phone" in class_name:
                        phone_detected = True
                    if class_name not in prohibited:
                        prohibited.append(class_name)
                        warnings.append(f"Suspicious object detected: {class_name.upper()}")

        if person_count > 1:
            warnings.append(f"Multiple persons detected ({person_count})")
        elif person_count == 0:
            warnings.append("No person detected in frame")

        # Report the real count. This used to be max(1, person_count), an
        # artificial floor that made "nobody in frame" structurally
        # unrepresentable — so the server had no way to notice a candidate who
        # had left, and the browser's MediaPipe was the only thing that could.
        # That mattered once the browser overlay turned out to fall back to a
        # simulator when its CDN-loaded WASM fails to initialise: the fake
        # overlay reports tracking forever and never flags an absent face.
        result["person_count"] = person_count
        result["phone_detected"] = phone_detected
        result["prohibited_objects"] = prohibited
        result["warnings"] = warnings
    except Exception as exc:
        logger.warning("Object detection error: %s", exc)
        result["status"] = "error"
    return result


def _analyse_frame_sync(frame_bytes: bytes) -> dict:
    frame_img = _decode_frame(frame_bytes)
    if frame_img is None:
        return dict(_EMPTY_FRAME_RESPONSE)

    object_result = _analyse_objects(frame_img)

    cheating_detected = False
    warnings: list[str] = []

    if object_result.get("phone_detected"):
        cheating_detected = True
        warnings.append("Phone detected in frame")

    person_count = object_result.get("person_count", 1)
    if person_count > 1:
        cheating_detected = True
        warnings.append("Multiple persons detected")
    elif person_count == 0:
        # Not flagged as cheating on a single frame: YOLO at 320x240 and 0.45
        # confidence can miss a person who is simply badly lit. The frontend
        # requires consecutive empty frames before it warns.
        warnings.append("No person detected")

    return {
        "status": "success",
        "object_analysis": object_result,
        "cheating_detected": cheating_detected,
        "warnings": warnings,
    }


def _record_proctoring(session_id: str, result: dict) -> None:
    """Persist the server's own object-detection verdict against the session.

    Only YOLO's findings are recorded here, and they are the only proctoring
    signals that remain server-verified: a phone in frame and a second person.
    Attention (gaze, face presence) is measured in the browser and submitted
    separately — see /api/session/{id}/attention — because the browser's
    iris-based estimate is strictly better than anything computable from one
    320x240 frame every three seconds, and nothing here depends on it being
    server-attested.

    Counters go to a separate Redis hash via HINCRBY so a frame arriving
    mid-answer cannot clobber the session blob.
    """
    objects = result.get("object_analysis") or {}
    fields = {
        "frames_analysed": 1,
        "phone_frames": 1 if objects.get("phone_detected") else 0,
        "multiple_person_frames": 1 if objects.get("person_count", 1) > 1 else 0,
        "no_person_frames": 1 if objects.get("person_count", 1) == 0 else 0,
    }
    try:
        session_manager.session_store.increment_proctoring(session_id, fields)
    except Exception as exc:
        # Proctoring is supplementary; never fail a frame over it.
        logger.warning("Could not record proctoring for %s: %s", session_id, exc)


@app.post("/api/analyze-frame")
async def analyze_frame(
    frame: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    current_user: db_models.User = Depends(rate_limit.frame_rate_limit),
    db: Session = Depends(database.get_db),
):
    """Analyse a video frame for face and object detection.

    ``session_id`` binds the frame to an interview the caller owns, so the
    verdict is recorded server-side and can back the integrity penalty. It stays
    optional so the endpoint remains usable standalone, but an unbound frame is
    analysed and forgotten.
    """
    frame_bytes = await _read_bounded(frame, _MAX_FRAME_BYTES, "Frame")
    if not frame_bytes:
        return JSONResponse(dict(_EMPTY_FRAME_RESPONSE))

    if session_id:
        # Same ownership rule as every other live-session route, read from the
        # session blob rather than the interviews row: this fires every three
        # seconds per candidate and was the app's largest source of database
        # traffic.
        get_live_session(session_id=session_id, identity=current_user, db=db)

    try:
        # CPU-bound inference must not run on the event loop; doing so blocked
        # every other request for the duration of the model call.
        result = await run_in_threadpool(_analyse_frame_sync, frame_bytes)
    except Exception as exc:
        logger.exception("Frame analysis failed: %s", exc)
        payload = dict(_EMPTY_FRAME_RESPONSE)
        payload["warnings"] = ["Analysis unavailable"]
        return JSONResponse(payload)

    if session_id:
        _record_proctoring(session_id, result)

    return JSONResponse(result)


@app.post("/api/detect-objects")
async def detect_objects(
    frame: UploadFile = File(...),
    current_user: db_models.User = Depends(rate_limit.frame_rate_limit),
):
    """Detect objects (people, phones) in a video frame."""
    frame_bytes = await _read_bounded(frame, _MAX_FRAME_BYTES, "Frame")

    def _run():
        img = _decode_frame(frame_bytes)
        if img is None:
            return None
        return _analyse_objects(img, min_confidence=0.50)

    try:
        result = await run_in_threadpool(_run)
    except Exception as exc:
        raise _fail(500, "Object detection failed", exc, "Object detection")

    if result is None:
        return JSONResponse({"status": "error", "message": "Invalid frame"}, status_code=400)

    return JSONResponse({"status": "success", "object_detection": result})


_VOICES = [
    {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "Default English", "language": "en"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "language": "en"},
    {"id": "MF3mGyEYCHltNiPSt4nC", "name": "Elli", "language": "en"},
]
_VOICE_IDS = {v["id"] for v in _VOICES}


@app.post("/api/generate-speech")
async def generate_speech(
    text: str = Form(...),
    voice_id: str = Form("JBFqnCBsd6RMkjVDRZzb"),
    current_user: db_models.User = Depends(rate_limit.tts_rate_limit),
):
    """Generate speech from text using ElevenLabs TTS."""
    client = get_elevenlabs_client()
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Text-to-speech is not configured. Set ELEVENLABS_API_KEY to enable it.",
        )

    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(text) > config.MAX_TTS_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds the {config.MAX_TTS_CHARS} character limit",
        )
    if not _VOICE_IDS or voice_id not in _VOICE_IDS:
        raise HTTPException(status_code=400, detail="Unknown voice_id")

    def _run():
        audio = client.text_to_speech.convert(
            voice_id=voice_id, text=text, model_id="eleven_multilingual_v2"
        )
        return base64.b64encode(b"".join(audio)).decode("utf-8")

    try:
        audio_base64 = await run_in_threadpool(_run)
    except Exception as exc:
        raise _fail(502, "Speech generation failed", exc, "Speech generation")

    return JSONResponse({"status": "success", "audio": audio_base64, "format": "mp3"})


@app.get("/api/tts-voices")
async def get_tts_voices():
    """Get available TTS voice IDs."""
    return JSONResponse({"status": "success", "voices": _VOICES})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

# InterviewAI

An AI-powered mock interview platform. It reads a candidate's résumé, generates
questions grounded in what that résumé actually shows, asks adaptive follow-ups,
evaluates each answer, and produces a scored report — while a webcam feed is
checked for a phone or a second person in frame.

A single FastAPI process serves both the API and the frontend. There is no
separate frontend server, no worker queue and no message broker.

---

## How it works

```
upload résumé + role  ──▶  setup (difficulty)  ──▶  one Groq call generates 8–12 questions
                                                              │
                                                              ▼
          report  ◀──  answer loop: evaluate ─▶ follow up or advance
```

Three stores, each with one job:

| Store | Holds |
|---|---|
| **Redis** | The live interview — questions, answers, evaluations, turn counter. 6-hour TTL. |
| **Postgres** | Who owns the interview, and the finished report once generated. |
| **Browser** | Real-time UX: the camera overlay, live transcript, attention measurement. |

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI + Uvicorn | Async routing, Pydantic validation, `run_in_threadpool` for blocking ML calls |
| LLM | Groq · `openai/gpt-oss-120b` (override with `GROQ_MODEL`) | Model id is configurable, not hardcoded: the previous `llama-3.3-70b-versatile` was decommissioned by Groq and surfaced only as a 502 with `model_not_found` buried in the log |
| Live state | Redis | Every answer rewrites the whole session blob 30–40 times a session — a `SET` that expires itself, not a large row update |
| Records | Postgres + SQLAlchemy 2.x | Ownership and finished reports |
| Auth | JWT (HS256) + bcrypt | Per-request DB lookup so `is_admin` is never trusted from the token |
| Vision | YOLOv8n | Phone and extra-person detection — the only server-verified integrity signals |
| Attention | Browser MediaPipe FaceMesh | Iris-based gaze at ~12 fps, in the tab. The only face detector in the system. Reported as feedback, never scored |
| Speech in | Web Speech API | Streaming recognition, written live into the answer box. Chrome/Edge only — other browsers type. Note the browser relays audio to its own vendor's service; it is not on-device |
| Speech out | ElevenLabs | Returns 503 when no key is set — no fallback key |
| Frontend | Vanilla JS | One `state` object, a `switch` router over `state.step`, `innerHTML` rendering with explicit escaping |

**No embeddings, no vector store, no retrieval.** Evaluation is a single
stateless prompt containing the question and the answer.

---

## Quick start

```bash
git clone https://github.com/your-username/InterviewAI.git
cd InterviewAI

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# create .env with DATABASE_URL and GROQ_API_KEY (see Configuration below)
uvicorn app:app --reload --port 8000
```

Open <http://localhost:8000>.

YOLO weights ship in the repo at `ml/yolov8n.pt` — no download step. No
speech model is downloaded: transcription happens in the browser.

Redis is optional in development: without it the app falls back to a
process-local dict and logs a warning. In production an unreachable Redis
**fails the boot** — the fallback is single-worker only and would silently lose
interviews across workers.

### Tests

```bash
python -m pytest        # 45 tests, no network, no models loaded
```

---

## Configuration

Everything is read from `.env` in the repo root. There is no template file —
this is the list.

| Variable | | |
|---|---|---|
| `DATABASE_URL` | **required** | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@localhost:5432/interviewai` |
| `GROQ_API_KEY` | **required** | Question generation and answer evaluation |
| `GROQ_MODEL` | optional | Defaults to `openai/gpt-oss-120b` |
| `JWT_SECRET_KEY` | required in production | 32+ chars. Unset in dev = a random per-process value, so tokens die on restart |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | optional | Defaults to 480. Do not lower to 60 — that is inside the length of a real interview, and expiry mid-session logs the candidate out and strands the Redis session |
| `ELEVENLABS_API_KEY` | optional | TTS. Unset ⇒ `/api/generate-speech` returns 503 |
| `REDIS_URL` | optional in dev | Without it, an in-process dict; single worker only |
| `SESSION_TTL_SECONDS` | optional | Defaults to 21600 (6 h) |
| `ENVIRONMENT` | optional | `development` (default) or `production` |
| `DEBUG`, `LOG_LEVEL` | optional | `false`, `INFO` |
| `CORS_ALLOW_ORIGINS` | optional | Comma-separated. `*` is rejected in production |
| `MAX_UPLOAD_SIZE_MB` | optional | Defaults to 10 |

Note the exact spelling `ELEVENLABS_API_KEY` — no underscore after `ELEVEN`.
A misspelt key is not an error: `get_elevenlabs_client()` returns `None`,
`/api/generate-speech` returns 503, and the frontend quietly falls back to the
browser's built-in `speechSynthesis` voice.

Configuration is validated at import, and a misconfigured production run
**refuses to start** rather than running quietly insecure. With
`ENVIRONMENT=production`, the app will not boot if:

- `JWT_SECRET_KEY` is missing, weak, or under 32 characters
- `DEBUG=true`
- `CORS_ALLOW_ORIGINS` is `*`
- Redis is unreachable

In development the JWT secret defaults to a *per-process random value*, so
tokens do not survive a restart. That is deliberate — it makes a well-known
signing key impossible to ship by accident.

---

## API

**Auth** — `POST /api/auth/signup` · `POST /api/auth/login` ·
`POST /api/auth/refresh` · `GET /api/auth/me`

**Interview** — `POST /api/upload-resume` ·
`POST /api/session/{id}/answer` · `GET /api/session/{id}/comprehensive-report` ·
`POST /api/session/{id}/end` · `POST /api/session/{id}/attention`

**Media** — `POST /api/analyze-frame` ·
`POST /api/generate-speech`

**Ops** — `GET /api/health` (also reports the session-store mode and the
evaluation parse-failure counter)

Every `/api/session/{id}/*` route depends on `get_owned_interview`, which
returns **404 rather than 403** when the caller does not own the session — 403
would confirm the ID exists and turn the endpoint into an enumeration oracle.

All endpoints that cost money or CPU are rate-limited: login, signup, upload,
answer, frame analysis and TTS.

---

## Design decisions worth knowing

**The final score is computed server-side and only server-side.**
`POST /api/session/{id}/end` takes no request body. The score is derived from
the real per-answer evaluations plus YOLO's own frame verdicts, as a weighted
percentage over the components that could actually be measured.

**Face tracking runs only in the browser.** MediaPipe FaceMesh, throttled to
~12 fps, estimates gaze from iris position between the eye corners — a better
measurement than anything recoverable from one 320×240 JPEG every three seconds,
and it tracks duration, which frame counts cannot. There is no server-side
FaceMesh: it duplicated this measurement more coarsely, its verdicts were
recorded and read by nothing, and YOLO's person count already covers the case it
existed for — the browser's CDN-loaded WASM failing to initialise. Because
attention is client-sourced it is presented as feedback and does not grade
anyone. The integrity penalty is sourced only from YOLO.

**Answer submissions are idempotent.** Each carries a turn token; a replayed or
duplicated submission is rejected with a 409 *before* either LLM call, rather
than two read-modify-writes silently losing an answer.

**Unparseable evaluations are excluded from the score.** When the model returns
JSON that cannot be parsed, the evaluation is tagged `unscored` — the fallback
rating still drives interview flow, but the placeholder value never inflates the
final number.

**A turn is dominated by the LLM, not by anything local.** Measured medians on an
M2 CPU: evaluation 7.7 s, follow-up generation 10.1 s, TTS 1.3 s, transcription
0 s (browser). Those two LLM calls run *sequentially* inside one
`run_in_threadpool`, so a follow-up turn is ~19 s and an advance turn ~8.9 s.
The follow-up call only needs the evaluation's `follow_up_direction`, not its
full body, so running the two concurrently is the obvious next win — it is not
done yet.

**Transcription is browser-only, on purpose.** No audio ever reaches this
application's server — but "browser-only" means the app never handles it, not
that it stays on the device: Chrome's `webkitSpeechRecognition` streams the
microphone to Google's speech service and Edge streams it to Microsoft's. That
is worth stating plainly to a candidate. A server-side faster-whisper
pass used to re-transcribe the recorded clip and overwrite the live text. It was
supposed to be gated on quality, but the gate read `info.language_probability` —
the model's confidence that the audio is *English*, which sits at 1.000 on
ordinary speech — so it never rejected anything. The result was ~6.7 s of blocking
CPU per answer (measured, `small`/int8, 35 s clip, RTF 0.19) to replace text that
was already correct. Removed. The cost is that Safari and Firefox have no voice
input and candidates there type.

**Résumé files are never written to disk.** They are parsed in memory and
discarded.

---

## Running it

There is no Docker setup in the repo — it was removed deliberately; this is run
locally, from the Quick start above. Two constraints are worth knowing before
that changes:

- **CPU-only torch.** PyPI's default Linux wheel pulls ~2 GB of NVIDIA CUDA
  packages that nothing here uses. `requirements.txt` already points torch at
  PyTorch's CPU index for this reason.
- **Single process.** Sessions and rate limits live in Redis, so multiple
  workers would be *correct*, but each one loads its own copy of torch and YOLO.
  That is a memory ceiling, not a correctness one.

Needs ~2 GB RAM, nearly all of it torch and YOLO.

---

## Known limitations

Stated plainly rather than discovered later.

1. **Prompt injection is unmitigated.** Résumé text goes verbatim into the
   generation prompt. Field normalisation and output escaping contain the blast
   radius, but a crafted résumé can still steer question content.
2. **Escaping is per-call-site.** The known XSS sinks are fixed; the pattern that
   allowed them is unchanged until rendering goes through an escape-by-default
   tagged template.
3. **Proctoring can be defeated by silence.** A client can stop uploading frames.
   The scoring *policy* is not client-controlled, but detecting a quiet client
   needs an expected-frame heartbeat.
4. **No migrations.** `create_all()` builds the schema on first boot; a later
   schema change will not apply to a live table.
5. **Minimal observability.** One parse-failure counter on `/api/health`. No
   metrics, no structured logs, no alerting.
6. **Score weights are a judgement, not a calibration.** They are defensible but
   were chosen, not derived from outcome data — and since communication,
   confidence and résumé alignment are all derived from the technical score, the
   effective weight on technical performance is far higher than its nominal 0.35.

---

## Repository layout

```
app.py                    FastAPI app, routes, YOLO/TTS handlers
api/                      auth and admin routers
core/                     settings, auth, database, Redis store, rate limiting
models/                   SQLAlchemy tables and Pydantic schemas
services/                 question generation, prompts, LLM JSON recovery
ml/extract_text.py        PDF/DOCX text extraction (walks tables)
ml/*.py                   standalone webcam/mic prototypes, not imported
frontend/                 vanilla JS SPA served by the same process
tests/                    45 tests — state machine, evaluation parsing, JSON recovery
```

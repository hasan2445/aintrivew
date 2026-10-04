# InterviewAI — Notes

## Proctoring pipeline (how video is handled)

1. The webcam video is not sent as a whole video file.

2. The frontend uses browser APIs to access the user's webcam and microphone
   (`navigator.mediaDevices.getUserMedia`, `frontend/pages/interview.js:16`).

3. Before sending anything to the server, the frontend runs a lightweight AI model called MediaPipe Face Mesh directly in the browser using JavaScript
   (loaded from CDN in `frontend/index.html:20-21`, initialised in `frontend/pages/interview.js:51`).

   • It analyzes the live video locally to map the user's face in real-time.

   • It calculates the position of the eyes and irises to detect if the user is looking away from the screen.

   • Because this happens in the browser, it requires no network transfer and provides instant visual feedback (like drawing the green/red bounding boxes around the face).

4. At every 3rd second, the browser takes a snapshot of the current webcam video frame and sends it (`setInterval(..., 3000)` in `startFrameAnalysis`, `frontend/pages/interview.js:652-743`). All the movement that happened between 0.1 and 2.9 seconds is completely ignored by the backend — only the in-browser Face Mesh sees it continuously.

5. The snapshot is drawn onto a 320×240 offscreen canvas and converted to JPEG (quality 0.6) before upload to `POST /api/analyze-frame`.

6. YOLO and Face Mesh accept the image and calculate using pixels (the server decodes the JPEG back into a pixel array before inference).

7. YOLO and Face Mesh use CNNs for reading and processing pixels.

8. Face Mesh is a specific Artificial Intelligence model designed to map the exact geometry of a human face.

9. MediaPipe (The Framework / The Toolbox), Face Mesh (The Model / The Tool).

---

## ML scripts

### 1. `face_detection.py`

**What it is:** A Python script using OpenCV and Google's MediaPipe Face Mesh.

**How it works:** It turns on the webcam, plots the 3D grid on the face, and constantly tracks the X/Y coordinates of the user's nose compared to the edges of their face.

**Why you used it:**

• **To detect "Looking Away":** By doing math on the nose position, the script knows if the user turns their head strongly left or right (ratio < 0.25 or > 0.75). It triggers a `"PLEASE LOOK FORWARD"` warning if they look away for more than 2 seconds (`LOOK_AWAY_TIME = 2`) — likely reading from a script.

• **To detect "Face Missing":** If the candidate leaves the camera view.

• **To detect "Multiple People":** If a friend sits next to them to help with answers.

### 2. `object_detection.py` and `yolov8n.pt` (YOLO)

**What it is:** A script running YOLOv8 (You Only Look Once), which is one of the fastest and most powerful AI object recognition models in the world. `yolov8n.pt` is the actual downloaded "brain" (weights file) that YOLO uses to recognize objects.

**How it works:** It scans the webcam video and looks for specific classes of objects out of the 80 things it is trained to know.

**Why you used it:**

• **Anti-Cheating (Phones):** The script specifically filters for an object called `"cell phone"`. If it sees one, it draws a red box and flashes `"CELL PHONE DETECTED"`.

• **Backup Multi-person detection:** It also counts how many `"person"` objects are in the frame to double-check that the candidate is alone.

### 3. `realtimetrans.py` (Real-Time Transcription)

**What it is:** An advanced audio processing script that uses two AI models: Silero VAD (Voice Activity Detection) and Faster Whisper (OpenAI's speech-to-text model).

**How it works:** It listens to the microphone in real-time. The VAD model checks if the person is actively speaking or just breathing/silent. When they speak, Whisper instantly turns their voice into English text.

**Why you used it:**

• **To capture the candidate's answers:** You use this so the candidate can answer interview questions by talking naturally instead of typing.

• **Smart Silence Detection:** You use Silero VAD so the system knows when the candidate has finished answering. If there are 7 seconds of silence (`SILENCE_TIMEOUT = 7`), the script automatically prints `"✅ Candidate finished speaking"` and stops recording, making the interview feel like a natural conversation.

### 4. `tts.py` (Text-to-Speech)

**What it is:** A script connecting to the ElevenLabs API, which is currently the industry standard for ultra-realistic, human-sounding AI voices.

**How it works:** You send it a text string (like `"tell me about your experience?"`), and it sends back an `.mp3` file of a lifelike voice speaking that sentence (`eleven_multilingual_v2`).

**Why you used it:**

• **To create the AI Interviewer:** Instead of the candidate just reading text on a screen, you use ElevenLabs to actually "speak" the interview questions out loud, making the application feel like a real Zoom interview with a human recruiter.

---

## Results page

Core Strengths
`${strengthsHtml}`

Growth Opportunities
`${weaknessesHtml}`

(`frontend/pages/results.js:69-74` builds the markup, rendered at `results.js:225-239`.)

---

## What Happens After an Interview Session Is Created?

When the client finishes the resume-upload step (`POST /api/upload-resume`), the server does a few things in sequence and then the interview proceeds through a well-defined lifecycle.

| Step | What the server does | Where in the code |
|---|---|---|
| **1 Session creation** | Extracts the raw text from the uploaded file (or uses the supplied `resume_text`). Calls `InterviewSessionManager.create_session()`. Inside `create_session()` a new `InterviewSession` Pydantic model is built: unique `session_id`, parsed profile, a list of generated interview questions, an empty memory buffer, etc. The freshly built session is persisted in Redis via `RedisSessionStore.set(session_id, session)`. | `app.py` → `upload_resume` (lines 290-393) → `services/question_generator.py` → `InterviewSessionManager.create_session` (lines 319-341) → `core/redis_session_store.py` (`set`, line 47) |
| **2 DB record** | A minimal row is inserted into the relational database (`InterviewSessionModel`) so the UI can list the interview later and store final scores. | `app.py` → after the session is built, `db_interview = db_models.InterviewSessionModel(...)` (lines 358-377) |
| **3 Return payload** | The API returns a JSON object that contains: • `session_id` • `total_questions` • `job_role` and extracted profile • All questions pre-formatted for the front-end UI • The first question (so the UI can show it immediately) | `app.py` → `return JSONResponse({...})` (lines 379-393) |
| **4 Front-end displays the first question** | The client receives the response, stores the `session_id`, shows the first question UI, and begins the interview loop. | Front-end (`frontend/pages/*.js`) consumes `/api/upload-resume` response |
| **5 Answer submission** | When the user submits an answer, the front-end calls `POST /api/session/{session_id}/answer`. The server: Retrieves the session from Redis (`session_manager.get_session`). Saves the answer (creates a `CandidateAnswer` object) and appends it to `session.answers`. Runs the LLM evaluator (`InterviewQuestionGenerator.evaluate_answer`). Decides whether to ask a follow-up (based on the evaluation rating and current follow-up depth) or move to the next primary question. If a follow-up is needed, it generates one with `generate_followup` and stores a `FollowUpQuestion` record. Updates the Redis entry (`session_store.set`) so the state is kept across requests. | `app.py` → `submit_answer` (lines 418-457) → `InterviewSessionManager.submit_answer` (lines 357-525) |
| **6 Follow-up vs. next question** | **Follow-up:** The response contains `action: "follow_up"` and the generated follow-up question. The UI asks the user again, staying on the same primary question. **Next question:** When follow-ups are finished or the rating is high enough, `action: "next_question"` is returned, `session.current_question_index` is incremented, and the UI receives the next primary question. | Same as step 5 (the `result` dict built in `submit_answer`) |
| **7 Skipping follow-ups** | The optional endpoint `POST /api/session/{session_id}/next-question` can be called to force-skip remaining follow-ups and move to the next primary question. | `app.py` → `next_question` (lines 459-497) |
| **8 Progress tracking** | The UI may poll `/api/session/{session_id}/progress` to get a percent-complete view. | `app.py` → `get_progress` (lines 499-514) |
| **9 Interview end** | When all primary questions are exhausted, the client calls `/api/session/{session_id}/end`, which sets `session.status` to `"completed"` in Redis and writes the status and final score to the DB row. The client can also request a final report (`/api/session/{session_id}/comprehensive-report`). | `app.py` → `end_session` (lines 625-646) and `get_comprehensive_report` (lines 575-623) |
| **🔟 Data persisted** | Throughout the interview, the session state lives in Redis (questions, answers, follow-ups, memory buffer). The summary (status, final score) is written back to the relational DB at the end. | `core/redis_session_store.py` for live state, `models/db_models.py` for DB rows |

### Summary Flow

1. Upload resume → server creates a fresh `InterviewSession` and stores it in Redis.
2. First question is sent back to the front-end.
3. User answers → server records the answer, evaluates it, decides on a follow-up or moves to the next question.
4. This loop repeats until all questions (including any follow-ups) are completed.
5. Finally, a comprehensive report (QA pairs, scores, improvement plan) is generated and the interview row in the DB is updated with the final status/score.

All heavy model objects (YOLO, Whisper, ElevenLabs, MediaPipe) are built lazily on first use and cached for the process lifetime via `@lru_cache` getters (`app.py:63-115`), so start-up stays fast and the interview lifecycle itself only reads/writes Redis and runs inference via those cached objects.

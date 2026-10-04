# InterviewAI - Quick Start Checklist ✅

## Pre-Setup Requirements
- [ ] Python 3.8+ installed
- [ ] Virtual environment prepared
- [ ] Internet connection (for model downloads)
- [ ] Modern web browser (Chrome, Firefox, Safari, Edge)

## Installation & Setup

### 1. Environment Configuration
```bash
cd /Applications/InterviewAI

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Variables (.env)
Create `.env` file in project root:
```
OPENAI_API_KEY=sk-...your-key...
ELEVENLABS_API_KEY=dbb0dafcd...your-key...
DATABASE_URL=sqlite:///./interviews.db
LOG_LEVEL=INFO
```

### 3. Download AI Models
```bash
# Download YOLOv8 model
python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

```

## Running the Application

### Start Backend
```bash
# Make sure venv is activated
source venv/bin/activate

# Start FastAPI server
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**
```
INFO:     Application startup complete [started server process]
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Access Frontend
1. Open browser to: **http://localhost:8000**
2. You should see the InterviewAI landing page

## Testing the Integration

### Health Check
```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "InterviewAI"
}
```

### Test Resume Upload
```bash
# Using a sample PDF
curl -X POST http://localhost:8000/api/upload-resume \
  -F "resume=@sample_resume.pdf" \
  -F "job_role=Data Scientist"
```

### Test Face Detection (via Frontend)
1. Go to http://localhost:8000
2. Proceed through upload and setup
3. Start interview - real-time face detection begins
4. Check browser console (F12) for frame analysis logs

## Quick Start Profile Data

The application comes with 3 pre-configured profiles:

### 📄 Goutham - Data Scientist
- **Skills**: Python, TensorFlow, SQL, Scikit-Learn, Pandas
- **Projects**: Crop Disease Detection, JobSphere, Sales Predictor
- **Experience**: 1.5 years internship at AI Lab

### 📄 Ananya - AI Engineer
- **Skills**: PyTorch, Transformers, HuggingFace, FastAPI, Python
- **Projects**: Medical Image ViT, DocChat Agent, VoiceScribe
- **Experience**: 2 years AI Developer experience

### 📄 Ryan - Full Stack Developer
- **Skills**: React, Node.js, Express, MongoDB, JavaScript
- **Projects**: E-comm Platform, TaskHub Board, ChatStream
- **Experience**: 3 years Frontend & Backend intern

## Job Roles Available
- Data Scientist
- AI Engineer
- Full Stack Developer
- Java Developer
- ML Engineer
- Backend Developer
- DevOps Engineer
- Cybersecurity Analyst

## Key Features Now Active

✅ **Resume Upload & Session Creation**
- Upload PDF/DOCX resumes
- Or select quick-start profiles
- Backend creates interview session

✅ **Real-Time Face Detection**
- Monitors face presence
- Detects looking away
- Detects multiple people (cheating)

✅ **Object Detection**
- Detects mobile phone usage
- Flags multiple persons
- Integration with YOLOv8

✅ **Audio Transcription**
- Real-time speech-to-text via the browser's Web Speech API
- Streams into the answer box as the candidate talks
- Chrome/Edge only; other browsers fall back to typing

✅ **Text-to-Speech**
- Question reading with AI voice
- ElevenLabs integration
- Multiple voice options

✅ **Real-Time Monitoring**
- Periodic frame analysis (every 2 seconds)
- Cheating detection
- Live metrics dashboard

✅ **Interview Flow**
- Question generation
- Answer evaluation
- Follow-up questions
- Comprehensive reporting

## API Endpoints Available

### Session Management
```
POST   /api/upload-resume                      # Create session
GET    /api/session/{id}/question              # Get current question
POST   /api/session/{id}/answer                # Submit answer
POST   /api/session/{id}/next-question         # Move next
GET    /api/session/{id}/progress              # Get progress
GET    /api/session/{id}/scores                # Get scores
GET    /api/session/{id}/comprehensive-report  # Final report
```

### AI Monitoring
```
POST   /api/analyze-frame                      # Full analysis
POST   /api/detect-face                        # Face detection
POST   /api/detect-objects                     # Object detection
POST   /api/generate-speech                    # Text to speech
GET    /api/tts-voices                         # Available voices
```

### System
```
GET    /api/health                             # Health check
```

## Browser Requirements

✅ **Required Features**
- WebSocket support (for fallback)
- MediaDevices API (camera/mic)
- Web Audio API (audio processing)
- Canvas API (frame capture)

✅ **Tested Browsers**
- Chrome 90+
- Firefox 88+
- Safari 15+
- Edge 90+

## Permissions Required

When starting an interview, grant:
1. ✅ **Camera access** - for face tracking
2. ✅ **Microphone access** - for transcription
3. Note: These can be denied and interview will run in simulation mode

## Debugging

### Check Backend Logs
- Watch terminal where you ran `uvicorn`
- Errors appear in red
- API calls logged with timestamps

### Check Frontend Logs
- Press F12 in browser
- Go to **Console** tab
- Look for blue `api-service.js` logs
- Errors appear in red

### Common Issues & Fixes

**Issue**: Backend won't start
```bash
# Check Python version
python3 --version  # Should be 3.8+

# Check if port 8000 is in use
lsof -i :8000
# Kill if needed: kill -9 <PID>
```

**Issue**: Camera access denied
- This is OK! Interview runs in simulation mode
- All monitoring still works via canvas simulation

**Issue**: Models not downloading
- Ensure internet connection
- Check disk space: `df -h`
- Manually download: `python3 -m pip install ultralytics`

## Performance Tips

### For Smooth Operation
1. Close other browser tabs
2. Use modern laptop/desktop
3. Ensure good internet (for TTS API calls)
4. Use wired connection if possible
5. Disable screen recording if interviewing

### If this ever needs to scale
Already done: model caching (`@lru_cache` singletons in `app.py`) and rate
limiting (`core/rate_limit.py`, six limiters). Still open:

1. Run the two per-turn LLM calls concurrently — they are sequential today and
   are ~90% of a turn's latency
2. GPU for YOLO inference (`ultralytics` picks the device automatically)
3. Database connection pooling
4. CDN for static assets

## Next Steps

1. ✅ **Test with Sample Profile**
   - Click "Goutham - Data Scientist"
   - Go through full interview
   - Check results page

2. ✅ **Test Resume Upload**
   - Prepare a PDF resume
   - Upload and verify extraction
   - Check question generation

3. ✅ **Monitor Real-Time Analysis**
   - Open browser console (F12)
   - Watch frame analysis logs
   - Test face/object detection

4. ✅ **Review Reports**
   - Complete an interview
   - Check comprehensive report
   - Verify all metrics

## Support Resources

- **API Docs**: http://localhost:8000/docs (interactive)
- **INTEGRATION_GUIDE.md**: Full technical documentation
- **Frontend Console**: F12 → Console (live logs)
- **Backend Logs**: Terminal output where uvicorn is running

## Useful Commands

```bash
# Run with verbose logging
uvicorn app:app --reload --log-level debug

# Run in background
nohup python3 -m uvicorn app:app > server.log 2>&1 &

# Check if server is responding
curl -v http://localhost:8000/api/health

# Test with actual file upload
curl -v -F "resume=@test.pdf" -F "job_role=Data Scientist" \
  http://localhost:8000/api/upload-resume
```

## Success Indicators ✨

When everything is working:
1. ✅ Landing page loads without errors
2. ✅ Can upload resume or select profile
3. ✅ Questions appear in interview
4. ✅ Metrics update in real-time
5. ✅ Can submit answers and get feedback
6. ✅ Final report shows scores
7. ✅ No console errors (F12)
8. ✅ API endpoints respond (http://localhost:8000/docs)

---

**Ready to start? Run this:**
```bash
cd /Applications/InterviewAI
source venv/bin/activate
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Then open: **http://localhost:8000**

Enjoy your AI interview experience! 🚀

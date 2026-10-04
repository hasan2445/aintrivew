

const state = {
    step: 0,
    sessionId: null,
    resumeFile: null,
    resumeFileName: '',
    jobRole: '',
    candidateName: '',
    difficulty: 'medium',
    currentQuestion: 0,
    questions: [],
    totalQuestions: 0,
    answers: [],
    metrics: {
        technicalScore: 0,
        communicationScore: 0,
        confidenceScore: 0,
        eyeContactScore: 0,
        resumeKnowledge: 0,
        problemSolving: 0,
        fillerWords: 0,
        speakingSpeed: 0,
        averagePause: 0,
        emotion: 'Neutral'
    },
    interviewActive: false,
    stream: null,
    faceDetected: true,
    eyeContactLost: false,
    warnings: [],
    agentStatus: {
        resumeAnalyzer: 'idle',
        questionGenerator: 'idle',
        technicalEvaluator: 'idle',
        communicationEvaluator: 'idle',
        faceMonitor: 'idle',
        feedbackGenerator: 'idle',
        reportGenerator: 'idle'
    },
    chatMessages: [],
    isRecording: false,
    transcript: '',
    cheatingAlerts: [],
    typing: false,


    cheatingStats: {
        lookedAwayCount: 0,
        multipleFacesCount: 0,
        mobileDetectedCount: 0,
        secondsLookedAway: 0
    },


    simulations: {
        lookAway: false,
        noFace: false,
        multipleFaces: false,
        phoneUsage: false
    },


    lastEvaluation: null,
    evaluations: [],


    resumeRawText: '',
    tempExtracted: null,
    reportData: null,
    sessionEnded: false,

    // Server-issued turn counter, echoed back on every answer submission so a
    // duplicate is rejected with a 409 instead of silently overwriting the
    // previous answer's evaluation.
    turn: 0,
    // Guards against a double-Enter / double-click firing two submissions.
    submitInFlight: false,

    // Browser-measured attention, reported to the server as feedback. The
    // server used to compute a coarser version of this itself; the browser's
    // iris-based estimate runs at camera rate and tracks duration, which frame
    // counts cannot.
    attention: {
        samples: 0,
        attentiveSamples: 0,
        lookAwayEvents: 0,
        lookAwaySeconds: 0,
        noFaceEvents: 0
    }
};


function resetState() {
    state.step = 0;
    state.sessionId = null;
    state.resumeFile = null;
    state.resumeFileName = '';
    state.jobRole = '';
    state.candidateName = '';
    state.difficulty = 'medium';
    state.currentQuestion = 0;
    state.questions = [];
    state.totalQuestions = 0;
    state.answers = [];
    state.metrics = {
        technicalScore: 0, communicationScore: 0, confidenceScore: 0,
        eyeContactScore: 0, resumeKnowledge: 0, problemSolving: 0,
        fillerWords: 0, speakingSpeed: 0, averagePause: 0, emotion: 'Neutral'
    };
    state.interviewActive = false;
    state.stream = null;
    state.faceDetected = true;
    state.eyeContactLost = false;
    state.warnings = [];
    state.agentStatus = {
        resumeAnalyzer: 'idle', questionGenerator: 'idle', technicalEvaluator: 'idle',
        communicationEvaluator: 'idle', faceMonitor: 'idle', feedbackGenerator: 'idle',
        reportGenerator: 'idle'
    };
    state.chatMessages = [];
    state.isRecording = false;
    state.transcript = '';
    state.cheatingAlerts = [];
    state.typing = false;
    state.cheatingStats = {
        lookedAwayCount: 0,
        multipleFacesCount: 0,
        mobileDetectedCount: 0,
        secondsLookedAway: 0
    };
    state.simulations = {
        lookAway: false,
        noFace: false,
        multipleFaces: false,
        phoneUsage: false
    };
    state.lastEvaluation = null;
    state.evaluations = [];
    // These are assigned dynamically by upload.js / results.js. Without clearing
    // them, a new interview inherited the previous run's resume text and report.
    state.resumeRawText = '';
    state.tempExtracted = null;
    state.reportData = null;
    // Left true after the first interview, this silently suppressed the
    // end-session call (and therefore the saved score) on every later run.
    state.sessionEnded = false;
    state.turn = 0;
    state.submitInFlight = false;
    state.attention = {
        samples: 0, attentiveSamples: 0, lookAwayEvents: 0,
        lookAwaySeconds: 0, noFaceEvents: 0
    };
}



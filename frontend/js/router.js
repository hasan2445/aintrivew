

const app = document.getElementById('app');

function logoutUser() {
    // Before resetState(), which clears the interview but would leave a
    // question still playing out loud on the landing page.
    if (typeof stopSpeaking === 'function') stopSpeaking();

    localStorage.removeItem('interviewai_token');
    // Allow the next sign-in to be re-verified against the server.
    if (typeof renderLanding === 'function') renderLanding._verified = false;
    // Clear interview data too, so the next person to sign in on this browser
    // does not inherit the previous user's transcript, scores or report.
    if (typeof resetState === 'function') resetState();
    state.step = 0;
    render();
}

function render() {
    switch (state.step) {
        case 0: renderLanding();         break;
        case 1: renderUpload();          break;
        // Setup now runs BEFORE analysis. It used to be step 3, i.e. after the
        // upload had already generated the questions, which is why its
        // difficulty picker could not possibly affect them.
        case 2: renderInterviewSetup();  break;
        case 3: renderAnalysis();        break;
        case 4: renderActiveInterview(); break;
        case 5: renderResults();         break;
        // Steps 6 and 7 held standalone renderLogin/renderSignup pages that were
        // only reachable from each other — the landing page uses an inline modal
        // instead. Both files are deleted; these cases fall through to landing.
        case 8: renderAdmin();           break;
        default: renderLanding();
    }


    if (window.lucide) {
        lucide.createIcons();
    }
}



function renderResults() {
    const name = state.candidateName || 'Candidate';
    // state.metrics / state.cheatingStats are the live in-interview estimate.
    // They are deliberately not read on this page any more: everything below
    // comes from the report the server computed.


    if (!state.reportData && state.sessionId) {
        app.innerHTML = `
        <div class="ia-page flex flex-col items-center justify-center text-slate-950 relative overflow-hidden">
            <div class="relative z-10 flex flex-col items-center">
                <svg class="animate-spin -ml-1 mr-3 h-12 w-12 text-blue-600 mb-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <h2 class="text-2xl font-bold tracking-tight mb-2">Generating report</h2>
                <p class="text-slate-600 text-sm">Synthesizing interview transcript and extracting personalized insights.</p>
            </div>
        </div>`;

        API.getComprehensiveReport(state.sessionId).then(data => {
            // Backend nests plan under comprehensive_report; keep flat fallback.
            const report = data && data.comprehensive_report ? data.comprehensive_report : data;
            state.reportData = Object.assign({}, data || {}, report || {}, {
                improvement_plan: (report && report.improvement_plan)
                    || (data && data.improvement_plan)
                    || { strengths: [], weaknesses: [] }
            });

            // The score is the server's, computed from the real per-answer
            // evaluations and the frames the server itself judged. The browser
            // used to compute a weighted formula over its own live metrics,
            // subtract integrity penalties it counted itself, and POST the
            // result to /end — which overwrote the backend number that
            // /comprehensive-report had just written. The scoring policy was
            // therefore editable in devtools. /end now takes no score at all.
            if (!state.sessionEnded && state.sessionId) {
                state.sessionEnded = true;
                API.endSession(state.sessionId).catch(err => console.error("Failed to end session", err));
            }

            renderResults();
        }).catch(err => {
            console.error("Error generating report", err);
            state.reportData = {
                improvement_plan: {
                    strengths: ["Report generation failed (Backend Error)"],
                    weaknesses: ["Unable to analyze transcript"]
                }
            };
            renderResults();
        });
        return;
    }

    const plan = (state.reportData && state.reportData.improvement_plan) ? state.reportData.improvement_plan : { strengths: [], weaknesses: [] };

    // Server metrics, on a 0-100 scale. `metrics` used to be fetched and then
    // ignored — only improvement_plan was read out of the report, and every
    // ring and bar on this page rendered browser state instead.
    const server = (state.reportData && state.reportData.metrics) || {};
    const proctoring = server.proctoring || {};
    // Browser-measured, shown as feedback. It is deliberately not one of the
    // scored components: the server no longer computes gaze, and a number the
    // client supplies should inform the candidate, not grade them.
    const attention = server.attention || {};
    const toTen = v => (typeof v === 'number' ? Math.round((v / 10) * 10) / 10 : null);


    const strengthsHtml = plan.strengths && plan.strengths.length > 0
        ? plan.strengths.map(s => _planItemEnhanced('emerald', s)).join('')
        : _planItemEnhanced('emerald', 'Insufficient conversational data to identify core strengths.');


    const weaknessesHtml = plan.weaknesses && plan.weaknesses.length > 0
        ? plan.weaknesses.map(w => _planItemEnhanced('indigo', w)).join('')
        : _planItemEnhanced('indigo', 'Insufficient conversational data to map growth areas.');


    const penalty = typeof server.integrity_penalty === 'number' ? server.integrity_penalty : 0;
    // A percentage, not a mean. The server weights each measurable component and
    // redistributes the weight of anything it could not measure across the rest,
    // so this is always "percent of the criteria that were actually assessed"
    // and two candidates are comparable even when one had no camera.
    const overall = typeof server.overall_score === 'number' ? Math.round(server.overall_score) : 0;
    const basis = server.score_basis || {};
    const basisCount = Array.isArray(basis.components) ? basis.components.length : 0;
    const overallGrade = overall >= 90 ? 'A+' : overall >= 80 ? 'A' : overall >= 70 ? 'B' : overall >= 60 ? 'C' : 'F';

    let gradeGlow = 'shadow-success-500/50';
    let gradeColor = 'from-emerald-400 to-teal-500';
    let strokeColor = '#10b981';

    if (overall < 60) {
        gradeColor = 'from-rose-400 to-red-500';
        gradeGlow = 'shadow-rose-500/50';
        strokeColor = '#f43f5e';
    } else if (overall < 80) {
        gradeColor = 'from-amber-400 to-orange-500';
        gradeGlow = 'shadow-amber-500/50';
        strokeColor = '#f59e0b';
    }

    const scoreItems = [
        { label: 'Technical Accuracy', score: toTen(server.technical_score), max: 10, bg: 'bg-indigo-500' },
        { label: 'Communication', score: toTen(server.communication_score), max: 10, bg: 'bg-emerald-500' },
        { label: 'Speech Confidence', score: toTen(server.confidence_score), max: 10, bg: 'bg-amber-500' },
        { label: 'Resume Validation', score: toTen(server.resume_alignment_score), max: 10, bg: 'bg-violet-500' },
        { label: 'Problem Solving', score: toTen(server.problem_solving_score), max: 10, bg: 'bg-rose-500' }
    ].filter(item => item.score !== null);

    app.innerHTML = `
    <div class="ia-page font-sans selection:bg-blue-200/60 overflow-x-hidden relative">
        <div class="relative z-10 max-w-5xl mx-auto px-6 py-16">


            <header class="mb-14 text-center slide-up">
                <div class="ia-chip mb-6">
                    <i data-lucide="check-circle" class="w-4 h-4 text-emerald-600"></i>
                    <span>Assessment complete</span>
                </div>
                <h1 class="text-4xl md:text-5xl font-bold tracking-tight mb-4 text-slate-950">
                    Interview Report
                </h1>
                <p class="text-base text-slate-600 max-w-2xl mx-auto">
                    Candidate <strong class="text-slate-950 font-semibold">${escapeHtml(name)}</strong> &middot; Role <strong class="text-slate-950 font-semibold">${escapeHtml(state.jobRole)}</strong>
                </p>
            </header>

            <div class="grid lg:grid-cols-12 gap-8 mb-12">


                <div class="lg:col-span-5 relative group slide-up" style="animation-delay: 0.1s">
                    <div class="h-full ia-card p-8 md:p-12 flex flex-col items-center justify-center text-center relative overflow-hidden">

                        <div class="relative w-48 h-48 mb-8">

                            <svg class="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                                <circle cx="50" cy="50" r="46" fill="none" stroke="#e5edf5" stroke-width="6" />
                                <circle cx="50" cy="50" r="46" fill="none" stroke="#2563eb" stroke-width="6" stroke-linecap="round"
                                    stroke-dasharray="${2 * Math.PI * 46}" stroke-dashoffset="${2 * Math.PI * 46 * (1 - overall/100)}"
                                    class="transition-all duration-1500 ease-out" />
                            </svg>
                            <div class="absolute inset-0 flex flex-col items-center justify-center">
                                <span class="text-6xl font-bold text-slate-950 tracking-tight">${overall}<span class="text-3xl align-top">%</span></span>
                                <span class="text-[10px] font-mono uppercase tracking-widest text-slate-500 mt-1">Overall</span>
                            </div>
                        </div>

                        <h2 class="text-xl font-semibold mb-2 text-slate-950">Grade ${overallGrade}</h2>
                        <p class="text-sm text-slate-600 leading-relaxed max-w-xs">
                            Weighted percentage across ${basisCount || 4} assessed criteria: technical accuracy, communication, confidence and resume alignment.
                        </p>
                    </div>
                </div>


                <div class="lg:col-span-7 flex flex-col gap-6 slide-up" style="animation-delay: 0.2s">

                    <div class="ia-card p-6 relative overflow-hidden">
                        <div class="flex items-center justify-between mb-5">
                            <h3 class="text-sm font-semibold text-slate-950 flex items-center gap-2">
                                <i data-lucide="shield" class="w-4 h-4 text-emerald-600"></i>
                                Integrity & Focus
                            </h3>
                            ${penalty > 0
                                ? '<span class="bg-rose-50 text-rose-700 text-[10px] uppercase tracking-wider px-3 py-1 rounded-full border border-rose-100">Anomalies Detected</span>'
                                : '<span class="bg-emerald-50 text-emerald-700 text-[10px] uppercase tracking-wider px-3 py-1 rounded-full border border-emerald-100">Verified</span>'}
                        </div>
                        <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
                            <div class="ia-card-soft p-4">
                                <div class="text-2xl font-bold text-slate-950 mb-1">${proctoring.phone_frames || 0}</div>
                                <div class="text-[10px] uppercase tracking-wider text-slate-500 font-mono">Phone Frames</div>
                            </div>
                            <div class="ia-card-soft p-4">
                                <div class="text-2xl font-bold text-slate-950 mb-1">${proctoring.multiple_person_frames || 0}</div>
                                <div class="text-[10px] uppercase tracking-wider text-slate-500 font-mono">Extra-Person Frames</div>
                            </div>
                            <div class="ia-card-soft p-4">
                                <div class="text-2xl font-bold text-slate-950 mb-1">${attention.reported ? attention.look_away_events : '—'}</div>
                                <div class="text-[10px] uppercase tracking-wider text-slate-500 font-mono">Look-Aways</div>
                            </div>
                            <div class="ia-card-soft p-4">
                                <div class="text-2xl font-bold text-slate-950 mb-1">${proctoring.frames_analysed || 0}</div>
                                <div class="text-[10px] uppercase tracking-wider text-slate-500 font-mono">Frames Analysed</div>
                            </div>
                        </div>
                        ${penalty > 0
                            ? `<div class="mt-4 text-xs text-rose-700 bg-rose-50 p-3 rounded-lg border border-rose-100">Integrity penalty applied: -${penalty} points deducted from final score.</div>`
                            : ''}
                        ${attention.reported
                            ? `<div class="mt-4 text-xs text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-200"><strong>Attention (self-measured):</strong> on screen ${attention.on_screen_percentage}% of the time · ${attention.look_away_events} look-aways totalling ${attention.look_away_seconds}s${attention.no_face_events ? ` · left frame ${attention.no_face_events} times` : ''}. Measured in your browser and shown as feedback — it does not affect your score.</div>`
                            : `<div class="mt-4 text-xs text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-200">No attention data was recorded for this session.</div>`}
                        ${server.unscored_evaluations > 0
                            ? `<div class="mt-4 text-xs text-amber-800 bg-amber-50 p-3 rounded-lg border border-amber-100">${server.unscored_evaluations} answer(s) could not be automatically evaluated and were excluded from the score.</div>`
                            : ''}
                    </div>


                    <div class="ia-card p-6 sm:p-8 flex-1 flex flex-col justify-center">
                        <div class="space-y-5">
                            ${scoreItems.map((item, i) => `
                                <div class="group">
                                    <div class="flex justify-between items-end mb-2">
                                        <span class="text-xs font-medium text-[#888888] group-hover:text-white transition-colors uppercase tracking-wider">${item.label}</span>
                                        <span class="text-xs font-mono text-[#666666] group-hover:text-[#888888] transition-colors">${(item.score).toFixed(1)} / ${item.max}</span>
                                    </div>
                                    <div class="h-1.5 w-full bg-slate-100 rounded-full overflow-hidden relative">
                                        <div class="absolute top-0 left-0 h-full bg-blue-600 rounded-full transition-all duration-1000 ease-out" style="width: ${(item.score / item.max) * 100}%; animation: growRight 1.5s cubic-bezier(0.2, 0.8, 0.2, 1) forwards;"></div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>


            <div class="grid md:grid-cols-2 gap-8 mb-12 slide-up" style="animation-delay: 0.3s">


                <div class="ia-card p-8 relative overflow-hidden">
                    <h3 class="text-slate-950 font-semibold text-sm mb-6 flex items-center gap-2">
                        <i data-lucide="trending-up" class="w-4 h-4 text-emerald-600"></i>
                        Core Strengths
                    </h3>
                    <ul class="space-y-4 relative z-10">
                        ${strengthsHtml}
                    </ul>
                </div>


                <div class="ia-card p-8 relative overflow-hidden">
                    <h3 class="text-slate-950 font-semibold text-sm mb-6 flex items-center gap-2">
                        <i data-lucide="trending-down" class="w-4 h-4 text-amber-600"></i>
                        Growth Opportunities
                    </h3>
                    <ul class="space-y-4 relative z-10">
                        ${weaknessesHtml}
                    </ul>
                </div>
            </div>


            <div class="flex flex-col sm:flex-row items-center justify-center gap-5 mt-16 slide-up" style="animation-delay: 0.4s">
                <button onclick="window.print()" class="w-full sm:w-auto px-6 py-3 ia-button-secondary text-sm font-semibold flex items-center justify-center gap-2">
                    <i data-lucide="download" class="w-4 h-4"></i>
                    Download PDF
                </button>
                <button onclick="resetState();render()" class="w-full sm:w-auto px-6 py-3 ia-button-primary text-sm font-semibold flex items-center justify-center gap-2">
                    Start New Interview
                    <i data-lucide="arrow-right" class="w-4 h-4"></i>
                </button>
            </div>

        </div>

        <style>
            @keyframes growRight { from { width: 0; } }
            .slide-up { animation: slideUpFade 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards; opacity: 0; transform: translateY(30px); }
            @keyframes slideUpFade { to { opacity: 1; transform: translateY(0); } }
        </style>
    </div>
    `;
    if(window.lucide) { setTimeout(() => lucide.createIcons(), 10); }
}



function _planItemEnhanced(color, text) {
    return `
    <li class="flex items-start gap-3 p-3 rounded-lg bg-slate-50 border border-slate-200 hover:bg-white transition-colors">
        <i data-lucide="${color === 'emerald' ? 'check-circle' : 'alert-circle'}" class="w-4 h-4 ${color === 'emerald' ? 'text-emerald-600' : 'text-amber-600'} flex-shrink-0 mt-0.5"></i>
        <span class="text-sm text-slate-700 leading-relaxed">${escapeHtml(text)}</span>
    </li>`;
}

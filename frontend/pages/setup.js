

function renderInterviewSetup() {
    const name = state.candidateName || 'Candidate';
    const choices = [
        { id: 'easy', label: 'Warm-up', name: 'Easy', icon: 'sprout', color: 'emerald', text: 'Build confidence with foundational questions and gentle follow-ups.', meta: 'Best for getting started' },
        { id: 'medium', label: 'Balanced', name: 'Medium', icon: 'target', color: 'indigo', text: 'A realistic mix of technical depth, breadth, and adaptive follow-ups.', meta: 'Recommended for most sessions' },
        { id: 'hard', label: 'Stretch', name: 'Hard', icon: 'flame', color: 'rose', text: 'Go deeper with ambiguous scenarios and challenging reasoning prompts.', meta: 'Best for final preparation' }
    ];

    app.innerHTML = `
    <div class="min-h-screen bg-surface-950 text-surface-200 font-sans selection:bg-indigo-500/30">
        <header class="sticky top-0 z-40 border-b border-white/10 bg-surface-950/85 backdrop-blur-xl">
            <div class="max-w-6xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between">
                <button onclick="state.step=1;render()" class="flex items-center gap-2 text-surface-400 hover:text-white text-sm transition-colors">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i> Back to profile
                </button>
                <div class="hidden sm:flex items-center gap-3 text-[10px] uppercase tracking-[.2em] font-semibold text-surface-500">
                    <span class="text-indigo-300">01 Profile</span><span class="text-surface-700">/</span><span class="text-white">02 Setup</span><span class="text-surface-700">/</span><span>03 Interview</span>
                </div>
                <span class="text-surface-500 text-xs font-mono">2 of 3</span>
            </div>
        </header>

        <main class="max-w-6xl mx-auto px-5 sm:px-8 py-10 sm:py-14">
            <div class="max-w-3xl mb-10">
                <div class="inline-flex items-center gap-2 rounded-full border border-indigo-400/20 bg-indigo-400/10 px-3 py-1 text-[11px] font-semibold text-indigo-300 mb-5">
                    <i data-lucide="sparkles" class="w-3.5 h-3.5"></i> Personalize your session
                </div>
                <h1 class="text-3xl sm:text-5xl font-semibold tracking-tight text-white">Set the tone for your interview.</h1>
                <p class="mt-4 text-sm sm:text-base leading-7 text-surface-400 max-w-2xl">Choose a difficulty that matches where you are today. Your interviewer will adapt the conversation and follow-ups around this choice.</p>
            </div>

            <div class="grid lg:grid-cols-[minmax(0,1fr)_330px] gap-6 lg:gap-10 items-start">
                <section>
                    <div class="flex items-end justify-between mb-4">
                        <div><p class="text-white text-sm font-semibold">Interview difficulty</p><p class="text-surface-500 text-xs mt-1">You can change this before you begin.</p></div>
                        <span class="text-[10px] uppercase tracking-widest text-surface-500 font-mono">Required</span>
                    </div>
                    <div class="space-y-3">
                        ${choices.map(choice => `
                            <button type="button" onclick="selectDifficulty('${choice.id}')" aria-pressed="${state.difficulty === choice.id}" class="setup-choice w-full text-left p-4 sm:p-5 flex items-start gap-4 ${state.difficulty === choice.id ? 'is-selected' : ''}">
                                <span class="w-11 h-11 shrink-0 rounded-xl flex items-center justify-center ${state.difficulty === choice.id ? `bg-${choice.color}-400/15 text-${choice.color}-300` : 'bg-white/5 text-surface-400'}"><i data-lucide="${choice.icon}" class="w-5 h-5"></i></span>
                                <span class="min-w-0 flex-1">
                                    <span class="flex flex-wrap items-center gap-2"><span class="text-white font-semibold">${choice.label}</span><span class="text-[10px] text-surface-500 uppercase tracking-widest">${choice.name}</span>${choice.id === 'medium' ? '<span class="rounded-full bg-indigo-400/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-widest text-indigo-300">Recommended</span>' : ''}</span>
                                    <span class="block text-sm leading-6 text-surface-400 mt-1">${choice.text}</span>
                                    <span class="block text-[11px] text-surface-500 mt-2">${choice.meta}</span>
                                </span>
                                <span class="w-5 h-5 shrink-0 rounded-full border flex items-center justify-center mt-1 ${state.difficulty === choice.id ? 'border-indigo-300 bg-indigo-400' : 'border-surface-600'}">${state.difficulty === choice.id ? '<i data-lucide="check" class="w-3 h-3 text-slate-950"></i>' : ''}</span>
                            </button>
                        `).join('')}
                    </div>

                    <div class="mt-6 rounded-xl border border-white/10 bg-white/[.03] p-4 flex gap-3">
                        <i data-lucide="info" class="w-4 h-4 text-surface-400 mt-0.5 shrink-0"></i>
                        <p class="text-xs leading-5 text-surface-400">The difficulty changes question complexity, not your profile. Every session still uses your resume, projects, and target role.</p>
                    </div>
                </section>

                <aside class="setup-summary p-5 lg:sticky lg:top-24">
                    <div class="flex items-center justify-between mb-5"><div><p class="text-white text-sm font-semibold">Session preview</p><p class="text-surface-500 text-xs mt-1">What you’re bringing in</p></div><span class="setup-step-dot w-2 h-2 rounded-full bg-emerald-400"></span></div>
                    <div class="rounded-xl border border-white/10 bg-black/10 p-4 mb-5">
                        <p class="text-[10px] uppercase tracking-widest text-surface-500 font-semibold">Candidate</p>
                        <p class="text-white font-medium mt-1">${escapeHtml(name)}</p>
                        <p class="text-surface-400 text-xs mt-1">${escapeHtml(state.jobRole)}</p>
                    </div>
                    <div class="space-y-4 text-xs">
                        <div class="flex items-center justify-between"><span class="text-surface-500">Questions</span><span class="text-white font-mono">${state.questions.length || '8–10'}</span></div>
                        <div class="flex items-center justify-between"><span class="text-surface-500">Difficulty</span><span class="text-indigo-300 font-semibold capitalize">${escapeHtml(state.difficulty)}</span></div>
                        <div class="flex items-center justify-between"><span class="text-surface-500">Focus checks</span><span class="text-emerald-300">Ready</span></div>
                    </div>
                    <div class="border-t border-white/10 mt-5 pt-5">
                        <p class="text-[10px] uppercase tracking-widest text-surface-500 font-semibold mb-3">Session includes</p>
                        <div class="space-y-2.5 text-xs text-surface-300">
                            ${['Resume-aware prompts', 'Live voice or text answers', 'Performance feedback'].map(item => `<div class="flex items-center gap-2"><i data-lucide="check" class="w-3.5 h-3.5 text-emerald-400"></i>${item}</div>`).join('')}
                        </div>
                    </div>
                    <button onclick="beginSession()" class="w-full mt-6 rounded-xl bg-indigo-500 hover:bg-indigo-400 text-white py-3.5 text-sm font-semibold transition-all shadow-lg shadow-indigo-500/20 flex items-center justify-center gap-2">Start interview <i data-lucide="arrow-up-right" class="w-4 h-4"></i></button>
                </aside>
            </div>
        </main>
    </div>`;

    if (window.lucide) setTimeout(() => lucide.createIcons(), 10);
}

/**
 * Questions do not exist yet on this screen.
 *
 * They used to be generated before setup, so `state.questions.length` was a
 * real number here. Generation moved into the analysis step (see beginSession
 * below) so that the chosen difficulty is sent *with* the resume — which means
 * the array is empty at this point and the summary showed a hard "0" for every
 * difficulty. The prompt asks for 8-10 questions and caps at 12
 * (MAX_PRIMARY_QUESTIONS), and difficulty changes question complexity, not
 * count, so the range is the same for easy/medium/hard.
 */
function selectDifficulty(diff) {
    state.difficulty = diff;
    renderInterviewSetup();
}

/**
 * Confirm the setup and generate the interview.
 *
 * This button used to call startInterview() directly, because the questions had
 * already been generated on the previous screen. It now moves to the analysis
 * step, which uploads the resume together with the chosen difficulty and only
 * then enters the interview.
 */
function beginSession() {
    state.step = 3;
    render();
    simulateAnalysis();
}

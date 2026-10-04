

function renderAnalysis() {
    const agents = [
        { id: 'resumeAnalyzer',   label: 'Profile Extraction',   icon: 'file-text' },
        { id: 'questionGenerator', label: 'Question Generation', icon: 'list-todo' },
        { id: 'faceMonitor',      label: 'Vision Configuration',       icon: 'camera' }
    ];

    app.innerHTML = `
    <div class="ia-page font-sans selection:bg-blue-200/60 flex items-center justify-center px-4 py-8">
        <div class="max-w-2xl w-full text-center">
            <div class="w-16 h-16 bg-slate-950 text-white rounded-lg flex items-center justify-center mx-auto mb-6 pulse-ring">
                <i data-lucide="loader" class="w-8 h-8 animate-spin"></i>
            </div>
            <h2 class="text-2xl font-bold text-slate-950 mb-2 tracking-tight">Processing your profile</h2>
            <p class="text-slate-600 text-sm mb-10">Extracting skills, generating tailored questions, and configuring the interview environment.</p>


            <div class="grid sm:grid-cols-3 gap-4 text-left max-w-xl mx-auto mb-10">
                ${agents.map(agent => `
                <div class="ia-card p-4 text-left" id="agent-${agent.id}">
                    <div class="flex items-center gap-3 mb-3">
                        <i data-lucide="${agent.icon}" class="w-4 h-4 text-blue-600"></i>
                        <div class="text-slate-950 text-sm font-semibold truncate tracking-tight">${agent.label}</div>
                    </div>
                    <div class="flex items-center gap-3">
                        <div class="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                            <div class="bg-blue-600 h-1.5 rounded-full transition-all duration-700" style="width:0%" id="progress-${agent.id}"></div>
                        </div>
                        <span class="text-slate-500 text-[10px] font-mono uppercase tracking-widest" id="status-${agent.id}">Wait</span>
                    </div>
                </div>
                `).join('')}
            </div>


            <div class="max-w-xl mx-auto">
                <div class="bg-slate-950 border border-slate-800 rounded-lg overflow-hidden shadow-2xl">
                    <div class="bg-slate-900 px-4 py-2 border-b border-slate-800 flex items-center justify-between">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 bg-rose-400 rounded-full"></span>
                            <span class="w-2.5 h-2.5 bg-amber-400 rounded-full"></span>
                            <span class="w-2.5 h-2.5 bg-emerald-400 rounded-full"></span>
                        </div>
                        <span class="text-[10px] font-mono text-slate-400 uppercase tracking-wider">Initialization Log</span>
                    </div>
                    <div class="p-5 font-mono text-xs text-left text-slate-300 h-64 overflow-y-auto space-y-2 leading-relaxed" id="terminalConsole">
                        <div class="text-white">> [System] Initializing session...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `;

    if(window.lucide) { setTimeout(() => lucide.createIcons(), 10); }
}

async function simulateAnalysis() {
    const consoleEl = document.getElementById('terminalConsole');

    function logMessage(text, type = 'normal') {
        if (!consoleEl) return;
        const line = document.createElement('div');
        if (type === 'system') {
            line.className = 'text-white font-medium';
        } else if (type === 'success') {
                line.className = 'text-emerald-400';
        } else if (type === 'error') {
            line.className = 'text-[#ef4444]';
        } else {
            line.className = 'text-[#888888]';
        }
        line.textContent = text;
        consoleEl.appendChild(line);
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }

    function updateAgentProgress(id, prog, label, isFinished = false) {
        const progBar = document.getElementById(`progress-${id}`);
        const statusEl = document.getElementById(`status-${id}`);
        if (progBar) progBar.style.width = `${prog}%`;
        if (statusEl) {
            statusEl.textContent = label;
            if (isFinished) {
                statusEl.className = 'text-emerald-600 font-mono text-[10px] uppercase tracking-widest';
                state.agentStatus[id] = 'complete';
            } else {
                statusEl.className = 'text-blue-600 font-mono text-[10px] uppercase tracking-widest animate-pulse';
            }
        }
    }

    try {
        logMessage(`> [System] Initializing backend processes...`, 'system');


        logMessage(`> [Process] Uploading resume and retrieving questions...`);
        updateAgentProgress('resumeAnalyzer', 30, 'Uploading');
        updateAgentProgress('questionGenerator', 30, 'Waiting');

        await uploadResumeToBackend();

        if (state.questions && state.questions.length > 0) {
            logMessage(`> [Extractor] Resume parsed successfully!`, 'success');
            updateAgentProgress('resumeAnalyzer', 100, 'Complete', true);

            logMessage(`> [Generator] Successfully configured ${state.questions.length} tailored questions!`, 'success');
            updateAgentProgress('questionGenerator', 100, 'Complete', true);
        } else {
            throw new Error("Failed to configure session from backend");
        }


        logMessage(`> [System] Connecting to vision system...`, 'system');
        updateAgentProgress('faceMonitor', 20, 'Connecting');

        await new Promise(r => setTimeout(r, 600));
        logMessage(`> [Vision] Loading MediaPipe FaceMesh models...`);
        updateAgentProgress('faceMonitor', 60, 'Loading');

        await new Promise(r => setTimeout(r, 800));
        logMessage(`> [Vision] Face Mesh loaded. Camera tracker ready.`, 'success');
        updateAgentProgress('faceMonitor', 100, 'Complete', true);

        logMessage(`> [System] Setup complete. Proceeding...`, 'system');

        await new Promise(r => setTimeout(r, 1000));
        // Straight into the interview: the difficulty screen has already run.
        startInterview();

    } catch (globalError) {
        logMessage(`> [System Error] Critical setup failure: ${globalError.message}`, 'error');
        console.error("Critical setup error", globalError);

        logMessage(`> [System] HALTING: Connection to server failed.`, 'error');
        alert("Backend API failed. Please ensure the server is running.");
    }
}

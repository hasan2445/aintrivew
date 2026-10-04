

function renderUpload() {
    app.innerHTML = `
    <div class="ia-page font-sans selection:bg-blue-200/60 pb-16">

        <div class="fixed top-0 w-full z-40 ia-topbar">
            <div class="max-w-5xl mx-auto px-4 py-4">
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-3">
                        <button onclick="state.step=0;render()" class="text-slate-500 hover:text-slate-950 transition-colors">
                            <i data-lucide="arrow-left" class="w-4 h-4"></i>
                        </button>
                        <span class="text-slate-950 text-sm font-semibold tracking-tight">Setup Interview</span>
                    </div>
                    <span class="text-slate-500 text-xs font-mono">Step 1 of 5</span>
                </div>
                <div class="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                    <div class="bg-blue-600 h-1.5 rounded-full transition-all duration-500" style="width:20%"></div>
                </div>
            </div>
        </div>

        <div class="max-w-5xl mx-auto px-4 pt-28">
            <div class="grid lg:grid-cols-[0.85fr_1.15fr] gap-6 items-start">
            <aside class="ia-card p-6">
                <div class="ia-chip mb-5"><i data-lucide="route" class="w-3.5 h-3.5 text-blue-600"></i> Practice roadmap</div>
                <h1 class="text-3xl font-bold text-slate-950 mb-3 tracking-tight">Configure session</h1>
                <p class="text-slate-600 text-sm leading-6 mb-6">Upload your resume and choose a target role. The next screen extracts skills and generates tailored questions.</p>
                <div class="space-y-3">
                    ${['Resume upload', 'Profile analysis', 'Interview setup', 'Live session', 'Report review'].map((item, i) => `
                        <div class="flex items-center gap-3 ${i === 0 ? 'text-slate-950' : 'text-slate-500'}">
                            <span class="w-7 h-7 rounded-lg ${i === 0 ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-500'} flex items-center justify-center text-xs font-bold">${i + 1}</span>
                            <span class="text-sm font-semibold">${item}</span>
                        </div>
                    `).join('')}
                </div>
            </aside>

            <section class="ia-card p-6 sm:p-8">


            <div class="mb-8">
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Candidate Name</label>
                <input type="text" id="nameInput" placeholder="e.g., Goutham" value="${escapeAttr(state.candidateName)}"
                    class="ia-input w-full px-4 py-2.5 text-sm placeholder:text-slate-400"
                    onchange="state.candidateName=this.value">
            </div>


            <div class="mb-8">
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Resume Document</label>
                <div id="dropZone" onclick="document.getElementById('fileInput').click()"
                    class="border border-dashed rounded-lg p-8 text-center cursor-pointer transition-all
                           ${state.resumeFile ? 'border-blue-300 bg-blue-50' : 'border-slate-300 bg-slate-50 hover:border-blue-400 hover:bg-blue-50/70'}">
                    <input type="file" id="fileInput" accept=".pdf,.doc,.docx" onchange="handleFileUpload(this)" class="hidden">
                    <div id="uploadContent">
                        ${state.resumeFile ? `
                            <div class="flex items-center justify-center gap-4">
                                <div class="w-10 h-10 bg-blue-600 text-white rounded-lg flex items-center justify-center">
                                    <i data-lucide="file-text" class="w-5 h-5"></i>
                                </div>
                                <div class="text-left">
                                    <div class="text-slate-950 text-sm font-semibold">${escapeHtml(state.resumeFileName)}</div>
                                    <div class="text-slate-500 text-xs mt-1">Click to replace file</div>
                                </div>
                            </div>
                        ` : `
                            <div class="w-12 h-12 bg-white rounded-lg border border-slate-200 flex items-center justify-center mx-auto mb-4 shadow-sm">
                                <i data-lucide="upload-cloud" class="w-5 h-5 text-blue-600"></i>
                            </div>
                            <div class="text-slate-950 text-sm font-semibold mb-1">Click to upload or drag and drop</div>
                            <div class="text-slate-500 text-xs">PDF, DOCX (max 5MB)</div>
                        `}
                    </div>
                </div>
            </div>


            <div class="mb-12">
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-3">Target Role</label>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    ${state.jobRoles.map(role => `
                    <button onclick="selectJobRole('${escapeJsString(role)}')"
                        class="p-3 rounded-lg border text-center transition-all text-xs font-semibold
                               ${state.jobRole === role
                                   ? 'border-blue-600 bg-blue-600 text-white'
                                   : 'border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:text-slate-950'}">
                        ${escapeHtml(role)}
                    </button>
                    `).join('')}
                </div>
            </div>


            <button onclick="startAnalysis()" id="continueBtn"
                class="w-full py-3.5 rounded-lg text-sm font-semibold transition-colors flex items-center justify-center gap-2
                       ${(!state.resumeFile || !state.jobRole)
                           ? 'bg-slate-100 text-slate-400 cursor-not-allowed border border-slate-200'
                           : 'ia-button-primary'}"
                ${(!state.resumeFile || !state.jobRole) ? 'disabled' : ''}>
                Continue <i data-lucide="arrow-right" class="w-4 h-4"></i>
            </button>
            </section>
            </div>
        </div>
    </div>
    `;

    _attachDropZone();
}



async function handleFileUpload(input) {
    if (input.files.length) {
        const file = input.files[0];
        state.resumeFile     = file;
        state.resumeFileName = file.name;


        if (!state.candidateName) {
            let base = state.resumeFileName.split('.')[0];
            base = base.replace(/[-_]/g, ' ');
            base = base.replace(/resume|cv|biodata|pdf/gi, '').trim();
            if (base) {
                state.candidateName = base.charAt(0).toUpperCase() + base.slice(1);
            }
        }


        state.tempExtracted = null;

        // pdf.js can only read PDFs. This used to run over every file: a .docx
        // threw, and the catch wrote a `Resume PDF: <filename>` placeholder that
        // was non-empty, got sent, and was preferred by the server over its own
        // DOCX extractor — so the interview was generated from a filename.
        // DOCX now goes to the server, which walks the document's tables (where
        // resumes keep skills and contact details).
        if (!/\.pdf$/i.test(file.name)) {
            state.resumeRawText = '';
            console.info('Non-PDF upload; the server will extract the text.');
            renderUpload();
            return;
        }

        state.resumeRawText = "Extracting text from PDF...";
        renderUpload();

        try {
            state.resumeRawText = await extractTextFromPDF(file);
            console.log("PDF parsed successfully. Characters:", state.resumeRawText.length);
        } catch (e) {
            // A failed parse must leave this empty, not filled with a
            // placeholder: empty is what makes the server fall back to its own
            // extractor instead of interviewing the candidate about their
            // filename.
            console.error("PDF parsing error", e);
            state.resumeRawText = '';
        }

        renderUpload();
    }
}

function selectJobRole(role) {
    state.jobRole = role;
    renderUpload();
}


async function uploadResumeToBackend() {
    try {
        const formData = new FormData();
        formData.append('resume', state.resumeFile);
        formData.append('job_role', state.jobRole);
        // The picker on the setup screen now reaches the generation prompt. It
        // previously set browser state that nothing sent anywhere.
        formData.append('difficulty', state.difficulty || 'medium');
        // Only offered for PDFs. pdf.js used to be run over every file type; a
        // .docx threw, the catch stored a "Resume PDF: <filename>" placeholder,
        // and that non-empty string was sent and preferred by the server, so
        // the interview was generated from a filename. The server rejects
        // client text for non-PDFs now, but not sending it is clearer.
        if (state.resumeRawText && /\.pdf$/i.test(state.resumeFileName || '')) {
            formData.append('resume_text', state.resumeRawText);
        }

        const response = await API.uploadResume(formData);

        if (response.status === 'success') {

            state.sessionId = response.session_id;
            state.totalQuestions = response.total_questions;
            state.turn = typeof response.turn === 'number' ? response.turn : 0;


            if (response.questions && response.questions.length > 0) {
                state.questions = response.questions.map((q, idx) => ({
                    id: idx + 1,
                    text: q.primary_question,
                    category: q.category,
                    name: q.name,
                    primary_question: q.primary_question,
                    context: q.context,
                    difficulty_level: q.difficulty_level,
                    ideal: `Context: ${q.context}`,
                    concepts: []
                }));
            }

            console.log('Resume uploaded successfully, session created:', state.sessionId);
            console.log('Loaded questions:', state.questions.length);
        } else {
            console.error('Resume upload failed:', response);
        }
    } catch (error) {
        console.error('Error uploading resume:', error);
    }
}

function loadSampleResume(name, role, skills, projects, experience) {
    state.candidateName = name;
    state.jobRole = role;
    state.resumeFileName = `${name}_Resume.pdf`;
    state.resumeFile = { name: state.resumeFileName, size: 124500 };


    state.resumeRawText = `
        CANDIDATE: ${name}
        TARGET ROLE: ${role}
        EXPERIENCE: ${experience}
        SKILLS DETECTED: ${skills.join(', ')}
        COMPLETED PROJECTS:
        - ${projects.join('\n        - ')}
    `.trim();

    state.tempExtracted = { skills, projects, experience };
    renderUpload();
}


async function extractTextFromPDF(file) {
    const arrayBuffer = await file.arrayBuffer();
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';

    const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
    const pdf = await loadingTask.promise;
    let fullText = '';

    for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const textContent = await page.getTextContent();
        const pageText = textContent.items.map(item => item.str).join(' ');
        fullText += pageText + '\n';
    }
    return fullText.trim();
}

function startAnalysis() {
    if (!state.resumeFile || !state.jobRole) return;

    // -> setup (difficulty). The upload no longer fires here: the questions are
    // generated after the candidate has chosen an intensity, which is the whole
    // reason that picker can now affect anything.
    state.step = 2;
    render();
}



function _attachDropZone() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;
    dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('border-accent-600'); });
    dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('border-accent-600'); });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('border-accent-600');
        if (e.dataTransfer.files.length) {
            state.resumeFile     = e.dataTransfer.files[0];
            state.resumeFileName = state.resumeFile.name;
            state.tempExtracted = null;
            renderUpload();
        }
    });
}

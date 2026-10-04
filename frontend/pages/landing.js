

function renderLanding() {
    // Structural check, not proof of authentication: a token signed with a
    // rotated secret still decodes and still looks unexpired. hasUsableToken()
    // clears the obviously-dead cases; verifySession() below asks the server
    // about the rest. Previously this tested only that *a string existed*, so a
    // stale token rendered a signed-in header with no route to the login screen
    // while every API call 401'd.
    const isAuthed = API.hasUsableToken();

    if (isAuthed && !renderLanding._verified) {
        renderLanding._verified = true;
        API.verifySession().then(ok => {
            if (!ok && state.step === 0) render();   // token was rejected: re-render logged out
        });
    }

    const features = [
        { icon: 'file-search', title: 'Resume-aware questions', text: 'Turns your resume into targeted interview prompts across projects, skills, and role expectations.' },
        { icon: 'messages-square', title: 'Live interview dialogue', text: 'Practice in a structured session with voice input, follow-ups, and an interviewer-style conversation.' },
        { icon: 'scan-face', title: 'Focus monitoring', text: 'Camera and object checks surface eye contact, presence, and suspicious-session signals.' },
        { icon: 'bar-chart-3', title: 'Skill scoring', text: 'Technical accuracy, communication, confidence, problem solving, and resume knowledge are scored together.' },
        { icon: 'route', title: 'Learning roadmap', text: 'Reports convert results into practical next steps so each practice session improves the next one.' },
        { icon: 'shield-check', title: 'Admin visibility', text: 'Admins can review users, sessions, statuses, and performance from a compact operational view.' }
    ];

    const modules = [
        { level: 'Warmup', title: 'Profile parsing', meta: 'Resume + role', progress: 88, color: 'bg-blue-600' },
        { level: 'Core', title: 'Technical depth', meta: 'Projects + skills', progress: 72, color: 'bg-emerald-500' },
        { level: 'Live', title: 'Presence signals', meta: 'Camera + audio', progress: 64, color: 'bg-amber-500' },
        { level: 'Review', title: 'Report analysis', meta: 'Actions + score', progress: 94, color: 'bg-rose-500' }
    ];

    app.innerHTML = `
    <div class="ia-page font-sans selection:bg-blue-200/60">
        <nav class="fixed top-0 w-full z-50 ia-topbar">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex items-center justify-between h-16">
                    <button onclick="state.step=0;render()" class="flex items-center gap-3">
                        <span class="w-9 h-9 rounded-lg bg-slate-950 text-white flex items-center justify-center">
                            <i data-lucide="brain-circuit" class="w-5 h-5"></i>
                        </span>
                        <span class="text-slate-950 font-semibold tracking-tight">InterviewAI</span>
                    </button>
                    <div class="hidden md:flex items-center gap-7">
                        <a href="#features" class="nav-link text-sm font-medium text-slate-500 hover:text-slate-950 hover:bg-slate-100 px-3 py-1.5 rounded-md transition-all duration-200" aria-label="Jump to features">Features</a>
                        <a href="#how-it-works" class="nav-link text-sm font-medium text-slate-500 hover:text-slate-950 hover:bg-slate-100 px-3 py-1.5 rounded-md transition-all duration-200" aria-label="Jump to how it works">How it works</a>
                        <a href="#roadmap" class="nav-link text-sm font-medium text-slate-500 hover:text-slate-950 hover:bg-slate-100 px-3 py-1.5 rounded-md transition-all duration-200" aria-label="Jump to roadmap">Roadmap</a>
                        <a href="#faq" class="nav-link text-sm font-medium text-slate-500 hover:text-slate-950 hover:bg-slate-100 px-3 py-1.5 rounded-md transition-all duration-200" aria-label="Jump to FAQ">FAQ</a>
                    </div>
                    <div class="flex items-center gap-3">
                        ${isAuthed ? `
                            <button onclick="state.step=8;render()" class="ia-button-secondary px-4 py-2 text-sm font-semibold hover:bg-slate-50 transition-colors">Dashboard</button>
                            <button onclick="logoutUser()" class="text-sm font-semibold text-slate-500 hover:text-slate-950 hover:bg-slate-100 px-3 py-1.5 rounded-md transition-colors">Logout</button>
                        ` : `
                            <button onclick="openAuthModal('login')" class="hidden sm:inline text-sm font-semibold text-slate-500 hover:text-slate-950 hover:bg-slate-100 px-3 py-1.5 rounded-md transition-colors">Log in</button>
                            <button onclick="openAuthModal('signup')" class="ia-button-primary px-4 py-2 text-sm font-semibold flex items-center gap-2 hover:shadow-lg transition-shadow">
                                Sign up <i data-lucide="arrow-right" class="w-4 h-4"></i>
                            </button>
                        `}
                    </div>
                </div>
            </div>
        </nav>

        <main class="pt-24">
            <section class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20 scroll-mt-24">
                <div class="grid lg:grid-cols-[1.02fr_0.98fr] gap-10 items-center">
                    <div class="py-10">
                        <div class="ia-chip mb-6">
                            <i data-lucide="sparkles" class="w-3.5 h-3.5 text-blue-600"></i>
                            Structured technical interview practice
                        </div>
                        <h1 class="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-slate-950 leading-[1.04] max-w-3xl">
                            Practice interviews like a focused learning roadmap.
                        </h1>
                        <p class="text-lg text-slate-600 leading-8 mt-6 max-w-2xl">
                            Upload a resume, run a realistic session, and get a report that connects technical depth, communication, and focus into a clear next practice plan.
                        </p>
                        <div class="flex flex-col sm:flex-row gap-3 mt-8">
                            <button onclick="${isAuthed ? 'resetState();state.step=1;render()' : 'openAuthModal(\'signup\')'}" class="ia-button-primary px-5 py-3 text-sm font-semibold flex items-center justify-center gap-2 w-max">
                                Start interview <i data-lucide="play" class="w-4 h-4"></i>
                            </button>
                        </div>
                    </div>

                    <div class="ia-card p-4 sm:p-5">
                        <div class="bg-slate-950 rounded-lg text-white overflow-hidden">
                            <div class="flex items-center justify-between px-4 py-3 border-b border-white/10">
                                <div class="flex items-center gap-2">
                                    <span class="w-2.5 h-2.5 rounded-full bg-rose-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                                </div>
                                <span class="text-[10px] uppercase tracking-widest text-slate-400 font-mono">Interview workspace</span>
                            </div>
                            <div class="grid sm:grid-cols-[1.2fr_0.8fr] gap-4 p-4">
                                <div class="rounded-lg bg-slate-900 border border-white/10 aspect-video flex items-center justify-center relative overflow-hidden">
                                    <div class="absolute inset-4 border border-emerald-400/50 rounded-lg"></div>
                                    <div class="text-center">
                                        <i data-lucide="scan-face" class="w-10 h-10 mx-auto text-emerald-300 mb-3"></i>
                                        <p class="text-sm font-semibold">Face tracked</p>
                                        <p class="text-xs text-slate-400 mt-1">Focus 94%</p>
                                    </div>
                                </div>
                                <div class="space-y-3">
                                    ${modules.map(m => `
                                        <div class="rounded-lg bg-white text-slate-900 p-3">
                                            <div class="flex items-center justify-between mb-2">
                                                <span class="text-[10px] uppercase tracking-widest text-slate-500 font-bold">${m.level}</span>
                                                <span class="text-xs font-mono text-slate-500">${m.progress}%</span>
                                            </div>
                                            <div class="text-sm font-semibold">${m.title}</div>
                                            <div class="text-xs text-slate-500 mt-0.5">${m.meta}</div>
                                            <div class="h-1.5 bg-slate-100 rounded-full mt-3 overflow-hidden">
                                                <div class="${m.color} h-full rounded-full" style="width:${m.progress}%"></div>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <section id="features" class="border-y border-slate-200 bg-white/72">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    <div class="flex flex-col md:flex-row md:items-end md:justify-between gap-5 mb-10">
                        <div>
                            <p class="text-sm font-bold text-blue-600 uppercase tracking-widest">Features</p>
                            <h2 class="text-3xl font-bold tracking-tight text-slate-950 mt-2">Everything needed for one complete practice loop.</h2>
                        </div>
                        <p class="text-slate-600 max-w-xl">The interface is organized around the same flow candidates actually follow: prepare, interview, evaluate, and improve.</p>
                    </div>
                    <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${features.map(item => `
                            <div class="ia-card p-5 hover:-translate-y-0.5 transition-transform">
                                <div class="w-10 h-10 rounded-lg bg-slate-950 text-white flex items-center justify-center mb-4">
                                    <i data-lucide="${item.icon}" class="w-5 h-5"></i>
                                </div>
                                <h3 class="font-semibold text-slate-950">${item.title}</h3>
                                <p class="text-sm text-slate-600 leading-6 mt-2">${item.text}</p>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </section>

            <section id="how-it-works" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                <div class="grid lg:grid-cols-[0.8fr_1.2fr] gap-10">
                    <div>
                        <p class="text-sm font-bold text-emerald-600 uppercase tracking-widest">How it works</p>
                        <h2 class="text-3xl font-bold tracking-tight text-slate-950 mt-2">Four steps, no clutter.</h2>
                        <p class="text-slate-600 leading-7 mt-4">The flow borrows from guide-style learning products: each step is explicit, progress is visible, and the report feeds the next session.</p>
                    </div>
                    <div class="grid sm:grid-cols-2 gap-4">
                        ${[
                            ['Upload profile', 'Add your resume and target role so questions match your background.', 'upload-cloud'],
                            ['Generate session', 'The backend extracts skills and creates tailored prompts.', 'wand-sparkles'],
                            ['Interview live', 'Answer by voice or text while the system tracks performance signals.', 'radio'],
                            ['Review report', 'Use a scorecard and improvement plan to choose what to practice next.', 'clipboard-check']
                        ].map((s, i) => `
                            <div class="ia-card ia-module-rail p-5 pl-6">
                                <div class="flex items-center justify-between mb-4">
                                    <span class="text-xs font-mono text-slate-500">0${i + 1}</span>
                                    <i data-lucide="${s[2]}" class="w-5 h-5 text-slate-500"></i>
                                </div>
                                <h3 class="font-semibold text-slate-950">${s[0]}</h3>
                                <p class="text-sm text-slate-600 leading-6 mt-2">${s[1]}</p>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </section>

            <section id="roadmap" class="bg-slate-950 text-white">
                <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    <div class="grid lg:grid-cols-3 gap-5">
                        <div class="lg:col-span-1">
                            <p class="text-sm font-bold text-blue-300 uppercase tracking-widest">Roadmap</p>
                            <h2 class="text-3xl font-bold tracking-tight mt-2">Track readiness like modules.</h2>
                        </div>
                        <div class="lg:col-span-2 grid sm:grid-cols-3 gap-4">
                            ${[
                                ['12', 'Question types', 'list-checks'],
                                ['6', 'Scored dimensions', 'gauge'],
                                ['4', 'Session stages', 'route']
                            ].map(s => `
                                <div class="rounded-lg border border-white/10 bg-white/5 p-5">
                                    <i data-lucide="${s[2]}" class="w-5 h-5 text-blue-300 mb-5"></i>
                                    <div class="text-4xl font-bold">${s[0]}</div>
                                    <div class="text-sm text-slate-300 mt-1">${s[1]}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </section>

            <section id="faq" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                <div class="grid md:grid-cols-3 gap-4">
                    ${[
                        ['Do I need a webcam?', 'No. The interview still works with text and audio, but focus metrics are richer with camera access.'],
                        ['Can I use it for system design?', 'Yes. Questions are generated from your resume, role, and difficulty setting.'],
                        ['Is there an admin view?', 'Yes. Admin users can review registered users and completed interview sessions.']
                    ].map(item => `
                        <div class="ia-card p-5">
                            <h3 class="font-semibold text-slate-950">${item[0]}</h3>
                            <p class="text-sm text-slate-600 leading-6 mt-2">${item[1]}</p>
                        </div>
                    `).join('')}
                </div>
            </section>
        </main>


        <div id="authModal" role="dialog" aria-modal="true" aria-labelledby="authModalTitle" onclick="if(event.target === this) closeAuthModal()" class="fixed inset-0 z-[100] hidden items-center justify-center bg-slate-900/40 backdrop-blur-sm opacity-0 transition-opacity duration-300 px-4">
            <div onclick="event.stopPropagation()" class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden transform scale-95 transition-transform duration-300">
                <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                    <h3 id="authModalTitle" class="text-lg font-bold text-slate-950">Log in</h3>
                    <button type="button" aria-label="Close authentication dialog" onclick="closeAuthModal()" class="w-8 h-8 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors flex items-center justify-center">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <div class="p-6">
                    <div id="authErrorBox" class="hidden border border-rose-200 bg-rose-50 text-rose-700 p-3 rounded-lg text-sm mb-5"></div>
                    <form id="authModalForm" class="space-y-4">
                        <input type="hidden" id="authModalType" value="login">
                        <div id="usernameGroup">
                            <label class="block text-sm font-semibold text-slate-700 mb-1.5">Username</label>
                            <div class="relative">
                                <i data-lucide="user" class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2"></i>
                                <input type="text" id="authUsername" required class="ia-input w-full pl-10 pr-3 py-2.5 text-sm" placeholder="Enter username">
                            </div>
                        </div>
                        <div id="emailGroup" class="hidden">
                            <label class="block text-sm font-semibold text-slate-700 mb-1.5">Email</label>
                            <div class="relative">
                                <i data-lucide="mail" class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2"></i>
                                <input type="email" id="authEmail" class="ia-input w-full pl-10 pr-3 py-2.5 text-sm" placeholder="you@example.com">
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-semibold text-slate-700 mb-1.5">Password</label>
                            <div class="relative">
                                <i data-lucide="key-round" class="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2"></i>
                                <input type="password" id="authPassword" required class="ia-input w-full pl-10 pr-3 py-2.5 text-sm" placeholder="Enter password">
                            </div>
                        </div>
                        <button type="submit" class="ia-button-primary w-full py-3 text-sm font-semibold flex items-center justify-center gap-2">
                            <span id="authSubmitText">Log in</span> <i data-lucide="arrow-right" class="w-4 h-4"></i>
                        </button>
                    </form>
                    <div class="mt-6 text-center text-sm text-slate-600">
                        <span id="authToggleText">Don't have an account?</span>
                        <button onclick="toggleAuthModalType()" id="authToggleButton" class="text-slate-950 font-semibold hover:underline">Sign up</button>
                    </div>
                </div>
            </div>
        </div>
    </div>
    `;

    window.openAuthModal = (type) => {
        const modal = document.getElementById('authModal');
        const modalInner = modal.querySelector('div');
        const title = document.getElementById('authModalTitle');
        const typeInput = document.getElementById('authModalType');
        const emailGroup = document.getElementById('emailGroup');
        const emailInput = document.getElementById('authEmail');
        const submitText = document.getElementById('authSubmitText');
        const toggleText = document.getElementById('authToggleText');
        const toggleButton = document.getElementById('authToggleButton');
        const errorBox = document.getElementById('authErrorBox');

        errorBox.classList.add('hidden');
        typeInput.value = type;

        if (type === 'signup') {
            title.textContent = 'Create account';
            emailGroup.classList.remove('hidden');
            emailInput.required = true;
            submitText.textContent = 'Sign up';
            toggleText.textContent = 'Already have an account?';
            toggleButton.textContent = 'Log in';
        } else {
            title.textContent = 'Welcome back';
            emailGroup.classList.add('hidden');
            emailInput.required = false;
            submitText.textContent = 'Log in';
            toggleText.textContent = "Don't have an account?";
            toggleButton.textContent = 'Sign up';
        }

        modal.classList.remove('hidden');
        modal.classList.add('flex');
        document.body.classList.add('overflow-hidden');
        setTimeout(() => {
            modal.classList.remove('opacity-0');
            modalInner.classList.remove('scale-95');
        }, 10);
    };

    window.closeAuthModal = () => {
        const modal = document.getElementById('authModal');
        const modalInner = modal.querySelector('div');
        modal.classList.add('opacity-0');
        modalInner.classList.add('scale-95');
        setTimeout(() => {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            document.body.classList.remove('overflow-hidden');
        }, 300);
    };

    window.toggleAuthModalType = () => {
        const currentType = document.getElementById('authModalType').value;
        window.openAuthModal(currentType === 'login' ? 'signup' : 'login');
    };

    if (window.lucide) { setTimeout(() => lucide.createIcons(), 10); }

    setTimeout(() => {

        const form = document.getElementById('authModalForm');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                const type = document.getElementById('authModalType').value;
                const username = document.getElementById('authUsername').value;
                const password = document.getElementById('authPassword').value;
                const errorBox = document.getElementById('authErrorBox');

                try {
                    let response;
                    if (type === 'login') {
                        const formData = new FormData();
                        formData.append('username', username);
                        formData.append('password', password);
                        response = await fetch('/api/auth/login', { method: 'POST', body: formData });
                    } else {
                        const email = document.getElementById('authEmail').value;
                        response = await fetch('/api/auth/signup', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ username, email, password })
                        });
                    }
                    const data = await response.json();

                    if (response.ok) {
                        localStorage.setItem('interviewai_token', data.access_token);
                        window.location.reload();
                    } else {
                        // FastAPI returns `detail` as a string for HTTPException but as an
                        // array of error objects for a 422 validation failure. Assigning
                        // that array to textContent rendered "[object Object]" and hid the
                        // actual reason. formatApiError() already existed in utils.js for
                        // exactly this and was simply never wired in here.
                        errorBox.textContent = formatApiError(
                            data, type === 'login' ? 'Login failed' : 'Signup failed'
                        );
                        errorBox.classList.remove('hidden');
                    }
                } catch (error) {
                    errorBox.textContent = 'Network error occurred';
                    errorBox.classList.remove('hidden');
                }
            });
        }


        const sections = document.querySelectorAll('section[id]');
        const navLinks = document.querySelectorAll('.nav-link');

        const setActiveNav = (id) => {
            navLinks.forEach(link => {
                const active = link.getAttribute('href') === '#' + id;
                link.classList.toggle('is-active', active);
                link.classList.toggle('text-blue-600', active);
                link.classList.toggle('bg-blue-50', active);
                link.classList.toggle('text-slate-500', !active);
            });
        };

        navLinks.forEach(link => link.addEventListener('click', () => setActiveNav(link.getAttribute('href').slice(1))));

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    setActiveNav(entry.target.id);
                }
            });
        }, { rootMargin: '-20% 0px -60% 0px' });

        sections.forEach(section => observer.observe(section));
        window.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !document.getElementById('authModal').classList.contains('hidden')) closeAuthModal();
        });
    }, 50);
}

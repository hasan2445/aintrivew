


const API = {
    BASE_URL: '/api',

    getHeaders(extraHeaders = {}) {
        const token = localStorage.getItem('interviewai_token');
        const headers = { ...extraHeaders };
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    },


    async uploadResume(formData) {
        try {
            const response = await fetch(`${this.BASE_URL}/upload-resume`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData
            });
            if (response.status === 401) {
                this.handleUnauthorized();
                return { status: 'error', detail: 'Unauthorized' };
            }
            return await response.json();
        } catch (error) {
            console.error('Resume upload error:', error);
            throw error;
        }
    },

    handleUnauthorized() {
        if (typeof state !== 'undefined' && typeof render !== 'undefined') {
            logoutUser();
        } else {
            localStorage.removeItem('interviewai_token');
            window.location.reload();
        }
    },

    /**
     * Single place where every authenticated call is made.
     *
     * Previously only uploadResume checked for 401, so an expired token during a
     * live interview produced a silent failure instead of sending the user back
     * to the login screen. This also normalises non-JSON error bodies (e.g. a
     * proxy's HTML 502 page) into a usable object rather than throwing on parse.
     */
    async _request(path, { method = 'GET', body = null, json = false } = {}) {
        const extra = json ? { 'Content-Type': 'application/json' } : {};
        const response = await fetch(`${this.BASE_URL}${path}`, {
            method,
            headers: this.getHeaders(extra),
            body
        });

        if (response.status === 401) {
            this.handleUnauthorized();
            return { status: 'error', detail: 'Unauthorized' };
        }

        let data;
        try {
            data = await response.json();
        } catch (parseError) {
            return {
                status: 'error',
                detail: `Server returned an unexpected response (HTTP ${response.status})`
            };
        }

        if (!response.ok) {
            return {
                status: 'error',
                httpStatus: response.status,
                detail: (typeof formatApiError === 'function')
                    ? formatApiError(data, `Request failed (HTTP ${response.status})`)
                    : (data && data.detail) || `Request failed (HTTP ${response.status})`
            };
        }
        return data;
    },


    async getCurrentQuestion(sessionId) {
        return this._request(`/session/${encodeURIComponent(sessionId)}/question`);
    },


    async submitAnswer(sessionId, answer, turn) {
        // `turn` makes the submission idempotent: the server rejects a turn it
        // has already consumed with a 409, before either LLM call, instead of
        // letting two concurrent read-modify-writes lose an answer.
        const payload = { answer };
        if (typeof turn === 'number') payload.turn = turn;
        return this._request(`/session/${encodeURIComponent(sessionId)}/answer`, {
            method: 'POST',
            json: true,
            body: JSON.stringify(payload)
        });
    },


    async nextQuestion(sessionId) {
        return this._request(`/session/${encodeURIComponent(sessionId)}/next-question`, {
            method: 'POST'
        });
    },


    async getProgress(sessionId) {
        return this._request(`/session/${encodeURIComponent(sessionId)}/progress`);
    },


    async getScores(sessionId) {
        return this._request(`/session/${encodeURIComponent(sessionId)}/scores`);
    },


    async getComprehensiveReport(sessionId) {
        return this._request(`/session/${encodeURIComponent(sessionId)}/comprehensive-report`);
    },


    /**
     * Report the browser's attention totals. Cumulative, so a dropped report is
     * harmless — the next one carries the same running values.
     */
    async reportAttention(sessionId, stats) {
        return this._request(`/session/${encodeURIComponent(sessionId)}/attention`, {
            method: 'POST',
            json: true,
            body: JSON.stringify(stats)
        });
    },

    async endSession(sessionId) {
        // No score parameter. The browser used to compute the final number and
        // POST it here, overwriting the server's own. The server computes it.
        try {
            return await this._request(`/session/${encodeURIComponent(sessionId)}/end`, {
                method: 'POST'
            });
        } catch (error) {
            console.error('End session error:', error);
            return { status: 'error' };
        }
    },

    /**
     * Renew the access token while the candidate is still authenticated.
     *
     * A fixed expiry hit mid-interview produced a 401, which handleUnauthorized
     * turned into a full logout — clearing the session id and stranding a
     * server-side session that was still alive in Redis for hours.
     */
    async refreshToken() {
        try {
            const response = await fetch(`${this.BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: this.getHeaders()
            });
            if (!response.ok) return false;
            const data = await response.json();
            if (data && data.access_token) {
                localStorage.setItem('interviewai_token', data.access_token);
                return true;
            }
        } catch (error) {
            console.warn('Token refresh failed', error);
        }
        return false;
    },

    /** Seconds until the stored token expires, or null when unreadable. */
    tokenSecondsRemaining() {
        const token = localStorage.getItem('interviewai_token');
        if (!token) return null;
        const parts = token.split('.');
        if (parts.length !== 3) return null;
        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            if (!payload || typeof payload.exp !== 'number') return null;
            return payload.exp - Math.floor(Date.now() / 1000);
        } catch (e) {
            return null;
        }
    },

    /**
     * Cheap local check that a stored token is at least structurally usable.
     *
     * Deliberately NOT proof of authentication: a JWT payload is base64, not
     * encrypted, so a token signed with a different secret still decodes and
     * still reports an unexpired `exp`. Only the server can reject a bad
     * signature — see verifySession(). This catches the malformed and expired
     * cases without a round trip, and self-clears so the UI cannot sit in a
     * half-signed-in state.
     */
    hasUsableToken() {
        const token = localStorage.getItem('interviewai_token');
        if (!token) return false;

        const remaining = this.tokenSecondsRemaining();
        if (remaining === null || remaining <= 0) {
            // Unreadable or expired: not something this app issued, or no
            // longer valid. Drop it rather than rendering a signed-in shell.
            localStorage.removeItem('interviewai_token');
            return false;
        }
        return true;
    },

    /**
     * Ask the server whether the stored token is actually valid.
     *
     * The landing page renders a signed-in header from local state alone and
     * makes no API call, so a token the server would reject — one signed with a
     * rotated JWT_SECRET_KEY, or issued by a different deployment — left the UI
     * showing "Dashboard" with no route back to the login screen while every
     * request 401'd. Returns true when the session is genuinely good.
     */
    async verifySession() {
        if (!this.hasUsableToken()) return false;
        try {
            const response = await fetch(`${this.BASE_URL}/auth/me`, { headers: this.getHeaders() });
            if (response.ok) return true;
            if (response.status === 401) {
                localStorage.removeItem('interviewai_token');
                return false;
            }
        } catch (error) {
            // Network failure is not proof the token is bad; leave it alone.
            console.warn('Could not verify session', error);
        }
        return true;
    },

    /** Refresh when less than `thresholdSeconds` of token life is left. */
    async refreshIfExpiringSoon(thresholdSeconds = 900) {
        const remaining = this.tokenSecondsRemaining();
        if (remaining !== null && remaining > 0 && remaining < thresholdSeconds) {
            return this.refreshToken();
        }
        return false;
    },






    // detectFace removed: /api/detect-face is gone with the server's MediaPipe.

    async detectObjects(frameBlob) {
        const formData = new FormData();
        formData.append('frame', frameBlob, 'frame.jpg');

        try {
            const response = await fetch(`${this.BASE_URL}/detect-objects`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData
            });
            return await response.json();
        } catch (error) {
            console.error('Object detection error:', error);
            return {
                status: 'error',
                object_detection: { status: 'error' }
            };
        }
    },


    async analyzeFrame(frameBlob, sessionId) {
        const formData = new FormData();
        formData.append('frame', frameBlob, 'frame.jpg');
        // Binds the frame to an interview the caller owns, so the server can
        // record its own verdict against the session instead of returning it
        // and forgetting. The integrity penalty is computed from those counters.
        if (sessionId) formData.append('session_id', sessionId);

        try {
            const response = await fetch(`${this.BASE_URL}/analyze-frame`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData
            });
            return await response.json();
        } catch (error) {
            console.error('Frame analysis error:', error);
            return {
                status: 'error',
                cheating_detected: false,
                warnings: []
            };
        }
    },






    async generateSpeech(text, voiceId = 'JBFqnCBsd6RMkjVDRZzb') {
        const formData = new FormData();
        formData.append('text', text);
        formData.append('voice_id', voiceId);

        try {
            const response = await fetch(`${this.BASE_URL}/generate-speech`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: formData
            });
            return await response.json();
        } catch (error) {
            console.error('Speech generation error:', error);
            return {
                status: 'error',
                audio: null
            };
        }
    },


    async getTTSVoices() {
        try {
            const response = await fetch(`${this.BASE_URL}/tts-voices`);
            return await response.json();
        } catch (error) {
            console.error('TTS voices error:', error);
            return {
                status: 'error',
                voices: []
            };
        }
    },


    async healthCheck() {
        try {
            const response = await fetch(`${this.BASE_URL}/health`);
            return await response.json();
        } catch (error) {
            console.error('Health check error:', error);
            return { status: 'unhealthy' };
        }
    }
};


function canvasToBlob(canvas, mimeType = 'image/jpeg', quality = 0.8) {
    return new Promise((resolve) => {
        canvas.toBlob(resolve, mimeType, quality);
    });
}


function playAudioFromBase64(base64String) {
    try {
        const audioData = base64String;
        const audio = new Audio();
        audio.src = 'data:audio/mp3;base64,' + audioData;
        audio.play();
        return audio;
    } catch (error) {
        console.error('Error playing audio:', error);
        return null;
    }
}


function captureFrame(videoElement) {
    const canvas = document.createElement('canvas');
    canvas.width = videoElement.videoWidth;
    canvas.height = videoElement.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoElement, 0, 0);
    return canvas;
}


function captureCanvasFrame(canvasElement) {
    return canvasElement;
}

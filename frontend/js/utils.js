/**
 * Shared helpers. Loaded before every other script.
 *
 * The pages in this app build their markup with template literals and assign it
 * via innerHTML. Any value that originated from a user, a filename, the database
 * or the LLM must be escaped on the way in, or it executes as markup.
 */

/** Escape a value for interpolation into HTML text content. */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Escape a value for interpolation into a quoted HTML attribute. */
function escapeAttr(value) {
    return escapeHtml(value);
}

/**
 * Escape a value for interpolation inside a single-quoted JS string that itself
 * sits in an HTML attribute, e.g. onclick="doThing('${escapeJsString(x)}')".
 */
function escapeJsString(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '\\r')
        .replace(/</g, '\\u003c')
        .replace(/>/g, '\\u003e')
        .replace(/&/g, '\\u0026');
}

/** Format an ISO timestamp for display, tolerating null/invalid values. */
function formatDate(value) {
    if (!value) return '—';
    const d = new Date(value);
    return isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
}

/**
 * FastAPI returns `detail` as a string for HTTPException but as an array of
 * error objects for 422 validation failures. Rendering the raw value showed
 * "[object Object]" to the user.
 */
function formatApiError(data, fallback) {
    const detail = data && data.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
        const messages = detail
            .map(d => {
                if (!d || typeof d.msg !== 'string') return null;
                const msg = d.msg.replace(/^Value error,\s*/, '');
                // Pydantic's built-in constraint messages name the type, not the
                // field ("String should have at least 8 characters"), which does
                // not tell the user *which* input to fix. `loc` carries the field
                // name; prepend it when the message does not already say so.
                const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
                if (field && typeof field === 'string' && field !== 'body'
                    && !msg.toLowerCase().includes(field.toLowerCase())) {
                    const label = field.charAt(0).toUpperCase() + field.slice(1);
                    return `${label}: ${msg.charAt(0).toLowerCase()}${msg.slice(1)}`;
                }
                return msg;
            })
            .filter(Boolean);
        if (messages.length) return messages.join(' ');
    }
    return fallback;
}

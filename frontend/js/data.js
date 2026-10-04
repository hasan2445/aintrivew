/**
 * Static reference data shipped to every visitor.
 *
 * This file used to be 559 lines, roughly 500 of them dead: a hand-written
 * QUESTION_BANK per job role with ideal answers and concept lists, a
 * FOLLOWUP_BANK keyed by topic, and generateQuestions() — the fossil record of
 * the app before question generation moved to the LLM. Nothing called
 * generateQuestions(); the concept lists it fed were read only by
 * evaluateAnswerAgainstIdeal(), which nothing called either. All of it shipped
 * on every page load. What is left is what is actually read.
 */

/** Populates the eight role buttons on the upload screen. */
const JOB_ROLES = [
    'Data Scientist', 'AI Engineer', 'Full Stack Developer', 'Java Developer',
    'ML Engineer', 'Backend Developer', 'DevOps Engineer', 'Cybersecurity Analyst'
];

state.jobRoles = JOB_ROLES;

/** Read by the live speech analysis in interview.js to count filler words. */
const FILLER_WORDS = [
    'um', 'ah', 'like', 'actually', 'basically',
    'you know', 'sort of', 'kind of', 'i mean'
];

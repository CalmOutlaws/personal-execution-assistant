"""Deterministic goal-breakdown suggestions for EXECUTE (V1).

This module has no Flask, SQLite, network, or LLM dependencies. It turns an
already-created goal title into a short list of actionable task titles. The
caller decides what, if anything, to persist later.

AI disclosure (CS50 final project requirement): this module was created with
AI assistance and reviewed and tested by the author.
"""


MAX_SUGGESTIONS = 5
MIN_SUGGESTIONS = 3


def _clean_subject(value):
    """Return a short display subject derived from a goal title."""
    if not isinstance(value, str):
        return ""
    subject = " ".join(value.strip().split())
    if len(subject) > 80:
        subject = subject[:80].rstrip()
    return subject


def _generic_steps(subject):
    """Return domain-neutral steps that work for any goal title."""
    label = subject or "this goal"
    return [
        "Define what done looks like for %s" % label,
        "List the materials or information needed for %s" % label,
        "Complete the first small part of %s" % label,
        "Review progress on %s and adjust the plan" % label,
        "Finish the remaining work for %s" % label,
    ]


# Small keyword map keeps suggestions actionable without claiming deep
# semantic understanding. Matching is case-insensitive substring matching on
# the normalized goal title. Each entry holds up to five step templates where
# {subject} is replaced with the cleaned goal title.
_STEP_TEMPLATES = (
    (("c++", "c plus plus", "cpp"), (
        "Define the {subject} topics to learn",
        "Set up a {subject} development environment",
        "Study the core {subject} language concepts",
        "Practice with small {subject} programs",
        "Review progress and identify the next {subject} topics",
    )),
    (("python",), (
        "Define the {subject} topics to learn",
        "Set up a {subject} development environment",
        "Study the core {subject} language concepts",
        "Practice with small {subject} programs",
        "Review progress and identify the next {subject} topics",
    )),
    (("internship",), (
        "Define target {subject} roles",
        "Prepare or update resume for {subject}",
        "Build or select relevant projects for {subject}",
        "Find suitable {subject} opportunities",
        "Submit applications and track follow-ups",
    )),
    (("job", "career"), (
        "Define target roles for {subject}",
        "Prepare or update resume for {subject}",
        "Build or select relevant work samples",
        "Find suitable openings for {subject}",
        "Submit applications and track follow-ups",
    )),
    (("marathon", "race", "fitness", "gym", "health"), (
        "Define the training outcome for {subject}",
        "Set a weekly training schedule for {subject}",
        "Complete the first week of {subject} training",
        "Track progress for {subject}",
        "Review recovery and adjust the {subject} plan",
    )),
    (("exam", "test", "course", "class", "study"), (
        "List the topics covered by {subject}",
        "Gather notes and materials for {subject}",
        "Study one {subject} topic at a time",
        "Practice with sample questions for {subject}",
        "Review weak areas before {subject}",
    )),
)


def suggest_steps(goal_title, deadline=None):
    """Return 3-5 deterministic suggested task titles for a goal.

    ``deadline`` is accepted for future extensibility but is intentionally
    ignored in V1: individual task due dates are never invented.
    """
    subject = _clean_subject(goal_title)
    lowered = subject.lower()
    for keywords, templates in _STEP_TEMPLATES:
        if any(keyword in lowered for keyword in keywords):
            steps = [template.format(subject=subject) for template in templates]
            return steps[MIN_SUGGESTIONS - 1:MAX_SUGGESTIONS] if len(steps) > MAX_SUGGESTIONS else steps
    return _generic_steps(subject)[:MAX_SUGGESTIONS]

import os
import sqlite3
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db
from breakdown import MAX_SUGGESTIONS, suggest_steps
from recurrence import RECURRENCES, is_valid_recurrence, next_due_at
from parser import parse_input

# AI disclosure (CS50 final project requirement): this project was written with
# the help of an AI coding assistant. AI assistance was used for the task, goal,
# event, commitment, Quick Add interpretation and confirmation, goal breakdown,
# recurring tasks, search and filtering, browser notifications, voice input and
# the associated templates; every change was reviewed and tested by the author.

load_dotenv()

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY is not set. Create a .env file containing a SECRET_KEY "
        "value before starting the application."
    )

app = Flask(__name__)
app.config["SECRET_KEY"] = _secret_key

PRIORITIES = ("low", "medium", "high")

RECURRENCE_OPTIONS = (None,) + RECURRENCES


def _normalize_recurrence(value):
    """Return allowlisted recurrence or None; reject anything else."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in RECURRENCES:
        return text
    return False


def parse_datetime(value):
    """Normalize a datetime-local form value into a SQLite timestamp.

    Returns (timestamp, is_valid). A blank value is valid and becomes None, so
    optional dates are stored as NULL instead of an empty string.
    """
    value = (value or "").strip()

    if not value:
        return None, True

    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S"), True
    except ValueError:
        return None, False


def now_timestamp():
    """The current local time in the same format as a stored timestamp.

    Every date entered through a form is normalized by parse_datetime() into a
    zero-padded "YYYY-MM-DD HH:MM:SS" string, so events can be compared against
    this value directly without a timezone library or an extra dependency.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_owned_goal(goal_id):
    """Return the logged-in user's goal, or abort with a 404.

    Every goal lookup is scoped by the session user_id, so another user's goal
    can never be read or changed by guessing its id.
    """
    connection = get_db()

    goal = connection.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?",
        (goal_id, session["user_id"]),
    ).fetchone()

    connection.close()

    if goal is None:
        abort(404)

    return goal


def load_owned_event(event_id):
    """Return the logged-in user's event, or abort with a 404.

    As with goals, every event lookup is scoped by the session user_id, so
    another user's event can never be read or changed by guessing its id.
    """
    connection = get_db()

    event = connection.execute(
        "SELECT * FROM events WHERE id = ? AND user_id = ?",
        (event_id, session["user_id"]),
    ).fetchone()

    connection.close()

    if event is None:
        abort(404)

    return event


def load_owned_commitment(commitment_id):
    """Return the logged-in user's commitment, or abort with a 404.

    As with goals and events, every commitment lookup is scoped by the session
    user_id, so another user's commitment can never be read or changed by
    guessing its id.
    """
    connection = get_db()

    commitment = connection.execute(
        "SELECT * FROM commitments WHERE id = ? AND user_id = ?",
        (commitment_id, session["user_id"]),
    ).fetchone()

    connection.close()

    if commitment is None:
        abort(404)

    return commitment


def login_required(view):
    """Redirect anonymous users to the login page."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
def index():
    if "user_id" in session:
        connection = get_db()

        # Small dashboard summary: how many goals are still active and what is
        # coming up next. The full analytics dashboard belongs to a later
        # milestone.
        active_goals = connection.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id = ? AND status = 'active'",
            (session["user_id"],),
        ).fetchone()[0]

        now = now_timestamp()

        # Upcoming events are counted and listed for the current user only. The
        # list is capped because this is a summary, not the events page.
        upcoming_event_count = connection.execute(
            "SELECT COUNT(*) FROM events WHERE user_id = ? AND starts_at >= ?",
            (session["user_id"], now),
        ).fetchone()[0]

        upcoming_events = connection.execute(
            """
            SELECT * FROM events
            WHERE user_id = ? AND starts_at >= ?
            ORDER BY starts_at, id
            LIMIT 3
            """,
            (session["user_id"], now),
        ).fetchall()

        # Pending commitments are counted and listed for the current user only.
        # Completed ones are excluded and commitments without a deadline sort
        # last, exactly as the commitment page does.
        pending_commitment_count = connection.execute(
            """
            SELECT COUNT(*) FROM commitments
            WHERE user_id = ? AND status = 'pending'
            """,
            (session["user_id"],),
        ).fetchone()[0]

        next_commitments = connection.execute(
            """
            SELECT * FROM commitments
            WHERE user_id = ? AND status = 'pending'
            ORDER BY (deadline IS NULL), deadline, id
            LIMIT 3
            """,
            (session["user_id"],),
        ).fetchall()

        overdue_tasks = connection.execute(
            """
            SELECT id, title, due_at FROM tasks
            WHERE user_id = ? AND status != 'completed'
                AND due_at IS NOT NULL AND due_at < ?
            ORDER BY due_at, id
            LIMIT 5
            """,
            (session["user_id"], now),
        ).fetchall()

        overdue_commitments = connection.execute(
            """
            SELECT id, title, deadline FROM commitments
            WHERE user_id = ? AND status = 'pending'
                AND deadline IS NOT NULL AND deadline < ?
            ORDER BY deadline, id
            LIMIT 5
            """,
            (session["user_id"], now),
        ).fetchall()

        due_soon_tasks = connection.execute(
            """
            SELECT id, title, due_at FROM tasks
            WHERE user_id = ? AND status != 'completed'
                AND due_at IS NOT NULL AND due_at >= ?
            ORDER BY due_at, id
            LIMIT 5
            """,
            (session["user_id"], now),
        ).fetchall()

        # Notification candidates for the client-side V1 poller: upcoming
        # pending tasks, upcoming events, and overdue pending items. Rendered
        # as data attributes so plain HTML works without JS too.
        notify_tasks = connection.execute(
            """
            SELECT id, title, due_at FROM tasks
            WHERE user_id = ? AND status = 'pending' AND due_at IS NOT NULL
            ORDER BY due_at, id
            LIMIT 10
            """,
            (session["user_id"],),
        ).fetchall()

        notify_events = connection.execute(
            """
            SELECT id, title, starts_at FROM events
            WHERE user_id = ? AND starts_at >= ?
            ORDER BY starts_at, id
            LIMIT 10
            """,
            (session["user_id"], now),
        ).fetchall()

        notify_overdue_tasks = connection.execute(
            """
            SELECT id, title, due_at FROM tasks
            WHERE user_id = ? AND status = 'pending'
                AND due_at IS NOT NULL AND due_at < ?
            ORDER BY due_at, id
            LIMIT 10
            """,
            (session["user_id"], now),
        ).fetchall()

        notify_overdue_commitments = connection.execute(
            """
            SELECT id, title, deadline FROM commitments
            WHERE user_id = ? AND status = 'pending'
                AND deadline IS NOT NULL AND deadline < ?
            ORDER BY deadline, id
            LIMIT 10
            """,
            (session["user_id"], now),
        ).fetchall()

        connection.close()

        return render_template(
            "dashboard.html",
            active_goals=active_goals,
            upcoming_event_count=upcoming_event_count,
            upcoming_events=upcoming_events,
            pending_commitment_count=pending_commitment_count,
            next_commitments=next_commitments,
            overdue_tasks=overdue_tasks,
            overdue_commitments=overdue_commitments,
            due_soon_tasks=due_soon_tasks,
            notify_tasks=notify_tasks,
            notify_events=notify_events,
            notify_overdue_tasks=notify_overdue_tasks,
            notify_overdue_commitments=notify_overdue_commitments,
        )

    return "EXECUTE is running."


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            return "Username and password are required.", 400

        password_hash = generate_password_hash(password)

        connection = get_db()

        try:
            connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.close()
            return "Username already exists.", 400

        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        connection = get_db()

        user = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        connection.close()

        if user is None or not check_password_hash(
            user["password_hash"], password
        ):
            return "Invalid username or password.", 400

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _format_interpretation_time(value):
    if not value:
        return "Not specified"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return "{} at {}:{} {}".format(
            parsed.strftime("%A, %B %d").replace(" 0", " "),
            parsed.strftime("%I").lstrip("0") or "0",
            parsed.strftime("%M"),
            parsed.strftime("%p"),
        )
    except (TypeError, ValueError):
        return value


def _format_interpretation_date(value):
    """Format a stored date-only timestamp without inventing a clock time."""
    parsed = None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, pattern)
            break
        except (TypeError, ValueError):
            continue
    if parsed is None:
        return value
    return parsed.strftime("%A, %B %d").replace(" 0", " ")


def _format_interpretation_when(interpretation):
    """Render the confirmation's When line truthfully.

    Exact timestamps keep the V1 wording. Vague periods such as "evening"
    render as the parsed date followed by the period, never as a fabricated
    exact time.
    """
    if not isinstance(interpretation, dict):
        return "Not specified"

    approximate = interpretation.get("approximate_time")
    if not isinstance(approximate, str):
        approximate = ""
    approximate = approximate.strip().lower()
    if approximate not in ("morning", "afternoon", "evening", "night"):
        approximate = ""

    if interpretation.get("type") == "event":
        exact = interpretation.get("starts_at")
        date_value = interpretation.get("date")
    else:
        exact = interpretation.get("due_at") or interpretation.get("deadline")
        date_value = interpretation.get("date")

    if exact:
        return _format_interpretation_time(exact)
    if date_value:
        formatted = _format_interpretation_date(date_value)
        if approximate:
            return f"{formatted} — {approximate}"
        return formatted
    return "Not specified"


def _quick_add_text(value, limit=1000):
    """Return safely bounded display text from a signed-session preview."""
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _validated_quick_add_preview(interpretation):
    """Validate a session preview before writing; the session is untrusted."""
    if not isinstance(interpretation, dict):
        return None, ["The Quick Add preview is missing or invalid. Please try again."]

    item_type = interpretation.get("type")
    if item_type not in ("task", "event", "commitment", "goal"):
        return None, ["The Quick Add interpretation is not supported."]

    title = _quick_add_text(interpretation.get("title"), 200)
    if not title:
        return None, ["The Quick Add interpretation is missing a title."]

    values = {
        "title": title,
        "description": _quick_add_text(interpretation.get("description")),
        "location": _quick_add_text(interpretation.get("location"), 200),
        "committed_to": _quick_add_text(interpretation.get("committed_to"), 200),
    }
    errors = []
    optional_fields = {
        "task": ("due_at",), "event": ("ends_at",),
        "commitment": ("deadline",), "goal": ("deadline",),
    }
    date_only_fallback_fields = {"due_at", "deadline"}
    for field in optional_fields[item_type]:
        field_value = interpretation.get(field)
        # Vague periods are stored as a parsed date with no exact clock time.
        # For nullable due/deadline columns, persist that date at midnight at
        # this validation boundary; the preview above remains date-plus-period.
        if (field in date_only_fallback_fields
                and (field_value is None or str(field_value).strip() == "")):
            field_value = interpretation.get("date")
        timestamp, valid = parse_datetime(field_value)
        if not valid:
            errors.append(f"The interpreted {field.replace('_', ' ')} is invalid.")
        values[field] = timestamp

    if item_type == "event":
        starts_value = interpretation.get("starts_at")
        if starts_value is None or str(starts_value).strip() == "":
            # events.starts_at is NOT NULL in the existing schema, so a
            # date-only/vague event is stored at midnight here without changing
            # the schema or presenting that midnight as an exact event time.
            starts_value = interpretation.get("date")
        starts_at, valid = parse_datetime(starts_value)
        if not valid or starts_at is None:
            errors.append("The interpreted event start date and time is required.")
        values["starts_at"] = starts_at
        if values["ends_at"] and starts_at and values["ends_at"] < starts_at:
            errors.append("The interpreted event must not end before it starts.")

    if errors:
        return None, errors
    return {"type": item_type, "values": values}, []


def _clear_quick_add_preview():
    session.pop("quick_add_interpretation", None)
    session.pop("quick_add_original_text", None)


@app.route("/quick-add", methods=["GET", "POST"])
@login_required
def quick_add():
    """Interpret a sentence and show a confirmation preview without persisting it."""
    if request.method == "GET":
        _clear_quick_add_preview()
        return render_template("quick_add.html", text="", interpretation=None)

    text = request.form.get("text", "").strip()
    if not text:
        return render_template(
            "quick_add.html", text="", interpretation=None,
            error="Please enter what you want to add.",
        ), 400

    interpretation = parse_input(text)
    if interpretation.get("type") == "unknown":
        return render_template(
            "quick_add.html", text=text, interpretation=interpretation,
            error=interpretation.get("error"),
        )

    interpretation["display_when"] = _format_interpretation_when(interpretation)
    session["quick_add_interpretation"] = interpretation
    session["quick_add_original_text"] = text
    return render_template(
        "quick_add_confirmation.html", text=text, interpretation=interpretation
    )


@app.route("/quick-add/confirm", methods=["POST"])
@login_required
def confirm_quick_add():
    """Persist one revalidated Quick Add preview for the current session user."""
    original_text = _quick_add_text(session.get("quick_add_original_text"))
    raw_interpretation = session.get("quick_add_interpretation")
    interpretation, errors = _validated_quick_add_preview(raw_interpretation)
    if errors:
        display = raw_interpretation if isinstance(raw_interpretation, dict) else {
            "type": "unknown", "title": original_text
        }
        return render_template(
            "quick_add_confirmation.html", text=original_text,
            interpretation=display, error=errors[0],
        ), 400

    item_type = interpretation["type"]
    values = interpretation["values"]
    user_id = session["user_id"]
    connection = get_db()
    try:
        if item_type == "task":
            cursor = connection.execute(
                "INSERT INTO tasks (user_id, title, description, due_at, priority, status) "
                "VALUES (?, ?, ?, ?, 'medium', 'pending')",
                (user_id, values["title"], values["description"], values["due_at"]),
            )
            endpoint, label = "task_detail", "Task"
        elif item_type == "event":
            cursor = connection.execute(
                "INSERT INTO events (user_id, title, description, starts_at, ends_at, location) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, values["title"], values["description"], values["starts_at"],
                 values["ends_at"], values["location"]),
            )
            endpoint, label = "event_detail", "Event"
        elif item_type == "commitment":
            cursor = connection.execute(
                "INSERT INTO commitments (user_id, title, description, committed_to, deadline, status) "
                "VALUES (?, ?, ?, ?, ?, 'pending')",
                (user_id, values["title"], values["description"],
                 values["committed_to"], values["deadline"]),
            )
            endpoint, label = "commitment_detail", "Commitment"
        else:
            cursor = connection.execute(
                "INSERT INTO goals (user_id, title, description, deadline, status) "
                "VALUES (?, ?, ?, ?, 'active')",
                (user_id, values["title"], values["description"], values["deadline"]),
            )
            endpoint, label = "goal_detail", "Goal"
        item_id = cursor.lastrowid
        connection.commit()
    finally:
        connection.close()

    _clear_quick_add_preview()
    flash(f"{label} created successfully.")
    return redirect(url_for(endpoint, **{f"{item_type}_id": item_id}))




@app.route("/tasks/<int:task_id>")
@login_required
def task_detail(task_id):
    """Return one owned task for the Quick Add success redirect."""
    connection = get_db()
    task = connection.execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, session["user_id"]),
    ).fetchone()
    connection.close()

    if task is None:
        abort(404)

    return render_template("task_detail.html", task=task)

def _search_like(value):
    """Return a bounded LIKE pattern; empty input matches nothing useful."""
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) > 200:
        text = text[:200]
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "%" + escaped + "%"


@app.route("/search")
@login_required
def search():
    """Search the current user's tasks, goals, events, and commitments."""
    query = (request.args.get("q", "") or "").strip()[:200]
    pattern = _search_like(query)
    task_results, goal_results, event_results, commitment_results = [], [], [], []

    if pattern:
        connection = get_db()
        task_results = connection.execute(
            """
            SELECT id, title, description, due_at, status, priority
            FROM tasks
            WHERE user_id = ?
                AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')
            ORDER BY id DESC
            LIMIT 25
            """,
            (session["user_id"], pattern, pattern),
        ).fetchall()
        goal_results = connection.execute(
            """
            SELECT id, title, description, deadline, status
            FROM goals
            WHERE user_id = ?
                AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')
            ORDER BY id DESC
            LIMIT 25
            """,
            (session["user_id"], pattern, pattern),
        ).fetchall()
        event_results = connection.execute(
            """
            SELECT id, title, description, location, starts_at
            FROM events
            WHERE user_id = ?
                AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'
                     OR location LIKE ? ESCAPE '\\')
            ORDER BY id DESC
            LIMIT 25
            """,
            (session["user_id"], pattern, pattern, pattern),
        ).fetchall()
        commitment_results = connection.execute(
            """
            SELECT id, title, description, committed_to, deadline, status
            FROM commitments
            WHERE user_id = ?
                AND (title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\'
                     OR committed_to LIKE ? ESCAPE '\\')
            ORDER BY id DESC
            LIMIT 25
            """,
            (session["user_id"], pattern, pattern, pattern),
        ).fetchall()
        connection.close()

    return render_template(
        "search.html",
        query=query,
        task_results=task_results,
        goal_results=goal_results,
        event_results=event_results,
        commitment_results=commitment_results,
        searched=bool(pattern),
    )


@app.route("/tasks")
@login_required
def tasks():
    # Lightweight GET filters; invalid values are safely ignored so the
    # default list behavior is unchanged.
    status_filter = (request.args.get("status", "") or "").strip().lower()
    if status_filter not in ("", "all", "pending", "completed"):
        status_filter = ""
    priority_filter = (request.args.get("priority", "") or "").strip().lower()
    if priority_filter not in ("", "all") and priority_filter not in PRIORITIES:
        priority_filter = ""
    recurring_filter = (request.args.get("recurring", "") or "").strip()
    recurring_only = recurring_filter in ("1", "true", "yes", "only")

    connection = get_db()

    # The current user's tasks, pending ones first, then by due date and id.
    # The join is scoped to the same user, so a task can only ever display a
    # goal that its owner actually owns.
    query = """
        SELECT tasks.*, goals.title AS goal_title
        FROM tasks
        LEFT JOIN goals
            ON goals.id = tasks.goal_id AND goals.user_id = tasks.user_id
        WHERE tasks.user_id = ?
    """
    params = [session["user_id"]]
    if status_filter in ("pending", "completed"):
        if status_filter == "pending":
            query += " AND tasks.status != 'completed'"
        else:
            query += " AND tasks.status = 'completed'"
    if priority_filter in PRIORITIES:
        query += " AND tasks.priority = ?"
        params.append(priority_filter)
    if recurring_only:
        query += " AND tasks.recurrence IS NOT NULL AND tasks.recurrence != ''"
    query += """
        ORDER BY (tasks.status = 'completed'), (tasks.due_at IS NULL),
            tasks.due_at, tasks.id
    """
    rows = connection.execute(query, params).fetchall()

    connection.close()

    pending_tasks = [task for task in rows if task["status"] != "completed"]
    completed_tasks = [task for task in rows if task["status"] == "completed"]
    filters = {
        "status": status_filter or "all",
        "priority": priority_filter or "all",
        "recurring": "1" if recurring_only else "",
    }

    return render_template(
        "tasks.html",
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
        filters=filters,
    )


@app.route("/tasks/new", methods=["GET", "POST"])
@login_required
def new_task():
    connection = get_db()

    # Only the logged-in user's own active goals can be linked to a new task.
    active_goals = connection.execute(
        """
        SELECT id, title FROM goals
        WHERE user_id = ? AND status = 'active'
        ORDER BY title, id
        """,
        (session["user_id"],),
    ).fetchall()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_at = request.form.get("due_at", "").strip()
        priority = request.form.get("priority", "").strip().lower()
        goal_id = request.form.get("goal_id", "").strip()
        recurrence = _normalize_recurrence(request.form.get("recurrence", ""))

        errors = []

        if not title:
            errors.append("Title is required.")

        if priority not in PRIORITIES:
            errors.append("Priority must be low, medium or high.")

        if recurrence is False:
            errors.append("Recurrence must be does not repeat, daily, weekly or monthly.")
            recurrence = None

        normalized_due_at, due_at_is_valid = parse_datetime(due_at)

        if not due_at_is_valid:
            errors.append("Due date and time must be a valid date and time.")

        # A task may only be attached to one of this user's own active goals,
        # so a submitted goal id can never link a task to someone else's goal.
        selected_goal_id = None

        if goal_id:
            owned_goal = connection.execute(
                """
                SELECT id FROM goals
                WHERE id = ? AND user_id = ? AND status = 'active'
                """,
                (goal_id, session["user_id"]),
            ).fetchone()

            if owned_goal is None:
                errors.append("Selected goal must be one of your own active goals.")
            else:
                selected_goal_id = owned_goal["id"]

        if errors:
            connection.close()
            return (
                render_template(
                    "task.html",
                    errors=errors,
                    priorities=PRIORITIES,
                    recurrences=RECURRENCES,
                    goals=active_goals,
                ),
                400,
            )

        # user_id always comes from the session, never from the submitted form.
        connection.execute(
            """
            INSERT INTO tasks (user_id, goal_id, title, description, due_at, priority, recurrence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                selected_goal_id,
                title,
                description or None,
                normalized_due_at,
                priority,
                recurrence,
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("tasks"))

    connection.close()

    return render_template(
        "task.html", priorities=PRIORITIES, recurrences=RECURRENCES,
        goals=active_goals,
    )


@app.route("/tasks/<int:task_id>/complete", methods=["POST"])
@login_required
def complete_task(task_id):
    connection = get_db()

    # Ownership check: the task must exist AND belong to the logged-in user,
    # so another user's task can never be modified.
    task = connection.execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, session["user_id"]),
    ).fetchone()

    if task is None:
        connection.close()
        abort(404)

    # Only pending tasks are updated, so completed_at is never overwritten by
    # a repeated submit of the same form.
    if task["status"] != "completed":
        connection.execute(
            """
            UPDATE tasks
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (task_id, session["user_id"]),
        )
        # Recurring tasks spawn exactly one next pending occurrence. Repeat
        # completion is idempotent: if a pending task with the same recurrence
        # and next due date already exists, no second copy is created.
        recurrence = task["recurrence"] if "recurrence" in task.keys() else None
        if recurrence in RECURRENCES:
            next_due = next_due_at(recurrence, task["due_at"])
            existing = None
            if next_due is not None:
                existing = connection.execute(
                    """
                    SELECT id FROM tasks
                    WHERE user_id = ? AND status = 'pending'
                        AND title = ? AND recurrence = ?
                        AND ((due_at IS NULL AND ? IS NULL) OR due_at = ?)
                        AND id != ?
                    """,
                    (session["user_id"], task["title"], recurrence,
                     next_due, next_due, task_id),
                ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO tasks
                        (user_id, goal_id, title, description, due_at,
                         priority, status, recurrence)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (session["user_id"], task["goal_id"], task["title"],
                     task["description"], next_due, task["priority"],
                     recurrence),
                )
        connection.commit()

    connection.close()

    return redirect(url_for("tasks"))


@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id):
    connection = get_db()

    # As with complete_task, the delete is scoped to the logged-in user.
    cursor = connection.execute(
        "DELETE FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, session["user_id"]),
    )
    deleted = cursor.rowcount
    connection.commit()
    connection.close()

    if deleted == 0:
        abort(404)

    return redirect(url_for("tasks"))


@app.route("/goals")
@login_required
def goals():
    connection = get_db()

    # Active goals first, then completed ones. Each card also carries a small
    # progress summary; the subqueries are scoped to the goal owner as well.
    rows = connection.execute(
        """
        SELECT goals.*,
            (
                SELECT COUNT(*) FROM tasks
                WHERE tasks.goal_id = goals.id AND tasks.user_id = goals.user_id
            ) AS task_count,
            (
                SELECT COUNT(*) FROM tasks
                WHERE tasks.goal_id = goals.id AND tasks.user_id = goals.user_id
                    AND tasks.status = 'pending'
            ) AS open_task_count
        FROM goals
        WHERE goals.user_id = ?
        ORDER BY (goals.status = 'completed'), (goals.deadline IS NULL),
            goals.deadline, goals.id
        """,
        (session["user_id"],),
    ).fetchall()

    connection.close()

    active_goals = [goal for goal in rows if goal["status"] != "completed"]
    completed_goals = [goal for goal in rows if goal["status"] == "completed"]

    return render_template(
        "goals.html",
        active_goals=active_goals,
        completed_goals=completed_goals,
    )


@app.route("/goals/new", methods=["GET", "POST"])
@login_required
def new_goal():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline, deadline_is_valid = parse_datetime(request.form.get("deadline", ""))

        errors = []

        if not title:
            errors.append("Title is required.")

        if not deadline_is_valid:
            errors.append("Deadline must be a valid date and time.")

        if errors:
            return render_template("goal_form.html", errors=errors), 400

        connection = get_db()

        # user_id always comes from the session, never from the submitted form.
        connection.execute(
            """
            INSERT INTO goals (user_id, title, description, deadline)
            VALUES (?, ?, ?, ?)
            """,
            (session["user_id"], title, description or None, deadline),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("goals"))

    return render_template("goal_form.html")


@app.route("/goals/<int:goal_id>")
@login_required
def goal_detail(goal_id):
    goal = load_owned_goal(goal_id)

    connection = get_db()

    # Only the current user's own tasks are listed, even if a goal id were
    # somehow reused by another account.
    rows = connection.execute(
        """
        SELECT * FROM tasks
        WHERE user_id = ? AND goal_id = ?
        ORDER BY (status = 'completed'), (due_at IS NULL), due_at, id
        """,
        (session["user_id"], goal_id),
    ).fetchall()

    connection.close()

    open_tasks = [task for task in rows if task["status"] != "completed"]
    completed_tasks = [task for task in rows if task["status"] == "completed"]

    return render_template(
        "goal.html",
        goal=goal,
        open_tasks=open_tasks,
        completed_tasks=completed_tasks,
    )


@app.route("/goals/<int:goal_id>/edit", methods=["GET", "POST"])
@login_required
def edit_goal(goal_id):
    goal = load_owned_goal(goal_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        deadline, deadline_is_valid = parse_datetime(request.form.get("deadline", ""))

        errors = []

        if not title:
            errors.append("Title is required.")

        if not deadline_is_valid:
            errors.append("Deadline must be a valid date and time.")

        if errors:
            return render_template("goal_form.html", errors=errors, goal=goal), 400

        connection = get_db()

        # The update is scoped to the session user and never touches user_id or
        # status, which are changed by their own routes.
        connection.execute(
            """
            UPDATE goals
            SET title = ?, description = ?, deadline = ?
            WHERE id = ? AND user_id = ?
            """,
            (title, description or None, deadline, goal_id, session["user_id"]),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("goal_detail", goal_id=goal_id))

    return render_template("goal_form.html", goal=goal)


@app.route("/goals/<int:goal_id>/complete", methods=["POST"])
@login_required
def complete_goal(goal_id):
    goal = load_owned_goal(goal_id)

    connection = get_db()

    # Only active goals are updated, so a repeated submit is harmless and
    # another user's goal can never be modified.
    if goal["status"] != "completed":
        connection.execute(
            """
            UPDATE goals
            SET status = 'completed'
            WHERE id = ? AND user_id = ?
            """,
            (goal_id, session["user_id"]),
        )
        connection.commit()

    connection.close()

    return redirect(url_for("goal_detail", goal_id=goal_id))


@app.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    connection = get_db()

    # As with tasks, the delete is scoped to the logged-in user. tasks.goal_id
    # is declared ON DELETE SET NULL, so the goal's tasks survive the delete and
    # simply become unlinked rather than being removed.
    cursor = connection.execute(
        "DELETE FROM goals WHERE id = ? AND user_id = ?",
        (goal_id, session["user_id"]),
    )
    deleted = cursor.rowcount
    connection.commit()
    connection.close()

    if deleted == 0:
        abort(404)

    return redirect(url_for("goals"))


@app.route("/goals/<int:goal_id>/breakdown")
@login_required
def goal_breakdown(goal_id):
    """Show deterministic suggested tasks for an owned active goal."""
    goal = load_owned_goal(goal_id)

    if goal["status"] != "active":
        abort(404)

    steps = suggest_steps(goal["title"], goal["deadline"])
    session["goal_breakdown"] = {"goal_id": goal_id, "steps": steps}
    return render_template(
        "goal_breakdown.html", goal=goal, steps=steps, selected=[],
        errors=[], error=None,
    )


@app.route("/goals/<int:goal_id>/breakdown/confirm", methods=["POST"])
@login_required
def confirm_goal_breakdown(goal_id):
    """Create selected suggested tasks as normal tasks linked to the goal."""
    goal = load_owned_goal(goal_id)

    if goal["status"] != "active":
        abort(404)

    pending = session.get("goal_breakdown")
    if (not isinstance(pending, dict) or pending.get("goal_id") != goal_id
            or not isinstance(pending.get("steps"), list)
            or not pending["steps"]):
        steps = suggest_steps(goal["title"], goal["deadline"])
        return render_template(
            "goal_breakdown.html", goal=goal, steps=steps, selected=[],
            errors=[], error="The breakdown suggestions expired. Please try again.",
        ), 400

    selected_indexes = []
    for raw in request.form.getlist("selected"):
        try:
            selected_indexes.append(int(raw))
        except (TypeError, ValueError):
            continue
    selected_indexes = sorted(set(selected_indexes))

    if not selected_indexes:
        return render_template(
            "goal_breakdown.html", goal=goal, steps=pending["steps"],
            selected=[], errors=[],
            error="Select at least one suggested task.",
        ), 400

    if len(selected_indexes) > MAX_SUGGESTIONS:
        return render_template(
            "goal_breakdown.html", goal=goal, steps=pending["steps"],
            selected=[str(index) for index in selected_indexes],
            errors=[], error="Select no more than five suggested tasks.",
        ), 400

    titles = []
    errors = []
    for index in selected_indexes:
        if index < 0 or index >= len(pending["steps"]):
            errors.append("One selected suggestion is invalid.")
            continue
        title = request.form.get("title-%d" % index, "").strip()[:200]
        if not title:
            errors.append("Each selected task needs a title.")
        else:
            titles.append(title)

    if errors:
        return render_template(
            "goal_breakdown.html", goal=goal, steps=pending["steps"],
            selected=[str(index) for index in selected_indexes],
            errors=errors, error=None,
        ), 400

    connection = get_db()
    try:
        for title in titles:
            connection.execute(
                """
                INSERT INTO tasks (user_id, goal_id, title, due_at, priority, status)
                VALUES (?, ?, ?, NULL, 'medium', 'pending')
                """,
                (session["user_id"], goal_id, title),
            )
        connection.commit()
    finally:
        connection.close()

    session.pop("goal_breakdown", None)
    flash("Selected tasks created successfully.")
    return redirect(url_for("goal_detail", goal_id=goal_id))


@app.route("/events")
@login_required
def events():
    connection = get_db()

    # Only the current user's events are ever returned. They are sorted by start
    # time here, then split into upcoming and past in Python so both sections
    # share a single query.
    rows = connection.execute(
        """
        SELECT * FROM events
        WHERE user_id = ?
        ORDER BY starts_at, id
        """,
        (session["user_id"],),
    ).fetchall()

    connection.close()

    now = now_timestamp()

    # Stored timestamps are zero-padded, so comparing them as text is enough to
    # decide whether an event has started yet.
    upcoming_events = [event for event in rows if event["starts_at"] >= now]

    # Past events read newest first, which is how a log is usually reviewed.
    past_events = [event for event in rows if event["starts_at"] < now][::-1]

    return render_template(
        "events.html",
        upcoming_events=upcoming_events,
        past_events=past_events,
    )


def validate_event_form(form):
    """Validate a submitted event form.

    Returns (values, errors). values holds the normalized column values, ready
    to be passed to SQLite as parameters. The event owner is deliberately not
    part of the result: user_id always comes from the session, never from the
    form, so a crafted user_id field cannot reassign an event.
    """
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    location = form.get("location", "").strip()
    starts_at, starts_at_is_valid = parse_datetime(form.get("starts_at", ""))
    ends_at, ends_at_is_valid = parse_datetime(form.get("ends_at", ""))

    errors = []

    if not title:
        errors.append("Title is required.")

    if not starts_at_is_valid:
        errors.append("Start date and time must be a valid date and time.")
    elif not starts_at:
        errors.append("Start date and time is required.")

    if not ends_at_is_valid:
        errors.append("End date and time must be a valid date and time.")

    # Both values use the same zero-padded stored format, so a plain string
    # comparison detects an end that comes before the start.
    if starts_at and ends_at and ends_at < starts_at:
        errors.append("End date and time cannot be before the start.")

    values = {
        "title": title,
        "description": description or None,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "location": location or None,
    }

    return values, errors


@app.route("/events/new", methods=["GET", "POST"])
@login_required
def new_event():
    if request.method == "POST":
        values, errors = validate_event_form(request.form)

        if errors:
            return render_template("event_form.html", errors=errors), 400

        connection = get_db()

        # user_id always comes from the session, never from the submitted form.
        connection.execute(
            """
            INSERT INTO events (user_id, title, description, starts_at, ends_at,
                location)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                values["title"],
                values["description"],
                values["starts_at"],
                values["ends_at"],
                values["location"],
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("events"))

    return render_template("event_form.html")


@app.route("/events/<int:event_id>")
@login_required
def event_detail(event_id):
    event = load_owned_event(event_id)

    return render_template("event.html", event=event)


@app.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    event = load_owned_event(event_id)

    if request.method == "POST":
        values, errors = validate_event_form(request.form)

        if errors:
            return (
                render_template("event_form.html", errors=errors, event=event),
                400,
            )

        connection = get_db()

        # The update is scoped to the session user and never touches user_id or
        # created_at, so an event cannot be handed to another account.
        connection.execute(
            """
            UPDATE events
            SET title = ?, description = ?, starts_at = ?, ends_at = ?,
                location = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                values["title"],
                values["description"],
                values["starts_at"],
                values["ends_at"],
                values["location"],
                event_id,
                session["user_id"],
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("event_detail", event_id=event_id))

    return render_template("event_form.html", event=event)


@app.route("/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    connection = get_db()

    # As with tasks and goals, the delete is scoped to the logged-in user, and
    # the route only accepts POST so a link or a crawl cannot remove an event.
    cursor = connection.execute(
        "DELETE FROM events WHERE id = ? AND user_id = ?",
        (event_id, session["user_id"]),
    )
    deleted = cursor.rowcount
    connection.commit()
    connection.close()

    if deleted == 0:
        abort(404)

    return redirect(url_for("events"))


def validate_commitment_form(form):
    """Validate a submitted commitment form.

    Returns (values, errors). values holds the normalized column values, ready
    to be passed to SQLite as parameters. The owner is deliberately not part of
    the result: user_id always comes from the session, never from the form, so a
    crafted user_id field cannot reassign a commitment. status, created_at and
    completed_at are also left alone because they are changed by their own
    routes.
    """
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    committed_to = form.get("committed_to", "").strip()
    deadline, deadline_is_valid = parse_datetime(form.get("deadline", ""))

    errors = []

    if not title:
        errors.append("Title is required.")

    if not deadline_is_valid:
        errors.append("Deadline must be a valid date and time.")

    values = {
        "title": title,
        "description": description or None,
        "committed_to": committed_to or None,
        "deadline": deadline,
    }

    return values, errors


@app.route("/commitments")
@login_required
def commitments():
    connection = get_db()

    # Only the current user's commitments are ever returned. Pending ones come
    # first, earliest deadline first, with undated commitments last; completed
    # ones follow in the order they were finished.
    rows = connection.execute(
        """
        SELECT * FROM commitments
        WHERE user_id = ?
        ORDER BY (status = 'completed'), (deadline IS NULL), deadline,
            created_at, id
        """,
        (session["user_id"],),
    ).fetchall()

    connection.close()

    pending_commitments = [row for row in rows if row["status"] != "completed"]
    completed_commitments = [row for row in rows if row["status"] == "completed"]

    return render_template(
        "commitments.html",
        pending_commitments=pending_commitments,
        completed_commitments=completed_commitments,
    )


@app.route("/commitments/new", methods=["GET", "POST"])
@login_required
def new_commitment():
    if request.method == "POST":
        values, errors = validate_commitment_form(request.form)

        if errors:
            return render_template("commitment_form.html", errors=errors), 400

        connection = get_db()

        # user_id always comes from the session, never from the submitted form.
        connection.execute(
            """
            INSERT INTO commitments (user_id, title, description, committed_to,
                deadline)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                values["title"],
                values["description"],
                values["committed_to"],
                values["deadline"],
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("commitments"))

    return render_template("commitment_form.html")


@app.route("/commitments/<int:commitment_id>")
@login_required
def commitment_detail(commitment_id):
    commitment = load_owned_commitment(commitment_id)

    return render_template("commitment.html", commitment=commitment)


@app.route("/commitments/<int:commitment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_commitment(commitment_id):
    commitment = load_owned_commitment(commitment_id)

    if request.method == "POST":
        values, errors = validate_commitment_form(request.form)

        if errors:
            return (
                render_template(
                    "commitment_form.html", errors=errors, commitment=commitment
                ),
                400,
            )

        connection = get_db()

        # The update is scoped to the session user and never touches user_id,
        # status, created_at or completed_at, so a commitment cannot be handed
        # to another account or have its history rewritten.
        connection.execute(
            """
            UPDATE commitments
            SET title = ?, description = ?, committed_to = ?, deadline = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                values["title"],
                values["description"],
                values["committed_to"],
                values["deadline"],
                commitment_id,
                session["user_id"],
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("commitment_detail", commitment_id=commitment_id))

    return render_template("commitment_form.html", commitment=commitment)


@app.route("/commitments/<int:commitment_id>/complete", methods=["POST"])
@login_required
def complete_commitment(commitment_id):
    connection = get_db()

    # Ownership check: the commitment must exist AND belong to the logged-in
    # user, so another user's commitment can never be modified.
    commitment = connection.execute(
        "SELECT status FROM commitments WHERE id = ? AND user_id = ?",
        (commitment_id, session["user_id"]),
    ).fetchone()

    if commitment is None:
        connection.close()
        abort(404)

    # Only pending commitments are updated, so completed_at is never overwritten
    # by a repeated submit of the same form.
    if commitment["status"] != "completed":
        connection.execute(
            """
            UPDATE commitments
            SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (commitment_id, session["user_id"]),
        )
        connection.commit()

    connection.close()

    return redirect(url_for("commitment_detail", commitment_id=commitment_id))


@app.route("/commitments/<int:commitment_id>/delete", methods=["POST"])
@login_required
def delete_commitment(commitment_id):
    connection = get_db()

    # As with tasks, goals and events, the delete is scoped to the logged-in
    # user, and the route only accepts POST so a link or a crawl cannot remove a
    # commitment.
    cursor = connection.execute(
        "DELETE FROM commitments WHERE id = ? AND user_id = ?",
        (commitment_id, session["user_id"]),
    )
    deleted = cursor.rowcount
    connection.commit()
    connection.close()

    if deleted == 0:
        abort(404)

    return redirect(url_for("commitments"))


if __name__ == "__main__":
    init_db()
    app.run(debug=False)
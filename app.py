import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db

# AI disclosure (CS50 final project requirement): this project was written with
# the help of an AI coding assistant. AI assistance was used for the goal and
# task management routes below, for the templates in templates/ and for
# static/style.css; every change was reviewed and tested by the author.

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

PRIORITIES = ("low", "medium", "high")


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

        # Small dashboard summary: how many goals are still active. The full
        # analytics dashboard belongs to a later milestone.
        active_goals = connection.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id = ? AND status = 'active'",
            (session["user_id"],),
        ).fetchone()[0]

        connection.close()

        return render_template("dashboard.html", active_goals=active_goals)

    return "EXECUTE is running."


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            return "Username and password are required."

        password_hash = generate_password_hash(password)

        connection = get_db()

        try:
            connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            connection.commit()
        except Exception:
            connection.close()
            return "Username already exists."

        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        connection = get_db()

        user = connection.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        connection.close()

        if user is None or not check_password_hash(
            user["password_hash"], password
        ):
            return "Invalid username or password."

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/tasks")
@login_required
def tasks():
    connection = get_db()

    # The current user's tasks, pending ones first, then by due date and id.
    # The join is scoped to the same user, so a task can only ever display a
    # goal that its owner actually owns.
    rows = connection.execute(
        """
        SELECT tasks.*, goals.title AS goal_title
        FROM tasks
        LEFT JOIN goals
            ON goals.id = tasks.goal_id AND goals.user_id = tasks.user_id
        WHERE tasks.user_id = ?
        ORDER BY (tasks.status = 'completed'), (tasks.due_at IS NULL),
            tasks.due_at, tasks.id
        """,
        (session["user_id"],),
    ).fetchall()

    connection.close()

    pending_tasks = [task for task in rows if task["status"] != "completed"]
    completed_tasks = [task for task in rows if task["status"] == "completed"]

    return render_template(
        "tasks.html",
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
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

        errors = []

        if not title:
            errors.append("Title is required.")

        if priority not in PRIORITIES:
            errors.append("Priority must be low, medium or high.")

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
                    goals=active_goals,
                ),
                400,
            )

        # user_id always comes from the session, never from the submitted form.
        connection.execute(
            """
            INSERT INTO tasks (user_id, goal_id, title, description, due_at, priority)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                selected_goal_id,
                title,
                description or None,
                normalized_due_at,
                priority,
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("tasks"))

    connection.close()

    return render_template("task.html", priorities=PRIORITIES, goals=active_goals)


@app.route("/tasks/<int:task_id>/complete", methods=["POST"])
@login_required
def complete_task(task_id):
    connection = get_db()

    # Ownership check: the task must exist AND belong to the logged-in user,
    # so another user's task can never be modified.
    task = connection.execute(
        "SELECT status FROM tasks WHERE id = ? AND user_id = ?",
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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
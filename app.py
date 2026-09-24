import os
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db

# AI disclosure (CS50 final project requirement): this project was written with
# the help of an AI coding assistant. AI assistance was used for the task
# management routes below and for the front end in templates/ and
# static/style.css; every change was reviewed and tested by the author.

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

PRIORITIES = ("low", "medium", "high")


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
        return render_template("dashboard.html")

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
    rows = connection.execute(
        """
        SELECT * FROM tasks
        WHERE user_id = ?
        ORDER BY (status = 'completed'), (due_at IS NULL), due_at, id
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
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_at = request.form.get("due_at", "").strip()
        priority = request.form.get("priority", "").strip().lower()

        errors = []

        if not title:
            errors.append("Title is required.")

        if priority not in PRIORITIES:
            errors.append("Priority must be low, medium or high.")

        normalized_due_at = None

        if due_at:
            try:
                normalized_due_at = datetime.fromisoformat(due_at).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                errors.append("Due date and time must be a valid date and time.")

        if errors:
            return render_template("task.html", errors=errors, priorities=PRIORITIES), 400

        connection = get_db()

        # user_id always comes from the session, never from the submitted form.
        connection.execute(
            """
            INSERT INTO tasks (user_id, title, description, due_at, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                title,
                description or None,
                normalized_due_at,
                priority,
            ),
        )
        connection.commit()
        connection.close()

        return redirect(url_for("tasks"))

    return render_template("task.html", priorities=PRIORITIES)


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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
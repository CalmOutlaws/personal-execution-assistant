# EXECUTE

**Turn intentions into actions.**

EXECUTE is a personal execution assistant written in Python with Flask and
SQLite. It is an early-stage project developed as a CS50x 2026 final project.
The current version covers user accounts, tasks, goals and events; the larger
ideas described under [What's Next](#whats-next) are not implemented yet.

## Project Description

Most people are not short of intentions. They have goals they want to reach,
commitments they have made to other people, deadlines that are closing in, and
tasks and events that all compete for the same hours of the day. The difficult
part is rarely deciding what matters. It is turning those intentions into
concrete actions and then following through on them.

EXECUTE is intended to become a personal execution assistant that narrows that
gap. The long-term idea is that a user writes down what they intend to do, and
the application organises that input into goals, tasks, commitments and events,
keeps it visible in one place, and follows up on it until it is finished.
Interpreting free-form, natural-language input is part of that goal.

The project is deliberately built up in small, verifiable milestones. What
exists today is the foundation: an account, tasks with priorities and optional
due dates, goals that group related tasks together, and events that block out
time in the calendar. Natural-language input, reminders and commitment handling
are design goals for later milestones, not finished features. Nothing in this
document should be read as a claim that the application is complete or
production-ready.

## Current Features

**Accounts and authentication**

- Register an account with a username and password.
- Log in and log out; the session remembers which user is signed in.
- Passwords are stored as Werkzeug hashes, never as plaintext, and are verified
  by checking the submitted password against the stored hash.
- Session-based authentication. The dashboard, task and goal pages all require a
  login, and anonymous requests for them are redirected to the login page;
  registration and login are the only public pages.

**Tasks**

- Create a task with a title, an optional description, a priority (low, medium
  or high) and an optional due date and time.
- List tasks, split into pending and completed, with pending work first and then
  ordered by due date.
- Mark a task as complete.
- Delete a task.
- Attach a task to one of your own active goals, and see the goal's title
  alongside the task in the task list.

**Goals**

- Create a goal with a title, an optional description and an optional deadline.
- List goals, split into active and completed, each card showing a small
  progress summary of how many of its tasks are still open.
- Open a goal detail page showing the goal's details and its tasks.
- Edit a goal's title, description and deadline.
- Mark a goal as complete.
- Delete a goal. Its tasks are not deleted; they are kept and become unlinked.

**Events**

- Create an event with a title, an optional description, a start date and time,
  an optional end date and time and an optional location.
- List events, split into upcoming and past, ordered by start time.
- Open an event detail page showing when and where it takes place.
- Edit an event's title, description, start, end and location.
- Delete an event.

**Data isolation and security**

- Every task, goal and event belongs to the user who created it.
- All reads and writes are scoped to the logged-in user, so another user's task,
  goal or event cannot be listed, opened, edited, completed or deleted;
  requests for data that is not yours return a 404.
- A task can only be linked to a goal that the same user owns and that is still
  active.
- All database access uses parameterised SQL queries, and the task, goal or
  event owner is always taken from the session rather than from submitted form
  data.

**Interface**

- Shared HTML layout with a header, navigation, page headings and a
  flash-message area.
- Dark theme with a responsive layout (breakpoints for smaller screens and
  support for reduced-motion preferences).
- The application currently ships no JavaScript; the interface is HTML and CSS
  only.

## Technology Stack

| Technology | Role in the project |
| --- | --- |
| Python 3 | The language the application is written in |
| Flask | Web framework: routing, sessions, requests and template rendering |
| Jinja2 | Server-side HTML templates |
| SQLite | Database, accessed through Python's built-in `sqlite3` module |
| Werkzeug | Password hashing and the development web server |
| python-dotenv | Loads the `SECRET_KEY` from a local `.env` file |
| HTML5 | Page structure in the Jinja templates |
| CSS3 | A single hand-written stylesheet in `static/style.css` |

There is no JavaScript in the project at this stage: no `.js` file exists and no
template contains a script tag. The exact pinned versions of the Python
dependencies are listed in `requirements.txt`.

## Project Structure

```
project/
├── app.py                  # Flask application: routes, validation, authentication
├── database.py             # SQLite helpers: connection handling and schema setup
├── requirements.txt        # Pinned Python dependencies
├── test_events.py          # Automated checks for the event routes and ownership rules
├── .env                    # Local SECRET_KEY (ignored by git, not committed)
├── execute.db              # SQLite database file (ignored by git, created on first run)
├── templates/
│   ├── layout.html         # Base layout: header, navigation, flash messages, footer
│   ├── register.html       # Registration form
│   ├── login.html          # Login form
│   ├── dashboard.html      # Landing page shown after logging in
│   ├── tasks.html          # Task list, split into pending and completed
│   ├── task.html           # Create-task form, including the optional goal selector
│   ├── task_card.html      # Partial rendering a single task, shared by the task and goal pages
│   ├── goals.html          # Goal list, split into active and completed
│   ├── goal.html           # Goal detail page with the goal's tasks
│   ├── goal_form.html      # Create/edit goal form
│   ├── events.html         # Event list, split into upcoming and past
│   ├── event.html          # Event detail page
│   ├── event_form.html     # Create/edit event form
│   └── event_card.html     # Partial rendering a single event, used by the event list
└── static/
    └── style.css           # The single dark, responsive stylesheet
```

`app.py` holds the routes and validation, `database.py` holds the `sqlite3`
connection helper and the schema, and the templates only render data that the
routes pass to them.

## How It Works

- **Flask handles the web application.** `app.py` defines the routes for the
  dashboard, accounts, tasks, goals and events. Each route reads the request,
  validates the submitted form fields, runs the required queries and either
  redirects or renders a Jinja template.
- **SQLite stores the data.** All state lives in a single SQLite file,
  `execute.db`. `database.py` opens a connection per request with a `sqlite3.Row`
  row factory so that columns can be read by name, and enables foreign key
  enforcement with `PRAGMA foreign_keys = ON`. The schema is created by
  `init_db()`, which runs when the application starts.
- **Authentication uses Flask sessions.** Logging in writes the user's id and
  username into the session; logging out clears it. The `SECRET_KEY` used to
  sign the session cookie is read from a local `.env` file through
  python-dotenv. A `login_required` decorator protects the task, goal and event
  pages, and the dashboard checks the session before rendering any user data.
- **Passwords are stored as hashes.** Registration hashes the password with
  Werkzeug's `generate_password_hash` and stores only the hash. Login compares
  the submitted password against that hash with `check_password_hash`, so the
  original password is never stored or compared as text.
- **Users own their goals, tasks and events.** The owner is taken from the
  session and never from the submitted form. Queries that touch a single task,
  goal or event filter on both the row id and the session user id, and they
  return a 404 if no such row belongs to the current user. This keeps one
  account's data invisible and immutable to another account.
- **Goals can contain multiple tasks.** `tasks.goal_id` references `goals.id`
  with `ON DELETE SET NULL`, so a goal groups any number of tasks, and deleting
  the goal leaves its tasks in place, unlinked rather than removed.
- **Dates are stored in one format.** Every date and time entered through a form
  is parsed with `datetime.fromisoformat` and stored as a zero-padded
  `YYYY-MM-DD HH:MM:SS` string, so dates can be sorted and compared in SQL. An
  event is treated as upcoming while its `starts_at` is greater than or equal to
  the current time, which is produced by the same helper.
- **The application uses direct SQLite queries rather than an ORM.** Statements
  are written by hand with `?` placeholders, which keeps the SQL visible and
  avoids an extra layer of abstraction at this size.
- The event pages use the existing `events` table, which needed no change: it
  already had the title, description, start, end, location and owner columns the
  feature requires. The `commitments` table is still reserved for a later
  milestone, and no route or template uses it yet.

## Running Locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Create a `.env` file containing a `SECRET_KEY` value before starting the
application, since sessions need it. `execute.db` is created automatically on
the first run; the Flask development server then serves the application on its
default local address.

## What's Next

The following are planned for later milestones. None of them is implemented, and
the commitments table mentioned above is currently unused.

- **Commitments** - things owed to other people, tracked separately from
  personal tasks.
- **A stronger execution-focused dashboard** - a summary of what needs attention
  today rather than a list of everything.
- **Natural-language interpretation** - turning free-form input such as "finish
  the problem set by Friday" into structured tasks, goals and events.
- **Voice input** through speech-to-text, so items can be captured without
  typing.
- **Recurring reminders** for tasks, goals and events that repeat.
- **Browser notifications** so upcoming work can surface at the right time.
- **More advanced reminder and follow-up behaviour** - escalating or re-surfacing
  items that have gone quiet.
- **Potential AI-assisted interpretation** of input and of how tasks relate to
  the goals behind them.

## CS50x

EXECUTE is the final project for CS50x 2026. The project is still in its early
stages; the README and the application itself will be extended as the remaining
milestones are completed.


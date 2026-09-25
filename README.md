# EXECUTE

**Turn intentions into actions.**

## Demo

[Watch the demo on YouTube](https://youtu.be/M-jeP2faq9E)

EXECUTE is a personal execution assistant written in Python with Flask and
SQLite, submitted as the CS50x 2026 final project. It covers accounts, tasks,
goals, events and commitments. It also captures free-form sentences, breaks a
goal into suggested tasks, repeats tasks on a schedule, searches everything a
user owns, and shows what needs attention on a dashboard.

## Contents

- [Demo](#demo)
- [Project Description](#project-description)
- [Current Features](#current-features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
- [Security and Limitations](#security-and-limitations)
- [Running Locally](#running-locally)
- [Possible Future Work](#possible-future-work)
- [AI Assistance Disclosure](#ai-assistance-disclosure)
- [CS50x](#cs50x)

## Project Description

Most people are not short of intentions. They have goals they want to reach,
commitments they have made to other people, deadlines that are closing in, and
tasks and events that all compete for the same hours of the day. The difficult
part is rarely deciding what matters. It is turning those intentions into
concrete actions and then following through on them.

EXECUTE is a personal execution assistant that narrows that gap. The user writes
down what they intend to do, and the application organises that input into
goals, tasks, commitments and events, keeps it visible in one place, and follows
up on it until it is finished. Free-form, natural-language input is part of
that: a sentence such as "Finish the problem set by Friday" can be captured
without choosing a form or an item type by hand.

The project was built in small, verifiable milestones, and this document
describes exactly what the submitted version implements: an account, tasks with
priorities, due dates and optional repeats, goals that group related tasks
together and can be broken into suggested steps, events that block out time in
the calendar, commitments tracked separately from personal tasks, natural
language capture with a confirmation step, search and filtering, and optional
browser notifications and dictation on the dashboard and Quick Add pages.
Nothing in this document should be read as a claim that the application is
production-ready.

## Current Features

**Accounts and authentication**

- Register an account with a username and password.
- Log in and log out; the session remembers which user is signed in.
- Passwords are stored as Werkzeug hashes, never as plaintext, and are verified
  by checking the submitted password against the stored hash.
- Session-based authentication. Every page that shows or changes user data
  requires a login, and anonymous requests for those pages are redirected to the
  login form. Apart from the pages that hold no user data (the root URL,
  registration, login and logout), every page needs a session.
- The root URL (`/`) serves a public landing page to signed-out visitors, and
  redirects users who are already signed in to the dashboard.

**Public landing page**

- The root URL renders a static page for signed-out visitors that describes what
  EXECUTE does, explains how to start, and links to registration and login.
- The page holds no user data: the dashboard queries live behind `/dashboard`,
  so an anonymous visitor can never be shown another account's items.
- A visitor who is already signed in is redirected to the dashboard instead of
  being shown the landing page again.

**Tasks**

- Create a task with a title, an optional description, a priority (low, medium
  or high), an optional due date and time, and an optional repeat: daily, weekly
  or monthly.
- List tasks, split into pending and completed, with pending work first and then
  ordered by due date.
- Filter the task list by status (all, pending or completed), by priority, and by
  "recurring only". A filter value that is not recognised is ignored rather than
  producing an error, so a hand-edited URL still returns a usable list.
- Mark a task as complete. Completing a recurring task automatically creates one
  next occurrence, described below under "Recurring tasks".
- Delete a task.
- Attach a task to one of your own active goals, and see the goal's title
  alongside the task in the task list.

**Goals**

- Create a goal with a title, an optional description and an optional deadline.
- List goals, split into active and completed, each card showing a small
  progress summary of how many of its tasks are still open.
- Open a goal detail page showing the goal's details and its tasks.
- Break an active goal into a short list of suggested tasks from the goal page;
  see "Goal breakdown" below.
- Edit a goal's title, description and deadline.
- Mark a goal as complete.
- Delete a goal. Its tasks are not deleted; they are kept and become unlinked.

**Events**

- Create an event with a title, an optional description, a start date and time,
  an optional end date and time and an optional location.
- List events, split into upcoming and past. Upcoming events are ordered by
  start time, and past events are shown newest first.
- Open an event detail page showing when and where it takes place.
- Edit an event's title, description, start, end and location.
- Delete an event.

**Commitments**

- Create a commitment with a title, an optional description, an optional
  deadline, and the person the promise was made to.
- List commitments, split into pending and completed, with pending work first
  and then ordered by deadline.
- Open a commitment detail page showing what was promised, to whom, and when.
- Edit a commitment's title, description, deadline and the person it was made
  to. Editing never changes the owner, the status or the completion timestamp.
- Mark a commitment as complete, recording when it was completed.
- Delete a commitment.
- The dashboard shows how many commitments are still pending and lists the
  next ones by deadline, so promises to other people stay visible separately
  from your own tasks.

**Quick Add (natural language)**

- Type one sentence on the Quick Add page and EXECUTE works out whether it
  describes a task, an event, a commitment or a goal, then shows what it
  understood before anything is saved.
- The confirmation step repeats what was typed, then shows the detected Type and
  Title, the interpreted When (for example "Friday, March 6 at 6:00 PM") and the
  Location when the sentence included one. Nothing is written to the database
  until "Confirm and create" is submitted.
- Vague input stays honest: a phrase such as "in the evening" is shown as an
  approximate period instead of being turned into an invented clock time.
- If the sentence cannot be understood, the form returns the text with an
  explanation instead of guessing.
- Two details of the interpretation are worth stating plainly. A bare
  twelve-hour time without AM or PM ("at 5") is read as PM. A date with no time
  is shown in the preview as the date on its own, and it is stored at midnight
  because the `due_at` and `deadline` columns hold timestamps.

**Goal breakdown**

- Any active goal has a "Break down this goal" action that suggests up to five
  concrete task titles (every step template in this version supplies five), for
  example "Prepare or update resume for summer internship" for a goal about an
  internship.
- Suggestions come from a small keyword map with a domain-neutral fallback, so a
  goal that matches no keyword still gets a usable list.
- The user selects which suggestions to keep and can edit each title before
  confirming. Only the selected rows are created, as ordinary tasks linked to
  the goal, with no due dates and medium priority.
- The suggestions are held in the signed session between the two requests. If
  that preview is missing when the form is submitted, the page shows the
  suggestions again and asks the user to confirm once more.

**Recurring tasks**

- A task can repeat daily, weekly or monthly.
- Completing a recurring task creates exactly one next occurrence with the same
  title, description, priority and goal link, and the due date advanced by one
  interval.
- The repeat is created only once: if an identical pending occurrence already
  exists, no second copy is added.
- Monthly repeats clamp to the end of a shorter month, so a task due on the 31st
  repeats on the 30th in a 30-day month rather than rolling into the next month.

**Search**

- The search page looks through the current user's own tasks, goals, events and
  commitments and groups the results by type.
- Matching covers titles and descriptions, plus the location of an event and the
  person a commitment was made to.
- `%` and `_` typed into the search box are treated as literal characters, and
  each type returns at most 25 results.
- An empty query shows an empty state instead of the whole database, and a query
  with no matches offers a link to Quick Add so the item can be captured in a
  single sentence.

**Dashboard**

- The dashboard lives at `/dashboard`, which is both the page shown after logging
  in and the target of the redirect from the root URL. It opens with "Needs
  attention now" (overdue tasks and commitments) and "Coming next" (work that is
  due soon), then explains how EXECUTE works and offers shortcuts for creating
  and viewing tasks and for opening goals, events and commitments. The goals,
  events and commitments shortcuts show the current count when there is one.
- The page ends with the next upcoming events, the commitments that are still
  pending, and the reminders panel.

**Browser voice input**

- The Quick Add page has a microphone button that fills the text box using the
  browser's speech recognition.
- Dictation only writes text into the field. It never submits the form, and the
  sentence is interpreted by the same parser and confirmed in the same way as
  typed input.
- Recognition starts in English (India) (`en-IN`) and retries once in `en-US`
  when the browser reports that the language is unsupported or fails on the
  network.
- If the browser has no speech support, or the microphone is blocked, the button
  reports the problem and typing keeps working.

**Browser notifications**

- The dashboard has a "Reminders" section with a button that asks for
  notification permission, and permission is only requested when that button is
  clicked.
- Once enabled, EXECUTE notifies about upcoming and overdue items, using the same
  items the dashboard already shows.
- Notifications are browser-local and deduplicated in `localStorage`; nothing
  about them is stored on the server, and no service worker or push service is
  used.

**Data isolation and security**

- Every task, goal, event and commitment belongs to the user who created it.
- All reads and writes are scoped to the logged-in user, so another user's task,
  goal, event or commitment cannot be listed, opened, edited, completed or
  deleted; requests for data that is not yours return a 404.
- A task can only be linked to a goal that the same user owns and that is still
  active.
- All database access uses parameterised SQL queries, and the task, goal,
  event or commitment owner is always taken from the session rather than from
  submitted form data.

**Interface**

- Shared HTML layout with a header, navigation, page headings and a
  flash-message area.
- Dark theme with a responsive layout (breakpoints for smaller screens and
  support for reduced-motion preferences).
- Two small, plain JavaScript files add optional browser features:
  `static/quick_add.js` (dictation on the Quick Add page) and
  `static/notifications.js` (reminders on the dashboard). Both only enhance
  forms that are rendered and validated on the server, so every page still works
  without JavaScript.

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
| JavaScript | Progressive enhancement for voice input and browser reminders |
| Web Speech API | Browser speech-to-text that fills the Quick Add text box |
| Notifications API | Opt-in, browser-local reminders shown while EXECUTE is open |

There is no npm, bundler or frontend framework. The two JavaScript files in
`static/` are plain browser scripts loaded with a `<script>` tag, and the
application remains fully usable without them. The exact pinned versions of the
Python dependencies are listed in `requirements.txt`.

## Project Structure

```
project/
├── app.py                     # Flask application: routes, validation, authentication
├── database.py                # SQLite helpers: connection handling and schema setup
├── parser.py                  # Deterministic natural-language interpretation for Quick Add
├── breakdown.py               # Deterministic goal-to-task suggestions
├── recurrence.py              # Recurrence validation and next-due-date calculation
├── requirements.txt           # Pinned Python dependencies
├── test_events.py             # Automated checks for the event routes and ownership rules
├── test_commitments.py        # Automated checks for the commitment routes and ownership rules
├── test_parser.py             # Automated checks for the parser, Quick Add and goal breakdown
├── test_recurrence.py         # Automated checks for recurrence and the notification script
├── test_search.py             # Automated checks for search and the task filters
├── test_home.py               # Automated checks for the landing page and the root redirect
├── .env                       # Local SECRET_KEY (ignored by git, not committed)
├── execute.db                 # SQLite database file (ignored by git, created on first run)
├── README.md                  # This document
├── .gitignore                 # Keeps .venv, .env, execute.db and caches out of git
├── templates/
│   ├── layout.html            # Base layout: header, navigation, flash messages, footer
│   ├── home.html              # Public landing page shown to signed-out visitors
│   ├── register.html          # Registration form
│   ├── login.html             # Login form
│   ├── dashboard.html         # Page shown after logging in, with the reminders panel
│   ├── quick_add.html         # Quick Add sentence form, including the optional voice button
│   ├── quick_add_confirmation.html  # The interpreted sentence, reviewed before it is saved
│   ├── tasks.html             # Task list with the status, priority and recurring filters
│   ├── task.html              # Create-task form, including the goal and recurrence selectors
│   ├── task_detail.html       # Single task page, reached from Quick Add or the dashboard
│   ├── task_card.html         # Partial rendering a single task, shared by the task and goal pages
│   ├── goals.html             # Goal list, split into active and completed
│   ├── goal.html              # Goal detail page with the goal's tasks and breakdown action
│   ├── goal_form.html         # Create/edit goal form
│   ├── goal_breakdown.html    # Suggested tasks for a goal, with editable titles
│   ├── search.html            # Search results for tasks, goals, events and commitments
│   ├── events.html            # Event list, split into upcoming and past
│   ├── event.html             # Event detail page
│   ├── event_form.html        # Create/edit event form
│   ├── event_card.html        # Partial rendering a single event, used by the event list
│   ├── commitments.html       # Commitment list, split into pending and completed
│   ├── commitment.html        # Commitment detail page
│   ├── commitment_form.html   # Create/edit commitment form
│   └── commitment_card.html   # Partial rendering a single commitment
└── static/
    ├── style.css              # The single dark, responsive stylesheet
    ├── quick_add.js           # Optional browser dictation for the Quick Add text box
    └── notifications.js       # Optional browser reminders while the dashboard is open
```

`app.py` holds the routes and validation, `database.py` holds the `sqlite3`
connection helper and the schema, and the templates only render data that the
routes pass to them. `parser.py`, `breakdown.py` and `recurrence.py` hold the
logic behind Quick Add, goal breakdown and repeating tasks: they are plain
Python with no Flask, database or network dependency, which keeps their
behaviour reproducible and easy to test on its own.

## How It Works

The application is split into four layers, and the split is deliberate.
`app.py` is the orchestration layer: it reads the request, validates what was
submitted, takes the owner from the session, runs the queries and either
redirects or renders a template. `parser.py`, `breakdown.py` and `recurrence.py`
are domain modules with no Flask, database, session or network dependency, which
makes their behaviour reproducible and individually testable. `database.py` owns
the connection helper and the schema, and the Jinja templates only render the
data the routes hand to them. The two scripts in `static/` are optional
enhancements layered on server-rendered, server-validated forms, so every page
still works without JavaScript. The consequence is that the parts of the project
worth arguing about - how a sentence is interpreted, how a goal is broken down,
when the next occurrence of a repeating task falls - live outside the web layer
and carry no state.

- **Flask handles the web application.** `app.py` defines the routes for the
  landing page, dashboard, accounts, tasks, goals, events, commitments, Quick
  Add, goal breakdown, search and logout. Each route reads the request, validates
  the submitted form fields, runs the required queries and either redirects or
  renders a Jinja template.
- **SQLite stores the data.** All state lives in a single SQLite file,
  `execute.db`. `database.py` opens a connection per request with a `sqlite3.Row`
  row factory so that columns can be read by name, and enables foreign key
  enforcement with `PRAGMA foreign_keys = ON`. The schema is created by
  `init_db()`, which runs when the application starts.
- **Authentication uses Flask sessions.** Logging in writes the user's id and
  username into the session; logging out clears it. The `SECRET_KEY` used to
  sign the session cookie is read from a local `.env` file through
  python-dotenv. A `login_required` decorator protects every page that shows or
  changes user data; only the root URL, registration and login are reachable
  without a session. The root URL renders the public landing page for signed-out
  visitors and redirects signed-in users to the dashboard route.
- **Passwords are stored as hashes.** Registration hashes the password with
  Werkzeug's `generate_password_hash` and stores only the hash. Login compares
  the submitted password against that hash with `check_password_hash`, so the
  original password is never stored or compared as text.
- **Users own their goals, tasks, events and commitments.** The owner is taken
  from the session and never from the submitted form. Queries that touch a
  single row filter on both the row id and the session user id, and they return
  a 404 if no such row belongs to the current user. This keeps one account's data
  invisible and immutable to another account.
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
- **Events and commitments needed no extra migration.** The `events` and
  `commitments` tables created by `init_db()` already contain the title,
  description, owner, status and date columns each of those features needs. The
  only column added after the first version of the schema is `tasks.recurrence`,
  which `init_db()` adds idempotently when it opens a database created before
  recurring tasks existed.
- **Completion is idempotent.** Marking a task, goal or commitment complete only
  writes `status` and `completed_at` while the row is still pending, so
  submitting the action twice cannot overwrite the original completion time.
- **Natural-language input is parsed deterministically.** `parser.py` uses
  regular expressions and keyword tables rather than a language model. It takes
  a sentence and an optional reference time and returns a plain dictionary of
  what it found, with no Flask, database, session or network dependency, so the
  same input always produces the same result.
- **Quick Add previews before it saves.** `POST /quick-add` interprets the
  sentence, stores the preview in the signed session and renders a confirmation
  page. `POST /quick-add/confirm` treats that session value as untrusted: the
  type, title, timestamps and owner are validated again, the owner is taken from
  the session, and only then is a single row inserted.
- **Goal breakdown is deterministic as well.** `breakdown.py` matches keywords
  in the goal title against a small set of step templates and falls back to
  generic steps. It returns at most five titles and never invents due dates.
  Selected suggestions are created as ordinary tasks linked to the goal.
- **The goal breakdown preview is re-checked, not trusted.** The suggested steps
  are held in the signed session, and the confirm route verifies that the
  preview still belongs to the same goal before it reads the edited titles from
  the form and inserts ordinary tasks with the session user id.
- **Recurrence is a small pure function.** `recurrence.py` validates the
  frequency and calculates the next due date, including month-end clamping,
  without touching the database. Completing a task uses it only after the task
  was actually pending, so one repeat is created and a repeated submit adds
  nothing.
- **Search and filtering are user-scoped and parameterised.** Search builds a
  `LIKE` pattern with `%`, `_` and `\` escaped and an explicit `ESCAPE` clause,
  binds it as a parameter, caps each result list at 25 rows and filters on
  `user_id`. The task filters append only fixed, allowlisted SQL fragments and
  bind any user value.
- **Voice input only supplies text.** `static/quick_add.js` copies the
  recognised transcript into the Quick Add text box and stops there. It never
  submits the form, and the sentence is interpreted by the same server-side
  parser as typed input.
- **Reminders are opt-in and browser-local.** `static/notifications.js` requests
  permission only when the reminders button is clicked, reads the upcoming and
  overdue items the dashboard already rendered as data attributes, and checks
  them once a minute while the page is open. Items already notified are recorded
  in `localStorage`.

## Security and Limitations

- **Passwords are hashed with Werkzeug.** Registration stores only a
  `generate_password_hash` value, and login compares the submitted password with
  `check_password_hash`, so the original password is never stored or compared as
  plain text.
- **Database queries are parameterised.** Every statement uses `?` placeholders
  with values passed separately, so user input is never concatenated into SQL.
  The only assembled statement is the task filter, which appends fixed,
  allowlisted fragments and binds the priority value.
- **Records are scoped to the logged-in user.** The owner of every task, goal,
  event and commitment comes from the session, never from submitted form data,
  and single-row reads and writes filter on the session user id.
- **Templates rely on Jinja autoescaping.** No template marks user data as safe,
  so titles, descriptions and locations are escaped when rendered, and the
  JavaScript files build no HTML from user data.
- **`SECRET_KEY` must be configured.** It is read from a local `.env` file
  through python-dotenv, and the application stops with a clear error at startup
  if it is missing instead of signing sessions with an empty key.
- **Account rules are minimal.** Registration requires only a non-empty
  username and password: there is no minimum password length or strength rule,
  no password confirmation field, and no rate limiting or lockout after repeated
  failed logins. A public deployment would need all of those.
- **Authentication errors are plain responses.** A failed registration or login
  returns a short plain-text `400` response instead of re-rendering the form
  with the error attached, so the failure is visible but not styled like the
  rest of the application.
- **Session cookie settings are Flask's defaults.** The cookie is signed and
  `HttpOnly`, but `Secure` is off and `SameSite` is unset. That is workable for
  the local development setup described below, and it is not a hardened
  production configuration.
- **There are no CSRF tokens.** This is a deliberately small Flask application
  without Flask-WTF, so state-changing forms rely on the session cookie and the
  ownership checks rather than per-form tokens. This is a known limitation
  rather than an oversight.
- **Logout is a GET link** from the navigation. Every action that changes user
  data uses POST, but logout itself is a plain link.
- **Voice input depends on the browser.** Dictation needs `SpeechRecognition`
  support, microphone permission and, in Chrome, a network-backed recognition
  service, so it is not available in every browser or while offline.
- **Notifications stay in the browser.** They require explicit permission, they
  only fire while the dashboard is open in the browser, and they are
  deduplicated per browser through `localStorage` rather than scheduled on the
  server.

## Running Locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Create a `.env` file containing a `SECRET_KEY` value before starting the
application:

```text
SECRET_KEY=replace-this-with-a-random-value
```

Flask needs that key to sign the session cookie, and the application stops with
a clear error at startup if the value is missing. `execute.db` is created
automatically on the first run, because the `python app.py` entry point calls
`init_db()` before it starts serving; starting the application through the
`flask` command instead would skip that call, so `python app.py` is the
supported way to run it. The Flask development server then serves the
application on its default local address (`http://127.0.0.1:5000`), and it
starts with `debug=False`, which is the safe default for a submitted or shared
copy. This is the development server rather than a production WSGI server.

The test suite runs from the same environment:

```powershell
python -m unittest discover -v
```

The tests use Flask's test client against temporary SQLite files. They cover the
parser and the Quick Add flow, goal breakdown, the recurrence helper, search and
the task filters, the landing page and the root redirect, the event and
commitment routes with their ownership checks, and the permission gating and
deduplication logic of the notification script (checked by reading the shipped
`static/notifications.js`, since the suite does not run a browser).

## Possible Future Work

The submitted version covers the scope it set out to cover. If it were extended
further, the most useful work would be about judgement rather than new surface
area.

- **Stronger dashboard prioritisation** - ranking what to do next, instead of
  listing everything that is overdue or due soon.
- **Richer follow-up and escalation** - re-surfacing items that have gone quiet,
  and letting overdue work escalate instead of being shown once.
- **More sophisticated parsing** - longer sentences, more than one item in a
  sentence, and phrasing that the current pattern set does not cover.

## AI Assistance Disclosure

AI tools were used while building this project. The Python modules, the Jinja
templates, the stylesheet and the tests were written with the help of an AI
coding assistant, and every source file repeats that disclosure in a header
comment. Each change was reviewed, run and tested by the author before it was
kept: the behaviour was checked against the requirement it was meant to satisfy,
the test suite was run, and the reasoning behind the non-obvious parts - the
deterministic parsing rules, the session-scoped ownership checks, the recurrence
calculation - is understood by the author and can be explained or changed on
request. AI assistance was also used to draft and revise this README, and every
claim in it was checked against the code.

No AI model is part of the running application. There is no model call, no API
key and no outbound network request in the code, and the only browser feature
that may rely on a remote service is the optional voice dictation supplied by
the browser itself.

## CS50x

EXECUTE is my final project for CS50x 2026. The source code, the test suite and
the video linked at the top of this document are the submission: the video walks
through the finished application, and this README documents the design, the
shipped features and the limitations of the submitted version.


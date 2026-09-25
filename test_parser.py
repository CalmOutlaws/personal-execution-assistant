"""Checks for the deterministic natural-language parser and Quick Add flow.

AI disclosure: these tests were created with AI assistance, reviewed, and run
by the author as part of the EXECUTE milestone.
"""

import gc
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta

import app as execute
import database
from parser import parse_input


REFERENCE = datetime(2026, 9, 25, 10, 0)  # Friday


class ParserTests(unittest.TestCase):
    def parse(self, text):
        return parse_input(text, REFERENCE)

    def test_event_relative_date_and_time(self):
        result = self.parse("Meet Rahul tomorrow at 6")
        self.assertEqual(result["type"], "event")
        self.assertEqual(result["title"], "Meet Rahul")
        self.assertEqual(result["starts_at"], "2026-09-26 18:00:00")

    def test_bare_hour_is_interpreted_as_pm(self):
        for text, expected_hour in (("Meet Rahul tomorrow at 5", 17),
                                    ("Meet Rahul tomorrow at 6", 18),
                                    ("Meet Rahul tomorrow at 7", 19)):
            result = self.parse(text)
            self.assertEqual(result["starts_at"], f"2026-09-26 {expected_hour:02d}:00:00")

    def test_explicit_times_remain_unchanged(self):
        cases = {
            "Meet Rahul tomorrow at 6 AM": "2026-09-26 06:00:00",
            "Meet Rahul tomorrow at 6 PM": "2026-09-26 18:00:00",
            "Meet Rahul tomorrow at 17:00": "2026-09-26 17:00:00",
            "Meet Rahul tomorrow at 5:30 PM": "2026-09-26 17:30:00",
        }
        for text, expected in cases.items():
            self.assertEqual(self.parse(text)["starts_at"], expected)

    def test_event_location(self):
        result = self.parse("Meet Rahul at Church Street tomorrow at 6 PM")
        self.assertEqual(result["type"], "event")
        self.assertEqual(result["title"], "Meet Rahul")
        self.assertEqual(result["location"], "Church Street")
        self.assertEqual(result["starts_at"], "2026-09-26 18:00:00")

    def test_event_weekday_and_meridiem(self):
        result = self.parse("Meeting with professor on Friday at 3 PM")
        self.assertEqual(result["type"], "event")
        self.assertEqual(result["starts_at"], "2026-09-25 15:00:00")

    def test_commitment_deadline(self):
        result = self.parse("Submit DBMS assignment by Friday")
        self.assertEqual(result["type"], "commitment")
        self.assertEqual(result["title"], "Submit DBMS assignment")
        self.assertEqual(result["deadline"], "2026-09-25 00:00:00")

    def test_commitment_absolute_deadline(self):
        result = self.parse("Finish project by October 5")
        self.assertEqual(result["type"], "commitment")
        self.assertEqual(result["deadline"], "2026-10-05 00:00:00")

    def test_commitment_this_week(self):
        result = self.parse("Apply for internships this week")
        self.assertEqual(result["type"], "commitment")
        self.assertEqual(result["deadline"], "2026-09-27 00:00:00")

    def test_task_relative_due_date(self):
        result = self.parse("Buy a notebook tomorrow")
        self.assertEqual(result["type"], "task")
        self.assertEqual(result["due_at"], "2026-09-26 00:00:00")

    def test_task_time(self):
        result = self.parse("Call Rahul at 5 PM")
        self.assertEqual(result["type"], "task")
        self.assertEqual(result["due_at"], "2026-09-25 17:00:00")

    def test_today(self):
        result = self.parse("Complete DSA practice today")
        self.assertEqual(result["type"], "task")
        self.assertEqual(result["due_at"], "2026-09-25 00:00:00")

    def test_tomorrow(self):
        result = self.parse("Buy milk tomorrow")
        self.assertEqual(result["due_at"], "2026-09-26 00:00:00")

    def test_invalid_unknown_and_empty(self):
        for text in ("hello world", "", "   "):
            result = self.parse(text)
            self.assertEqual(result["type"], "unknown")
            self.assertEqual(result["confidence"], 0.0)
            self.assertIn("error", result)

    def test_title_cleanup(self):
        result = self.parse("I need to submit my DBMS assignment by Friday.")
        self.assertEqual(result["title"], "Submit DBMS assignment")

    def test_case_variations(self):
        result = self.parse("MEET RAHUL TOMORROW AT 6 PM")
        self.assertEqual(result["type"], "event")
        self.assertEqual(result["title"], "MEET RAHUL")
        self.assertEqual(result["starts_at"], "2026-09-26 18:00:00")

    def test_noncrashing_inputs(self):
        for text in ("October 99", "Meet Rahul at 99:99", "???", "buy"):
            self.assertIsInstance(self.parse(text), dict)


class ParserV2Tests(unittest.TestCase):
    """Fixed-reference coverage for the V2 intent, date, time and location rules."""

    REFERENCE = datetime(2026, 9, 25, 10, 0)  # Friday

    def parse(self, text):
        return parse_input(text, self.REFERENCE)

    def test_event_intent_requires_event_signal_and_schedule(self):
        cases = {
            "Meeting with professor tomorrow": "Meeting with professor",
            "Appointment with dentist at 3 PM": "Appointment with dentist",
            "Go to college tomorrow": "Go to college",
            "Dinner with Rahul this week": "Dinner with Rahul",
            "Class tomorrow evening": "Class",
            "Visit grandma tomorrow": "Visit grandma",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "event")
                self.assertEqual(result["title"], title)

    def test_commitment_intent_from_obligation_or_deadline(self):
        cases = {
            "I have to finish DBMS assignment by Friday": "Finish DBMS assignment",
            "I need to submit report by October 5": "Submit report",
            "I must pay fees on Monday": "Pay fees",
            "I should apply for internships this week": "Apply for internships",
            "Submit DBMS assignment by Friday": "Submit DBMS assignment",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "commitment")
                self.assertEqual(result["title"], title)
                self.assertIn("deadline", result)

    def test_direct_actions_remain_tasks(self):
        cases = {
            "Buy milk tomorrow": "Buy milk",
            "Complete DSA practice today": "Complete DSA practice",
            "Practice SQL tomorrow": "Practice SQL",
            "Check email at 5 PM": "Check email",
            "Read the project proposal tomorrow": "Read the project proposal",
            "Finish DSA practice today": "Finish DSA practice",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "task")
                self.assertEqual(result["title"], title)

    def test_goal_language_is_intentional(self):
        cases = {
            "My goal is to learn C++": "Learn C++",
            "goal: get an internship": "Get an internship",
            "I want to get fit": "Get fit",
            "I want to become a developer": "Become a developer",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "goal")
                self.assertEqual(result["title"], title)
                self.assertGreater(result["confidence"], 0.0)

    def test_non_goal_want_sentence_stays_a_task(self):
        result = self.parse("I want to buy milk tomorrow")
        self.assertEqual(result["type"], "task")
        self.assertEqual(result["title"], "Buy milk")

    def test_reminders_are_tasks_even_with_event_verbs(self):
        cases = {
            "Remind me to call dad tomorrow": "Call dad",
            "Please remind me to submit report by Friday": "Submit report",
            "Remember to book tickets tomorrow": "Book tickets",
            "Remind me to meet Rahul tomorrow": "Meet Rahul",
            "Remember to meet Rahul tomorrow": "Meet Rahul",
            "Don't forget to call dad tomorrow": "Call dad",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "task")
                self.assertEqual(result["title"], title)

    def test_relative_dates_use_fixed_reference(self):
        cases = {
            "Buy milk today": "2026-09-25 00:00:00",
            "Buy milk tomorrow": "2026-09-26 00:00:00",
            "Buy milk on Saturday": "2026-09-26 00:00:00",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)["due_at"], expected)

    def test_weekday_dates_choose_next_occurrence(self):
        meeting = self.parse("Meeting with professor on Monday at 9 AM")
        self.assertEqual(meeting["starts_at"], "2026-09-28 09:00:00")
        sunday = self.parse("Submit report by Sunday")
        self.assertEqual(sunday["deadline"], "2026-09-27 00:00:00")
        same_day = self.parse("Meeting with professor on Friday at 3 PM")
        self.assertEqual(same_day["starts_at"], "2026-09-25 15:00:00")

    def test_month_day_year_and_numeric_dates(self):
        cases = {
            "Finish project by October 5": "2026-10-05 00:00:00",
            "Submit application on March 3, 2027": "2027-03-03 00:00:00",
            "Pay rent on 10/5": "2026-10-05 00:00:00",
            "Submit on 12/31/2026": "2026-12-31 00:00:00",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "commitment")
                self.assertEqual(result["deadline"], expected)

    def test_past_month_day_rolls_to_next_year(self):
        result = self.parse("Submit tax documents on September 20")
        self.assertEqual(result["deadline"], "2027-09-20 00:00:00")

    def test_this_week_is_the_upcoming_sunday(self):
        result = self.parse("Apply for internships this week")
        self.assertEqual(result["deadline"], "2026-09-27 00:00:00")

    def test_exact_time_forms_are_normalized(self):
        cases = {
            "Call at 6 AM": "2026-09-25 06:00:00",
            "Call at 6 PM": "2026-09-25 18:00:00",
            "Call at 12 PM": "2026-09-25 12:00:00",
            "Call at 12 AM": "2026-09-25 00:00:00",
            "Call at 5:30 PM": "2026-09-25 17:30:00",
            "Call at 17:00": "2026-09-25 17:00:00",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)["due_at"], expected)

    def test_bare_hour_still_uses_pm_convention(self):
        cases = {"at 5": 17, "at 6": 18, "at 7": 19}
        for suffix, hour in cases.items():
            with self.subTest(text=suffix):
                result = self.parse(f"Meet Rahul tomorrow {suffix}")
                self.assertEqual(result["starts_at"],
                                 f"2026-09-26 {hour:02d}:00:00")

    def test_vague_periods_never_invent_an_exact_time(self):
        for period in ("morning", "afternoon", "evening", "night"):
            with self.subTest(period=period):
                result = self.parse(f"Meet Rahul tomorrow {period}")
                self.assertEqual(result["type"], "event")
                self.assertEqual(result["date"], "2026-09-26 00:00:00")
                self.assertEqual(result["approximate_time"], period)
                self.assertEqual(result["time_text"], period)
                self.assertIsNone(result.get("starts_at"))

    def test_exact_time_takes_precedence_over_vague_period(self):
        result = self.parse("Meet Rahul tomorrow morning at 6 AM")
        self.assertEqual(result["starts_at"], "2026-09-26 06:00:00")
        self.assertNotIn("approximate_time", result)
        self.assertNotIn("time_text", result)

    def test_vague_task_and_commitment_keep_none_exact_fields(self):
        task = self.parse("Remind me to call dad tomorrow evening")
        self.assertEqual(task["type"], "task")
        self.assertIsNone(task.get("due_at"))
        self.assertEqual(task["date"], "2026-09-26 00:00:00")
        self.assertEqual(task["approximate_time"], "evening")

        commitment = self.parse("I need to submit report tomorrow morning")
        self.assertEqual(commitment["type"], "commitment")
        self.assertIsNone(commitment.get("deadline"))
        self.assertEqual(commitment["date"], "2026-09-26 00:00:00")
        self.assertEqual(commitment["approximate_time"], "morning")

    def test_location_is_extracted_without_date_or_time(self):
        cases = {
            "Meet Rahul at Church Street tomorrow at 6 PM": "Church Street",
            "Meet Rahul at the library tomorrow at 6 PM": "library",
            "Meeting with professor in the college tomorrow": "college",
            "Class in the office at 5 PM": "office",
        }
        for text, location in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "event")
                self.assertEqual(result["location"], location)
                self.assertNotIn("tomorrow", result["location"])
                self.assertNotIn("6 PM", result["location"])

    def test_location_works_with_vague_periods(self):
        cases = {
            "Meet at home in the evening": "home",
            "Meet in the evening at home": "home",
            "Meet at college in the evening": "college",
        }
        for text, location in cases.items():
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "event")
                self.assertEqual(result["location"], location)
                self.assertEqual(result["approximate_time"], "evening")

    def test_title_cleanup_removes_wrappers_and_schedule(self):
        cases = {
            "I have to finish my DBMS assignment by Friday":
                "Finish DBMS assignment",
            "I need to submit the project on October 5": "Submit the project",
            "Please call mom tomorrow": "Call mom",
            "Remember to return the book tomorrow": "Return the book",
            "Buy milk tomorrow at 5 PM": "Buy milk",
            "Submit report by Friday": "Submit report",
        }
        for text, title in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)["title"], title)

    def test_title_cleanup_preserves_meaningful_words(self):
        self.assertEqual(self.parse("Read the project proposal tomorrow")["title"],
                         "Read the project proposal")
        self.assertEqual(self.parse("MEET RAHUL TOMORROW AT 6 PM")["title"],
                         "MEET RAHUL")
    def test_unknown_inputs_return_bounded_errors(self):
        for text in ("", "   ", "???", "hello world", "meeting", "appointment"):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], "unknown")
                self.assertEqual(result["confidence"], 0.0)
                self.assertIn("error", result)

    def test_case_and_whitespace_variations_are_stable(self):
        expected = self.parse("Meet Rahul tomorrow at 6 PM")
        variants = (
            "meet   rahul\n tomorrow\tat 6 PM",
            "  MEET RAHUL TOMORROW AT 6 PM  ",
        )
        for text in variants:
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertEqual(result["type"], expected["type"])
                self.assertEqual(result["title"].lower(), expected["title"].lower())
                self.assertEqual(result["starts_at"], expected["starts_at"])

    def test_malformed_inputs_do_not_crash(self):
        for text in ("October 99", "Meet Rahul at 99:99", "Pay on 13/45",
                     "Call at 25:00", "buy"):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertIsInstance(result, dict)
                self.assertIn("type", result)

    def test_confidence_is_bounded_and_meaningful(self):
        known = self.parse("Meet Rahul tomorrow at 6 PM")
        weak = self.parse("buy")
        unknown = self.parse("???")
        self.assertGreater(known["confidence"], weak["confidence"])
        self.assertGreater(weak["confidence"], unknown["confidence"])
        for result in (known, weak, unknown):
            self.assertGreaterEqual(result["confidence"], 0.0)
            self.assertLessEqual(result["confidence"], 1.0)

    def test_commitment_rules_are_not_applied_to_plain_tasks(self):
        for text in ("Finish DSA practice today", "Buy milk on Friday",
                     "Complete homework today"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)["type"], "task")

    def test_parser_module_has_no_flask_or_sqlite_imports(self):
        path = os.path.join(os.path.dirname(__file__), "parser.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read().lower()
        self.assertNotRegex(source, r"(?m)^\s*(?:import|from)\s+(?:flask|sqlite3)")


class QuickAddTestBase(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.original_database = database.DATABASE
        database.DATABASE = self.db_path
        database.init_db()
        connection = database.get_db()
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (1, ?, ?)",
            ("quickuser", "test-hash"),
        )
        connection.commit()
        connection.close()
        execute.app.config.update(TESTING=True, SECRET_KEY="quick-add-test")
        self.client = execute.app.test_client()
        # The parser and interpretation flow do not read or write item data.
        # Seed only the signed session so this test does not depend on users
        # already existing in the project's local SQLite file.
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "quickuser"

    def tearDown(self):
        self.client.get("/logout")
        database.DATABASE = self.original_database
        gc.collect()
        try:
            os.remove(self.db_path)
        except PermissionError:
            pass

    def text(self, response):
        return re.sub(r"\s+", " ", response.get_data(as_text=True))


class QuickAddRouteTests(QuickAddTestBase):
    def test_anonymous_access_redirects(self):
        self.client.get("/logout")
        response = self.client.get("/quick-add")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_authenticated_get_works(self):
        response = self.client.get("/quick-add")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Quick Add", self.text(response))

    def test_valid_input_renders_interpretation(self):
        response = self.client.post(
            "/quick-add", data={"text": "Meet Rahul tomorrow at 6 PM"}
        )
        self.assertEqual(response.status_code, 200)
        body = self.text(response)
        self.assertIn("EXECUTE understood", body)
        self.assertIn("Meet Rahul", body)
        self.assertIn("Event", body)

    def test_blank_input_is_graceful(self):
        response = self.client.post("/quick-add", data={"text": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Please enter", self.text(response))

    def test_known_existing_flows_still_work(self):
        self.assertEqual(self.client.get("/tasks").status_code, 200)
        self.assertEqual(self.client.get("/goals").status_code, 200)
        self.assertEqual(self.client.get("/events").status_code, 200)
        self.assertEqual(self.client.get("/commitments").status_code, 200)

    def confirmation(self, interpretation):
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "quickuser"
            session["quick_add_interpretation"] = interpretation
        return self.client.post("/quick-add/confirm")

    def test_task_confirmation_creates_and_redirects(self):
        response = self.confirmation({"type": "task", "title": "Buy milk",
                                      "due_at": "2026-09-26 00:00:00"})
        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.headers["Location"], r"^/tasks/\d+$")
        item_id = int(response.headers["Location"].rsplit("/", 1)[1])
        connection = database.get_db()
        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (item_id,)
        ).fetchone()
        connection.close()
        self.assertEqual(row["user_id"], 1)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["priority"], "medium")

    def test_event_confirmation_creates_and_redirects(self):
        response = self.confirmation({"type": "event", "title": "Meet Rahul",
                                      "starts_at": "2026-09-26 18:00:00",
                                      "location": "Church Street"})
        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.headers["Location"], r"^/events/\d+$")

    def test_commitment_confirmation_creates_and_redirects(self):
        response = self.confirmation({"type": "commitment", "title": "Submit project",
                                      "deadline": "2026-10-05 00:00:00"})
        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.headers["Location"], r"^/commitments/\d+$")

    def test_missing_preview_is_safe(self):
        response = self.client.post("/quick-add/confirm")
        self.assertEqual(response.status_code, 400)

    def test_unknown_type_creates_nothing(self):
        response = self.confirmation({"type": "unknown", "title": "Not actionable"})
        self.assertEqual(response.status_code, 400)
        connection = database.get_db()
        try:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("tasks", "goals", "events", "commitments")
            }
        finally:
            connection.close()
        self.assertEqual(set(counts.values()), {0})

    def test_invalid_type_is_rejected(self):
        response = self.confirmation({"type": "tasks; DROP TABLE tasks", "title": "x"})
        self.assertEqual(response.status_code, 400)

    def test_missing_title_is_rejected(self):
        response = self.confirmation({"type": "task", "due_at": "2026-09-26 00:00:00"})
        self.assertEqual(response.status_code, 400)

    def test_malformed_datetime_is_rejected(self):
        response = self.confirmation({"type": "event", "title": "Meet",
                                      "starts_at": "not-a-datetime"})
        self.assertEqual(response.status_code, 400)

    def test_preview_is_cleared_after_creation(self):
        self.confirmation({"type": "task", "title": "One task"})
        with self.client.session_transaction() as session:
            self.assertNotIn("quick_add_interpretation", session)

    def test_duplicate_refresh_does_not_create_another_row(self):
        response = self.confirmation({"type": "task", "title": "One task"})
        item_id = response.headers["Location"].rsplit("/", 1)[1]
        detail = self.client.get(response.headers["Location"])
        self.assertEqual(detail.status_code, 200)
        self.assertIn(f"/tasks/{item_id}", response.headers["Location"])

    def test_anonymous_confirmation_redirects(self):
        self.client.get("/logout")
        response = self.client.post("/quick-add/confirm")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_user_controlled_values_are_escaped(self):
        interpretation = {"type": "task", "title": "<script>alert(1)</script>"}
        self.confirmation(interpretation)
        with self.client.session_transaction() as session:
            self.assertNotIn("quick_add_interpretation", session)
        # Jinja autoescaping must prevent the stored title from becoming markup.
        connection = database.get_db()
        row = connection.execute(
            "SELECT id FROM tasks WHERE title = ?", (interpretation["title"],)
        ).fetchone()
        connection.close()
        self.assertIsNotNone(row)
        detail = self.client.get(f"/tasks/{row['id']}")
        self.assertNotIn("<script>alert(1)</script>", detail.get_data(as_text=True))
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",
                      detail.get_data(as_text=True))

    def test_vague_event_preview_shows_period_without_midnight(self):
        response = self.client.post(
            "/quick-add", data={"text": "Meet Rahul tomorrow evening"}
        )
        self.assertEqual(response.status_code, 200)
        body = self.text(response)
        self.assertIn("Event", body)
        self.assertRegex(body, r"\b\w+day, \w+ \d+ — evening\b")
        self.assertNotIn("at 12:00 AM", body)

    def test_vague_task_preview_shows_period(self):
        response = self.client.post(
            "/quick-add", data={"text": "Remind me to call dad tomorrow evening"}
        )
        self.assertEqual(response.status_code, 200)
        body = self.text(response)
        self.assertIn("Task", body)
        self.assertIn("— evening", body)
        self.assertNotIn("at 12:00 AM", body)

    def test_exact_time_preview_still_shows_clock_time(self):
        response = self.client.post(
            "/quick-add", data={"text": "Meet Rahul tomorrow at 6 PM"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("at 6:00 PM", self.text(response))

    def test_vague_event_confirmation_persists_date_only_start(self):
        response = self.confirmation({
            "type": "event", "title": "Meet Rahul",
            "starts_at": None, "date": "2026-09-26 00:00:00",
            "approximate_time": "evening",
        })
        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.headers["Location"], r"^/events/\d+$")
        item_id = int(response.headers["Location"].rsplit("/", 1)[1])
        connection = database.get_db()
        row = connection.execute(
            "SELECT starts_at FROM events WHERE id = ?", (item_id,)
        ).fetchone()
        connection.close()
        # The schema forbids NULL starts_at; only persistence falls back to
        # midnight while the preview displayed "date — evening".
        self.assertEqual(row["starts_at"], "2026-09-26 00:00:00")

    def test_vague_task_and_commitment_confirmation_persist_dates(self):
        task = self.confirmation({
            "type": "task", "title": "Call dad",
            "due_at": None, "date": "2026-09-26 00:00:00",
            "approximate_time": "evening",
        })
        self.assertEqual(task.status_code, 302)
        commitment = self.confirmation({
            "type": "commitment", "title": "Submit report",
            "deadline": None, "date": "2026-09-27 00:00:00",
            "approximate_time": "morning",
        })
        self.assertEqual(commitment.status_code, 302)
        task_id = int(task.headers["Location"].rsplit("/", 1)[1])
        commitment_id = int(commitment.headers["Location"].rsplit("/", 1)[1])
        connection = database.get_db()
        task_row = connection.execute(
            "SELECT due_at FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        commitment_row = connection.execute(
            "SELECT deadline FROM commitments WHERE id = ?", (commitment_id,)
        ).fetchone()
        connection.close()
        self.assertEqual(task_row["due_at"], "2026-09-26 00:00:00")
        self.assertEqual(commitment_row["deadline"], "2026-09-27 00:00:00")

    def test_event_without_start_or_date_is_rejected(self):
        response = self.confirmation({
            "type": "event", "title": "Meet Rahul", "starts_at": None,
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()

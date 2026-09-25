"""Checks for the deterministic natural-language parser and Quick Add flow.

AI disclosure: these tests were created with AI assistance, reviewed, and run
by the author as part of the EXECUTE milestone.
"""

import gc
import os
import re
import tempfile
import unittest
from datetime import datetime

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


if __name__ == "__main__":
    unittest.main()

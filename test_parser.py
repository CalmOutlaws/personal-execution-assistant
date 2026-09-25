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


if __name__ == "__main__":
    unittest.main()

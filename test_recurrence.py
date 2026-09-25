"""Recurring tasks + browser notifications checks.

AI disclosure: these tests were created with AI assistance, reviewed, and run
by the author as part of the EXECUTE milestone.
"""

import gc
import os
import re
import tempfile
import unittest

import app as execute
import database
import recurrence


class RecurrenceBase(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.original_database = database.DATABASE
        database.DATABASE = self.db_path
        database.init_db()
        connection = database.get_db()
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (1, ?, ?)",
            ("recurrence-user", "test-hash"),
        )
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (2, ?, ?)",
            ("other-user", "test-hash"),
        )
        connection.execute(
            "INSERT INTO goals (id, user_id, title, status) VALUES (1, 1, ?, ?)",
            ("Goal", "active"),
        )
        connection.commit()
        connection.close()
        execute.app.config.update(TESTING=True, SECRET_KEY="recurrence-test")
        self.client = execute.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "recurrence-user"

    def tearDown(self):
        self.client.get("/logout")
        database.DATABASE = self.original_database
        gc.collect()
        try:
            os.remove(self.db_path)
        except PermissionError:
            pass

    def create_task(self, **overrides):
        data = {
            "title": "Water plants",
            "description": "Balcony pots",
            "due_at": "2026-09-26T09:00",
            "priority": "high",
            "goal_id": "1",
            "recurrence": "",
        }
        data.update(overrides)
        return self.client.post("/tasks/new", data=data)

    def task_rows(self):
        connection = database.get_db()
        rows = connection.execute(
            "SELECT * FROM tasks ORDER BY id"
        ).fetchall()
        connection.close()
        return rows

    def text(self, response):
        return re.sub(r"\s+", " ", response.get_data(as_text=True))


class RecurrenceHelperTests(unittest.TestCase):
    def test_next_due_daily_weekly_monthly(self):
        self.assertEqual(
            recurrence.next_due_at("daily", "2026-09-26 09:00:00"),
            "2026-09-27 09:00:00",
        )
        self.assertEqual(
            recurrence.next_due_at("weekly", "2026-09-26 09:00:00"),
            "2026-10-03 09:00:00",
        )
        self.assertEqual(
            recurrence.next_due_at("monthly", "2026-01-31 09:00:00"),
            "2026-02-28 09:00:00",
        )

    def test_invalid_recurrence_returns_none(self):
        self.assertIsNone(recurrence.next_due_at("yearly", "2026-09-26 09:00:00"))
        self.assertIsNone(recurrence.next_due_at(None, "2026-09-26 09:00:00"))
        self.assertFalse(recurrence.is_valid_recurrence("yearly"))
        self.assertTrue(recurrence.is_valid_recurrence("daily"))


class RecurringTaskRouteTests(RecurrenceBase):
    def test_non_recurring_completion_still_works(self):
        self.assertEqual(self.create_task().status_code, 302)
        task_id = self.task_rows()[0]["id"]
        self.assertEqual(
            self.client.post(f"/tasks/{task_id}/complete").status_code, 302
        )
        rows = self.task_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "completed")

    def test_daily_recurrence_creates_one_next_task(self):
        self.create_task(recurrence="daily")
        task_id = self.task_rows()[0]["id"]
        self.client.post(f"/tasks/{task_id}/complete")
        rows = self.task_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["due_at"], "2026-09-27 09:00:00")

    def test_weekly_recurrence_creates_one_next_task(self):
        self.create_task(recurrence="weekly")
        task_id = self.task_rows()[0]["id"]
        self.client.post(f"/tasks/{task_id}/complete")
        rows = self.task_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["due_at"], "2026-10-03 09:00:00")

    def test_monthly_recurrence_handles_shorter_months(self):
        self.create_task(recurrence="monthly", due_at="2026-01-31T09:00")
        task_id = self.task_rows()[0]["id"]
        self.client.post(f"/tasks/{task_id}/complete")
        rows = self.task_rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["due_at"], "2026-02-28 09:00:00")

    def test_next_occurrence_preserves_fields_and_defaults(self):
        self.create_task(recurrence="daily")
        task_id = self.task_rows()[0]["id"]
        self.client.post(f"/tasks/{task_id}/complete")
        original, nxt = self.task_rows()
        self.assertEqual(nxt["user_id"], original["user_id"])
        self.assertEqual(nxt["goal_id"], original["goal_id"])
        self.assertEqual(nxt["title"], original["title"])
        self.assertEqual(nxt["description"], original["description"])
        self.assertEqual(nxt["priority"], original["priority"])
        self.assertEqual(nxt["recurrence"], "daily")
        self.assertEqual(nxt["status"], "pending")
        self.assertIsNone(nxt["completed_at"])

    def test_repeated_completion_is_idempotent(self):
        self.create_task(recurrence="daily")
        task_id = self.task_rows()[0]["id"]
        self.client.post(f"/tasks/{task_id}/complete")
        self.client.post(f"/tasks/{task_id}/complete")
        self.assertEqual(len(self.task_rows()), 2)

    def test_invalid_recurrence_is_rejected(self):
        response = self.create_task(recurrence="yearly")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.task_rows(), [])

    def test_unauthorized_users_cannot_complete_recurring_tasks(self):
        self.create_task(recurrence="daily")
        task_id = self.task_rows()[0]["id"]
        with self.client.session_transaction() as session:
            session["user_id"] = 2
            session["username"] = "other-user"
        self.assertEqual(
            self.client.post(f"/tasks/{task_id}/complete").status_code, 404
        )
        self.assertEqual(len(self.task_rows()), 1)


class NotificationScriptTests(unittest.TestCase):
    def source(self):
        path = os.path.join(os.path.dirname(__file__), "static", "notifications.js")
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_permission_gated_and_not_automatic(self):
        source = self.source()
        self.assertIn("requestPermission", source)
        self.assertIn("Notification.requestPermission", source)
        self.assertIn('addEventListener("click"', source)
        # Permission must only be requested from the click handler path, never
        # at top-level load/init scope.
        lines = source.splitlines()
        bare_calls = [
            line for line in lines
            if "requestPermission()" in line
            and "Notification.requestPermission" not in line
            and "addEventListener" not in line
            and "function requestPermission" not in line
        ]
        self.assertEqual(bare_calls, [])

    def test_deduplication_and_fallback_exist(self):
        source = self.source()
        self.assertIn("localStorage", source)
        self.assertIn("alreadyNotified", source)
        self.assertIn("markNotified", source)
        self.assertIn("60 * 1000", source)
        self.assertIn("not supported", source.lower())

    def test_dashboard_offers_notification_control(self):
        path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        self.assertIn("enable-notifications-button", body)
        self.assertIn("notification-status", body)
        self.assertIn("notifications.js", body)


if __name__ == "__main__":
    unittest.main()



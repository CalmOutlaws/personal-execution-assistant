"""Search, filtering, and final UX polish checks.

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


class SearchFilterBase(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.original_database = database.DATABASE
        database.DATABASE = self.db_path
        database.init_db()
        connection = database.get_db()
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (1, ?, ?)",
            ("search-user", "test-hash"),
        )
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (2, ?, ?)",
            ("other-user", "test-hash"),
        )
        connection.commit()
        connection.close()
        execute.app.config.update(TESTING=True, SECRET_KEY="search-test")
        self.client = execute.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "search-user"

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


class SearchTests(SearchFilterBase):
    def seed(self):
        connection = database.get_db()
        connection.execute(
            "INSERT INTO tasks (user_id, title, description) VALUES (1, ?, ?)",
            ("Write report", "Draft the quarterly summary"),
        )
        connection.execute(
            "INSERT INTO tasks (user_id, title) VALUES (2, ?)",
            ("Other secret task",),
        )
        connection.execute(
            "INSERT INTO goals (user_id, title) VALUES (1, ?)",
            ("Learn Spanish",),
        )
        connection.execute(
            "INSERT INTO events (user_id, title, location, starts_at)"
            " VALUES (1, ?, ?, ?)",
            ("Team lunch", "Church Street", "2099-01-01 12:00:00"),
        )
        connection.execute(
            "INSERT INTO commitments (user_id, title, committed_to)"
            " VALUES (1, ?, ?)",
            ("Submit slides", "Professor Rao"),
        )
        connection.commit()
        connection.close()

    def test_search_requires_authentication(self):
        self.client.get("/logout")
        response = self.client.get("/search?q=report")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_search_only_returns_current_user_records(self):
        self.seed()
        body = self.text(self.client.get("/search?q=secret"))
        self.assertIn("No results", body)
        self.assertNotIn("Other secret task", body)

    def test_search_matches_task_title(self):
        self.seed()
        body = self.text(self.client.get("/search?q=report"))
        self.assertIn("Write report", body)

    def test_search_matches_event_location(self):
        self.seed()
        body = self.text(self.client.get("/search?q=Church"))
        self.assertIn("Team lunch", body)

    def test_search_matches_commitment_recipient(self):
        self.seed()
        body = self.text(self.client.get("/search?q=Rao"))
        self.assertIn("Submit slides", body)

    def test_search_matches_goal_title(self):
        self.seed()
        body = self.text(self.client.get("/search?q=Spanish"))
        self.assertIn("Learn Spanish", body)

    def test_empty_search_behaves_safely(self):
        self.seed()
        for query in ("", "   "):
            body = self.text(self.client.get(f"/search?q={query}"))
            self.assertEqual(self.client.get("/search").status_code, 200)
            self.assertIn("Enter a word", body)


class TaskFilterTests(SearchFilterBase):
    def seed(self):
        connection = database.get_db()
        connection.execute(
            "INSERT INTO tasks (user_id, title, status, priority, recurrence)"
            " VALUES (1, ?, 'pending', 'high', NULL)",
            ("Pending high",),
        )
        connection.execute(
            "INSERT INTO tasks (user_id, title, status, priority, recurrence)"
            " VALUES (1, ?, 'completed', 'low', NULL)",
            ("Done low",),
        )
        connection.execute(
            "INSERT INTO tasks (user_id, title, status, priority, recurrence)"
            " VALUES (1, ?, 'pending', 'medium', 'daily')",
            ("Recurring daily",),
        )
        connection.commit()
        connection.close()

    def test_status_filter(self):
        self.seed()
        body = self.text(self.client.get("/tasks?status=pending"))
        self.assertIn("Pending high", body)
        self.assertNotIn("Done low", body)
        body = self.text(self.client.get("/tasks?status=completed"))
        self.assertIn("Done low", body)
        self.assertNotIn("Pending high", body)

    def test_recurring_filter(self):
        self.seed()
        body = self.text(self.client.get("/tasks?recurring=1"))
        self.assertIn("Recurring daily", body)
        self.assertNotIn("Pending high", body)

    def test_priority_filter(self):
        self.seed()
        body = self.text(self.client.get("/tasks?priority=high"))
        self.assertIn("Pending high", body)
        self.assertNotIn("Recurring daily", body)

    def test_invalid_filters_safely_ignored(self):
        self.seed()
        body = self.text(self.client.get("/tasks?status=bogus&priority=bogus"))
        self.assertIn("Pending high", body)
        self.assertIn("Done low", body)
        self.assertIn("Recurring daily", body)


if __name__ == "__main__":
    unittest.main()



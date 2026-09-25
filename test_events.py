"""Checks for the event management milestone.

The tests run against a throwaway SQLite file, so the real execute.db is never
touched. Run them from the project folder with:

    python -m unittest test_events -v

AI disclosure: these tests were created with AI assistance, reviewed and run by
the author before the milestone was accepted.
"""

import gc
import os
import re
import tempfile
import unittest

import app as execute
import database


class EventTestBase(unittest.TestCase):
    """Shared setup: a temporary database and two logged-in users."""

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)

        # Point the shared helpers at the temporary file for the whole test.
        self.original_database = database.DATABASE
        database.DATABASE = self.db_path
        database.init_db()

        execute.app.config.update(TESTING=True, SECRET_KEY="test-secret-key")
        self.client = execute.app.test_client()

        self.alice_id = self.register("alice", "password-a")
        self.bob_id = self.register("bob", "password-b")
        self.login("alice", "password-a")

    def tearDown(self):
        database.DATABASE = self.original_database
        self.client.get("/logout")

        # A failing assertion can leave a database connection alive; collecting
        # first keeps the temporary file removable on Windows.
        gc.collect()

        try:
            os.remove(self.db_path)
        except PermissionError:
            pass

    # -- helpers ----------------------------------------------------------

    def register(self, username, password):
        response = self.client.post(
            "/register", data={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 302)

        connection = database.get_db()
        user_id = connection.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()["id"]
        connection.close()

        return user_id

    def login(self, username, password):
        response = self.client.post(
            "/login", data={"username": username, "password": password}
        )
        self.assertEqual(response.status_code, 302)

        with self.client.session_transaction() as session:
            self.assertIn("user_id", session)

    def logout(self):
        self.client.get("/logout")

    def text(self, response):
        """Response body with runs of whitespace collapsed, for text checks."""
        return re.sub(r"\s+", " ", response.get_data(as_text=True))

    def event_row(self, event_id):
        connection = database.get_db()
        row = connection.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        connection.close()
        return row

    def event_count(self):
        connection = database.get_db()
        count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        connection.close()
        return count

    def newest_event_id(self):
        connection = database.get_db()
        row = connection.execute(
            "SELECT id FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        connection.close()
        return row["id"] if row else None

    def create_event(self, **overrides):
        data = {
            "title": "Team standup",
            "description": "Daily sync",
            "location": "Room 4",
            "starts_at": "2099-01-01T09:00",
            "ends_at": "2099-01-01T09:30",
        }

        # When a test moves the start time but does not care about the end, drop
        # the default end time so it cannot end up before the new start.
        if "starts_at" in overrides and "ends_at" not in overrides:
            data["ends_at"] = ""

        data.update(overrides)

        response = self.client.post("/events/new", data=data)

        if response.status_code == 302:
            return self.newest_event_id()

        return response


class EventCrudTests(EventTestBase):
    """Creation, listing, detail, editing and deletion."""

    def test_create_event_stores_values_for_session_user(self):
        event_id = self.create_event(
            title="  Dentist appointment  ",
            description="  Check-up  ",
            location="  Room 4  ",
            starts_at="2099-03-04T13:05",
            ends_at="2099-03-04T13:35",
        )

        event = self.event_row(event_id)

        self.assertEqual(event["title"], "Dentist appointment")
        self.assertEqual(event["description"], "Check-up")
        self.assertEqual(event["location"], "Room 4")
        self.assertEqual(event["starts_at"], "2099-03-04 13:05:00")
        self.assertEqual(event["ends_at"], "2099-03-04 13:35:00")
        self.assertEqual(event["user_id"], self.alice_id)
        self.assertTrue(event["created_at"])

    def test_event_list_shows_upcoming_and_past_sections(self):
        self.create_event(title="Future review", starts_at="2099-05-01T09:00")
        self.create_event(title="Old workshop", starts_at="2000-05-01T09:00")

        response = self.client.get("/events")
        body = self.text(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Future review", body)
        self.assertIn("Old workshop", body)
        self.assertIn("Upcoming", body)
        self.assertIn("Past", body)

    def test_event_detail_page_shows_all_fields(self):
        event_id = self.create_event(
            title="Conference talk",
            description="Present the milestone",
            location="Auditorium",
            starts_at="2099-06-01T10:00",
            ends_at="2099-06-01T11:00",
        )

        body = self.text(self.client.get(f"/events/{event_id}"))

        self.assertIn("Conference talk", body)
        self.assertIn("Present the milestone", body)
        self.assertIn("Auditorium", body)
        self.assertIn("2099-06-01 10:00:00", body)
        self.assertIn("2099-06-01 11:00:00", body)

    def test_optional_description_and_location_may_be_omitted(self):
        event_id = self.create_event(
            title="Solo focus block", description="", location=""
        )

        event = self.event_row(event_id)
        self.assertIsNone(event["description"])
        self.assertIsNone(event["location"])

        body = self.text(self.client.get(f"/events/{event_id}"))
        self.assertIn("No description yet.", body)
        self.assertIn("No location", body)

    def test_edit_event_updates_fields_only(self):
        event_id = self.create_event(
            title="First draft", starts_at="2099-07-01T08:00"
        )
        created_at = self.event_row(event_id)["created_at"]

        response = self.client.post(
            f"/events/{event_id}/edit",
            data={
                "title": "Final draft",
                "description": "Rewritten",
                "location": "Library",
                "starts_at": "2099-07-02T08:30",
                "ends_at": "2099-07-02T09:30",
                "user_id": self.bob_id,
            },
        )

        self.assertEqual(response.status_code, 302)

        event = self.event_row(event_id)
        self.assertEqual(event["title"], "Final draft")
        self.assertEqual(event["description"], "Rewritten")
        self.assertEqual(event["location"], "Library")
        self.assertEqual(event["starts_at"], "2099-07-02 08:30:00")
        self.assertEqual(event["ends_at"], "2099-07-02 09:30:00")
        # Owner and creation time are never taken from the form.
        self.assertEqual(event["user_id"], self.alice_id)
        self.assertEqual(event["created_at"], created_at)

    def test_edit_form_is_prefilled_with_stored_values(self):
        event_id = self.create_event(
            title="Piano lesson",
            starts_at="2099-08-01T17:00",
            ends_at="2099-08-01T17:45",
        )

        body = self.text(self.client.get(f"/events/{event_id}/edit"))

        self.assertIn('value="Piano lesson"', body)
        self.assertIn('value="2099-08-01T17:00"', body)
        self.assertIn('value="2099-08-01T17:45"', body)

    def test_delete_event_removes_it(self):
        event_id = self.create_event()

        response = self.client.post(f"/events/{event_id}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.event_row(event_id))
        self.assertEqual(self.event_count(), 0)

    def test_user_id_in_form_cannot_reassign_the_event(self):
        event_id = self.create_event(title="Mine", user_id=self.bob_id)

        self.assertEqual(self.event_row(event_id)["user_id"], self.alice_id)


class EventValidationTests(EventTestBase):
    """Required fields, malformed dates and the start/end ordering rule."""

    def test_title_is_required(self):
        response = self.create_event(title="   ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Title is required.", self.text(response))
        self.assertEqual(self.event_count(), 0)

    def test_start_is_required(self):
        response = self.create_event(starts_at="")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Start date and time is required.", self.text(response))
        self.assertEqual(self.event_count(), 0)

    def test_malformed_start_is_rejected(self):
        response = self.create_event(starts_at="not-a-date")

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid date and time", self.text(response))
        self.assertEqual(self.event_count(), 0)

    def test_malformed_end_is_rejected(self):
        response = self.create_event(ends_at="31/12/2099 09:00")

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "End date and time must be a valid date and time.", self.text(response)
        )
        self.assertEqual(self.event_count(), 0)

    def test_end_before_start_is_rejected(self):
        response = self.create_event(
            starts_at="2099-09-01T12:00", ends_at="2099-09-01T11:00"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "End date and time cannot be before the start.", self.text(response)
        )
        self.assertEqual(self.event_count(), 0)

    def test_end_equal_to_start_is_allowed(self):
        event_id = self.create_event(
            starts_at="2099-09-01T12:00", ends_at="2099-09-01T12:00"
        )

        self.assertEqual(self.event_row(event_id)["ends_at"], "2099-09-01 12:00:00")

    def test_edit_rejects_end_before_start_and_keeps_stored_values(self):
        event_id = self.create_event(starts_at="2099-10-01T12:00")

        response = self.client.post(
            f"/events/{event_id}/edit",
            data={
                "title": "Changed",
                "starts_at": "2099-10-01T12:00",
                "ends_at": "2099-10-01T10:00",
            },
        )

        self.assertEqual(response.status_code, 400)

        event = self.event_row(event_id)
        self.assertEqual(event["title"], "Team standup")
        self.assertEqual(event["starts_at"], "2099-10-01 12:00:00")


class EventSecurityTests(EventTestBase):
    """Authentication, ownership and output safety."""

    def test_anonymous_users_are_sent_to_login(self):
        self.logout()

        for url in ("/events", "/events/new", "/events/1", "/events/1/edit"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response.headers["Location"], "/login", url)

        response = self.client.post("/events/1/delete")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_user_cannot_see_another_users_event(self):
        event_id = self.create_event(title="Alice only")

        self.logout()
        self.login("bob", "password-b")

        self.assertEqual(self.client.get(f"/events/{event_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/events/{event_id}/edit").status_code, 404)

        body = self.text(self.client.get("/events"))
        self.assertNotIn("Alice only", body)

    def test_user_cannot_edit_another_users_event(self):
        event_id = self.create_event(
            title="Alice only", starts_at="2099-11-01T09:00"
        )

        self.logout()
        self.login("bob", "password-b")

        response = self.client.post(
            f"/events/{event_id}/edit",
            data={
                "title": "Hijacked",
                "starts_at": "2099-11-01T09:00",
                "ends_at": "",
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.event_row(event_id)["title"], "Alice only")

    def test_user_cannot_delete_another_users_event(self):
        event_id = self.create_event(title="Alice only")

        self.logout()
        self.login("bob", "password-b")

        response = self.client.post(f"/events/{event_id}/delete")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.event_count(), 1)

    def test_missing_and_malformed_ids_are_handled_safely(self):
        for url in (
            "/events/999999",
            "/events/999999/edit",
            "/events/not-a-number",
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)

        self.assertEqual(self.client.post("/events/999999/delete").status_code, 404)

    def test_delete_is_post_only(self):
        event_id = self.create_event()

        response = self.client.get(f"/events/{event_id}/delete")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.event_count(), 1)

    def test_event_content_is_escaped(self):
        event_id = self.create_event(
            title="<script>alert(1)</script>",
            description="<img src=x onerror=alert(2)>",
            location="<b>bold</b>",
        )

        body = self.client.get(f"/events/{event_id}").get_data(as_text=True)
        listing = self.client.get("/events").get_data(as_text=True)

        for page in (body, listing):
            self.assertNotIn("<script>alert(1)</script>", page)
            self.assertNotIn("<img src=x onerror=alert(2)>", page)

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", body)
        self.assertEqual(
            self.event_row(event_id)["title"], "<script>alert(1)</script>"
        )


class DashboardAndNavigationTests(EventTestBase):
    """The dashboard summary and the navigation entry."""

    def test_dashboard_summarises_only_your_own_upcoming_events(self):
        self.create_event(title="Alice future", starts_at="2099-12-01T09:00")
        self.create_event(title="Alice second", starts_at="2099-12-02T09:00")
        self.create_event(title="Alice past", starts_at="2001-01-01T09:00")

        self.logout()
        self.login("bob", "password-b")
        self.create_event(title="Bob future", starts_at="2099-12-03T09:00")

        self.logout()
        self.login("alice", "password-a")

        # Signed-in "/" redirects here; see test_home.py.
        body = self.text(self.client.get("/dashboard"))
        self.assertIn("Alice future", body)
        self.assertIn("Alice second", body)
        self.assertIn("2 upcoming events on your schedule.", body)
        self.assertNotIn("Bob future", body)
        self.assertNotIn("Alice past", body)

    def test_dashboard_shows_an_empty_event_state_without_events(self):
        # Signed-in "/" redirects here; see test_home.py.
        body = self.text(self.client.get("/dashboard"))

        self.assertIn("Nothing scheduled yet.", body)
        self.assertIn('href="/events"', body)

    def test_navigation_links_to_events(self):
        body = self.text(self.client.get("/events"))

        self.assertIn('href="/events"', body)
        self.assertIn('href="/tasks"', body)
        self.assertIn('href="/goals"', body)


class ExistingFeatureRegressionTests(EventTestBase):
    """Tasks and goals must keep working unchanged."""

    def test_goal_and_task_flow_still_works(self):
        response = self.client.post(
            "/goals/new",
            data={"title": "Ship milestone", "description": "Events", "deadline": ""},
        )
        self.assertEqual(response.status_code, 302)

        connection = database.get_db()
        goal_id = connection.execute(
            "SELECT id FROM goals WHERE user_id = ?", (self.alice_id,)
        ).fetchone()["id"]
        connection.close()

        response = self.client.post(
            "/tasks/new",
            data={
                "title": "Write the event routes",
                "description": "",
                "due_at": "2099-01-01T09:00",
                "priority": "high",
                "goal_id": str(goal_id),
            },
        )
        self.assertEqual(response.status_code, 302)

        body = self.text(self.client.get("/tasks"))
        self.assertIn("Write the event routes", body)
        self.assertIn("High priority", body)

        body = self.text(self.client.get(f"/goals/{goal_id}"))
        self.assertIn("Ship milestone", body)
        self.assertIn("Write the event routes", body)

    def test_goal_completion_and_deletion_still_work(self):
        self.client.post(
            "/goals/new", data={"title": "Tidy desk", "description": ""}
        )

        connection = database.get_db()
        goal_id = connection.execute(
            "SELECT id FROM goals WHERE user_id = ?", (self.alice_id,)
        ).fetchone()["id"]
        connection.close()

        self.assertEqual(
            self.client.post(f"/goals/{goal_id}/complete").status_code, 302
        )
        self.assertEqual(self.client.get(f"/goals/{goal_id}").status_code, 200)
        self.assertEqual(
            self.client.post(f"/goals/{goal_id}/delete").status_code, 302
        )

        connection = database.get_db()
        remaining = connection.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id = ?", (self.alice_id,)
        ).fetchone()[0]
        connection.close()

        self.assertEqual(remaining, 0)

    def test_pages_still_render(self):
        for url in (
            # Signed-in "/" redirects to the dashboard; see test_home.py.
            "/dashboard",
            "/tasks",
            "/tasks/new",
            "/goals",
            "/goals/new",
            "/events",
            "/events/new",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)


if __name__ == "__main__":
    unittest.main()


"""Checks for the commitment management milestone.

The tests run against a throwaway SQLite file, so the real execute.db is never
touched. Run them from the project folder with:

    python -m unittest test_commitments -v

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


class CommitmentTestBase(unittest.TestCase):
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

    def commitment_row(self, commitment_id):
        connection = database.get_db()
        row = connection.execute(
            "SELECT * FROM commitments WHERE id = ?", (commitment_id,)
        ).fetchone()
        connection.close()
        return row

    def commitment_count(self):
        connection = database.get_db()
        count = connection.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
        connection.close()
        return count

    def set_completed_at(self, commitment_id, value):
        """Force a known completed_at so a rewrite would be visible."""
        connection = database.get_db()
        connection.execute(
            "UPDATE commitments SET completed_at = ? WHERE id = ?",
            (value, commitment_id),
        )
        connection.commit()
        connection.close()

    def newest_commitment_id(self):
        connection = database.get_db()
        row = connection.execute(
            "SELECT id FROM commitments ORDER BY id DESC LIMIT 1"
        ).fetchone()
        connection.close()
        return row["id"] if row else None

    def create_commitment(self, **overrides):
        data = {
            "title": "Submit the DBMS assignment",
            "description": "Include the ER diagram and the query output.",
            "committed_to": "Professor Rao",
            "deadline": "2099-01-01T09:00",
        }
        data.update(overrides)

        response = self.client.post("/commitments/new", data=data)

        if response.status_code == 302:
            return self.newest_commitment_id()

        return response


class CommitmentCrudTests(CommitmentTestBase):
    """Creation, listing, detail, editing, completion and deletion."""

    def test_create_commitment_stores_values_for_session_user(self):
        commitment_id = self.create_commitment(
            title="  Send the internship application  ",
            description="  Attach the transcript.  ",
            committed_to="  Career cell  ",
            deadline="2099-03-04T13:05",
        )

        commitment = self.commitment_row(commitment_id)

        self.assertEqual(commitment["title"], "Send the internship application")
        self.assertEqual(commitment["description"], "Attach the transcript.")
        self.assertEqual(commitment["committed_to"], "Career cell")
        self.assertEqual(commitment["deadline"], "2099-03-04 13:05:00")
        self.assertEqual(commitment["status"], "pending")
        self.assertEqual(commitment["user_id"], self.alice_id)
        self.assertIsNone(commitment["completed_at"])
        self.assertTrue(commitment["created_at"])

    def test_commitment_list_shows_pending_and_completed_sections(self):
        pending_id = self.create_commitment(title="Call Rahul")
        completed_id = self.create_commitment(title="Old promise")
        self.client.post(f"/commitments/{completed_id}/complete")

        response = self.client.get("/commitments")
        body = self.text(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Pending", body)
        self.assertIn("Completed", body)
        self.assertIn("Call Rahul", body)
        self.assertIn("Old promise", body)
        self.assertIsNone(self.commitment_row(pending_id)["completed_at"])

    def test_commitment_detail_page_shows_all_fields(self):
        commitment_id = self.create_commitment(
            title="Finish the project report",
            description="Twelve pages plus references.",
            committed_to="Dr. Nair",
            deadline="2099-06-01T10:00",
        )

        body = self.text(self.client.get(f"/commitments/{commitment_id}"))

        self.assertIn("Finish the project report", body)
        self.assertIn("Twelve pages plus references.", body)
        self.assertIn("Dr. Nair", body)
        self.assertIn("2099-06-01 10:00:00", body)
        self.assertIn("Pending", body)

    def test_optional_fields_may_be_omitted(self):
        commitment_id = self.create_commitment(
            title="Reply to the email", description="", committed_to="", deadline=""
        )

        commitment = self.commitment_row(commitment_id)
        self.assertIsNone(commitment["description"])
        self.assertIsNone(commitment["committed_to"])
        self.assertIsNone(commitment["deadline"])

        body = self.text(self.client.get(f"/commitments/{commitment_id}"))
        self.assertIn("No description yet.", body)
        self.assertIn("Not recorded", body)
        self.assertIn("No deadline", body)

    def test_edit_commitment_updates_fields_only(self):
        commitment_id = self.create_commitment(title="First version")
        original = self.commitment_row(commitment_id)

        response = self.client.post(
            f"/commitments/{commitment_id}/edit",
            data={
                "title": "Second version",
                "description": "Rewritten",
                "committed_to": "The whole team",
                "deadline": "2099-07-02T08:30",
                "user_id": self.bob_id,
                "status": "completed",
                "completed_at": "2000-01-01 00:00:00",
            },
        )

        self.assertEqual(response.status_code, 302)

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["title"], "Second version")
        self.assertEqual(commitment["description"], "Rewritten")
        self.assertEqual(commitment["committed_to"], "The whole team")
        self.assertEqual(commitment["deadline"], "2099-07-02 08:30:00")
        # Owner, status and both timestamps are never taken from the form.
        self.assertEqual(commitment["user_id"], self.alice_id)
        self.assertEqual(commitment["status"], "pending")
        self.assertEqual(commitment["created_at"], original["created_at"])
        self.assertIsNone(commitment["completed_at"])

    def test_edit_form_is_prefilled_with_stored_values(self):
        commitment_id = self.create_commitment(
            title="Call Rahul",
            committed_to="Rahul",
            deadline="2099-08-01T17:00",
        )

        body = self.text(self.client.get(f"/commitments/{commitment_id}/edit"))

        self.assertIn('value="Call Rahul"', body)
        self.assertIn('value="Rahul"', body)
        self.assertIn('value="2099-08-01T17:00"', body)

    def test_delete_commitment_removes_it(self):
        commitment_id = self.create_commitment()

        response = self.client.post(f"/commitments/{commitment_id}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.commitment_row(commitment_id))
        self.assertEqual(self.commitment_count(), 0)

    def test_user_id_in_form_cannot_reassign_the_commitment(self):
        commitment_id = self.create_commitment(title="Mine", user_id=self.bob_id)

        self.assertEqual(self.commitment_row(commitment_id)["user_id"], self.alice_id)


class CommitmentValidationTests(CommitmentTestBase):
    """Required fields and malformed deadline handling."""

    def test_title_is_required(self):
        response = self.create_commitment(title="")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Title is required.", self.text(response))
        self.assertEqual(self.commitment_count(), 0)

    def test_whitespace_only_title_is_rejected(self):
        response = self.create_commitment(title="   \t  ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Title is required.", self.text(response))
        self.assertEqual(self.commitment_count(), 0)

    def test_malformed_deadline_is_rejected(self):
        response = self.create_commitment(deadline="31/12/2099 09:00")

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Deadline must be a valid date and time.", self.text(response)
        )
        self.assertEqual(self.commitment_count(), 0)

    def test_blank_deadline_is_stored_as_null(self):
        commitment_id = self.create_commitment(deadline="   ")

        self.assertIsNone(self.commitment_row(commitment_id)["deadline"])

    def test_edit_rejects_malformed_deadline_and_keeps_stored_values(self):
        commitment_id = self.create_commitment(deadline="2099-10-01T12:00")

        response = self.client.post(
            f"/commitments/{commitment_id}/edit",
            data={"title": "Changed", "description": "", "deadline": "soon"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Deadline must be a valid date and time.", self.text(response))

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["title"], "Submit the DBMS assignment")
        self.assertEqual(commitment["deadline"], "2099-10-01 12:00:00")


class CommitmentCompletionTests(CommitmentTestBase):
    """The completion rules shared with tasks and goals."""

    def test_completing_sets_status_and_timestamp(self):
        commitment_id = self.create_commitment()

        response = self.client.post(f"/commitments/{commitment_id}/complete")

        self.assertEqual(response.status_code, 302)

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["status"], "completed")
        self.assertIsNotNone(commitment["completed_at"])
        self.assertRegex(
            commitment["completed_at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        )

    def test_completed_commitment_shows_completion_details(self):
        commitment_id = self.create_commitment(title="Send the report")
        self.client.post(f"/commitments/{commitment_id}/complete")

        body = self.text(self.client.get(f"/commitments/{commitment_id}"))
        self.assertIn("Completed", body)

        listing = self.text(self.client.get("/commitments"))
        self.assertIn("commitment--completed", listing)
        self.assertNotIn(
            f"/commitments/{commitment_id}/complete",
            listing.replace(" ", ""),
        )

    def test_repeated_completion_does_not_rewrite_the_timestamp(self):
        commitment_id = self.create_commitment()

        self.client.post(f"/commitments/{commitment_id}/complete")

        # Force a known timestamp, then complete again: the timestamp must stay.
        sentinel = "2000-01-01 00:00:00"
        self.set_completed_at(commitment_id, sentinel)

        response = self.client.post(f"/commitments/{commitment_id}/complete")

        self.assertEqual(response.status_code, 302)

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["completed_at"], sentinel)
        self.assertEqual(commitment["status"], "completed")

    def test_completion_still_works_after_an_edit(self):
        commitment_id = self.create_commitment(title="Original promise")

        self.client.post(
            f"/commitments/{commitment_id}/edit",
            data={"title": "Edited promise", "description": "", "deadline": ""},
        )
        self.client.post(f"/commitments/{commitment_id}/complete")

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["title"], "Edited promise")
        self.assertEqual(commitment["status"], "completed")
        self.assertIsNotNone(commitment["completed_at"])


class CommitmentSecurityTests(CommitmentTestBase):
    """Authentication, ownership, method safety and output escaping."""

    def test_anonymous_users_are_sent_to_login(self):
        self.logout()

        for url in (
            "/commitments",
            "/commitments/new",
            "/commitments/1",
            "/commitments/1/edit",
        ):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response.headers["Location"], "/login", url)

        for url in ("/commitments/1/complete", "/commitments/1/delete"):
            response = self.client.post(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response.headers["Location"], "/login", url)

    def test_user_cannot_see_another_users_commitment(self):
        commitment_id = self.create_commitment(title="Alice only")

        self.logout()
        self.login("bob", "password-b")

        self.assertEqual(
            self.client.get(f"/commitments/{commitment_id}").status_code, 404
        )
        self.assertEqual(
            self.client.get(f"/commitments/{commitment_id}/edit").status_code, 404
        )

        body = self.text(self.client.get("/commitments"))
        self.assertNotIn("Alice only", body)

    def test_user_cannot_edit_another_users_commitment(self):
        commitment_id = self.create_commitment(title="Alice only")

        self.logout()
        self.login("bob", "password-b")

        response = self.client.post(
            f"/commitments/{commitment_id}/edit",
            data={"title": "Hijacked", "description": "", "deadline": ""},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.commitment_row(commitment_id)["title"], "Alice only")

    def test_user_cannot_complete_another_users_commitment(self):
        commitment_id = self.create_commitment(title="Alice only")

        self.logout()
        self.login("bob", "password-b")

        response = self.client.post(f"/commitments/{commitment_id}/complete")

        self.assertEqual(response.status_code, 404)

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["status"], "pending")
        self.assertIsNone(commitment["completed_at"])

    def test_user_cannot_delete_another_users_commitment(self):
        commitment_id = self.create_commitment(title="Alice only")

        self.logout()
        self.login("bob", "password-b")

        response = self.client.post(f"/commitments/{commitment_id}/delete")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.commitment_count(), 1)

    def test_missing_and_malformed_ids_are_handled_safely(self):
        for url in (
            "/commitments/999999",
            "/commitments/999999/edit",
            "/commitments/not-a-number",
        ):
            self.assertEqual(self.client.get(url).status_code, 404, url)

        self.assertEqual(
            self.client.post("/commitments/999999/complete").status_code, 404
        )
        self.assertEqual(
            self.client.post("/commitments/999999/delete").status_code, 404
        )

    def test_state_changing_routes_reject_get(self):
        commitment_id = self.create_commitment()

        for action in ("complete", "delete"):
            response = self.client.get(f"/commitments/{commitment_id}/{action}")
            self.assertEqual(response.status_code, 405, action)

        commitment = self.commitment_row(commitment_id)
        self.assertEqual(commitment["status"], "pending")
        self.assertEqual(self.commitment_count(), 1)

    def test_commitment_content_is_escaped(self):
        commitment_id = self.create_commitment(
            title="<script>alert(1)</script>",
            description="<img src=x onerror=alert(2)>",
            committed_to="<b>bold</b>",
        )

        detail = self.client.get(f"/commitments/{commitment_id}").get_data(as_text=True)
        listing = self.client.get("/commitments").get_data(as_text=True)

        for page in (detail, listing):
            self.assertNotIn("<script>alert(1)</script>", page)
            self.assertNotIn("<img src=x onerror=alert(2)>", page)

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", detail)
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", detail)
        self.assertEqual(
            self.commitment_row(commitment_id)["title"], "<script>alert(1)</script>"
        )


class CommitmentDashboardTests(CommitmentTestBase):
    """The dashboard summary and the navigation entry."""

    def test_dashboard_counts_only_your_own_pending_commitments(self):
        self.create_commitment(title="Alice pending one")
        self.create_commitment(title="Alice pending two")
        finished = self.create_commitment(title="Alice finished")
        self.client.post(f"/commitments/{finished}/complete")

        self.logout()
        self.login("bob", "password-b")
        self.create_commitment(title="Bob pending")

        self.logout()
        self.login("alice", "password-a")

        body = self.text(self.client.get("/"))

        self.assertIn("2 pending commitments you have promised to others.", body)
        self.assertIn("Alice pending one", body)
        self.assertNotIn("Bob pending", body)
        self.assertNotIn("Alice finished", body)

    def test_dashboard_lists_the_next_pending_commitments_by_deadline(self):
        self.create_commitment(title="Latest promise", deadline="2099-03-01T09:00")
        self.create_commitment(title="Earliest promise", deadline="2099-01-01T09:00")
        self.create_commitment(title="Middle promise", deadline="2099-02-01T09:00")
        self.create_commitment(title="Undated promise", deadline="")
        self.create_commitment(title="Fourth promise", deadline="2099-04-01T09:00")

        body = self.text(self.client.get("/"))

        self.assertIn("Earliest promise", body)
        self.assertIn("Middle promise", body)
        self.assertIn("Latest promise", body)
        # The summary is capped at three, and undated commitments sort last.
        self.assertNotIn("Fourth promise", body)
        self.assertNotIn("Undated promise", body)

        self.assertLess(
            body.index("Earliest promise"), body.index("Middle promise")
        )
        self.assertLess(body.index("Middle promise"), body.index("Latest promise"))

        # Undated commitments still appear on the commitments page itself.
        listing = self.text(self.client.get("/commitments"))
        self.assertIn("Undated promise", listing)
        self.assertIn("No deadline", listing)

    def test_dashboard_shows_a_commitment_empty_state(self):
        body = self.text(self.client.get("/"))

        self.assertIn("You have nothing pending.", body)
        self.assertIn('href="/commitments"', body)

    def test_navigation_links_to_every_section(self):
        body = self.text(self.client.get("/commitments"))

        for href in ('"/"', '"/tasks"', '"/goals"', '"/events"', '"/commitments"', '"/tasks/new"'):
            self.assertIn(f"href={href}", body)


class ExistingFeatureRegressionTests(CommitmentTestBase):
    """Tasks, goals and events must keep working unchanged."""

    def test_task_and_goal_flow_still_works(self):
        response = self.client.post(
            "/goals/new",
            data={"title": "Ship milestone", "description": "Commitments", "deadline": ""},
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
                "title": "Write the commitment routes",
                "description": "",
                "due_at": "2099-01-01T09:00",
                "priority": "high",
                "goal_id": str(goal_id),
            },
        )
        self.assertEqual(response.status_code, 302)

        body = self.text(self.client.get("/tasks"))
        self.assertIn("Write the commitment routes", body)
        self.assertIn("High priority", body)

        body = self.text(self.client.get(f"/goals/{goal_id}"))
        self.assertIn("Ship milestone", body)
        self.assertIn("Write the commitment routes", body)

    def test_event_flow_still_works(self):
        response = self.client.post(
            "/events/new",
            data={
                "title": "Milestone review",
                "description": "",
                "location": "Room 4",
                "starts_at": "2099-05-01T09:00",
                "ends_at": "2099-05-01T10:00",
            },
        )
        self.assertEqual(response.status_code, 302)

        body = self.text(self.client.get("/events"))
        self.assertIn("Milestone review", body)
        self.assertIn("Room 4", body)

        body = self.text(self.client.get("/events/1"))
        self.assertIn("Milestone review", body)

    def test_pages_still_render(self):
        for url in (
            "/",
            "/tasks",
            "/tasks/new",
            "/goals",
            "/goals/new",
            "/events",
            "/events/new",
            "/commitments",
            "/commitments/new",
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)


if __name__ == "__main__":
    unittest.main()





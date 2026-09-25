"""Landing page and root-route redirect checks.

The root URL serves the public landing page to signed-out visitors and sends
signed-in users to the dashboard route.

AI disclosure: these tests were created with AI assistance, reviewed, and run
by the author as part of the EXECUTE milestone.
"""

import gc
import os
import re
import tempfile
import unittest

from werkzeug.security import generate_password_hash

import app as execute
import database


class HomeRouteBase(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.original_database = database.DATABASE
        database.DATABASE = self.db_path
        database.init_db()
        connection = database.get_db()
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (1, ?, ?)",
            ("home-user", generate_password_hash("home-password")),
        )
        connection.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (2, ?, ?)",
            ("other-user", generate_password_hash("other-password")),
        )
        connection.execute(
            "INSERT INTO tasks (user_id, title, description, due_at)"
            " VALUES (1, ?, ?, ?)",
            ("Private task", "Only home-user should ever see this", "2099-01-01 09:00:00"),
        )
        connection.execute(
            "INSERT INTO tasks (user_id, title, due_at) VALUES (2, ?, ?)",
            ("Other user task", "2099-01-02 09:00:00"),
        )
        connection.commit()
        connection.close()
        execute.app.config.update(TESTING=True, SECRET_KEY="home-test")
        self.client = execute.app.test_client()

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

    def login(self, username="home-user", password="home-password"):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
        )


class LandingPageTests(HomeRouteBase):
    """The public landing page rendered for signed-out visitors."""

    def test_root_renders_the_landing_page_when_signed_out(self):
        response = self.client.get("/")
        body = self.text(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Turn intentions into actions", body)
        self.assertIn("What EXECUTE does", body)
        self.assertIn("How to start", body)

    def test_landing_page_links_to_login_and_registration(self):
        body = self.text(self.client.get("/"))

        self.assertIn('href="/login"', body)
        self.assertIn('href="/register"', body)

    def test_landing_page_does_not_render_the_dashboard_or_user_data(self):
        body = self.text(self.client.get("/"))

        self.assertNotIn("Welcome back", body)
        self.assertNotIn("Needs attention now", body)
        self.assertNotIn("Coming next", body)
        self.assertNotIn("Private task", body)
        self.assertNotIn("Other user task", body)

    def test_landing_page_is_served_again_after_logging_out(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 302)

        self.client.get("/logout")

        body = self.text(self.client.get("/"))
        self.assertIn("What EXECUTE does", body)
        self.assertNotIn("Welcome back", body)


class RootRedirectTests(HomeRouteBase):
    """The signed-in redirect from the root URL to the dashboard."""

    def test_root_redirects_signed_in_users_to_the_dashboard(self):
        self.login()

        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/dashboard")

    def test_following_the_redirect_renders_the_dashboard(self):
        self.login()

        response = self.client.get("/", follow_redirects=True)
        body = self.text(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Welcome back", body)
        self.assertIn("How EXECUTE works", body)
        self.assertNotIn("What EXECUTE does", body)

    def test_login_still_lands_on_the_dashboard(self):
        response = self.login()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        body = self.text(self.client.get(response.headers["Location"], follow_redirects=True))
        self.assertIn("Welcome back", body)


class DashboardRouteTests(HomeRouteBase):
    """The dashboard route itself, which requires a session."""

    def test_dashboard_requires_a_login(self):
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")

    def test_dashboard_renders_for_the_signed_in_user(self):
        self.login()

        response = self.client.get("/dashboard")
        body = self.text(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Welcome back", body)
        self.assertIn('href="/tasks"', body)
        self.assertIn("Private task", body)
        self.assertNotIn("Other user task", body)

    def test_dashboard_only_shows_the_signed_in_users_data(self):
        self.login()

        body = self.text(self.client.get("/dashboard"))

        self.assertNotIn("Other user task", body)

        self.login("other-user", "other-password")
        other_body = self.text(self.client.get("/dashboard"))

        self.assertIn("Other user task", other_body)
        self.assertNotIn("Private task", other_body)


if __name__ == "__main__":
    unittest.main()

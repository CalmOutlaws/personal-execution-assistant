from flask import Flask, render_template, request, redirect, url_for
from werkzeug.security import generate_password_hash

from database import get_db, init_db

app = Flask(__name__)


@app.route("/")
def index():
    return "EXECUTE is running."


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            return "Username and password are required."

        password_hash = generate_password_hash(password)

        connection = get_db()

        try:
            connection.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            connection.commit()
        except Exception:
            connection.close()
            return "Username already exists."

        connection.close()

        return redirect(url_for("index"))

    return render_template("register.html")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
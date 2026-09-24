from flask import Flask

app = Flask(__name__)

@ app.route("/")
def index():
    return "Personal Execution Assistant"

if __name__ == "__main__":
    app.run(debug=True)
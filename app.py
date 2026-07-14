"""
Real-Time Chat Application
Flask + Flask-SocketIO + Flask-Login + SQLite

Features:
- User registration & login (authentication)
- Real-time messaging over WebSockets
- Persistent chat history stored in SQLite
"""

from datetime import datetime

from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"


# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "username": self.username,
            "content": self.content,
            "timestamp": self.timestamp.strftime("%H:%M:%S"),
        }


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# Auth Routes
# ---------------------------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.")
            return redirect(url_for("register"))

        if User.query.filter_by(username=username).first():
            flash("Username already taken. Choose another one.")
            return redirect(url_for("register"))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Account created successfully! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("chat"))

        flash("Invalid username or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Chat Route
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def chat():
    return render_template("chat.html", username=current_user.username)


# ---------------------------------------------------------------------------
# SocketIO Events
# ---------------------------------------------------------------------------
@socketio.on("connect")
def handle_connect():
    if not current_user.is_authenticated:
        return False  # reject unauthenticated socket connections

    # Send the last 50 messages as chat history when a user connects
    history = Message.query.order_by(Message.id.desc()).limit(50).all()
    history.reverse()
    emit("chat_history", [m.to_dict() for m in history])

    emit(
        "status",
        {"msg": f"{current_user.username} has joined the chat."},
        broadcast=True,
    )


@socketio.on("disconnect")
def handle_disconnect():
    if current_user.is_authenticated:
        emit(
            "status",
            {"msg": f"{current_user.username} has left the chat."},
            broadcast=True,
        )


@socketio.on("send_message")
def handle_send_message(data):
    if not current_user.is_authenticated:
        return

    content = (data.get("message") or "").strip()
    if not content:
        return

    message = Message(username=current_user.username, content=content)
    db.session.add(message)
    db.session.commit()

    emit("receive_message", message.to_dict(), broadcast=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)

"""
auth.py – Odoo XML-RPC authentication for the chatbot.
"""
from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, render_template

# Import Odoo authentication
from odoo_service import odoo_authenticate

auth_bp = Blueprint("auth", __name__)

# ─── Decorator ────────────────────────────────────────────────────────────────

def login_required(f):
    """Redirect to /login if the user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated

# ─── Routes ───────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        result = odoo_authenticate(username, password)
        
        if result and result.get("success"):
            user_data = result["user_data"]
            session.permanent = True
            session["logged_in"] = True
            session["user_id"] = user_data["uid"]
            session["username"] = user_data["name"]
            return redirect(url_for("index"))
        else:
            error = result.get("error", "An unknown error occurred during authentication.") if result else "Authentication failed."

    return render_template("login.html", error=error)

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

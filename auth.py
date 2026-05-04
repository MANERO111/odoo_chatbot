"""
auth.py – Odoo XML-RPC authentication for the chatbot.
"""
from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, render_template

# Import Odoo authentication and helpers
from odoo_service import odoo_authenticate, odoo_get_commercial_by_uid, odoo_list_companies
from utils import set_state, clear_state

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

            # ── Pre-seed the chat state with commercial + companies ──
            # Use display_name as key — same as session["username"] used in app.py
            _init_chat_state(user_data["name"], user_data["uid"], user_data["name"])

            return redirect(url_for("index"))
        else:
            error = result.get("error", "An unknown error occurred during authentication.") if result else "Authentication failed."

    return render_template("login.html", error=error)

@auth_bp.route("/logout")
def logout():
    # Clear any lingering chat state for this browser session
    clear_state(session.get("username", "default_user"))
    session.clear()
    return redirect(url_for("auth.login"))


# ─── Internal helper ──────────────────────────────────────────────────────────

def _init_chat_state(session_key, uid, display_name):
    """Resolve companies and seed the initial chat state after login.
    session_key must match session['username'] used in app.py (i.e. the display name)."""
    clear_state(session_key)

    comm = odoo_get_commercial_by_uid(uid, display_name)
    commercial_name = comm.get("name", display_name)
    commercial_id   = comm.get("user_id", uid)

    companies = odoo_list_companies()

    if len(companies) > 1:
        set_state(session_key, "CHOOSE_COMPANY",
                  commercial_name=commercial_name,
                  commercial_id=commercial_id,
                  companies=companies)
    else:
        company_id   = companies[0]["id"]   if companies else None
        company_name = companies[0]["name"] if companies else None
        set_state(session_key, "ASK_CLIENT_NAME",
                  commercial_name=commercial_name,
                  commercial_id=commercial_id,
                  company_id=company_id,
                  company_name=company_name)

import os
import json
from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv

load_dotenv()

from utils import set_state, get_state, clear_state, generate_choice_message, generate_company_choice_message
from ai_service import extract_name, extract_order_products, extract_client_details, resolve_product_choice, is_confirmation, is_denial
from odoo_service import (
    odoo_check_client, odoo_create_client, odoo_search_product,
    odoo_create_quotation, odoo_search_commercial, odoo_list_companies
)
from auth import auth_bp, login_required, init_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "icg-copilot-super-secret-2025")
app.config["PERMANENT_SESSION_LIFETIME"] = 3600 * 8  # 8 hours

# Register auth routes (/login, /logout)
app.register_blueprint(auth_bp)

# Ensure users table exists on startup
with app.app_context():
    init_db()

# ─── STEPS ───
STEP_VERIFY_COMMERCIAL = "VERIFY_COMMERCIAL"
STEP_CHOOSE_COMPANY    = "CHOOSE_COMPANY"       # NEW – only when Odoo has > 1 company
STEP_ASK_CLIENT_NAME   = "ASK_CLIENT_NAME"
STEP_CREATE_CLIENT     = "CREATE_CLIENT"
STEP_WAIT_ORDER        = "WAIT_ORDER"
STEP_CONFIRM_MORE      = "CONFIRM_MORE"
STEP_CHOOSE_PRODUCT    = "CHOOSE_PRODUCT"
STEP_ASK_DISCOUNT      = "ASK_DISCOUNT"

@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session.get('username', ''))

@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.json
        incoming_msg = data.get("message", "").strip()
        session_id  = data.get("session_id", "default_user")

        state        = get_state(session_id)
        current_step = state.get("step", STEP_VERIFY_COMMERCIAL)

        print(f"[CHAT] Session: {session_id} | Step: {current_step} | Msg: {incoming_msg}")

        # ──────────────────────────────────────────────
        # STEP 1 – Identify the Commercial
        # ──────────────────────────────────────────────
        if current_step == STEP_VERIFY_COMMERCIAL:
            name = extract_name(incoming_msg)
            comm = odoo_search_commercial(name)

            if comm and comm.get("found"):
                # Fetch companies to decide whether to ask
                companies = odoo_list_companies()

                if len(companies) > 1:
                    # Store everything and ask which company
                    set_state(session_id, STEP_CHOOSE_COMPANY,
                              commercial_name=comm["name"],
                              commercial_id=comm["user_id"],
                              companies=companies)
                    choice_msg = generate_company_choice_message(companies)
                    return reply(
                        f"Marhba bik {comm['name']}! "
                        f"3ndna bzzaf dyal l-companies f Odoo. Afak khtar wahda:\n\n{choice_msg}"
                    )
                else:
                    # Single company – skip straight to client step
                    company_id   = companies[0]["id"]   if companies else None
                    company_name = companies[0]["name"] if companies else None
                    set_state(session_id, STEP_ASK_CLIENT_NAME,
                              commercial_name=comm["name"],
                              commercial_id=comm["user_id"],
                              company_id=company_id,
                              company_name=company_name)
                    return reply(f"Marhba bik {comm['name']}! Chno smit l-client li bghiti t-dir lih la commande?")
            else:
                return reply(f"Malqitouch l-commercial '{name}' f Odoo. Hawel mra khra.")

        # ──────────────────────────────────────────────
        # STEP 1b – Choose which company (multi-company)
        # ──────────────────────────────────────────────
        elif current_step == STEP_CHOOSE_COMPANY:
            companies = state.get("companies", [])
            chosen_company = None

            # Try to parse a number
            try:
                idx = int(incoming_msg.strip()) - 1
                if 0 <= idx < len(companies):
                    chosen_company = companies[idx]
            except ValueError:
                # Try matching by name substring
                for c in companies:
                    if incoming_msg.strip().lower() in c["name"].lower():
                        chosen_company = c
                        break

            if not chosen_company:
                # Re-show the list
                choice_msg = generate_company_choice_message(companies)
                return reply(f"Malqitouch. Afak jawb b rqm sahih:\n\n{choice_msg}")

            set_state(session_id, STEP_ASK_CLIENT_NAME,
                      commercial_name=state.get("commercial_name"),
                      commercial_id=state.get("commercial_id"),
                      company_id=chosen_company["id"],
                      company_name=chosen_company["name"])
            return reply(
                f"Mzyan! Khtarti '{chosen_company['name']}'. "
                f"Chno smit l-client li bghiti t-dir lih la commande?"
            )

        # ──────────────────────────────────────────────
        # STEP 2 – Get the Client name
        # ──────────────────────────────────────────────
        elif current_step == STEP_ASK_CLIENT_NAME:
            msg_lower = incoming_msg.lower()
            # Check if user wants to create a new client
            create_keywords = ["jdid", "creer", "create", "nouveau", "new", "dir wahd", "ssawb wahd"]
            wants_create = any(kw in msg_lower for kw in create_keywords)

            if wants_create:
                last_name = state.get("last_tried_client", incoming_msg)
                set_state(session_id, STEP_CREATE_CLIENT,
                          commercial_name=state.get("commercial_name"),
                          company_id=state.get("company_id"),
                          company_name=state.get("company_name"),
                          client_name=last_name)
                return reply("Okey, ghadi nssawbo client jdid. Afak 3tini smiytho, numero d-telephone, o l-address dyalo.")

            client_name = extract_name(incoming_msg)
            client_data = odoo_check_client(client_name, "")

            if client_data and client_data.get("found"):
                set_state(session_id, STEP_WAIT_ORDER,
                          commercial_name=state.get("commercial_name"),
                          company_id=state.get("company_id"),
                          company_name=state.get("company_name"),
                          client_id=client_data["partner_id"],
                          client_name=client_name,
                          accumulated_products=[])
                comm = state.get("commercial_name", "")
                return reply(f"Lqina l-client '{client_name}'. Okey {comm}, chno bghiti t-commander lih?")
            else:
                # Stay in ASK_CLIENT_NAME so they can retry
                set_state(session_id, STEP_ASK_CLIENT_NAME,
                          commercial_name=state.get("commercial_name"),
                          company_id=state.get("company_id"),
                          company_name=state.get("company_name"),
                          last_tried_client=client_name)
                return reply(f"Malqitouch l-client '{client_name}'. Hawel mra khra, wla gol 'creer jdid' bash nssawbo lih hissab.")

        # ──────────────────────────────────────────────
        # STEP 3 – Create a new Client
        # ──────────────────────────────────────────────
        elif current_step == STEP_CREATE_CLIENT:
            details = extract_client_details(incoming_msg)
            name    = details.get("name") or state.get("client_name")
            phone   = details.get("phone")
            address = details.get("address")

            if phone and address:
                client_id = odoo_create_client(name, phone, address=address)
                if client_id:
                    set_state(session_id, STEP_WAIT_ORDER,
                              commercial_name=state.get("commercial_name"),
                              company_id=state.get("company_id"),
                              company_name=state.get("company_name"),
                              client_id=client_id,
                              client_name=name,
                              accumulated_products=[])
                    comm = state.get("commercial_name", "")
                    return reply(f"L-client '{name}' tssawab! Okey {comm}, chno bghiti t-commander lih?")
                else:
                    return reply("Smhlia, maqdrnach nssawbo l-client. Hawel mn b3d.")
            else:
                return reply("Afak 3tini l-phone o l-address dyal l-client f rissala whda.")

        # ──────────────────────────────────────────────
        # STEP 4 – Receive products
        # ──────────────────────────────────────────────
        elif current_step == STEP_WAIT_ORDER:
            order_data = extract_order_products(incoming_msg)

            if not order_data or not order_data.get("products"):
                return reply("Mafhamtch l-moumtajat. Afak 3awd kteb chno bghiti (ex: 2 table o 3 lampe).")

            state["pending_products"] = order_data["products"]
            state["promo_code"]       = order_data.get("promo_code") or state.get("promo_code")
            state.pop("step", None)
            set_state(session_id, STEP_WAIT_ORDER, **state)
            return process_order_logic(session_id)

        # ──────────────────────────────────────────────
        # STEP 5 – Ask if they want more
        # ──────────────────────────────────────────────
        elif current_step == STEP_CONFIRM_MORE:
            # First: try to extract products (user may have typed them directly)
            order_data = extract_order_products(incoming_msg)
            if order_data and order_data.get("products"):
                state["pending_products"] = order_data["products"]
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return process_order_logic(session_id)

            # Second: check if they said no / finished
            if is_denial(incoming_msg):
                state.pop("step", None)
                set_state(session_id, STEP_ASK_DISCOUNT, **state)
                return reply("Wach 3ndk chi remise l had l-client? (Ila la gol 'la', wla 3tini l-pourcentage bhal '20')")

            # Third: check if they said yes
            if is_confirmation(incoming_msg):
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return reply("Okey, chno l-moumtajat li bghiti t-zid?")

            return reply("Wach bghiti t-zid chi haja khora? (Ah / Non)")

        # ──────────────────────────────────────────────
        # STEP 6 – Choose between similar products
        # ──────────────────────────────────────────────
        elif current_step == STEP_CHOOSE_PRODUCT:
            options = state.get("options", [])
            chosen  = resolve_product_choice(incoming_msg, options)
            if chosen:
                accumulated = state.get("accumulated_products", [])
                current_p   = state.get("current_resolving_product")
                accumulated.append({
                    "product_id": chosen["product_id"],
                    "name": chosen["name"],
                    "qty": current_p.get("qty", 1)
                })
                state["accumulated_products"] = accumulated
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return process_order_logic(session_id)
            else:
                return reply("Afak khtar rqm dyal l-moumtaj mn l-qaima.")

        # ──────────────────────────────────────────────
        # STEP 7 – Ask for discount
        # ──────────────────────────────────────────────
        elif current_step == STEP_ASK_DISCOUNT:
            if is_denial(incoming_msg):
                state["discount"] = None
                state.pop("step", None)
                set_state(session_id, STEP_ASK_DISCOUNT, **state)
                return finalize_quotation(session_id)
            else:
                import re
                match = re.search(r'\d+(\.\d+)?', incoming_msg)
                if match:
                    state["discount"] = float(match.group())
                    state.pop("step", None)
                    set_state(session_id, STEP_ASK_DISCOUNT, **state)
                    return finalize_quotation(session_id)
                else:
                    return reply("Mafhamtch l-pourcentage. Afak 3tini rqm (ex: 20) wla gol 'la'.")

        return reply("Smhlia, mafhamtch. Taqdar t-3awd?")

    except Exception as e:
        import traceback
        print(f"[CRITICAL ERROR] {e}")
        print(traceback.format_exc())
        return jsonify({"reply": "Oops! Kyn chi mochkil f l-server."}), 500


# ─── HELPER: Send a reply ───
def reply(text):
    return jsonify({"reply": text})


# ─── Process the pending product queue ───
def process_order_logic(session_id):
    state       = get_state(session_id)
    pending     = state.get("pending_products", [])
    accumulated = state.get("accumulated_products", [])

    while pending:
        p = pending.pop(0)
        search_results = odoo_search_product(p["name"])

        if not search_results:
            state["pending_products"]     = pending
            state["accumulated_products"] = accumulated
            state.pop("step", None)
            set_state(session_id, STEP_WAIT_ORDER, **state)
            return reply(f"Malqina hta moumtaj b-smit '{p['name']}'. Afak 3awd kteb smiytho.")

        if len(search_results) == 1:
            accumulated.append({
                "product_id": search_results[0]["product_id"],
                "name": search_results[0]["name"],
                "qty": p.get("qty", 1)
            })
        else:
            state.update({
                "options": search_results,
                "current_resolving_product": p,
                "pending_products": pending,
                "accumulated_products": accumulated
            })
            state.pop("step", None)
            set_state(session_id, STEP_CHOOSE_PRODUCT, **state)
            choice_msg = generate_choice_message(search_results)
            return reply(f"B-nisba l '{p['name']}', {choice_msg}")

    # All products resolved → ask if they want more
    state["accumulated_products"] = accumulated
    state["pending_products"]     = []
    state.pop("step", None)
    set_state(session_id, STEP_CONFIRM_MORE, **state)

    added = ", ".join([f"{pr['name']} x{pr['qty']}" for pr in accumulated])
    return reply(f"Tssajlat: {added}. Wach bghiti t-zid chi haja khora?")


# ─── Create the final quotation ───
def finalize_quotation(session_id):
    state       = get_state(session_id)
    accumulated = state.get("accumulated_products", [])
    discount    = state.get("discount")

    if not accumulated:
        return reply("Ma-darti hta moumtaj. Chno bghiti t-order?")

    # Passing discount as a named argument to ensure compatibility and trigger a reload
    result          = odoo_create_quotation(state["client_id"], accumulated, promo_code=state.get("promo_code"), discount=discount)
    commercial_name = state.get("commercial_name", "")
    company_name    = state.get("company_name", "")
    order_name      = result.get("order_name", "???") if result else "???"

    clear_state(session_id)
    set_state(session_id, STEP_VERIFY_COMMERCIAL)

    summary = "\n".join([f"  - {pr['name']} x{pr['qty']}" for pr in accumulated])
    company_line = f" ({company_name})" if company_name else ""
    return reply(
        f"Tm b-njah! L-commande {order_name} tssawbat l-client '{state.get('client_name', '')}'{company_line}.\n\n"
        f"Summary:\n{summary}\n\n"
        f"Chokran {commercial_name}! Ila bghiti t-dir commande khora, kteb smitk."
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

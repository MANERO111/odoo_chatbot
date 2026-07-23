import os
import json
from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
load_dotenv()

from utils import set_state, get_state, clear_state, generate_choice_message, generate_company_choice_message
from ai_service import (
    extract_name, extract_order_products, extract_client_details,
    resolve_product_choice, is_confirmation, is_denial, correct_product_spelling,
    extract_navigation_intent, extract_add_more_quantity, extract_remove_product,
    extract_quantity
)
from odoo_service import (
    odoo_check_client, odoo_create_client, odoo_search_product,
    odoo_create_quotation, odoo_list_companies
)
from auth import auth_bp, login_required

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "icg-copilot-super-secret-2025")
app.config["PERMANENT_SESSION_LIFETIME"] = 3600 * 8  # 8 hours
app.config['APPLICATION_ROOT'] = '/chatbot'
# Register auth routes (/login, /logout)
app.register_blueprint(auth_bp)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)


# ─── STEPS ───
STEP_CHOOSE_COMPANY    = "CHOOSE_COMPANY"       # Select company (when Odoo has > 1)
STEP_ASK_CLIENT_NAME   = "ASK_CLIENT_NAME"
STEP_CREATE_CLIENT     = "CREATE_CLIENT"
STEP_WAIT_ORDER        = "WAIT_ORDER"
STEP_CONFIRM_MORE      = "CONFIRM_MORE"
STEP_CHOOSE_PRODUCT    = "CHOOSE_PRODUCT"
STEP_ASK_QUANTITY      = "ASK_QUANTITY"
STEP_ASK_DISCOUNT      = "ASK_DISCOUNT"


@app.route('/')
@login_required
def index():
    # Force re-seed when loading the main page
    from auth import _init_chat_state
    _init_chat_state(session.get('username'), session.get('user_id'), session.get('username'))
    #
    return render_template('index.html', username=session.get('username', ''))

@app.route('/api/greeting', methods=['GET'])
@login_required
def greeting():
    """Return the initial bot message based on the pre-seeded state."""
    session_id = session.get("username", "default_user")
    state      = get_state(session_id)
    step       = state.get("step", STEP_CHOOSE_COMPANY)
    comm_name  = state.get("commercial_name", session.get("username", ""))

    if step == STEP_CHOOSE_COMPANY:
        companies  = state.get("companies", [])
        choice_msg = generate_company_choice_message(companies)
        msg = (
            f"Marhba bik {comm_name}! "
            f"3ndna bzzaf dyal l-companies f Odoo. Afak khtar wahda:\n\n{choice_msg}"
        )
    else:
        msg = f"Marhba bik {comm_name}! Chno smit l-client li bghiti t-dir lih la commande?"

    return jsonify({"reply": msg, "commercial_name": comm_name})


@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    try:
        data = request.json
        incoming_msg = data.get("message", "").strip()
        # Use the logged-in username as the session key so state is per-user
        session_id  = session.get("username", data.get("session_id", "default_user"))

        state        = get_state(session_id)
        current_step = state.get("step", STEP_CHOOSE_COMPANY)

        print(f"[CHAT] Session: {session_id} | Step: {current_step} | Msg: {incoming_msg}")

        # ──────────────────────────────────────────────
        # CHECK NAVIGATION INTENT FIRST (Step Back / Change Company / Change Client)
        # ──────────────────────────────────────────────
        nav_intent = extract_navigation_intent(incoming_msg)
        print(f"[DEBUG] nav_intent='{nav_intent}' for msg='{incoming_msg}'")
        
        if nav_intent == "CHANGE_COMPANY":
            companies = state.get("companies", [])
            if companies:
                set_state(session_id, STEP_CHOOSE_COMPANY,
                          commercial_name=state.get("commercial_name"),
                          commercial_id=state.get("commercial_id"),
                          companies=companies)
                choice_msg = generate_company_choice_message(companies)
                return reply(f"Wakha, nraj3o l-khtiyar dyal l-company. Afak khtar wahda:\n\n{choice_msg}")
            else:
                return reply("Smhlia, makayninch companies khrin bach tbdelhom.")
                
        elif nav_intent == "CHANGE_CLIENT":
            if current_step != STEP_CHOOSE_COMPANY:
                set_state(session_id, STEP_ASK_CLIENT_NAME,
                          commercial_name=state.get("commercial_name"),
                          commercial_id=state.get("commercial_id"),
                          company_id=state.get("company_id"),
                          company_name=state.get("company_name"),
                          companies=state.get("companies", []))
                return reply("Wakha, nraj3o l-khtiyar dyal l-client. Chno smit l-client li bghiti t-dir lih la commande?")
            else:
                return reply("Mzl makhtarity l-company. Afak khtar company b3da.")
                
        elif nav_intent == "CHANGE_PRODUCTS":
            if current_step not in [STEP_CHOOSE_COMPANY, STEP_ASK_CLIENT_NAME, STEP_CREATE_CLIENT]:
                state["pending_products"] = []
                state["accumulated_products"] = []
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return reply("Wakha, msahna l-moumtajat li khtarti. Chno bghiti t-commander mn jdid?")
            else:
                return reply("Mzl mawsalti l-khtiyar dyal l-moumtajat.")
                
        elif nav_intent == "STEP_BACK":
            if current_step == STEP_ASK_CLIENT_NAME:
                companies = state.get("companies", [])
                if companies:
                    set_state(session_id, STEP_CHOOSE_COMPANY,
                              commercial_name=state.get("commercial_name"),
                              commercial_id=state.get("commercial_id"),
                              companies=companies)
                    choice_msg = generate_company_choice_message(companies)
                    return reply(f"Rja3na l-khtiyar dyal l-company. Afak khtar wahda:\n\n{choice_msg}")
                else:
                    return reply("Hada howa l-awal, ma-taqdarsh tarja3 ktar.")
            elif current_step in [STEP_WAIT_ORDER, STEP_CREATE_CLIENT]:
                set_state(session_id, STEP_ASK_CLIENT_NAME,
                          commercial_name=state.get("commercial_name"),
                          commercial_id=state.get("commercial_id"),
                          company_id=state.get("company_id"),
                          company_name=state.get("company_name"),
                          companies=state.get("companies", []))
                return reply("Rja3na. Chno smit l-client li bghiti t-dir lih la commande?")
            elif current_step in [STEP_CONFIRM_MORE, STEP_CHOOSE_PRODUCT, STEP_ASK_QUANTITY]:
                state["pending_products"] = []
                state.pop("selected_product", None)
                state.pop("options", None)
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return reply("Rja3na l-khtiyar dyal l-moumtajat. Chno bghiti t-commander?")
            elif current_step == STEP_ASK_DISCOUNT:
                state.pop("step", None)
                set_state(session_id, STEP_CONFIRM_MORE, **state)
                return reply("Rja3na. Wach bghiti t-zid chi haja khora?")
            elif current_step == STEP_CHOOSE_COMPANY:
                return reply("Hada howa l-awal, ma-taqdarsh tarja3 ktar.")
                
        elif nav_intent == "SHOW_CART":
            accumulated = state.get("accumulated_products", [])
            if not accumulated:
                return reply("Mzl makhtarti hta moumtaj. Chno bghiti t-commander?")
            else:
                cart_list = "\n".join([f"- {p['name']} x{p['qty']}" for p in accumulated])
                return reply(f"Dakchi li sjlti htal daba:\n{cart_list}\n\nWach bghiti t-zid chi haja khora?")

        # ──────────────────────────────────────────────
        # STEP 1 – Choose which company (multi-company)
        # ──────────────────────────────────────────────
        if current_step == STEP_CHOOSE_COMPANY:
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
            print(f"[DEBUG] extract_order_products result: {order_data}")

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
            # Minus One: check if user wants to remove a product (e.g. "msah product 1", "hayad galby")
            accumulated = state.get("accumulated_products", [])
            remove_idx = extract_remove_product(incoming_msg, accumulated)
            if remove_idx is not None and 0 <= remove_idx < len(accumulated):
                removed = accumulated.pop(remove_idx)
                state["accumulated_products"] = accumulated
                state.pop("step", None)
                set_state(session_id, STEP_CONFIRM_MORE, **state)
                return reply(f"Msahna {removed['name']} mn l-commande. Wach bghiti t-zid chi haja khora?")

            # Zero: check if user wants to add more qty of the LAST product (e.g. "zidni mno 3")
            add_qty_info = extract_add_more_quantity(incoming_msg)
            if add_qty_info and add_qty_info.get("qty"):
                qty = add_qty_info["qty"]
                action = add_qty_info["action"]
                accumulated = state.get("accumulated_products", [])
                if accumulated:
                    if action == "set":
                        accumulated[-1]["qty"] = qty
                        msg_action = "Badalna l-qte!"
                    else:
                        accumulated[-1]["qty"] = accumulated[-1].get("qty", 1) + qty
                        msg_action = "Zidna!"
                    state["accumulated_products"] = accumulated
                    state.pop("step", None)
                    set_state(session_id, STEP_CONFIRM_MORE, **state)
                    last_name = accumulated[-1]["name"]
                    last_qty  = accumulated[-1]["qty"]
                    return reply(f"{msg_action} {last_name} wslat l {last_qty}. Wach bghiti t-zid chi haja khora?")
                else:
                    return reply("Ma-kaynch moumtaj f l-qaima bach nbadlo l-qte dyalo. Chno bghiti t-commander?")

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
            if is_denial(incoming_msg):
                state.pop("options", None)
                state.pop("current_resolving_product", None)
                state.pop("step", None)
                state["pending_products"] = []
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return reply("Okey, chno l-moumtajat li bghiti t-zid?")
                
            options = state.get("options", [])
            chosen  = resolve_product_choice(incoming_msg, options)
            if chosen:
                state.pop("options", None)
                state.pop("current_resolving_product", None)
                state["selected_product"] = {
                    "product_id": chosen["product_id"],
                    "name": chosen["name"]
                }
                state.pop("step", None)
                set_state(session_id, STEP_ASK_QUANTITY, **state)
                return reply(f"Khtarti: '{chosen['name']}'. Chhal d-la quantité li bghiti mnou?")
            else:
                return reply("Afak khtar rqm dyal l-moumtaj mn l-qaima.")

        # ──────────────────────────────────────────────
        # STEP 6.5 – Ask quantity for selected product
        # ──────────────────────────────────────────────
        elif current_step == STEP_ASK_QUANTITY:
            selected_product = state.get("selected_product")
            if not selected_product:
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return reply("Mzl makhtarti hta moumtaj. Chno bghiti t-commander?")

            if is_denial(incoming_msg):
                state.pop("selected_product", None)
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return reply("Okey, cancelna l-moumtaj. Chno bghiti t-commander?")

            qty = extract_quantity(incoming_msg)
            if qty and isinstance(qty, int) and qty > 0:
                accumulated = state.get("accumulated_products", [])
                accumulated.append({
                    "product_id": selected_product["product_id"],
                    "name": selected_product["name"],
                    "qty": qty
                })
                state["accumulated_products"] = accumulated
                state.pop("selected_product", None)
                state.pop("step", None)
                set_state(session_id, STEP_WAIT_ORDER, **state)
                return process_order_logic(session_id)
            else:
                p_name = selected_product.get("name", "l-moumtaj")
                return reply(f"Afak 3tini rqm sahih d-la quantité d '{p_name}' (ex: 1, 2, 5...).")

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
        corrected_name = correct_product_spelling(p["name"])
        print(f"[Product Search] Original: '{p['name']}' -> Corrected: '{corrected_name}'")
        search_results = odoo_search_product(corrected_name)

        if not search_results:
            state["pending_products"]     = pending
            state["accumulated_products"] = accumulated
            state.pop("step", None)
            set_state(session_id, STEP_WAIT_ORDER, **state)
            return reply(f"Malqina hta moumtaj b-smit '{p['name']}'. Afak 3awd kteb smiytho.")

        if len(search_results) == 1:
            single = search_results[0]
            state.update({
                "selected_product": {
                    "product_id": single["product_id"],
                    "name": single["name"]
                },
                "pending_products": pending,
                "accumulated_products": accumulated
            })
            state.pop("step", None)
            set_state(session_id, STEP_ASK_QUANTITY, **state)
            return reply(f"Lqina: '{single['name']}'. Chhal d-la quantité li bghiti mnou?")
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

    # Passing discount and commercial_id as named arguments to ensure compatibility
    result          = odoo_create_quotation(
        state["client_id"], 
        accumulated, 
        promo_code=state.get("promo_code"), 
        discount=discount,
        user_id=state.get("commercial_id")
    )
    commercial_name = state.get("commercial_name", "")
    company_name    = state.get("company_name", "")
    order_name      = result.get("order_name", "???") if result else "???"

    clear_state(session_id)
    # Re-seed state so the user can immediately start a new order
    from auth import _init_chat_state
    _init_chat_state(session_id, session.get("user_id"), session.get("username"))

    # Find the new initial step to tell the user what to do next
    new_state    = get_state(session_id)
    next_step    = new_state.get("step", STEP_ASK_CLIENT_NAME)
    new_companies = new_state.get("companies", [])

    summary = "\n".join([f"  - {pr['name']} x{pr['qty']}" for pr in accumulated])
    company_line = f" ({company_name})" if company_name else ""

    if next_step == STEP_CHOOSE_COMPANY:
        choice_msg = generate_company_choice_message(new_companies)
        followup = f"\n\nBghiti dir commande khora? Khtar l-company:\n{choice_msg}"
    else:
        followup = f"\n\nBghiti dir commande khora? Chno smit l-client?"

    return reply(
        f"Tm b-njah! L-commande {order_name} tssawbat l-client '{state.get('client_name', '')}'{company_line}.\n\n"
        f"Summary:\n{summary}\n\n"
        f"Chokran {commercial_name}!{followup}"
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

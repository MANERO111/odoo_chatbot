import requests
import os
import json
import xmlrpc.client

def get_config():
    ODOO_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
    ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "your_secure_api_key_here")
    return ODOO_URL, ODOO_API_KEY

def odoo_list_companies():
    """Return a list of all companies from Odoo: [{"id": 1, "name": "..."}, ...]"""
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/list_companies",
            json={"params": {}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code == 200:
            companies = response.json().get('result', [])
            
            # Filter by ALLOWED_COMPANIES from .env if present
            allowed_str = os.environ.get("ALLOWED_COMPANIES", "").strip()
            if allowed_str:
                allowed_ids = [int(x.strip()) for x in allowed_str.split(",") if x.strip().isdigit()]
                if allowed_ids:
                    companies = [c for c in companies if c.get("id") in allowed_ids]
                    
            return companies
        return []
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - list_companies failed: {e}")
        return []

def odoo_check_client(name, phone):
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/check_client", 
            json={"params": {"name": name, "phone": phone}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get('result', {"found": False})
        return {"found": False}
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - check_client failed: {e}")
        return None

def odoo_search_commercial(name):
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/search_commercial",
            json={"params": {"name": name}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get('result', {"found": False})
        return {"found": False}
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - search_commercial failed: {e}")
        return None

def odoo_get_commercial_by_uid(uid, name):
    """Look up the commercial (res.users) record by Odoo UID.
    Returns {"found": True, "name": ..., "user_id": ...} or {"found": False}."""
    ODOO_URL, ODOO_API_KEY = get_config()
    # First try by name (same endpoint as search_commercial)
    try:
        response = requests.post(
            f"{ODOO_URL}/api/search_commercial",
            json={"params": {"name": name}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code == 200:
            result = response.json().get('result', {"found": False})
            if result.get("found"):
                return result
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - get_commercial_by_uid (name lookup) failed: {e}")
    # Fallback: use uid as the user_id directly
    return {"found": True, "name": name, "user_id": uid}

def odoo_create_client(name, phone, email=None, address=None):
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/create_client",
            json={"params": {"name": name, "phone": phone, "email": email, "address": address}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code in (200, 201):
             return response.json().get('result', {}).get("partner_id")
        return None
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - create_client failed: {e}")
        return None

def odoo_search_product(product_name):
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/search_product",
            json={"params": {"product_name": product_name, "sale_ok": True}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json().get('result', {})
            if data.get("found"):
                products = data.get("products", [])
                # Client-side safety filter: exclude products explicitly marked as not saleable
                products = [p for p in products if p.get("sale_ok", True) is not False]
                return products
        return []
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - search_product failed: {e}")
        return None


def odoo_create_quotation(partner_id, products, promo_code=None, discount=None, user_id=None):
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/create_quotation",
            json={"params": {
                "partner_id": partner_id, 
                "products": products, 
                "promo_code": promo_code, 
                "discount": discount,
                "user_id": user_id
            }},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=10
        )
        if response.status_code in (200, 201):
            result = response.json().get('result', {})
            return {
                "order_id": result.get("order_id"),
                "order_name": result.get("order_name", f"#{result.get('order_id')}")
            }
        return None
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - create_quotation failed: {e}")
        return None

def odoo_authenticate(username, password):
    ODOO_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
    ODOO_DB = os.environ.get("ODOO_DB", "")
    
    if not ODOO_DB:
        print("[Odoo Auth Error] - ODOO_DB is not set in environment variables.")
        return {"success": False, "error": "Configuration error: ODOO_DB is not set."}

    try:
        print(f"[Odoo Auth Debug] - Attempting to authenticate user '{username}' on DB '{ODOO_DB}' at '{ODOO_URL}'")
        common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
        uid = common.authenticate(ODOO_DB, username, password, {})
        print(f"[Odoo Auth Debug] - Authentication result UID: {uid}")
        
        if uid:
            models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
            
            # Check if user has access to sales
            try:
                has_sales_access = models.execute_kw(ODOO_DB, uid, password, 'res.users', 'has_group', ['sales_team.group_sale_salesman'])
                print(f"[Odoo Auth Debug] - has_sales_access: {has_sales_access}")
            except Exception as e:
                print(f"[Odoo Auth Debug] - Exception during has_group check: {e}")
                has_sales_access = False
            
            if not has_sales_access:
                print(f"[Odoo Auth Error] - User {username} does not have sales access (sales_team.group_sale_salesman).")
                # Also try checking if they are just an internal user
                is_employee = models.execute_kw(ODOO_DB, uid, password, 'res.users', 'has_group', ['base.group_user'])
                print(f"[Odoo Auth Debug] - is_employee (base.group_user): {is_employee}")
                return {"success": False, "error": f"Authenticated successfully, but user lacks the required sales permissions (sales_team.group_sale_salesman). Employee access: {is_employee}"}

            user_data = models.execute_kw(ODOO_DB, uid, password, 'res.users', 'read', [[uid]], {'fields': ['name', 'login']})
            if user_data:
                return {
                    "success": True,
                    "user_data": {
                        "uid": uid,
                        "name": user_data[0].get("name"),
                        "login": user_data[0].get("login")
                    }
                }
            else:
                return {"success": False, "error": "Could not read user data after authentication."}
        else:
            print(f"[Odoo Auth Error] - common.authenticate returned False/None for {username}.")
            return {"success": False, "error": "Invalid username or password."}
    except Exception as e:
        import traceback
        print(f"[Odoo Auth Error] - Authentication failed with exception:")
        traceback.print_exc()
        return {"success": False, "error": f"Server error during authentication: {str(e)}"}

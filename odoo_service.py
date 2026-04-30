import requests
import os
import json

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
            return response.json().get('result', [])
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
            json={"params": {"product_name": product_name}},
            headers={"X-API-KEY": ODOO_API_KEY},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json().get('result', {})
            if data.get("found"):
                return data.get("products", [])
        return []
    except requests.RequestException as e:
        print(f"[Odoo Sync Error] - search_product failed: {e}")
        return None

def odoo_create_quotation(partner_id, products, promo_code=None, discount=None):
    ODOO_URL, ODOO_API_KEY = get_config()
    try:
        response = requests.post(
            f"{ODOO_URL}/api/create_quotation",
            json={"params": {"partner_id": partner_id, "products": products, "promo_code": promo_code, "discount": discount}},
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

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def extract_name(message):
    """
    Extract a person's name from a natural language message.
    Examples:
      "ana marc" -> "marc"
      "smiti adam" -> "adam"
      "lclient smito John Doe" -> "John Doe"
      "John Doe" -> "John Doe"
    """
    prompt = (
        f"Extract only the person's name from this message: '{message}'. "
        "Respond with ONLY the name, nothing else. If no name is found, respond with the original message as-is."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=30
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[AI Error] extract_name: {e}")
        return message.strip()


def extract_order_products(message):
    """
    Extract products and quantities from a natural language order message.
    Returns: {"products": [{"name": "...", "qty": N}], "promo_code": "..." or null}
    """
    prompt = f"""
    Extract products and quantities from this message: '{message}'
    Return a JSON object: {{"products": [{{"name": "product name", "qty": number}}], "promo_code": "string or null"}}
    If no products found, return {{"products": []}}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a data extraction assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        if "products" not in data:
            data["products"] = []
        return data
    except Exception as e:
        print(f"[AI Error] extract_order_products: {e}")
        return None


def is_confirmation(message):
    """
    Check if the user is saying 'yes' / confirming.
    """
    msg = message.lower().strip()
    yes_words = ["ah", "oui", "yes", "iyeh", "wah", "ok", "okay", "safi", "d'accord",
                 "bien sur", "tab3an", "mzyan", "bikhir", "bghit", "zid", "encore"]
    return any(w in msg for w in yes_words)


def is_denial(message):
    """
    Check if the user is saying 'no' / finishing.
    Uses whole-word matching to avoid false positives (e.g. 'blanc' matching 'la').
    """
    import re
    msg = message.lower().strip()
    no_words = ["non", "no", "la", "baraka", "safi", "khlas", "hadchi", "c'est tout",
                "that's it", "thats it", "sf", "bas", "chokran"]
    for w in no_words:
        if re.search(r'\b' + re.escape(w) + r'\b', msg):
            return True
    return False


def extract_client_details(message):
    """
    Extract client details (name, phone, address) from a message.
    """
    prompt = f"""
    Extract client details from this message: '{message}'
    Return a JSON object with: "name", "phone", "address".
    If a field is missing, use null.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a data extraction assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[AI Error] extract_client_details: {e}")
        return {}


def resolve_product_choice(user_input, options):
    """
    Resolve which product the user chose from a list of options.
    """
    options_json = json.dumps([{"id": i + 1, "name": o["name"]} for i, o in enumerate(options)])
    prompt = (
        f"User was shown: {options_json}. "
        f"User replied: '{user_input}'. "
        f"Return ONLY the numeric ID chosen (1-{len(options)}) or 0 if unclear."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Return ONLY an integer."},
                      {"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        choice = int(response.choices[0].message.content.strip())
        if 1 <= choice <= len(options):
            return options[choice - 1]
        return None
    except Exception:
        return None

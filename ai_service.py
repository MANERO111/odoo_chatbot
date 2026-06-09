import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# Configurable model — set AI_MODEL in .env to switch (e.g. gpt-4o, gpt-4o-mini)
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o")


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
            model=AI_MODEL,
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
You are a smart order assistant for a Moroccan salesperson. Extract products and quantities from this message: '{message}'

IMPORTANT RULES:
1. If the user gives only a brand/product name with NO quantity (e.g., "galby", "magiclear", "bghit galby"), extract it with qty = 1.
2. If the user asks for a list of products (e.g., "la liste dyal X", "3tini list X", "wrin liya products X", "3tini list products X") → extract ONLY the brand/product name X with qty = 1. DO NOT include words like "list", "liste", "products", or "moumtajat" in the extracted name. For example, if they say "3tini list galby", extract "galby", NOT "list galby".
3. If the user gives a quantity + name (e.g., "2 galby", "3 table"), use that quantity.
4. Messages can be in French, English, or Moroccan Darija (e.g., "bghit", "3tini", "khtar", "zidni").
5. Extract ALL products mentioned. Each product gets its own entry.
6. If truly no product name is identifiable (e.g., pure navigation commands like "rje3", "back", "la"), return {{"products": []}}.
7. CRITICAL: DO NOT split a single product into multiple entries. E.g., if the user says "2 galby creme", that is ONE product with name "galby creme" and qty 2. Do not separate it into "galby" and "creme".

Return a JSON object: {{"products": [{{"name": "product name", "qty": number}}], "promo_code": "string or null"}}
"""
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
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


def extract_navigation_intent(message):
    """
    Check if the user wants to navigate backwards or change a previous selection.
    Returns one of: "CHANGE_COMPANY", "CHANGE_CLIENT", "STEP_BACK", or null.
    """
    prompt = f"""
    Analyze this message: '{message}'
    Determine if the user's PRIMARY intent is to navigate backwards or change a previous selection.
    Categories:
    - "CHANGE_COMPANY": User wants to change the selected company (e.g., "change company", "company akhra", "nbdel charika").
    - "CHANGE_CLIENT": User wants to change the selected client (e.g., "change client", "client akhor", "nbdl lclient").
    - "CHANGE_PRODUCTS": User wants to clear their cart, change products, or restart product selection (e.g., "bghit n3awd nkhtar lproducts", "change products", "nbdl la commande").
    - "STEP_BACK": User just wants to go back one step (examples: "step back", "rje3 lor", "rje3 mara khra", "back").
    - "SHOW_CART": User wants to see the products they have ALREADY SELECTED in their cart (e.g., "wrini chno sjlti", "chno dert", "show cart", "la liste dyal dakchi li khtart", "wrini la commande dyali"). DO NOT use this if the user asks for a list of products from a brand.
    - null: The message is an order for a SPECIFIC product (e.g., "bghit 2 magiclear gel", "3 galby creme"), answering a question, giving a number ("1", "2"), giving a name, or anything else.
    
    CRITICAL RULE 1: If the user is asking to view their CURRENT CART (e.g., "chno khtarit", "chno sjlti"), return "SHOW_CART". If they ask to see a brand's products (e.g., "wrini products galby", "list products galby"), it is NOT a cart, return null.
    CRITICAL RULE 2: If the user provides an order with a quantity and a specific product name or just a product name (e.g., "bghit 2 magiclear", "pdv", "2 soivre", "galby creme", "biomed"), it is an ORDER, NOT a navigation intent. Return null. Do not confuse brand names (like 'magiclear', 'soivre', 'galby', 'pdv', 'biomed', etc) with commands.
    CRITICAL RULE 3: If the user asks for a LIST of products from a specific brand (e.g., "3tini list products galby", "la liste dyal magiclear", "wrini products galby"), it is a PRODUCT SEARCH, NOT a navigation intent. Return null.
    CRITICAL RULE 4: Single unrecognized words (like "reistill", "cleare", "alfaderm", "biomed") are PRODUCT SEARCHES. They are NOT navigation intents. Do not mistake "cleare" for "clear products", and do not mistake "reistill" for "step back". Return null.
    CRITICAL RULE 5: ONLY return a navigation intent if the user explicitly uses clear navigation phrases (like "rje3 lor", "msah lcommande kamla"). Do not assume a single English/French word is a navigation command.
    CRITICAL RULE 6: If the user wants to remove ONE SPECIFIC product from their cart (e.g., "msah product 2", "hayad galby", "delete 1"), return null. This is NOT a navigation intent. ONLY return "CHANGE_PRODUCTS" if they want to clear the ENTIRE cart (e.g., "msah kolchi", "delete all products", "msah lcommande kamla").
    If in doubt, return null. Return a JSON object: {{"intent": "CHANGE_COMPANY" | "CHANGE_CLIENT" | "CHANGE_PRODUCTS" | "STEP_BACK" | "SHOW_CART" | null}}
    """
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are an intent classification assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        data = json.loads(response.choices[0].message.content)
        return data.get("intent")
    except Exception as e:
        print(f"[AI Error] extract_navigation_intent: {e}")
        return None


def extract_add_more_quantity(message):
    """
    Detect if the user wants to add more of the LAST ordered product.
    Examples:
      "zidni mno 3"  -> 3
      "add 3 more"   -> 3
      "zid 5 mn nfs chi" -> 5
      "3 mn dak"     -> 3
      "encore 2"     -> 2
    Returns: integer quantity to add, or None if this is NOT an "add more" intent.
    """
    prompt = f"""
Analyze this message: '{message}'
Determine if the user wants to ADD MORE QUANTITY of the LAST product they ordered (not a new product).
Phrases that indicate this intent (in Darija/French/English):
- "zidni mno N", "zid mno N", "zidni N mn nfs chi", "N mn dak", "encore N", "add N more", "N more of that", "zid N", "zidni N"

Rules:
- Only return a quantity if the user clearly means "add more of the SAME last product" WITHOUT mentioning a product name.
- CRITICAL: If the user explicitly mentions ANY brand name, product name, or unrecognized word (e.g., "2 magiclear", "galby", "soivre", "table", "2 biomed", "pdv"), DO NOT return a quantity. Return null, because they are starting a new search/order for that product.
- Only allow words that mean "more", "of it", "from that" (like "mno", "mn nfs chi", "dak", "encore", "more"). If there are other words (like "biomed", "galby", "magiclear", "creme"), return null.
- If unclear, return null.

Return JSON: {{"add_qty": number_or_null}}
"""
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are an intent classifier. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=30
        )
        data = json.loads(response.choices[0].message.content)
        qty = data.get("add_qty")
        if qty and isinstance(qty, (int, float)) and qty > 0:
            return int(qty)
        return None
    except Exception as e:
        print(f"[AI Error] extract_add_more_quantity: {e}")
        return None


def extract_remove_product(message, accumulated_products):
    """
    Detect if the user wants to remove a product from their cart.
    Examples: "msah product 1", "hayad galby", "supprimer lwl"
    Returns the 0-based index to remove, or None.
    """
    if not accumulated_products:
        return None
        
    cart_info = [{"index": i, "name": p["name"]} for i, p in enumerate(accumulated_products)]
    prompt = f"""
Analyze this message: '{message}'
The user's current cart is: {json.dumps(cart_info)}

Determine if the user explicitly wants to REMOVE/DELETE a product from this cart.
If yes, identify WHICH product they mean, and return its EXACT 'index' (which is 0-based).
- If they say "msah product 1", "hayad lwl", or "1", they mean the 1st product in the list -> index 0.
- If they say "msah 2" or "delete product 2", they mean the 2nd product in the list -> index 1.
- If they give a name (e.g., "msah magiclear serum clarifiant"), you MUST find the item in the cart whose name BEST matches the user's input. Do not just pick the first item that contains a matching word. Pick the one that is the closest match.

CRITICAL RULES:
1. ONLY return an index if the user EXPLICITLY uses a removal word like "msah", "hayad", "delete", "remove", "supprimer".
2. If the user DOES NOT use a removal word (e.g., they just say "2 galby", "magiclear"), it is an order, NOT a removal. Return null.

Return JSON ONLY: {{"remove_index": integer_or_null}}
"""
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=30
        )
        data = json.loads(response.choices[0].message.content)
        idx = data.get("remove_index")
        if isinstance(idx, int) and 0 <= idx < len(accumulated_products):
            return idx
        return None
    except Exception as e:
        print(f"[AI Error] extract_remove_product: {e}")
        return None



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
            model=AI_MODEL,
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

def correct_product_spelling(product_name):
    """
    Correct the spelling of a product name that might contain typos (e.g., phonetic spelling).
    """
    prompt = (
        f"Correct the spelling of this product name: '{product_name}'. "
        "It might be in French, English, or Moroccan Darija. "
        "Fix phonetic mistakes (e.g. 'crime' -> 'creme', 'ecron soler' -> 'ecran solaire', 'gil douche' -> 'gel douche'). "
        "CRITICAL RULE 1: DO NOT correct or change brand names. Preserve these exactly as typed: "
        "'galby', 'magiclear', 'biomed', 'alfaderm', 'cosmetix', 'evoluderm', 'pdv', 'soivre', 'alfa' ,'reistill', 'dentyucral','cleare','davaj','capilift'. "
        "CRITICAL RULE 2: DO NOT add any extra words. NEVER attempt to guess or auto-complete the product name. Only fix the spelling of the words provided. "
        "Respond ONLY with the corrected name, nothing else."
    )
    try:
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=30
        )
        corrected = response.choices[0].message.content.strip()
        
        # Hardcode fix for stubborn AI translation of 'galby'
        if "galby" in product_name.lower() and "galbi" in corrected.lower():
            corrected = corrected.lower().replace("galbi", "galby")
            
        return corrected
    except Exception as e:
        print(f"[AI Error] correct_product_spelling: {e}")
        return product_name.strip()

